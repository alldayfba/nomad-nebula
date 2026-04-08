#!/usr/bin/env python3
"""
Script: deal_scanner.py (v4.0)
Purpose: Amazon FBA online arbitrage sourcing tool.
         Scans real retailer websites (Walmart, Target, CVS, Walgreens, Home Depot,
         Kohl's, Vitacost) for products cheaper than Amazon, then calculates
         profitability for FBA resale.

v4.0 Upgrades:
  - Retailer clearance scanning: crawls real clearance/sale pages via Playwright
  - Keepa reverse sourcing: finds Amazon bestsellers, checks if cheaper at retail
  - Replaces dead Target Redsky API with working multi-retailer system
  - Forward sourcing (clearance pages) + reverse sourcing (Keepa → retail)

v3.0 Features (retained):
  - KeepaClient with correct CSV indices (34=FBA, 35=FBM)
  - Private label detection, multi-seller verification
  - Price trend data, buy links

Sources:
  Retailer clearance pages (Playwright)  → Walmart, Target, CVS, Walgreens, etc.
  Hip2Save RSS (free, 200 deals)         → deals from real retailers
  Keepa reverse (bestsellers → UPC check) → Amazon products cheaper at retail
  KeepaClient (1 token/search)           → Amazon ASIN + price + seller verification

Usage:
  python3 execution/deal_scanner.py --count 20 --source clearance --match-amazon
  python3 execution/deal_scanner.py --count 20 --source reverse --match-amazon
  python3 execution/deal_scanner.py --count 20 --source all --match-amazon
  python3 execution/deal_scanner.py --count 20 --match-amazon --retailers walmart,target,cvs
  python3 execution/deal_scanner.py --count 20 --match-amazon --min-sellers 2 --no-private-label
  python3 execution/deal_scanner.py --count 20 --source hip2save
  python3 execution/deal_scanner.py --count 20 --supabase
"""

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# ── Target Redsky API ────────────────────────────────────────────────────────

TARGET_API_KEY = os.getenv("TARGET_API_KEY", "ff457966e64d5e877fdbad070f276d18ecec4a01")
TARGET_SEARCH_URL = "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2"
TARGET_STORE_ID = "1375"  # Default store; can be overridden

TARGET_SEARCH_TERMS = {
    "grocery": [
        "snacks", "cereal", "coffee", "candy", "protein bars",
        "granola bars", "chips", "cookies", "crackers", "tea",
        "pasta sauce", "rice", "popcorn", "energy drinks", "nuts",
    ],
    "health": [
        "vitamins", "supplements", "probiotics", "first aid",
        "toothpaste", "sunscreen", "pain relief", "allergy medicine",
        "melatonin", "fish oil", "collagen", "biotin",
    ],
    "beauty": [
        "shampoo", "conditioner", "face wash", "moisturizer",
        "body wash", "deodorant", "lip balm", "mascara",
        "foundation", "sunscreen spf",
    ],
    "baby": [
        "diapers", "baby wipes", "baby formula", "baby food",
    ],
    "pets": [
        "dog food", "cat food", "dog treats", "cat treats", "pet toys",
    ],
}

# ── Hip2Save RSS ─────────────────────────────────────────────────────────────

HIP2SAVE_FEED = "https://hip2save.com/feed/"

# ── Category Keywords (for filtering Hip2Save) ──────────────────────────────

CATEGORY_KEYWORDS = {
    "grocery": [
        "candy", "chocolate", "snack", "cookie", "cracker", "chip", "cereal",
        "bar", "granola", "nut", "popcorn", "pretzel", "gum", "mint",
        "sauce", "spice", "seasoning", "oil", "vinegar", "pasta", "rice",
        "coffee", "tea", "cocoa", "drink", "juice", "water", "soda", "energy",
        "protein", "shake", "powder", "organic", "gluten", "vegan",
        "pantry", "grocery", "food", "meal", "soup", "broth",
    ],
    "health": [
        "vitamin", "supplement", "probiotic", "omega", "magnesium", "zinc",
        "turmeric", "collagen", "biotin", "melatonin", "ashwagandha",
        "first aid", "bandage", "thermometer", "medicine", "otc",
        "toothpaste", "toothbrush", "floss", "mouthwash", "dental",
    ],
    "beauty": [
        "shampoo", "conditioner", "lotion", "cream", "serum", "moisturizer",
        "sunscreen", "spf", "face wash", "cleanser", "mask", "lip",
        "mascara", "foundation", "concealer", "eyeshadow", "makeup",
        "deodorant", "body wash", "soap", "razor", "shaving",
    ],
    "baby": [
        "diaper", "wipe", "formula", "baby food", "pacifier", "bottle",
        "sippy", "bib", "onesie", "stroller", "car seat",
    ],
    "pets": [
        "dog food", "cat food", "pet", "puppy", "kitten", "treats",
        "litter", "flea", "tick", "collar", "leash",
    ],
}

# ── Store Detection (for Hip2Save parsing) ───────────────────────────────────

STORE_PATTERNS = [
    (r"\bat\s+amazon\b", "Amazon"),
    (r"\bat\s+walmart\b", "Walmart"),
    (r"\bat\s+target\b", "Target"),
    (r"\bat\s+costco\b", "Costco"),
    (r"\bat\s+cvs\b", "CVS"),
    (r"\bat\s+walgreens\b", "Walgreens"),
    (r"\bat\s+kroger\b", "Kroger"),
    (r"\bat\s+sam'?s\s+club\b", "Sam's Club"),
    (r"\bat\s+bj'?s\b", "BJ's"),
    (r"\bat\s+rite\s+aid\b", "Rite Aid"),
    (r"\bat\s+home\s+depot\b", "Home Depot"),
    (r"\bat\s+lowe'?s\b", "Lowe's"),
    (r"\bat\s+dollar\s+tree\b", "Dollar Tree"),
    (r"\bat\s+dollar\s+general\b", "Dollar General"),
    (r"\bat\s+meijer\b", "Meijer"),
    (r"\bat\s+publix\b", "Publix"),
    (r"\bat\s+aldi\b", "Aldi"),
    (r"\bat\s+trader\s+joe'?s\b", "Trader Joe's"),
    (r"\bat\s+whole\s+foods\b", "Whole Foods"),
    (r"\bat\s+sprouts\b", "Sprouts"),
    (r"amazon\.com", "Amazon"),
    (r"walmart\.com", "Walmart"),
    (r"target\.com", "Target"),
    (r"cvs\.com", "CVS"),
    (r"walgreens\.com", "Walgreens"),
]


# ── Source 1: Target Redsky API ──────────────────────────────────────────────

def fetch_target_products(categories=None, count=24):
    """
    Search Target's Redsky API for products. Returns structured deal dicts.
    Free, no auth required, fast (<2s per query).
    """
    if categories is None:
        categories = ["grocery"]

    search_terms = []
    for cat in categories:
        terms = TARGET_SEARCH_TERMS.get(cat, [])
        search_terms.extend(terms)

    if not search_terms:
        search_terms = TARGET_SEARCH_TERMS["grocery"]

    all_products = []
    seen_tcins = set()

    for term in search_terms:
        try:
            params = {
                "key": TARGET_API_KEY,
                "channel": "WEB",
                "count": min(count, 24),
                "keyword": term,
                "pricing_store_id": TARGET_STORE_ID,
                "store_ids": TARGET_STORE_ID,
                "default_purchasability_filter": "true",
                "include_sponsored": "false",
                "offset": 0,
                "page": f"/s/{term}",
                "visitor_id": "0",
            }
            try:
                r = requests.get(TARGET_SEARCH_URL, params=params, headers=HEADERS, timeout=15)
            except Exception as e:
                print(f"  [target] '{term}': request failed: {e}", file=sys.stderr)
                continue
            if r.status_code != 200:
                print(f"  [target] '{term}': HTTP {r.status_code}", file=sys.stderr)
                continue

            data = r.json()
            search_resp = data.get("data", {}).get("search", {}).get("products", [])

            for product in search_resp:
                tcin = product.get("tcin", "")
                if not tcin or tcin in seen_tcins:
                    continue
                seen_tcins.add(tcin)

                # Extract price info
                price_data = product.get("price", {})
                reg_price = price_data.get("reg_retail")
                current_price = price_data.get("current_retail")

                if not current_price:
                    continue

                # Parse prices to float
                try:
                    current_f = float(current_price)
                except (ValueError, TypeError):
                    continue

                reg_f = None
                if reg_price:
                    try:
                        reg_f = float(reg_price)
                    except (ValueError, TypeError):
                        pass

                on_sale = reg_f is not None and reg_f > current_f

                # Extract product info
                item_data = product.get("item", {})
                desc = item_data.get("product_description", {})
                title = desc.get("title", "")
                enrichment = item_data.get("enrichment", {})
                buy_url = enrichment.get("buy_url", "")

                if not title:
                    continue

                # Detect categories
                title_lower = title.lower()
                cats = []
                for cat, keywords in CATEGORY_KEYWORDS.items():
                    if any(kw in title_lower for kw in keywords):
                        cats.append(cat)

                all_products.append({
                    "name": title,
                    "price": current_f,
                    "regular_price": reg_f,
                    "on_sale": on_sale,
                    "store": "Target",
                    "tcin": tcin,
                    "link": buy_url or f"https://www.target.com/p/-/A-{tcin}",
                    "categories": cats,
                    "source": "target",
                })

            found = len(search_resp) if search_resp else 0
            print(f"  [target] '{term}': {found} products", file=sys.stderr)
            time.sleep(0.3)  # Be polite to Target API

        except Exception as e:
            print(f"  [target] '{term}': error — {e}", file=sys.stderr)
            continue

    return all_products


# ── Source 2: Hip2Save RSS ───────────────────────────────────────────────────

def fetch_hip2save_deals():
    """
    Fetch deals from Hip2Save RSS feed. Returns deal dicts from real retailers
    (Walmart, Target, CVS, Walgreens, etc.). Free, ~200 deals per fetch.
    """
    all_deals = []
    try:
        r = requests.get(HIP2SAVE_FEED, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  [hip2save] HTTP {r.status_code}", file=sys.stderr)
            return []

        root = ET.fromstring(r.text)
        items = root.findall(".//item")

        for item in items:
            title = (item.find("title").text or "").strip()
            link = (item.find("link").text or "").strip()

            if not title:
                continue

            title_lower = title.lower()

            # Extract price
            price_match = re.search(r"\$(\d+(?:[.,]\d{1,2})?)", title)
            price = float(price_match.group(1).replace(",", "")) if price_match else None

            # Extract store
            store = None
            for pattern, store_name in STORE_PATTERNS:
                if re.search(pattern, title_lower):
                    store = store_name
                    break

            # Skip Amazon deals (we want retail → Amazon arbitrage)
            if store == "Amazon":
                continue

            # Skip deals with no store identified or no price
            if not store or not price:
                continue

            # Clean product name
            name = title
            name = re.sub(r"\s*\$\d+(?:[.,]\d{1,2})?\s*", " ", name)
            name = re.sub(r"\s*\+\s*(?:free\s+)?(?:shipping|delivery|s&s|subscribe).*", "", name, flags=re.I)
            name = re.sub(r"\s+(?:at|@)\s+\w+(?:\.\w+)?$", "", name, flags=re.I)
            name = name.strip(" -|+")

            # Detect categories
            cats = []
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in title_lower for kw in keywords):
                    cats.append(cat)

            all_deals.append({
                "name": name,
                "price": price,
                "store": store,
                "link": link,
                "categories": cats,
                "original_title": title,
                "source": "hip2save",
            })

        print(f"  [hip2save] {len(all_deals)} retail deals (from {len(items)} total)", file=sys.stderr)

    except Exception as e:
        print(f"  [hip2save] error — {e}", file=sys.stderr)

    # Deduplicate by cleaned name
    seen = set()
    unique = []
    for d in all_deals:
        key = d["name"].lower()[:50]
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


# ── Source 3: Retailer Clearance Pages (Playwright) ──────────────────────────

# Retailers available for clearance scanning
CLEARANCE_RETAILERS = {
    "walmart": "Walmart",
    "target": "Target",
    "cvs": "CVS",
    "walgreens": "Walgreens",
    "homedepot": "Home Depot",
    "kohls": "Kohl's",
    "vitacost": "Vitacost",
}

DEFAULT_CLEARANCE_RETAILERS = ["walmart", "target", "cvs", "walgreens"]


def fetch_retailer_clearance(retailers=None, categories=None, max_per_retailer=15):
    """Scan clearance/sale pages of real retailers via Playwright.

    Uses multi_retailer_search.py's scan_clearance() which crawls retailer
    clearance URLs defined in retailer_registry.py, extracts products via
    CSS selectors from retailer_configs.py.

    Args:
        retailers: List of retailer keys (e.g. ["walmart", "target"]).
        categories: Optional category filter (e.g. ["Grocery", "Health"]).
        max_per_retailer: Max products to scrape per retailer.

    Returns:
        List of deal dicts compatible with the main pipeline.
    """
    if retailers is None:
        retailers = DEFAULT_CLEARANCE_RETAILERS

    try:
        from multi_retailer_search import scan_clearance
        from retailer_registry import get_clearance_urls
        from scrape_retail_products import USER_AGENT, STEALTH_SCRIPT
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"  [clearance] Import error: {e}", file=sys.stderr)
        print(f"  [clearance] Install: pip install playwright && playwright install chromium",
              file=sys.stderr)
        return []

    # Filter clearance URLs to only requested retailers
    category = categories[0].title() if categories else None
    all_clearance = get_clearance_urls(category)

    # Filter to only our target retailers
    retailer_keys = set(retailers)
    filtered_clearance = [
        (r, url) for r, url in all_clearance
        if r.get("key", "").lower() in retailer_keys
    ]

    if not filtered_clearance:
        print(f"  [clearance] No clearance URLs for retailers: {retailers}", file=sys.stderr)
        return []

    print(f"  [clearance] Scanning {len(filtered_clearance)} retailer clearance pages...",
          file=sys.stderr)

    all_deals = []
    try:
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

            products = scan_clearance(
                page, category, max_retailers=len(filtered_clearance),
                max_per_retailer=max_per_retailer,
            )

            browser.close()

        # Convert to deal_scanner format
        for prod in products:
            price = prod.get("retail_price") or prod.get("price")
            if not price:
                continue
            try:
                price = float(price)
            except (ValueError, TypeError):
                continue

            deal = {
                "name": prod.get("name") or prod.get("title") or "",
                "price": price,
                "regular_price": prod.get("regular_price"),
                "on_sale": prod.get("sale_price") is not None,
                "store": prod.get("retailer") or prod.get("retailer_key", ""),
                "link": prod.get("retail_url") or prod.get("url") or "",
                "upc": prod.get("upc"),
                "image_url": prod.get("image_url"),
                "categories": [],
                "source": "clearance",
                "cashback_percent": prod.get("cashback_percent", 0),
            }

            # Detect categories from title
            title_lower = deal["name"].lower()
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if any(kw in title_lower for kw in keywords):
                    deal["categories"].append(cat)

            all_deals.append(deal)

    except Exception as e:
        print(f"  [clearance] Error: {e}", file=sys.stderr)

    print(f"  [clearance] Total: {len(all_deals)} products from clearance pages",
          file=sys.stderr)
    return all_deals


# ── Source 4: Keepa Reverse Sourcing (Bestsellers → Retail Check) ────────────

def fetch_keepa_reverse(categories=None, count=20, keepa_tier="pro"):
    """Reverse sourcing: find Amazon bestsellers, check if cheaper at retail.

    Uses Keepa to get top-selling ASINs with UPCs, then checks prices at
    Walmart/Target. Returns products where retail is cheaper than Amazon.

    Token cost: ~50 (bestsellers) + ~10-20 (batch product details) = ~60-70 tokens.

    Returns:
        List of deal dicts with _pre_matched=True (skip Keepa search in pipeline).
    """
    try:
        from fast_grocery_scan import (
            search_retailers_by_upc, KEEPA_CATEGORIES,
        )
        from keepa_client import KeepaClient
    except ImportError as e:
        print(f"  [keepa-reverse] Import error: {e}", file=sys.stderr)
        return []

    client = _get_keepa_client(keepa_tier)
    if not client:
        print("  [keepa-reverse] No KeepaClient available", file=sys.stderr)
        return []

    if categories is None:
        categories = ["grocery"]

    # Wait for enough tokens before starting (bestsellers=50 + batch=20 = ~70 tokens)
    print(f"  [keepa-reverse] Waiting for tokens (need ~75)...", file=sys.stderr)
    client.wait_for_tokens(min_tokens=75)

    all_deals = []
    session = requests.Session()

    for cat in categories:
        cat_id = KEEPA_CATEGORIES.get(cat)
        if not cat_id:
            print(f"  [keepa-reverse] Unknown category: {cat}", file=sys.stderr)
            continue

        print(f"  [keepa-reverse] Bestsellers for '{cat}' (ID: {cat_id})...",
              file=sys.stderr)

        # 50 tokens: get bestseller ASINs
        asins = client.get_bestsellers(cat_id)
        if not asins:
            print(f"  [keepa-reverse] No bestsellers found for {cat}", file=sys.stderr)
            continue
        print(f"  [keepa-reverse] Got {len(asins)} ASINs", file=sys.stderr)

        # Batch fetch product details — limit to save tokens
        batch_size = min(count, 20)
        batch = asins[:batch_size]
        products = client.get_products_batch(batch, stats=1)
        print(f"  [keepa-reverse] Got {len(products)} product details", file=sys.stderr)

        # Filter: need UPC + price in arbitrage range
        candidates = [
            p for p in products
            if p.get("upc") and p.get("sell_price") and 5.0 <= p["sell_price"] <= 75.0
        ]
        print(f"  [keepa-reverse] {len(candidates)} candidates with UPC",
              file=sys.stderr)

        # Check retail prices for each UPC
        for p in candidates:
            upc = p["upc"]
            amz_price = p["sell_price"]

            retail = search_retailers_by_upc(upc, session)

            if retail and retail.get("retail_price"):
                retail_price = retail["retail_price"]
                margin = amz_price - retail_price
                if margin > 2.0:  # At least $2 cheaper at retail
                    all_deals.append({
                        "name": retail.get("name") or p.get("title", ""),
                        "price": retail_price,
                        "store": retail.get("retailer", "Retail"),
                        "link": retail.get("buy_url") or retail.get("url", ""),
                        "amazon_url": f"https://www.amazon.com/dp/{p['asin']}",
                        "categories": [cat],
                        "source": "keepa_reverse",
                        "asin": p["asin"],
                        "upc": upc,
                        "amazon_price": amz_price,
                        "bsr": p.get("bsr"),
                        "brand": p.get("brand", ""),
                        "fba_seller_count": p.get("fba_seller_count"),
                        "fbm_seller_count": p.get("fbm_seller_count"),
                        "review_count": p.get("review_count"),
                        "_pre_matched": True,
                    })
                    print(f"    HIT | ${retail_price:.2f} retail vs "
                          f"${amz_price:.2f} AMZ | {p.get('title', '')[:45]}",
                          file=sys.stderr)

            time.sleep(1.5)  # Be polite to retailers

            if len(all_deals) >= count:
                break

        if len(all_deals) >= count:
            break

    print(f"  [keepa-reverse] Total: {len(all_deals)} products cheaper at retail",
          file=sys.stderr)
    return all_deals


# ── Amazon Matching (KeepaClient) ────────────────────────────────────────────

_keepa_client = None

def _get_keepa_client(tier="pro"):
    """Lazy-init the KeepaClient singleton."""
    global _keepa_client
    if _keepa_client is None:
        try:
            from keepa_client import KeepaClient
            _keepa_client = KeepaClient(tier=tier)
        except Exception as e:
            print(f"  [keepa] Failed to init KeepaClient: {e}", file=sys.stderr)
            return None
    return _keepa_client


def match_amazon_keepa(product_name, upc=None, min_sellers=0,
                        no_private_label=False, keepa_tier="pro"):
    """Match a product to Amazon via KeepaClient.

    Returns enriched dict with seller counts, private label flag, price trends,
    or None if no match found.
    """
    client = _get_keepa_client(keepa_tier)
    if not client:
        return None

    query = upc if upc else product_name
    product = client.search_product(query)
    if not product:
        return None

    # Check tokens
    tokens_left = product.get("tokens_left", 0)
    if tokens_left is not None and tokens_left <= 1:
        print(f"  [keepa] Only {tokens_left} tokens left — stopping", file=sys.stderr)
        return None

    sell_price = product.get("sell_price")
    if not sell_price:
        return None

    # ── Private label check ──────────────────────────────────────────
    pl = product.get("private_label", {})
    is_pl = pl.get("is_private_label")
    if no_private_label and is_pl:
        print(f"  [keepa] SKIP private label: {pl.get('reason', '')}", file=sys.stderr)
        return {**product, "_skip": True, "_skip_reason": f"Private label: {pl.get('reason', '')}"}

    # ── Min sellers check ────────────────────────────────────────────
    fba_count = product.get("fba_seller_count")
    if min_sellers > 0 and fba_count is not None and fba_count < min_sellers:
        print(f"  [keepa] SKIP: only {fba_count} FBA seller(s) (need {min_sellers}+)", file=sys.stderr)
        return {**product, "_skip": True, "_skip_reason": f"Only {fba_count} FBA seller(s)"}

    return {
        "asin": product.get("asin", ""),
        "title": product.get("title", ""),
        "amazon_price": sell_price,
        "brand": product.get("brand", ""),
        "bsr": product.get("bsr"),
        "category": product.get("category", ""),
        "tokens_left": tokens_left,
        # New v3.0 fields
        "fba_seller_count": fba_count,
        "fbm_seller_count": product.get("fbm_seller_count"),
        "total_offer_count": product.get("total_offer_count"),
        "amazon_on_listing": product.get("amazon_on_listing", False),
        "private_label": pl,
        "price_trends": product.get("price_trends", {}),
        "review_count": product.get("review_count"),
        "rating": product.get("rating"),
    }


# ── Profitability Calculation ────────────────────────────────────────────────

def calculate_profit(deal, amazon_data):
    """Calculate profitability using existing calculator or fallback."""
    try:
        from calculate_fba_profitability import calculate_product_profitability
    except ImportError:
        # Fallback: simple calculation
        buy = deal["price"]
        sell = amazon_data.get("amazon_price", 0)
        if not buy or not sell or sell <= buy:
            return {"verdict": "SKIP", "roi_percent": 0, "profit_per_unit": 0}
        # Rough estimate: 15% referral + $3.50 FBA fee
        fees = sell * 0.15 + 3.50
        profit = sell - buy - fees
        roi = (profit / buy) * 100 if buy > 0 else 0
        verdict = "BUY" if roi >= 30 and profit >= 3.50 else ("MAYBE" if roi >= 20 else "SKIP")
        return {
            "verdict": verdict,
            "roi_percent": round(roi, 1),
            "profit_per_unit": round(profit, 2),
            "buy_cost": round(buy, 2),
            "sell_price": round(sell, 2),
            "estimated_fees": round(fees, 2),
        }

    # Use full calculator
    product = {
        "name": deal.get("name", ""),
        "retail_price": deal["price"],
        "retailer": deal.get("store", ""),
        "amazon": {
            "asin": amazon_data.get("asin", ""),
            "title": amazon_data.get("title", ""),
            "amazon_price": amazon_data.get("amazon_price"),
            "category": amazon_data.get("category", "General"),
            "match_confidence": 0.8,
        },
    }
    try:
        return calculate_product_profitability(product, auto_cashback=True)
    except Exception as e:
        print(f"  [profit] Error: {e}", file=sys.stderr)
        return {"verdict": "SKIP", "roi_percent": 0, "profit_per_unit": 0}


# ── Supabase Push ────────────────────────────────────────────────────────────

def push_to_supabase(results, scan_summary):
    """Push results to Supabase sourcing_deals table."""
    supa_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
    supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    org_id = os.getenv("SOURCING_ORG_ID", "")

    if not supa_url or not supa_key:
        print("  [supabase] Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return False

    headers = {
        "apikey": supa_key,
        "Authorization": f"Bearer {supa_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # Insert deals
    rows = []
    for r in results:
        prof = r.get("profitability", {})
        rows.append({
            "organization_id": org_id,
            "asin": r.get("asin", ""),
            "upc": r.get("upc", ""),
            "product_name": r.get("name", "")[:200],
            "retail_price": r.get("price"),
            "amazon_price": r.get("amazon_price"),
            "retailer": r.get("store", ""),
            "deal_url": r.get("link", ""),
            "profit_per_unit": prof.get("profit_per_unit"),
            "roi_percent": prof.get("roi_percent"),
            "verdict": prof.get("verdict", "SKIP"),
            "category": (r.get("categories", [""])[0] if r.get("categories") else ""),
            "deal_score": prof.get("deal_score"),
            "source": r.get("source", "target"),
        })

    if rows:
        try:
            resp = requests.post(f"{supa_url}/rest/v1/sourcing_deals",
                                 headers=headers, json=rows, timeout=15)
        except Exception as e:
            print(f"  [supabase] Deals insert request failed: {e}", file=sys.stderr)
            return False
        if resp.status_code in (200, 201):
            print(f"  [supabase] Inserted {len(rows)} deals", file=sys.stderr)
        else:
            print(f"  [supabase] Insert error: {resp.status_code} {resp.text[:200]}",
                  file=sys.stderr)
            return False

    # Insert scan record
    scan_row = {
        "organization_id": org_id,
        "scan_type": "deal_scanner_v2",
        "deals_found": scan_summary.get("total_deals", 0),
        "buy_count": scan_summary.get("buy_count", 0),
        "maybe_count": scan_summary.get("maybe_count", 0),
        "duration_ms": scan_summary.get("duration_ms", 0),
    }
    try:
        requests.post(f"{supa_url}/rest/v1/sourcing_scans",
                      headers=headers, json=scan_row, timeout=10)
    except Exception as e:
        print(f"  [supabase] Scan record insert failed: {e}", file=sys.stderr)

    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Deal scanner v3 — real retailer sourcing for Amazon FBA")
    parser.add_argument("--count", "-n", type=int, default=20,
                        help="Max deals to return (default: 20)")
    parser.add_argument("--category", "-c", default=None,
                        help="Filter: grocery, health, beauty, baby, pets")
    parser.add_argument("--source", "-s", default="all",
                        choices=["all", "clearance", "reverse", "hip2save", "target"],
                        help="Source: all, clearance (retailer pages), reverse (Keepa→retail), hip2save, target (legacy)")
    parser.add_argument("--retailers", default=None,
                        help="Comma-separated retailers for clearance scan "
                             "(default: walmart,target,cvs,walgreens). "
                             "Options: " + ",".join(CLEARANCE_RETAILERS.keys()))
    parser.add_argument("--match-amazon", action="store_true",
                        help="Match deals to Amazon via Keepa (costs 1 token/match)")
    parser.add_argument("--supabase", action="store_true",
                        help="Push results to Supabase for dashboard display")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--min-price", type=float, default=3.0)
    parser.add_argument("--max-price", type=float, default=50.0)
    parser.add_argument("--sale-only", action="store_true",
                        help="Target only: show only on-sale items")
    # v3.0 flags
    parser.add_argument("--min-sellers", type=int, default=2,
                        help="Min FBA sellers required (default: 2)")
    parser.add_argument("--no-private-label", action="store_true", default=True,
                        help="Skip private label products (default: ON)")
    parser.add_argument("--allow-private-label", action="store_true",
                        help="Allow private label products (overrides --no-private-label)")
    parser.add_argument("--check-stock", action="store_true",
                        help="Verify Target product stock via Redsky API")
    parser.add_argument("--keepa-tier", default="pro",
                        choices=["basic", "pro"],
                        help="Keepa subscription tier (affects rate limiting)")

    # ── Keepa Deals API filters (v4.1) ──────────────────────────────────────
    deals_group = parser.add_argument_group("Keepa Deals API filters",
        "Advanced filters for Keepa deal searches (used with --source keepa-deals)")
    deals_group.add_argument("--keepa-deals", action="store_true",
                             help="Use Keepa Deals API directly (5 tokens/page)")
    # Boolean filters
    deals_group.add_argument("--back-in-stock", action="store_true",
                             help="Only show products recently back in stock")
    deals_group.add_argument("--no-amazon-offer", action="store_true",
                             help="Exclude products where Amazon is a seller")
    deals_group.add_argument("--lowest-90", action="store_true",
                             help="Only products at their lowest 90-day price")
    deals_group.add_argument("--lowest-ever", action="store_true",
                             help="Only products at their lowest ever price")
    deals_group.add_argument("--single-variation", action="store_true",
                             help="Only single-variation listings (no parent/child)")
    # Value filters
    deals_group.add_argument("--warehouse-conditions", type=str, default=None,
                             help="Comma-separated warehouse conditions (1-5)")
    deals_group.add_argument("--brand", type=str, default=None,
                             help="Filter by brand name(s), comma-separated")
    deals_group.add_argument("--title-search", type=str, default="",
                             help="Filter deals by title keyword")
    deals_group.add_argument("--min-rating", type=int, default=None,
                             help="Minimum rating * 10 (e.g. 40 = 4.0 stars)")
    # Range filters
    deals_group.add_argument("--delta-min", type=float, default=None,
                             help="Min absolute price change in dollars")
    deals_group.add_argument("--delta-max", type=float, default=None,
                             help="Max absolute price change in dollars")
    deals_group.add_argument("--delta-pct-min", type=float, default=None,
                             help="Min percentage price change")
    deals_group.add_argument("--delta-pct-max", type=float, default=None,
                             help="Max percentage price change")
    deals_group.add_argument("--bsr-min", type=int, default=None,
                             help="Min sales rank (BSR)")
    deals_group.add_argument("--bsr-max", type=int, default=None,
                             help="Max sales rank (BSR)")
    # Sort
    deals_group.add_argument("--sort", default="percent",
                             choices=["newest", "delta", "rank", "percent"],
                             help="Sort deals by (default: percent)")
    deals_group.add_argument("--sort-desc", action="store_true",
                             help="Sort in descending order")
    # Price type
    deals_group.add_argument("--price-type", default="amazon",
                             choices=["amazon", "new", "used", "sales", "fba",
                                      "buybox", "warehouse", "lightning", "prime_excl"],
                             help="Price type to track (default: amazon)")
    # Paging
    deals_group.add_argument("--max-pages", type=int, default=1,
                             help="Max pages to fetch (150 deals/page, max 67 pages = 10,000 deals)")
    deals_group.add_argument("--date-range", type=int, default=0,
                             choices=[0, 1, 2, 3, 4, 5],
                             help="Date range: 0=24h, 1=3d, 2=7d, 3=14d, 4=30d, 5=90d")

    args = parser.parse_args()

    # Handle private label flag logic
    if args.allow_private_label:
        args.no_private_label = False

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    start = time.time()

    categories = [args.category] if args.category else ["grocery", "health", "beauty"]

    # Parse retailers list
    retailers = None
    if args.retailers:
        retailers = [r.strip().lower() for r in args.retailers.split(",")]
    else:
        retailers = DEFAULT_CLEARANCE_RETAILERS

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[deal-scanner v4.1] Online Arbitrage Sourcing", file=sys.stderr)
    print(f"  Source:     {args.source}", file=sys.stderr)
    print(f"  Categories: {', '.join(categories)}", file=sys.stderr)
    print(f"  Count:      {args.count}", file=sys.stderr)
    print(f"  Price:      ${args.min_price}-${args.max_price}", file=sys.stderr)
    if args.source in ("all", "clearance"):
        print(f"  Retailers:  {', '.join(retailers)}", file=sys.stderr)
    if args.sale_only:
        print(f"  Sale only:  YES", file=sys.stderr)
    if args.match_amazon:
        print(f"  Min sellers: {args.min_sellers}", file=sys.stderr)
        print(f"  No PL:      {args.no_private_label}", file=sys.stderr)
        print(f"  Check stock: {args.check_stock}", file=sys.stderr)
        print(f"  Keepa tier:  {args.keepa_tier}", file=sys.stderr)
    if getattr(args, "keepa_deals", False):
        print(f"  Keepa Deals: YES (5 tokens/page)", file=sys.stderr)
        print(f"  Price type:  {getattr(args, 'price_type', 'amazon')}", file=sys.stderr)
        print(f"  Sort:        {getattr(args, 'sort', 'percent')} {'(desc)' if getattr(args, 'sort_desc', False) else ''}", file=sys.stderr)
        print(f"  Max pages:   {getattr(args, 'max_pages', 1)}", file=sys.stderr)
        if getattr(args, "title_search", ""):
            print(f"  Title search: {args.title_search}", file=sys.stderr)
        if getattr(args, "brand", None):
            print(f"  Brand:       {args.brand}", file=sys.stderr)
        if getattr(args, "lowest_ever", False):
            print(f"  Lowest ever: YES", file=sys.stderr)
        if getattr(args, "lowest_90", False):
            print(f"  Lowest 90d:  YES", file=sys.stderr)
        if getattr(args, "no_amazon_offer", False):
            print(f"  No Amazon:   YES", file=sys.stderr)
        if getattr(args, "back_in_stock", False):
            print(f"  Back in stock: YES", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    all_deals = []

    # ── Fetch from Retailer Clearance Pages (Playwright) ──
    if args.source in ("all", "clearance"):
        print("[deal-scanner] Scanning retailer clearance pages...", file=sys.stderr)
        clearance_deals = fetch_retailer_clearance(
            retailers=retailers,
            categories=categories,
            max_per_retailer=15,
        )
        print(f"  Total clearance products: {len(clearance_deals)}", file=sys.stderr)
        all_deals.extend(clearance_deals)

    # ── Fetch from Keepa Reverse Sourcing ──
    if args.source in ("all", "reverse") and args.match_amazon:
        print("\n[deal-scanner] Keepa reverse sourcing (bestsellers → retail check)...",
              file=sys.stderr)
        reverse_deals = fetch_keepa_reverse(
            categories=categories,
            count=args.count,
            keepa_tier=args.keepa_tier,
        )
        print(f"  Total reverse-sourced deals: {len(reverse_deals)}", file=sys.stderr)
        all_deals.extend(reverse_deals)

    # ── Fetch from Hip2Save RSS ──
    if args.source in ("all", "hip2save"):
        print("\n[deal-scanner] Fetching from Hip2Save RSS...", file=sys.stderr)
        hip_deals = fetch_hip2save_deals()
        print(f"  Total Hip2Save deals: {len(hip_deals)}", file=sys.stderr)
        all_deals.extend(hip_deals)

    # ── Fetch from Target Redsky API (legacy — may be dead) ──
    if args.source == "target":
        print("\n[deal-scanner] Fetching from Target Redsky API (legacy)...", file=sys.stderr)
        target_deals = fetch_target_products(categories=categories, count=24)
        print(f"  Total Target products: {len(target_deals)}", file=sys.stderr)
        if args.sale_only:
            target_deals = [d for d in target_deals if d.get("on_sale")]
        all_deals.extend(target_deals)

    # ── Fetch from Keepa Deals API (full queryJSON) ──
    if getattr(args, "keepa_deals", False):
        print("\n[deal-scanner] Fetching from Keepa Deals API...", file=sys.stderr)
        client = _get_keepa_client(args.keepa_tier)
        if client:
            from keepa_client import KeepaClient as _KC

            # Map CLI args to get_deals params
            price_type_map = getattr(_KC, "DEAL_PRICE_TYPES", {})
            sort_map = getattr(_KC, "DEAL_SORT_TYPES", {})

            price_type_int = price_type_map.get(
                getattr(args, "price_type", "amazon"), 0)
            sort_int = sort_map.get(getattr(args, "sort", "percent"), 4)

            # Build range params
            deals_price_range = (
                int(args.min_price * 100), int(args.max_price * 100))

            delta_range = None
            if getattr(args, "delta_min", None) is not None or getattr(args, "delta_max", None) is not None:
                d_min = int((args.delta_min or 0) * 100)
                d_max = int((args.delta_max or 99999) * 100)
                delta_range = (d_min, d_max)

            delta_pct_range = None
            if getattr(args, "delta_pct_min", None) is not None or getattr(args, "delta_pct_max", None) is not None:
                dp_min = int(args.delta_pct_min or 0)
                dp_max = int(args.delta_pct_max or 100)
                delta_pct_range = (dp_min, dp_max)

            bsr_range = None
            if getattr(args, "bsr_min", None) is not None or getattr(args, "bsr_max", None) is not None:
                bsr_range = (args.bsr_min or 1, args.bsr_max or 500000)

            brand_list = None
            if getattr(args, "brand", None):
                brand_list = [b.strip() for b in args.brand.split(",")]

            wh_conditions = None
            if getattr(args, "warehouse_conditions", None):
                wh_conditions = [int(c.strip()) for c in args.warehouse_conditions.split(",")]

            keepa_deals = client.get_deals(
                category=int(args.category) if args.category and args.category.isdigit() else 0,
                price_range=deals_price_range,
                sort_by=sort_int,
                count=args.count,
                delta_range=delta_range,
                delta_percent_range=delta_pct_range,
                sales_rank_range=bsr_range,
                price_types=[price_type_int],
                title_search=getattr(args, "title_search", ""),
                brand=brand_list,
                is_lowest=getattr(args, "lowest_ever", False),
                is_lowest_90=getattr(args, "lowest_90", False),
                is_back_in_stock=getattr(args, "back_in_stock", False),
                must_not_have_amazon_offer=getattr(args, "no_amazon_offer", False),
                single_variation=getattr(args, "single_variation", False),
                min_rating=getattr(args, "min_rating", None),
                warehouse_conditions=wh_conditions,
                date_range=getattr(args, "date_range", 0),
                sort_desc=getattr(args, "sort_desc", False),
                max_pages=getattr(args, "max_pages", 1),
            )
            print(f"  Total Keepa deals: {len(keepa_deals)}", file=sys.stderr)

            # Convert Keepa deal format to deal_scanner format
            for kd in keepa_deals:
                kd_price = kd.get("current_price", 0)
                if not kd_price or kd_price <= 0:
                    continue
                all_deals.append({
                    "name": kd.get("title", ""),
                    "price": kd_price,
                    "store": "Amazon",
                    "link": f"https://www.amazon.com/dp/{kd.get('asin', '')}",
                    "asin": kd.get("asin", ""),
                    "categories": [kd.get("category", "")] if kd.get("category") else [],
                    "source": "keepa_deals",
                    "amazon_price": kd_price,
                    "previous_price": kd.get("previous_price"),
                    "delta_percent": kd.get("delta_percent", 0),
                    "bsr": kd.get("bsr", 0),
                    "_pre_matched": True,  # Already from Amazon, skip Keepa search
                })
        else:
            print("  [keepa-deals] No KeepaClient available", file=sys.stderr)

    # ── Filter ──
    print(f"\n[deal-scanner] Filtering {len(all_deals)} total deals...", file=sys.stderr)

    # Price range filter
    filtered = [d for d in all_deals if d["price"] and args.min_price <= d["price"] <= args.max_price]
    print(f"  Price ${args.min_price}-${args.max_price}: {len(filtered)}", file=sys.stderr)

    # Category filter
    if args.category:
        cat = args.category.lower()
        filtered = [d for d in filtered if cat in d.get("categories", [])]
        print(f"  Category '{args.category}': {len(filtered)}", file=sys.stderr)

    # Remove duplicates (same product at different prices → keep cheapest)
    seen_names = {}
    for d in filtered:
        key = d["name"].lower()[:60]
        if key not in seen_names or d["price"] < seen_names[key]["price"]:
            seen_names[key] = d
    filtered = list(seen_names.values())
    print(f"  After dedup: {len(filtered)}", file=sys.stderr)

    # Sort by price (cheapest first — more likely to have good ROI)
    filtered.sort(key=lambda x: x["price"])

    # ── Stock Check (Target products only) ──
    if args.check_stock and args.source in ("all", "target"):
        print(f"\n[deal-scanner] Checking Target stock availability...", file=sys.stderr)
        from keepa_client import KeepaClient
        stock_checked = 0
        for deal in filtered:
            if deal.get("source") == "target" and deal.get("tcin"):
                stock_info = KeepaClient.check_target_stock(deal["tcin"])
                deal["stock"] = stock_info
                in_stock = stock_info.get("in_stock")
                status = "YES" if in_stock else ("NO" if in_stock is False else "?")
                deal["in_stock"] = in_stock
                stock_checked += 1
                time.sleep(0.3)
        print(f"  Checked {stock_checked} Target products", file=sys.stderr)

        # Move out-of-stock to end
        in_stock_deals = [d for d in filtered if d.get("in_stock") is not False]
        oos_deals = [d for d in filtered if d.get("in_stock") is False]
        filtered = in_stock_deals + oos_deals

    # ── Amazon Matching ──
    results = []
    skipped_pl = 0
    skipped_sellers = 0
    if args.match_amazon:
        print(f"\n[deal-scanner] Matching to Amazon via KeepaClient (tier: {args.keepa_tier})...",
              file=sys.stderr)
        for deal in filtered[:args.count * 3]:  # Check more to find count good ones
            if len(results) >= args.count:
                break

            # Skip out-of-stock if stock was checked
            if args.check_stock and deal.get("in_stock") is False:
                print(f"  SKIP | Out of stock | {deal['name'][:40]}", file=sys.stderr)
                continue

            # Pre-matched products (from keepa_reverse) skip Keepa search
            if deal.get("_pre_matched") and deal.get("amazon_price"):
                amz = {
                    "asin": deal.get("asin", ""),
                    "title": deal.get("name", ""),
                    "amazon_price": deal["amazon_price"],
                    "brand": deal.get("brand", ""),
                    "bsr": deal.get("bsr"),
                    "fba_seller_count": deal.get("fba_seller_count"),
                    "fbm_seller_count": deal.get("fbm_seller_count"),
                    "review_count": deal.get("review_count"),
                    "tokens_left": 999,
                }
            else:
                amz = match_amazon_keepa(
                    deal["name"][:80],
                    min_sellers=args.min_sellers,
                    no_private_label=args.no_private_label,
                    keepa_tier=args.keepa_tier,
                )

            if amz and amz.get("_skip"):
                # Product was matched but failed seller/PL checks
                reason = amz.get("_skip_reason", "filtered")
                if "Private label" in reason:
                    skipped_pl += 1
                else:
                    skipped_sellers += 1
                print(f"  SKIP | {reason} | {deal['name'][:40]}", file=sys.stderr)
                if amz.get("tokens_left", 99) <= 1:
                    print("  [keepa] Out of tokens — stopping", file=sys.stderr)
                    break
                continue

            if amz and amz.get("amazon_price"):
                deal["asin"] = amz["asin"]
                deal["amazon_price"] = amz["amazon_price"]
                deal["amazon_title"] = amz["title"]
                deal["bsr"] = amz.get("bsr")
                deal["fba_seller_count"] = amz.get("fba_seller_count")
                deal["fbm_seller_count"] = amz.get("fbm_seller_count")
                deal["amazon_on_listing"] = amz.get("amazon_on_listing", False)
                deal["private_label"] = amz.get("private_label", {})
                deal["price_trends"] = amz.get("price_trends", {})
                deal["review_count"] = amz.get("review_count")

                prof = calculate_profit(deal, amz)
                deal["profitability"] = prof
                results.append(deal)

                verdict = prof.get("verdict") or "?"
                roi = prof.get("roi_percent") or 0
                profit = prof.get("profit_per_unit") or 0
                tokens = amz.get("tokens_left", "?")
                fba_n = amz.get("fba_seller_count", "?")
                pl_flag = "Y" if (amz.get("private_label", {}).get("is_private_label")) else "N"
                trend = (amz.get("price_trends") or {}).get("trend", "?")
                print(f"  {verdict:>5} | ROI:{roi:>5.1f}% | ${profit:>5.2f} | "
                      f"${deal['price']:.2f} → ${amz['amazon_price']:.2f} AMZ | "
                      f"FBA:{fba_n} PL:{pl_flag} {trend} | "
                      f"ASIN:{amz['asin']} | tokens:{tokens} | "
                      f"{deal['name'][:30]}", file=sys.stderr)

                if amz.get("tokens_left", 99) <= 1:
                    print("  [keepa] Out of tokens — stopping", file=sys.stderr)
                    break
            else:
                print(f"  SKIP | No Amazon match | {deal['name'][:40]}", file=sys.stderr)
    else:
        # Without Amazon matching, just return filtered deals for review
        print(f"\n[deal-scanner] No Amazon matching — returning raw deals", file=sys.stderr)
        for deal in filtered[:args.count]:
            deal["profitability"] = {"verdict": "REVIEW", "roi_percent": 0, "profit_per_unit": 0}
            results.append(deal)

    # Sort by ROI
    results.sort(key=lambda x: x.get("profitability", {}).get("roi_percent", 0) or 0, reverse=True)
    results = results[:args.count]

    # Summary
    elapsed_ms = int((time.time() - start) * 1000)
    buy_count = sum(1 for r in results if r.get("profitability", {}).get("verdict") == "BUY")
    maybe_count = sum(1 for r in results if r.get("profitability", {}).get("verdict") == "MAYBE")

    # Push to Supabase
    if args.supabase:
        print(f"\n[deal-scanner] Pushing to Supabase...", file=sys.stderr)
        push_to_supabase(results, {
            "total_deals": len(results),
            "buy_count": buy_count,
            "maybe_count": maybe_count,
            "duration_ms": elapsed_ms,
        })

    # Output JSON
    sources_used = list(set(d.get("source", "unknown") for d in all_deals))

    output_data = {
        "deals": results,
        "count": len(results),
        "summary": {
            "sources": sources_used,
            "total_found": len(all_deals),
            "after_filters": len(filtered),
            "results": len(results),
            "buy_count": buy_count,
            "maybe_count": maybe_count,
            "skipped_private_label": skipped_pl,
            "skipped_low_sellers": skipped_sellers,
            "elapsed_ms": elapsed_ms,
            "filters": {
                "min_sellers": args.min_sellers if args.match_amazon else None,
                "no_private_label": args.no_private_label if args.match_amazon else None,
                "check_stock": args.check_stock,
                "keepa_tier": args.keepa_tier if args.match_amazon else None,
            },
        },
        "timestamp": datetime.now().isoformat(),
    }

    output_path = args.output or str(TMP_DIR / f"{ts}-deals.json")
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    # Print summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[deal-scanner v4] COMPLETE ({elapsed_ms / 1000:.1f}s)", file=sys.stderr)
    print(f"  Sources:       {', '.join(sources_used)}", file=sys.stderr)
    print(f"  Total found:   {len(all_deals)}", file=sys.stderr)
    print(f"  After filters: {len(filtered)}", file=sys.stderr)
    print(f"  Results:       {len(results)}", file=sys.stderr)
    print(f"  BUY:           {buy_count}", file=sys.stderr)
    print(f"  MAYBE:         {maybe_count}", file=sys.stderr)
    if args.match_amazon:
        print(f"  Skipped (PL):  {skipped_pl}", file=sys.stderr)
        print(f"  Skipped (sel): {skipped_sellers}", file=sys.stderr)
    print(f"  JSON:          {output_path}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # Print table (v3.0 — includes FBA#, PL?, Stock, Trend columns)
    if results:
        print(f"\n{'Verdict':>7} | {'ROI':>5} | {'Profit':>7} | "
              f"{'Price':>7} | {'AMZ$':>7} | {'FBA#':>4} | {'PL?':>3} | "
              f"{'Stock':>5} | {'Trend':>7} | {'Store':>10} | Product")
        print("─" * 130)
        for r in results:
            prof = r.get("profitability", {})
            amz = r.get("amazon_price")
            amz_str = f"${amz:.2f}" if amz else "  N/A"
            verdict = prof.get("verdict") or "?"
            roi = prof.get("roi_percent") or 0
            profit = prof.get("profit_per_unit") or 0
            price = r.get("price") or 0
            store = r.get("store") or "?"
            asin = r.get("asin", "")
            asin_str = f" [{asin}]" if asin else ""

            # v3.0 columns
            fba_n = r.get("fba_seller_count")
            fba_str = str(fba_n) if fba_n is not None else "?"
            pl_info = r.get("private_label", {})
            pl_str = "Y" if (isinstance(pl_info, dict) and pl_info.get("is_private_label")) else "N"
            in_stock = r.get("in_stock")
            stock_str = "YES" if in_stock is True else ("NO" if in_stock is False else " -")
            trends = r.get("price_trends", {})
            trend_str = (trends.get("trend", "-") if isinstance(trends, dict) else "-")

            print(f"{verdict:>7} | "
                  f"{roi:>4.0f}% | "
                  f"${profit:>5.2f} | "
                  f"${price:>6.2f} | "
                  f"{amz_str:>7} | "
                  f"{fba_str:>4} | "
                  f"{pl_str:>3} | "
                  f"{stock_str:>5} | "
                  f"{trend_str:>7} | "
                  f"{store:>10} | "
                  f"{r.get('name','')[:30]}{asin_str}")

        # Print buy links for BUY/MAYBE deals
        buys = [r for r in results if r.get("profitability", {}).get("verdict") in ("BUY", "MAYBE")]
        if buys:
            print(f"\n{'='*60}")
            print(f"  Profitable Deals — Buy Links")
            print(f"{'='*60}")
            for r in buys:
                prof = r.get("profitability", {})
                asin = r.get("asin", "")
                fba_n = r.get("fba_seller_count", "?")
                reviews = r.get("review_count", "?")
                bsr = r.get("bsr", "?")
                trends = r.get("price_trends", {})
                trend_str = (trends.get("trend", "?") if isinstance(trends, dict) else "?")

                print(f"\n  [{prof.get('verdict')}] {r.get('name','')[:50]}")
                print(f"    Retail:  {r.get('store')} @ ${r.get('price', 0):.2f}")
                print(f"    Amazon:  ${r.get('amazon_price', 0):.2f} | "
                      f"ROI: {prof.get('roi_percent', 0):.0f}% | "
                      f"Profit: ${prof.get('profit_per_unit', 0):.2f}")
                print(f"    FBA Sellers: {fba_n} | Reviews: {reviews} | BSR: {bsr} | Trend: {trend_str}")
                if asin:
                    print(f"    Amazon:  https://www.amazon.com/dp/{asin}")
                print(f"    Retail:  {r.get('link', 'N/A')}")


if __name__ == "__main__":
    main()
