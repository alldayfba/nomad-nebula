#!/usr/bin/env python3
"""
Script: run_sourcing_pipeline.py
Purpose: CLI orchestrator that chains: scrape retail → match Amazon → calculate profitability
Inputs:  --url (required), --min-roi, --min-profit, --max-price, --max-products, --shipping-cost, --output
Outputs: JSON + CSV with ranked profitable products
"""

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python3"
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"


def run_step(script_name, args, step_label, timeout=600):
    """Run an execution script and return subprocess result. Raises on failure."""
    script = PROJECT_ROOT / "execution" / script_name
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    cmd = [python, str(script)] + args

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[pipeline] Step: {step_label}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    # Print stderr from the step (progress messages)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        raise RuntimeError(f"{step_label} failed (exit code {result.returncode}): {result.stderr}")

    return result


def export_csv(results_path, csv_path):
    """Export BUY and MAYBE products to a CSV file."""
    with open(results_path) as f:
        data = json.load(f)

    products = data.get("products", [])
    profitable = [p for p in products
                  if p.get("profitability", {}).get("verdict") in ("BUY", "MAYBE")]

    if not profitable:
        print("[pipeline] No profitable products to export to CSV", file=sys.stderr)
        return 0

    fieldnames = [
        "verdict", "name", "retailer", "buy_cost", "amazon_price", "asin",
        "profit_per_unit", "roi_percent", "estimated_monthly_sales",
        "estimated_monthly_profit", "match_confidence", "sales_rank",
        "retail_url", "amazon_url",
    ]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in profitable:
            prof = p.get("profitability", {})
            amz = p.get("amazon", {})
            writer.writerow({
                "verdict": prof.get("verdict", ""),
                "name": p.get("name", ""),
                "retailer": p.get("retailer", ""),
                "buy_cost": prof.get("buy_cost", ""),
                "amazon_price": prof.get("sell_price", ""),
                "asin": amz.get("asin", ""),
                "profit_per_unit": prof.get("profit_per_unit", ""),
                "roi_percent": prof.get("roi_percent", ""),
                "estimated_monthly_sales": prof.get("estimated_monthly_sales", ""),
                "estimated_monthly_profit": prof.get("estimated_monthly_profit", ""),
                "match_confidence": amz.get("match_confidence", ""),
                "sales_rank": amz.get("sales_rank", ""),
                "retail_url": p.get("retail_url", ""),
                "amazon_url": f"https://www.amazon.com/dp/{amz['asin']}" if amz.get("asin") else "",
            })

    return len(profitable)


def main():
    parser = argparse.ArgumentParser(description="Amazon FBA product sourcing pipeline")
    parser.add_argument("--url", required=True, help="Retail URL to source from")
    parser.add_argument("--min-roi", type=float, default=30, help="Minimum ROI %% (default: 30)")
    parser.add_argument("--min-profit", type=float, default=3.0, help="Min profit per unit (default: $3)")
    parser.add_argument("--max-price", type=float, default=50.0, help="Max buy price (default: $50)")
    parser.add_argument("--max-products", type=int, default=50, help="Max products to scrape (default: 50)")
    parser.add_argument("--shipping-cost", type=float, default=1.00,
                        help="Est. shipping to FBA per unit (default: $1.00)")
    parser.add_argument("--no-details", action="store_true",
                        help="Skip Amazon product detail pages (faster, no BSR)")
    parser.add_argument("--auto-cashback", action="store_true",
                        help="Auto-apply estimated Rakuten cashback based on retailer")
    parser.add_argument("--cashback-percent", type=float, default=0.0,
                        help="Manual cashback %% override")
    parser.add_argument("--auto-giftcard", action="store_true",
                        help="Auto-apply CardBear gift card discount based on retailer")
    parser.add_argument("--gift-card-discount", type=float, default=0.0,
                        help="Manual gift card discount %% override")
    parser.add_argument("--prep-cost", type=float, default=None,
                        help="Manual prep cost per unit override (default: auto-estimate)")
    parser.add_argument("--tax-state", type=str, default="none",
                        help="State abbreviation for sales tax (e.g. TX, CA). Default: none")
    parser.add_argument("--no-storage", action="store_true",
                        help="Exclude estimated FBA storage fees from profit calc")
    parser.add_argument("--output", default=None, help="Output JSON path (default: .tmp/sourcing/)")
    parser.add_argument("--auto-export", action="store_true",
                        help="Auto-export BUY/MAYBE results to Google Sheets after pipeline")
    parser.add_argument("--deal-drop-format", action="store_true",
                        help="Also output IC-style deal drop CSV after pipeline")
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[pipeline] Starting FBA sourcing pipeline", file=sys.stderr)
    print(f"[pipeline] URL: {args.url}", file=sys.stderr)
    print(f"[pipeline] Filters: ROI >= {args.min_roi}% | Profit >= ${args.min_profit} | "
          f"Max price: ${args.max_price}", file=sys.stderr)

    start_time = datetime.now()

    # ── Step 1: Scrape retail products ────────────────────────────────────────
    retail_output = str(TMP_DIR / f"{ts}-1-retail.json")
    run_step("scrape_retail_products.py", [
        "--url", args.url,
        "--max-products", str(args.max_products),
        "--output", retail_output,
    ], "Scrape retail products", timeout=300)

    # Check if we got products
    with open(retail_output) as f:
        retail_data = json.load(f)
    product_count = retail_data.get("count", 0)
    if product_count == 0:
        print("[pipeline] No products scraped. Check URL and retailer selectors.", file=sys.stderr)
        # Write empty results
        final_output = args.output or str(TMP_DIR / f"{ts}-3-results.json")
        with open(final_output, "w") as f:
            json.dump({"products": [], "count": 0, "summary": {
                "total_analyzed": 0, "buy_count": 0, "maybe_count": 0, "skip_count": 0
            }}, f, indent=2)
        print(f"[pipeline] Empty results → {final_output}", file=sys.stderr)
        return

    print(f"\n[pipeline] Scraped {product_count} products from {retail_data.get('retailer', 'unknown')}",
          file=sys.stderr)

    # Record prices to history for clearance cadence tracking
    try:
        import sys as _sys, os as _os
        _sys.path.insert(0, str(PROJECT_ROOT / "execution"))
        from clearance_predictor import record_scan_prices
        retailer_name = retail_data.get("retailer", "")
        record_scan_prices(retail_data.get("products", []), retailer=retailer_name)
    except Exception:
        pass  # Non-fatal

    # ── Step 2: Match to Amazon ───────────────────────────────────────────────
    matched_output = str(TMP_DIR / f"{ts}-2-matched.json")
    match_args = [
        "--input", retail_output,
        "--output", matched_output,
        "--max-matches", str(args.max_products),
    ]
    if args.no_details:
        match_args.append("--no-details")

    run_step("match_amazon_products.py", match_args, "Match to Amazon ASINs", timeout=600)

    # Filter: require match confidence >= 0.70 before running profitability
    with open(matched_output) as f:
        matched_data = json.load(f)
    matched_products = matched_data.get("products", [])
    original_count = len(matched_products)
    matched_products = [
        p for p in matched_products
        if p.get("amazon", {}).get("match_confidence", 0) >= 0.70
    ]
    if len(matched_products) < original_count:
        print(f"[pipeline] Confidence filter: {original_count - len(matched_products)} products "
              f"dropped below 0.70 threshold ({len(matched_products)} remain)", file=sys.stderr)
    if not matched_products:
        print("[pipeline] No products met 0.70 confidence threshold after matching",
              file=sys.stderr)
        final_output = args.output or str(TMP_DIR / f"{ts}-3-results.json")
        with open(final_output, "w") as f:
            json.dump({"products": [], "count": 0, "summary": {
                "total_analyzed": 0, "buy_count": 0, "maybe_count": 0, "skip_count": 0
            }}, f, indent=2)
        print(f"[pipeline] Empty results → {final_output}", file=sys.stderr)
        return
    matched_data["products"] = matched_products
    with open(matched_output, "w") as f:
        json.dump(matched_data, f, indent=2)

    # ── Step 3: Calculate profitability ───────────────────────────────────────
    final_output = args.output or str(TMP_DIR / f"{ts}-3-results.json")
    profit_args = [
        "--input", matched_output,
        "--output", final_output,
        "--min-roi", str(args.min_roi),
        "--min-profit", str(args.min_profit),
        "--max-price", str(args.max_price),
        "--shipping-cost", str(args.shipping_cost),
    ]
    if args.auto_cashback:
        profit_args.append("--auto-cashback")
    if args.cashback_percent > 0:
        profit_args.extend(["--cashback-percent", str(args.cashback_percent)])
    if args.auto_giftcard:
        profit_args.append("--auto-giftcard")
    if args.gift_card_discount > 0:
        profit_args.extend(["--gift-card-discount", str(args.gift_card_discount)])
    if args.prep_cost is not None:
        profit_args.extend(["--prep-cost", str(args.prep_cost)])
    if args.tax_state != "none":
        profit_args.extend(["--tax-state", args.tax_state])
    if args.no_storage:
        profit_args.append("--no-storage")
    run_step("calculate_fba_profitability.py", profit_args,
             "Calculate profitability", timeout=60)

    # Add price trajectory to each product in final results
    try:
        import sys as _sys, os as _os
        _sys.path.insert(0, str(PROJECT_ROOT / "execution"))
        from clearance_predictor import get_price_trajectory
        with open(final_output) as _f:
            _results_data = json.load(_f)
        for _product in _results_data.get("products", []):
            try:
                trajectory_data = get_price_trajectory(
                    retailer=_product.get("retailer", ""),
                    url=_product.get("retail_url", ""),
                    asin=_product.get("amazon", {}).get("asin", ""),
                )
                _product["price_trajectory"] = trajectory_data.get("trajectory", "unknown")
                _product["price_recommendation"] = trajectory_data.get("recommendation", "")
            except Exception:
                _product["price_trajectory"] = "unknown"
                _product["price_recommendation"] = ""
        with open(final_output, "w") as _f:
            json.dump(_results_data, _f, indent=2)
    except Exception:
        pass  # Non-fatal

    # Product Review Agent — filter out false matches before output
    try:
        import sys as _sys
        _sys.path.insert(0, str(PROJECT_ROOT / "execution"))
        from product_review_agent import batch_review_products
        with open(final_output) as _f:
            _pre_review = json.load(_f)
        _products_to_review = _pre_review.get("products", [])
        if _products_to_review:
            review_output = batch_review_products(_products_to_review, use_ai=True)
            # Keep verified and flagged; rejected products are logged and dropped
            _pre_review["products"] = review_output["verified"] + review_output["flagged"]
            _stats = review_output["stats"]
            print(
                f"[pipeline] Review: {_stats['verified_count']} verified, "
                f"{_stats['flagged_count']} flagged, {_stats['rejected_count']} rejected",
                file=sys.stderr,
            )
            if isinstance(_pre_review.get("summary"), dict):
                _pre_review["summary"]["review_stats"] = _stats
            with open(final_output, "w") as _f:
                json.dump(_pre_review, _f, indent=2)
    except ImportError:
        pass  # Non-fatal if product_review_agent not available
    except Exception as _e:
        print(f"[pipeline] Product review agent error (non-fatal): {_e}", file=sys.stderr)

    # Trigger feedback analysis every 10 scans (non-blocking)
    try:
        import random as _random
        if _random.random() < 0.1:  # 10% of scans trigger feedback analysis
            from feedback_engine import run_daily_feedback_cycle
            import threading as _threading
            _t = _threading.Thread(target=run_daily_feedback_cycle, daemon=True)
            _t.start()
    except Exception:
        pass

    # ── Export CSV ────────────────────────────────────────────────────────────
    csv_output = final_output.replace(".json", ".csv")
    csv_count = export_csv(final_output, csv_output)

    # ── Auto-export to Google Sheets ──────────────────────────────────────────
    if args.auto_export:
        try:
            import importlib.util
            export_module = PROJECT_ROOT / "execution" / "export_to_sheets.py"
            spec = importlib.util.spec_from_file_location("export_to_sheets", export_module)
            export_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(export_mod)
            sheet_url = export_mod.export_to_sheets(final_output)
            if sheet_url:
                print(f"[pipeline] Sheets export: {sheet_url}", file=sys.stderr)
        except Exception as e:
            print(f"[pipeline] Sheets export failed (non-fatal): {e}", file=sys.stderr)

    # ── IC-Style Deal Drop CSV ────────────────────────────────────────────────
    if args.deal_drop_format:
        try:
            import importlib.util
            fmt_module = PROJECT_ROOT / "execution" / "format_deal_drop.py"
            spec = importlib.util.spec_from_file_location("format_deal_drop", fmt_module)
            fmt_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fmt_mod)
            deal_drop_path = fmt_mod.format_deal_drop(final_output)
            if deal_drop_path:
                print(f"[pipeline] Deal drop CSV: {deal_drop_path}", file=sys.stderr)
        except Exception as e:
            print(f"[pipeline] Deal drop format failed (non-fatal): {e}", file=sys.stderr)

    # ── Step 4: Track in database ─────────────────────────────────────────────
    try:
        from price_tracker import store_sourcing_results
        alerts = store_sourcing_results(final_output)
        if alerts:
            print(f"[pipeline] {len(alerts)} new price alerts generated", file=sys.stderr)
    except Exception as e:
        print(f"[pipeline] Price tracking skipped: {e}", file=sys.stderr)

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()

    with open(final_output) as f:
        results = json.load(f)
    summary = results.get("summary", {})

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[pipeline] SOURCING COMPLETE ({elapsed:.0f}s)", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    print(f"  Total analyzed:  {summary.get('total_analyzed', 0)}", file=sys.stderr)
    print(f"  BUY:             {summary.get('buy_count', 0)}", file=sys.stderr)
    print(f"  MAYBE:           {summary.get('maybe_count', 0)}", file=sys.stderr)
    print(f"  SKIP:            {summary.get('skip_count', 0)}", file=sys.stderr)
    if summary.get("avg_roi_percent"):
        print(f"  Avg ROI:         {summary['avg_roi_percent']}%", file=sys.stderr)
    if summary.get("avg_profit_per_unit"):
        print(f"  Avg profit:      ${summary['avg_profit_per_unit']}", file=sys.stderr)
    print(f"  JSON:            {final_output}", file=sys.stderr)
    if csv_count > 0:
        print(f"  CSV:             {csv_output} ({csv_count} products)", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)


if __name__ == "__main__":
    main()
