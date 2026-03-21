#!/usr/bin/env python3
"""
Script: seasonal_analyzer.py
Purpose: Plot a 12-month BSR seasonality curve using Keepa historical data,
         identify optimal buy/sell windows, and use Google Trends to confirm
         demand signals for Amazon FBA sourcing decisions.
Inputs:  --asin, --keyword, --file
Outputs: JSON to stdout, progress to stderr
"""

import argparse
import ast
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
    from dotenv import load_dotenv
    from pytrends.request import TrendReq
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    sys.exit(1)

load_dotenv(Path(__file__).parent.parent / ".env")

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY")
KEEPA_BASE_URL = "https://api.keepa.com/product"
KEEPA_EPOCH = datetime(2011, 1, 1)

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# ---------------------------------------------------------------------------
# Keepa helpers
# ---------------------------------------------------------------------------

def _keepa_time_to_datetime(keepa_minutes: int) -> datetime:
    """Convert Keepa integer timestamp (minutes since 2011-01-01) to datetime."""
    return KEEPA_EPOCH + timedelta(minutes=keepa_minutes)


def _parse_bsr_history(csv_data: list) -> dict[int, list[int]]:
    """Parse BSR history from Keepa csv index 3.

    Returns dict mapping calendar month (1–12) → list of BSR readings.
    """
    if not csv_data or len(csv_data) < 4 or not csv_data[3]:
        return {}

    arr = csv_data[3]  # index 3 = sales rank history
    monthly: dict[int, list[int]] = {m: [] for m in range(1, 13)}
    cutoff = datetime.utcnow() - timedelta(days=365)

    i = 0
    while i < len(arr) - 1:
        keepa_time = arr[i]
        value = arr[i + 1]
        i += 2
        if keepa_time < 0 or value < 0:
            continue
        dt = _keepa_time_to_datetime(keepa_time)
        if dt < cutoff:
            continue
        monthly[dt.month].append(value)

    return monthly


def _compute_monthly_medians(monthly_raw: dict[int, list[int]]) -> dict[str, int | None]:
    """Return month-name → median BSR dict."""
    result: dict[str, int | None] = {}
    for m in range(1, 13):
        readings = monthly_raw.get(m, [])
        result[MONTH_NAMES[m - 1]] = int(median(readings)) if readings else None
    return result


def fetch_keepa_history(asin: str) -> dict:
    """Fetch 365-day Keepa BSR history for an ASIN.

    Returns dict with product_name, monthly_bsr, and raw monthly data.
    """
    if not KEEPA_API_KEY:
        print("ERROR: KEEPA_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    print(f"  Fetching Keepa history for {asin}…", file=sys.stderr)
    params = {
        "key": KEEPA_API_KEY,
        "domain": "1",
        "asin": asin,
        "stats": "365",
        "history": "1",
    }
    try:
        resp = requests.get(KEEPA_BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"ERROR: Keepa API request failed — {exc}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    if not data.get("products"):
        print(f"ERROR: No Keepa data found for ASIN {asin}", file=sys.stderr)
        sys.exit(1)

    product = data["products"][0]
    product_name = product.get("title") or "Unknown Product"
    csv_data = product.get("csv", [])

    monthly_raw = _parse_bsr_history(csv_data)
    monthly_bsr = _compute_monthly_medians(monthly_raw)

    print(f"  Parsed BSR data for: {product_name}", file=sys.stderr)
    return {
        "product_name": product_name,
        "monthly_bsr": monthly_bsr,
        "monthly_raw": monthly_raw,
    }


# ---------------------------------------------------------------------------
# Seasonality analysis helpers
# ---------------------------------------------------------------------------

def _identify_windows(monthly_bsr: dict[str, int | None]) -> tuple[list[str], list[str], list[str]]:
    """Identify peak demand, buy window, and sell window from monthly BSR.

    Lower BSR = higher demand. Peak demand = lowest BSR month(s).
    Buy window = 1–2 months before peak (ship to FBA).
    Sell window = peak month(s) ± 1.
    """
    valid = {name: bsr for name, bsr in monthly_bsr.items() if bsr is not None}
    if not valid:
        return [], [], []

    min_bsr = min(valid.values())
    # All months within 15% of the minimum are peak months
    peak_threshold = min_bsr * 1.15
    peak_months = [name for name, bsr in valid.items() if bsr <= peak_threshold]

    month_indices = {name: i for i, name in enumerate(MONTH_NAMES)}
    peak_indices = sorted(month_indices[m] for m in peak_months)

    # Buy window: 1–2 months before earliest peak (circular)
    buy_indices = set()
    for pi in peak_indices:
        buy_indices.add((pi - 1) % 12)
        buy_indices.add((pi - 2) % 12)
    # Exclude months that are already peak
    buy_indices -= set(peak_indices)
    buy_months = [MONTH_NAMES[i] for i in sorted(buy_indices)]

    # Sell window: peak months + 1 month after last peak
    sell_indices = set(peak_indices)
    for pi in peak_indices:
        sell_indices.add((pi + 1) % 12)
    sell_months = [MONTH_NAMES[i] for i in sorted(sell_indices)]

    return peak_months, buy_months, sell_months


def _compute_seasonal_score(monthly_bsr: dict[str, int | None]) -> int:
    """Score 0–20 for how seasonal the product is.

    High variance between best and worst month = more seasonal = higher score.
    """
    values = [v for v in monthly_bsr.values() if v is not None]
    if len(values) < 3:
        return 0
    min_bsr = min(values)
    max_bsr = max(values)
    ratio = max_bsr / min_bsr if min_bsr > 0 else 1.0
    # ratio of 1 = not seasonal, ratio of 5+ = highly seasonal
    score = min(20, int((ratio - 1.0) / 4.0 * 20))
    return score


def _timing_verdict(
    monthly_bsr: dict[str, int | None],
    peak_months: list[str],
    buy_months: list[str],
    sell_months: list[str],
    trends_momentum: str,
    current_month_name: str,
) -> tuple[str, str, str]:
    """Return (timing_label, confidence, recommendation) for the current month."""
    valid = {name: bsr for name, bsr in monthly_bsr.items() if bsr is not None}
    if not valid or not peak_months:
        return "UNKNOWN", "LOW", "Insufficient data to make a timing recommendation."

    annual_avg = sum(valid.values()) / len(valid)
    current_bsr = valid.get(current_month_name)

    # Determine timing label
    if current_month_name in buy_months:
        timing = "BUY"
    elif current_month_name in sell_months and current_month_name not in peak_months:
        timing = "SELL_WINDOW"
    elif current_month_name in peak_months:
        timing = "SELL_WINDOW"
    elif current_bsr is not None and current_bsr > annual_avg * 2.0:
        timing = "AVOID"
    else:
        # Determine EARLY vs LATE relative to nearest peak
        month_indices = {name: i for i, name in enumerate(MONTH_NAMES)}
        current_idx = month_indices[current_month_name]
        nearest_peak_idx = min(
            (month_indices[p] for p in peak_months),
            key=lambda pi: min((pi - current_idx) % 12, (current_idx - pi) % 12),
        )
        months_until_peak = (nearest_peak_idx - current_idx) % 12
        if months_until_peak >= 3:
            timing = "EARLY"
        else:
            timing = "LATE"

    # Confidence
    data_completeness = len(valid) / 12
    has_trends = trends_momentum in ("rising", "stable")
    if data_completeness >= 0.75 and has_trends and timing in ("BUY", "SELL_WINDOW"):
        confidence = "HIGH"
    elif data_completeness >= 0.5:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # Boost confidence if trends confirm
    if trends_momentum == "rising" and timing == "BUY":
        confidence = "HIGH"

    # Build recommendation text
    month_indices = {name: i for i, name in enumerate(MONTH_NAMES)}
    if buy_months:
        earliest_buy = min(buy_months, key=lambda m: (month_indices[m] - month_indices[current_month_name]) % 12)
    else:
        earliest_buy = None

    peak_str = "/".join(peak_months) if peak_months else "unknown"

    if timing == "BUY":
        rec = f"Ship inventory now to be in stock for the {peak_str} demand peak."
    elif timing == "SELL_WINDOW":
        rec = f"Peak demand is now ({peak_str}). Focus on repricing and review generation."
    elif timing == "EARLY":
        months_away = min((month_indices[p] - month_indices[current_month_name]) % 12 for p in peak_months)
        if earliest_buy:
            rec = f"Peak is {months_away} month(s) away. Plan to ship inventory in {earliest_buy}."
        else:
            rec = f"Peak is {months_away} month(s) away. Hold sourcing for now."
    elif timing == "LATE":
        rec = f"Demand is declining after {peak_str} peak. Wait for next cycle before sourcing."
    elif timing == "AVOID":
        rec = "Counter-seasonal period — BSR well above annual average. Avoid sourcing now."
    else:
        rec = "Not enough historical data to give a confident recommendation."

    return timing, confidence, rec


# ---------------------------------------------------------------------------
# Google Trends helpers
# ---------------------------------------------------------------------------

def fetch_google_trends(keyword: str) -> dict:
    """Fetch 12-month Google Trends data for a keyword.

    Returns dict with weekly_interest list, current_momentum, and monthly averages.
    """
    print(f"  Fetching Google Trends for: '{keyword}'…", file=sys.stderr)
    try:
        pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        pytrends.build_payload([keyword], cat=0, timeframe="today 12-m", geo="US")
        time.sleep(1)  # polite delay
        df = pytrends.interest_over_time()
    except Exception as exc:
        print(f"WARNING: Google Trends fetch failed — {exc}", file=sys.stderr)
        return {"error": str(exc), "weekly_interest": [], "current_momentum": "unknown"}

    if df is None or df.empty or keyword not in df.columns:
        return {"weekly_interest": [], "current_momentum": "unknown", "monthly_interest": {}}

    series = df[keyword].tolist()
    dates = df.index.tolist()

    # Build weekly interest pairs
    weekly = [
        {"date": str(d.date()), "interest": int(v)}
        for d, v in zip(dates, series)
    ]

    # Monthly averages (group by year-month, use last 12 months)
    monthly_totals: dict[str, list[int]] = {}
    for d, v in zip(dates, series):
        key = MONTH_NAMES[d.month - 1]
        monthly_totals.setdefault(key, []).append(int(v))
    monthly_interest = {k: int(sum(v) / len(v)) for k, v in monthly_totals.items()}

    # Detect momentum: compare last 4 weeks vs weeks 5-12
    if len(series) >= 12:
        recent = sum(series[-4:]) / 4
        prior = sum(series[-12:-4]) / 8
        if prior == 0:
            momentum = "rising" if recent > 10 else "stable"
        elif recent > prior * 1.15:
            momentum = "rising"
        elif recent < prior * 0.85:
            momentum = "falling"
        else:
            momentum = "stable"
    else:
        momentum = "unknown"

    print(f"  Trends momentum: {momentum}", file=sys.stderr)
    return {
        "weekly_interest": weekly,
        "monthly_interest": monthly_interest,
        "current_momentum": momentum,
        "peak_interest_month": max(monthly_interest, key=monthly_interest.get) if monthly_interest else None,
    }


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_analyze(args) -> dict:
    """analyze subcommand: fetch Keepa BSR history and compute seasonal profile."""
    keepa = fetch_keepa_history(args.asin)
    monthly_bsr = keepa["monthly_bsr"]

    peak_months, buy_months, sell_months = _identify_windows(monthly_bsr)
    seasonal_score = _compute_seasonal_score(monthly_bsr)
    current_month_name = MONTH_NAMES[datetime.utcnow().month - 1]

    timing, confidence, recommendation = _timing_verdict(
        monthly_bsr, peak_months, buy_months, sell_months,
        trends_momentum="unknown",
        current_month_name=current_month_name,
    )

    return {
        "asin": args.asin,
        "product_name": keepa["product_name"],
        "monthly_bsr": monthly_bsr,
        "peak_demand_months": peak_months,
        "buy_window": buy_months,
        "sell_window": sell_months,
        "current_timing": timing,
        "confidence": confidence,
        "google_trends_momentum": "not_fetched",
        "seasonal_score": seasonal_score,
        "recommendation": recommendation,
    }


def cmd_trends(args) -> dict:
    """trends subcommand: fetch and display Google Trends 12-month curve."""
    trends = fetch_google_trends(args.keyword)
    return {
        "keyword": args.keyword,
        "monthly_interest": trends.get("monthly_interest", {}),
        "current_momentum": trends.get("current_momentum", "unknown"),
        "peak_interest_month": trends.get("peak_interest_month"),
        "weekly_interest": trends.get("weekly_interest", []),
    }


def cmd_timing(args) -> dict:
    """timing subcommand: combine Keepa BSR + Google Trends for sourcing verdict."""
    keepa = fetch_keepa_history(args.asin)
    monthly_bsr = keepa["monthly_bsr"]
    peak_months, buy_months, sell_months = _identify_windows(monthly_bsr)
    seasonal_score = _compute_seasonal_score(monthly_bsr)

    keyword = args.keyword or keepa["product_name"]
    trends = fetch_google_trends(keyword)
    trends_momentum = trends.get("current_momentum", "unknown")

    current_month_name = MONTH_NAMES[datetime.utcnow().month - 1]
    timing, confidence, recommendation = _timing_verdict(
        monthly_bsr, peak_months, buy_months, sell_months,
        trends_momentum=trends_momentum,
        current_month_name=current_month_name,
    )

    return {
        "asin": args.asin,
        "product_name": keepa["product_name"],
        "keyword": keyword,
        "monthly_bsr": monthly_bsr,
        "peak_demand_months": peak_months,
        "buy_window": buy_months,
        "sell_window": sell_months,
        "current_timing": timing,
        "confidence": confidence,
        "google_trends_momentum": trends_momentum,
        "google_trends_monthly": trends.get("monthly_interest", {}),
        "seasonal_score": seasonal_score,
        "recommendation": recommendation,
    }


def cmd_batch(args) -> list:
    """batch subcommand: analyze multiple ASINs from a file."""
    input_path = Path(args.file)
    if not input_path.exists():
        print(f"ERROR: File not found — {args.file}", file=sys.stderr)
        sys.exit(1)

    asins = [line.strip() for line in input_path.read_text().splitlines() if line.strip()]
    if not asins:
        print("ERROR: No ASINs found in file.", file=sys.stderr)
        sys.exit(1)

    print(f"  Processing {len(asins)} ASIN(s)…", file=sys.stderr)
    results = []
    for idx, asin in enumerate(asins, 1):
        print(f"  [{idx}/{len(asins)}] {asin}", file=sys.stderr)
        try:
            # Build a minimal namespace for reuse
            ns = argparse.Namespace(asin=asin)
            result = cmd_analyze(ns)
            results.append(result)
        except SystemExit:
            results.append({"asin": asin, "error": "Failed to fetch data"})
        # Polite delay between Keepa requests
        if idx < len(asins):
            time.sleep(2)

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seasonal demand analyzer for Amazon FBA sourcing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python execution/seasonal_analyzer.py analyze --asin B08XYZ1234\n"
            "  python execution/seasonal_analyzer.py trends --keyword 'space heater'\n"
            "  python execution/seasonal_analyzer.py timing --asin B08XYZ1234 --keyword 'space heater'\n"
            "  python execution/seasonal_analyzer.py batch --file asins.txt\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = sub.add_parser("analyze", help="Fetch Keepa BSR history and compute seasonal profile.")
    p_analyze.add_argument("--asin", required=True, help="Amazon ASIN to analyze.")

    # trends
    p_trends = sub.add_parser("trends", help="Fetch Google Trends 12-month interest curve.")
    p_trends.add_argument("--keyword", required=True, help="Search keyword for Google Trends.")

    # timing
    p_timing = sub.add_parser("timing", help="Combine Keepa + Google Trends for a sourcing verdict.")
    p_timing.add_argument("--asin", required=True, help="Amazon ASIN to analyze.")
    p_timing.add_argument("--keyword", default=None, help="Google Trends keyword (defaults to product title).")

    # batch
    p_batch = sub.add_parser("batch", help="Analyze multiple ASINs from a text file (one per line).")
    p_batch.add_argument("--file", required=True, help="Path to file with one ASIN per line.")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        result = cmd_analyze(args)
    elif args.command == "trends":
        result = cmd_trends(args)
    elif args.command == "timing":
        result = cmd_timing(args)
    elif args.command == "batch":
        result = cmd_batch(args)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
