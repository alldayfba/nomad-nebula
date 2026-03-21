from __future__ import annotations
"""
Reverse Search Mode — Start from known ASINs, find retail sources cheaper than max_cost.
The #1 power feature of Tactical Arbitrage: demand is validated FIRST.

Usage:
    python execution/source.py reverse --asins B001234,B005678 --min-roi 30
    python execution/source.py reverse --asins-file path/to/asins.txt --min-roi 30
"""
import os
import sys
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)
sys.path.insert(0, os.path.dirname(__file__))


def run_reverse_search(
    asins: list[str],
    min_roi: float = 30.0,
    min_profit: float = 3.00,
    max_workers: int = 5,
    output_format: str = "table",
) -> list[dict]:
    """
    Reverse search: given ASINs, find retail sources where price <= max_cost.

    Returns list of sourcing opportunities sorted by ROI descending.
    """
    from dotenv import load_dotenv
    load_dotenv()

    opportunities = []

    # Step 1: Get Keepa data for all ASINs (what Amazon price + fees look like)
    try:
        from keepa_client import KeepaClient
        keepa = KeepaClient(os.getenv("KEEPA_API_KEY"))
    except Exception as e:
        logger.error(f"Keepa required for reverse search: {e}")
        return []

    logger.info(f"Fetching Amazon data for {len(asins)} ASINs...")
    try:
        products = keepa.get_products(asins)
    except Exception as e:
        logger.error(f"Keepa product fetch failed: {e}")
        return []

    # Step 2: Calculate max_cost for each ASIN
    asin_targets: dict[str, dict] = {}
    for product in products:
        asin = product.get("asin", "")
        if not asin:
            continue

        try:
            from calculate_fba_profitability import calculate_product_profitability
            sell_price = product.get("fba_price") or product.get("buy_box_price") or product.get("amazon_price", 0)
            if not sell_price or sell_price <= 0:
                continue

            weight = product.get("weight_lbs", 0.5)
            category = product.get("category", "")

            # Calculate what max buy cost would be at target ROI
            prof = calculate_product_profitability(
                buy_cost=sell_price * 0.5,  # placeholder
                sell_price=sell_price,
                weight_lbs=weight,
                category=category,
            )
            max_cost = prof.get("max_cost", 0)
            if max_cost <= 0:
                continue

            asin_targets[asin] = {
                "asin": asin,
                "title": product.get("title", ""),
                "amazon_price": sell_price,
                "max_cost": max_cost,
                "category": category,
                "bsr": product.get("bsr", 0),
                "fba_seller_count": product.get("fba_seller_count", 0),
            }
        except Exception as e:
            logger.debug(f"Could not calculate max_cost for {asin}: {e}")

    if not asin_targets:
        logger.warning("No valid targets found after Keepa lookup")
        return []

    logger.info(f"Searching retailers for {len(asin_targets)} ASINs (max costs: ${min(v['max_cost'] for v in asin_targets.values()):.2f}–${max(v['max_cost'] for v in asin_targets.values()):.2f})")

    # Step 3: Search retailers for each ASIN
    try:
        from multi_retailer_search import search_multi_retailer
    except ImportError:
        logger.warning("multi_retailer_search not available, using source.py asin mode")
        search_multi_retailer = None

    for asin, target in asin_targets.items():
        max_cost = target["max_cost"]
        title = target["title"]

        # Search retailers using the asin sourcing mode via existing infrastructure
        try:
            import subprocess
            result = subprocess.run(
                [
                    sys.executable, os.path.join(os.path.dirname(__file__), "source.py"),
                    "asin", "--asin", asin, "--max-results", "10", "--output", "json"
                ],
                capture_output=True, text=True, timeout=180,
                cwd=os.path.dirname(os.path.dirname(__file__))
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    for p in data.get("products", []):
                        retail_price = p.get("buy_cost", 0) or p.get("retail_price", 0)
                        if retail_price > 0 and retail_price <= max_cost:
                            roi = ((target["amazon_price"] - retail_price) / retail_price * 100) if retail_price > 0 else 0
                            if roi >= min_roi:
                                opportunities.append({
                                    **p,
                                    "asin": asin,
                                    "amazon_title": title,
                                    "amazon_price": target["amazon_price"],
                                    "max_cost": max_cost,
                                    "retail_price": retail_price,
                                    "estimated_roi": round(roi, 1),
                                    "source_type": "reverse_search",
                                })
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.debug(f"Retailer search for {asin} failed: {e}")

    # Sort by ROI descending
    opportunities.sort(key=lambda x: x.get("estimated_roi", 0), reverse=True)

    logger.info(f"Reverse search complete: {len(opportunities)} opportunities found")
    return opportunities


def load_asins_from_file(filepath: str) -> list[str]:
    """Load ASINs from a text file (one per line, or comma-separated)."""
    with open(filepath) as f:
        content = f.read()
    # Handle both newline and comma separated
    asins = [a.strip() for a in content.replace(",", "\n").split("\n")]
    return [a for a in asins if a and len(a) == 10 and a.startswith("B")]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reverse search: ASIN to cheapest retail source")
    parser.add_argument("--asins", help="Comma-separated ASIN list")
    parser.add_argument("--asins-file", help="Path to file with ASINs")
    parser.add_argument("--min-roi", type=float, default=30.0)
    parser.add_argument("--min-profit", type=float, default=3.00)
    args = parser.parse_args()

    asins = []
    if args.asins:
        asins = [a.strip() for a in args.asins.split(",")]
    elif args.asins_file:
        asins = load_asins_from_file(args.asins_file)

    if not asins:
        print("Provide --asins or --asins-file")
        sys.exit(1)

    results = run_reverse_search(asins, args.min_roi, args.min_profit)
    print(json.dumps(results, indent=2))
