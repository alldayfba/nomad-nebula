#!/usr/bin/env python3
"""
Script: match_amazon_products.py
Purpose: Match retail products to Amazon ASINs by searching Amazon via Playwright
         (Tier 0, free) or Keepa API (Tier 1, if KEEPA_API_KEY is set).
Inputs:  --input (JSON from scrape_retail_products.py), --output (JSON path)
Outputs: JSON with Amazon match data appended to each product
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
AMAZON_SEARCH_DELAY = 3.0  # seconds between Amazon searches

# v3.0: Import centralized KeepaClient
try:
    from keepa_client import KeepaClient as _KeepaClient
    HAS_KEEPA_CLIENT = True
except ImportError:
    HAS_KEEPA_CLIENT = False

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Pricing for cost tracking
_PRICING = {
    "claude-haiku-4-5-20251001": (0.25, 1.25),
}


def title_similarity(retail_title, amazon_title):
    """Simple word-overlap similarity score between two product titles."""
    if not retail_title or not amazon_title:
        return 0.0
    # Normalize: lowercase, extract alphanumeric words
    words_a = set(re.findall(r"[a-z0-9]+", retail_title.lower()))
    words_b = set(re.findall(r"[a-z0-9]+", amazon_title.lower()))
    # Remove common filler words
    filler = {"the", "a", "an", "and", "or", "of", "for", "with", "in", "on", "by", "to", "is"}
    words_a -= filler
    words_b -= filler
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


def classify_match_with_haiku(retail_title, amazon_title):
    """Use Claude Haiku to classify ambiguous product matches (confidence 0.4-0.7)."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": (
                    f"Are these the same product? Answer only YES or NO.\n"
                    f"Product A: {retail_title}\n"
                    f"Product B: {amazon_title}"
                ),
            }],
        )
        answer = resp.content[0].text.strip().upper()
        in_tokens = resp.usage.input_tokens
        out_tokens = resp.usage.output_tokens
        cost = (in_tokens * 0.25 + out_tokens * 1.25) / 1_000_000
        print(f"    [haiku] {answer} (~${cost:.4f})", file=sys.stderr)
        return answer == "YES"
    except Exception as e:
        print(f"    [haiku error] {e}", file=sys.stderr)
        return None


def parse_amazon_price(text):
    """Parse Amazon price text like '$12.99' or '$12\n99'."""
    if not text:
        return None
    # Handle Amazon's split price format (whole + fraction)
    cleaned = re.sub(r"\s+", ".", text.replace("$", "").replace(",", ""))
    match = re.search(r"(\d+\.?\d*)", cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def extract_sales_rank(soup):
    """Try to extract BSR/sales rank from an Amazon product page."""
    # Look in product details table
    for el in soup.select("#productDetails_detailBullets_sections1 tr, #detailBullets_feature_div li"):
        text = el.get_text()
        if "Best Sellers Rank" in text or "Amazon Best Sellers Rank" in text:
            match = re.search(r"#([\d,]+)", text)
            if match:
                return int(match.group(1).replace(",", ""))
    # Look in bullet list
    for el in soup.select("li"):
        text = el.get_text()
        if "Best Sellers Rank" in text:
            match = re.search(r"#([\d,]+)", text)
            if match:
                return int(match.group(1).replace(",", ""))
    return None


def extract_category(soup):
    """Try to extract category from Amazon product page breadcrumbs."""
    breadcrumbs = soup.select("ul.a-unordered-list.a-horizontal a, #wayfinding-breadcrumbs_feature_div a")
    if breadcrumbs:
        return breadcrumbs[-1].get_text(strip=True)
    return None


def search_amazon_playwright(page, query, is_upc=False):
    """Search Amazon for a product by title or UPC and return top match."""
    encoded = quote_plus(query)
    search_url = f"https://www.amazon.com/s?k={encoded}"

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"    [amazon search error] {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(page.content(), "html.parser")

    # Check for CAPTCHA
    if soup.select_one("form[action*='captcha']") or "robot" in soup.get_text().lower()[:500]:
        print("    [amazon] CAPTCHA detected — skipping", file=sys.stderr)
        return None

    # Find search result items
    results = soup.select('div[data-asin][data-component-type="s-search-result"]')
    if not results:
        # Fallback: any div with data-asin
        results = [el for el in soup.select("div[data-asin]") if el.get("data-asin")]

    print(f"    [debug] {len(results)} result divs for query={query[:30]}", file=sys.stderr)

    matches = []
    for item in results[:5]:
        asin = item.get("data-asin", "").strip()
        if not asin or len(asin) != 10:
            continue

        # Title (Amazon HTML evolves — try multiple selectors)
        title_el = item.select_one(
            "h2 a span, h2 span.a-text-normal, "
            "[data-cy='title-recipe'] h2, h2 span"
        )
        title = title_el.get_text(strip=True) if title_el else None
        print(f"    [debug] ASIN={asin} title={'YES' if title else 'NO'}", file=sys.stderr)

        # Price
        price_el = item.select_one("span.a-price span.a-offscreen, span.a-price-whole")
        price = parse_amazon_price(price_el.get_text(strip=True) if price_el else None)

        # Rating
        rating_el = item.select_one('span[aria-label*="out of"], i.a-icon-star-small')
        rating = None
        if rating_el:
            rating_text = rating_el.get("aria-label", "") or rating_el.get_text()
            m = re.search(r"([\d.]+)\s*out of", rating_text)
            if m:
                rating = float(m.group(1))

        # Review count
        review_el = item.select_one('span[aria-label*="ratings"], span.a-size-base.s-underline-text')
        review_count = None
        if review_el:
            review_text = review_el.get("aria-label", "") or review_el.get_text()
            m = re.search(r"([\d,]+)", review_text.replace(",", ""))
            if m:
                review_count = int(m.group(1))

        # Sponsored flag
        sponsored = bool(item.select_one('span:contains("Sponsored"), span.puis-label-popover'))

        # FBA seller count — look for "X+ offers" or "X offers" text on search cards
        fba_seller_count = None
        offers_el = item.select_one('a[href*="offer-listing"], span.a-color-secondary')
        if offers_el:
            offers_text = offers_el.get_text()
            m = re.search(r"(\d+)\+?\s*offer", offers_text, re.IGNORECASE)
            if m:
                fba_seller_count = int(m.group(1))

        if title:
            matches.append({
                "asin": asin,
                "title": title,
                "amazon_price": price,
                "rating": rating,
                "review_count": review_count,
                "sponsored": sponsored,
                "fba_seller_count": fba_seller_count,
                "product_url": f"https://www.amazon.com/dp/{asin}",
            })

    return matches


def get_amazon_product_details(page, asin):
    """Visit an Amazon product page to get sales rank, category, and seller data."""
    url = f"https://www.amazon.com/dp/{asin}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2500)
        soup = BeautifulSoup(page.content(), "html.parser")

        sales_rank = extract_sales_rank(soup)
        category = extract_category(soup)

        # FBA seller count — look for "New (X) from $Y" or offers link
        fba_seller_count = None
        offers_section = soup.select_one("#olp-upd-new, #olp_feature_div, #newBuyBoxPrice")
        if offers_section:
            offers_text = offers_section.get_text()
            m = re.search(r"New\s*\((\d+)\)", offers_text)
            if m:
                fba_seller_count = int(m.group(1))
        # Fallback: check "X+ offers" links elsewhere on page
        if fba_seller_count is None:
            for link in soup.select('a[href*="offer-listing"]'):
                m = re.search(r"(\d+)\+?\s*(?:new\s+)?offer", link.get_text(), re.IGNORECASE)
                if m:
                    fba_seller_count = int(m.group(1))
                    break

        # Amazon on listing — check if Amazon.com is a seller
        amazon_on_listing = False
        merchant_el = soup.select_one("#merchant-info, #tabular-buybox-container, #buyBoxInner")
        if merchant_el:
            merchant_text = merchant_el.get_text()
            if re.search(r"(?:ships?\s+from\s+and\s+)?sold\s+by\s+Amazon\.com", merchant_text, re.IGNORECASE):
                amazon_on_listing = True
            elif re.search(r"Amazon\.com", merchant_text):
                amazon_on_listing = True

        # Offer count — extract from "Other Sellers on Amazon" section
        offer_count = None
        other_sellers = soup.select_one("#olp-upd-new-used, #aod-filter-string, #olp_feature_div")
        if other_sellers:
            ot = other_sellers.get_text()
            m = re.search(r"(\d+)\s*(?:new|used|offer)", ot, re.IGNORECASE)
            if m:
                offer_count = int(m.group(1))
        # Fallback: look for the "Other Sellers on Amazon" heading area
        if offer_count is None:
            for el in soup.select("#mbc, #more-buying-choices-content, .mbc-offer-row"):
                rows = el.select(".mbc-offer-row, .a-row")
                if rows:
                    offer_count = len(rows)
                    break

        return {
            "sales_rank": sales_rank,
            "category": category,
            "fba_seller_count": fba_seller_count,
            "amazon_on_listing": amazon_on_listing,
            "offer_count": offer_count,
        }
    except Exception as e:
        print(f"    [product detail error] {e}", file=sys.stderr)
        return {
            "sales_rank": None,
            "category": None,
            "fba_seller_count": None,
            "amazon_on_listing": None,
            "offer_count": None,
        }


def search_keepa(query, is_upc=False):
    """Search Keepa API for a product via centralized KeepaClient.

    Uses KeepaClient.search_product() for proper rate limiting, token tracking,
    and correct CSV parsing (indices 34/35 for FBA/FBM seller counts).
    """
    if not KEEPA_API_KEY:
        return None
    try:
        from keepa_client import KeepaClient
        client = KeepaClient(tier="pro")
        product = client.search_product(query)

        if not product:
            return None

        asin = product.get("asin", "")

        return {
            "asin": asin,
            "title": product.get("title", ""),
            "amazon_price": product.get("buy_box_price") or product.get("amazon_price"),
            "fba_price": product.get("fba_price"),
            "sales_rank": product.get("bsr") or product.get("sales_rank"),
            "category": product.get("category"),
            "fba_seller_count": product.get("fba_seller_count"),
            "fbm_seller_count": product.get("fbm_seller_count"),
            "new_offer_count": product.get("new_offer_count"),
            "amazon_on_listing": product.get("amazon_on_listing"),
            "rating": product.get("rating"),
            "review_count": product.get("review_count"),
            "product_url": f"https://www.amazon.com/dp/{asin}",
            "data_source": "keepa",
        }
    except Exception as e:
        print(f"    [keepa error] {e}", file=sys.stderr)
        return None


def get_keepa_product_details(asin):
    """Fetch detailed product data from Keepa API for a specific ASIN.

    v3.0: Uses centralized KeepaClient when available for correct CSV parsing
    (indices 34/35 for FBA/FBM seller counts, private label detection).
    Falls back to inline parsing if KeepaClient not importable.

    Returns dict with sales_rank, category, fba_seller_count, fbm_seller_count,
    amazon_on_listing, new_offer_count, fba_price, amazon_price — or None on failure.
    """
    if not KEEPA_API_KEY:
        return None

    # v3.0: Use KeepaClient if available
    if HAS_KEEPA_CLIENT:
        try:
            client = _KeepaClient(api_key=KEEPA_API_KEY)
            product = client.get_product(asin)
            if not product:
                return None
            return {
                "sales_rank": product.get("bsr"),
                "category": product.get("category"),
                "amazon_price": product.get("sell_price"),
                "fba_price": product.get("fba_price"),
                "fba_seller_count": product.get("fba_seller_count"),
                "fbm_seller_count": product.get("fbm_seller_count"),
                "new_offer_count": product.get("total_offer_count"),
                "amazon_on_listing": product.get("amazon_on_listing"),
                "private_label": product.get("private_label", {}),
                "price_trends": product.get("price_trends", {}),
                "review_count": product.get("review_count"),
            }
        except Exception as e:
            print(f"    [keepa client error] {e}", file=sys.stderr)

    # Fallback: inline parsing
    try:
        import requests
        params = {
            "key": KEEPA_API_KEY,
            "domain": "1",
            "asin": asin,
        }
        resp = requests.get("https://api.keepa.com/product", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("products"):
            return None

        product = data["products"][0]
        csv_data = product.get("csv", [])

        def _last_valid(csv_list, index):
            if not csv_list or index >= len(csv_list) or not csv_list[index]:
                return None
            arr = csv_list[index]
            for i in range(len(arr) - 1, 0, -2):
                if arr[i] >= 0:
                    return arr[i]
            return None

        sales_rank = product.get("salesRankCurrent", None)
        if sales_rank is not None and sales_rank < 0:
            sales_rank = None

        category_tree = product.get("categoryTree", [{}])
        category = category_tree[-1].get("name", "") if category_tree else None

        amazon_price = None
        buy_box_raw = _last_valid(csv_data, 18)
        if buy_box_raw is not None:
            amazon_price = buy_box_raw / 100.0
        else:
            amazon_raw = _last_valid(csv_data, 0)
            if amazon_raw is not None:
                amazon_price = amazon_raw / 100.0

        fba_price = None
        fba_raw = _last_valid(csv_data, 10)
        if fba_raw is not None:
            fba_price = fba_raw / 100.0

        fba_seller_count = _last_valid(csv_data, 34)
        fbm_seller_count = _last_valid(csv_data, 35)
        new_offer_count = _last_valid(csv_data, 11)

        amazon_on_listing = None
        amazon_price_raw = _last_valid(csv_data, 0)
        if amazon_price_raw is not None:
            amazon_on_listing = True
        elif csv_data and len(csv_data) > 0 and csv_data[0]:
            amazon_on_listing = False

        return {
            "sales_rank": sales_rank,
            "category": category,
            "amazon_price": amazon_price,
            "fba_price": fba_price,
            "fba_seller_count": fba_seller_count,
            "fbm_seller_count": fbm_seller_count,
            "new_offer_count": new_offer_count,
            "amazon_on_listing": amazon_on_listing,
        }
    except Exception as e:
        print(f"    [keepa product detail error] {e}", file=sys.stderr)
        return None


def match_single_product(page, product, use_keepa=False, fetch_details=True):
    """Match a single retail product to Amazon. Returns amazon data dict."""
    name = product.get("name", "")
    upc = product.get("upc")

    if not name and not upc:
        return {"asin": None, "match_confidence": 0.0, "match_method": "none"}

    best_match = None
    best_confidence = 0.0
    match_method = "title"

    # Strategy 1: Search by UPC (highest confidence)
    if upc:
        match_method = "upc"
        if use_keepa:
            keepa_result = search_keepa(upc, is_upc=True)
            if keepa_result:
                best_match = keepa_result
                best_confidence = 0.95
        if not best_match:
            results = search_amazon_playwright(page, upc, is_upc=True)
            if results:
                best_match = results[0]
                best_confidence = 0.90
            time.sleep(AMAZON_SEARCH_DELAY)

    # Strategy 2: Search by title
    if not best_match or best_confidence < 0.7:
        if use_keepa and not best_match:
            keepa_result = search_keepa(name)
            if keepa_result:
                sim = title_similarity(name, keepa_result.get("title", ""))
                if sim > best_confidence:
                    best_match = keepa_result
                    best_confidence = sim
                    match_method = "keepa_title"

        if not best_match or best_confidence < 0.7:
            results = search_amazon_playwright(page, name)
            if results:
                # Score each result by title similarity
                for result in results:
                    sim = title_similarity(name, result.get("title", ""))
                    # Boost non-sponsored results slightly
                    if not result.get("sponsored"):
                        sim += 0.05
                    if sim > best_confidence:
                        best_match = result
                        best_confidence = sim
                        match_method = "title"
            time.sleep(AMAZON_SEARCH_DELAY)

    if not best_match:
        return {"asin": None, "match_confidence": 0.0, "match_method": "none"}

    # For ambiguous matches, try Haiku classification
    if 0.4 <= best_confidence <= 0.7 and name and best_match.get("title"):
        haiku_result = classify_match_with_haiku(name, best_match["title"])
        if haiku_result is True:
            best_confidence = max(best_confidence, 0.75)
        elif haiku_result is False:
            best_confidence = min(best_confidence, 0.3)

    # Optionally fetch product details (sales rank, category, seller data)
    # Prefer Keepa when available (faster, no CAPTCHA risk), fall back to Playwright
    if fetch_details and best_match.get("asin") and best_confidence >= 0.70:
        if use_keepa:
            keepa_details = get_keepa_product_details(best_match["asin"])
            if keepa_details:
                # Merge keepa details without overwriting existing non-None values
                for key, val in keepa_details.items():
                    if val is not None and not best_match.get(key):
                        best_match[key] = val
        elif not best_match.get("sales_rank"):
            # Fall back to Playwright for product details
            details = get_amazon_product_details(page, best_match["asin"])
            best_match.update(details)
            time.sleep(AMAZON_SEARCH_DELAY)

    best_match["match_confidence"] = round(best_confidence, 3)
    best_match["match_method"] = match_method
    best_match.pop("sponsored", None)

    return best_match


def match_products(input_path, output_path, max_matches=50, fetch_details=True):
    """Main matching loop. Processes all products from input JSON."""
    with open(input_path) as f:
        data = json.load(f)

    products = data.get("products", [])
    use_keepa = bool(KEEPA_API_KEY)

    if use_keepa:
        print("[match] Using Keepa API for Amazon matching", file=sys.stderr)
    else:
        print("[match] Using Playwright Amazon search (Tier 0, free)", file=sys.stderr)

    print(f"[match] Matching {min(len(products), max_matches)} products...", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        matched_count = 0
        for i, product in enumerate(products[:max_matches]):
            print(f"  [{i + 1}/{min(len(products), max_matches)}] {product.get('name', 'unknown')[:60]}",
                  file=sys.stderr)

            amazon_data = match_single_product(page, product, use_keepa, fetch_details)
            product["amazon"] = amazon_data

            if amazon_data.get("asin"):
                matched_count += 1
                conf = amazon_data.get("match_confidence", 0)
                print(f"    → ASIN: {amazon_data['asin']} | confidence: {conf:.2f} | "
                      f"${amazon_data.get('amazon_price', 'N/A')}", file=sys.stderr)
            else:
                print(f"    → No match found", file=sys.stderr)

        browser.close()

    # Filter: only return matches with confidence >= 0.70 (UPC matches at 0.90+ are unaffected)
    for product in products[:max_matches]:
        if product.get("amazon", {}).get("asin") and \
                product["amazon"].get("match_confidence", 0) < 0.70:
            product["amazon"] = {"asin": None, "match_confidence": 0.0, "match_method": "below_threshold"}
            matched_count -= 1

    # For products beyond max_matches, add empty amazon data
    for product in products[max_matches:]:
        product["amazon"] = {"asin": None, "match_confidence": 0.0, "match_method": "skipped"}

    # Write output
    output_data = {
        "retailer": data.get("retailer", "unknown"),
        "url": data.get("url", ""),
        "products": products,
        "count": len(products),
        "matched_count": matched_count,
        "match_rate": round(matched_count / max(len(products[:max_matches]), 1) * 100, 1),
        "data_source": "keepa" if use_keepa else "playwright",
        "matched_at": datetime.now().isoformat(),
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"[match] Done. {matched_count}/{min(len(products), max_matches)} products matched → {output_path}",
          file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Match retail products to Amazon ASINs")
    parser.add_argument("--input", required=True, help="Input JSON from scrape_retail_products.py")
    parser.add_argument("--output", required=True, help="Output JSON with Amazon matches")
    parser.add_argument("--max-matches", type=int, default=50, help="Max products to match (default: 50)")
    parser.add_argument("--no-details", action="store_true",
                        help="Skip fetching product detail pages (faster, no BSR)")
    args = parser.parse_args()

    match_products(args.input, args.output, args.max_matches, fetch_details=not args.no_details)


if __name__ == "__main__":
    main()
