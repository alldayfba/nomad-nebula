#!/usr/bin/env python3
"""
Unified CLI for Amazon FBA online arbitrage sourcing.

Modes:
  brand     — Search retailers for a specific brand
  category  — Browse a category for arbitrage opportunities
  retailer  — Scan a retailer's clearance/sale pages
  scan      — Multi-source scan (clearance + deal sites + optional Keepa)
  asin      — Reverse-source a single ASIN
  oos       — Find out-of-stock Amazon opportunities (Keepa Pro required)
  a2a       — Amazon-to-Amazon flips (warehouse, variation, multipack)
  finder    — Keepa Product Finder (bulk catalog search for price drops)

Zero-token-first principle:
  1. FREE: Scrape retailers via Playwright (0 Keepa tokens)
  2. CHEAP: Verify top candidates on Amazon via Keepa search (1 token/ea)
  3. EXPENSIVE: Deep verify top hits with offers data (21 tokens/ea) — optional

Usage:
  python execution/source.py brand "Jellycat" --retailers target,walgreens,walmart
  python execution/source.py brand "CeraVe" --retailers target --max 30
  python execution/source.py category "toys" --subcategory "plush"
  python execution/source.py retailer target --section clearance
  python execution/source.py scan --count 20
  python execution/source.py asin B08XYZ1234
  python execution/source.py oos --count 30 --max-bsr 100000
  python execution/source.py a2a --type warehouse --count 30
  python execution/source.py finder --min-drop 30 --max-bsr 100000
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

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"

# ── Checkpoint/Resume helpers ────────────────────────────────────────────────

_checkpoint_scan_id = None
_resume_mode = False


def _checkpoint_path(scan_id=None):
    """Return path to checkpoint file for a scan."""
    sid = scan_id or _checkpoint_scan_id or "default"
    return TMP_DIR / f"checkpoint_{sid}.json"


def _load_checkpoint(scan_id=None):
    """Load checkpoint data. Returns (processed_asins_set, partial_results_list)."""
    cp = _checkpoint_path(scan_id)
    if cp.exists():
        try:
            data = json.loads(cp.read_text())
            processed = set(data.get("processed_asins", []))
            results = data.get("results", [])
            print(f"[checkpoint] Resuming: {len(processed)} already processed, "
                  f"{len(results)} results so far", file=sys.stderr)
            return processed, results
        except Exception as e:
            print(f"[checkpoint] Failed to load checkpoint: {e}", file=sys.stderr)
    return set(), []


def _save_checkpoint(processed_asins, results, scan_id=None):
    """Save checkpoint after each product verification."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    cp = _checkpoint_path(scan_id)
    data = {
        "processed_asins": list(processed_asins),
        "results": results,
        "updated_at": datetime.now().isoformat(),
    }
    cp.write_text(json.dumps(data, indent=2, default=str))


def _clear_checkpoint(scan_id=None):
    """Remove checkpoint file after successful completion."""
    cp = _checkpoint_path(scan_id)
    if cp.exists():
        cp.unlink()
        print(f"[checkpoint] Cleared checkpoint file", file=sys.stderr)


# ── Lazy imports (avoid loading Playwright/Keepa unless needed) ──────────────

_keepa_client = None
_pw_context = None


def _get_keepa():
    """Lazy-init KeepaClient."""
    global _keepa_client
    if _keepa_client is None:
        from keepa_client import KeepaClient
        _keepa_client = KeepaClient(tier="pro")
    return _keepa_client


STEALTH_JS = '''
// Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
delete navigator.__proto__.webdriver;

// Realistic language/plugins
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
            {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
        ];
        plugins.length = 3;
        return plugins;
    }
});

// Chrome runtime
window.chrome = {runtime: {}, loadTimes: function(){return {}}, csi: function(){return {}}};

// Permissions API spoof
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : originalQuery(parameters);

// WebGL vendor/renderer (avoid "Google Inc." which flags headless)
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.apply(this, arguments);
};

// Canvas fingerprint noise
const toBlob = HTMLCanvasElement.prototype.toBlob;
const toDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toBlob = function() {
    const context = this.getContext('2d');
    if (context) {
        const shift = {r: Math.floor(Math.random() * 2) - 1, g: Math.floor(Math.random() * 2) - 1, b: 0};
        const imageData = context.getImageData(0, 0, this.width, this.height);
        for (let i = 0; i < imageData.data.length; i += 4) {
            imageData.data[i] += shift.r;
            imageData.data[i+1] += shift.g;
        }
        context.putImageData(imageData, 0, 0);
    }
    return toBlob.apply(this, arguments);
};
'''

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _get_pw_context():
    """Lazy-init shared Playwright browser context with stealth + optional proxy."""
    global _pw_context
    if _pw_context is None:
        from playwright.sync_api import sync_playwright

        # Proxy rotation — only use paid proxies, skip free (they cause timeouts)
        proxy_config = None
        try:
            from proxy_manager import get_proxy_manager
            pm = get_proxy_manager()
            if pm.provider in ("smartproxy", "brightdata"):
                proxy_config = pm.next()
                if proxy_config:
                    print(f"[source] Proxy: {pm.provider}", file=sys.stderr)
            else:
                print(f"[source] Direct connection (no proxy)", file=sys.stderr)
        except Exception:
            pass

        pw = sync_playwright().start()
        launch_kwargs = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        }
        if proxy_config:
            launch_kwargs["proxy"] = proxy_config
        browser = pw.chromium.launch(**launch_kwargs)
        _pw_context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            color_scheme="light",
        )
        _pw_context.add_init_script(STEALTH_JS)
    return _pw_context


# ── Retailer search (returns real product page URLs) ─────────────────────────

RETAILER_SEARCH = {
    "target": {
        "search_url": "https://www.target.com/s?searchTerm={query}",
        "card_selectors": [
            'a[data-test="product-title"]',
            'a[data-test="@web/ProductCard/title"]',
            'div[data-test="product-card"] a[href*="/p/"]',
            'a[href*="/p/"][href*="-"]',
        ],
        "price_selectors": [
            'span[data-test="current-price"] span',
            'span[data-test="current-price"]',
        ],
        "base_url": "https://www.target.com",
        "no_results": "couldn't find a match",
    },
    "walgreens": {
        "search_url": "https://www.walgreens.com/search/results.jsp?Ntt={query}",
        "card_selectors": [
            '.card a[href*="/store/c/"]',
            'a[href*="/store/c/"][href*="-product"]',
            'a[href*="/store/c/"]',
        ],
        "price_selectors": [
            '[class*="price"]',
            '.product__price',
        ],
        "base_url": "https://www.walgreens.com",
        "no_results": "no results found",
    },
    "hmart": {
        "search_url": "https://www.hmart.com/search?q={query}",
        "card_selectors": [
            'a[href*="/p"]',
            '.product-card a',
            'a.product-link',
        ],
        "price_selectors": [
            '.price',
            '[class*="price"]',
            'span.money',
        ],
        "base_url": "https://www.hmart.com",
        "no_results": "no results",
    },
}


def _extract_price(text):
    """Extract first dollar amount from text."""
    m = re.search(r"\$\s*([\d,]+\.?\d*)", text)
    return float(m.group(1).replace(",", "")) if m else None


def _extract_pack_quantity(title):
    """Extract pack/count from title. Returns int or None."""
    if not title:
        return None
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
        r"(\d+)\s*bags?\b",
        r"(\d+)\s*bars?\b",
        r"(\d+)\s*sheets?\b",
    ]
    for pat in patterns:
        m = re.search(pat, title, re.I)
        if m:
            qty = int(m.group(1))
            if 2 <= qty <= 500:
                return qty
    return None


# ── Size/weight normalization for product matching ────────────────────────

# Conversion factors to normalize everything to ounces (weight) or fl oz (volume)
_SIZE_CONVERSIONS = {
    "oz": 1.0,
    "fl oz": 1.0,
    "ml": 0.033814,     # 1 ml = 0.033814 fl oz
    "l": 33.814,        # 1 L = 33.814 fl oz
    "liter": 33.814,
    "litre": 33.814,
    "lb": 16.0,         # 1 lb = 16 oz
    "lbs": 16.0,
    "pound": 16.0,
    "g": 0.035274,      # 1 g = 0.035274 oz
    "gram": 0.035274,
    "grams": 0.035274,
    "kg": 35.274,       # 1 kg = 35.274 oz
    "kilogram": 35.274,
    "gal": 128.0,       # 1 gal = 128 fl oz
    "gallon": 128.0,
    "qt": 32.0,         # 1 qt = 32 fl oz
    "quart": 32.0,
    "pt": 16.0,         # 1 pint = 16 fl oz
    "pint": 16.0,
}

_SIZE_PATTERNS = [
    # "16 fl oz", "8 fl. oz", "32fl oz"
    (r"(\d+(?:\.\d+)?)\s*fl\.?\s*oz\b", "fl oz"),
    # "16oz", "8 oz" (without "fl" — could be weight or volume, treat as oz)
    (r"(\d+(?:\.\d+)?)\s*oz\b", "oz"),
    # "500ml", "250 ml"
    (r"(\d+(?:\.\d+)?)\s*ml\b", "ml"),
    # "1L", "2 liter", "1.5 litre"
    (r"(\d+(?:\.\d+)?)\s*(?:L|liter|litre)s?\b", "l"),
    # "1 lb", "2 lbs", "5 pound"
    (r"(\d+(?:\.\d+)?)\s*(?:lb|lbs|pound)s?\b", "lb"),
    # "100g", "250 gram"
    (r"(\d+(?:\.\d+)?)\s*(?:g|gram|grams)\b", "g"),
    # "1 kg", "2.5 kilogram"
    (r"(\d+(?:\.\d+)?)\s*(?:kg|kilogram)s?\b", "kg"),
    # "1 gallon", "0.5 gal"
    (r"(\d+(?:\.\d+)?)\s*(?:gal|gallon)s?\b", "gal"),
    # "1 quart", "2 qt"
    (r"(\d+(?:\.\d+)?)\s*(?:qt|quart)s?\b", "qt"),
]


def _extract_product_size(title):
    """Extract product size/weight from title and normalize to ounces.

    Returns (normalized_oz, raw_str) or (None, None).
    Examples:
        "CeraVe Cream 16 oz" → (16.0, "16 oz")
        "Shampoo 500ml"       → (16.907, "500ml")
        "Coffee 1 lb"         → (16.0, "1 lb")
    """
    if not title:
        return None, None

    for pattern, unit_key in _SIZE_PATTERNS:
        m = re.search(pattern, title, re.I)
        if m:
            value = float(m.group(1))
            if value <= 0 or value > 10000:
                continue
            factor = _SIZE_CONVERSIONS.get(unit_key, 1.0)
            normalized = value * factor
            raw = m.group(0).strip()
            return normalized, raw

    return None, None


def _sizes_match(size_a, size_b, tolerance=0.15):
    """Check if two normalized sizes are within tolerance of each other.
    Returns True (match), False (mismatch), or None (can't determine)."""
    if size_a is None or size_b is None:
        return None
    if size_a <= 0 or size_b <= 0:
        return None
    ratio = max(size_a, size_b) / min(size_a, size_b)
    return ratio <= (1.0 + tolerance)


_STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "with", "in", "of", "to", "by",
    "is", "it", "at", "on", "from", "new", "free", "size", "each", "per",
    "all", "one", "two", "-", "&", "|",
}


def compute_match_confidence(retail_title, amazon_title, image_score=None):
    """Score how well a retail result matches the Amazon product (0.0-1.0).

    Factors (when image_score provided, 20% each; otherwise 25% each):
    - Brand match: brand name appears in both titles
    - Core product match: product keywords overlap (excl. brand/pack/size)
    - Pack count match: explicit pack counts match
    - Size/weight match: physical size within 15% tolerance
    - Image match (optional): perceptual hash similarity from image_matcher

    Hard caps:
    - Size mismatch (extractable sizes differ by >15%) → capped at 0.30
    - Pack count mismatch (both have counts, they differ) → capped at 0.30
    """
    if not retail_title or not amazon_title:
        return 0.0

    def _keywords(title):
        words = re.findall(r"[a-z0-9]+", title.lower())
        return {w for w in words if w not in _STOP_WORDS and len(w) > 1}

    retail_kw = _keywords(retail_title)
    amazon_kw = _keywords(amazon_title)

    if not amazon_kw:
        return 0.0

    # ── Brand match (25%) ──
    # Check if first 1-2 words of Amazon title appear in retail title
    amazon_words = amazon_title.lower().split()[:2]
    brand_score = 1.0 if any(w in retail_title.lower() for w in amazon_words if len(w) > 2) else 0.0

    # ── Core product keyword overlap (25%) ──
    # How many Amazon keywords appear in retail title
    overlap = len(retail_kw & amazon_kw)
    keyword_score = min(overlap / max(len(amazon_kw), 1), 1.0)

    # ── Pack count match (25%) ──
    retail_pack = _extract_pack_quantity(retail_title)
    amazon_pack = _extract_pack_quantity(amazon_title)
    pack_mismatch = False
    if retail_pack and amazon_pack:
        pack_score = 1.0 if retail_pack == amazon_pack else 0.0
        pack_mismatch = retail_pack != amazon_pack
    elif retail_pack is None and amazon_pack is None:
        pack_score = 0.4  # Both assumed singles — neutral, not confident
    else:
        pack_score = 0.1  # One has pack info, other doesn't — likely mismatch

    # ── Size/weight match (25%) ──
    retail_size, _ = _extract_product_size(retail_title)
    amazon_size, _ = _extract_product_size(amazon_title)
    size_match_result = _sizes_match(retail_size, amazon_size)
    size_mismatch = False
    if size_match_result is True:
        size_score = 1.0
    elif size_match_result is False:
        size_score = 0.0
        size_mismatch = True
    else:
        # Can't determine — give partial credit
        size_score = 0.5

    # Weight allocation: 5 factors at 20% if image available, else 4 at 25%
    if image_score is not None:
        w = 0.20
        raw_score = (brand_score * w) + (keyword_score * w) + \
                    (pack_score * w) + (size_score * w) + (image_score * w)
    else:
        w = 0.25
        raw_score = (brand_score * w) + (keyword_score * w) + \
                    (pack_score * w) + (size_score * w)

    # Hard caps for definite mismatches
    if size_mismatch:
        return round(min(0.30, raw_score), 2)
    if pack_mismatch:
        return round(min(0.30, raw_score), 2)

    return round(raw_score, 2)


def _shorten_query(title):
    """Shorten title for retail search."""
    title = re.sub(r"\s*-\s*\d+\s*(Pack|Count|Ct|pk|ct).*", "", title, flags=re.I)
    return " ".join(title.split()[:8])


def scrape_hmart_brand(brand_name, max_results=30):
    """Scrape H Mart brand page directly. H Mart has /brand-name pages
    that list all products for a brand with prices.

    Product cards are <a href="/product-slug/p"> elements containing
    the brand name, product title, and prices inline in their text.

    Returns list of dicts with: name, retail_price, buy_url, retailer.
    """
    from bs4 import BeautifulSoup

    # H Mart brand pages are at hmart.com/{brand-slug}
    slug = brand_name.lower().replace(" ", "-").replace("'", "")
    brand_url = f"https://www.hmart.com/{slug}"

    ctx = _get_pw_context()
    page = ctx.new_page()
    results = []

    try:
        print(f"  [hmart] Loading brand page: {brand_url}", file=sys.stderr)
        page.goto(brand_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(5000)

        # Scroll to load lazy content
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)

        soup = BeautifulSoup(page.content(), "html.parser")

        # H Mart product cards: <a href="/product-slug/p"> with inline text like:
        # "-33%HAIOPremium Roasted Seaweed Value Pack (Original+green Laver) 0.15oz(4.25g) 16 Packs$5.99$8.99"
        product_links = soup.select('a[href$="/p"]')
        if not product_links:
            product_links = soup.select('a[href*="/p"]')

        brand_upper = brand_name.upper()
        for link in product_links[:max_results]:
            href = link.get("href", "")
            full_text = link.get_text(strip=True)
            if not full_text or len(full_text) < 5:
                continue

            buy_url = f"https://www.hmart.com{href}" if href.startswith("/") else href

            # Extract product name: strip H Mart inline junk, discount prefixes,
            # category labels, brand name, prices, ratings, buttons
            name = full_text
            # Remove leading category/promo text + discount before brand name
            # e.g. "Weekly Sale-43%HAIOSoy Bean..." → "Soy Bean..."
            # e.g. "RefrigeratedHAIOFresh Knife-cut..." → "Fresh Knife-cut..."
            # e.g. "-33%HAIOPremium..." → "Premium..."
            brand_re = re.escape(brand_name)
            name = re.sub(
                rf"^.*?{brand_re}",
                "",
                name,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            # If brand wasn't found, fall back to simple discount strip
            if name == full_text:
                name = re.sub(r"^-?\d+%", "", name).strip()
            # Remove trailing price/rating/button text
            name = re.sub(r"\$[\d,.]+.*$", "", name).strip()
            name = re.sub(r"★.*$", "", name).strip()
            name = re.sub(r"See price.*$", "", name, flags=re.I).strip()
            name = re.sub(r"Buy Now.*$", "", name, flags=re.I).strip()
            # Prefix brand for clarity
            name = f"{brand_name} {name}" if name else brand_name

            # Extract first price (sale price comes first)
            price = _extract_price(full_text)
            if not price or price < 0.50 or price > 200:
                continue

            results.append({
                "name": name,
                "retail_price": price,
                "buy_url": buy_url,
                "source_url": buy_url,
                "retailer": "H Mart",
            })

    except Exception as e:
        print(f"  [hmart] Error: {e}", file=sys.stderr)
    finally:
        page.close()

    print(f"  [hmart] Found {len(results)} products for '{brand_name}'", file=sys.stderr)
    return results


_UPC_CAPABLE_RETAILERS = {"walmart", "walgreens"}  # Target UPC search confirmed broken


def search_google_shopping(query, max_results=10):
    """Search Google Shopping via SerpAPI. Returns prices from multiple retailers in one call.

    Cost: 1 SerpAPI credit per search (250 free/month).
    """
    import requests as _requests

    api_key = os.environ.get("SERPAPI_KEY", "")
    if not api_key:
        print("  [google_shopping] SERPAPI_KEY not set — skipping", file=sys.stderr)
        return []

    try:
        resp = _requests.get(
            "https://serpapi.com/search",
            params={"engine": "google_shopping", "q": query, "api_key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [google_shopping] SerpAPI error: {e}", file=sys.stderr)
        return []

    results = []
    for item in data.get("shopping_results", [])[:max_results]:
        title = item.get("title", "")
        price_str = item.get("extracted_price") or item.get("price", "")
        try:
            price = float(price_str) if price_str else None
        except (ValueError, TypeError):
            price = _extract_price(str(price_str)) if price_str else None
        if not price or price < 0.50:
            continue

        source = item.get("source", "")
        link = item.get("link", "")
        if not link:
            continue

        confidence = compute_match_confidence(title, query)
        results.append({
            "name": title,
            "retail_price": price,
            "buy_url": link,
            "source_url": link,
            "retailer": source,
            "match_confidence": confidence,
        })

    results = [r for r in results if r.get("match_confidence", 0) >= 0.70]
    results.sort(key=lambda r: r.get("match_confidence", 0), reverse=True)
    return results


def search_walmart_serpapi(query, max_results=10):
    """Search Walmart via SerpAPI (no Playwright needed, bypasses bot detection).

    Requires SERPAPI_KEY in .env.  Free tier: 100 searches/month.
    Returns list of dicts with: name, retail_price, buy_url, retailer.
    """
    import requests as _requests

    api_key = os.environ.get("SERPAPI_KEY", "")
    if not api_key:
        print("  [walmart] SERPAPI_KEY not set — skipping Walmart", file=sys.stderr)
        return []

    try:
        resp = _requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "walmart",
                "query": query,
                "api_key": api_key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [walmart] SerpAPI error: {e}", file=sys.stderr)
        return []

    results = []
    for item in data.get("organic_results", [])[:max_results]:
        title = item.get("title", "")
        price = None
        offer = item.get("primary_offer") or {}
        price = offer.get("offer_price")
        if price is None:
            # Fallback: try to extract from offer_current_price
            price = offer.get("offer_current_price")
        if price is None:
            continue

        try:
            price = float(price)
        except (ValueError, TypeError):
            continue

        product_url = item.get("product_page_url", "")
        if not product_url:
            us_item_id = item.get("us_item_id") or item.get("product_id", "")
            if us_item_id:
                product_url = f"https://www.walmart.com/ip/{us_item_id}"
            else:
                continue  # No buy link = no output

        if not title or price < 0.50 or price > 500:
            continue

        confidence = compute_match_confidence(title, query)
        results.append({
            "name": title,
            "retail_price": price,
            "buy_url": product_url,
            "source_url": product_url,
            "retailer": "Walmart",
            "match_confidence": confidence,
        })

    # Filter low confidence and sort best-first
    MIN_CONFIDENCE = 0.70
    results = [r for r in results if r.get("match_confidence", 0) >= MIN_CONFIDENCE]
    results.sort(key=lambda r: r.get("match_confidence", 0), reverse=True)
    return results


def search_retailer(retailer_key, query, max_results=10, upc=None):
    """Search a retailer for products matching query.

    Returns list of dicts with: name, retail_price, buy_url, retailer.
    Uses Playwright + BeautifulSoup to extract real product page URLs.
    For H Mart brand searches, uses the dedicated brand page scraper.
    For Walmart, uses SerpAPI (bypasses bot detection).

    If upc is provided and the retailer supports it, tries UPC search first
    (exact match), then falls back to title search.
    """
    from bs4 import BeautifulSoup

    # UPC-first: try exact barcode search before title (walmart, walgreens only)
    if upc and retailer_key in _UPC_CAPABLE_RETAILERS:
        print(f"  [{retailer_key}] Trying UPC search: {upc}", file=sys.stderr)
        upc_results = _search_retailer_inner(retailer_key, upc, max_results, BeautifulSoup)
        if upc_results:
            print(f"  [{retailer_key}] UPC match found! ({len(upc_results)} results)",
                  file=sys.stderr)
            # Mark as UPC-matched (higher confidence)
            for r in upc_results:
                r["match_method"] = "upc"
                r["match_confidence"] = max(r.get("match_confidence", 0), 0.85)
            return upc_results
        print(f"  [{retailer_key}] UPC search empty, falling back to title",
              file=sys.stderr)

    return _search_retailer_inner(retailer_key, query, max_results, BeautifulSoup)


def _search_retailer_inner(retailer_key, query, max_results, BeautifulSoup):
    """Core retailer search logic (called by search_retailer)."""

    # H Mart: use dedicated brand page scraper for better results
    if retailer_key == "hmart":
        return scrape_hmart_brand(query, max_results=max_results)

    # Walmart: use SerpAPI (Playwright is blocked by bot detection)
    if retailer_key == "walmart":
        return search_walmart_serpapi(query, max_results=max_results)

    config = RETAILER_SEARCH.get(retailer_key)
    if not config:
        # Dynamic lookup from retailer_registry (231 retailers)
        try:
            from retailer_registry import get_retailer
            reg = get_retailer(retailer_key)
            if reg and reg.get("search_url"):
                config = {
                    "search_url": reg["search_url"],
                    "card_selectors": reg.get("card_selectors", ['a[href*="/p"]', '.product-card a']),
                    "price_selectors": reg.get("price_selectors", ['[class*="price"]', '.price']),
                    "base_url": reg.get("base_url", ""),
                    "no_results": reg.get("no_results", ""),
                }
        except Exception:
            pass
    if not config:
        print(f"  [source] Unknown retailer: {retailer_key}", file=sys.stderr)
        return []

    ctx = _get_pw_context()
    page = ctx.new_page()
    results = []

    try:
        search_url = config["search_url"].format(query=quote_plus(query))
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        # Wait for product cards to render (JS-heavy SPAs need extra time)
        try:
            for sel in config["card_selectors"]:
                try:
                    page.wait_for_selector(sel, timeout=8000)
                    break
                except Exception:
                    continue
        except Exception:
            pass
        page.wait_for_timeout(2000)  # Extra buffer for lazy-loaded content

        soup = BeautifulSoup(page.content(), "html.parser")
        body_text = soup.get_text(" ", strip=True).lower()

        if config.get("no_results") and config["no_results"] in body_text:
            return []

        # Find all product cards
        cards_found = []
        for selector in config["card_selectors"]:
            cards_found = soup.select(selector)
            if cards_found:
                break

        if not cards_found:
            # Fallback: try to find any link with a price nearby
            return []

        base_url = config["base_url"]
        for card in cards_found[:max_results]:
            href = card.get("href", "")
            product_url = f"{base_url}{href}" if href.startswith("/") else (href or search_url)
            card_text = card.get_text(strip=True)

            # Find price near this card
            price = None
            # Walk up ancestor chain to find a container with price info
            # Some sites (Target) nest cards deep — need to go up 6+ levels
            ancestor = card
            for _ in range(8):
                ancestor = ancestor.parent if ancestor else None
                if not ancestor:
                    break
                for sel in config["price_selectors"]:
                    price_el = ancestor.select_one(sel)
                    if price_el:
                        price = _extract_price(price_el.get_text())
                        if price:
                            break
                if price:
                    break

            # Fallback: try price selectors on card itself
            if not price:
                for sel in config["price_selectors"]:
                    price_el = soup.select_one(sel)
                    if price_el:
                        price = _extract_price(price_el.get_text())
                        if price and 0.50 < price < 500:
                            break

            if price and 0.50 < price < 500 and card_text:
                confidence = compute_match_confidence(card_text, query)
                results.append({
                    "name": card_text,
                    "retail_price": price,
                    "buy_url": product_url,
                    "source_url": product_url,
                    "retailer": retailer_key.title(),
                    "match_confidence": confidence,
                })

    except Exception as e:
        print(f"  [source] Error searching {retailer_key}: {e}", file=sys.stderr)
    finally:
        page.close()

    # Sort by confidence (best first) — don't filter here since brand/category
    # modes apply their own filters (brand name check, Amazon match, etc.)
    # Filtering at 0.70 here was dropping valid products when the search query
    # is short (e.g. a brand name) vs a full product title.
    results.sort(key=lambda r: r.get("match_confidence", 0), reverse=True)
    return results


# ── Amazon verification (Keepa) ─────────────────────────────────────────────

def verify_on_amazon(candidates, max_verify=20, deep_verify=5, min_profit=2.0):
    """Zero-token-first verification pipeline.

    Phase B: Keepa search for top candidates (1 token each)
    Phase C: Deep verify top hits with offers (21 tokens each) — optional

    Returns list of verified results with profitability data.
    Supports checkpoint/resume via global _resume_mode flag.
    """
    from calculate_fba_profitability import calculate_product_profitability
    from auto_ungated_brands import is_auto_ungated

    keepa = _get_keepa()
    verified = []
    seen_asins = set()
    tokens_used = 0

    # Checkpoint/resume support
    processed_names = set()
    if _resume_mode:
        processed_names_set, prior_results = _load_checkpoint()
        if prior_results:
            verified = prior_results
            seen_asins = {r.get("asin", "") for r in prior_results if r.get("asin")}
            processed_names = processed_names_set

    print(f"\n[verify] Phase B: Quick-verifying {min(len(candidates), max_verify)} "
          f"candidates on Amazon (1 token each)...", file=sys.stderr)

    for i, cand in enumerate(candidates[:max_verify]):
        name = cand.get("name", "")
        retail_price = cand.get("retail_price", 0)

        # Skip already-processed candidates on resume
        if name in processed_names:
            print(f"  [{i+1}/{min(len(candidates), max_verify)}] "
                  f"SKIP (resumed) | {name[:50]}", file=sys.stderr)
            continue

        print(f"  [{i+1}/{min(len(candidates), max_verify)}] "
              f"${retail_price:.2f} | {name[:50]}", file=sys.stderr)

        # Search Keepa for this product (1 token)
        product = keepa.search_product(name)
        tokens_used += 1

        # Mark as processed for checkpoint (whether it matches or not)
        processed_names.add(name)

        if not product:
            print(f"    → No Amazon match", file=sys.stderr)
            continue

        # Deduplicate by ASIN — skip if we already verified this listing
        asin = product.get("asin", "")
        if asin and asin in seen_asins:
            print(f"    → SKIP: Duplicate ASIN {asin} (already verified)", file=sys.stderr)
            continue
        if asin:
            seen_asins.add(asin)

        sell_price = product.get("sell_price")
        if not sell_price:
            print(f"    → No Amazon price", file=sys.stderr)
            continue

        # Pack-size mismatch detection: if Amazon price is 3x+ retail,
        # it's almost certainly a multi-pack listing vs single unit retail.
        # Flag it but don't auto-skip — let the pack_info check handle it.
        price_ratio = sell_price / retail_price if retail_price > 0 else 0
        likely_pack_mismatch = price_ratio >= 3.0

        if likely_pack_mismatch:
            # Estimate how many units the Amazon pack likely contains
            est_pack = round(price_ratio)
            true_cost = retail_price * est_pack
            true_profit = sell_price - true_cost - (true_cost * 0.15 + 4.0)
            if true_profit < min_profit:
                print(f"    → SKIP: Pack mismatch kills profit — need {est_pack}x units "
                      f"(${true_cost:.2f} true cost, ${true_profit:.2f} profit)",
                      file=sys.stderr)
                continue

        # Quick margin check (rough estimate)
        estimated_fees = retail_price * 0.15 + 4.0
        estimated_profit = sell_price - retail_price - estimated_fees
        if estimated_profit < min_profit:
            print(f"    → Low margin: ~${estimated_profit:.2f} est. profit", file=sys.stderr)
            continue

        # PL filter: only skip DEFINITIVE private label (offers-verified)
        # CSV-based PL signals are unreliable — let "possible"/"strong" through
        pl = product.get("private_label", {})
        if isinstance(pl, dict) and pl.get("is_private_label") and pl.get("confidence") == "definitive":
            print(f"    → SKIP: Confirmed private label ({pl.get('reason', '')})", file=sys.stderr)
            continue

        # Hard filter: Amazon on listing (nuanced)
        amazon_on = product.get("amazon_on_listing", False)
        if amazon_on:
            amz_price = product.get("amazon_price")
            bb_price = product.get("buy_box_price") or sell_price
            if amz_price and bb_price and amz_price > bb_price * 1.15:
                print(f"    → Amazon on listing but priced above Buy Box — OK", file=sys.stderr)
            else:
                print(f"    → SKIP: Amazon is on this listing", file=sys.stderr)
                continue

        # Hard filter: <2 FBA sellers
        fba_count = product.get("fba_seller_count")
        if fba_count is not None and fba_count < 2:
            print(f"    → SKIP: Only {fba_count} FBA seller(s)", file=sys.stderr)
            continue

        # Pack size comparison
        amazon_title = product.get("title", "")
        retail_pack = _extract_pack_quantity(name)
        amazon_pack = _extract_pack_quantity(amazon_title)
        pack_match = (retail_pack == amazon_pack) if (retail_pack and amazon_pack) else None

        # Brand hard gate: Amazon brand must appear somewhere in the retail title
        amazon_brand = product.get("brand", "").lower().strip()
        retail_title_lower = name.lower()
        if amazon_brand and len(amazon_brand) > 2:
            brand_words = [w for w in amazon_brand.split() if len(w) > 2]
            if brand_words and not any(w in retail_title_lower for w in brand_words):
                print(f"    → SKIP brand mismatch: Amazon brand '{amazon_brand}' not in retail title '{name[:60]}'",
                      file=sys.stderr)
                continue

        # Compute match confidence between retail name and Amazon title
        retail_amazon_confidence = compute_match_confidence(name, amazon_title)
        if retail_amazon_confidence < 0.70:
            print(f"    → SKIP: Low match confidence ({retail_amazon_confidence:.0%}) "
                  f"retail≠amazon", file=sys.stderr)
            continue

        # Calculate full profitability
        product_data = {
            "name": name,
            "retail_price": retail_price,
            "retailer": cand.get("retailer", ""),
            "upc": product.get("upc", ""),
            "amazon": {
                "asin": product.get("asin", ""),
                "title": amazon_title,
                "amazon_price": sell_price,
                "sales_rank": product.get("bsr"),
                "category": product.get("category", ""),
                "fba_seller_count": fba_count or 0,
                "amazon_on_listing": amazon_on,
                "amazon_direct_price": product.get("amazon_price"),
                "buy_box_price": product.get("buy_box_price"),
                "private_label": pl,
                "match_confidence": retail_amazon_confidence,
                "match_method": "title_search",
                "review_count": product.get("review_count"),
            },
        }

        try:
            prof = calculate_product_profitability(product_data, auto_cashback=True)
        except Exception as e:
            print(f"    → Profitability calc error: {e}", file=sys.stderr)
            continue

        verdict = prof.get("verdict", "SKIP")
        profit = prof.get("profit_per_unit", 0)
        roi = prof.get("roi_percent", 0)

        if verdict == "SKIP":
            reason = prof.get("skip_reason", "")
            print(f"    → SKIP: {reason}", file=sys.stderr)
            continue

        print(f"    → {verdict}: ${profit:.2f} profit, {roi:.0f}% ROI", file=sys.stderr)

        brand = product.get("brand", "")
        ungated = is_auto_ungated(brand)
        if ungated:
            print(f"    ✓ Auto-ungated brand: {brand}", file=sys.stderr)

        # Match confidence from initial retailer search
        cand_conf = cand.get("match_confidence", 0.5)
        cand_method = cand.get("match_method", "title")
        # Also factor in retail→amazon title match
        combined_conf = min(cand_conf, retail_amazon_confidence)

        verified.append({
            # Standardized output fields (Sabbo's requested format)
            "asin": product.get("asin", ""),
            "amazon_title": amazon_title,
            "amazon_price": sell_price,
            "source_retailer": cand.get("retailer", ""),
            "source_url": cand.get("buy_url", ""),
            "buy_cost": retail_price,
            "estimated_profit": profit,
            "estimated_roi": roi,
            "match_method": cand_method,
            "match_confidence": combined_conf,
            "verdict": verdict,
            # Additional fields
            "name": name,
            "retail_price": retail_price,
            "amazon_url": f"https://www.amazon.com/dp/{product.get('asin', '')}",
            "bsr": product.get("bsr"),
            "bsr_drops_30d": product.get("bsr_drops_30d", 0),
            "bsr_drops_60d": product.get("bsr_drops_60d", 0),
            "bsr_drops_90d": product.get("bsr_drops_90d", 0),
            "category": product.get("category", ""),
            "brand": brand,
            "auto_ungated": ungated,
            "profitability": prof,
            "pack_info": {
                "retail_title": name,
                "amazon_title": amazon_title,
                "retail_pack": retail_pack,
                "amazon_pack": amazon_pack,
                "match": pack_match,
                "verified": False,
                "warning": "Verify pack sizes with Amazon Seller App"
                           if pack_match is not True else None,
            },
        })

        # Save checkpoint after each successful verification
        processed_names.add(name)
        _save_checkpoint(processed_names, verified)

        time.sleep(3.0)  # Keepa Pro rate limit

    print(f"\n[verify] Phase B complete: {len(verified)} verified hits "
          f"({tokens_used} tokens used)", file=sys.stderr)

    # Phase C: Deep verify top hits (optional, expensive)
    if deep_verify > 0 and verified:
        _deep_verify_results(verified[:deep_verify], keepa)

    # Clear checkpoint on successful completion
    _clear_checkpoint()

    return verified


def _deep_verify_results(results, keepa):
    """Phase C: Deep verify with offers data (21 tokens each).
    Updates results in-place with definitive seller/PL info."""
    print(f"\n[verify] Phase C: Deep-verifying top {len(results)} hits "
          f"(21 tokens each)...", file=sys.stderr)

    for r in results:
        asin = r.get("asin")
        if not asin:
            continue

        print(f"  Deep-verifying {asin}: {r['name'][:40]}", file=sys.stderr)

        try:
            product = keepa.get_product(asin, offers=20)
            if not product:
                continue

            # Update seller count from offers data
            offers = product.get("offers", [])
            fba_sellers = [o for o in offers if o.get("is_fba")]
            r["fba_seller_count_verified"] = len(fba_sellers)

            # Check for Amazon as seller in offers
            amazon_seller = any(
                "amazon" in (o.get("seller_name", "") or "").lower()
                for o in offers
            )
            if amazon_seller:
                r["amazon_on_listing_verified"] = True
                print(f"    → WARNING: Amazon confirmed as seller in offers data",
                      file=sys.stderr)

            # Definitive PL check from offers
            brand = r.get("brand", "")
            if brand and offers:
                seller_names = [o.get("seller_name", "") for o in offers if o.get("is_fba")]
                brand_is_only_seller = all(
                    brand.lower() in (s or "").lower() for s in seller_names
                ) if seller_names else False
                if brand_is_only_seller:
                    r["private_label_verified"] = True
                    print(f"    → WARNING: Brand is only FBA seller — likely PL",
                          file=sys.stderr)

            print(f"    → {len(fba_sellers)} FBA sellers confirmed", file=sys.stderr)

        except Exception as e:
            print(f"    → Deep verify error: {e}", file=sys.stderr)

        time.sleep(3.0)


# ── Mode: Brand Search ───────────────────────────────────────────────────────

def mode_brand(brand_name, retailers, max_results=20, min_profit=2.0,
               deep_verify=5):
    """Search retailers for a specific brand, then verify on Amazon."""
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[source] BRAND MODE: '{brand_name}'", file=sys.stderr)
    print(f"[source] Retailers: {', '.join(retailers)}", file=sys.stderr)
    print(f"[source] Min profit: ${min_profit:.2f}/unit", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    # Phase A: FREE — search retailers via Playwright
    all_products = []
    for retailer in retailers:
        print(f"[source] Searching {retailer} for '{brand_name}'...", file=sys.stderr)
        products = search_retailer(retailer, brand_name, max_results=max_results)

        # Filter: keep only products with brand name in title
        # Skip brand filter for retailers with dedicated brand pages (e.g. H Mart)
        # — the page itself is the brand, titles may not repeat the brand name
        BRAND_PAGE_RETAILERS = {"hmart"}
        if retailer in BRAND_PAGE_RETAILERS:
            brand_products = products
        else:
            # Normalize brand name for matching — strip punctuation so
            # "Dr Bronners" matches "Dr. Bronner's" in product titles
            brand_norm = re.sub(r"[^a-z0-9 ]", "", brand_name.lower())
            brand_products = [
                p for p in products
                if brand_norm in re.sub(r"[^a-z0-9 ]", "", p["name"].lower())
            ]

        print(f"  → Found {len(products)} products, {len(brand_products)} match brand",
              file=sys.stderr)
        all_products.extend(brand_products)

    if not all_products:
        print(f"\n[source] No products found for '{brand_name}'", file=sys.stderr)
        return []

    # Sort by price ascending (cheapest first = best arbitrage potential)
    all_products.sort(key=lambda x: x["retail_price"])

    # Phase B+C: Verify on Amazon
    verified = verify_on_amazon(
        all_products, max_verify=min(len(all_products), max_results),
        deep_verify=deep_verify, min_profit=min_profit,
    )

    return verified


# ── Mode: Brands List (student-confirmed ungated brands) ─────────────────────

def mode_brands(retailers=None, max_tier=3, max_per_brand=10, min_profit=2.0,
                deep_verify=3, brand_filter=None):
    """Scan retailers for deals across all student-confirmed ungated brands.

    Loops through student_ungated_brands.py (50+ brands mined from Discord),
    runs mode_brand for each, and returns all profitable hits sorted by ROI.

    Args:
        max_tier:       Max brand tier to include (1=Sabbo-posted, 2=+leads, 3=all)
        max_per_brand:  Max products to check per brand (keep low to save Keepa tokens)
        brand_filter:   Optional list of brand names to restrict scan to
    """
    from student_ungated_brands import get_all_brands  # type: ignore[import]

    if retailers is None:
        retailers = ["target", "walgreens", "walmart"]

    brands = get_all_brands(max_tier=max_tier)
    if brand_filter:
        filter_lower = {b.lower() for b in brand_filter}
        brands = [b for b in brands if b.lower() in filter_lower]

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[source] BRANDS MODE: {len(brands)} brands (tier 1–{max_tier})", file=sys.stderr)
    print(f"  Retailers: {', '.join(retailers)}", file=sys.stderr)
    print(f"  Max per brand: {max_per_brand} | Min profit: ${min_profit:.2f}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    all_results = []
    for i, brand in enumerate(brands, 1):
        print(f"\n[brands {i}/{len(brands)}] {brand}", file=sys.stderr)
        try:
            hits = mode_brand(brand, retailers, max_results=max_per_brand,
                              min_profit=min_profit, deep_verify=deep_verify)
            if hits:
                all_results.extend(hits)
                print(f"  → {len(hits)} hit(s)", file=sys.stderr)
            else:
                print(f"  → No hits", file=sys.stderr)
        except Exception as e:
            print(f"  → Error: {e}", file=sys.stderr)

    # Deduplicate by ASIN, sort by ROI descending
    seen = set()
    unique = []
    for r in all_results:
        if r.get("asin") not in seen:
            seen.add(r.get("asin"))
            unique.append(r)

    unique.sort(key=lambda x: x.get("profitability", {}).get("roi_percent", 0), reverse=True)
    print(f"\n[brands] Done. {len(unique)} unique profitable products across {len(brands)} brands",
          file=sys.stderr)
    return unique


# ── Mode: Category Browse ────────────────────────────────────────────────────

def mode_category(category, subcategory=None, retailers=None, max_results=20,
                  min_profit=2.0, deep_verify=5):
    """Browse a category. Zero-token-first: retailer clearance → Keepa verify."""
    if retailers is None:
        retailers = ["target", "walgreens"]

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[source] CATEGORY MODE: '{category}'", file=sys.stderr)
    if subcategory:
        print(f"[source] Subcategory: '{subcategory}'", file=sys.stderr)
    print(f"[source] Retailers: {', '.join(retailers)}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    # Phase A: FREE — scan retailer clearance pages
    all_products = []

    # Try clearance scan via deal_scanner
    try:
        from deal_scanner import fetch_retailer_clearance
        print(f"[source] Scanning clearance pages...", file=sys.stderr)
        clearance = fetch_retailer_clearance(
            retailers=retailers, categories=[category],
            max_per_retailer=max_results,
        )
        for deal in clearance:
            deal_url = deal.get("url", "")
            all_products.append({
                "name": deal.get("name", deal.get("title", "")),
                "retail_price": deal.get("sale_price") or deal.get("price", 0),
                "buy_url": deal_url,
                "source_url": deal_url,
                "retailer": deal.get("retailer", ""),
            })
        print(f"  → {len(clearance)} clearance products found", file=sys.stderr)
    except Exception as e:
        print(f"  [clearance] Error: {e}", file=sys.stderr)

    # Also search by category keyword
    search_query = f"{subcategory} {category}" if subcategory else category
    for retailer in retailers:
        print(f"[source] Searching {retailer} for '{search_query}'...", file=sys.stderr)
        products = search_retailer(retailer, search_query, max_results=max_results)
        all_products.extend(products)
        print(f"  → {len(products)} products found", file=sys.stderr)

    if not all_products:
        print(f"\n[source] No products found for category '{category}'", file=sys.stderr)
        return []

    # Deduplicate by name similarity
    seen_names = set()
    unique = []
    for p in all_products:
        key = p["name"].lower()[:30]
        if key not in seen_names:
            seen_names.add(key)
            unique.append(p)
    all_products = unique

    # Sort by price (cheapest first)
    all_products.sort(key=lambda x: x["retail_price"])

    # Phase B+C: Verify on Amazon
    verified = verify_on_amazon(
        all_products, max_verify=min(len(all_products), max_results),
        deep_verify=deep_verify, min_profit=min_profit,
    )

    return verified


# ── Mode: Retailer Scan ──────────────────────────────────────────────────────

def mode_retailer(retailer_key, section="clearance", brand_filter=None,
                  max_results=20, min_profit=2.0, deep_verify=5):
    """Scan a retailer's clearance/sale pages."""
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[source] RETAILER MODE: {retailer_key} ({section})", file=sys.stderr)
    if brand_filter:
        print(f"[source] Brand filter: '{brand_filter}'", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    all_products = []

    # Try clearance scan
    if section == "clearance":
        try:
            from deal_scanner import fetch_retailer_clearance
            clearance = fetch_retailer_clearance(
                retailers=[retailer_key], max_per_retailer=max_results * 2,
            )
            for deal in clearance:
                deal_url = deal.get("url", "")
                all_products.append({
                    "name": deal.get("name", deal.get("title", "")),
                    "retail_price": deal.get("sale_price") or deal.get("price", 0),
                    "buy_url": deal_url,
                    "source_url": deal_url,
                    "retailer": deal.get("retailer", retailer_key.title()),
                })
            print(f"  → {len(clearance)} clearance products", file=sys.stderr)
        except Exception as e:
            print(f"  [clearance] Error: {e}", file=sys.stderr)

    # Also do a general search if section is "all" or clearance yielded few results
    if section != "clearance" or len(all_products) < 5:
        query = brand_filter or "deals"
        products = search_retailer(retailer_key, query, max_results=max_results)
        all_products.extend(products)

    # Apply brand filter if specified
    if brand_filter:
        brand_lower = brand_filter.lower()
        all_products = [p for p in all_products if brand_lower in p["name"].lower()]

    if not all_products:
        print(f"\n[source] No products found", file=sys.stderr)
        return []

    all_products.sort(key=lambda x: x["retail_price"])

    verified = verify_on_amazon(
        all_products, max_verify=min(len(all_products), max_results),
        deep_verify=deep_verify, min_profit=min_profit,
    )

    return verified


# ── Mode: Full Scan ──────────────────────────────────────────────────────────

def mode_scan(sources="all", retailers=None, count=20, min_profit=2.0,
              deep_verify=5):
    """Multi-source scan. Wraps deal_scanner with better filters."""
    if retailers is None:
        retailers = ["target", "walgreens"]

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[source] SCAN MODE: sources={sources}", file=sys.stderr)
    print(f"[source] Retailers: {', '.join(retailers)}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    all_products = []

    # Clearance pages (FREE)
    if sources in ("all", "clearance"):
        try:
            from deal_scanner import fetch_retailer_clearance
            clearance = fetch_retailer_clearance(
                retailers=retailers, max_per_retailer=count,
            )
            for deal in clearance:
                all_products.append({
                    "name": deal.get("name", deal.get("title", "")),
                    "retail_price": deal.get("sale_price") or deal.get("price", 0),
                    "buy_url": deal.get("url", ""),
                    "retailer": deal.get("retailer", ""),
                })
            print(f"  → {len(clearance)} clearance products", file=sys.stderr)
        except Exception as e:
            print(f"  [clearance] Error: {e}", file=sys.stderr)

    # Hip2Save deals (FREE)
    if sources in ("all", "hip2save"):
        try:
            from deal_scanner import fetch_hip2save_deals
            deals = fetch_hip2save_deals()
            for deal in deals[:count]:
                if deal.get("price"):
                    deal_url = deal.get("url", "")
                    all_products.append({
                        "name": deal.get("title", ""),
                        "retail_price": deal["price"],
                        "buy_url": deal_url,
                        "source_url": deal_url,
                        "retailer": deal.get("retailer", "Hip2Save"),
                    })
            print(f"  → {len(deals)} Hip2Save deals", file=sys.stderr)
        except Exception as e:
            print(f"  [hip2save] Error: {e}", file=sys.stderr)

    if not all_products:
        print(f"\n[source] No products found from any source", file=sys.stderr)
        return []

    # Deduplicate
    seen = set()
    unique = []
    for p in all_products:
        key = p["name"].lower()[:30]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    unique.sort(key=lambda x: x["retail_price"])

    verified = verify_on_amazon(
        unique, max_verify=min(len(unique), count),
        deep_verify=deep_verify, min_profit=min_profit,
    )

    return verified


# ── Mode: Single ASIN ────────────────────────────────────────────────────────

def mode_asin(asin, retailers=None, min_profit=2.0):
    """Reverse-source a single ASIN across retailers."""
    if retailers is None:
        retailers = ["target", "walgreens", "walmart"]

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[source] ASIN MODE: {asin}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    # Get product info from Keepa (1 token)
    keepa = _get_keepa()
    product = keepa.get_product(asin)
    if not product:
        print(f"[source] Could not find ASIN {asin} on Keepa", file=sys.stderr)
        return []

    title = product.get("title", "")
    sell_price = product.get("sell_price")
    if not sell_price:
        print(f"[source] No Amazon price for {asin}", file=sys.stderr)
        return []

    print(f"  Amazon: {title[:60]}", file=sys.stderr)
    print(f"  Price: ${sell_price:.2f}", file=sys.stderr)

    # Search retailers (UPC-first when available)
    query = _shorten_query(title)
    upc = product.get("upc", "") or ""
    if upc:
        print(f"  UPC: {upc}", file=sys.stderr)
    all_retail = []
    for retailer in retailers:
        print(f"  Searching {retailer}...", file=sys.stderr)
        results = search_retailer(retailer, query, max_results=5, upc=upc)
        all_retail.extend(results)

    if not all_retail:
        print(f"\n[source] No retail matches found for '{title[:40]}'", file=sys.stderr)
        return []

    # Build candidates with known Amazon data
    from calculate_fba_profitability import calculate_product_profitability
    from auto_ungated_brands import is_auto_ungated

    verified = []
    for retail in all_retail:
        retail_price = retail["retail_price"]
        if retail_price >= sell_price:
            continue

        # Hard gate: Amazon brand must appear in retail title
        asin_brand_check = str(product.get("brand") or "").lower().strip()
        retail_name_lower = str(retail.get("name") or "").lower()
        if asin_brand_check and len(asin_brand_check) > 2:
            brand_words = asin_brand_check.split()
            brand_present = any(w in retail_name_lower for w in brand_words if len(w) > 2)
            if not brand_present:
                print(f"    → SKIP: Brand '{asin_brand_check}' not in retail title",
                      file=sys.stderr)
                continue

        # Compute actual match confidence — threshold raised from 0.4 → 0.70
        confidence = compute_match_confidence(retail["name"], title)
        if confidence < 0.70:
            print(f"    → SKIP: Low match ({confidence:.0%}) "
                  f"'{retail['name'][:30]}' vs '{title[:30]}'", file=sys.stderr)
            continue

        product_data = {
            "name": retail["name"],
            "retail_price": retail_price,
            "retailer": retail.get("retailer", ""),
            "amazon": {
                "asin": asin,
                "title": title,
                "amazon_price": sell_price,
                "sales_rank": product.get("bsr"),
                "category": product.get("category", ""),
                "fba_seller_count": product.get("fba_seller_count", 0),
                "amazon_on_listing": product.get("amazon_on_listing", False),
                "amazon_direct_price": product.get("amazon_price"),
                "buy_box_price": product.get("buy_box_price"),
                "private_label": product.get("private_label", {}),
                "match_confidence": confidence,
                "match_method": "title_search",
            },
        }

        try:
            prof = calculate_product_profitability(product_data, auto_cashback=True)
        except Exception as e:
            print(f"    → Error: {e}", file=sys.stderr)
            continue

        if prof.get("verdict") == "SKIP":
            continue

        amazon_title = title
        retail_pack = _extract_pack_quantity(retail["name"])
        amazon_pack = _extract_pack_quantity(amazon_title)
        pack_match = (retail_pack == amazon_pack) if (retail_pack and amazon_pack) else None

        asin_brand = product.get("brand", "")
        retail_buy_url = retail.get("source_url") or retail.get("buy_url", "")
        verified.append({
            "name": retail["name"],
            "asin": asin,
            "retailer": retail.get("retailer", ""),
            "retail_price": retail_price,
            "amazon_price": sell_price,
            "buy_url": retail_buy_url,
            "source_url": retail_buy_url,
            "amazon_url": f"https://www.amazon.com/dp/{asin}",
            "bsr": product.get("bsr"),
            "category": product.get("category", ""),
            "brand": asin_brand,
            "auto_ungated": is_auto_ungated(asin_brand),
            "match_confidence": confidence,
            "match_method": retail.get("match_method", "title"),
            "profitability": prof,
            "pack_info": {
                "retail_title": retail["name"],
                "amazon_title": amazon_title,
                "retail_pack": retail_pack,
                "amazon_pack": amazon_pack,
                "match": pack_match,
                "verified": False,
                "warning": "Verify pack sizes with Amazon Seller App"
                           if pack_match is not True else None,
            },
        })

    return verified


# ── Mode: Batch (pipeline from storefront scanner) ────────────────────────────

def mode_batch(input_file, retailers=None, min_profit=2.0, max_asins=50):
    """Batch-source ASINs from a file. Each ASIN is run through mode_asin.

    Designed for pipeline use:
      seller_storefront_scan.py --output-asins asins.txt
      source.py batch --input asins.txt --retailers target,walgreens,hmart
    """
    if retailers is None:
        retailers = ["target", "walgreens", "hmart"]

    input_path = Path(input_file)
    if not input_path.exists():
        print(f"[batch] File not found: {input_file}", file=sys.stderr)
        return []

    asins = [line.strip() for line in input_path.read_text().splitlines()
             if line.strip() and line.strip().startswith("B")]

    if not asins:
        print(f"[batch] No valid ASINs found in {input_file}", file=sys.stderr)
        return []

    asins = asins[:max_asins]
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[source] BATCH MODE: {len(asins)} ASINs from {input_file}", file=sys.stderr)
    print(f"  Retailers: {', '.join(retailers)}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    all_results = []
    for i, asin in enumerate(asins, 1):
        print(f"\n[batch {i}/{len(asins)}] Processing {asin}...", file=sys.stderr)
        try:
            hits = mode_asin(asin, retailers=retailers, min_profit=min_profit)
            if hits:
                all_results.extend(hits)
                print(f"  → {len(hits)} profitable match(es) found", file=sys.stderr)
            else:
                print(f"  → No profitable matches", file=sys.stderr)
        except Exception as e:
            print(f"  → Error: {e}", file=sys.stderr)

    # Deduplicate by ASIN (same product may appear in multiple storefronts)
    seen = set()
    unique = []
    for r in all_results:
        if r["asin"] not in seen:
            seen.add(r["asin"])
            unique.append(r)

    print(f"\n[batch] Done. {len(unique)} unique profitable products "
          f"(from {len(asins)} ASINs checked)", file=sys.stderr)
    return unique


# ── Mode: Deals (Keepa price drops + RSS feeds) ─────────────────────────────

def mode_deals(source="all", min_drop=15, count=30, min_profit=1.50,
               retailers=None):
    """Find deals via Keepa price drops and/or deal RSS feeds.

    source: "all", "keepa", or "rss"
    """
    if retailers is None:
        retailers = ["target", "walgreens", "walmart"]

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[source] DEALS MODE: source={source}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    all_results = []

    # ── Keepa Deals API (5 tokens per request) ────────────────────────
    if source in ("all", "keepa"):
        try:
            keepa = _get_keepa()
            print(f"[deals] Fetching Keepa price drops (>{min_drop}% drop)...",
                  file=sys.stderr)
            deals = keepa.get_deals(
                price_range=(500, 5000),
                count=min(count, 150),
            )
            print(f"  → {len(deals)} Keepa deals found", file=sys.stderr)

            # Reverse-source each deal at retailers
            for i, deal in enumerate(deals[:count]):
                asin = deal.get("asin", "")
                title = deal.get("title", "")
                amz_price = deal.get("current_price", 0)
                if not asin or amz_price <= 0:
                    continue

                print(f"  [{i+1}] {title[:50]} — ${amz_price:.2f} "
                      f"({deal.get('delta_percent', 0):.0f}% drop)", file=sys.stderr)

                # Search retailers for this product
                query = _shorten_query(title)
                for retailer in retailers:
                    retail_results = search_retailer(retailer, query, max_results=3)
                    for r in retail_results:
                        if r["retail_price"] >= amz_price:
                            continue
                        # Quick margin check
                        est_fees = r["retail_price"] * 0.15 + 3.50
                        est_profit = amz_price - r["retail_price"] - est_fees
                        if est_profit < min_profit:
                            continue

                        r_buy_url = r.get("source_url") or r.get("buy_url", "")
                        all_results.append({
                            "name": r["name"],
                            "asin": asin,
                            "retailer": r.get("retailer", ""),
                            "retail_price": r["retail_price"],
                            "amazon_price": amz_price,
                            "buy_url": r_buy_url,
                            "source_url": r_buy_url,
                            "amazon_url": f"https://www.amazon.com/dp/{asin}",
                            "bsr": deal.get("bsr"),
                            "category": deal.get("category", ""),
                            "brand": "",
                            "auto_ungated": False,
                            "profitability": {
                                "verdict": "MAYBE",
                                "profit_per_unit": round(est_profit, 2),
                                "roi_percent": round(est_profit / r["retail_price"] * 100, 1) if r["retail_price"] > 0 else 0,
                            },
                        })
                        print(f"    → MATCH at {retailer}: ${r['retail_price']:.2f} "
                              f"(~${est_profit:.2f} profit)", file=sys.stderr)
        except Exception as e:
            print(f"  [keepa deals] Error: {e}", file=sys.stderr)

    # ── RSS Deal Feeds (free) ──────────────────────────────────────────
    if source in ("all", "rss"):
        try:
            from deal_feed_scanner import fetch_deals_from_feeds, verify_deals_on_amazon
            print(f"\n[deals] Fetching RSS deal feeds...", file=sys.stderr)
            rss_deals = fetch_deals_from_feeds(max_per_source=count)
            if rss_deals:
                verified = verify_deals_on_amazon(
                    rss_deals, max_verify=min(len(rss_deals), count),
                    min_profit=min_profit,
                )
                all_results.extend(verified)
        except Exception as e:
            print(f"  [rss deals] Error: {e}", file=sys.stderr)

    # Deduplicate by ASIN
    seen = set()
    unique = []
    for r in all_results:
        key = r.get("asin", r.get("name", ""))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"\n[deals] Done. {len(unique)} actionable deals found.", file=sys.stderr)
    return unique


# ── Output formatting ────────────────────────────────────────────────────────

def format_results(results, mode_name=""):
    """Format verified results as readable text — standardized output.

    Output format per Sabbo's request:
    ASIN, Amazon title, Amazon price, source link, buy cost, estimated profit, estimated ROI
    Plus match method/confidence for verification.
    """
    if not results:
        return "No profitable products found matching your criteria.\n"

    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  SOURCING RESULTS — {mode_name}")
    lines.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  {len(results)} actionable products found")
    lines.append(f"{'='*70}\n")

    # Summary table
    lines.append(f"{'#':>2} {'ASIN':<12} {'Amazon Title':<30} {'AMZ$':>6} "
                 f"{'Source':>8} {'Buy$':>6} {'Profit':>7} {'ROI':>5} {'Match':>10}")
    lines.append("─" * 100)

    for i, r in enumerate(results, 1):
        verdict = r.get("verdict") or r.get("profitability", {}).get("verdict") or "?"
        profit = r.get("estimated_profit") or r.get("profitability", {}).get("profit_per_unit", 0) or 0
        roi = r.get("estimated_roi") or r.get("profitability", {}).get("roi_percent", 0) or 0
        amz_price = r.get("amazon_price", 0) or 0
        buy_cost = r.get("buy_cost") or r.get("retail_price", 0) or 0
        retailer = r.get("source_retailer") or r.get("retailer", "")
        title = r.get("amazon_title") or r.get("name", "")
        method = r.get("match_method", "?")
        conf = r.get("match_confidence", 0) or 0
        if conf and conf > 0:
            conf_str = f"{conf * 100:.0f}%"
        else:
            conf_str = "Unverified"
        match_str = f"{'UPC' if method == 'upc' else 'Title'} {conf_str}"

        lines.append(f"{i:>2} {r.get('asin',''):<12} {title[:28]:<30} ${amz_price:>5.2f} "
                     f"{retailer:>8} ${buy_cost:>5.2f} ${profit:>5.2f} {roi:>4.0f}% "
                     f"{match_str:>10} [{verdict}]")

    # Detail section with links
    lines.append(f"\n{'─'*70}")
    lines.append("  DETAIL + LINKS")
    lines.append(f"{'─'*70}")

    for i, r in enumerate(results, 1):
        verdict = r.get("verdict") or r.get("profitability", {}).get("verdict") or "?"
        title = r.get("amazon_title") or r.get("name", "")
        pack = r.get("pack_info", {})

        lines.append(f"\n  #{i}  [{verdict}]  {title[:60]}")
        lines.append(f"  ASIN: {r.get('asin', 'N/A')}")

        if r.get("brand"):
            ungated_tag = " [AUTO-UNGATED]" if r.get("auto_ungated") else ""
            lines.append(f"  Brand: {r['brand']}{ungated_tag}")

        # Pack info
        if pack.get("retail_pack") or pack.get("amazon_pack"):
            rp = pack.get("retail_pack", "?")
            ap = pack.get("amazon_pack", "?")
            match_label = "MATCH" if pack.get("match") else "MISMATCH" if pack.get("match") is False else "UNVERIFIED"
            lines.append(f"  Pack: Retail={rp}, Amazon={ap} [{match_label}]")
        if pack.get("warning"):
            lines.append(f"  Warning: {pack['warning']}")

        # HARD GATE: No buy link = RESEARCH, period
        buy_url = r.get("source_url") or r.get("buy_url", "")
        amz_url = r.get("amazon_url", "N/A")
        if (not buy_url or buy_url == "N/A") and verdict in ("BUY", "MAYBE"):
            r["verdict"] = "RESEARCH"
            r["verdict_note"] = "No verified buy link — find at retail manually"
        if not buy_url or buy_url == "N/A":
            buy_url = "N/A — no retail source found"

        # Links — ALWAYS included (standing directive)
        lines.append(f"  BUY:  {buy_url}")
        lines.append(f"  AMZ:  {amz_url}")

        # Verdict note (verification warnings, mode notes)
        if r.get("verdict_note"):
            lines.append(f"  NOTE: {r['verdict_note']}")

    lines.append(f"\n{'='*70}")
    lines.append(f"  Verify all products in Amazon Seller App before purchasing.")
    lines.append(f"{'='*70}\n")

    return "\n".join(lines)


def save_results(results, mode_name=""):
    """Save results as JSON, formatted text, and to SQLite results DB."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON
    json_path = TMP_DIR / f"{ts}_source_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Formatted text
    text = format_results(results, mode_name)
    text_path = TMP_DIR / f"{ts}_source_results.txt"
    with open(text_path, "w") as f:
        f.write(text)

    # Persist to SQLite for historical queries
    try:
        from results_db import ResultsDB
        db = ResultsDB()
        mode = mode_name.split(":")[0].strip().lower() if ":" in mode_name else mode_name.lower()
        saved = db.save_results(ts, mode, results)
        if saved:
            print(f"[source] Saved {saved} results to history DB", file=sys.stderr)
    except Exception as e:
        print(f"[source] Results DB save error: {e}", file=sys.stderr)

    return json_path, text_path


# ── New Modes (v7.0) ─────────────────────────────────────────────────────────


def mode_oos(count=30, category=0, max_bsr=100000, min_reviews=50,
             min_price=5.0, max_price=50.0, reverse_source=False,
             max_retailers=10):
    """Find out-of-stock Amazon opportunities via Keepa.

    Delegates to oos_opportunity_scanner.py for the heavy lifting.
    Returns results in the standard format for format_results().
    """
    try:
        from oos_opportunity_scanner import scan_oos_opportunities
    except ImportError:
        print("[source] ERROR: oos_opportunity_scanner.py not found", file=sys.stderr)
        return []

    price_range = (int(min_price * 100), int(max_price * 100))

    opportunities = scan_oos_opportunities(
        count=count,
        category=category,
        max_bsr=max_bsr,
        min_reviews=min_reviews,
        price_range=price_range,
        reverse_source=reverse_source,
        max_retailers=max_retailers,
        verbose=True,
    )

    # Convert to standard result format
    results = []
    for opp in opportunities:
        result = {
            "name": opp.get("title", ""),
            "asin": opp.get("asin", ""),
            "amazon_url": opp.get("amazon_url", ""),
            "amazon_price": opp.get("last_known_price"),
            "bsr": opp.get("bsr"),
            "review_count": opp.get("review_count"),
            "category": opp.get("category", ""),
            "verdict": "RESEARCH",
            "verdict_note": "Out of stock on Amazon — find at retail before it restocks",
            "match_method": "OOS_OPPORTUNITY",
            "oos_data": {
                "days_oos": opp.get("days_oos"),
                "last_fba_count": opp.get("last_fba_count"),
                "seller_trend": opp.get("seller_trend"),
            },
            "match_confidence": 1.0,  # Direct Keepa data, high confidence
            "risk_flags": {
                "amazon_on_listing": False,
                "is_gated": None,
                "hazmat_risk": None,
                "ip_risk": None,
            },
        }

        # Add best retail source if reverse-sourced
        if opp.get("retail_sources"):
            best = opp["retail_sources"][0]
            result["retailer"] = best.get("retailer", "")
            result["retail_url"] = best.get("retail_url", "")
            result["buy_cost"] = best.get("buy_cost")
            result["profitability"] = {
                "profit_per_unit": best.get("profit_per_unit", 0),
                "roi_percent": best.get("roi_percent", 0),
                "verdict": "BUY" if best.get("roi_percent", 0) >= 30 else "MAYBE",
            }
            result["all_sources"] = opp["retail_sources"]

        # Enrich with velocity signals from BSR drops and Amazon OOS data
        drops_30d = opp.get("bsr_drops_30d", 0)
        amazon_oos_pct = opp.get("amazon_oos_pct", 0.0)

        if drops_30d > 10 and amazon_oos_pct > 0.3:
            result["oos_opportunity_score"] = "HIGH"
            result["oos_note"] = (
                f"Strong: ~{drops_30d} sales/mo, Amazon OOS {int(amazon_oos_pct * 100)}% of time"
            )
        elif drops_30d > 5:
            result["oos_opportunity_score"] = "MEDIUM"
            result["oos_note"] = f"Moderate: ~{drops_30d} sales/mo"
        else:
            result["oos_opportunity_score"] = "LOW"
            result["oos_note"] = "Low velocity — proceed with caution"

        results.append(result)

    # Sort: HIGH first, then MEDIUM, then LOW; within each tier sort by bsr_drops_30d desc
    _score_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    results.sort(key=lambda x: (
        _score_order.get(x.get("oos_opportunity_score", "LOW"), 2),
        -(x.get("oos_data", {}).get("bsr_drops_30d") or 0),
    ))

    return results


def mode_a2a(a2a_type="warehouse", count=30, asin=None, min_discount=40,
             max_bsr=200000):
    """Amazon-to-Amazon flips: warehouse deals, variation arbitrage, multipack.

    Returns results in the standard format for format_results().
    """
    results = []

    if a2a_type == "warehouse":
        try:
            keepa = _get_keepa()
        except ValueError:
            print("[source] ERROR: KEEPA_API_KEY not set. A2A warehouse requires Keepa Pro.",
                  file=sys.stderr)
            return []

        deals = keepa.get_warehouse_deals(
            max_bsr=max_bsr,
            min_discount_pct=min_discount,
            count=count,
        )

        for deal in deals:
            a2a_asin = deal.get("asin", "")
            results.append({
                "name": deal.get("title", ""),
                "asin": a2a_asin,
                "amazon_url": f"https://www.amazon.com/dp/{a2a_asin}",
                "amazon_price": deal.get("new_price"),
                "buy_cost": deal.get("used_price"),
                "buy_price": deal.get("used_price"),
                "source_url": f"https://www.amazon.com/dp/{a2a_asin}?condition=used",
                "retailer": "Amazon Warehouse",
                "bsr": deal.get("bsr"),
                "category": deal.get("category", ""),
                "verdict": "A2A_WAREHOUSE",
                "match_method": "A2A_WAREHOUSE",
                "match_confidence": 1.0,
                "profitability": {
                    "profit_per_unit": deal.get("potential_profit", 0),
                    "roi_percent": round(
                        (deal["potential_profit"] / deal["used_price"] * 100)
                        if deal.get("used_price") and deal["used_price"] > 0 else 0, 1
                    ),
                    "discount_pct": deal.get("discount_pct", 0),
                },
                "risk_flags": {
                    "condition_risk": True,  # Used/renewed condition uncertainty
                },
            })

    elif a2a_type == "variation" and asin:
        try:
            from variation_analyzer import analyze_variations
            variation_results = analyze_variations(asin)
            if variation_results:
                for var in variation_results:
                    results.append({
                        "name": var.get("title", ""),
                        "asin": var.get("asin", ""),
                        "amazon_url": f"https://www.amazon.com/dp/{var.get('asin', '')}",
                        "amazon_price": var.get("price"),
                        "bsr": var.get("bsr"),
                        "verdict": "A2A_VARIATION",
                        "match_confidence": 1.0,
                        "variation_data": var,
                    })
        except ImportError:
            print("[source] ERROR: variation_analyzer.py not found", file=sys.stderr)
        except Exception as e:
            print(f"[source] Variation analysis failed: {e}", file=sys.stderr)

    elif a2a_type == "multipack":
        # Multipack arbitrage: find multi-pack Amazon listings, then check if
        # buying N singles is cheaper than the multi-pack price. If so, buy
        # singles, bundle them, and sell as the multi-pack listing.
        try:
            keepa = _get_keepa()
        except ValueError:
            print("[source] ERROR: KEEPA_API_KEY not set. Multipack requires Keepa Pro.",
                  file=sys.stderr)
            return []

        print(f"\n[source] A2A MULTIPACK: Searching for multi-pack listings...",
              file=sys.stderr)

        # Step 1: Use Product Finder to find multi-pack listings (title contains pack/count)
        # Focus on Grocery, Health, Beauty where multi-packs are common
        finder_results = keepa.product_finder(
            min_price_drop_pct=10,
            max_bsr=max_bsr,
            price_range=(2000, 10000),  # $20-100 (multi-packs are pricier)
            min_sellers=2,
            max_sellers=10,
            count=min(count * 3, 150),  # Over-fetch to filter
        )

        multipack_candidates = []
        for prod in finder_results:
            title = prod.get("title", "")
            pack_qty = _extract_pack_quantity(title)
            if pack_qty and pack_qty >= 2:
                multipack_candidates.append({
                    **prod,
                    "pack_qty": pack_qty,
                })

        print(f"  → Found {len(multipack_candidates)} multi-pack listings "
              f"(from {len(finder_results)} candidates)", file=sys.stderr)

        # Step 2: For each multi-pack, search for the single version
        for mp in multipack_candidates[:count]:
            title = mp.get("title", "")
            asin_mp = mp.get("asin", "")
            pack_qty = mp["pack_qty"]
            mp_price = mp.get("buy_box_price") or mp.get("amazon_price") or 0

            if not mp_price or mp_price <= 0:
                continue

            # Build single-unit search query: remove pack/count references
            single_query = re.sub(
                r"\b\d+\s*[-\s]?\s*(pack|pk|count|ct)\b", "", title, flags=re.I
            ).strip()
            single_query = " ".join(single_query.split()[:6])  # Keep first 6 words

            if not single_query:
                continue

            print(f"  Checking: {title[:50]} (pack of {pack_qty}, ${mp_price:.2f})",
                  file=sys.stderr)

            # Search for single version on Keepa
            single = keepa.search_product(single_query)
            if not single:
                continue

            single_price = single.get("buy_box_price") or single.get("amazon_price") or 0
            single_asin = single.get("asin", "")

            if not single_price or single_price <= 0 or single_asin == asin_mp:
                continue

            # Calculate arbitrage: cost of N singles vs multi-pack price
            total_singles_cost = single_price * pack_qty
            # Account for FBA fees on the multi-pack
            from calculate_fba_profitability import estimate_fba_fee, get_referral_fee_rate
            referral = mp_price * get_referral_fee_rate(mp.get("category", ""))
            fba_fee = estimate_fba_fee(mp_price)
            total_fees = referral + fba_fee + 1.50  # +$1.50 prep/bundle cost

            profit = mp_price - total_singles_cost - total_fees
            roi = (profit / total_singles_cost * 100) if total_singles_cost > 0 else 0

            if profit > 2.0 and roi > 20:
                results.append({
                    "name": title,
                    "asin": asin_mp,
                    "amazon_url": f"https://www.amazon.com/dp/{asin_mp}",
                    "amazon_title": title,
                    "amazon_price": mp_price,
                    "buy_cost": total_singles_cost,
                    "estimated_profit": round(profit, 2),
                    "estimated_roi": round(roi, 1),
                    "bsr": mp.get("bsr"),
                    "category": mp.get("category", ""),
                    "verdict": "A2A_MULTIPACK",
                    "match_confidence": 1.0,
                    "source_retailer": "Amazon",
                    "source_url": f"https://www.amazon.com/dp/{single_asin}",
                    "profitability": {
                        "profit_per_unit": round(profit, 2),
                        "roi_percent": round(roi, 1),
                        "verdict": "BUY" if roi >= 30 else "MAYBE",
                    },
                    "multipack_data": {
                        "pack_qty": pack_qty,
                        "single_asin": single_asin,
                        "single_price": single_price,
                        "total_singles_cost": round(total_singles_cost, 2),
                        "multipack_price": mp_price,
                        "fees": round(total_fees, 2),
                    },
                })
                print(f"    → ARBITRAGE: Buy {pack_qty}x ${single_price:.2f} = "
                      f"${total_singles_cost:.2f} → Sell as pack ${mp_price:.2f} "
                      f"→ ${profit:.2f} profit ({roi:.0f}% ROI)", file=sys.stderr)

            time.sleep(3.0)  # Keepa rate limit

        print(f"\n[source] Multipack scan complete: {len(results)} opportunities",
              file=sys.stderr)

    return results


def mode_finder(min_drop=30, max_bsr=100000, price_range=(10, 50),
                min_sellers=3, max_sellers=15, category=0, count=50,
                reverse_source=False, retailers=None):
    """Keepa Product Finder: bulk catalog search for arbitrage windows.

    Finds products where price dropped significantly, then optionally
    reverse-sources from retailers.
    """
    try:
        keepa = _get_keepa()
    except ValueError:
        print("[source] ERROR: KEEPA_API_KEY not set. Finder requires Keepa Pro.",
              file=sys.stderr)
        return []

    price_range_cents = (int(price_range[0] * 100), int(price_range[1] * 100))

    products = keepa.product_finder(
        min_price_drop_pct=min_drop,
        max_bsr=max_bsr,
        price_range=price_range_cents,
        min_sellers=min_sellers,
        max_sellers=max_sellers,
        category=category,
        count=count,
    )

    if not products:
        print("[source] Product Finder returned 0 results.", file=sys.stderr)
        return []

    print(f"[source] Product Finder returned {len(products)} candidates.", file=sys.stderr)

    results = []
    for p in products:
        current_price = p.get("sell_price") or p.get("buy_box_price") or p.get("amazon_price")
        avg_90d = (p.get("price_trends") or {}).get("avg_90d")
        drop_pct = round((1 - current_price / avg_90d) * 100, 1) if current_price and avg_90d and avg_90d > 0 else 0

        result = {
            "name": p.get("title", ""),
            "asin": p.get("asin", ""),
            "amazon_url": f"https://www.amazon.com/dp/{p.get('asin', '')}",
            "amazon_price": current_price,
            "bsr": p.get("bsr"),
            "review_count": p.get("review_count"),
            "category": p.get("category", ""),
            "fba_seller_count": p.get("fba_seller_count"),
            "amazon_on_listing": p.get("amazon_on_listing", False),
            "verdict": "RESEARCH",
            "verdict_note": "Price drop detected — find this product at retail to source",
            "match_method": "FINDER_CANDIDATE",
            "match_confidence": 1.0,
            "price_drop_pct": drop_pct,
            "avg_90d_price": avg_90d,
            "price_trends": p.get("price_trends"),
        }
        results.append(result)

    # Reverse-source if requested
    if reverse_source and results and retailers:
        print(f"[source] Reverse-sourcing {len(results)} candidates...", file=sys.stderr)
        for result in results[:20]:  # Cap at 20 to avoid rate limits
            try:
                asin_results = mode_asin(result["asin"], retailers=retailers, min_profit=1.0)
                if asin_results:
                    best = asin_results[0]
                    result["retailer"] = best.get("retailer", "")
                    result["retail_url"] = best.get("retail_url", "")
                    result["buy_cost"] = best.get("buy_cost")
                    result["profitability"] = best.get("profitability", {})
                    if result["profitability"].get("roi_percent", 0) >= 30:
                        result["verdict"] = "BUY"
                    elif result["profitability"].get("roi_percent", 0) >= 20:
                        result["verdict"] = "MAYBE"
            except Exception as e:
                print(f"[source] Reverse-source failed for {result['asin']}: {e}",
                      file=sys.stderr)

    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Unified Amazon FBA sourcing CLI (zero-token-first)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s brand "Jellycat" --retailers target,walgreens
  %(prog)s brand "CeraVe" --retailers target --max 30
  %(prog)s category "toys" --subcategory "plush"
  %(prog)s retailer target --section clearance
  %(prog)s scan --count 20
  %(prog)s asin B08XYZ1234
        """,
    )

    sub = parser.add_subparsers(dest="mode", required=True)

    # Brand mode
    p_brand = sub.add_parser("brand", help="Search retailers for a specific brand")
    p_brand.add_argument("brand_name", help="Brand to search for (e.g. 'Jellycat')")
    p_brand.add_argument("--retailers", "-r", default="target,walgreens,walmart",
                         help="Comma-separated retailer keys (default: target,walgreens,walmart)")
    p_brand.add_argument("--max", "-n", type=int, default=20,
                         help="Max products to verify (default: 20)")
    p_brand.add_argument("--min-profit", type=float, default=2.0,
                         help="Min profit per unit (default: $2.00)")
    p_brand.add_argument("--deep-verify", type=int, default=5,
                         help="Top N to deep-verify with offers (default: 5, 0=skip)")

    # Brands mode — scan all student-confirmed ungated brands
    p_brands = sub.add_parser("brands", help="Scan retailers across all student-confirmed ungated brands")
    p_brands.add_argument("--retailers", "-r", default="target,walgreens,walmart",
                          help="Comma-separated retailer keys (default: target,walgreens,walmart)")
    p_brands.add_argument("--tier", type=int, default=3, choices=[1, 2, 3],
                          help="Max brand tier to include: 1=Sabbo-posted, 2=+leads, 3=all (default: 3)")
    p_brands.add_argument("--max-per-brand", type=int, default=10,
                          help="Max products to check per brand (default: 10)")
    p_brands.add_argument("--min-profit", type=float, default=2.0)
    p_brands.add_argument("--deep-verify", type=int, default=3)
    p_brands.add_argument("--brands", dest="brand_filter", default=None,
                          help="Comma-separated subset of brands to scan (default: all)")

    # Category mode
    p_cat = sub.add_parser("category", help="Browse a category for arbitrage")
    p_cat.add_argument("category", help="Category (e.g. 'toys', 'beauty', 'grocery')")
    p_cat.add_argument("--subcategory", "-s", default=None,
                       help="Subcategory filter (e.g. 'plush', 'candy')")
    p_cat.add_argument("--retailers", "-r", default="target,walgreens,walmart")
    p_cat.add_argument("--max", "-n", type=int, default=20)
    p_cat.add_argument("--min-profit", type=float, default=2.0)
    p_cat.add_argument("--deep-verify", type=int, default=5)

    # Retailer mode
    p_ret = sub.add_parser("retailer", help="Scan a retailer's pages")
    p_ret.add_argument("retailer_key", help="Retailer (e.g. 'target', 'walgreens')")
    p_ret.add_argument("--section", default="clearance",
                       help="Section to scan (default: clearance)")
    p_ret.add_argument("--brand", default=None, help="Filter by brand name")
    p_ret.add_argument("--max", "-n", type=int, default=20)
    p_ret.add_argument("--min-profit", type=float, default=2.0)
    p_ret.add_argument("--deep-verify", type=int, default=5)

    # Scan mode
    p_scan = sub.add_parser("scan", help="Multi-source scan")
    p_scan.add_argument("--source", default="all",
                        choices=["all", "clearance", "hip2save"],
                        help="Source to scan (default: all)")
    p_scan.add_argument("--retailers", "-r", default="target,walgreens,walmart")
    p_scan.add_argument("--count", "-n", type=int, default=20)
    p_scan.add_argument("--min-profit", type=float, default=2.0)
    p_scan.add_argument("--deep-verify", type=int, default=5)

    # ASIN mode
    p_asin = sub.add_parser("asin", help="Reverse-source a single ASIN")
    p_asin.add_argument("asin", help="Amazon ASIN (e.g. B08XYZ1234)")
    p_asin.add_argument("--retailers", "-r", default="target,walgreens,walmart")
    p_asin.add_argument("--min-profit", type=float, default=2.0)

    # Batch mode: read ASINs from file, source each one
    p_batch = sub.add_parser("batch", help="Batch-source ASINs from a file (pipeline mode)")
    p_batch.add_argument("--input", "-i", required=True,
                         help="Path to file with one ASIN per line")
    p_batch.add_argument("--retailers", "-r", default="target,walgreens,walmart,hmart")
    p_batch.add_argument("--min-profit", type=float, default=2.0)
    p_batch.add_argument("--max", type=int, default=50,
                         help="Max ASINs to process (default: 50)")

    # Deals mode: Keepa price drops + RSS feeds
    p_deals = sub.add_parser("deals", help="Find deals via Keepa price drops and RSS feeds")
    p_deals.add_argument("--source", default="all",
                         choices=["all", "keepa", "rss"],
                         help="Deal source (default: all)")
    p_deals.add_argument("--min-drop", type=int, default=15,
                         help="Min price drop %% for Keepa deals (default: 15)")
    p_deals.add_argument("--count", "-n", type=int, default=30,
                         help="Max deals to process (default: 30)")
    p_deals.add_argument("--min-profit", type=float, default=1.50)
    p_deals.add_argument("--retailers", "-r", default="target,walgreens,walmart",
                         help="Retailers for reverse-sourcing Keepa deals")

    # OOS mode: Out-of-stock opportunity scanning (Keepa Pro required)
    p_oos = sub.add_parser("oos", help="Find out-of-stock Amazon opportunities")
    p_oos.add_argument("--count", "-n", type=int, default=30,
                       help="Max candidates to scan (default: 30)")
    p_oos.add_argument("--max-bsr", type=int, default=100000,
                       help="Maximum BSR threshold (default: 100000)")
    p_oos.add_argument("--min-reviews", type=int, default=50,
                       help="Minimum review count (default: 50)")
    p_oos.add_argument("--min-price", type=float, default=5.0,
                       help="Minimum price in dollars (default: 5.0)")
    p_oos.add_argument("--max-price", type=float, default=50.0,
                       help="Maximum price in dollars (default: 50.0)")
    p_oos.add_argument("--category", type=int, default=0,
                       help="Keepa category ID (0 = all)")
    p_oos.add_argument("--reverse-source", action="store_true",
                       help="Search retailers for each OOS product")
    p_oos.add_argument("--max-retailers", type=int, default=10,
                       help="Max retailers per product (default: 10)")

    # A2A mode: Amazon-to-Amazon flips
    p_a2a = sub.add_parser("a2a", help="Amazon-to-Amazon flips (warehouse, variation, multipack)")
    p_a2a.add_argument("--type", dest="a2a_type", default="warehouse",
                       choices=["warehouse", "variation", "multipack"],
                       help="Flip type (default: warehouse)")
    p_a2a.add_argument("--count", "-n", type=int, default=30,
                       help="Max results (default: 30)")
    p_a2a.add_argument("--asin", default=None,
                       help="ASIN for variation analysis")
    p_a2a.add_argument("--min-discount", type=int, default=40,
                       help="Min discount %% for warehouse deals (default: 40)")
    p_a2a.add_argument("--max-bsr", type=int, default=200000,
                       help="Maximum BSR (default: 200000)")

    # Finder mode: Keepa Product Finder (bulk catalog search)
    p_finder = sub.add_parser("finder", help="Keepa Product Finder — bulk catalog search for price drops")
    p_finder.add_argument("--min-drop", type=int, default=30,
                          help="Min price drop %% over 90 days (default: 30)")
    p_finder.add_argument("--max-bsr", type=int, default=100000,
                          help="Maximum BSR (default: 100000)")
    p_finder.add_argument("--price-range", default="10,50",
                          help="Price range in dollars, comma-separated (default: 10,50)")
    p_finder.add_argument("--min-sellers", type=int, default=3,
                          help="Min FBA sellers (default: 3)")
    p_finder.add_argument("--max-sellers", type=int, default=15,
                          help="Max FBA sellers (default: 15)")
    p_finder.add_argument("--category", type=int, default=0,
                          help="Keepa category ID (0 = all)")
    p_finder.add_argument("--count", "-n", type=int, default=50,
                          help="Max results (default: 50)")
    p_finder.add_argument("--reverse-source", action="store_true",
                          help="Reverse-source each candidate from retailers")
    p_finder.add_argument("--retailers", "-r", default="target,walgreens,walmart")

    p_reverse = sub.add_parser("reverse", help="Reverse search: given ASINs, find retail sources")
    p_reverse.add_argument("--asins", help="Comma-separated ASINs")
    p_reverse.add_argument("--asins-file", help="Path to file with ASINs (one per line)")
    p_reverse.add_argument("--min-roi", type=float, default=30.0,
                           help="Minimum ROI %% to include (default: 30)")
    p_reverse.add_argument("--min-profit", type=float, default=3.00,
                           help="Minimum profit per unit (default: $3.00)")

    # ── Catalog mode (full retailer dump — StartUpFBA workflow) ────────
    p_catalog = sub.add_parser("catalog", help="Scrape entire retailer catalog → filter → match → score")
    p_catalog.add_argument("retailer_url", help="Retailer URL (e.g., https://www.shopwss.com)")
    p_catalog.add_argument("--max-tokens", type=int, default=3000,
                           help="Max Keepa tokens to spend (default: 3000)")
    p_catalog.add_argument("--min-roi", type=float, default=15.0,
                           help="Min ROI %% (default: 15)")
    p_catalog.add_argument("--min-profit", type=float, default=2.0,
                           help="Min profit per unit (default: $2)")
    p_catalog.add_argument("--max-bsr", type=int, default=500000,
                           help="Max BSR (default: 500000)")
    p_catalog.add_argument("--min-price", type=float, default=5.0,
                           help="Min retail price filter (default: $5)")
    p_catalog.add_argument("--max-price", type=float, default=0,
                           help="Max retail price filter (0=no cap, default: no cap)")
    p_catalog.add_argument("--coupon", type=str, default=None,
                           help="Coupon to apply (e.g., '20%% off')")
    p_catalog.add_argument("--limit-scrape", type=int, default=0,
                           help="Max products to scrape (0=unlimited)")
    p_catalog.add_argument("--deep-verify", type=int, default=0,
                           help="Deep verify top N with Keepa offers (21 tokens each)")
    p_catalog.add_argument("--verify-links", action="store_true",
                           help="Enable buy link verification (off by default)")
    p_catalog.add_argument("--no-coupon", action="store_true",
                           help="Skip coupon auto-discovery")
    p_catalog.add_argument("--strict", action="store_true",
                           help="Drop products below thresholds instead of tagging")

    # ── Mode 15: Storefront Stalker ──────────────────────────────────────
    p_storefront = sub.add_parser("storefront", help="Scrape Amazon seller storefront for product ideas")
    sf_group = p_storefront.add_mutually_exclusive_group(required=True)
    sf_group.add_argument("--seller", help="Amazon seller ID (e.g., A1B2C3D4E5F6G7)")
    sf_group.add_argument("--url", help="Full Amazon storefront URL")
    p_storefront.add_argument("--max-products", type=int, default=100,
                              help="Max products to extract (default: 100)")
    p_storefront.add_argument("--no-details", action="store_true",
                              help="Skip detail page enrichment (faster)")
    p_storefront.add_argument("--reverse-source", action="store_true",
                              help="Reverse source top products at retail stores")

    # Global flags (apply to all modes)
    parser.add_argument("--export", choices=["sheets"], default=None,
                        help="Export results to Google Sheets after scan")
    parser.add_argument("--notify", action="store_true",
                        help="Send Telegram alert for BUY/MAYBE results")
    parser.add_argument("--resume", action="store_true",
                        help="Resume a previously interrupted scan from checkpoint")

    args = parser.parse_args()

    # Set global resume mode for checkpoint/resume support
    global _resume_mode, _checkpoint_scan_id
    _resume_mode = getattr(args, "resume", False)
    if _resume_mode:
        _checkpoint_scan_id = args.mode
        print(f"[source] Resume mode enabled — loading checkpoint for '{args.mode}'",
              file=sys.stderr)

    # Dispatch
    if args.mode == "brands":
        retailers = [r.strip().lower() for r in args.retailers.split(",")]
        brand_filter = [b.strip() for b in args.brand_filter.split(",")] if args.brand_filter else None
        results = mode_brands(retailers=retailers, max_tier=args.tier,
                              max_per_brand=args.max_per_brand,
                              min_profit=args.min_profit, deep_verify=args.deep_verify,
                              brand_filter=brand_filter)
        mode_name = f"Brands (tier 1-{args.tier})"

    elif args.mode == "brand":
        retailers = [r.strip().lower() for r in args.retailers.split(",")]
        results = mode_brand(args.brand_name, retailers, max_results=args.max,
                             min_profit=args.min_profit, deep_verify=args.deep_verify)
        mode_name = f"Brand: {args.brand_name}"

    elif args.mode == "category":
        retailers = [r.strip().lower() for r in args.retailers.split(",")]
        results = mode_category(args.category, subcategory=args.subcategory,
                                retailers=retailers, max_results=args.max,
                                min_profit=args.min_profit, deep_verify=args.deep_verify)
        mode_name = f"Category: {args.category}"

    elif args.mode == "retailer":
        results = mode_retailer(args.retailer_key.lower(), section=args.section,
                                brand_filter=args.brand, max_results=args.max,
                                min_profit=args.min_profit, deep_verify=args.deep_verify)
        mode_name = f"Retailer: {args.retailer_key}"

    elif args.mode == "scan":
        retailers = [r.strip().lower() for r in args.retailers.split(",")]
        results = mode_scan(sources=args.source, retailers=retailers,
                            count=args.count, min_profit=args.min_profit,
                            deep_verify=args.deep_verify)
        mode_name = f"Scan: {args.source}"

    elif args.mode == "asin":
        retailers = [r.strip().lower() for r in args.retailers.split(",")]
        results = mode_asin(args.asin, retailers=retailers,
                            min_profit=args.min_profit)
        mode_name = f"ASIN: {args.asin}"

    elif args.mode == "batch":
        retailers = [r.strip().lower() for r in args.retailers.split(",")]
        results = mode_batch(args.input, retailers=retailers,
                             min_profit=args.min_profit, max_asins=args.max)
        mode_name = f"Batch: {args.input}"

    elif args.mode == "deals":
        results = mode_deals(source=args.source, min_drop=args.min_drop,
                             count=args.count, min_profit=args.min_profit,
                             retailers=[r.strip().lower() for r in args.retailers.split(",")])
        mode_name = f"Deals: {args.source}"

    elif args.mode == "oos":
        results = mode_oos(count=args.count, category=args.category,
                           max_bsr=args.max_bsr, min_reviews=args.min_reviews,
                           min_price=args.min_price, max_price=args.max_price,
                           reverse_source=args.reverse_source,
                           max_retailers=args.max_retailers)
        mode_name = "OOS Opportunities"

    elif args.mode == "a2a":
        results = mode_a2a(a2a_type=args.a2a_type, count=args.count,
                           asin=args.asin, min_discount=args.min_discount,
                           max_bsr=args.max_bsr)
        mode_name = f"A2A: {args.a2a_type}"

    elif args.mode == "finder":
        pr = args.price_range.split(",")
        price_min = float(pr[0]) if len(pr) > 0 else 10
        price_max = float(pr[1]) if len(pr) > 1 else 50
        results = mode_finder(min_drop=args.min_drop, max_bsr=args.max_bsr,
                              price_range=(price_min, price_max),
                              min_sellers=args.min_sellers,
                              max_sellers=args.max_sellers,
                              category=args.category, count=args.count,
                              reverse_source=args.reverse_source,
                              retailers=[r.strip().lower() for r in args.retailers.split(",")])
        mode_name = f"Finder: drop>{args.min_drop}%"

    elif args.mode == "catalog":
        from catalog_pipeline import run_pipeline as _run_catalog
        output = _run_catalog(
            url=args.retailer_url,
            max_tokens=args.max_tokens,
            min_roi=args.min_roi,
            min_profit=args.min_profit,
            max_bsr=args.max_bsr,
            min_price=args.min_price,
            max_price=args.max_price,
            coupon=args.coupon,
            limit_scrape=args.limit_scrape,
            resume=getattr(args, "resume", False),
            deep_verify=getattr(args, "deep_verify", 0),
            verify_links=getattr(args, "verify_links", False),
            no_coupon=getattr(args, "no_coupon", False),
            strict=getattr(args, "strict", False),
        )
        # Catalog has its own output — convert to source.py result format
        results = output.get("products", [])
        mode_name = f"Catalog: {args.retailer_url}"

    elif args.mode == "storefront":
        from storefront_stalker import run_stalker, extract_seller_id, normalize_stalker_results
        raw_input = getattr(args, "seller", None) or getattr(args, "url", None)
        seller_id = extract_seller_id(raw_input)
        if not seller_id:
            print(f"ERROR: Could not extract seller ID from: {raw_input}", file=sys.stderr)
            sys.exit(1)
        output = run_stalker(
            seller_id=seller_id,
            max_products=args.max_products,
            fetch_details=not getattr(args, "no_details", False),
            reverse_source=getattr(args, "reverse_source", False),
        )
        # Normalize to Schema B for unified results
        results = normalize_stalker_results(output) if output else []
        mode_name = f"Storefront: {seller_id}"

    elif args.mode == "reverse":
        from mode_reverse import run_reverse_search, load_asins_from_file
        asins = []
        if getattr(args, "asins", None):
            asins = [a.strip() for a in args.asins.split(",") if a.strip()]
        elif getattr(args, "asins_file", None):
            asins = load_asins_from_file(args.asins_file)
        if not asins:
            print("Error: provide --asins or --asins-file for reverse mode", file=sys.stderr)
            sys.exit(1)
        results = run_reverse_search(
            asins,
            getattr(args, "min_roi", 30.0),
            getattr(args, "min_profit", 3.0),
        )
        if results:
            print(f"\n{'=' * 60}")
            print(f"REVERSE SEARCH RESULTS — {len(results)} opportunities found")
            print(f"{'=' * 60}")
            for r in results:
                print(f"\n[{r.get('estimated_roi', 0):.0f}% ROI] "
                      f"{r.get('amazon_title', r.get('name', 'Unknown'))[:60]}")
                print(f"  ASIN: {r.get('asin', 'N/A')} | "
                      f"Amazon: ${r.get('amazon_price', 0):.2f}")
                print(f"  Buy at: {r.get('source_retailer', 'Unknown')} for "
                      f"${r.get('retail_price', r.get('buy_cost', 0)):.2f} "
                      f"(max cost: ${r.get('max_cost', 0):.2f})")
                print(f"  Link: {r.get('source_url', 'N/A')}")
        else:
            print("\nNo opportunities found. Try different ASINs or lower your ROI threshold.")
        mode_name = f"Reverse: {len(asins)} ASINs"

    else:
        parser.print_help()
        return

    # ── MEGA VERIFICATION LAYER ────────────────────────────────────────────
    # Every result passes through verify_sourcing_results before output.
    # Bad links, wrong matches, and non-arbitrage products are rejected.
    if results:
        try:
            from verify_sourcing_results import verify_results as _verify
            verification = _verify(results, strict=True)
            rejected_count = verification["summary"]["rejected"]
            if rejected_count:
                print(f"\n  [verify] Rejected {rejected_count} results "
                      f"(bad links, wrong match, price issues)", file=sys.stderr)
            results = verification["verified"] + verification["flagged"]
        except Exception as e:
            print(f"  [verify] Verification error (continuing): {e}", file=sys.stderr)

    # Output
    text = format_results(results, mode_name)
    print(text)

    if results:
        json_path, text_path = save_results(results, mode_name)
        print(f"\nSaved: {json_path}", file=sys.stderr)
        print(f"Saved: {text_path}", file=sys.stderr)

        # Schema-adapted export/notify (converts Schema B → Schema A automatically)
        if getattr(args, "export", None) == "sheets" or getattr(args, "notify", False):
            try:
                from schema_adapter import wrap_for_export
                export_data = wrap_for_export(results, mode_name=mode_name)
                export_json_path = TMP_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_export.json"
                with open(export_json_path, "w") as f:
                    json.dump(export_data, f, indent=2, default=str)
            except Exception as e:
                print(f"[source] Schema adapter error: {e}", file=sys.stderr)
                export_json_path = None

        if getattr(args, "export", None) == "sheets" and export_json_path:
            try:
                from export_to_sheets import export_results
                print(f"\n[source] Exporting to Google Sheets...", file=sys.stderr)
                export_results(str(export_json_path))
            except Exception as e:
                print(f"[source] Sheets export error: {e}", file=sys.stderr)

        if getattr(args, "notify", False) and export_json_path:
            try:
                from sourcing_alerts import send_sourcing_alert
                print(f"\n[source] Sending Telegram alert...", file=sys.stderr)
                send_sourcing_alert(str(export_json_path))
            except Exception as e:
                print(f"[source] Telegram alert error: {e}", file=sys.stderr)

    print(f"\n[source] Done. {len(results)} products found.", file=sys.stderr)


if __name__ == "__main__":
    main()
