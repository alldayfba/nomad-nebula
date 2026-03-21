#!/usr/bin/env python3
"""
Script: find_cheapest_source.py
Purpose: Given an Amazon ASIN, search all enabled retailers to find the cheapest
         effective buy price (raw price after cashback + gift card + coupons).
Inputs:  --asin (required)
Outputs: JSON ranked list of retailer matches to stdout

Steps:
  1. Keepa lookup: ASIN → title + brand + current Amazon price
  2. Search each enabled retailer (parallel HTTP + JSON-LD extraction)
  3. Apply discount stack: raw × (1-cashback) × (1-gc) × (1-coupon) - flat_coupon
  4. Rank by effective cost

Usage:
  python execution/find_cheapest_source.py --asin B08N5WRWNW
  python execution/find_cheapest_source.py --asin B08N5WRWNW --max-retailers 50
  python execution/find_cheapest_source.py --asin B08N5WRWNW --timeout 8 --top 5
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

sys.path.insert(0, str(PROJECT_ROOT))

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}


# ── Keepa Lookup ─────────────────────────────────────────────────────────────

def keepa_lookup(asin):
    """Look up ASIN via Keepa. Returns dict with title, brand, amazon_price or None."""
    try:
        from execution.keepa_client import KeepaClient
        client = KeepaClient(tier="pro")
        product = client.get_product(asin, stats=30)
        if not product:
            print(f"[finder] Keepa returned no data for ASIN {asin}", file=sys.stderr)
            return None
        return product
    except Exception as e:
        print(f"[finder] Keepa lookup failed: {e}", file=sys.stderr)
        return None


# ── Retailer Registry ─────────────────────────────────────────────────────────

def load_retailers():
    """Load enabled retailers from retailer_registry.py. Returns list of retailer dicts."""
    try:
        from execution.retailer_registry import RETAILERS
        return [r for r in RETAILERS if r.get("enabled", True) and r.get("search_url")]
    except Exception as e:
        print(f"[finder] Could not load retailer_registry: {e}", file=sys.stderr)
        return []


# ── Discount Stack ────────────────────────────────────────────────────────────

def _get_live_gc_discount(retailer_name):
    """Look up current gift card discount from CardBear SQLite DB."""
    try:
        from execution.scrape_cardbear import get_gift_card_discount
        return get_gift_card_discount(retailer_name) / 100.0
    except Exception:
        return 0.0


def _get_coupon_discount(retailer_name):
    """Look up best coupon discount from RETAILER_COUPON_CODES."""
    try:
        from execution.calculate_fba_profitability import RETAILER_COUPON_CODES
        codes = RETAILER_COUPON_CODES.get(retailer_name, [])
        best_pct = 0.0
        best_flat = 0.0
        best_code = None
        for c in codes:
            if c.get("discount_type") == "percent" and c.get("value", 0) > best_pct:
                best_pct = c["value"]
                best_code = c.get("code")
            elif c.get("discount_type") == "flat" and c.get("value", 0) > best_flat:
                best_flat = c["value"]
        return best_pct / 100.0, best_flat, best_code
    except Exception:
        return 0.0, 0.0, None


def calculate_effective_price(raw_price, retailer):
    """Apply full discount stack to raw price. Returns (effective_price, breakdown_dict)."""
    name = retailer.get("name", "")

    cashback_pct = retailer.get("cashback_percent", 0) / 100.0
    gc_static = retailer.get("gift_card_discount", 0) / 100.0
    gc_live = _get_live_gc_discount(name)
    gc_pct = max(gc_static, gc_live)  # use best available

    coupon_pct, coupon_flat, coupon_code = _get_coupon_discount(name)

    price = raw_price
    price *= (1 - cashback_pct)
    price *= (1 - gc_pct)
    price *= (1 - coupon_pct)
    price -= coupon_flat
    effective = max(round(price, 2), 0.0)

    total_savings_pct = round((1 - effective / raw_price) * 100, 1) if raw_price > 0 else 0.0

    breakdown = {
        "raw_price": round(raw_price, 2),
        "cashback_pct": round(cashback_pct * 100, 1),
        "gift_card_pct": round(gc_pct * 100, 1),
        "gift_card_source": "live" if gc_live >= gc_static and gc_live > 0 else "static",
        "coupon_pct": round(coupon_pct * 100, 1),
        "coupon_flat": coupon_flat,
        "coupon_code": coupon_code,
        "total_savings_pct": total_savings_pct,
    }

    return effective, breakdown


# ── Price Extraction ──────────────────────────────────────────────────────────

def _extract_price_from_html(html, domain):
    """Extract lowest visible price from a retail search results page.

    Tries (in order):
      1. JSON-LD Product schema
      2. og:price:amount meta tag
      3. Regex for common price patterns
    """
    # 1. JSON-LD
    ld_matches = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                            html, re.DOTALL | re.IGNORECASE)
    for block in ld_matches:
        try:
            data = json.loads(block.strip())
            items = data if isinstance(data, list) else [data]
            for item in items:
                # Handle ItemList or single Product
                if item.get("@type") == "ItemList":
                    for element in item.get("itemListElement", []):
                        item2 = element.get("item", element)
                        price = _price_from_offer(item2)
                        if price:
                            return price
                price = _price_from_offer(item)
                if price:
                    return price
        except (json.JSONDecodeError, AttributeError):
            continue

    # 2. og:price:amount
    og_match = re.search(r'<meta[^>]+property="og:price:amount"[^>]+content="([0-9.,]+)"',
                         html, re.IGNORECASE)
    if og_match:
        try:
            return float(og_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # 3. Regex fallback — find lowest "$XX.XX" price on page
    prices = re.findall(r'\$\s*([\d,]+\.\d{2})', html)
    if prices:
        vals = []
        for p in prices:
            try:
                vals.append(float(p.replace(",", "")))
            except ValueError:
                pass
        if vals:
            # Filter out obviously wrong values (>$500 or <$0.50)
            vals = [v for v in vals if 0.50 <= v <= 500]
            if vals:
                return min(vals)

    return None


def _price_from_offer(item):
    """Extract price from a JSON-LD item that may have offers."""
    offers = item.get("offers") or item.get("Offers")
    if not offers:
        return None
    if isinstance(offers, list):
        offers = offers[0]
    if isinstance(offers, dict):
        for key in ("price", "lowPrice", "Price"):
            val = offers.get(key)
            if val is not None:
                try:
                    return float(str(val).replace(",", ""))
                except (ValueError, TypeError):
                    pass
    return None


# ── Retailer Search ───────────────────────────────────────────────────────────

def search_retailer(retailer, query, timeout=10):
    """Search a single retailer for a product by query string.

    Returns dict with retailer info + raw_price, or None if not found.
    """
    search_url_template = retailer.get("search_url", "")
    if not search_url_template:
        return None

    url = search_url_template.replace("{query}", quote_plus(query))
    name = retailer.get("name", retailer.get("key", "unknown"))

    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return None

        raw_price = _extract_price_from_html(resp.text, retailer.get("domain", ""))
        if raw_price is None or raw_price <= 0:
            return None

        return {
            "retailer": name,
            "domain": retailer.get("domain", ""),
            "raw_price": raw_price,
            "search_url": url,
            "cashback_percent": retailer.get("cashback_percent", 0),
            "gift_card_discount": retailer.get("gift_card_discount", 0),
        }

    except Exception:
        return None


# ── Main Finder ───────────────────────────────────────────────────────────────

def find_cheapest_source(asin, max_retailers=100, timeout=10, top=10):
    """Search all enabled retailers for the given ASIN and rank by effective buy price.

    Args:
        asin: Amazon ASIN to search for.
        max_retailers: Max number of retailers to search (default: 100).
        timeout: Per-retailer HTTP timeout in seconds (default: 10).
        top: Number of top results to return (default: 10).

    Returns:
        Dict with asin, title, amazon_price, and ranked list of retailer matches.
    """
    print(f"[finder] Looking up ASIN {asin} via Keepa...", file=sys.stderr)
    product = keepa_lookup(asin)

    if product:
        title = product.get("title", "")
        brand = product.get("brand", "")
        amazon_price = product.get("current_price") or product.get("amazon_price") or 0
        print(f"[finder] Found: {title[:60]}", file=sys.stderr)
        print(f"[finder] Brand: {brand} | Amazon price: ${amazon_price:.2f}", file=sys.stderr)
    else:
        print(f"[finder] No Keepa data — enter product title manually.", file=sys.stderr)
        print(f"[finder] Usage: --title \"Product Name\" to override", file=sys.stderr)
        return {"error": "Keepa lookup failed", "asin": asin}

    # Build search query (brand + title keywords)
    query_parts = []
    if brand:
        query_parts.append(brand)
    # Take first 4-5 significant words from title
    title_words = [w for w in re.split(r'\s+', title) if len(w) > 2][:5]
    query_parts.extend(title_words)
    query = " ".join(query_parts)
    print(f"[finder] Search query: \"{query}\"", file=sys.stderr)

    retailers = load_retailers()
    if not retailers:
        return {"error": "No retailers loaded", "asin": asin}

    # Limit retailer list
    retailers = retailers[:max_retailers]
    print(f"[finder] Searching {len(retailers)} retailers (parallel, timeout={timeout}s)...",
          file=sys.stderr)

    start = time.time()
    raw_results = []

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(search_retailer, r, query, timeout): r
            for r in retailers
        }
        done = 0
        for future in as_completed(futures):
            done += 1
            result = future.result()
            if result:
                raw_results.append(result)
            if done % 20 == 0:
                print(f"[finder] {done}/{len(retailers)} searched, {len(raw_results)} matches so far...",
                      file=sys.stderr)

    elapsed = time.time() - start
    print(f"[finder] Search complete in {elapsed:.1f}s — {len(raw_results)} price matches found.",
          file=sys.stderr)

    if not raw_results:
        print(f"[finder] No prices found. The product may not be carried by searched retailers,",
              file=sys.stderr)
        print(f"  or the search URL templates need updating for these retailers.", file=sys.stderr)
        return {
            "asin": asin,
            "title": title,
            "brand": brand,
            "amazon_price": amazon_price,
            "query_used": query,
            "retailers_searched": len(retailers),
            "matches": [],
        }

    # Apply discount stack and rank
    ranked = []
    for match in raw_results:
        retailer_obj = next(
            (r for r in retailers if r.get("name") == match["retailer"]),
            match
        )
        effective, breakdown = calculate_effective_price(match["raw_price"], retailer_obj)

        margin = round(amazon_price * 0.85 - effective, 2) if amazon_price else None
        roi = round(margin / effective * 100, 1) if margin and effective > 0 else None

        ranked.append({
            "retailer": match["retailer"],
            "domain": match["domain"],
            "raw_price": match["raw_price"],
            "effective_price": effective,
            "estimated_margin": margin,
            "estimated_roi_pct": roi,
            "discount_breakdown": breakdown,
            "search_url": match["search_url"],
        })

    ranked.sort(key=lambda x: x["effective_price"])
    top_results = ranked[:top]

    # Print summary table
    print(f"\n{'─' * 70}", file=sys.stderr)
    print(f"  TOP {min(top, len(top_results))} CHEAPEST SOURCES FOR {asin}", file=sys.stderr)
    print(f"  Amazon sell price: ${amazon_price:.2f}", file=sys.stderr)
    print(f"{'─' * 70}", file=sys.stderr)
    for i, r in enumerate(top_results, 1):
        savings = r["discount_breakdown"]["total_savings_pct"]
        margin_str = f"  ~${r['estimated_margin']:.2f} margin" if r["estimated_margin"] else ""
        print(f"  {i}. {r['retailer']}: ${r['raw_price']:.2f} raw → "
              f"${r['effective_price']:.2f} effective ({savings:.0f}% off){margin_str}",
              file=sys.stderr)
    print(f"{'─' * 70}", file=sys.stderr)

    return {
        "asin": asin,
        "title": title,
        "brand": brand,
        "amazon_price": amazon_price,
        "query_used": query,
        "retailers_searched": len(retailers),
        "matches_found": len(ranked),
        "top_results": top_results,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Find cheapest retailer source for an Amazon ASIN"
    )
    parser.add_argument("--asin", required=True, help="Amazon ASIN to search for")
    parser.add_argument("--max-retailers", type=int, default=100,
                        help="Max retailers to search (default: 100)")
    parser.add_argument("--timeout", type=float, default=10,
                        help="Per-retailer HTTP timeout in seconds (default: 10)")
    parser.add_argument("--top", type=int, default=10,
                        help="Number of top results to return (default: 10)")
    args = parser.parse_args()

    result = find_cheapest_source(
        asin=args.asin.strip().upper(),
        max_retailers=args.max_retailers,
        timeout=args.timeout,
        top=args.top,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
