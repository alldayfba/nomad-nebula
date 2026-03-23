#!/usr/bin/env python3
from __future__ import annotations
"""
Script: smart_scan.py
Purpose: One-command product discovery using ALL working Keepa-based modes.

         Runs finder, deals, a2a, and oos in sequence, compiles results,
         deduplicates by ASIN, ranks by profit, and outputs a unified list.

         This is the PRIMARY sourcing command — no retailer scraping needed.

Usage:
    python execution/smart_scan.py                     # Default: 500 tokens
    python execution/smart_scan.py --tokens 1000       # More tokens = more results
    python execution/smart_scan.py --preset toys       # Category-focused scan
    python execution/smart_scan.py --quick              # Fast scan (deals + a2a only, ~50 tokens)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

OUTPUT_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing" / "smart_scan"


# ── Category Presets ─────────────────────────────────────────────────────────

PRESETS = {
    "health_beauty": {
        "description": "Health & beauty products — high margin, small/light, fast sellers",
        "finder": {"category": 3760901, "min_drop": 25, "price_range": (8, 40), "max_bsr": 75000},
        "deals": {"source": "keepa"},
        "a2a": {"a2a_type": "warehouse"},
    },
    "toys": {
        "description": "Toys & games — seasonal spikes, brand gating common",
        "finder": {"category": 165793011, "min_drop": 30, "price_range": (10, 60), "max_bsr": 100000},
        "deals": {"source": "keepa"},
        "a2a": {"a2a_type": "warehouse"},
    },
    "sports": {
        "description": "Sports & outdoors — steady demand, good margins",
        "finder": {"category": 3375251, "min_drop": 25, "price_range": (15, 80), "max_bsr": 100000},
        "deals": {"source": "keepa"},
        "a2a": {"a2a_type": "warehouse"},
    },
    "electronics": {
        "description": "Electronics — high ticket, fast movers, competitive",
        "finder": {"category": 172282, "min_drop": 20, "price_range": (20, 100), "max_bsr": 50000},
        "deals": {"source": "keepa"},
        "a2a": {"a2a_type": "warehouse"},
    },
    "home_kitchen": {
        "description": "Home & kitchen — broad category, steady demand",
        "finder": {"category": 1055398, "min_drop": 25, "price_range": (10, 50), "max_bsr": 75000},
        "deals": {"source": "keepa"},
        "a2a": {"a2a_type": "warehouse"},
    },
    "grocery": {
        "description": "Grocery & gourmet — replenishable, ungated for most sellers",
        "finder": {"category": 16310101, "min_drop": 20, "price_range": (5, 30), "max_bsr": 50000},
        "deals": {"source": "keepa"},
        "a2a": {"a2a_type": "multipack"},
    },
    "all": {
        "description": "Scan all categories — maximum deal flow",
        "finder": {"min_drop": 30, "price_range": (10, 50), "max_bsr": 100000},
        "deals": {"source": "all"},
        "a2a": {"a2a_type": "warehouse"},
    },
}


def run_smart_scan(
    max_tokens: int = 500,
    preset: str = "all",
    quick: bool = False,
    count: int = 30,
    min_profit: float = 2.0,
) -> dict:
    """Run all working Keepa-based sourcing modes and compile results.

    Args:
        max_tokens: Total Keepa token budget across all modes.
        preset: Category preset name.
        quick: If True, only run deals + a2a (fast, ~50 tokens).
        count: Max results per mode.
        min_profit: Minimum profit per unit to include.

    Returns:
        dict with metadata, mode_results, and compiled products list.
    """
    from source import mode_deals, mode_finder, mode_a2a, mode_oos
    from batch_keepa_analyzer import check_tokens

    start_time = time.time()
    scan_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Check token balance
    tokens_left, refill_rate = check_tokens()
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"SMART SCAN — {scan_date}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"Keepa tokens: {tokens_left} available, budget: {max_tokens}", file=sys.stderr)
    print(f"Preset: {preset} | Quick: {quick} | Min profit: ${min_profit}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    if tokens_left < 50:
        print("[smart_scan] Token balance too low. Try again later.", file=sys.stderr)
        return {"error": "insufficient_tokens", "tokens_left": tokens_left}

    preset_config = PRESETS.get(preset, PRESETS["all"])
    all_results = []
    mode_summaries = []
    tokens_used_estimate = 0

    # ── Mode 1: Keepa Deals (cheapest, fastest) ─────────────────────────
    print("[1/4] Running Keepa Deals scan...", file=sys.stderr)
    try:
        deals_config = preset_config.get("deals", {})
        deals_results = mode_deals(
            source=deals_config.get("source", "keepa"),
            min_drop=15,
            count=count,
            min_profit=min_profit,
        )
        tokens_used_estimate += 5
        mode_summaries.append({"mode": "deals", "found": len(deals_results)})
        for r in deals_results:
            r["_source_mode"] = "deals"
        all_results.extend(deals_results)
        print(f"  → {len(deals_results)} products found", file=sys.stderr)
    except Exception as e:
        print(f"  → Deals error: {e}", file=sys.stderr)
        mode_summaries.append({"mode": "deals", "found": 0, "error": str(e)})

    # ── Mode 2: A2A Warehouse Deals ──────────────────────────────────────
    print("[2/4] Running A2A Warehouse scan...", file=sys.stderr)
    try:
        a2a_config = preset_config.get("a2a", {})
        a2a_results = mode_a2a(
            a2a_type=a2a_config.get("a2a_type", "warehouse"),
            count=count,
            min_discount=30,
            max_bsr=100000,
        )
        tokens_used_estimate += 10
        mode_summaries.append({"mode": "a2a", "found": len(a2a_results)})
        for r in a2a_results:
            r["_source_mode"] = "a2a"
        all_results.extend(a2a_results)
        print(f"  → {len(a2a_results)} products found", file=sys.stderr)
    except Exception as e:
        print(f"  → A2A error: {e}", file=sys.stderr)
        mode_summaries.append({"mode": "a2a", "found": 0, "error": str(e)})

    if not quick:
        # ── Mode 3: Keepa Product Finder ─────────────────────────────────
        if tokens_used_estimate < max_tokens - 10:
            print("[3/4] Running Keepa Finder scan...", file=sys.stderr)
            try:
                finder_config = preset_config.get("finder", {})
                finder_results = mode_finder(
                    min_drop=finder_config.get("min_drop", 30),
                    max_bsr=finder_config.get("max_bsr", 100000),
                    price_range=finder_config.get("price_range", (10, 50)),
                    min_sellers=3,
                    max_sellers=15,
                    category=finder_config.get("category", 0),
                    count=count,
                    reverse_source=False,
                )
                tokens_used_estimate += 10
                mode_summaries.append({"mode": "finder", "found": len(finder_results)})
                for r in finder_results:
                    r["_source_mode"] = "finder"
                all_results.extend(finder_results)
                print(f"  → {len(finder_results)} products found", file=sys.stderr)
            except Exception as e:
                print(f"  → Finder error: {e}", file=sys.stderr)
                mode_summaries.append({"mode": "finder", "found": 0, "error": str(e)})
        else:
            print("[3/4] Skipping Finder (token budget)", file=sys.stderr)

        # ── Mode 4: OOS Opportunities ────────────────────────────────────
        if tokens_used_estimate < max_tokens - 10:
            print("[4/4] Running OOS scan...", file=sys.stderr)
            try:
                oos_results = mode_oos(
                    count=count,
                    max_bsr=75000,
                    min_reviews=50,
                    reverse_source=False,
                )
                tokens_used_estimate += 10
                mode_summaries.append({"mode": "oos", "found": len(oos_results)})
                for r in oos_results:
                    r["_source_mode"] = "oos"
                all_results.extend(oos_results)
                print(f"  → {len(oos_results)} products found", file=sys.stderr)
            except Exception as e:
                print(f"  → OOS error: {e}", file=sys.stderr)
                mode_summaries.append({"mode": "oos", "found": 0, "error": str(e)})
        else:
            print("[4/4] Skipping OOS (token budget)", file=sys.stderr)
    else:
        print("[3/4] Skipped (quick mode)", file=sys.stderr)
        print("[4/4] Skipped (quick mode)", file=sys.stderr)

    # ── Compile + Deduplicate ────────────────────────────────────────────
    seen_asins = {}
    for r in all_results:
        asin = r.get("asin", "")
        if not asin:
            continue
        profit = r.get("profitability", {}).get("profit_per_unit", 0) or r.get("estimated_profit", 0) or 0
        if asin not in seen_asins or profit > (seen_asins[asin].get("profitability", {}).get("profit_per_unit", 0) or 0):
            seen_asins[asin] = r

    unique_products = list(seen_asins.values())

    # ── QUALITY GATES — Filter garbage before output ─────────────────────
    print(f"\n[smart_scan] Applying quality gates to {len(unique_products)} products...", file=sys.stderr)

    gated_products = []
    skip_reasons = {"pack_mismatch": 0, "bad_buy_link": 0, "competition": 0,
                    "private_label": 0, "low_profit": 0, "verified_reject": 0}

    for p in unique_products:
        asin = p.get("asin", "")
        buy_price = p.get("buy_cost") or p.get("retail_price") or p.get("source_price") or 0
        amazon_price = p.get("amazon_price") or p.get("sell_price") or 0
        profit = p.get("profitability", {}).get("profit_per_unit", 0) or p.get("estimated_profit", 0) or 0
        source_url = p.get("source_url", "")
        fba_sellers = p.get("fba_seller_count")
        amazon_on = p.get("amazon_on_listing")

        # Gate 1: Pack size mismatch detection (price ratio check)
        # If retail is 3x+ cheaper than Amazon, it's almost certainly a pack mismatch
        if buy_price > 0 and amazon_price > 0:
            price_ratio = amazon_price / buy_price
            if price_ratio >= 3.0:
                # Check if pack counts are explicitly confirmed in titles
                retail_title = p.get("retail_title") or p.get("name") or ""
                amazon_title = p.get("amazon_title") or p.get("title") or ""
                import re as _re
                retail_pack = _re.search(r'(\d+)\s*(?:pack|count|ct|pk)\b', retail_title.lower())
                amazon_pack = _re.search(r'(\d+)\s*(?:pack|count|ct|pk)\b', amazon_title.lower())
                if not (retail_pack and amazon_pack):
                    # Can't confirm pack sizes match — likely mismatch
                    p["_skip_reason"] = f"Likely pack mismatch (price ratio {price_ratio:.1f}x, pack counts unconfirmed)"
                    skip_reasons["pack_mismatch"] += 1
                    continue

        # Gate 2: Buy link validation — must be a direct product page
        if source_url:
            bad_url_patterns = ["/productlist/", "/browse/", "/c/", "/sale-event/",
                                "/shop/", "?q=", "/search/", "Brands=yes",
                                "/store/c/", "N="]
            is_bad_link = any(pat in source_url for pat in bad_url_patterns)
            has_product_id = any(pat in source_url for pat in ["/p/", "/product/", "/dp/", "/ip/",
                                                                "/A-", "ID=prod", "ID=3"])
            if is_bad_link and not has_product_id:
                p["_skip_reason"] = f"Buy link is a category/search page, not a product: {source_url[:60]}"
                skip_reasons["bad_buy_link"] += 1
                continue

        # Gate 3: Competition check from Keepa stats
        stats = p.get("stats", {}) or {}
        current = stats.get("current", []) if stats else []

        # Pull seller count from various locations
        if fba_sellers is None and current and len(current) > 34:
            raw = current[34]
            if raw and raw >= 0:
                fba_sellers = raw
                p["fba_seller_count"] = fba_sellers

        # Pull Amazon-on-listing
        if amazon_on is None and current and len(current) > 0:
            if current[0] and current[0] > 0:
                amazon_on = True
                p["amazon_on_listing"] = True

        # Skip private label (0-1 sellers)
        if fba_sellers is not None and fba_sellers <= 1:
            p["_skip_reason"] = f"Likely private label (only {fba_sellers} FBA seller)"
            skip_reasons["private_label"] += 1
            continue

        # Skip saturated (>20 sellers)
        if fba_sellers is not None and fba_sellers > 20:
            p["_skip_reason"] = f"Saturated listing ({fba_sellers} FBA sellers)"
            skip_reasons["competition"] += 1
            continue

        # Skip Amazon on listing (can't win Buy Box)
        if amazon_on:
            p["_skip_reason"] = "Amazon is a seller on this listing"
            skip_reasons["competition"] += 1
            continue

        # Gate 4: Minimum real profit after realistic fees
        if profit <= 2.0:
            p["_skip_reason"] = f"Profit too low (${profit:.2f})"
            skip_reasons["low_profit"] += 1
            continue

        gated_products.append(p)

    # Run through verify_sourcing_results for final check
    try:
        from verify_sourcing_results import verify_results as _verify
        verification = _verify(gated_products, strict=False)
        final_products = verification.get("verified", []) + verification.get("flagged", [])
        skip_reasons["verified_reject"] = len(verification.get("rejected", []))
        print(f"[smart_scan] Verification: {len(final_products)} passed, "
              f"{skip_reasons['verified_reject']} rejected", file=sys.stderr)
    except ImportError:
        print("[smart_scan] WARNING: verify_sourcing_results not available, skipping verification", file=sys.stderr)
        final_products = gated_products
    except Exception as e:
        print(f"[smart_scan] Verification error: {e} — using unverified results", file=sys.stderr)
        final_products = gated_products

    # Sort by profit
    final_products.sort(
        key=lambda x: x.get("profitability", {}).get("profit_per_unit", 0) or x.get("estimated_profit", 0) or 0,
        reverse=True,
    )

    print(f"[smart_scan] Quality gates: {len(unique_products)} → {len(final_products)} products", file=sys.stderr)
    for reason, count in skip_reasons.items():
        if count > 0:
            print(f"  Removed {count} — {reason}", file=sys.stderr)

    elapsed = time.time() - start_time

    # ── Output ───────────────────────────────────────────────────────────
    output = {
        "metadata": {
            "scan_type": "smart_scan",
            "preset": preset,
            "quick": quick,
            "scan_date": scan_date,
            "elapsed_seconds": round(elapsed, 1),
            "tokens_estimated": tokens_used_estimate,
            "total_raw": len(all_results),
            "total_unique": len(unique_products),
            "total_after_gates": len(final_products),
        },
        "mode_results": mode_summaries,
        "products": final_products,
    }

    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"smart_scan_{date_str}.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    # Print summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"SMART SCAN COMPLETE", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    for ms in mode_summaries:
        status = f"{ms['found']} found" if 'error' not in ms else f"ERROR: {ms['error'][:40]}"
        print(f"  {ms['mode']:<10}: {status}", file=sys.stderr)
    print(f"\n  Total raw: {len(all_results)}", file=sys.stderr)
    print(f"  Unique ASINs: {len(unique_products)} → After gates: {len(final_products)}", file=sys.stderr)
    buys = sum(1 for p in final_products if p.get("verdict") == "BUY" or p.get("profitability", {}).get("verdict") == "BUY")
    maybes = sum(1 for p in final_products if p.get("verdict") == "MAYBE" or p.get("profitability", {}).get("verdict") == "MAYBE")
    print(f"  BUY: {buys} | MAYBE: {maybes}", file=sys.stderr)
    print(f"  Time: {elapsed:.0f}s | ~{tokens_used_estimate} tokens", file=sys.stderr)
    print(f"  Saved: {output_path}", file=sys.stderr)

    # Print top deals
    if final_products:
        print(f"\n  TOP DEALS:", file=sys.stderr)
        for i, p in enumerate(final_products[:10], 1):
            asin = p.get("asin", "?")
            title = (p.get("amazon_title") or p.get("title", "?"))[:40]
            profit = p.get("profitability", {}).get("profit_per_unit", 0) or p.get("estimated_profit", 0) or 0
            roi = p.get("profitability", {}).get("roi_percent", 0) or p.get("estimated_roi", 0) or 0
            verdict = p.get("verdict") or p.get("profitability", {}).get("verdict", "?")
            source = p.get("_source_mode", "?")
            buy_url = p.get("source_url", "")
            print(f"  {i:>2}. [{verdict:<8}] {title}", file=sys.stderr)
            print(f"      ${profit:.2f} profit | {roi:.0f}% ROI | {source} | {asin}", file=sys.stderr)
            if buy_url:
                print(f"      Buy: {buy_url}", file=sys.stderr)

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Smart Scan — run all working Keepa modes in one command"
    )
    parser.add_argument("--tokens", type=int, default=500, help="Keepa token budget (default: 500)")
    parser.add_argument("--preset", default="all",
                        choices=list(PRESETS.keys()),
                        help="Category preset (default: all)")
    parser.add_argument("--quick", action="store_true", help="Fast scan: deals + a2a only (~50 tokens)")
    parser.add_argument("--count", type=int, default=30, help="Max results per mode (default: 30)")
    parser.add_argument("--min-profit", type=float, default=2.0, help="Min profit per unit (default: $2)")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    args = parser.parse_args()

    output = run_smart_scan(
        max_tokens=args.tokens,
        preset=args.preset,
        quick=args.quick,
        count=args.count,
        min_profit=args.min_profit,
    )

    if args.json and output:
        print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
