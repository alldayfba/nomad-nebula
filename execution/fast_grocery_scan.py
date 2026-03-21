#!/usr/bin/env python3
"""
Script: fast_grocery_scan.py
Purpose: Fast grocery product sourcing using Keepa API + Target HTTP API.
         No headless browser needed. Finds profitable arbitrage opportunities.

Strategy:
  1. Keepa → get popular grocery ASINs with prices, BSR, UPCs
  2. Target Redsky API (or HTML scrape) → check if same UPC is cheaper at retail
  3. Calculate profitability → rank by ROI

Usage:
  python execution/fast_grocery_scan.py --category grocery --count 20
  python execution/fast_grocery_scan.py --category candy --count 30
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

import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calculate_fba_profitability import calculate_product_profitability
from source import compute_match_confidence, _extract_product_size, _sizes_match

KEEPA_KEY = os.getenv("KEEPA_API_KEY", "")
PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Import centralized KeepaClient (v3.0)
try:
    from keepa_client import KeepaClient
    _keepa_client = None
    def _get_client():
        global _keepa_client
        if _keepa_client is None:
            _keepa_client = KeepaClient()
        return _keepa_client
    HAS_KEEPA_CLIENT = True
except ImportError:
    HAS_KEEPA_CLIENT = False

# Keepa category IDs
KEEPA_CATEGORIES = {
    "grocery": 16310101,
    "candy": 16310101,       # Grocery & Gourmet Food
    "health": 3760901,       # Health & Household
    "beauty": 3760911,       # Beauty & Personal Care
    "baby": 165796011,       # Baby
    "pets": 2619533011,      # Pet Supplies
    "home": 1055398,         # Home & Kitchen
    "toys": 165793011,       # Toys & Games
    "sports": 3375251,       # Sports & Outdoors
    "office": 1064954,       # Office Products
}

KEEPA_DELAY = 3.0  # seconds between Keepa calls (Pro tier: 20 tokens/min)


def wait_for_keepa_tokens(min_tokens=5):
    """Wait until we have enough Keepa tokens."""
    while True:
        try:
            r = requests.get("https://api.keepa.com/token",
                             params={"key": KEEPA_KEY}, timeout=10)
            bal = r.json()
        except Exception as e:
            print(f"  [keepa] Token check failed: {e}", file=sys.stderr)
            time.sleep(10)
            continue
        tokens = bal["tokensLeft"]
        if tokens >= min_tokens:
            return tokens
        wait = (abs(tokens) + min_tokens) * 60 // max(bal["refillRate"], 1) + 5
        print(f"  [keepa] Waiting {wait}s for tokens (have {tokens}, need {min_tokens})...",
              file=sys.stderr)
        time.sleep(wait)


def keepa_get_bestsellers(category_id, count=50):
    """Get best-selling ASINs in a category from Keepa."""
    wait_for_keepa_tokens(5)
    try:
        r = requests.get("https://api.keepa.com/bestsellers", params={
            "key": KEEPA_KEY,
            "domain": 1,
            "category": category_id,
        }, timeout=15)
    except Exception as e:
        print(f"  [keepa] Bestsellers request failed: {e}", file=sys.stderr)
        return []
    if r.status_code != 200:
        print(f"  [keepa] Bestsellers error: {r.status_code}", file=sys.stderr)
        return []
    data = r.json()
    asins = data.get("bestSellersList", {}).get("asinList", [])
    print(f"  [keepa] Got {len(asins)} bestseller ASINs", file=sys.stderr)
    return asins[:count]


def keepa_get_products(asins):
    """Fetch product details for a batch of ASINs from Keepa (max 100 per call)."""
    if not asins:
        return []
    # Token cost: 1 per ASIN (no offers/buybox = much cheaper)
    tokens_needed = len(asins) + 1
    wait_for_keepa_tokens(tokens_needed)
    try:
        r = requests.get("https://api.keepa.com/product", params={
            "key": KEEPA_KEY,
            "domain": 1,
            "asin": ",".join(asins),
            "stats": 180,  # 180-day stats — populates CSV history for PL detection
        }, timeout=30)
    except Exception as e:
        print(f"  [keepa] Product request failed: {e}", file=sys.stderr)
        return []
    if r.status_code != 200:
        print(f"  [keepa] Product error: {r.status_code} {r.text[:100]}", file=sys.stderr)
        return []
    data = r.json()
    products = data.get("products", [])
    tokens = data.get("tokensLeft", "?")
    print(f"  [keepa] Got {len(products)} product details (tokens left: {tokens})",
          file=sys.stderr)
    return products


def parse_keepa_product(kp):
    """Parse a Keepa product into a clean dict with price, BSR, UPC, etc.

    v3.0: Uses KeepaClient.parse_product() when available for correct
    CSV indices (34=FBA sellers, 35=FBM sellers) and private label detection.
    Falls back to inline parsing if KeepaClient not importable.
    """
    if HAS_KEEPA_CLIENT:
        client = _get_client()
        parsed = client.parse_product(kp)
        # Map to the format expected by the rest of this script
        return {
            "asin": parsed.get("asin", ""),
            "title": parsed.get("title", ""),
            "amazon_price": parsed.get("sell_price"),
            "amz_direct_price": parsed.get("amazon_price"),
            "mp_price": parsed.get("new_3p_price"),
            "bb_price": parsed.get("buy_box_price"),
            "bsr": parsed.get("bsr"),
            "upc": parsed.get("upc", ""),
            "category": parsed.get("category", ""),
            "fba_seller_count": parsed.get("fba_seller_count") or 0,
            "fbm_seller_count": parsed.get("fbm_seller_count"),
            "amazon_on_listing": parsed.get("amazon_on_listing", False),
            "brand": parsed.get("brand", ""),
            "private_label": parsed.get("private_label", {}),
            "price_trends": parsed.get("price_trends", {}),
            "review_count": parsed.get("review_count"),
        }

    # Fallback: inline parsing (pre-v3.0 logic)
    asin = kp.get("asin", "")
    title = kp.get("title", "")

    stats = kp.get("stats", {})
    amz_price = None
    if stats.get("current"):
        p = stats["current"][0]
        if isinstance(p, (int, float)) and p > 0:
            amz_price = p / 100.0

    mp_price = None
    if stats.get("current") and len(stats["current"]) > 1:
        p = stats["current"][1]
        if isinstance(p, (int, float)) and p > 0:
            mp_price = p / 100.0

    bb_price = None
    if stats.get("current") and len(stats["current"]) > 18:
        p = stats["current"][18]
        if isinstance(p, (int, float)) and p > 0:
            bb_price = p / 100.0

    sell_price = bb_price or amz_price or mp_price

    bsr = None
    if stats.get("current") and len(stats["current"]) > 3:
        b = stats["current"][3]
        if isinstance(b, (int, float)) and b > 0:
            bsr = int(b)

    ean_list = kp.get("eanList", [])
    upc_list = kp.get("upcList", [])
    upc = upc_list[0] if upc_list else (ean_list[0] if ean_list else "")

    category = ""
    cat_tree = kp.get("categoryTree", [])
    if cat_tree:
        category = cat_tree[-1].get("name", "")

    fba_count = kp.get("fbaOfferCount", 0) or 0

    amazon_on = False
    if stats.get("current") and len(stats["current"]) > 0:
        amazon_on = (stats["current"][0] is not None and
                     isinstance(stats["current"][0], (int, float)) and
                     stats["current"][0] > 0)

    brand = kp.get("brand", "")

    return {
        "asin": asin,
        "title": title,
        "amazon_price": sell_price,
        "amz_direct_price": amz_price,
        "mp_price": mp_price,
        "bb_price": bb_price,
        "bsr": bsr,
        "upc": upc,
        "category": category,
        "fba_seller_count": fba_count,
        "amazon_on_listing": amazon_on,
        "brand": brand,
    }


def search_target_by_upc(upc, session=None):
    """Search Target for a product by UPC using their search page."""
    if not upc:
        return None
    s = session or requests.Session()
    try:
        r = s.get(f"https://www.target.com/s?searchTerm={upc}",
                  headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # Look for price in the page
        # Target embeds product data in JSON-LD or __NEXT_DATA__
        # Try JSON-LD first
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld = json.loads(script.string or "")
                if isinstance(ld, list):
                    ld = ld[0]
                if ld.get("@type") == "Product":
                    offers = ld.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price = offers.get("price")
                    name = ld.get("name", "")
                    if price:
                        return {
                            "retailer": "Target",
                            "name": name,
                            "retail_price": float(price),
                            "upc": upc,
                        }
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        # Try parsing price from HTML
        price_el = soup.select_one('span[data-test="current-price"] span')
        if price_el:
            price_text = price_el.get_text(strip=True)
            match = re.search(r"\$?([\d,]+\.?\d*)", price_text)
            if match:
                price = float(match.group(1).replace(",", ""))
                title_el = soup.select_one('a[data-test="@web/ProductCard/title"]')
                name = title_el.get_text(strip=True) if title_el else ""
                return {
                    "retailer": "Target",
                    "name": name,
                    "retail_price": price,
                    "upc": upc,
                }
    except Exception as e:
        print(f"    [target] Error for UPC {upc}: {e}", file=sys.stderr)
    return None


def search_walmart_by_upc(upc, session=None):
    """Search Walmart for a product by UPC — uses the search page HTML."""
    if not upc:
        return None
    s = session or requests.Session()
    try:
        # Walmart sometimes works with UPC search via regular HTTP
        url = f"https://www.walmart.com/search?q={upc}"
        r = s.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # Check for bot detection
        title = soup.find("title")
        if title and "robot" in title.get_text().lower():
            return None

        # Look for __NEXT_DATA__
        script = soup.find("script", id="__NEXT_DATA__")
        if script:
            data = json.loads(script.string)
            try:
                items = data["props"]["pageProps"]["initialData"]["searchResult"]["itemStacks"][0]["items"]
                if items:
                    item = items[0]
                    price_info = item.get("priceInfo", {})
                    price_str = price_info.get("linePrice", "")
                    price = float(re.search(r"[\d.]+", price_str).group()) if price_str else None
                    return {
                        "retailer": "Walmart",
                        "name": item.get("name", ""),
                        "retail_price": price,
                        "upc": upc,
                    }
            except (KeyError, IndexError, TypeError, AttributeError):
                pass
    except Exception as e:
        print(f"    [walmart] Error for UPC {upc}: {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Playwright-powered retailer UPC search (renders JavaScript properly)
# ---------------------------------------------------------------------------
_pw_browser = None

def _get_playwright_browser():
    """Lazy-init a shared Playwright browser instance."""
    global _pw_browser
    if _pw_browser is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        _pw_browser = pw.chromium.launch(headless=True)
    return _pw_browser


def _extract_price_from_text(text):
    """Pull the first dollar amount from a string."""
    m = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


STEALTH_JS = '''
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}};
'''

_pw_context = None


def _get_playwright_context():
    """Lazy-init a shared Playwright browser context with stealth."""
    global _pw_context
    if _pw_context is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        _pw_context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        _pw_context.add_init_script(STEALTH_JS)
    return _pw_context


def _shorten_title(title):
    """Strip brand qualifiers and shorten title for retail search."""
    # Remove common suffixes that hurt search
    title = re.sub(r"\s*-\s*\d+\s*(Pack|Count|Ct|pk|ct).*", "", title, flags=re.I)
    # Keep first ~6 meaningful words
    words = title.split()[:8]
    return " ".join(words)


def _extract_pack_quantity(title):
    """Extract pack/count from a product title. Returns int or None."""
    if not title:
        return None
    # Match patterns like "12-Pack", "6 Count", "24ct", "Pack of 8", "x12"
    patterns = [
        r"(\d+)\s*[-\s]?\s*(pack|pk|count|ct)\b",
        r"pack\s+of\s+(\d+)",
        r"\bx\s*(\d+)\b",
        r"(\d+)\s*rolls?\b",
        r"(\d+)\s*cans?\b",
        r"(\d+)\s*bottles?\b",
        r"(\d+)\s*pods?\b",
        r"(\d+)\s*capsules?\b",
        r"(\d+)\s*sticks?\b",
        r"(\d+)\s*wipes?\b",
    ]
    for pat in patterns:
        m = re.search(pat, title, re.I)
        if m:
            qty = int(m.group(1))
            if 2 <= qty <= 500:  # sanity range
                return qty
    return None


def search_target_pw(product_title, upc="", amazon_title=""):
    """Search Target by product name using Playwright (JS-rendered).
    Target does NOT support UPC search — must use product title.
    Evaluates top 3 search results and picks the best match against amazon_title.
    Returns None if no result scores >= 0.70 confidence."""
    if not product_title:
        return None
    # Use amazon_title for scoring if provided, otherwise score against product_title
    score_against = amazon_title or product_title
    ctx = _get_playwright_context()
    page = ctx.new_page()
    try:
        query = _shorten_title(product_title)
        search_url = f"https://www.target.com/s?searchTerm={quote_plus(query)}"
        page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(4000)

        soup = BeautifulSoup(page.content(), "html.parser")
        body_text = soup.get_text(" ", strip=True).lower()
        if "couldn't find a match" in body_text:
            return None

        # Find ALL product cards (up to 3) and score each
        card_selectors = [
            'a[data-test="product-title"]',
            'a[data-test="@web/ProductCard/title"]',
            'div[data-test="product-card"] a[href*="/p/"]',
            'a[href*="/p/"][href*="-"]',
        ]
        all_cards = []
        for sel in card_selectors:
            all_cards = soup.select(sel)
            if all_cards:
                break

        if not all_cards:
            return None

        # Score top 3 cards against the Amazon title
        candidates = []
        for card in all_cards[:3]:
            href = card.get("href", "")
            card_text = card.get_text(strip=True)
            if not card_text:
                continue

            card_url = f"https://www.target.com{href}" if href.startswith("/") else (href or search_url)

            # Find price near this card (walk up to parent container)
            card_price = None
            parent = card.find_parent("div") or card.find_parent("li")
            if parent:
                for psel in ['span[data-test="current-price"] span', 'span[data-test="current-price"]']:
                    price_el = parent.select_one(psel)
                    if price_el:
                        card_price = _extract_price_from_text(price_el.get_text())
                        if card_price:
                            break

            if not card_price or card_price < 0.50 or card_price > 500:
                continue

            confidence = compute_match_confidence(card_text, score_against)
            candidates.append({
                "retailer": "Target",
                "name": card_text,
                "retail_price": card_price,
                "upc": upc,
                "buy_url": card_url,
                "match_confidence": confidence,
                "match_method": "title",
            })

        if not candidates:
            # Fallback: try extracting first price from page (old behavior)
            price_el = (
                soup.select_one('span[data-test="current-price"] span')
                or soup.select_one('span[data-test="current-price"]')
            )
            if price_el:
                price = _extract_price_from_text(price_el.get_text())
                if price and 0.50 < price < 500:
                    confidence = compute_match_confidence(product_title, score_against)
                    if confidence >= 0.70:
                        return {
                            "retailer": "Target",
                            "name": product_title,
                            "retail_price": price,
                            "upc": upc,
                            "buy_url": search_url,
                            "match_confidence": confidence,
                            "match_method": "title",
                        }
            return None

        # Pick best match
        candidates.sort(key=lambda c: c["match_confidence"], reverse=True)
        best = candidates[0]

        if best["match_confidence"] < 0.70:
            print(f"    [target-pw] Best match only {best['match_confidence']:.0%} confidence: "
                  f"'{best['name'][:40]}' — rejecting", file=sys.stderr)
            return None

        print(f"    [target-pw] Best match {best['match_confidence']:.0%}: "
              f"'{best['name'][:40]}' @ ${best['retail_price']:.2f}", file=sys.stderr)
        return best

    except Exception as e:
        print(f"    [target-pw] Error: {e}", file=sys.stderr)
    finally:
        page.close()
    return None


def search_walgreens_pw(product_title, upc="", amazon_title=""):
    """Search Walgreens by product name using Playwright.
    Evaluates top 3 search results and picks the best match against amazon_title.
    Returns None if no result scores >= 0.70 confidence."""
    if not product_title:
        return None
    score_against = amazon_title or product_title
    ctx = _get_playwright_context()
    page = ctx.new_page()
    try:
        query = _shorten_title(product_title)
        search_url = f"https://www.walgreens.com/search/results.jsp?Ntt={quote_plus(query)}"
        page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(4000)

        title_text = page.title()
        if "access denied" in title_text.lower():
            return None

        soup = BeautifulSoup(page.content(), "html.parser")

        # Find ALL product cards (up to 3) and score each
        # Walgreens uses .card containers with links to /store/c/ paths
        card_selectors = [
            '.card a[href*="/store/c/"]',
            'a[href*="/store/c/"][href*="-product"]',
            'a[href*="/store/c/"]',
        ]
        all_cards = []
        for sel in card_selectors:
            all_cards = soup.select(sel)
            if all_cards:
                break

        if not all_cards:
            return None

        candidates = []
        for card in all_cards[:3]:
            href = card.get("href", "")
            card_text = card.get_text(strip=True)
            if not card_text:
                continue

            card_url = f"https://www.walgreens.com{href}" if href.startswith("/") else (href or search_url)

            # Find price — check parent .card container for price info
            card_price = None
            parent = card.find_parent(class_="card") or card.find_parent("div") or card.find_parent("li")
            if parent:
                parent_text = parent.get_text(" ", strip=True)
                # Prefer sale price: "Current sale price is $X.XX"
                sale_match = re.search(r'[Ss]ale\s+price\s+(?:is\s+)?\$(\d+\.?\d*)', parent_text)
                if sale_match:
                    card_price = float(sale_match.group(1))
                else:
                    # Fall back to any price in the card
                    for psel in ['[class*="price"]', '.product__price']:
                        price_el = parent.select_one(psel)
                        if price_el:
                            price_text = price_el.get_text()
                            if "off" not in price_text.lower() and "code" not in price_text.lower():
                                card_price = _extract_price_from_text(price_text)
                                if card_price:
                                    break
                    # If still no price, extract from raw card text
                    if not card_price:
                        card_price = _extract_price_from_text(parent_text)

            if not card_price or card_price < 0.50 or card_price > 500:
                continue

            confidence = compute_match_confidence(card_text, score_against)
            candidates.append({
                "retailer": "Walgreens",
                "name": card_text,
                "retail_price": card_price,
                "upc": upc,
                "buy_url": card_url,
                "match_confidence": confidence,
                "match_method": "title",
            })

        if not candidates:
            return None

        # Pick best match
        candidates.sort(key=lambda c: c["match_confidence"], reverse=True)
        best = candidates[0]

        if best["match_confidence"] < 0.70:
            print(f"    [walgreens-pw] Best match only {best['match_confidence']:.0%} confidence: "
                  f"'{best['name'][:40]}' — rejecting", file=sys.stderr)
            return None

        print(f"    [walgreens-pw] Best match {best['match_confidence']:.0%}: "
              f"'{best['name'][:40]}' @ ${best['retail_price']:.2f}", file=sys.stderr)
        return best

    except Exception as e:
        print(f"    [walgreens-pw] Error: {e}", file=sys.stderr)
    finally:
        page.close()
    return None


def _search_retailer_by_upc_pw(upc, retailer, amazon_title=""):
    """Try UPC search at a retailer via Playwright. Returns result or None.
    UPC searches give exact product matches (confidence 1.0)."""
    if not upc:
        return None
    ctx = _get_playwright_context()
    page = ctx.new_page()
    try:
        if retailer == "target":
            search_url = f"https://www.target.com/s?searchTerm={upc}"
            card_sel = 'a[data-test="product-title"]'
            price_sel = 'span[data-test="current-price"] span'
            no_results = "couldn't find a match"
            base = "https://www.target.com"
        elif retailer == "walgreens":
            search_url = f"https://www.walgreens.com/search/results.jsp?Ntt={upc}"
            card_sel = '.card a[href*="/store/c/"]'
            price_sel = '[class*="price"]'
            no_results = "access denied"
            base = "https://www.walgreens.com"
        else:
            return None

        page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(4000)

        soup = BeautifulSoup(page.content(), "html.parser")
        body_text = soup.get_text(" ", strip=True).lower()
        if no_results in body_text:
            return None

        card = soup.select_one(card_sel)
        if not card:
            return None

        href = card.get("href", "")
        card_text = card.get_text(strip=True)
        product_url = f"{base}{href}" if href.startswith("/") else (href or search_url)

        # Get price
        price = None
        parent = card.find_parent("div") or card.find_parent("li")
        if parent:
            price_el = parent.select_one(price_sel)
            if price_el:
                price = _extract_price_from_text(price_el.get_text())

        if not price or price < 0.50 or price > 500:
            return None

        # UPC match — verify the result actually looks right by checking title overlap
        if amazon_title and card_text:
            conf = compute_match_confidence(card_text, amazon_title)
            # UPC search can still return wrong results if UPC maps to different variant
            # But we trust UPC more, so use lower threshold (0.50 vs 0.70 for title)
            if conf < 0.50:
                print(f"    [{retailer}] UPC found but low title match ({conf:.0%}): "
                      f"'{card_text[:40]}' — skipping", file=sys.stderr)
                return None

        print(f"    [{retailer}] UPC match! '{card_text[:40]}' @ ${price:.2f}", file=sys.stderr)
        return {
            "retailer": retailer.title(),
            "name": card_text,
            "retail_price": price,
            "upc": upc,
            "buy_url": product_url,
            "match_confidence": 0.95,  # UPC = near-certain match
            "match_method": "upc",
        }
    except Exception as e:
        print(f"    [{retailer}] UPC search error: {e}", file=sys.stderr)
    finally:
        page.close()
    return None


def search_retailers_by_upc(upc, session=None, use_playwright=True,
                             product_title="", amazon_title=""):
    """Search multiple retailers for a product. Strategy:
    1. Try UPC search via Playwright (exact match, confidence 0.95)
    2. Fall back to title search with multi-result scoring (confidence 0.70+ required)
    Searches Target + Walgreens (Walmart/CVS block bots)."""
    results = []
    score_title = amazon_title or product_title

    if use_playwright:
        for retailer in ["target", "walgreens"]:
            # Step 1: Try UPC search first (exact match)
            if upc:
                upc_result = _search_retailer_by_upc_pw(upc, retailer, amazon_title=score_title)
                if upc_result and upc_result.get("retail_price"):
                    results.append(upc_result)
                    continue  # Got UPC match, skip title search for this retailer

            # Step 2: Fall back to title search with scoring
            if product_title:
                if retailer == "target":
                    title_result = search_target_pw(product_title, upc, amazon_title=score_title)
                else:
                    title_result = search_walgreens_pw(product_title, upc, amazon_title=score_title)
                if title_result and title_result.get("retail_price"):
                    results.append(title_result)
    else:
        # HTTP fallback (usually fails)
        target = search_target_by_upc(upc, session)
        if target and target.get("retail_price"):
            results.append(target)
        walmart = search_walmart_by_upc(upc, session)
        if walmart and walmart.get("retail_price"):
            results.append(walmart)

    if not results:
        return None

    # Return cheapest
    results.sort(key=lambda x: x["retail_price"])
    best = results[0]
    if len(results) > 1:
        best["alternative_sources"] = results[1:]
    return best


def calculate_profit(amazon_product, retail_match):
    """Calculate profitability for a product found cheaper at retail."""
    product = {
        "name": retail_match.get("name") or amazon_product["title"],
        "retail_price": retail_match["retail_price"],
        "retailer": retail_match.get("retailer", ""),
        "upc": retail_match.get("upc", ""),
        "amazon": {
            "asin": amazon_product["asin"],
            "title": amazon_product["title"],
            "amazon_price": amazon_product["amazon_price"],
            "sales_rank": amazon_product.get("bsr"),
            "category": amazon_product.get("category", "Grocery"),
            "fba_seller_count": amazon_product.get("fba_seller_count", 0),
            "amazon_on_listing": amazon_product.get("amazon_on_listing", False),
            "match_confidence": 0.95,  # UPC match = high confidence
            "match_method": "upc",
        },
    }
    try:
        prof = calculate_product_profitability(product, auto_cashback=True)
        return prof
    except Exception as e:
        print(f"    [profit] Error: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Fast grocery sourcing via Keepa + retail price check")
    parser.add_argument("--category", "-c", default="grocery",
                        help=f"Category: {', '.join(KEEPA_CATEGORIES.keys())}")
    parser.add_argument("--count", "-n", type=int, default=20,
                        help="Number of products to scan (default: 20)")
    parser.add_argument("--output", "-o", default=None)
    args = parser.parse_args()

    cat_id = KEEPA_CATEGORIES.get(args.category.lower(), KEEPA_CATEGORIES["grocery"])
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    start = time.time()

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[fast-scan] Category: {args.category} (Keepa ID: {cat_id})", file=sys.stderr)
    print(f"[fast-scan] Target count: {args.count}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    # Phase 1: Get bestseller ASINs from Keepa
    print("[fast-scan] Phase 1: Getting bestseller ASINs from Keepa...", file=sys.stderr)
    asins = keepa_get_bestsellers(cat_id, count=min(args.count * 3, 100))
    if not asins:
        print("[fast-scan] No ASINs found. Check Keepa API key.", file=sys.stderr)
        return

    # Phase 2: Get product details (prices, UPCs, BSR) in small batches
    # Keepa costs ~1 token per ASIN with stats=1, so batch of 10 = ~11 tokens
    batch_size = 10
    print(f"\n[fast-scan] Phase 2: Fetching details for {len(asins)} ASINs "
          f"(batches of {batch_size})...", file=sys.stderr)
    all_products = []
    for i in range(0, len(asins), batch_size):
        batch = asins[i:i+batch_size]
        products = keepa_get_products(batch)
        for kp in products:
            parsed = parse_keepa_product(kp)
            # PL filter: only skip DEFINITIVE private label (offers-verified)
            # "possible" and "strong" from CSV data are unreliable — let them through
            pl_info = parsed.get("private_label", {})
            if isinstance(pl_info, dict) and pl_info.get("is_private_label") and pl_info.get("confidence") == "definitive":
                print(f"    [PL-SKIP] {parsed.get('title', '?')[:50]} — confirmed private label",
                      file=sys.stderr)
                continue
            if parsed["amazon_price"] and parsed["upc"]:
                all_products.append(parsed)
        # Stop early if we have enough candidates
        if len(all_products) >= args.count * 2:
            print(f"  [fast-scan] Got enough candidates ({len(all_products)}), stopping Keepa calls",
                  file=sys.stderr)
            break
        if i + batch_size < len(asins):
            time.sleep(KEEPA_DELAY)

    print(f"  [fast-scan] {len(all_products)} products with price + UPC", file=sys.stderr)

    # Filter: only products in good price range for arbitrage
    candidates = [p for p in all_products
                  if p["amazon_price"] and 3.0 <= p["amazon_price"] <= 50.0
                  and p.get("bsr") and p["bsr"] < 200000]
    print(f"  [fast-scan] {len(candidates)} candidates in $3-50 range with BSR < 200K",
          file=sys.stderr)

    # Phase 3: Price check at retail
    print(f"\n[fast-scan] Phase 3: Checking retail prices...", file=sys.stderr)
    session = requests.Session()
    results = []
    for i, product in enumerate(candidates[:args.count * 2]):
        upc = product["upc"]
        print(f"  [{i+1}/{min(len(candidates), args.count*2)}] "
              f"UPC:{upc} | ${product['amazon_price']:.2f} AMZ | {product['title'][:40]}",
              file=sys.stderr)

        retail = search_retailers_by_upc(upc, session,
                                                product_title=product["title"],
                                                amazon_title=product["title"])
        if retail and retail.get("retail_price"):
            # Pack-size mismatch filter: if Amazon is 3x+ retail price,
            # likely multi-pack vs single unit — adjust profit calc
            price_ratio = product["amazon_price"] / retail["retail_price"] if retail["retail_price"] > 0 else 0
            if price_ratio >= 3.0:
                est_pack = round(price_ratio)
                true_cost = retail["retail_price"] * est_pack
                true_profit = product["amazon_price"] - true_cost - (true_cost * 0.15 + 4.0)
                if true_profit < 1.50:
                    print(f"    → Skip (pack mismatch: ~{est_pack}x units, "
                          f"${true_cost:.2f} true cost, ${true_profit:.2f} profit)",
                          file=sys.stderr)
                    continue
            # Quick check: is retail cheaper than Amazon?
            margin = product["amazon_price"] - retail["retail_price"]
            if margin > 2.0:  # At least $2 cheaper at retail
                prof = calculate_profit(product, retail)
                if prof:
                    retail_name = retail.get("name") or product["title"]
                    amazon_title = product["title"]
                    retail_pack = _extract_pack_quantity(retail_name)
                    amazon_pack = _extract_pack_quantity(amazon_title)
                    pack_match = (retail_pack == amazon_pack) if (retail_pack and amazon_pack) else None

                    # Match confidence from the retailer search
                    match_conf = retail.get("match_confidence", 0.5)
                    match_method = retail.get("match_method", "title")

                    results.append({
                        "asin": product["asin"],
                        "amazon_title": amazon_title,
                        "amazon_price": product["amazon_price"],
                        "source_retailer": retail["retailer"],
                        "source_url": retail.get("buy_url", ""),
                        "buy_cost": retail["retail_price"],
                        "estimated_profit": prof.get("profit_per_unit", 0) or 0,
                        "estimated_roi": prof.get("roi_percent", 0) or 0,
                        "match_method": match_method,
                        "match_confidence": match_conf,
                        "verdict": prof.get("verdict") or "?",
                        # Keep legacy fields for compatibility
                        "name": retail_name,
                        "upc": upc,
                        "retail_price": retail["retail_price"],
                        "amazon_url": f"https://www.amazon.com/dp/{product['asin']}",
                        "bsr": product.get("bsr"),
                        "category": product.get("category", "Grocery"),
                        "profitability": prof,
                        "pack_info": {
                            "retail_title": retail_name,
                            "amazon_title": amazon_title,
                            "retail_pack": retail_pack,
                            "amazon_pack": amazon_pack,
                            "match": pack_match,
                            "verified": False,
                            "warning": "Verify pack sizes with Amazon Seller App before buying"
                                       if pack_match is not True else None,
                        },
                        "alternative_sources": retail.get("alternative_sources", []),
                    })
                    verdict = prof.get("verdict") or "?"
                    roi = prof.get("roi_percent", 0) or 0
                    profit = prof.get("profit_per_unit", 0) or 0
                    print(f"    → {verdict} | ROI:{roi:.0f}% | ${profit:.2f} profit | "
                          f"${retail['retail_price']:.2f} @ {retail['retailer']} → "
                          f"${product['amazon_price']:.2f} AMZ | "
                          f"Match: {match_method} {match_conf:.0%}", file=sys.stderr)
            else:
                print(f"    → Skip (margin ${margin:.2f} too thin)", file=sys.stderr)
        else:
            print(f"    → Not found at retail", file=sys.stderr)

        time.sleep(1.5)  # Be polite to retailers

        if len(results) >= args.count:
            break

    # Sort by ROI
    results.sort(key=lambda x: x.get("profitability", {}).get("roi_percent", 0) or 0, reverse=True)

    # Output
    elapsed = time.time() - start
    buy_count = sum(1 for r in results if r.get("profitability", {}).get("verdict") == "BUY")
    maybe_count = sum(1 for r in results if r.get("profitability", {}).get("verdict") == "MAYBE")

    output = {
        "category": args.category,
        "products": results,
        "count": len(results),
        "summary": {
            "total_scanned": len(candidates),
            "retail_matches": len(results),
            "buy_count": buy_count,
            "maybe_count": maybe_count,
            "elapsed_seconds": round(elapsed),
        },
        "timestamp": datetime.now().isoformat(),
    }

    output_path = args.output or str(TMP_DIR / f"{ts}-fast-grocery.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[fast-scan] COMPLETE ({elapsed:.0f}s)", file=sys.stderr)
    print(f"  Scanned:  {len(candidates)} Amazon products", file=sys.stderr)
    print(f"  Matches:  {len(results)} found cheaper at retail", file=sys.stderr)
    print(f"  BUY:      {buy_count}", file=sys.stderr)
    print(f"  MAYBE:    {maybe_count}", file=sys.stderr)
    print(f"  JSON:     {output_path}", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)

    # Print results table — standardized format
    if results:
        print(f"\n{'#':>2} {'ASIN':<12} {'Amazon Title':<30} {'AMZ$':>6} "
              f"{'Source':>8} {'Buy$':>6} {'Profit':>7} {'ROI':>5} {'Match':>10}")
        print("─" * 100)
        for idx, r in enumerate(results, 1):
            verdict = r.get("verdict") or "?"
            roi = r.get("estimated_roi", 0) or 0
            profit = r.get("estimated_profit", 0) or 0
            amz_price = r.get("amazon_price", 0) or 0
            buy_cost = r.get("buy_cost", 0) or r.get("retail_price", 0) or 0
            retailer = r.get("source_retailer", "") or r.get("retailer", "")
            title = r.get("amazon_title", "") or r.get("name", "")
            method = r.get("match_method", "?")
            conf = r.get("match_confidence", 0) or 0
            match_str = f"{'UPC' if method == 'upc' else 'Title'} {conf:.0%}"

            print(f"{idx:>2} {r['asin']:<12} {title[:28]:<30} ${amz_price:>5.2f} "
                  f"{retailer:>8} ${buy_cost:>5.2f} ${profit:>5.2f} {roi:>4.0f}% "
                  f"{match_str:>10} [{verdict}]")


if __name__ == "__main__":
    main()
