#!/usr/bin/env python3
from __future__ import annotations
"""
Script: clearance_scanner.py
Purpose: Scan retailer clearance/sale pages for deeply discounted products.

         This is where the real FBA arb gold is — stores like Walmart, Target,
         CVS mark down products 40-80% on clearance pages. Full-price catalogs
         (like ShopWSS) only find marginal deals.

         Two modes:
         1. Single store: Scrape one retailer's clearance page
         2. Auto-queue: Scan top N clearance stores overnight

Usage:
    python execution/clearance_scanner.py --store walmart --max-tokens 500
    python execution/clearance_scanner.py --top 10 --total-tokens 5000
    python execution/clearance_scanner.py --list  # Show all available clearance stores
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.retailer_registry import RETAILERS
from execution.catalog_pipeline import run_pipeline

OUTPUT_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing" / "clearance"


def get_clearance_stores() -> list[dict]:
    """Get all retailers with clearance URLs, sorted by tier then name."""
    stores = [r for r in RETAILERS if r.get("clearance_url")]
    stores.sort(key=lambda x: (x.get("tier", 99), x.get("name", "")))
    return stores


def list_clearance_stores():
    """Print available clearance stores."""
    stores = get_clearance_stores()
    print(f"\n{len(stores)} retailers with clearance pages:\n")
    print(f"{'Tier':>4}  {'Store':<30}  {'Categories':<40}  URL")
    print("-" * 120)
    for s in stores:
        cats = ", ".join(s.get("categories", []))[:38]
        url = s.get("clearance_url", "")[:50]
        print(f"  {s.get('tier', '?'):>2}   {s['name']:<30}  {cats:<40}  {url}")


def scan_clearance_store(
    store_key: str,
    max_tokens: int = 500,
    min_roi: float = 15.0,
    min_profit: float = 2.0,
) -> dict | None:
    """Scan a single retailer's clearance page.

    Uses the clearance URL instead of the main site URL, targeting
    marked-down products where arb margins are best.
    """
    # Find the store
    store = None
    for r in RETAILERS:
        if r.get("key", "").lower() == store_key.lower() or \
           r.get("name", "").lower() == store_key.lower() or \
           r.get("domain", "").lower() == store_key.lower():
            store = r
            break

    if not store:
        print(f"[clearance] Store not found: {store_key}", file=sys.stderr)
        print(f"[clearance] Try: --list to see available stores", file=sys.stderr)
        return None

    clearance_url = store.get("clearance_url")
    if not clearance_url:
        print(f"[clearance] {store['name']} has no clearance URL in registry", file=sys.stderr)
        return None

    print(f"\n[clearance] Scanning {store['name']} clearance: {clearance_url}", file=sys.stderr)
    print(f"[clearance] Token budget: {max_tokens} | Min ROI: {min_roi}%", file=sys.stderr)

    # Run the catalog pipeline on the clearance URL
    output = run_pipeline(
        url=clearance_url,
        max_tokens=max_tokens,
        min_roi=min_roi,
        min_profit=min_profit,
    )

    # Tag results with clearance source
    if output and output.get("products"):
        for p in output["products"]:
            p["source_type"] = "clearance"
            p["clearance_url"] = clearance_url

    return output


def scan_top_clearance(
    n: int = 10,
    total_tokens: int = 5000,
    min_roi: float = 15.0,
    min_profit: float = 2.0,
    tier: int = 0,
) -> dict:
    """Scan top N clearance stores, splitting token budget proportionally.

    Args:
        n: Number of stores to scan.
        total_tokens: Total Keepa token budget across all stores.
        min_roi: Minimum ROI filter.
        min_profit: Minimum profit filter.
        tier: Only scan stores of this tier (0 = all tiers).

    Returns:
        Combined results dict.
    """
    stores = get_clearance_stores()
    if tier > 0:
        stores = [s for s in stores if s.get("tier") == tier]

    stores = stores[:n]
    tokens_per_store = max(100, total_tokens // len(stores))

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"CLEARANCE SCANNER: {len(stores)} stores, {total_tokens} tokens", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    all_products = []
    results_summary = []

    for i, store in enumerate(stores):
        print(f"\n[{i+1}/{len(stores)}] {store['name']} ({tokens_per_store} tokens)", file=sys.stderr)

        output = scan_clearance_store(
            store_key=store.get("key", store.get("name", "")),
            max_tokens=tokens_per_store,
            min_roi=min_roi,
            min_profit=min_profit,
        )

        if output and output.get("products"):
            products = output["products"]
            buy_count = sum(1 for p in products if p.get("confidence_verdict") == "BUY")
            maybe_count = sum(1 for p in products if p.get("confidence_verdict") == "MAYBE")
            all_products.extend(products)
            results_summary.append({
                "store": store["name"],
                "products": len(products),
                "buy": buy_count,
                "maybe": maybe_count,
            })
            print(f"  -> {len(products)} leads ({buy_count} BUY, {maybe_count} MAYBE)", file=sys.stderr)
        else:
            results_summary.append({"store": store["name"], "products": 0, "buy": 0, "maybe": 0})
            print(f"  -> 0 leads", file=sys.stderr)

    # Sort all products by confidence
    all_products.sort(key=lambda x: x.get("confidence_score", 0), reverse=True)

    # Save combined results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    output_path = OUTPUT_DIR / f"clearance_scan_{date_str}.json"

    combined = {
        "metadata": {
            "scan_type": "clearance",
            "stores_scanned": len(stores),
            "total_products": len(all_products),
            "total_tokens": total_tokens,
            "generated_at": datetime.now().isoformat(),
        },
        "store_results": results_summary,
        "products": all_products,
    }

    with open(output_path, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"CLEARANCE SCAN COMPLETE", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Stores: {len(stores)}", file=sys.stderr)
    print(f"  Total leads: {len(all_products)}", file=sys.stderr)
    buy_total = sum(s["buy"] for s in results_summary)
    maybe_total = sum(s["maybe"] for s in results_summary)
    print(f"  BUY: {buy_total} | MAYBE: {maybe_total}", file=sys.stderr)
    print(f"  Saved: {output_path}", file=sys.stderr)

    return combined


# ── Price Drop Detection ────────────────────────────────────────────────────


def detect_price_drops(catalog: list[dict], min_drop_pct: float = 20.0) -> list[dict]:
    """Filter catalog for products with significant price drops.

    Compares compare_at_price (original) vs price (current).
    Only works on stores that populate compare_at_price (mostly Shopify).

    Args:
        catalog: Raw catalog products from catalog_scraper.
        min_drop_pct: Minimum discount percentage to consider.

    Returns:
        Filtered list with price_drop_pct field added.
    """
    drops = []
    for p in catalog:
        compare = p.get("compare_at_price", 0)
        current = p.get("price", 0)

        if not compare or not current or compare <= 0 or current <= 0:
            continue
        if current >= compare:
            continue  # Not on sale

        drop_pct = ((compare - current) / compare) * 100
        if drop_pct >= min_drop_pct:
            p["price_drop_pct"] = round(drop_pct, 1)
            p["original_price"] = compare
            drops.append(p)

    drops.sort(key=lambda x: x.get("price_drop_pct", 0), reverse=True)
    return drops


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Scan retailer clearance pages for FBA arbitrage deals"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--store", help="Scan single store clearance (name or key)")
    group.add_argument("--top", type=int, help="Scan top N clearance stores")
    group.add_argument("--list", action="store_true", help="List all stores with clearance URLs")

    parser.add_argument("--max-tokens", type=int, default=500,
                        help="Keepa tokens per store (default: 500)")
    parser.add_argument("--total-tokens", type=int, default=5000,
                        help="Total tokens for --top mode (default: 5000)")
    parser.add_argument("--min-roi", type=float, default=15.0,
                        help="Min ROI %% (default: 15)")
    parser.add_argument("--min-profit", type=float, default=2.0,
                        help="Min profit (default: $2)")
    parser.add_argument("--tier", type=int, default=0,
                        help="Only scan stores of this tier (0=all)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON to stdout")

    args = parser.parse_args()

    if args.list:
        list_clearance_stores()
        return

    if args.store:
        output = scan_clearance_store(
            store_key=args.store,
            max_tokens=args.max_tokens,
            min_roi=args.min_roi,
            min_profit=args.min_profit,
        )
        if args.json and output:
            print(json.dumps(output, indent=2))

    elif args.top:
        output = scan_top_clearance(
            n=args.top,
            total_tokens=args.total_tokens,
            min_roi=args.min_roi,
            min_profit=args.min_profit,
            tier=args.tier,
        )
        if args.json:
            print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
