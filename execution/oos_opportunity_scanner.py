#!/usr/bin/env python3
"""
Script: oos_opportunity_scanner.py
Purpose: Find Amazon listings where all FBA sellers have dropped off but the
         product is still available at retail. You enter as the sole seller.

This is the highest-margin signal in online arbitrage. Nepeto built their
entire business around this.

Pipeline:
  1. Keepa Deals API (isOutOfStock=True) → candidate ASINs
  2. Filter by BSR, review count, OOS duration
  3. For each candidate, search retailers for availability
  4. Calculate profitability via calculate_fba_profitability
  5. Output with OOS_OPPORTUNITY verdict + estimated monopoly window

Usage:
  python execution/oos_opportunity_scanner.py --count 30 --max-bsr 100000
  python execution/oos_opportunity_scanner.py --count 30 --category 0 --min-reviews 50
  python execution/oos_opportunity_scanner.py --count 30 --reverse-source --max-retailers 10

Keepa cost: ~35 tokens per full scan (5 for deals + 1 per ASIN verification)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"


def scan_oos_opportunities(count=30, category=0, max_bsr=100000,
                           min_reviews=50, price_range=(500, 5000),
                           reverse_source=False, max_retailers=10,
                           verbose=False):
    """Main OOS scanning pipeline.

    Args:
        count: Max OOS candidates to find
        category: Keepa category ID (0 = all)
        max_bsr: Maximum BSR threshold
        min_reviews: Minimum review count (ensures established product)
        price_range: (min_cents, max_cents) price range
        reverse_source: If True, search retailers for each candidate
        max_retailers: Max retailers to search per candidate
        verbose: Print progress

    Returns:
        list of opportunity dicts
    """
    from keepa_client import KeepaClient

    try:
        client = KeepaClient(tier="pro")
    except ValueError:
        print("[oos] ERROR: KEEPA_API_KEY not set. OOS scanning requires Keepa Pro.",
              file=sys.stderr)
        return []

    # ── Step 1: Get OOS deals from Keepa ──────────────────────────────────
    if verbose:
        print(f"[oos] Scanning for OOS opportunities (max_bsr={max_bsr}, "
              f"min_reviews={min_reviews}, count={count})...", file=sys.stderr)

    deals = client.get_oos_deals(
        category=category,
        price_range=price_range,
        max_bsr=max_bsr,
        count=count,
    )

    if not deals:
        if verbose:
            print("[oos] No OOS deals found from Keepa.", file=sys.stderr)
        return []

    if verbose:
        print(f"[oos] Found {len(deals)} OOS candidates from Keepa.", file=sys.stderr)

    # ── Step 2: Enrich with seller history & filter ───────────────────────
    opportunities = []
    for i, deal in enumerate(deals):
        asin = deal["asin"]

        # Filter by review count (if available from deals data)
        if deal.get("review_count") and deal["review_count"] < min_reviews:
            if verbose:
                print(f"[oos] SKIP {asin}: reviews={deal.get('review_count')} < {min_reviews}",
                      file=sys.stderr)
            continue

        # Get seller count history to estimate OOS duration
        seller_history = client.get_seller_count_history(asin)

        days_oos = seller_history.get("days_oos")
        if days_oos is not None and days_oos < 0.5:
            if verbose:
                print(f"[oos] SKIP {asin}: OOS for only {days_oos} days (too fresh)",
                      file=sys.stderr)
            continue

        opportunity = {
            "asin": asin,
            "title": deal["title"],
            "last_known_price": deal["last_known_price"],
            "category": deal["category"],
            "bsr": deal["bsr"],
            "review_count": deal.get("review_count"),
            "image": deal.get("image", ""),
            "amazon_url": f"https://www.amazon.com/dp/{asin}",
            "days_oos": days_oos,
            "last_fba_count": seller_history.get("last_fba_count"),
            "seller_trend": seller_history.get("trend"),
            "verdict": "OOS_OPPORTUNITY",
        }

        opportunities.append(opportunity)

        if verbose:
            print(f"[oos] [{i+1}/{len(deals)}] {asin} — "
                  f"${deal['last_known_price']} | BSR {deal['bsr']} | "
                  f"OOS {days_oos or '?'} days | {deal['title'][:50]}",
                  file=sys.stderr)

    if verbose:
        print(f"[oos] {len(opportunities)} opportunities after filtering.", file=sys.stderr)

    # ── Step 3: Reverse-source from retailers (optional) ──────────────────
    if reverse_source and opportunities:
        if verbose:
            print(f"[oos] Reverse-sourcing {len(opportunities)} products across "
                  f"{max_retailers} retailers...", file=sys.stderr)

        try:
            from multi_retailer_search import search_product_across_retailers
            from calculate_fba_profitability import calculate_profitability
        except ImportError:
            if verbose:
                print("[oos] WARNING: multi_retailer_search or calculate_fba_profitability "
                      "not available. Skipping reverse-source.", file=sys.stderr)
            return opportunities

        for opp in opportunities:
            title = opp["title"]
            try:
                retail_results = search_product_across_retailers(
                    query=title,
                    max_retailers=max_retailers,
                    max_products_per_retailer=3,
                )
            except Exception as e:
                if verbose:
                    print(f"[oos] Retail search failed for {opp['asin']}: {e}",
                          file=sys.stderr)
                opp["retail_sources"] = []
                continue

            sources = []
            for result in (retail_results or []):
                buy_cost = result.get("price")
                if not buy_cost or buy_cost <= 0:
                    continue

                # Calculate profitability
                sell_price = opp["last_known_price"]
                try:
                    profit_data = calculate_profitability(
                        buy_cost=buy_cost,
                        sell_price=sell_price,
                        category=opp.get("category", ""),
                    )
                except Exception:
                    profit_data = {
                        "profit_per_unit": sell_price - buy_cost - (sell_price * 0.20),
                        "roi_percent": ((sell_price - buy_cost - (sell_price * 0.20)) / buy_cost * 100)
                        if buy_cost > 0 else 0,
                    }

                sources.append({
                    "retailer": result.get("retailer", "Unknown"),
                    "retail_url": result.get("url", ""),
                    "buy_cost": round(buy_cost, 2),
                    "profit_per_unit": round(profit_data.get("profit_per_unit", 0), 2),
                    "roi_percent": round(profit_data.get("roi_percent", 0), 1),
                })

            # Sort sources by ROI
            sources.sort(key=lambda x: x.get("roi_percent", 0), reverse=True)
            opp["retail_sources"] = sources

            if sources and verbose:
                best = sources[0]
                print(f"[oos] {opp['asin']} best source: {best['retailer']} "
                      f"${best['buy_cost']} → ${opp['last_known_price']} "
                      f"({best['roi_percent']}% ROI)", file=sys.stderr)

    return opportunities


def save_results(opportunities, output_path=None):
    """Save results to JSON and print summary."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_path is None:
        output_path = TMP_DIR / f"oos_{timestamp}.json"
    else:
        output_path = Path(output_path)

    results = {
        "timestamp": datetime.now().isoformat(),
        "scan_type": "oos_opportunity",
        "total_opportunities": len(opportunities),
        "opportunities": opportunities,
    }

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*70}")
    print(f"OOS OPPORTUNITY SCAN RESULTS — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}")
    print(f"Total opportunities found: {len(opportunities)}")
    print(f"Results saved to: {output_path}")
    print()

    if not opportunities:
        print("No OOS opportunities found. Try broadening filters.")
        return output_path

    for i, opp in enumerate(opportunities, 1):
        print(f"  [{i}] {opp['asin']} — {opp['title'][:60]}")
        print(f"      Amazon: {opp['amazon_url']}")
        print(f"      Last price: ${opp['last_known_price']} | BSR: {opp['bsr']} | "
              f"OOS: {opp.get('days_oos', '?')} days")

        if opp.get("retail_sources"):
            best = opp["retail_sources"][0]
            print(f"      Best source: {best['retailer']} @ ${best['buy_cost']} "
                  f"→ {best['roi_percent']}% ROI (${best['profit_per_unit']}/unit)")
            if best.get("retail_url"):
                print(f"      Source URL: {best['retail_url']}")
        print()

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Scan for out-of-stock Amazon opportunities"
    )
    parser.add_argument("--count", type=int, default=30,
                        help="Max candidates to scan (default: 30)")
    parser.add_argument("--category", type=int, default=0,
                        help="Keepa category ID (0 = all)")
    parser.add_argument("--max-bsr", type=int, default=100000,
                        help="Maximum BSR threshold (default: 100000)")
    parser.add_argument("--min-reviews", type=int, default=50,
                        help="Minimum review count (default: 50)")
    parser.add_argument("--min-price", type=float, default=5.0,
                        help="Minimum price in dollars (default: 5.0)")
    parser.add_argument("--max-price", type=float, default=50.0,
                        help="Maximum price in dollars (default: 50.0)")
    parser.add_argument("--reverse-source", action="store_true",
                        help="Search retailers for each OOS product")
    parser.add_argument("--max-retailers", type=int, default=10,
                        help="Max retailers to search per product (default: 10)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: auto-generated)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print progress to stderr")

    args = parser.parse_args()

    price_range = (int(args.min_price * 100), int(args.max_price * 100))

    opportunities = scan_oos_opportunities(
        count=args.count,
        category=args.category,
        max_bsr=args.max_bsr,
        min_reviews=args.min_reviews,
        price_range=price_range,
        reverse_source=args.reverse_source,
        max_retailers=args.max_retailers,
        verbose=args.verbose,
    )

    save_results(opportunities, args.output)


if __name__ == "__main__":
    main()
