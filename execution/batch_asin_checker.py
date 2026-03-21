#!/usr/bin/env python3
"""
Script: batch_asin_checker.py
Purpose: Bulk ASIN lookup tool for Amazon FBA sourcing. Takes a list of ASINs
         (from file, stdin, or CLI args), fetches product data, calculates
         profitability at various buy prices, and outputs a ranked summary.
Inputs:  --asins (CLI args), --file (one ASIN per line), --stdin (pipe)
         --buy-prices (comma-separated), --output (JSON), --use-keepa
Outputs: JSON to stdout (or file), summary table to stderr
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    print("Install with: pip install playwright beautifulsoup4", file=sys.stderr)
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from calculate_fba_profitability import (
    get_referral_fee_rate,
    estimate_fba_fee,
    estimate_monthly_sales,
    score_competition,
    check_restrictions,
)
from match_amazon_products import (
    get_keepa_product_details,
    get_amazon_product_details,
    parse_amazon_price,
    USER_AGENT,
)

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY")
AMAZON_PAGE_DELAY = 3.0  # seconds between Amazon page loads
DEFAULT_BUY_PRICES = [5.00, 10.00, 15.00, 20.00, 25.00, 30.00]

# Shipping cost per unit to FBA warehouse (conservative default)
SHIPPING_TO_FBA = 1.00

# Thresholds for BUY verdict
MIN_ROI_DEFAULT = 30.0      # percent
MIN_PROFIT_DEFAULT = 3.50   # dollars


# ── Amazon Product Fetching ──────────────────────────────────────────────────

def fetch_asin_keepa(asin):
    """Fetch product data from Keepa API for a single ASIN.

    Returns dict with: title, amazon_price, sales_rank, category,
    fba_seller_count, amazon_on_listing — or None on failure.
    """
    if not KEEPA_API_KEY:
        return None

    details = get_keepa_product_details(asin)
    if not details:
        return None

    # get_keepa_product_details returns sales_rank, category, amazon_price,
    # fba_price, fba_seller_count, fbm_seller_count, new_offer_count,
    # amazon_on_listing. We also need the title, which requires the full
    # product endpoint.
    try:
        import requests
        params = {
            "key": KEEPA_API_KEY,
            "domain": "1",  # amazon.com
            "asin": asin,
        }
        resp = requests.get("https://api.keepa.com/product", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("products"):
            product = data["products"][0]
            title = product.get("title", "")
        else:
            title = ""
    except Exception:
        title = ""

    return {
        "asin": asin,
        "title": title,
        "amazon_price": details.get("amazon_price") or details.get("fba_price"),
        "sales_rank": details.get("sales_rank"),
        "category": details.get("category"),
        "fba_seller_count": details.get("fba_seller_count"),
        "amazon_on_listing": details.get("amazon_on_listing"),
        "data_source": "keepa",
    }


def fetch_asin_playwright(page, asin):
    """Fetch product data from Amazon product page via Playwright.

    Returns dict with: title, amazon_price, sales_rank, category,
    fba_seller_count, amazon_on_listing — or None on failure.
    """
    url = f"https://www.amazon.com/dp/{asin}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
        soup = BeautifulSoup(page.content(), "html.parser")

        # Check for CAPTCHA
        if soup.select_one("form[action*='captcha']") or "robot" in soup.get_text().lower()[:500]:
            print(f"    [amazon] CAPTCHA detected on {asin} — skipping", file=sys.stderr)
            return None

        # Title
        title_el = soup.select_one("#productTitle, #title span, h1#title")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            print(f"    [amazon] Could not extract title for {asin}", file=sys.stderr)
            return None

        # Price
        price = None
        price_selectors = [
            "span.a-price span.a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "span.a-price-whole",
            "#corePrice_feature_div span.a-offscreen",
        ]
        for sel in price_selectors:
            price_el = soup.select_one(sel)
            if price_el:
                price = parse_amazon_price(price_el.get_text(strip=True))
                if price:
                    break

        # Get detailed info (BSR, category, sellers)
        details = get_amazon_product_details(page, asin)

        return {
            "asin": asin,
            "title": title,
            "amazon_price": price,
            "sales_rank": details.get("sales_rank"),
            "category": details.get("category"),
            "fba_seller_count": details.get("fba_seller_count"),
            "amazon_on_listing": details.get("amazon_on_listing"),
            "data_source": "playwright",
        }

    except Exception as e:
        print(f"    [amazon] Error fetching {asin}: {e}", file=sys.stderr)
        return None


def fetch_asin_data(asin, use_keepa=False, page=None):
    """Fetch product data for an ASIN. Tries Keepa first if enabled,
    falls back to Playwright."""
    if use_keepa:
        data = fetch_asin_keepa(asin)
        if data:
            return data
        print(f"    [keepa] No data for {asin}, falling back to Playwright", file=sys.stderr)

    if page is None:
        print(f"    [error] No Playwright page available for {asin}", file=sys.stderr)
        return None

    return fetch_asin_playwright(page, asin)


# ── Profitability Calculation ─────────────────────────────────────────────────

def calculate_at_buy_price(buy_price, sell_price, category,
                           min_roi=MIN_ROI_DEFAULT, min_profit=MIN_PROFIT_DEFAULT):
    """Calculate profitability at a specific buy price.

    Returns dict with: profit, roi, total_fees, verdict
    """
    if not sell_price or sell_price <= 0:
        return {
            "profit": None,
            "roi": None,
            "total_fees": None,
            "verdict": "SKIP",
        }

    referral_fee_rate = get_referral_fee_rate(category)
    referral_fee = round(sell_price * referral_fee_rate, 2)
    fba_fee = estimate_fba_fee(sell_price)
    total_fees = round(referral_fee + fba_fee + SHIPPING_TO_FBA, 2)

    profit = round(sell_price - buy_price - total_fees, 2)
    roi = round((profit / buy_price) * 100, 1) if buy_price > 0 else 0.0

    if roi >= min_roi and profit >= min_profit:
        verdict = "BUY"
    elif roi >= 20 and profit >= 2.00:
        verdict = "MAYBE"
    else:
        verdict = "SKIP"

    return {
        "profit": profit,
        "roi": roi,
        "total_fees": total_fees,
        "verdict": verdict,
    }


def find_max_buy_price(amazon_price, category, min_roi=MIN_ROI_DEFAULT,
                       min_profit=MIN_PROFIT_DEFAULT):
    """Binary search for the highest price you can pay and still hit BUY thresholds.

    Returns the max buy price (float) rounded to 2 decimal places, or 0.0 if
    no price yields a BUY verdict.
    """
    if not amazon_price or amazon_price <= 0:
        return 0.0

    lo = 0.01
    hi = amazon_price * 0.90  # never pay more than 90% of sell price
    best = 0.0

    # Binary search with ~1 cent precision
    for _ in range(50):
        if lo > hi:
            break
        mid = round((lo + hi) / 2, 2)
        result = calculate_at_buy_price(mid, amazon_price, category, min_roi, min_profit)

        if result["verdict"] == "BUY":
            best = mid
            lo = round(mid + 0.01, 2)
        else:
            hi = round(mid - 0.01, 2)

    return round(best, 2)


def calculate_deal_score(product_data, profitability_at_prices, buy_prices):
    """Calculate a composite deal score (0-100).

    Weights:
    - ROI at median buy price: 25 points
    - Monthly sales velocity: 25 points
    - Competition (fewer sellers = better): 20 points
    - Risk flags (no hazmat/gating/IP = better): 15 points
    - BSR quality (lower = better): 15 points
    """
    score = 0.0

    # ── ROI at median buy price (25 points) ──────────────────────────────
    median_price = f"{buy_prices[len(buy_prices) // 2]:.2f}"
    median_data = profitability_at_prices.get(median_price, {})
    roi = median_data.get("roi")
    if roi is not None:
        if roi >= 100:
            score += 25.0
        elif roi >= 50:
            score += 20.0
        elif roi >= 30:
            score += 15.0
        elif roi >= 20:
            score += 10.0
        elif roi > 0:
            score += 5.0

    # ── Monthly sales velocity (25 points) ────────────────────────────────
    monthly_sales = product_data.get("estimated_monthly_sales")
    if monthly_sales is not None:
        if monthly_sales >= 500:
            score += 25.0
        elif monthly_sales >= 200:
            score += 20.0
        elif monthly_sales >= 100:
            score += 17.0
        elif monthly_sales >= 50:
            score += 12.0
        elif monthly_sales >= 20:
            score += 8.0
        elif monthly_sales >= 5:
            score += 4.0

    # ── Competition (20 points) ───────────────────────────────────────────
    competition = product_data.get("competition_score", "UNKNOWN")
    if competition == "LOW":
        score += 20.0
    elif competition == "MODERATE":
        score += 14.0
    elif competition == "HIGH":
        score += 7.0
    elif competition == "UNKNOWN":
        score += 10.0  # assume moderate if unknown
    # SATURATED and HIGH_RISK get 0

    # ── Risk flags (15 points) ────────────────────────────────────────────
    restrictions = product_data.get("restrictions", {})
    risk_deductions = 0
    if restrictions.get("is_gated"):
        risk_deductions += 5
    if restrictions.get("hazmat_risk"):
        risk_deductions += 5
    if restrictions.get("ip_risk"):
        risk_deductions += 5
    score += max(0, 15 - risk_deductions)

    # ── BSR quality (15 points) ───────────────────────────────────────────
    bsr = product_data.get("sales_rank")
    if bsr is not None:
        if bsr <= 5000:
            score += 15.0
        elif bsr <= 20000:
            score += 12.0
        elif bsr <= 50000:
            score += 9.0
        elif bsr <= 100000:
            score += 6.0
        elif bsr <= 200000:
            score += 3.0
        # BSR > 200000 gets 0

    return round(score)


# ── Core: Check Single ASIN ──────────────────────────────────────────────────

def check_single_asin(asin, buy_prices, use_keepa=False, page=None,
                       min_roi=MIN_ROI_DEFAULT, min_profit=MIN_PROFIT_DEFAULT):
    """Fetch data for an ASIN and calculate profitability at each buy price.

    Returns a dict with all product data, profitability at each buy price,
    max buy price, competition score, restrictions, and deal score.
    """
    # Fetch Amazon product data
    data = fetch_asin_data(asin, use_keepa=use_keepa, page=page)

    if not data:
        return {
            "asin": asin,
            "title": None,
            "amazon_price": None,
            "sales_rank": None,
            "category": None,
            "fba_seller_count": None,
            "amazon_on_listing": None,
            "estimated_monthly_sales": None,
            "max_buy_price": 0.0,
            "profitability_at_prices": {},
            "competition_score": "UNKNOWN",
            "restrictions": {"is_gated": False, "hazmat_risk": False, "ip_risk": False},
            "deal_score": 0,
            "error": "Could not fetch product data",
        }

    amazon_price = data.get("amazon_price")
    category = data.get("category")
    sales_rank = data.get("sales_rank")
    title = data.get("title", "")

    # Monthly sales estimate
    monthly_sales = estimate_monthly_sales(sales_rank, category)

    # Competition score
    competition_score, competition_warnings = score_competition(data)

    # Restriction checks
    restrictions = check_restrictions(title, category)
    # Flatten to match output spec (drop restriction_warnings for output)
    restriction_output = {
        "is_gated": restrictions.get("is_gated", False),
        "hazmat_risk": restrictions.get("hazmat_risk", False),
        "ip_risk": restrictions.get("ip_risk", False),
    }

    # Calculate profitability at each buy price
    profitability_at_prices = {}
    for bp in buy_prices:
        result = calculate_at_buy_price(bp, amazon_price, category, min_roi, min_profit)
        profitability_at_prices[f"{bp:.2f}"] = {
            "profit": result["profit"],
            "roi": result["roi"],
            "verdict": result["verdict"],
        }

    # Find max buy price for BUY verdict
    max_buy = find_max_buy_price(amazon_price, category, min_roi, min_profit)

    # Build result
    result = {
        "asin": asin,
        "title": title,
        "amazon_price": amazon_price,
        "sales_rank": sales_rank,
        "category": category,
        "fba_seller_count": data.get("fba_seller_count"),
        "amazon_on_listing": data.get("amazon_on_listing", False),
        "estimated_monthly_sales": monthly_sales,
        "max_buy_price": max_buy,
        "profitability_at_prices": profitability_at_prices,
        "competition_score": competition_score,
        "restrictions": restriction_output,
        "deal_score": 0,  # placeholder, calculated below
    }

    # Deal score
    result["deal_score"] = calculate_deal_score(result, profitability_at_prices, buy_prices)

    return result


# ── Batch Processing ─────────────────────────────────────────────────────────

def batch_check(asins, buy_prices, use_keepa=False, output_path=None,
                min_roi=MIN_ROI_DEFAULT, min_profit=MIN_PROFIT_DEFAULT):
    """Process a list of ASINs with progress output. Returns list of results."""
    print(f"\n[batch] Starting ASIN check for {len(asins)} ASIN(s)", file=sys.stderr)
    print(f"[batch] Buy prices: {', '.join(f'${p:.2f}' for p in buy_prices)}", file=sys.stderr)
    print(f"[batch] Keepa: {'enabled' if use_keepa else 'disabled (using Playwright)'}", file=sys.stderr)
    print(f"[batch] Thresholds: min ROI {min_roi}%, min profit ${min_profit:.2f}", file=sys.stderr)

    results = []
    need_playwright = not use_keepa or not KEEPA_API_KEY

    if need_playwright:
        pw_ctx = sync_playwright().start()
        browser = pw_ctx.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
    else:
        pw_ctx = None
        browser = None
        page = None

    try:
        for i, asin in enumerate(asins):
            asin = asin.strip().upper()
            if not asin or not re.match(r'^[A-Z0-9]{10}$', asin):
                print(f"\n[batch] Skipping invalid ASIN: '{asin}'", file=sys.stderr)
                continue

            print(f"\n[batch] [{i + 1}/{len(asins)}] {asin}", file=sys.stderr)

            result = check_single_asin(
                asin, buy_prices, use_keepa=use_keepa, page=page,
                min_roi=min_roi, min_profit=min_profit,
            )
            results.append(result)

            if result.get("error"):
                print(f"  ERROR: {result['error']}", file=sys.stderr)
            else:
                title = (result.get("title") or "")[:60]
                price = result.get("amazon_price")
                max_buy = result.get("max_buy_price", 0)
                score = result.get("deal_score", 0)
                print(f"  {title}", file=sys.stderr)
                print(f"  Price: ${price}" if price else "  Price: N/A", file=sys.stderr)
                print(f"  Max buy: ${max_buy:.2f} | Deal score: {score}/100", file=sys.stderr)

            # Delay between ASINs to avoid rate limits
            if i < len(asins) - 1:
                time.sleep(AMAZON_PAGE_DELAY)
    finally:
        if browser:
            browser.close()
        if pw_ctx:
            pw_ctx.stop()

    # Sort by deal score descending
    results.sort(key=lambda r: r.get("deal_score", 0), reverse=True)

    # Print summary table to stderr
    format_summary_table(results, buy_prices)

    # Build output
    output_data = {
        "mode": "batch_asin_check",
        "asins_checked": len(results),
        "buy_prices": [f"{p:.2f}" for p in buy_prices],
        "thresholds": {
            "min_roi": min_roi,
            "min_profit": min_profit,
        },
        "results": results,
        "summary": {
            "total_checked": len(results),
            "with_data": sum(1 for r in results if not r.get("error")),
            "buy_worthy": sum(
                1 for r in results
                if r.get("max_buy_price", 0) > 0
            ),
            "avg_deal_score": round(
                sum(r.get("deal_score", 0) for r in results) / max(len(results), 1), 1
            ),
        },
        "checked_at": datetime.now().isoformat(),
    }

    # Output
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\n[batch] Results saved to {output_path}", file=sys.stderr)
    else:
        print(json.dumps(output_data, indent=2))

    return output_data


# ── Summary Table ─────────────────────────────────────────────────────────────

def format_summary_table(results, buy_prices):
    """Pretty-print results as a table to stderr."""
    if not results:
        print("\n[batch] No results to display.", file=sys.stderr)
        return

    # Header
    print(f"\n{'=' * 100}", file=sys.stderr)
    print(f"  BATCH ASIN CHECK RESULTS — {len(results)} ASIN(s)", file=sys.stderr)
    print(f"{'=' * 100}", file=sys.stderr)

    # Column headers
    bp_headers = "".join(f"{'$' + f'{p:.0f}':>8}" for p in buy_prices)
    header = f"{'ASIN':<12} {'Score':>5} {'Price':>8} {'MaxBuy':>8} {'BSR':>10} {'Sell#':>5} {bp_headers}"
    print(f"\n{header}", file=sys.stderr)
    print(f"{'-' * len(header)}", file=sys.stderr)

    for r in results:
        asin = r.get("asin", "?")
        score = r.get("deal_score", 0)
        price = r.get("amazon_price")
        max_buy = r.get("max_buy_price", 0)
        bsr = r.get("sales_rank")
        sellers = r.get("fba_seller_count")

        price_str = f"${price:.2f}" if price else "N/A"
        max_buy_str = f"${max_buy:.2f}" if max_buy > 0 else "---"
        bsr_str = f"{bsr:,}" if bsr else "N/A"
        seller_str = str(sellers) if sellers is not None else "?"

        # Verdict at each buy price
        bp_verdicts = ""
        for bp in buy_prices:
            key = f"{bp:.2f}"
            prof = r.get("profitability_at_prices", {}).get(key, {})
            verdict = prof.get("verdict", "---")
            if verdict == "BUY":
                bp_verdicts += f"{'BUY':>8}"
            elif verdict == "MAYBE":
                bp_verdicts += f"{'MAYBE':>8}"
            else:
                bp_verdicts += f"{'SKIP':>8}"

        line = f"{asin:<12} {score:>5} {price_str:>8} {max_buy_str:>8} {bsr_str:>10} {seller_str:>5} {bp_verdicts}"
        print(line, file=sys.stderr)

    # Footer with title list
    print(f"\n{'—' * 100}", file=sys.stderr)
    print(f"  TITLES:", file=sys.stderr)
    for r in results:
        asin = r.get("asin", "?")
        title = (r.get("title") or "N/A")[:80]
        flags = []
        restrictions = r.get("restrictions", {})
        if restrictions.get("is_gated"):
            flags.append("GATED")
        if restrictions.get("hazmat_risk"):
            flags.append("HAZMAT")
        if restrictions.get("ip_risk"):
            flags.append("IP-RISK")
        if r.get("amazon_on_listing"):
            flags.append("AMZ-ON")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  {asin}: {title}{flag_str}", file=sys.stderr)

    print(f"{'=' * 100}\n", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_buy_prices(s):
    """Parse comma-separated buy prices string into list of floats."""
    prices = []
    for part in s.split(","):
        part = part.strip()
        if part:
            try:
                prices.append(float(part))
            except ValueError:
                print(f"Warning: ignoring invalid buy price '{part}'", file=sys.stderr)
    return sorted(prices) if prices else DEFAULT_BUY_PRICES


def read_asins_from_file(filepath):
    """Read ASINs from a file (one per line, # comments allowed)."""
    path = Path(filepath)
    if not path.exists():
        print(f"ERROR: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    asins = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            # Handle lines that might have extra data after ASIN (e.g. "B08XYZ notes")
            asin = line.split()[0].strip().upper()
            if re.match(r'^[A-Z0-9]{10}$', asin):
                asins.append(asin)
            else:
                print(f"Warning: skipping invalid ASIN in file: '{line}'", file=sys.stderr)
    return asins


def read_asins_from_stdin():
    """Read ASINs from stdin (one per line)."""
    asins = []
    for line in sys.stdin:
        line = line.strip()
        if line and not line.startswith("#"):
            asin = line.split()[0].strip().upper()
            if re.match(r'^[A-Z0-9]{10}$', asin):
                asins.append(asin)
    return asins


def main():
    parser = argparse.ArgumentParser(
        description="Bulk ASIN checker for FBA sourcing — check profitability at various buy prices",
        epilog=(
            "Examples:\n"
            "  python batch_asin_checker.py --asins B08XYZ1234 B09ABC5678\n"
            "  python batch_asin_checker.py --file asins.txt\n"
            "  python batch_asin_checker.py --file asins.txt --buy-prices 5,10,15,20\n"
            "  python batch_asin_checker.py --file asins.txt --output results.json --use-keepa\n"
            "  cat asins.txt | python batch_asin_checker.py --stdin\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ASIN input (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--asins", nargs="+", help="One or more ASINs to check")
    group.add_argument("--file", help="File with one ASIN per line")
    group.add_argument("--stdin", action="store_true", help="Read ASINs from stdin")

    # Options
    parser.add_argument(
        "--buy-prices", type=str, default=None,
        help=f"Comma-separated buy prices to evaluate (default: {','.join(str(int(p)) for p in DEFAULT_BUY_PRICES)})"
    )
    parser.add_argument("--output", help="Output JSON path (default: stdout)")
    parser.add_argument(
        "--use-keepa", action="store_true",
        help="Use Keepa API for Amazon data (requires KEEPA_API_KEY in .env)"
    )
    parser.add_argument(
        "--min-roi", type=float, default=MIN_ROI_DEFAULT,
        help=f"Min ROI %% for BUY verdict (default: {MIN_ROI_DEFAULT})"
    )
    parser.add_argument(
        "--min-profit", type=float, default=MIN_PROFIT_DEFAULT,
        help=f"Min profit ($) for BUY verdict (default: ${MIN_PROFIT_DEFAULT})"
    )

    args = parser.parse_args()

    # Build ASIN list
    if args.asins:
        asins = [a.strip().upper() for a in args.asins]
    elif args.file:
        asins = read_asins_from_file(args.file)
    elif args.stdin:
        asins = read_asins_from_stdin()
    else:
        parser.print_help()
        sys.exit(1)

    if not asins:
        print("ERROR: No valid ASINs provided", file=sys.stderr)
        sys.exit(1)

    # Deduplicate while preserving order
    seen = set()
    unique_asins = []
    for a in asins:
        if a not in seen:
            seen.add(a)
            unique_asins.append(a)
    asins = unique_asins

    # Parse buy prices
    buy_prices = parse_buy_prices(args.buy_prices) if args.buy_prices else DEFAULT_BUY_PRICES

    # Auto-detect Keepa
    use_keepa = args.use_keepa or bool(KEEPA_API_KEY)
    if use_keepa and not KEEPA_API_KEY:
        print("[batch] Warning: --use-keepa set but KEEPA_API_KEY not found in .env",
              file=sys.stderr)
        use_keepa = False

    # Run
    batch_check(
        asins, buy_prices,
        use_keepa=use_keepa,
        output_path=args.output,
        min_roi=args.min_roi,
        min_profit=args.min_profit,
    )


if __name__ == "__main__":
    main()
