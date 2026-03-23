#!/usr/bin/env python3
from __future__ import annotations
"""
Script: batch_keepa_analyzer.py
Purpose: Batch-process a wholesale manifest through Keepa API for FBA profitability.
         Uses Keepa's batch UPC lookup (100 UPCs/request) instead of individual searches.
         ~100x faster than Playwright scraping, no throttle issues.
Inputs:  --manifest (CSV path)
Outputs: JSON with ranked BUY/MAYBE/SKIP products
"""

import csv
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import requests

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY")
if not KEEPA_API_KEY:
    print("ERROR: KEEPA_API_KEY not set in .env", file=sys.stderr)
    sys.exit(1)

# Import profitability calculator
from execution.calculate_fba_profitability import calculate_product_profitability


def check_tokens():
    """Check current Keepa token balance."""
    try:
        r = requests.get(f"https://api.keepa.com/token?key={KEEPA_API_KEY}", timeout=10)
        data = r.json()
        return data.get("tokensLeft", 0), data.get("refillRate", 5)
    except Exception as e:
        print(f"WARNING: Keepa token check failed: {e}", file=sys.stderr)
        return (0, 0)


def batch_upc_lookup(upcs: list[str], stats: int = 180) -> dict:
    """Look up multiple UPCs via Keepa product API. Returns {upc: [products]}."""
    code_str = ",".join(upcs)
    params = {
        "key": KEEPA_API_KEY,
        "domain": "1",
        "code": code_str,
        "stats": str(stats),
    }
    try:
        r = requests.get("https://api.keepa.com/product", params=params, timeout=30)
        data = r.json()
    except Exception as e:
        print(f"WARNING: Keepa product lookup failed: {e}", file=sys.stderr)
        return {}

    tokens_left = data.get("tokensLeft", 0)
    tokens_consumed = data.get("tokensConsumed", 0)

    # Map results back to UPCs
    upc_map = {}
    for product in data.get("products", []):
        # Keepa stores EAN list
        ean_list = product.get("eanList", []) or []
        upc_list = product.get("upcList", []) or []
        all_codes = set(ean_list + upc_list)

        for upc in upcs:
            # Check if this product matches the UPC (partial match for zero-padded)
            if upc in all_codes or upc.lstrip("0") in {c.lstrip("0") for c in all_codes}:
                if upc not in upc_map:
                    upc_map[upc] = []
                upc_map[upc].append(product)

    return upc_map, tokens_left, tokens_consumed


def pick_best_match(products: list[dict], wholesale_name: str) -> dict | None:
    """From multiple Keepa results for a UPC, pick the best match for FBA."""
    if not products:
        return None

    scored = []
    for p in products:
        asin = p.get("asin", "")
        title = p.get("title", "")
        rank = p.get("salesRankCurrent", -1) or -1

        # Parse current price from stats — try multiple sources aggressively
        stats = p.get("stats", {}) or {}
        current_price = None
        current = stats.get("current", [])
        avg30 = stats.get("avg30", [])
        avg90 = stats.get("avg90", [])

        # Priority: Amazon price > FBA price > Buy Box > New 3P > buyBoxPrice stat
        # Rationale: For arbitrage, you want the actual sell price, not the lowest
        # competitor price (Buy Box). Amazon's price or FBA price = what you'd sell at.
        if not current_price and len(current) > 0 and current[0] and current[0] > 0:
            current_price = current[0] / 100.0  # Amazon's own price
        if not current_price and len(current) > 10 and current[10] and current[10] > 0:
            current_price = current[10] / 100.0  # FBA price
        if not current_price and len(current) > 18 and current[18] and current[18] > 0:
            current_price = current[18] / 100.0  # Buy Box price
        if not current_price and len(current) > 1 and current[1] and current[1] > 0:
            current_price = current[1] / 100.0  # New 3rd party price
        buy_box_price = stats.get("buyBoxPrice", -1)
        if not current_price and buy_box_price and buy_box_price > 0:
            current_price = buy_box_price / 100.0
        # Fallback to 30-day or 90-day averages (same priority order)
        if not current_price:
            for avg_arr in [avg30, avg90]:
                for idx in [0, 10, 18, 1]:
                    if len(avg_arr) > idx and avg_arr[idx] and avg_arr[idx] > 0:
                        current_price = avg_arr[idx] / 100.0
                        break
                if current_price:
                    break

        # Score: prefer products with price data, good rank, matching title
        score = 0
        if current_price and current_price > 0:
            score += 50
        if rank > 0:
            score += 30
            if rank < 100000:
                score += 20
            if rank < 50000:
                score += 10
        # Title similarity bonus
        name_words = set(re.findall(r"[a-z0-9]+", wholesale_name.lower()))
        title_words = set(re.findall(r"[a-z0-9]+", title.lower()))
        filler = {"the", "a", "an", "and", "or", "of", "for", "with", "in", "on", "by"}
        name_words -= filler
        title_words -= filler
        if name_words and title_words:
            overlap = len(name_words & title_words) / max(len(name_words), len(title_words))
            score += overlap * 30

        scored.append((score, p, current_price))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_product, best_price = scored[0]

    if best_price is None or best_price <= 0:
        return None  # No usable price data

    return {
        "product": best_product,
        "price": best_price,
        "score": best_score,
    }


def extract_keepa_data(product: dict, price: float) -> dict:
    """Extract structured Amazon data from a Keepa product response."""
    stats = product.get("stats", {}) or {}

    # Sales rank
    rank = product.get("salesRankCurrent", None)
    if rank and rank < 0:
        rank = None

    # Category
    cat_tree = product.get("categoryTree", [])
    category = cat_tree[-1].get("name", "") if cat_tree else None
    root_category = cat_tree[0].get("name", "") if cat_tree else None

    # Seller counts from stats
    fba_seller_count = None
    new_offer_count = None
    current_stats = stats.get("current", [])
    if current_stats and len(current_stats) > 34:
        fba_count_raw = current_stats[34]
        if fba_count_raw and fba_count_raw >= 0:
            fba_seller_count = fba_count_raw
    if current_stats and len(current_stats) > 11:
        new_count_raw = current_stats[11]
        if new_count_raw and new_count_raw >= 0:
            new_offer_count = new_count_raw

    # Amazon on listing: check if Amazon price (index 0) is positive
    amazon_on_listing = None
    if current_stats and len(current_stats) > 0:
        amz_price = current_stats[0]
        if amz_price and amz_price > 0:
            amazon_on_listing = True
        elif amz_price is not None:
            amazon_on_listing = False

    # Weight (for accurate FBA fee calculation)
    weight_lbs = None
    package_weight = product.get("packageWeight")
    item_weight = product.get("itemWeight")
    if package_weight and package_weight > 0:
        weight_lbs = package_weight / 100.0  # Keepa stores in hundredths of pounds
    elif item_weight and item_weight > 0:
        weight_lbs = item_weight / 100.0

    # Price staleness: check how recent the price data is
    price_age_days = None
    csv_data = product.get("csv", [])
    if csv_data and len(csv_data) > 0:
        # Check Amazon price CSV (index 0) for last timestamp
        amz_csv = csv_data[0] if csv_data[0] else []
        if amz_csv and len(amz_csv) >= 2:
            import time as _time
            last_ts_keepa = amz_csv[-2]  # Second-to-last = last timestamp
            if last_ts_keepa and last_ts_keepa > 0:
                # Keepa epoch: 2011-01-01
                last_unix = 1293840000 + (last_ts_keepa * 60)
                price_age_days = round((_time.time() - last_unix) / 86400, 1)

    # Price history for stability checks (avg30, avg90 from stats)
    avg30 = stats.get("avg30", [])
    avg90 = stats.get("avg90", [])

    # Extract average prices at different windows (same index priority as current)
    avg30_price = None
    avg90_price = None
    for idx in [0, 10, 18, 1]:  # Amazon, FBA, BuyBox, New3P
        if avg30_price is None and avg30 and len(avg30) > idx and avg30[idx] and avg30[idx] > 0:
            avg30_price = avg30[idx] / 100.0
        if avg90_price is None and avg90 and len(avg90) > idx and avg90[idx] and avg90[idx] > 0:
            avg90_price = avg90[idx] / 100.0

    # Price stability analysis
    price_stability = {}
    if price and price > 0:
        if avg90_price and avg90_price > 0:
            spike_pct = ((price - avg90_price) / avg90_price) * 100
            price_stability["vs_90d_avg"] = round(spike_pct, 1)
            price_stability["avg_90d"] = round(avg90_price, 2)
            price_stability["is_spike"] = spike_pct > 20  # >20% above 90d avg = spike
        if avg30_price and avg30_price > 0:
            price_stability["avg_30d"] = round(avg30_price, 2)
            change_30d = ((price - avg30_price) / avg30_price) * 100
            price_stability["vs_30d_avg"] = round(change_30d, 1)

    return {
        "asin": product.get("asin", ""),
        "title": product.get("title", ""),
        "amazon_price": price,
        "sales_rank": rank,
        "category": category,
        "root_category": root_category,
        "fba_seller_count": fba_seller_count,
        "new_offer_count": new_offer_count,
        "amazon_on_listing": amazon_on_listing,
        "weight_lbs": weight_lbs,
        "price_age_days": price_age_days,
        "price_stability": price_stability,
        "avg30_price": avg30_price,
        "avg90_price": avg90_price,
        "product_url": f"https://www.amazon.com/dp/{product.get('asin', '')}",
        "match_confidence": 0.92,
        "match_method": "keepa_batch_upc",
        "data_source": "keepa",
    }


def parse_manifest(path: str) -> list[dict]:
    """Parse wholesale manifest CSV."""
    products = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not any(str(v).strip() for v in row.values()):
                continue
            raw_price = row.get("PRICE", "")
            price_cleaned = re.sub(r"[^\d.]", "", str(raw_price).strip())
            try:
                cost = float(price_cleaned) if price_cleaned else None
            except ValueError:
                cost = None

            upc_raw = row.get("UPC", "").strip()
            upc_digits = re.sub(r"\D", "", upc_raw)
            upc = upc_digits if len(upc_digits) >= 8 else None

            products.append({
                "name": row.get("DESCRIPTION", "").strip(),
                "upc": upc,
                "wholesale_cost": cost,
                "pack_qty": 1,
            })
    return products


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--min-roi", type=float, default=30.0)
    parser.add_argument("--min-profit", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    products = parse_manifest(args.manifest)
    print(f"[batch] Parsed {len(products)} products from manifest", file=sys.stderr)

    # Filter to products with valid UPCs and costs
    valid = [p for p in products if p["upc"] and p["wholesale_cost"] and p["wholesale_cost"] > 0]
    print(f"[batch] {len(valid)} products with valid UPC + cost", file=sys.stderr)

    # Deduplicate UPCs (some manifests have duplicates)
    upc_to_products = {}
    for p in valid:
        upc = p["upc"]
        if upc not in upc_to_products:
            upc_to_products[upc] = p

    unique_upcs = list(upc_to_products.keys())
    print(f"[batch] {len(unique_upcs)} unique UPCs to look up", file=sys.stderr)

    # Check token balance
    tokens_left, refill_rate = check_tokens()
    print(f"[batch] Keepa tokens: {tokens_left} left, refill {refill_rate}/min", file=sys.stderr)

    # Batch lookup
    all_matches = {}
    batch_size = args.batch_size
    total_batches = (len(unique_upcs) + batch_size - 1) // batch_size
    total_tokens_used = 0

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(unique_upcs))
        batch_upcs = unique_upcs[start:end]

        # Check tokens before each batch
        if batch_idx > 0 and batch_idx % 5 == 0:
            tokens_left, _ = check_tokens()
            if tokens_left < 50:
                wait_time = max(60, (100 - tokens_left) / refill_rate * 60)
                print(f"[batch] Low tokens ({tokens_left}), waiting {int(wait_time)}s for refill...",
                      file=sys.stderr)
                time.sleep(wait_time)

        print(f"  [batch {batch_idx+1}/{total_batches}] UPCs {start+1}-{end} "
              f"({len(batch_upcs)} UPCs)", file=sys.stderr)

        try:
            upc_map, tokens_left, consumed = batch_upc_lookup(batch_upcs)
            total_tokens_used += consumed
            matches_count = sum(len(v) for v in upc_map.values())
            print(f"    → {len(upc_map)} UPCs matched, {matches_count} products, "
                  f"{consumed} tokens used ({tokens_left} left)", file=sys.stderr)
            all_matches.update(upc_map)
        except Exception as e:
            print(f"    → ERROR: {e}", file=sys.stderr)

        # Small delay between batches to be respectful
        if batch_idx < total_batches - 1:
            time.sleep(1)

    print(f"\n[batch] Lookup complete: {len(all_matches)} UPCs matched on Amazon, "
          f"{total_tokens_used} total tokens used", file=sys.stderr)

    # Process matches and calculate profitability
    results = []
    for upc, product_data in upc_to_products.items():
        keepa_products = all_matches.get(upc, [])
        best = pick_best_match(keepa_products, product_data["name"])

        if not best:
            # No match or no price data
            results.append({
                **product_data,
                "amazon": {"asin": None, "match_confidence": 0.0, "match_method": "none"},
                "profitability": {"verdict": "SKIP", "skip_reason": "No Amazon match"},
            })
            continue

        amazon_data = extract_keepa_data(best["product"], best["price"])

        # Build product dict for profitability calculation
        product_for_calc = {
            "name": product_data["name"],
            "upc": upc,
            "sale_price": product_data["wholesale_cost"],
            "retail_price": product_data["wholesale_cost"],
            "retailer": "wholesale",
            "amazon": amazon_data,
        }

        profitability = calculate_product_profitability(product_for_calc, shipping_to_fba=1.00)

        # Wholesale override: relax arbitrage-specific filters
        # "1 FBA seller" and "Amazon on listing" are risks, not deal-breakers for wholesale
        roi = profitability.get("roi_percent", 0) or 0
        profit = profitability.get("profit_per_unit", 0) or 0
        skip_reason = profitability.get("skip_reason", "") or ""

        if profitability["verdict"] == "SKIP" and roi > 15 and profit > 1.50:
            if "FBA seller" in skip_reason or "Amazon is a seller" in skip_reason:
                profitability["verdict"] = "MAYBE"
                profitability["risk_note"] = skip_reason
                profitability["skip_reason"] = None

        # Apply min_roi / min_profit thresholds
        if profitability["verdict"] == "BUY" and (roi < args.min_roi or profit < args.min_profit):
            profitability["verdict"] = "MAYBE"

        results.append({
            **product_data,
            "amazon": amazon_data,
            "profitability": profitability,
        })

    # Sort: BUY → MAYBE → SKIP, by ROI descending within tier
    tier_order = {"BUY": 0, "MAYBE": 1, "SKIP": 2}
    results.sort(key=lambda r: (
        tier_order.get(r.get("profitability", {}).get("verdict", "SKIP"), 2),
        -(r.get("profitability", {}).get("roi_percent") or 0),
    ))

    # Summary stats
    buys = [r for r in results if r.get("profitability", {}).get("verdict") == "BUY"]
    maybes = [r for r in results if r.get("profitability", {}).get("verdict") == "MAYBE"]
    skips = [r for r in results if r.get("profitability", {}).get("verdict") == "SKIP"]

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"RESULTS: {len(buys)} BUY | {len(maybes)} MAYBE | {len(skips)} SKIP", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    if buys:
        print(f"\n🏆 TOP BUY OPPORTUNITIES:", file=sys.stderr)
        for r in buys[:30]:
            p = r["profitability"]
            a = r["amazon"]
            print(f"  ${r['wholesale_cost']:.2f} → ${a.get('amazon_price', 0):.2f} | "
                  f"ROI: {p.get('roi_percent', 0):.0f}% | "
                  f"Profit: ${p.get('profit_per_unit', 0):.2f} | "
                  f"Score: {p.get('deal_score', 0):.0f} | "
                  f"{r['name'][:50]}", file=sys.stderr)

    # Output JSON
    output = {
        "summary": {
            "total_products": len(products),
            "analyzed": len(results),
            "buy_count": len(buys),
            "maybe_count": len(maybes),
            "skip_count": len(skips),
            "tokens_used": total_tokens_used,
        },
        "products": results,
    }

    if args.output:
        out_path = Path(args.output).resolve()
        # Restrict output to project directory or .tmp
        project_root = Path(__file__).parent.parent.resolve()
        if not str(out_path).startswith(str(project_root)):
            print(f"ERROR: Output path must be within project directory", file=sys.stderr)
            sys.exit(1)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\n[batch] Results saved to {out_path}", file=sys.stderr)
    else:
        print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
