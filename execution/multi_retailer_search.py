#!/usr/bin/env python3
"""
Script: multi_retailer_search.py
Purpose: Search for a product across multiple retailers simultaneously.
         Uses retailer_registry.py for smart category routing — given a product
         query like "reeses easter eggs", it picks the right 5-15 retailers,
         searches each, scrapes results, matches to Amazon, and calculates
         profitability. Returns consolidated results ranked by ROI.

Inputs:  --query (required), --max-retailers (default 10), --max-per-retailer (default 5),
         --category (optional override), --min-roi, --min-profit, --output
Outputs: JSON with consolidated results from all retailers, ranked by ROI.

Key difference from run_sourcing_pipeline.py:
  - Pipeline takes a single URL (one retailer).
  - This script takes a product QUERY, searches across many retailers.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from retailer_registry import (
    get_retailers_for_product,
    get_search_url,
    get_retailer,
    get_clearance_urls,
    detect_category,
)
from retailer_configs import get_retailer_config
from scrape_retail_products import (
    scrape_category_page,
    parse_price,
    USER_AGENT,
    STEALTH_SCRIPT,
)

try:
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from match_amazon_products import match_single_product, title_similarity
from calculate_fba_profitability import calculate_product_profitability

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_MAX_RETAILERS = 10
DEFAULT_MAX_PER_RETAILER = 5
DEFAULT_MIN_ROI = 30.0
DEFAULT_MIN_PROFIT = 3.0
DEFAULT_MAX_PRICE = 50.0
SEARCH_DELAY = 3.0  # seconds between retailer searches
AMAZON_DELAY = 5.0  # seconds between Amazon/Keepa lookups (Keepa rate limits at ~1/3s)


# ── Core Search Logic ────────────────────────────────────────────────────────

def search_single_retailer(page, retailer, query, max_products=5):
    """Search a single retailer for a product query and return scraped products.

    Args:
        page: Playwright page object (reused across retailers).
        retailer: Retailer dict from retailer_registry.
        query: Product search query.
        max_products: Max results to scrape from this retailer.

    Returns:
        List of product dicts with name, retail_price, retail_url, retailer,
        OR a structured error dict {"error": ..., "retailer": ..., "products": [], "elapsed": ...}
        if scraping fails entirely.
    """
    retailer_name = retailer["name"]
    start_time = time.time()

    search_url = get_search_url(retailer, query)
    if not search_url:
        print(f"  [{retailer_name}] No search URL template — skipping", file=sys.stderr)
        return []

    retailer_key, config = get_retailer_config(search_url)
    delay = retailer.get("request_delay", config.get("request_delay", 3.0))

    print(f"  [{retailer_name}] Searching: {search_url[:80]}...", file=sys.stderr)

    try:
        products = scrape_category_page(page, search_url, config, max_products)
    except Exception as e:
        elapsed = time.time() - start_time
        logger.warning(
            f"[RETAILER_ERROR] {retailer_name}: {type(e).__name__} after {elapsed:.1f}s"
            f" — {str(e)[:100]}"
        )
        return {"error": str(type(e).__name__), "retailer": retailer_name, "products": [], "elapsed": elapsed}

    # Tag each product with retailer info
    for p in products:
        p["retailer"] = retailer["name"]
        p["retailer_key"] = retailer["key"]
        p["retailer_tier"] = retailer["tier"]
        p["cashback_percent"] = retailer.get("cashback_percent", 0)

    # Filter: keep only products with a name that's somewhat relevant to the query
    if query:
        query_lower = query.lower()
        query_words = set(query_lower.split())
        filtered = []
        for p in products:
            name = (p.get("name") or "").lower()
            if not name:
                continue
            # At least one query word must appear in the product name
            if any(w in name for w in query_words if len(w) > 2):
                filtered.append(p)
        if filtered:
            products = filtered
        # If no filtered results, keep all (generic search pages may not match well)

    print(f"  [{retailer['name']}] Found {len(products)} products", file=sys.stderr)
    return products[:max_products]


def search_retailers(page, query, retailers, max_per_retailer=5, progress_cb=None):
    """Search across multiple retailers for a product query.

    Args:
        page: Playwright page object.
        query: Product search query.
        retailers: List of retailer dicts from registry.
        max_per_retailer: Max products per retailer.
        progress_cb: Optional callback(retailer_name, index, total).

    Returns:
        Dict with keys:
          "products"         — list of all successfully scraped product dicts
          "failed_retailers" — list of {"retailer", "error", "elapsed"} for failures
    """
    all_products = []
    failed_retailers = []
    total = len(retailers)

    for i, retailer in enumerate(retailers):
        if progress_cb:
            progress_cb(retailer["name"], i + 1, total)

        result = search_single_retailer(page, retailer, query, max_per_retailer)

        # Detect structured error dict vs normal product list
        if isinstance(result, dict) and "error" in result:
            failed_retailers.append({
                "retailer": result["retailer"],
                "error": result["error"],
                "elapsed": result["elapsed"],
            })
        else:
            all_products.extend(result)

        # Delay between retailers to avoid being flagged
        if i < total - 1:
            delay = retailer.get("request_delay", SEARCH_DELAY)
            time.sleep(delay)

    if failed_retailers:
        logger.warning(
            f"[SEARCH_RETAILERS] {len(failed_retailers)} retailer(s) failed: "
            + ", ".join(f["retailer"] for f in failed_retailers)
        )

    return {"products": all_products, "failed_retailers": failed_retailers}


def match_and_price(page, products, min_roi=30.0, min_profit=3.0, max_price=50.0,
                    auto_cashback=True, use_keepa=False, progress_cb=None):
    """Match retail products to Amazon and calculate profitability.

    Uses match_single_product (handles UPC + title search + details + confidence)
    then calculate_product_profitability (expects product dict with 'amazon' key).

    Args:
        page: Playwright page object.
        products: List of retail product dicts.
        min_roi: Minimum ROI % filter.
        min_profit: Minimum profit per unit filter.
        max_price: Maximum retail buy price filter.
        auto_cashback: Auto-apply cashback estimates.
        progress_cb: Optional callback(product_name, index, total).

    Returns:
        List of product dicts enriched with amazon + profitability data.
    """
    results = []
    total = len(products)

    for i, product in enumerate(products):
        name = product.get("name", "")
        price = product.get("retail_price")

        if progress_cb:
            progress_cb(name[:40], i + 1, total)

        # Skip products without name or price
        if not name or not price:
            continue

        # Skip products above max buy price
        if price > max_price:
            continue

        # Match to Amazon using match_single_product (handles UPC, title, details)
        try:
            amazon_data = match_single_product(page, product, use_keepa=use_keepa, fetch_details=True)
        except Exception as e:
            print(f"    [amazon] Error matching '{name[:40]}': {e}", file=sys.stderr)
            continue

        if not amazon_data or not amazon_data.get("asin"):
            continue

        confidence = amazon_data.get("match_confidence", 0)
        if confidence < 0.35:
            continue

        # Build enriched product dict for calculate_product_profitability
        enriched = {
            "name": name,
            "retail_price": price,
            "retailer": product.get("retailer", ""),
            "retailer_key": product.get("retailer_key", ""),
            "retail_url": product.get("retail_url", ""),
            "source_url": product.get("retail_url") or product.get("source_url", ""),
            "upc": product.get("upc"),
            "cashback_percent": product.get("cashback_percent", 0),
            "amazon": {
                "asin": amazon_data.get("asin", ""),
                "title": amazon_data.get("title", ""),
                "amazon_price": amazon_data.get("amazon_price"),
                "sales_rank": amazon_data.get("sales_rank"),
                "category": amazon_data.get("category", "General"),
                "fba_seller_count": amazon_data.get("fba_seller_count"),
                "amazon_on_listing": amazon_data.get("amazon_on_listing", False),
                "match_confidence": confidence,
                "match_method": amazon_data.get("match_method", "title"),
            },
        }

        # Calculate profitability
        try:
            profitability = calculate_product_profitability(
                enriched, auto_cashback=auto_cashback,
            )
        except Exception as e:
            print(f"    [profit] Error for '{name[:40]}': {e}", file=sys.stderr)
            continue

        enriched["profitability"] = profitability

        results.append(enriched)
        time.sleep(AMAZON_DELAY)

    return results


def deduplicate_by_asin(products):
    """Deduplicate products by ASIN — keep the one with the lowest buy cost (best deal)."""
    by_asin = {}
    for p in products:
        asin = p.get("amazon", {}).get("asin", "")
        if not asin:
            continue
        if asin not in by_asin:
            by_asin[asin] = p
        else:
            existing_cost = by_asin[asin].get("profitability", {}).get("buy_cost", 999)
            new_cost = p.get("profitability", {}).get("buy_cost", 999)
            if new_cost < existing_cost:
                # Keep cheaper source, but record alternative
                p["alternative_sources"] = by_asin[asin].get("alternative_sources", [])
                p["alternative_sources"].append({
                    "retailer": by_asin[asin]["retailer"],
                    "buy_cost": existing_cost,
                    "retail_url": by_asin[asin].get("retail_url", ""),
                })
                by_asin[asin] = p
            else:
                existing = by_asin[asin]
                if "alternative_sources" not in existing:
                    existing["alternative_sources"] = []
                existing["alternative_sources"].append({
                    "retailer": p["retailer"],
                    "buy_cost": new_cost,
                    "retail_url": p.get("retail_url", ""),
                })

    return list(by_asin.values())


def rank_results(products, min_roi=30.0, min_profit=3.0):
    """Filter and rank products by profitability."""
    # Categorize
    buy = []
    maybe = []
    skip = []

    for p in products:
        verdict = p.get("profitability", {}).get("verdict", "SKIP")
        if verdict == "BUY":
            buy.append(p)
        elif verdict == "MAYBE":
            maybe.append(p)
        else:
            skip.append(p)

    # Sort each tier by ROI descending
    key_fn = lambda p: p.get("profitability", {}).get("roi_percent", 0) or 0
    buy.sort(key=key_fn, reverse=True)
    maybe.sort(key=key_fn, reverse=True)
    skip.sort(key=key_fn, reverse=True)

    return buy + maybe + skip


def build_summary(products):
    """Build summary stats from ranked product list."""
    buy_products = [p for p in products if p.get("profitability", {}).get("verdict") == "BUY"]
    maybe_products = [p for p in products if p.get("profitability", {}).get("verdict") == "MAYBE"]
    profitable = buy_products + maybe_products

    avg_roi = 0
    avg_profit = 0
    if profitable:
        rois = [p["profitability"]["roi_percent"] for p in profitable if p["profitability"].get("roi_percent")]
        profits = [p["profitability"]["profit_per_unit"] for p in profitable if p["profitability"].get("profit_per_unit")]
        avg_roi = round(sum(rois) / len(rois), 1) if rois else 0
        avg_profit = round(sum(profits) / len(profits), 2) if profits else 0

    retailers_searched = list(set(p.get("retailer", "") for p in products))

    return {
        "total_analyzed": len(products),
        "buy_count": len(buy_products),
        "maybe_count": len(maybe_products),
        "skip_count": len(products) - len(buy_products) - len(maybe_products),
        "avg_roi_percent": avg_roi,
        "avg_profit_per_unit": avg_profit,
        "retailers_searched": retailers_searched,
        "retailer_count": len(retailers_searched),
    }


# ── Clearance Scan ───────────────────────────────────────────────────────────

def scan_clearance(page, category=None, max_retailers=10, max_per_retailer=10,
                   progress_cb=None):
    """Scan clearance/deals pages across multiple retailers.

    Unlike search (which requires a query), this scans known clearance URLs.

    Args:
        page: Playwright page object.
        category: Optional category filter (e.g. "Grocery", "Health").
        max_retailers: Max retailers to scan.
        max_per_retailer: Max products per retailer.
        progress_cb: Optional callback.

    Returns:
        List of scraped products from clearance pages.
    """
    clearance_list = get_clearance_urls(category)[:max_retailers]
    all_products = []
    total = len(clearance_list)

    for i, (retailer, clearance_url) in enumerate(clearance_list):
        if progress_cb:
            progress_cb(retailer["name"], i + 1, total)

        print(f"  [{retailer['name']}] Scanning clearance: {clearance_url[:80]}...", file=sys.stderr)

        retailer_key, config = get_retailer_config(clearance_url)

        try:
            products = scrape_category_page(page, clearance_url, config, max_per_retailer)
        except Exception as e:
            print(f"  [{retailer['name']}] Clearance scrape error: {e}", file=sys.stderr)
            continue

        for p in products:
            p["retailer"] = retailer["name"]
            p["retailer_key"] = retailer["key"]
            p["retailer_tier"] = retailer["tier"]
            p["cashback_percent"] = retailer.get("cashback_percent", 0)
            p["source_type"] = "clearance"

        all_products.extend(products)
        print(f"  [{retailer['name']}] Found {len(products)} clearance products", file=sys.stderr)

        if i < total - 1:
            time.sleep(retailer.get("request_delay", SEARCH_DELAY))

    return all_products


# ── Main CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Multi-retailer product search — find the cheapest retail source for any product"
    )

    # Mode: search or clearance
    subparsers = parser.add_subparsers(dest="mode", help="Search mode")

    # Search mode
    search_parser = subparsers.add_parser("search", help="Search for a product across retailers")
    search_parser.add_argument("--query", "-q", required=True, help="Product search query")
    search_parser.add_argument("--category", "-c", default=None,
                               help="Override auto-detected category (e.g. 'Grocery', 'Health')")
    search_parser.add_argument("--max-retailers", type=int, default=DEFAULT_MAX_RETAILERS,
                               help=f"Max retailers to search (default: {DEFAULT_MAX_RETAILERS})")
    search_parser.add_argument("--max-per-retailer", type=int, default=DEFAULT_MAX_PER_RETAILER,
                               help=f"Max products per retailer (default: {DEFAULT_MAX_PER_RETAILER})")
    search_parser.add_argument("--min-roi", type=float, default=DEFAULT_MIN_ROI)
    search_parser.add_argument("--min-profit", type=float, default=DEFAULT_MIN_PROFIT)
    search_parser.add_argument("--max-price", type=float, default=DEFAULT_MAX_PRICE)
    search_parser.add_argument("--auto-cashback", action="store_true", default=True)
    search_parser.add_argument("--use-keepa", action="store_true", default=False,
                               help="Use Keepa API for Amazon matching (bypasses bot detection)")
    search_parser.add_argument("--no-amazon", action="store_true",
                               help="Skip Amazon matching (just show retail prices)")
    search_parser.add_argument("--output", default=None)

    # Clearance mode
    clear_parser = subparsers.add_parser("clearance", help="Scan clearance pages across retailers")
    clear_parser.add_argument("--category", "-c", default=None,
                              help="Category filter (e.g. 'Grocery', 'Health')")
    clear_parser.add_argument("--max-retailers", type=int, default=DEFAULT_MAX_RETAILERS)
    clear_parser.add_argument("--max-per-retailer", type=int, default=10)
    clear_parser.add_argument("--min-roi", type=float, default=DEFAULT_MIN_ROI)
    clear_parser.add_argument("--min-profit", type=float, default=DEFAULT_MIN_PROFIT)
    clear_parser.add_argument("--max-price", type=float, default=DEFAULT_MAX_PRICE)
    clear_parser.add_argument("--auto-cashback", action="store_true", default=True)
    clear_parser.add_argument("--use-keepa", action="store_true", default=False,
                              help="Use Keepa API for Amazon matching")
    clear_parser.add_argument("--no-amazon", action="store_true")
    clear_parser.add_argument("--output", default=None)

    # List mode — show which retailers would be searched
    list_parser = subparsers.add_parser("list", help="List retailers for a query (dry run)")
    list_parser.add_argument("--query", "-q", required=True)
    list_parser.add_argument("--category", "-c", default=None)
    list_parser.add_argument("--max-retailers", type=int, default=DEFAULT_MAX_RETAILERS)

    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        sys.exit(1)

    # ── List mode (dry run) ──────────────────────────────────────────────────
    if args.mode == "list":
        query = args.query
        categories = detect_category(query)
        if args.category:
            categories = [args.category]

        print(f"Query: '{query}'")
        print(f"Detected categories: {categories}")
        retailers = get_retailers_for_product(
            args.category or query, max_retailers=args.max_retailers
        )
        print(f"\nRetailers ({len(retailers)}):")
        for r in retailers:
            tier = "T1" if r["tier"] == 1 else "T2"
            url = get_search_url(r, query) or "(no search URL)"
            print(f"  [{tier}] {r['name']:25s} | {r['cashback_percent']}% cb | {url[:70]}")
        return

    # ── Search or Clearance mode ─────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    start_time = datetime.now()

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[multi-search] Mode: {args.mode}", file=sys.stderr)
    if args.mode == "search":
        print(f"[multi-search] Query: '{args.query}'", file=sys.stderr)
    if args.category:
        print(f"[multi-search] Category override: {args.category}", file=sys.stderr)
    print(f"[multi-search] Max retailers: {args.max_retailers}", file=sys.stderr)
    print(f"{'=' * 60}\n", file=sys.stderr)

    # Proxy rotation for anti-CAPTCHA
    try:
        from proxy_manager import get_proxy_manager
        _proxy_mgr = get_proxy_manager()
        _proxy_config = _proxy_mgr.next()
        if _proxy_config:
            print(f"[multi-search] Proxy: {_proxy_mgr.provider} ({_proxy_config.get('server', 'gateway')})",
                  file=sys.stderr)
    except Exception:
        _proxy_mgr = None
        _proxy_config = None

    with sync_playwright() as p:
        launch_args = {"headless": True}
        if _proxy_config:
            launch_args["proxy"] = _proxy_config
        browser = p.chromium.launch(**launch_args)
        context = browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        context.add_init_script(STEALTH_SCRIPT)
        page = context.new_page()

        # ── Phase 1: Scrape retail products ──────────────────────────────────
        if args.mode == "search":
            query_or_cat = args.category or args.query
            retailers = get_retailers_for_product(query_or_cat, args.max_retailers)

            print(f"[multi-search] Phase 1: Searching {len(retailers)} retailers...", file=sys.stderr)
            categories = detect_category(args.query)
            if args.category:
                categories = [args.category]
            print(f"[multi-search] Categories: {categories}", file=sys.stderr)
            print(f"[multi-search] Retailers: {', '.join(r['name'] for r in retailers)}", file=sys.stderr)

            search_result = search_retailers(
                page, args.query, retailers, args.max_per_retailer,
            )
            all_products = search_result["products"]
            failed_retailers = search_result["failed_retailers"]
        else:
            # Clearance mode
            print(f"[multi-search] Phase 1: Scanning clearance pages...", file=sys.stderr)
            all_products = scan_clearance(
                page, args.category, args.max_retailers, args.max_per_retailer,
            )
            failed_retailers = []

        retail_count = len(all_products)
        print(f"\n[multi-search] Phase 1 complete: {retail_count} total retail products scraped",
              file=sys.stderr)
        if failed_retailers:
            print(
                f"[multi-search] {len(failed_retailers)} retailer(s) failed: "
                + ", ".join(f["retailer"] for f in failed_retailers),
                file=sys.stderr,
            )

        # Record health events to feedback engine for self-healing monitor
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from feedback_engine import record_retailer_event
            for _failed in failed_retailers:
                record_retailer_event(
                    _failed.get("retailer", "unknown"),
                    _failed.get("error", "error"),
                    0,
                    str(_failed.get("error", "")),
                )
            # Group successful products by retailer and record success events
            _retailer_product_counts: dict = {}
            for _p in all_products:
                _rname = _p.get("retailer", "unknown")
                _retailer_product_counts[_rname] = _retailer_product_counts.get(_rname, 0) + 1
            for _rname, _count in _retailer_product_counts.items():
                record_retailer_event(_rname, "success", _count)
        except Exception:
            pass

        if retail_count == 0:
            print("[multi-search] No products found. Try different query or retailers.", file=sys.stderr)
            output_path = args.output or str(TMP_DIR / f"{ts}-multi-results.json")
            with open(output_path, "w") as f:
                json.dump({"products": [], "count": 0, "failed_retailers": failed_retailers, "summary": {
                    "total_analyzed": 0, "buy_count": 0, "maybe_count": 0, "skip_count": 0,
                    "retailers_searched": [], "retailer_count": 0,
                }}, f, indent=2)
            browser.close()
            return

        # ── Phase 2: Match to Amazon + calculate profitability ───────────────
        if args.no_amazon:
            print(f"[multi-search] Skipping Amazon matching (--no-amazon)", file=sys.stderr)
            # Just return retail products without Amazon matching
            ranked = sorted(all_products, key=lambda p: p.get("retail_price") or 999)
            output_data = {
                "query": getattr(args, "query", None),
                "mode": args.mode,
                "category": args.category,
                "products": ranked,
                "count": len(ranked),
                "failed_retailers": failed_retailers,
                "summary": {
                    "total_scraped": retail_count,
                    "retailers_searched": list(set(p.get("retailer", "") for p in ranked)),
                },
                "timestamp": datetime.now().isoformat(),
            }
        else:
            print(f"\n[multi-search] Phase 2: Matching {retail_count} products to Amazon...",
                  file=sys.stderr)
            matched = match_and_price(
                page, all_products,
                min_roi=args.min_roi,
                min_profit=args.min_profit,
                max_price=args.max_price,
                auto_cashback=args.auto_cashback,
                use_keepa=args.use_keepa,
            )

            print(f"[multi-search] Phase 2 complete: {len(matched)} products matched", file=sys.stderr)

            # Deduplicate by ASIN
            deduped = deduplicate_by_asin(matched)
            print(f"[multi-search] After dedup: {len(deduped)} unique ASINs", file=sys.stderr)

            # Rank
            ranked = rank_results(deduped, args.min_roi, args.min_profit)
            summary = build_summary(ranked)

            output_data = {
                "query": getattr(args, "query", None),
                "mode": args.mode,
                "category": args.category,
                "products": ranked,
                "count": len(ranked),
                "failed_retailers": failed_retailers,
                "summary": summary,
                "timestamp": datetime.now().isoformat(),
            }

        browser.close()

    # ── MEGA VERIFICATION LAYER ─────────────────────────────────────────────
    if ranked:
        try:
            from verify_sourcing_results import verify_results as _verify
            verification = _verify(ranked, strict=True)
            rejected_count = verification["summary"]["rejected"]
            if rejected_count:
                print(f"\n  [verify] Rejected {rejected_count} results "
                      f"(bad links, wrong match, price issues)", file=sys.stderr)
            ranked = verification["verified"] + verification["flagged"]
            if "products" in output_data:
                output_data["products"] = ranked
                output_data["count"] = len(ranked)
        except Exception as e:
            print(f"  [verify] Verification error (continuing): {e}", file=sys.stderr)

    # ── Write output ─────────────────────────────────────────────────────────
    output_path = args.output or str(TMP_DIR / f"{ts}-multi-results.json")
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    # ── CSV export ───────────────────────────────────────────────────────────
    if not args.no_amazon:
        import csv
        csv_path = output_path.replace(".json", ".csv")
        profitable = [p for p in ranked
                      if p.get("profitability", {}).get("verdict") in ("BUY", "MAYBE")]
        if profitable:
            fieldnames = [
                "verdict", "name", "retailer", "buy_cost", "amazon_price", "asin",
                "profit_per_unit", "roi_percent", "deal_score",
                "estimated_monthly_sales", "match_confidence",
                "retail_url", "amazon_url", "alternative_sources",
            ]
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for p in profitable:
                    prof = p.get("profitability", {})
                    amz = p.get("amazon", {})
                    alts = p.get("alternative_sources", [])
                    alt_str = "; ".join(f"{a['retailer']} ${a['buy_cost']:.2f}" for a in alts) if alts else ""
                    writer.writerow({
                        "verdict": prof.get("verdict", ""),
                        "name": p.get("name", ""),
                        "retailer": p.get("retailer", ""),
                        "buy_cost": prof.get("buy_cost", ""),
                        "amazon_price": prof.get("sell_price", ""),
                        "asin": amz.get("asin", ""),
                        "profit_per_unit": prof.get("profit_per_unit", ""),
                        "roi_percent": prof.get("roi_percent", ""),
                        "deal_score": prof.get("deal_score", ""),
                        "estimated_monthly_sales": prof.get("estimated_monthly_sales", ""),
                        "match_confidence": amz.get("match_confidence", ""),
                        "retail_url": p.get("retail_url", ""),
                        "amazon_url": f"https://www.amazon.com/dp/{amz['asin']}" if amz.get("asin") else "",
                        "alternative_sources": alt_str,
                    })
            print(f"[multi-search] CSV: {csv_path} ({len(profitable)} products)", file=sys.stderr)

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    summary = output_data.get("summary", {})

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[multi-search] COMPLETE ({elapsed:.0f}s)", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    if not args.no_amazon:
        print(f"  Total analyzed:   {summary.get('total_analyzed', 0)}", file=sys.stderr)
        print(f"  BUY:              {summary.get('buy_count', 0)}", file=sys.stderr)
        print(f"  MAYBE:            {summary.get('maybe_count', 0)}", file=sys.stderr)
        print(f"  SKIP:             {summary.get('skip_count', 0)}", file=sys.stderr)
        if summary.get("avg_roi_percent"):
            print(f"  Avg ROI:          {summary['avg_roi_percent']}%", file=sys.stderr)
        if summary.get("avg_profit_per_unit"):
            print(f"  Avg profit:       ${summary['avg_profit_per_unit']}", file=sys.stderr)
    print(f"  Retailers:        {summary.get('retailer_count', 0)}", file=sys.stderr)
    print(f"  JSON:             {output_path}", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)


if __name__ == "__main__":
    main()
