#!/usr/bin/env python3
"""
Script: scrape_retail_products.py
Purpose: Scrape product data from any retail website URL (Walmart, Target, Home Depot, etc.)
Inputs:  --url (required), --max-products (default 50), --enrich/--no-enrich, --output (JSON path)
Outputs: JSON file with scraped product data
"""

import argparse
import json
import re
import sys
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retailer_configs import get_retailer_config, detect_page_type

try:
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    sys.exit(1)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}};
"""


def wait_for_products(page, card_selector, timeout=15000):
    """Wait for product cards to appear on the page. Tries each selector variant."""
    if not card_selector:
        page.wait_for_timeout(5000)
        return
    for sel in card_selector.split(", "):
        sel = sel.strip()
        if not sel:
            continue
        try:
            page.wait_for_selector(sel, timeout=timeout)
            return
        except Exception:
            continue
    # Fallback: just wait
    page.wait_for_timeout(5000)


def parse_price(text):
    """Extract numeric price from text like '$12.99' or '12.99'."""
    if not text:
        return None
    match = re.search(r"\$?([\d,]+\.?\d*)", text.replace(",", ""))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def extract_element(soup, selector_string):
    """Try each selector in a comma-separated string, return first match's text/attr."""
    if not selector_string:
        return None
    for sel in selector_string.split(", "):
        sel = sel.strip()
        if not sel:
            continue
        el = soup.select_one(sel)
        if el:
            if el.name == "meta":
                return el.get("content")
            if el.name == "img":
                return el.get("src") or el.get("data-src")
            return el.get_text(strip=True)
    return None


def scrape_product_page(page, url, selectors):
    """Scrape a single product page and return product data dict."""
    try:
        page.goto(url, wait_until="networkidle", timeout=25000)
        page.wait_for_timeout(2000)
    except Exception:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  [page load error] {url}: {e}", file=sys.stderr)
            return None

    soup = BeautifulSoup(page.content(), "html.parser")

    title = extract_element(soup, selectors.get("title"))
    price_text = extract_element(soup, selectors.get("price"))
    sale_text = extract_element(soup, selectors.get("sale_price"))
    upc = extract_element(soup, selectors.get("upc"))
    image = extract_element(soup, selectors.get("image"))

    retail_price = parse_price(price_text)
    sale_price = parse_price(sale_text)

    # Normalize: retail_price = higher (original), sale_price = lower (discounted)
    if retail_price and sale_price and sale_price > retail_price:
        retail_price, sale_price = sale_price, retail_price

    # Also try to extract UPC from structured data (JSON-LD)
    if not upc:
        for script_tag in soup.select('script[type="application/ld+json"]'):
            try:
                ld = json.loads(script_tag.string or "")
                if isinstance(ld, list):
                    ld = ld[0]
                for key in ["gtin13", "gtin12", "gtin", "sku", "mpn"]:
                    if ld.get(key):
                        upc = str(ld[key])
                        break
                # Check nested product
                if not upc and ld.get("@type") == "Product":
                    offers = ld.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    for key in ["gtin13", "gtin12", "gtin", "sku"]:
                        if ld.get(key):
                            upc = str(ld[key])
                            break
            except (json.JSONDecodeError, TypeError, IndexError):
                continue

    # Also try to get price from JSON-LD if not found via selectors
    if not retail_price:
        for script_tag in soup.select('script[type="application/ld+json"]'):
            try:
                ld = json.loads(script_tag.string or "")
                if isinstance(ld, list):
                    ld = ld[0]
                if ld.get("@type") == "Product":
                    offers = ld.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    p = offers.get("price")
                    if p:
                        retail_price = float(p)
                        break
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    if not title and not retail_price:
        return None

    return {
        "name": title,
        "retail_url": url,
        "source_url": url,  # Normalized alias
        "retail_price": retail_price,
        "sale_price": sale_price,
        "upc": upc,
        "image_url": image,
        "scraped_at": datetime.now().isoformat(),
    }


def scrape_category_page(page, url, config, max_products):
    """Scrape a category/search/clearance page and return list of product dicts."""
    products = []
    cat_selectors = config.get("category_page", {})
    pagination = config.get("pagination", {})
    delay = config.get("request_delay", 2.0)
    max_pages = min(pagination.get("max_pages", 3), 10)

    current_url = url
    for page_num in range(max_pages):
        if len(products) >= max_products:
            break

        print(f"  [category] Page {page_num + 1} — {current_url}", file=sys.stderr)

        try:
            page.goto(current_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  [page load error] {e}", file=sys.stderr)
            break

        # Bail on CAPTCHA / bot detection pages
        page_text = page.evaluate("document.title + ' ' + (document.body?.innerText?.slice(0, 500) || '')")
        if any(kw in page_text.lower() for kw in ["robot", "captcha", "verify you", "access denied", "blocked"]):
            print(f"  [category] Bot detection triggered — skipping", file=sys.stderr)
            break

        # Wait for product cards to render (JS-heavy sites)
        wait_for_products(page, cat_selectors.get("product_cards"))

        # Scroll to trigger lazy loading
        for _ in range(4):
            page.evaluate("window.scrollBy(0, 1200)")
            page.wait_for_timeout(800)

        soup = BeautifulSoup(page.content(), "html.parser")

        # Find product cards
        cards_selector = cat_selectors.get("product_cards", "")
        cards = []
        for sel in cards_selector.split(", "):
            sel = sel.strip()
            if sel:
                cards = soup.select(sel)
                if cards:
                    break

        if not cards:
            print(f"  [category] No product cards found on page {page_num + 1}", file=sys.stderr)
            break

        print(f"  [category] Found {len(cards)} product cards", file=sys.stderr)

        for card in cards:
            if len(products) >= max_products:
                break

            # Extract link
            link_sel = cat_selectors.get("card_link", "a")
            link_el = None
            for sel in link_sel.split(", "):
                sel = sel.strip()
                if sel:
                    link_el = card.select_one(sel) if card.name != "a" else card
                    if link_el:
                        break
            if not link_el and card.name == "a":
                link_el = card

            href = link_el.get("href") if link_el else None
            if href:
                href = urljoin(current_url, href)

            # Extract title from card
            title = None
            title_sel = cat_selectors.get("card_title", "")
            for sel in title_sel.split(", "):
                sel = sel.strip()
                if sel:
                    title_el = card.select_one(sel)
                    if title_el:
                        title = title_el.get_text(strip=True)
                        break

            # Extract price from card
            price = None
            price_sel = cat_selectors.get("card_price", "")
            for sel in price_sel.split(", "):
                sel = sel.strip()
                if sel:
                    price_el = card.select_one(sel)
                    if price_el:
                        price = parse_price(price_el.get_text(strip=True))
                        break

            if title or href:
                products.append({
                    "name": title,
                    "retail_url": href,
                    "source_url": href,  # Normalized alias
                    "retail_price": price,
                    "sale_price": None,
                    "upc": None,
                    "image_url": None,
                    "scraped_at": datetime.now().isoformat(),
                })

        # Try pagination
        next_sel = pagination.get("next_button", "")
        if next_sel and page_num < max_pages - 1:
            next_link = None
            for sel in next_sel.split(", "):
                sel = sel.strip()
                if sel:
                    next_link = soup.select_one(sel)
                    if next_link:
                        break
            if next_link and next_link.get("href"):
                current_url = urljoin(current_url, next_link["href"])
                time.sleep(delay)
            else:
                break
        else:
            break

    return products


def enrich_from_product_pages(page, products, config, max_enrich=20):
    """Visit individual product pages to get UPC, images, exact prices."""
    prod_selectors = config.get("product_page", {})
    delay = config.get("request_delay", 2.0)

    enriched_count = 0
    for i, product in enumerate(products[:max_enrich]):
        if not product.get("retail_url"):
            continue

        print(f"  [enrich] {i + 1}/{min(len(products), max_enrich)} — {product.get('name', 'unknown')[:60]}",
              file=sys.stderr)

        try:
            detail = scrape_product_page(page, product["retail_url"], prod_selectors)
            if not detail:
                continue

            # Merge — keep existing data, fill in blanks
            for key in ["upc", "image_url", "sale_price"]:
                if not product.get(key) and detail.get(key):
                    product[key] = detail[key]
            if not product.get("name") and detail.get("name"):
                product["name"] = detail["name"]
            if not product.get("retail_price") and detail.get("retail_price"):
                product["retail_price"] = detail["retail_price"]

            enriched_count += 1
            time.sleep(delay)
        except Exception as e:
            print(f"  [enrich error] {product.get('name', 'unknown')}: {e}", file=sys.stderr)

    print(f"  [enrich] Enriched {enriched_count}/{min(len(products), max_enrich)} products", file=sys.stderr)
    return products


def main():
    parser = argparse.ArgumentParser(description="Scrape product data from retail websites")
    parser.add_argument("--url", required=True, help="Retail URL to scrape (product page or category/search page)")
    parser.add_argument("--max-products", type=int, default=50, help="Max products to scrape (default: 50)")
    parser.add_argument("--enrich", action="store_true", default=True,
                        help="Visit individual product pages for UPC/details (default: on)")
    parser.add_argument("--no-enrich", action="store_false", dest="enrich",
                        help="Skip enrichment (faster but less data)")
    parser.add_argument("--max-enrich", type=int, default=20,
                        help="Max products to enrich with detail pages (default: 20)")
    parser.add_argument("--output", default=None, help="Output JSON path (default: .tmp/sourcing/)")
    args = parser.parse_args()

    retailer_key, config = get_retailer_config(args.url)
    page_type = detect_page_type(args.url)

    print(f"[scrape_retail] Retailer: {config['name']} | Page type: {page_type}", file=sys.stderr)
    print(f"[scrape_retail] URL: {args.url}", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        context.add_init_script(STEALTH_SCRIPT)
        page = context.new_page()

        if page_type == "product":
            result = scrape_product_page(page, args.url, config["product_page"])
            products = [result] if result else []
            for prod in products:
                prod["retailer"] = config["name"]
        else:
            products = scrape_category_page(page, args.url, config, args.max_products)
            for prod in products:
                prod["retailer"] = config["name"]
            if args.enrich and products:
                products = enrich_from_product_pages(page, products, config, args.max_enrich)

        browser.close()

    # Filter out products with no name and no price
    products = [p for p in products if p.get("name") or p.get("retail_price")]

    # Output
    output_path = args.output
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(__file__).parent.parent / ".tmp" / "sourcing"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"{ts}-retail-products.json")

    with open(output_path, "w") as f:
        json.dump({
            "retailer": config["name"],
            "retailer_key": retailer_key,
            "url": args.url,
            "page_type": page_type,
            "products": products,
            "count": len(products),
            "scraped_at": datetime.now().isoformat(),
        }, f, indent=2)

    print(f"[scrape_retail] Done. {len(products)} products scraped → {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
