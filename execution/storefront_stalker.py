#!/usr/bin/env python3
"""
Script: storefront_stalker.py
Purpose: Scrape an Amazon seller's storefront to extract their product catalog,
         then analyze each product for profitability. Pro FBA sellers "stalk"
         successful competitors to find pre-vetted product ideas.
Inputs:  --seller (seller ID or URL), --url (storefront URL), --max-products,
         --output (JSON path), --reverse-source (find cheaper retail sources)
Outputs: JSON with product catalog, deal scores, and summary analysis
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent))

try:
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    print("Install with: pip install playwright beautifulsoup4", file=sys.stderr)
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from calculate_fba_profitability import (
    estimate_monthly_sales,
    score_competition,
    check_restrictions,
    get_referral_fee_rate,
    estimate_fba_fee,
)
from match_amazon_products import (
    parse_amazon_price,
    extract_sales_rank,
    extract_category,
    get_amazon_product_details,
)

# ── Config ────────────────────────────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PAGE_DELAY_MIN = 3.0       # seconds between storefront pages
PAGE_DELAY_MAX = 4.0       # upper bound for randomized delay
DETAIL_DELAY = 3.0         # seconds between product detail page visits
MAX_PAGES = 10             # max storefront pages to scrape
STOREFRONT_URL_TEMPLATE = "https://www.amazon.com/s?me={seller_id}"


# ── Seller ID Extraction ─────────────────────────────────────────────────────

def extract_seller_id(url_or_id):
    """Parse seller ID from a URL or accept a raw seller ID string.

    Supported URL formats:
      - https://www.amazon.com/sp?seller=A1B2C3D4E5F6G7
      - https://www.amazon.com/s?me=A1B2C3D4E5F6G7
      - https://www.amazon.com/shops/A1B2C3D4E5F6G7
      - Raw seller ID: A1B2C3D4E5F6G7

    Returns the seller ID string, or None if unparseable.
    """
    if not url_or_id:
        return None

    url_or_id = url_or_id.strip()

    # If it looks like a raw seller ID (alphanumeric, 10-14 chars)
    if re.match(r"^[A-Z0-9]{10,14}$", url_or_id):
        return url_or_id

    # Try parsing as URL
    try:
        parsed = urlparse(url_or_id)
        params = parse_qs(parsed.query)

        # ?seller=... (from /sp page)
        if "seller" in params:
            return params["seller"][0].strip()

        # ?me=... (from /s search page)
        if "me" in params:
            return params["me"][0].strip()

        # /shops/SELLER_ID path format
        path_match = re.search(r"/shops/([A-Z0-9]{10,14})", parsed.path)
        if path_match:
            return path_match.group(1)

    except Exception:
        pass

    # Last resort: find anything that looks like a seller ID in the string
    match = re.search(r"([A-Z0-9]{13,14})", url_or_id)
    if match:
        return match.group(1)

    return None


# ── Storefront Scraping ──────────────────────────────────────────────────────

def _random_delay():
    """Return a randomized delay between PAGE_DELAY_MIN and PAGE_DELAY_MAX."""
    import random
    return random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX)


def _extract_rating(item):
    """Extract star rating from a search result card."""
    rating_el = item.select_one("span.a-icon-alt, i.a-icon-star-small span.a-icon-alt")
    if rating_el:
        text = rating_el.get_text()
        m = re.search(r"([\d.]+)\s*out of", text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


def _extract_review_count(item):
    """Extract review count from a search result card."""
    review_el = item.select_one(
        "span.a-size-base.s-underline-text, "
        "span[aria-label*='ratings'], "
        "a[href*='customerReviews'] span"
    )
    if review_el:
        text = review_el.get("aria-label", "") or review_el.get_text()
        # Remove commas and extract number
        cleaned = text.replace(",", "")
        m = re.search(r"([\d]+)", cleaned)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return None


def scrape_storefront(page, seller_id, max_products=100):
    """Navigate to a seller's product listing and extract all products with pagination.

    Args:
        page: Playwright page object
        seller_id: Amazon seller ID
        max_products: Maximum number of products to extract

    Returns:
        tuple: (seller_name, products_list)
    """
    products = []
    seller_name = None
    page_num = 0

    while len(products) < max_products and page_num < MAX_PAGES:
        page_num += 1
        url = STOREFRONT_URL_TEMPLATE.format(seller_id=seller_id)
        if page_num > 1:
            url += f"&page={page_num}"

        print(f"  [storefront] Page {page_num} — {url}", file=sys.stderr)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            delay_ms = int(_random_delay() * 1000)
            page.wait_for_timeout(delay_ms)
        except Exception as e:
            print(f"  [storefront] Page load error: {e}", file=sys.stderr)
            break

        # Scroll to trigger lazy loading
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 1200)")
            page.wait_for_timeout(500)

        soup = BeautifulSoup(page.content(), "html.parser")

        # Check for CAPTCHA
        if soup.select_one("form[action*='captcha']") or "robot" in soup.get_text().lower()[:500]:
            print("  [storefront] CAPTCHA detected — stopping", file=sys.stderr)
            break

        # Try to extract seller name from page (first page only)
        if not seller_name:
            # Look for seller name in search results header or breadcrumbs
            name_el = soup.select_one(
                "span.a-size-extra-large, "
                "span.a-color-state.a-text-bold, "
                "h1.a-size-large, "
                "span[data-component-type='s-brand-filter'] span"
            )
            if name_el:
                seller_name = name_el.get_text(strip=True)
                # Clean up common prefixes
                seller_name = re.sub(r"^(Results from|Sold by)\s+", "", seller_name, flags=re.IGNORECASE)

        # Find product cards
        results = soup.select('div[data-asin][data-component-type="s-search-result"]')
        if not results:
            # Fallback: any div with a non-empty data-asin
            results = [el for el in soup.select("div[data-asin]")
                       if el.get("data-asin") and len(el.get("data-asin", "")) == 10]

        if not results:
            print(f"  [storefront] No products found on page {page_num}", file=sys.stderr)
            break

        page_product_count = 0
        for item in results:
            if len(products) >= max_products:
                break

            asin = item.get("data-asin", "").strip()
            if not asin or len(asin) != 10:
                continue

            # Skip duplicate ASINs
            if any(p["asin"] == asin for p in products):
                continue

            # Title
            title_el = item.select_one("h2 a span, h2 span.a-text-normal, h2 span")
            title = title_el.get_text(strip=True) if title_el else None
            if not title:
                continue

            # Price
            price_el = item.select_one("span.a-price span.a-offscreen")
            price = parse_amazon_price(price_el.get_text(strip=True) if price_el else None)

            # Rating
            rating = _extract_rating(item)

            # Review count
            review_count = _extract_review_count(item)

            # Product URL from title link
            link_el = item.select_one("h2 a")
            product_url = None
            if link_el and link_el.get("href"):
                href = link_el["href"]
                if href.startswith("/"):
                    product_url = f"https://www.amazon.com{href}"
                elif href.startswith("http"):
                    product_url = href
            if not product_url:
                product_url = f"https://www.amazon.com/dp/{asin}"

            products.append({
                "asin": asin,
                "title": title,
                "price": price,
                "rating": rating,
                "review_count": review_count,
                "product_url": product_url,
            })
            page_product_count += 1

        print(f"  [storefront] Extracted {page_product_count} products from page {page_num} "
              f"(total: {len(products)})", file=sys.stderr)

        # Check for next page
        next_btn = soup.select_one("a.s-pagination-next:not(.s-pagination-disabled)")
        if not next_btn:
            print("  [storefront] No more pages", file=sys.stderr)
            break

        # Delay before next page
        time.sleep(_random_delay())

    return seller_name, products


# ── Product Detail Enrichment ────────────────────────────────────────────────

def enrich_product_details(page, products, max_enrich=None):
    """Visit individual product pages to get BSR, category, and seller count.

    Args:
        page: Playwright page object
        products: List of product dicts to enrich
        max_enrich: Maximum products to enrich (None = all)

    Returns:
        The same products list, enriched in-place.
    """
    to_enrich = products if max_enrich is None else products[:max_enrich]
    total = len(to_enrich)

    print(f"\n  [enrich] Fetching details for {total} products...", file=sys.stderr)

    for i, product in enumerate(to_enrich):
        asin = product["asin"]
        print(f"  [enrich] [{i + 1}/{total}] {asin} — {product['title'][:50]}...", file=sys.stderr)

        details = get_amazon_product_details(page, asin)

        product["sales_rank"] = details.get("sales_rank")
        product["category"] = details.get("category")
        product["fba_seller_count"] = details.get("fba_seller_count")
        product["amazon_on_listing"] = details.get("amazon_on_listing")
        product["offer_count"] = details.get("offer_count")

        if product["sales_rank"]:
            print(f"           BSR: #{product['sales_rank']} in {product.get('category', 'N/A')}",
                  file=sys.stderr)

        time.sleep(DETAIL_DELAY)

    return products


# ── Deal Score Calculation ───────────────────────────────────────────────────

def calculate_deal_score(product):
    """Calculate a composite deal score (0-100) for a product based on:
    - Sales rank / demand signal (40% weight)
    - Competition level (25% weight)
    - Price sweet spot (20% weight)
    - Review quality (15% weight)

    Higher score = better opportunity. Returns the score and a breakdown dict.
    """
    score = 0.0
    breakdown = {}

    # ── Sales Rank Score (0-40) ──────────────────────────────────────────
    bsr = product.get("sales_rank")
    if bsr:
        if bsr <= 500:
            rank_score = 40
        elif bsr <= 2000:
            rank_score = 35
        elif bsr <= 5000:
            rank_score = 30
        elif bsr <= 10000:
            rank_score = 25
        elif bsr <= 25000:
            rank_score = 20
        elif bsr <= 50000:
            rank_score = 15
        elif bsr <= 100000:
            rank_score = 10
        elif bsr <= 250000:
            rank_score = 5
        else:
            rank_score = 2
    else:
        rank_score = 0  # no data = can't score

    breakdown["demand"] = rank_score
    score += rank_score

    # ── Competition Score (0-25) ─────────────────────────────────────────
    seller_count = product.get("fba_seller_count")
    amazon_on = product.get("amazon_on_listing", False)

    if amazon_on:
        comp_score = 5  # Amazon on listing = tough competition
    elif seller_count is not None:
        if seller_count <= 2:
            comp_score = 25
        elif seller_count <= 5:
            comp_score = 20
        elif seller_count <= 10:
            comp_score = 15
        elif seller_count <= 20:
            comp_score = 10
        else:
            comp_score = 5
    else:
        comp_score = 12  # unknown = assume moderate

    breakdown["competition"] = comp_score
    score += comp_score

    # ── Price Sweet Spot Score (0-20) ────────────────────────────────────
    # FBA arbitrage/wholesale sweet spot: $15-$50
    price = product.get("price")
    if price:
        if 15 <= price <= 50:
            price_score = 20
        elif 10 <= price < 15 or 50 < price <= 75:
            price_score = 15
        elif 8 <= price < 10 or 75 < price <= 100:
            price_score = 10
        elif price < 8:
            price_score = 5  # too cheap, fees eat profit
        else:
            price_score = 8  # expensive, higher risk
    else:
        price_score = 0

    breakdown["price"] = price_score
    score += price_score

    # ── Review Quality Score (0-15) ──────────────────────────────────────
    rating = product.get("rating")
    reviews = product.get("review_count")

    review_score = 0
    if rating and rating >= 4.0:
        review_score += 8
    elif rating and rating >= 3.5:
        review_score += 5
    elif rating:
        review_score += 2

    if reviews and reviews >= 100:
        review_score += 7
    elif reviews and reviews >= 30:
        review_score += 5
    elif reviews and reviews >= 10:
        review_score += 3

    # Cap at 15
    review_score = min(review_score, 15)
    breakdown["reviews"] = review_score
    score += review_score

    return round(score, 1), breakdown


# ── Storefront Analysis ──────────────────────────────────────────────────────

def analyze_storefront(products):
    """Analyze the full product list: calculate deal scores, monthly sales estimates,
    and identify top opportunities.

    Returns:
        List of products with analysis data added in-place.
    """
    print(f"\n  [analyze] Scoring {len(products)} products...", file=sys.stderr)

    for product in products:
        # Deal score
        deal_score, score_breakdown = calculate_deal_score(product)
        product["deal_score"] = deal_score
        product["score_breakdown"] = score_breakdown

        # Monthly sales estimate
        monthly_sales = estimate_monthly_sales(
            product.get("sales_rank"),
            product.get("category")
        )
        product["estimated_monthly_sales"] = monthly_sales

        # Estimated monthly revenue
        if monthly_sales and product.get("price"):
            product["estimated_monthly_revenue"] = round(monthly_sales * product["price"], 2)
        else:
            product["estimated_monthly_revenue"] = None

        # Competition assessment
        amazon_data = {
            "fba_seller_count": product.get("fba_seller_count"),
            "amazon_on_listing": product.get("amazon_on_listing", False),
        }
        comp_score, comp_warnings = score_competition(amazon_data)
        product["competition_score"] = comp_score
        product["competition_warnings"] = comp_warnings

        # Restriction checks
        restrictions = check_restrictions(
            product.get("title", ""),
            product.get("category"),
            brand=None,
        )
        product["restrictions"] = restrictions

        # Estimated profitability (rough — no buy cost known, so estimate margin)
        price = product.get("price")
        category = product.get("category")
        if price:
            referral_fee = round(price * get_referral_fee_rate(category), 2)
            fba_fee = estimate_fba_fee(price)
            total_fees = round(referral_fee + fba_fee + 1.00, 2)  # +$1 shipping to FBA
            product["estimated_fees"] = total_fees
            product["estimated_net_after_fees"] = round(price - total_fees, 2)
        else:
            product["estimated_fees"] = None
            product["estimated_net_after_fees"] = None

    # Sort by deal score descending
    products.sort(key=lambda p: p.get("deal_score", 0), reverse=True)

    return products


# ── Stalker Report ───────────────────────────────────────────────────────────

def stalker_report(seller_id, seller_name, products, output_path=None):
    """Format a summary report and output JSON.

    Args:
        seller_id: Amazon seller ID
        seller_name: Extracted seller name (may be None)
        products: Analyzed product list
        output_path: Path to write JSON (None = stdout)

    Returns:
        The full output dict.
    """
    # Build summary stats
    prices = [p["price"] for p in products if p.get("price")]
    categories = {}
    for p in products:
        cat = p.get("category")
        if cat:
            categories[cat] = categories.get(cat, 0) + 1

    top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)
    top_category_names = [c[0] for c in top_categories[:5]]

    products_under_50 = sum(1 for p in products if p.get("price") and p["price"] < 50)

    total_monthly_rev = sum(
        p.get("estimated_monthly_revenue", 0) or 0 for p in products
    )

    # Top opportunities (deal_score >= 50 or top 10, whichever is more)
    top_opportunities = [p for p in products if p.get("deal_score", 0) >= 50]
    if len(top_opportunities) < 10:
        top_opportunities = products[:10]

    summary = {
        "total_products": len(products),
        "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        "price_range": f"${min(prices):.2f} - ${max(prices):.2f}" if prices else None,
        "top_categories": top_category_names,
        "products_under_50": products_under_50,
        "estimated_monthly_revenue": round(total_monthly_rev, 2),
        "avg_deal_score": round(
            sum(p.get("deal_score", 0) for p in products) / len(products), 1
        ) if products else 0,
        "products_with_bsr": sum(1 for p in products if p.get("sales_rank")),
        "high_opportunity_count": sum(1 for p in products if p.get("deal_score", 0) >= 60),
    }

    output_data = {
        "seller_id": seller_id,
        "seller_name": seller_name,
        "products_found": len(products),
        "products": products,
        "top_opportunities": [
            {
                "asin": p["asin"],
                "title": p["title"],
                "price": p.get("price"),
                "deal_score": p.get("deal_score"),
                "sales_rank": p.get("sales_rank"),
                "category": p.get("category"),
                "estimated_monthly_sales": p.get("estimated_monthly_sales"),
                "competition_score": p.get("competition_score"),
            }
            for p in top_opportunities
        ],
        "summary": summary,
        "stalked_at": datetime.now().isoformat(),
    }

    # Print summary table to stderr
    print(f"\n{'=' * 70}", file=sys.stderr)
    print(f"  STOREFRONT STALKER REPORT", file=sys.stderr)
    print(f"{'=' * 70}", file=sys.stderr)
    print(f"  Seller ID:    {seller_id}", file=sys.stderr)
    print(f"  Seller Name:  {seller_name or 'Unknown'}", file=sys.stderr)
    print(f"  Products:     {summary['total_products']}", file=sys.stderr)
    print(f"  Avg Price:    ${summary['avg_price']}" if summary["avg_price"] else
          f"  Avg Price:    N/A", file=sys.stderr)
    print(f"  Price Range:  {summary['price_range']}" if summary["price_range"] else
          f"  Price Range:  N/A", file=sys.stderr)
    print(f"  Under $50:    {summary['products_under_50']}", file=sys.stderr)
    print(f"  Categories:   {', '.join(top_category_names) if top_category_names else 'N/A'}",
          file=sys.stderr)
    print(f"  Avg Deal Score: {summary['avg_deal_score']}/100", file=sys.stderr)
    print(f"  High Opps (60+): {summary['high_opportunity_count']}", file=sys.stderr)
    print(f"  Est. Monthly Rev: ${summary['estimated_monthly_revenue']:,.2f}", file=sys.stderr)
    print(f"{'=' * 70}", file=sys.stderr)

    if top_opportunities:
        print(f"\n  TOP OPPORTUNITIES:", file=sys.stderr)
        print(f"  {'ASIN':<12} {'Score':>5} {'Price':>8} {'BSR':>10} {'Category':<25} Title",
              file=sys.stderr)
        print(f"  {'-' * 90}", file=sys.stderr)
        for p in top_opportunities[:15]:
            bsr_str = f"#{p.get('sales_rank', 'N/A')}" if p.get("sales_rank") else "N/A"
            price_str = f"${p.get('price', 0):.2f}" if p.get("price") else "N/A"
            cat = (p.get("category") or "N/A")[:24]
            title = p["title"][:40]
            print(f"  {p['asin']:<12} {p.get('deal_score', 0):>5.0f} {price_str:>8} "
                  f"{bsr_str:>10} {cat:<25} {title}", file=sys.stderr)
        print(f"{'=' * 70}", file=sys.stderr)

    # Write output
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\n[stalker] Results saved to {output_path}", file=sys.stderr)
    else:
        print(json.dumps(output_data, indent=2))

    return output_data


# ── Reverse Sourcing Integration ─────────────────────────────────────────────

def reverse_source_top_products(products, output_path=None, max_products=10):
    """Run reverse sourcing on the top-scoring products.

    Imports and delegates to reverse_sourcing.py. Only processes products
    with deal_score >= 50 (or top N).
    """
    try:
        from reverse_sourcing import reverse_source_batch
    except ImportError:
        print("[stalker] WARNING: reverse_sourcing.py not available — skipping", file=sys.stderr)
        return None

    # Select top products by deal score
    candidates = [p for p in products if p.get("deal_score", 0) >= 50]
    if len(candidates) < max_products:
        candidates = products[:max_products]

    asins = [p["asin"] for p in candidates[:max_products]]

    if not asins:
        print("[stalker] No products to reverse source", file=sys.stderr)
        return None

    print(f"\n[stalker] Reverse sourcing {len(asins)} top products...", file=sys.stderr)

    rs_output = None
    if output_path:
        rs_output = str(Path(output_path).with_suffix("")) + "_reverse_sourced.json"

    return reverse_source_batch(asins, output_path=rs_output)


# ── Schema B Normalization (Unified Sourcing) ──────────────────────────────


def normalize_to_schema_b(stalker_product: dict, seller_id: str = "") -> dict:
    """Convert a stalker product dict to Schema B (unified sourcing format).

    This allows storefront stalker results to be stored in the same scan_results
    table as all other sourcing modes (brand, category, catalog, etc.).
    """
    asin = stalker_product.get("asin", "")
    price = stalker_product.get("price", 0)
    deal_score = stalker_product.get("deal_score", 0)

    # Map deal_score to standard verdict
    if deal_score >= 70:
        verdict = "BUY"
    elif deal_score >= 50:
        verdict = "MAYBE"
    elif deal_score >= 30:
        verdict = "RESEARCH"
    else:
        verdict = "SKIP"

    return {
        "asin": asin,
        "amazon_title": stalker_product.get("title", ""),
        "amazon_url": f"https://www.amazon.com/dp/{asin}",
        "amazon_price": price,
        "buy_cost": None,  # Storefront stalking = no retail source
        "source_url": f"https://www.amazon.com/dp/{asin}",
        "source_retailer": f"Amazon Storefront ({seller_id})",
        "estimated_profit": None,
        "estimated_roi": None,
        "verdict": verdict,
        "match_method": "storefront_stalk",
        "match_confidence": 1.0,
        "profitability": {
            "profit_per_unit": None,
            "roi_percent": None,
            "verdict": verdict,
        },
        "bsr": stalker_product.get("sales_rank"),
        "brand": stalker_product.get("brand", ""),
        "category": stalker_product.get("category", ""),
        "fba_seller_count": stalker_product.get("fba_seller_count"),
        "amazon_on_listing": stalker_product.get("amazon_on_listing"),
        "deal_score": deal_score,
        "estimated_monthly_sales": stalker_product.get("estimated_monthly_sales"),
        "rating": stalker_product.get("rating"),
        "review_count": stalker_product.get("review_count"),
        "seller_id": seller_id,
        "mode": "storefront",
    }


def normalize_stalker_results(output_data: dict) -> list[dict]:
    """Normalize all products from a stalker run to Schema B.

    Args:
        output_data: Full output dict from run_stalker().

    Returns:
        List of Schema B dicts ready for scan_results insertion.
    """
    if not output_data:
        return []

    seller_id = output_data.get("seller_id", "")
    products = output_data.get("products", [])
    return [normalize_to_schema_b(p, seller_id) for p in products]


# ── Main Flow ────────────────────────────────────────────────────────────────

def run_stalker(seller_id, max_products=100, output_path=None,
                fetch_details=True, reverse_source=False):
    """Full storefront stalker pipeline.

    1. Launch Playwright headless browser
    2. Navigate to seller's product listing
    3. Extract products from search results (ASIN, title, price, rating, reviews)
    4. For each product, optionally get detail data (BSR, category, seller count)
    5. Calculate deal_score for each product
    6. Optionally reverse-source top products
    7. Output JSON + summary table
    """
    print(f"\n[stalker] Storefront Stalker — Seller: {seller_id}", file=sys.stderr)
    print(f"[stalker] Max products: {max_products} | Details: {fetch_details} | "
          f"Reverse source: {reverse_source}", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        # Step 1: Scrape storefront
        print(f"\n[stalker] Step 1/3: Scraping storefront...", file=sys.stderr)
        seller_name, products = scrape_storefront(page, seller_id, max_products)

        if not products:
            print("[stalker] ERROR: No products found. Check seller ID or try again later.",
                  file=sys.stderr)
            browser.close()
            return None

        print(f"[stalker] Found {len(products)} products from {seller_name or 'Unknown Seller'}",
              file=sys.stderr)

        # Step 2: Enrich with product details (BSR, category, sellers)
        if fetch_details:
            print(f"\n[stalker] Step 2/3: Fetching product details...", file=sys.stderr)
            enrich_product_details(page, products)
        else:
            print(f"\n[stalker] Step 2/3: Skipping detail enrichment (--no-details)", file=sys.stderr)

        browser.close()

    # Step 3: Analyze and score
    print(f"\n[stalker] Step 3/3: Analyzing products...", file=sys.stderr)
    products = analyze_storefront(products)

    # Generate report
    output_data = stalker_report(seller_id, seller_name, products, output_path)

    # Optional: reverse source top products
    if reverse_source:
        reverse_source_top_products(products, output_path)

    return output_data


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape an Amazon seller's storefront and analyze products for FBA opportunities"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seller", help="Amazon seller ID (e.g., A1B2C3D4E5F6G7) or storefront URL")
    group.add_argument("--url", help="Full Amazon storefront URL")

    parser.add_argument("--max-products", type=int, default=100,
                        help="Max products to extract (default: 100)")
    parser.add_argument("--output", default=None,
                        help="Output JSON path (default: stdout)")
    parser.add_argument("--no-details", action="store_true",
                        help="Skip fetching product detail pages (faster, no BSR/category)")
    parser.add_argument("--reverse-source", action="store_true",
                        help="Reverse source top products at retail stores")
    args = parser.parse_args()

    # Resolve seller ID
    raw_input = args.seller or args.url
    seller_id = extract_seller_id(raw_input)

    if not seller_id:
        print(f"ERROR: Could not extract seller ID from: {raw_input}", file=sys.stderr)
        print("Provide a seller ID (e.g., A1B2C3D4E5F6G7) or a valid Amazon storefront URL.",
              file=sys.stderr)
        sys.exit(1)

    print(f"[stalker] Resolved seller ID: {seller_id}", file=sys.stderr)

    # Determine output path
    output_path = args.output
    if not output_path and sys.stdout.isatty():
        # Interactive terminal — default to .tmp file
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(__file__).parent.parent / ".tmp" / "stalker"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"{ts}-{seller_id}.json")
        print(f"[stalker] Output: {output_path}", file=sys.stderr)

    run_stalker(
        seller_id=seller_id,
        max_products=args.max_products,
        output_path=output_path,
        fetch_details=not args.no_details,
        reverse_source=args.reverse_source,
    )


if __name__ == "__main__":
    main()
