#!/usr/bin/env python3
"""
Script: reverse_sourcing.py
Purpose: Reverse sourcing — start with an Amazon ASIN (or list of ASINs),
         find cheaper retail sources at Walmart, Target, Home Depot, CVS,
         Walgreens, and Costco. Calculate profitability for each source found.
Inputs:  --asin (single ASIN), --asin-file (one ASIN per line), --output (JSON)
Outputs: JSON with ranked retail sources per ASIN, best ROI first.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

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

from retailer_configs import get_retailer_config, RETAILER_CONFIGS
from retailer_registry import (
    get_retailers_for_product,
    get_search_url,
    get_retailer,
    get_all_retailers,
)
from match_amazon_products import (
    title_similarity,
    parse_amazon_price,
    get_amazon_product_details,
    search_keepa,
)
from calculate_fba_profitability import (
    calculate_product_profitability,
    get_referral_fee_rate,
    estimate_fba_fee,
    estimate_monthly_sales,
)


# ── Config ────────────────────────────────────────────────────────────────────

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Legacy hardcoded map replaced by retailer_registry.py
# Now uses get_retailers_for_product() for smart routing

SEARCH_DELAY = 3.0       # seconds between retailer searches
AMAZON_DELAY = 3.0       # seconds between Amazon page loads
MIN_TITLE_SIMILARITY = 0.40  # minimum similarity to consider a match
MAX_RESULTS_PER_RETAILER = 3  # max matching products to keep per retailer


# ── Amazon Product Fetching ──────────────────────────────────────────────────

def get_amazon_info(page, asin, use_keepa=False):
    """Fetch Amazon product info for an ASIN.

    Returns dict with: title, price, category, sales_rank, fba_seller_count, product_url
    Returns None if the product cannot be found.
    """
    # Try Keepa first if available
    if use_keepa:
        keepa_data = search_keepa(asin, is_upc=False)
        if keepa_data and keepa_data.get("title"):
            return {
                "asin": asin,
                "title": keepa_data.get("title", ""),
                "amazon_price": keepa_data.get("amazon_price") or keepa_data.get("fba_price"),
                "category": keepa_data.get("category"),
                "sales_rank": keepa_data.get("sales_rank"),
                "fba_seller_count": keepa_data.get("fba_seller_count"),
                "amazon_on_listing": keepa_data.get("amazon_on_listing"),
                "product_url": f"https://www.amazon.com/dp/{asin}",
                "data_source": "keepa",
            }

    # Fall back to Playwright scraping
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
            "category": details.get("category"),
            "sales_rank": details.get("sales_rank"),
            "fba_seller_count": details.get("fba_seller_count"),
            "amazon_on_listing": details.get("amazon_on_listing"),
            "product_url": url,
            "data_source": "playwright",
        }

    except Exception as e:
        print(f"    [amazon] Error fetching {asin}: {e}", file=sys.stderr)
        return None


# ── Retailer Search ──────────────────────────────────────────────────────────

def _parse_price_text(text):
    """Parse a price string like '$14.99' or '14.99' into a float."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    match = re.search(r"(\d+\.?\d*)", cleaned)
    if match:
        try:
            val = float(match.group(1))
            # Sanity check: prices should be between $0.01 and $9999
            if 0.01 <= val <= 9999:
                return val
        except ValueError:
            pass
    return None


def search_retailer(page, retailer_name, product_title):
    """Search a single retailer for a product. Returns list of found products.

    Each result: {retailer, title, retail_price, url, title_similarity}
    """
    retailer_info = get_retailer(retailer_name)
    if not retailer_info:
        return []

    domain_key = retailer_info["domain"]
    config = RETAILER_CONFIGS.get(domain_key)
    if not config:
        # Tier 2 retailer without custom CSS — use generic config
        config = RETAILER_CONFIGS.get("generic", {})
        if not config:
            return []

    # Build search query — use first ~60 chars of title to avoid overly specific searches
    query_words = product_title.split()[:8]
    query = " ".join(query_words)
    search_url = get_search_url(retailer_info, query)
    if not search_url:
        return []

    results = []

    try:
        try:
            page.goto(search_url, wait_until="networkidle", timeout=25000)
            page.wait_for_timeout(2000)
        except Exception:
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(config.get("request_delay", 3.0) * 1000)

        # Scroll to trigger lazy-loaded cards
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(500)

        soup = BeautifulSoup(page.content(), "html.parser")

        # Extract product cards using retailer-specific selectors
        cat_config = config.get("category_page", {})
        card_selector = cat_config.get("product_cards", "")
        title_selector = cat_config.get("card_title", "")
        price_selector = cat_config.get("card_price", "")
        link_selector = cat_config.get("card_link", "")

        cards = soup.select(card_selector) if card_selector else []

        for card in cards[:10]:  # check top 10 cards max
            # Extract title
            card_title = None
            if title_selector:
                title_el = card.select_one(title_selector)
                if title_el:
                    card_title = title_el.get_text(strip=True)

            if not card_title:
                continue

            # Calculate similarity
            similarity = title_similarity(product_title, card_title)
            if similarity < MIN_TITLE_SIMILARITY:
                continue

            # Extract price
            card_price = None
            if price_selector:
                price_el = card.select_one(price_selector)
                if price_el:
                    card_price = _parse_price_text(price_el.get_text(strip=True))

            if not card_price:
                continue

            # Extract link
            card_url = ""
            if link_selector:
                link_el = card.select_one(link_selector)
                if link_el:
                    href = link_el.get("href", "")
                    if href.startswith("/"):
                        # Build full URL from retailer domain
                        card_url = f"https://www.{domain_key}{href}"
                    elif href.startswith("http"):
                        card_url = href

            results.append({
                "retailer": retailer_name,
                "title": card_title,
                "retail_price": card_price,
                "url": card_url,
                "title_similarity": round(similarity, 3),
            })

        # Sort by similarity descending and keep top N
        results.sort(key=lambda r: r["title_similarity"], reverse=True)
        results = results[:MAX_RESULTS_PER_RETAILER]

    except Exception as e:
        print(f"    [{retailer_name}] Search error: {e}", file=sys.stderr)

    return results


# ── Profitability Calculation ─────────────────────────────────────────────────

def calculate_source_profitability(retail_price, amazon_price, category=None):
    """Calculate profitability for a single retail source.

    Returns dict with: buy_cost, sell_price, profit_per_unit, roi_percent, verdict
    """
    if not retail_price or not amazon_price or retail_price <= 0 or amazon_price <= 0:
        return {
            "buy_cost": retail_price,
            "sell_price": amazon_price,
            "profit_per_unit": None,
            "roi_percent": None,
            "verdict": "SKIP",
            "skip_reason": "Missing price data",
        }

    referral_fee_rate = get_referral_fee_rate(category)
    referral_fee = round(amazon_price * referral_fee_rate, 2)
    fba_fee = estimate_fba_fee(amazon_price)
    shipping_to_fba = 1.00
    total_fees = round(referral_fee + fba_fee + shipping_to_fba, 2)

    profit = round(amazon_price - retail_price - total_fees, 2)
    roi = round((profit / retail_price) * 100, 1) if retail_price > 0 else 0

    # Verdict
    if roi >= 30 and profit >= 3.50:
        verdict = "BUY"
    elif roi >= 20 and profit >= 2.00:
        verdict = "MAYBE"
    else:
        verdict = "SKIP"

    return {
        "buy_cost": round(retail_price, 2),
        "sell_price": round(amazon_price, 2),
        "referral_fee": referral_fee,
        "fba_fee": fba_fee,
        "shipping_to_fba": shipping_to_fba,
        "total_fees": total_fees,
        "profit_per_unit": profit,
        "roi_percent": roi,
        "verdict": verdict,
    }


# ── Core Reverse Sourcing ────────────────────────────────────────────────────

def reverse_source_asin(page, asin, use_keepa=False):
    """Given an ASIN, find cheaper retail sources.

    Steps:
    1. Get Amazon product info (title, price, category, BSR)
    2. Search each retailer for the product
    3. Calculate profitability for each source found
    4. Return ranked results (best ROI first)
    """
    print(f"\n[reverse] Processing ASIN: {asin}", file=sys.stderr)

    # Step 1: Get Amazon product info
    print(f"  [1/4] Fetching Amazon product info...", file=sys.stderr)
    amazon_info = get_amazon_info(page, asin, use_keepa=use_keepa)

    if not amazon_info:
        print(f"  ERROR: Could not fetch Amazon info for {asin}", file=sys.stderr)
        return {
            "asin": asin,
            "amazon_title": None,
            "amazon_price": None,
            "bsr": None,
            "category": None,
            "retail_sources": [],
            "best_source": None,
            "error": "Could not fetch Amazon product info",
            "searched_at": datetime.now().isoformat(),
        }

    amazon_title = amazon_info.get("title", "")
    amazon_price = amazon_info.get("amazon_price")
    category = amazon_info.get("category")
    bsr = amazon_info.get("sales_rank")

    print(f"  Title: {amazon_title[:80]}{'...' if len(amazon_title) > 80 else ''}", file=sys.stderr)
    print(f"  Price: ${amazon_price}" if amazon_price else "  Price: N/A", file=sys.stderr)
    print(f"  BSR: {bsr}" if bsr else "  BSR: N/A", file=sys.stderr)
    print(f"  Category: {category}" if category else "  Category: N/A", file=sys.stderr)

    if not amazon_price:
        print(f"  WARNING: No Amazon price found — profitability cannot be calculated", file=sys.stderr)

    # Step 2: Search retailers — smart-routed via registry
    # Use product title + category to pick the best retailers
    search_retailers = get_retailers_for_product(
        category or amazon_title, max_retailers=15
    )
    retailer_names = [r["name"] for r in search_retailers]
    print(f"  [2/4] Searching {len(retailer_names)} retailers (smart-routed)...", file=sys.stderr)
    all_sources = []

    for retailer_name in retailer_names:
        print(f"    Searching {retailer_name}...", file=sys.stderr)
        matches = search_retailer(page, retailer_name, amazon_title)

        if matches:
            print(f"    Found {len(matches)} potential match(es)", file=sys.stderr)
            for m in matches:
                print(f"      - {m['title'][:50]}... @ ${m['retail_price']:.2f} "
                      f"(similarity: {m['title_similarity']:.0%})", file=sys.stderr)
        else:
            print(f"    No matches found", file=sys.stderr)

        all_sources.extend(matches)
        time.sleep(SEARCH_DELAY)

    # Step 3: Calculate profitability for each source
    print(f"  [3/4] Calculating profitability for {len(all_sources)} source(s)...", file=sys.stderr)
    for source in all_sources:
        source["profitability"] = calculate_source_profitability(
            source["retail_price"], amazon_price, category
        )

    # Step 4: Rank by ROI (best first), filtering out sources more expensive than Amazon
    actionable_sources = [
        s for s in all_sources
        if amazon_price and s["retail_price"] < amazon_price
    ]
    actionable_sources.sort(
        key=lambda s: s["profitability"].get("roi_percent", -999),
        reverse=True,
    )

    # Also include sources priced at or above Amazon (sorted separately, appended at end)
    non_actionable = [
        s for s in all_sources
        if not amazon_price or s["retail_price"] >= amazon_price
    ]
    for s in non_actionable:
        s["profitability"]["verdict"] = "SKIP"
        s["profitability"]["skip_reason"] = "Retail price >= Amazon price"

    ranked_sources = actionable_sources + non_actionable

    # Determine best source
    best_source = None
    if actionable_sources:
        best = actionable_sources[0]
        if best["profitability"].get("verdict") in ("BUY", "MAYBE"):
            best_source = best

    # Monthly sales estimate
    monthly_sales = estimate_monthly_sales(bsr, category)

    print(f"  [4/4] Done. {len(actionable_sources)} actionable source(s) found.", file=sys.stderr)
    if best_source:
        bp = best_source["profitability"]
        print(f"  BEST: {best_source['retailer']} @ ${best_source['retail_price']:.2f} "
              f"-> {bp['verdict']} (ROI: {bp['roi_percent']}%, profit: ${bp['profit_per_unit']})",
              file=sys.stderr)

    return {
        "asin": asin,
        "amazon_title": amazon_title,
        "amazon_price": amazon_price,
        "bsr": bsr,
        "category": category,
        "fba_seller_count": amazon_info.get("fba_seller_count"),
        "amazon_on_listing": amazon_info.get("amazon_on_listing"),
        "estimated_monthly_sales": monthly_sales,
        "retail_sources": ranked_sources,
        "best_source": best_source,
        "searched_at": datetime.now().isoformat(),
    }


# ── Batch Processing ─────────────────────────────────────────────────────────

def reverse_source_batch(asins, output_path=None, use_keepa=False):
    """Process a list of ASINs. Returns list of results."""
    print(f"\n[reverse] Starting reverse sourcing for {len(asins)} ASIN(s)", file=sys.stderr)
    print(f"[reverse] Retailers: smart-routed via registry (up to 15 per ASIN)", file=sys.stderr)
    print(f"[reverse] Keepa: {'enabled' if use_keepa else 'disabled (using Playwright)'}", file=sys.stderr)

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        for i, asin in enumerate(asins):
            asin = asin.strip().upper()
            if not asin or len(asin) != 10:
                print(f"\n[reverse] Skipping invalid ASIN: '{asin}'", file=sys.stderr)
                continue

            print(f"\n{'=' * 60}", file=sys.stderr)
            print(f"[reverse] [{i + 1}/{len(asins)}] ASIN: {asin}", file=sys.stderr)
            print(f"{'=' * 60}", file=sys.stderr)

            result = reverse_source_asin(page, asin, use_keepa=use_keepa)
            results.append(result)

            # Brief delay between ASINs
            if i < len(asins) - 1:
                time.sleep(AMAZON_DELAY)

        browser.close()

    # Summary
    total_sources = sum(len(r.get("retail_sources", [])) for r in results)
    buy_count = sum(
        1 for r in results
        if r.get("best_source", {}) and r["best_source"].get("profitability", {}).get("verdict") == "BUY"
    )
    maybe_count = sum(
        1 for r in results
        if r.get("best_source", {}) and r["best_source"].get("profitability", {}).get("verdict") == "MAYBE"
    )

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"[reverse] COMPLETE", file=sys.stderr)
    print(f"{'=' * 60}", file=sys.stderr)
    print(f"  ASINs processed: {len(results)}", file=sys.stderr)
    print(f"  Total retail sources found: {total_sources}", file=sys.stderr)
    print(f"  BUY recommendations: {buy_count}", file=sys.stderr)
    print(f"  MAYBE recommendations: {maybe_count}", file=sys.stderr)

    # Build output
    output_data = {
        "mode": "reverse_sourcing",
        "asins_processed": len(results),
        "results": results,
        "summary": {
            "total_retail_sources": total_sources,
            "buy_count": buy_count,
            "maybe_count": maybe_count,
        },
        "searched_at": datetime.now().isoformat(),
    }

    # Write output
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"[reverse] Results saved to {output_path}", file=sys.stderr)
    else:
        # Print to stdout
        print(json.dumps(output_data, indent=2))

    return output_data


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Reverse sourcing: find cheaper retail sources for Amazon ASINs"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--asin", help="Single ASIN to reverse source")
    group.add_argument("--asin-file", help="File with one ASIN per line")
    parser.add_argument("--output", help="Output JSON path (default: stdout)")
    parser.add_argument(
        "--use-keepa", action="store_true",
        help="Use Keepa API for Amazon data (requires KEEPA_API_KEY in .env)"
    )
    args = parser.parse_args()

    # Build ASIN list
    if args.asin:
        asins = [args.asin]
    else:
        asin_file = Path(args.asin_file)
        if not asin_file.exists():
            print(f"ERROR: ASIN file not found: {asin_file}", file=sys.stderr)
            sys.exit(1)
        asins = [
            line.strip() for line in asin_file.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not asins:
            print("ERROR: No ASINs found in file", file=sys.stderr)
            sys.exit(1)

    # Auto-detect Keepa
    use_keepa = args.use_keepa or bool(KEEPA_API_KEY)
    if use_keepa and not KEEPA_API_KEY:
        print("[reverse] Warning: --use-keepa set but KEEPA_API_KEY not found in .env",
              file=sys.stderr)
        use_keepa = False

    reverse_source_batch(asins, output_path=args.output, use_keepa=use_keepa)


if __name__ == "__main__":
    main()
