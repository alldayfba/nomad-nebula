#!/usr/bin/env python3
"""
Script: keepa_client.py
Purpose: Centralized Keepa API client — single source of truth for all Keepa
         interactions across the sourcing pipeline. Replaces duplicated parsing
         across deal_scanner.py, fast_grocery_scan.py, keepa_deal_hunter.py,
         match_amazon_products.py, and calculate_fba_profitability.py.

Key fixes over previous inline implementations:
  - Correct CSV indices: 34 = FBA seller count, 35 = FBM seller count (NOT 11)
  - Offers parameter support: returns actual seller list with names
  - Private label detection: 3-tier (offers data → CSV indices → heuristic)
  - Token budget management: allocates tokens across pipeline stages
  - Price trend extraction: 30d/90d/180d averages, direction, volatility

CSV Index Reference (Keepa API):
  0  = Amazon price history
  1  = New 3rd party price
  2  = Used price
  3  = Sales rank history
  4  = List price
  5  = Collectible price
  7  = New 3P FBM shipping
  10 = FBA price (Buy Box eligible)
  11 = New offer count (total, includes FBM — NOT reliable for FBA count)
  18 = Buy Box price
  27 = Used offer count
  31 = Review count history
  34 = FBA seller count (count of Buy Box eligible offers)
  35 = FBM seller count (merchant-fulfilled only)

Usage:
  from keepa_client import KeepaClient

  client = KeepaClient(tier="pro")
  product = client.search_product("Bigelow Earl Grey Tea")
  product = client.get_product("B000GG5IXM")
  product = client.get_product("B000GG5IXM", offers=20)  # includes seller list
"""

import os
import sys
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


# ── CSV Index Constants ──────────────────────────────────────────────────────

CSV_AMAZON_PRICE = 0
CSV_NEW_3P_PRICE = 1
CSV_USED_PRICE = 2
CSV_SALES_RANK = 3
CSV_LIST_PRICE = 4
CSV_FBA_PRICE = 10
CSV_NEW_OFFER_COUNT = 11   # Total new offers (FBA + FBM) — NOT reliable alone
CSV_BUY_BOX_PRICE = 18
CSV_USED_OFFER_COUNT = 27
CSV_REVIEW_COUNT = 31
CSV_FBA_SELLER_COUNT = 34  # FBA-only seller count (Buy Box eligible)
CSV_FBM_SELLER_COUNT = 35  # FBM-only seller count

# ── Tier Configuration ───────────────────────────────────────────────────────

TIER_CONFIG = {
    "basic": {
        "tokens_per_min": 5,
        "delay_seconds": 13.0,   # 60/5 = 12s + 1s buffer
        "max_batch_size": 20,
        "offers_feasible": False,
    },
    "pro": {
        "tokens_per_min": 20,
        "delay_seconds": 4.0,    # 60/20 = 3s + 1s buffer
        "max_batch_size": 100,
        "offers_feasible": True,
    },
}


# ── Helper Functions ─────────────────────────────────────────────────────────

def _last_valid_price(arr):
    """Return the last non-negative value from a Keepa CSV array, divided by 100."""
    if not arr:
        return None
    for i in range(len(arr) - 1, 0, -2):
        if arr[i] >= 0:
            return arr[i] / 100.0
    return None


def _last_valid_raw(arr):
    """Return the last non-negative value from a Keepa CSV array (no /100)."""
    if not arr:
        return None
    for i in range(len(arr) - 1, 0, -2):
        if arr[i] >= 0:
            return arr[i]
    return None


def _average_price(arr, n_pairs=60):
    """Average last n_pairs price values from a Keepa CSV array, divided by 100."""
    if not arr:
        return None
    values = []
    pairs = list(zip(arr[::2], arr[1::2]))
    for _, val in pairs[-n_pairs:]:
        if val >= 0:
            values.append(val / 100.0)
    return round(sum(values) / len(values), 2) if values else None


def _average_raw(arr, n_pairs=60):
    """Average last n_pairs raw values from a Keepa CSV array (no /100)."""
    if not arr:
        return None
    values = []
    pairs = list(zip(arr[::2], arr[1::2]))
    for _, val in pairs[-n_pairs:]:
        if val >= 0:
            values.append(val)
    return round(sum(values) / len(values), 1) if values else None


def _csv_at(csv_data, index):
    """Safely get CSV array at given index."""
    if csv_data and index < len(csv_data):
        return csv_data[index]
    return None


# ── Token Budget ─────────────────────────────────────────────────────────────

class TokenBudget:
    """Allocates Keepa tokens across pipeline stages to prevent exhaustion.

    Default allocation:
      40% search — finding products
      30% product — fetching details
      30% offers  — seller verification (pro tier only)
    """

    def __init__(self, total_tokens, search_pct=0.40, product_pct=0.30, offers_pct=0.30):
        self.total = total_tokens
        self.budgets = {
            "search": int(total_tokens * search_pct),
            "product": int(total_tokens * product_pct),
            "offers": int(total_tokens * offers_pct),
        }
        self.spent = {"search": 0, "product": 0, "offers": 0}

    def can_spend(self, stage, cost=1):
        """Check if we have budget for this stage."""
        return self.spent[stage] + cost <= self.budgets[stage]

    def spend(self, stage, cost=1):
        """Record token spend for a stage."""
        self.spent[stage] += cost

    def remaining(self, stage):
        """Tokens remaining for a stage."""
        return self.budgets[stage] - self.spent[stage]

    def summary(self):
        return {stage: f"{self.spent[stage]}/{self.budgets[stage]}"
                for stage in self.budgets}


# ── KeepaClient ──────────────────────────────────────────────────────────────

class KeepaClient:
    """Centralized Keepa API client with correct CSV parsing, rate limiting,
    and private label detection."""

    BASE_URL = "https://api.keepa.com"

    def __init__(self, api_key=None, tier="pro"):
        self.api_key = api_key or os.getenv("KEEPA_API_KEY", "")
        if not self.api_key:
            raise ValueError("KEEPA_API_KEY not set — pass api_key or set in .env")

        self.tier = tier
        self.config = TIER_CONFIG.get(tier, TIER_CONFIG["basic"])
        self.delay = self.config["delay_seconds"]
        self.last_call_time = 0
        self.tokens_left = None

    def _rate_limit(self):
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self.last_call_time
        if elapsed < self.delay:
            wait = self.delay - elapsed
            time.sleep(wait)
        self.last_call_time = time.time()

    def _request(self, endpoint, params):
        """Make a rate-limited request to Keepa API."""
        self._rate_limit()
        params["key"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                print("[keepa] Rate limited (429) — waiting 60s", file=sys.stderr)
                time.sleep(60)
                r = requests.get(url, params=params, timeout=30)
            if r.status_code != 200:
                print(f"[keepa] HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
                return None
            data = r.json()
            self.tokens_left = data.get("tokensLeft")
            if self.tokens_left is not None and self.tokens_left <= 0:
                print(f"[keepa] Tokens exhausted ({self.tokens_left})", file=sys.stderr)
            return data
        except Exception as e:
            print(f"[keepa] Request error: {e}", file=sys.stderr)
            return None

    def check_tokens(self):
        """Check current token balance."""
        data = self._request("token", {})
        if data:
            self.tokens_left = data.get("tokensLeft", 0)
            return {
                "tokens_left": self.tokens_left,
                "refill_rate": data.get("refillRate", 0),
                "refill_in": data.get("refillIn", 0),
            }
        return None

    def wait_for_tokens(self, min_tokens=5):
        """Block until we have enough tokens."""
        while True:
            info = self.check_tokens()
            if info and info["tokens_left"] >= min_tokens:
                return info["tokens_left"]
            refill_rate = info["refill_rate"] if info else 5
            wait = (abs(self.tokens_left or 0) + min_tokens) * 60 // max(refill_rate, 1) + 5
            print(f"[keepa] Waiting {wait}s for tokens (have {self.tokens_left}, need {min_tokens})",
                  file=sys.stderr)
            time.sleep(wait)

    # ── Search ───────────────────────────────────────────────────────────────

    def search_product(self, query, domain=1):
        """Search Keepa for a product by name or UPC. Returns parsed product or None."""
        data = self._request("search", {
            "domain": domain,
            "type": "product",
            "term": query,
        })
        if not data or not data.get("products"):
            return None
        return self.parse_product(data["products"][0])

    # ── Product Lookup ───────────────────────────────────────────────────────

    def get_product(self, asin, domain=1, offers=0, stats=180):
        """Fetch product data for a single ASIN.

        Args:
            asin: Amazon ASIN
            offers: Number of offers to include (0 = none, 20-100 for seller list)
            stats: Days of stats to include (0 = none)

        Returns: Parsed product dict with seller data, or None.
        """
        params = {
            "domain": domain,
            "asin": asin,
            "history": 1,
        }
        if stats:
            params["stats"] = stats
        if offers > 0:
            params["offers"] = offers
        data = self._request("product", params)
        if not data or not data.get("products"):
            return None
        raw = data["products"][0]
        parsed = self.parse_product(raw)
        if offers > 0:
            parsed["offers_data"] = self.parse_offers(raw)
        # Enrich with BSR drops and Amazon OOS analysis
        bsr_drop_data = self.get_bsr_drops(raw)
        parsed["bsr_drops_30d"] = bsr_drop_data["drops_30d"]
        parsed["bsr_drops_60d"] = bsr_drop_data["drops_60d"]
        parsed["bsr_drops_90d"] = bsr_drop_data["drops_90d"]
        parsed["est_sales_from_drops"] = bsr_drop_data["est_sales_monthly"]
        parsed["amazon_oos_pct"] = self.get_amazon_oos_pct(raw)
        return parsed

    def get_products_batch(self, asins, domain=1, offers=0, stats=1):
        """Fetch product data for multiple ASINs (max 100 per call).

        Token cost: 1 per ASIN + additional for offers.
        """
        if not asins:
            return []
        batch = asins[:self.config["max_batch_size"]]
        params = {
            "domain": domain,
            "asin": ",".join(batch),
        }
        if stats:
            params["stats"] = stats
        if offers > 0:
            params["offers"] = offers
        data = self._request("product", params)
        if not data or not data.get("products"):
            return []
        results = []
        for raw in data["products"]:
            parsed = self.parse_product(raw)
            if offers > 0:
                parsed["offers_data"] = self.parse_offers(raw)
            # Enrich with BSR drops and Amazon OOS analysis
            bsr_drop_data = self.get_bsr_drops(raw)
            parsed["bsr_drops_30d"] = bsr_drop_data["drops_30d"]
            parsed["bsr_drops_60d"] = bsr_drop_data["drops_60d"]
            parsed["bsr_drops_90d"] = bsr_drop_data["drops_90d"]
            parsed["est_sales_from_drops"] = bsr_drop_data["est_sales_monthly"]
            parsed["amazon_oos_pct"] = self.get_amazon_oos_pct(raw)
            results.append(parsed)
        return results

    def get_bestsellers(self, category_id, domain=1):
        """Get bestseller ASINs for a Keepa category ID."""
        data = self._request("bestsellers", {
            "domain": domain,
            "category": category_id,
        })
        if not data:
            return []
        return data.get("bestSellersList", {}).get("asinList", [])

    def get_deals(self, category=0, domain=1, price_range=(500, 5000),
                  sort_by=3, count=150):
        """Fetch current Keepa deals (products with recent price changes).

        Uses POST endpoint. Returns products sorted by price volatility.

        Args:
            category: Keepa category ID (0 = all categories)
            domain: 1 = Amazon.com
            price_range: (min_cents, max_cents) — e.g. (500, 5000) = $5-$50
            sort_by: 3 = by delta percentage
            count: max results (up to 150 per request)

        Cost: 5 tokens per request.
        Returns: list of deal dicts with ASIN, title, prices, delta.
        """
        self._rate_limit()
        selection = {
            "page": 0,
            "domainId": domain,
            "excludeCategories": [],
            "includeCategories": [category] if category else [],
            "priceTypes": [0],  # 0 = Amazon price
            "salesRankRange": [1, 500000],
            "currentRange": list(price_range),
            "isLowest": False,
            "isLowestOffer": False,
            "isOutOfStock": False,
            "titleSearch": "",
            "isRangeEnabled": True,
            "isFilterEnabled": True,
            "hasReviews": True,
            "isPrimeExclusive": False,
            "mustHaveAmazonOffer": False,
            "mustNotHaveAmazonOffer": False,
            "sortType": sort_by,
            "dateRange": 0,  # 0 = last 24h
        }

        try:
            r = requests.post(
                f"{self.BASE_URL}/deal",
                params={"key": self.api_key, "domain": domain},
                json=selection,
                timeout=30,
            )
            if r.status_code != 200:
                print(f"[keepa] Deals HTTP {r.status_code}: {r.text[:200]}",
                      file=sys.stderr)
                return []
            data = r.json()
            self.tokens_left = data.get("tokensLeft")
        except Exception as e:
            print(f"[keepa] Deals request error: {e}", file=sys.stderr)
            return []

        deal_items = data.get("deals", {}).get("dr", [])

        deals = []
        for d in deal_items[:count]:
            asin = d.get("asin", "")
            title = d.get("title", "")
            current = d.get("current", [])
            delta = d.get("delta", [])       # 2D: [time_range][price_type]
            delta_pct = d.get("deltaPercent", [])  # 2D: same

            # current[0] = Amazon price in cents (-1 = no data, -2 = OOS)
            amz_price = 0
            if current and isinstance(current, list) and len(current) > 0:
                raw_price = current[0]
                if isinstance(raw_price, (int, float)) and raw_price > 0:
                    amz_price = raw_price / 100.0

            # Try Buy Box price (index 18) if Amazon price unavailable
            if amz_price <= 0 and isinstance(current, list) and len(current) > 18:
                bb_price = current[18]
                if isinstance(bb_price, (int, float)) and bb_price > 0:
                    amz_price = bb_price / 100.0

            # Try New 3P price (index 1) as last resort
            if amz_price <= 0 and isinstance(current, list) and len(current) > 1:
                new_price = current[1]
                if isinstance(new_price, (int, float)) and new_price > 0:
                    amz_price = new_price / 100.0

            if amz_price <= 0:
                continue

            # delta[0][0] = 24h Amazon price change in cents
            price_delta = 0
            pct_delta = 0
            if delta and isinstance(delta, list) and len(delta) > 0:
                row = delta[0]
                if isinstance(row, list) and len(row) > 0:
                    val = row[0]
                    if isinstance(val, (int, float)):
                        price_delta = val / 100.0
            if delta_pct and isinstance(delta_pct, list) and len(delta_pct) > 0:
                row = delta_pct[0]
                if isinstance(row, list) and len(row) > 0:
                    val = row[0]
                    if isinstance(val, (int, float)):
                        pct_delta = val

            # Category from categoryTree
            cat_name = ""
            cat_tree = d.get("categoryTree")
            if cat_tree and isinstance(cat_tree, list):
                cat_name = cat_tree[-1].get("name", "") if cat_tree else ""

            deals.append({
                "asin": asin,
                "title": title,
                "current_price": round(amz_price, 2),
                "previous_price": round(amz_price - price_delta, 2),
                "delta_percent": round(pct_delta, 1),
                "category": cat_name,
                "bsr": d.get("salesRank") or 0,
                "image": d.get("image", ""),
            })

        print(f"[keepa] Deals API returned {len(deals)} items (cost: 5 tokens)",
              file=sys.stderr)
        return deals

    # ── Parsing ──────────────────────────────────────────────────────────────

    def parse_product(self, raw):
        """Parse a raw Keepa product dict into a clean, canonical format.

        Uses CORRECT CSV indices:
          34 = FBA seller count (NOT 11)
          35 = FBM seller count
        """
        csv_data = raw.get("csv", [])
        stats = raw.get("stats", {}) or {}

        # ── Prices ───────────────────────────────────────────────────────
        amazon_price = _last_valid_price(_csv_at(csv_data, CSV_AMAZON_PRICE))
        new_3p_price = _last_valid_price(_csv_at(csv_data, CSV_NEW_3P_PRICE))
        fba_price = _last_valid_price(_csv_at(csv_data, CSV_FBA_PRICE))
        buy_box_price = _last_valid_price(_csv_at(csv_data, CSV_BUY_BOX_PRICE))

        # Best sell price: buy box > FBA > Amazon > 3P
        sell_price = buy_box_price or fba_price or amazon_price or new_3p_price

        # ── BSR ──────────────────────────────────────────────────────────
        bsr = _last_valid_raw(_csv_at(csv_data, CSV_SALES_RANK))
        # Also check salesRankCurrent field
        if bsr is None:
            sr = raw.get("salesRankCurrent")
            if sr is not None and sr > 0:
                bsr = sr

        # ── Seller Counts (CORRECT indices) ──────────────────────────────
        fba_seller_count = _last_valid_raw(_csv_at(csv_data, CSV_FBA_SELLER_COUNT))
        fbm_seller_count = _last_valid_raw(_csv_at(csv_data, CSV_FBM_SELLER_COUNT))
        total_offer_count = _last_valid_raw(_csv_at(csv_data, CSV_NEW_OFFER_COUNT))

        # Also check fbaOfferCount field (Keepa sometimes includes this)
        if fba_seller_count is None:
            fba_seller_count = raw.get("fbaOfferCount")

        # Convert to int if present
        if fba_seller_count is not None:
            fba_seller_count = int(fba_seller_count)
        if fbm_seller_count is not None:
            fbm_seller_count = int(fbm_seller_count)
        if total_offer_count is not None:
            total_offer_count = int(total_offer_count)

        # ── Amazon on listing (recency-checked) ─────────────────────────
        # Only flag Amazon as "on listing" if the price data is recent (within 30 days).
        # Keepa CSV: [timestamp, value, timestamp, value, ...] — timestamps in Keepa minutes
        # (minutes since 2011-01-01 00:00 UTC).
        amazon_on_listing = False
        amz_csv = _csv_at(csv_data, CSV_AMAZON_PRICE)
        if amz_csv and len(amz_csv) >= 2:
            last_ts = amz_csv[-2]
            last_price = amz_csv[-1]
            keepa_now = int((time.time() - 1293840000) / 60)  # minutes since 2011-01-01
            is_recent = (keepa_now - last_ts) < 43200  # 30 days in minutes
            amazon_on_listing = last_price > 0 and is_recent

        # ── UPC / EAN ────────────────────────────────────────────────────
        upc_list = raw.get("upcList", [])
        ean_list = raw.get("eanList", [])
        upc = upc_list[0] if upc_list else (ean_list[0] if ean_list else "")

        # ── Category ─────────────────────────────────────────────────────
        cat_tree = raw.get("categoryTree", [])
        category = cat_tree[-1].get("name", "") if cat_tree else ""

        # ── Reviews ──────────────────────────────────────────────────────
        review_count = None
        rating = None
        if stats.get("current") and len(stats["current"]) > 31:
            rc = stats["current"][31]
            if isinstance(rc, (int, float)) and rc > 0:
                review_count = int(rc)
        # Keepa also has these top-level fields
        if review_count is None:
            review_count = raw.get("reviewCount")
        rating = raw.get("rating")

        # ── Brand ────────────────────────────────────────────────────────
        brand = raw.get("brand", "")

        # ── Price Trends ─────────────────────────────────────────────────
        price_trends = self.extract_price_trends(csv_data)

        # ── Private Label Detection ──────────────────────────────────────
        pl_result = self.detect_private_label(
            brand=brand,
            fba_seller_count=fba_seller_count,
            fbm_seller_count=fbm_seller_count,
            total_offer_count=total_offer_count,
            amazon_on_listing=amazon_on_listing,
            offers_data=None,  # filled later if offers param was used
        )

        return {
            "asin": raw.get("asin", ""),
            "title": raw.get("title", ""),
            "brand": brand,
            "upc": upc,
            "category": category,
            # Prices
            "amazon_price": amazon_price,
            "new_3p_price": new_3p_price,
            "fba_price": fba_price,
            "buy_box_price": buy_box_price,
            "sell_price": sell_price,
            # Rankings
            "bsr": int(bsr) if bsr else None,
            "review_count": review_count,
            "rating": rating,
            # Seller counts (CORRECT — index 34/35)
            "fba_seller_count": fba_seller_count,
            "fbm_seller_count": fbm_seller_count,
            "total_offer_count": total_offer_count,
            "amazon_on_listing": amazon_on_listing,
            # Analysis
            "price_trends": price_trends,
            "private_label": pl_result,
            # Metadata
            "tokens_left": self.tokens_left,
            "data_source": "keepa",
        }

    def parse_offers(self, raw):
        """Parse the offers array from a Keepa product response.

        Only available when offers=20+ was passed in the API call.
        Returns list of seller dicts with name, FBA flag, price, stock estimate.
        """
        offers_raw = raw.get("offers", [])
        if not offers_raw:
            return []

        sellers = []
        for offer in offers_raw:
            seller_name = offer.get("sellerName", "") or offer.get("seller", "")
            is_fba = offer.get("isFBA", False)
            is_amazon = offer.get("isAmazon", False)
            condition = offer.get("condition", 1)  # 1 = new
            if condition != 1:
                continue  # Only care about new condition

            # Price from offer
            offer_csv = offer.get("offerCSV", [])
            price = None
            if offer_csv:
                # offerCSV format: [timestamp, price, shipping, timestamp, price, shipping, ...]
                # Walk backwards to find last valid price
                for i in range(len(offer_csv) - 3, -1, -3):
                    if i + 1 < len(offer_csv) and offer_csv[i + 1] >= 0:
                        price = offer_csv[i + 1] / 100.0
                        break

            # Stock estimate from stockCSV
            stock = None
            stock_csv = offer.get("stockCSV", [])
            if stock_csv:
                for i in range(len(stock_csv) - 1, 0, -2):
                    if stock_csv[i] >= 0:
                        stock = stock_csv[i]
                        break

            # Buy box win percentage
            buy_box_pct = offer.get("buyBoxPercentage")
            is_buy_box_winner = offer.get("isBuyBoxWinner", False)

            sellers.append({
                "seller_name": seller_name,
                "seller_id": offer.get("sellerId", ""),
                "is_fba": is_fba,
                "is_amazon": is_amazon,
                "price": price,
                "stock_estimate": stock,
                "buy_box_percentage": buy_box_pct,
                "is_buy_box_winner": is_buy_box_winner,
                "last_seen": offer.get("lastSeen"),
            })

        return sellers

    # ── Private Label Detection ──────────────────────────────────────────

    def detect_private_label(self, brand, fba_seller_count=None,
                              fbm_seller_count=None, total_offer_count=None,
                              amazon_on_listing=False, offers_data=None):
        """3-tier private label detection.

        Tier 1 (definitive): Offers data shows seller name matches brand name
        Tier 2 (strong signal): FBA count == 1 AND FBM count <= 1
        Tier 3 (heuristic): Total offers == 1 AND no Amazon

        Returns:
            dict with is_private_label (bool), confidence (str), reason (str)
        """
        brand_lower = (brand or "").lower().strip()

        # ── Tier 1: Check offers data (most reliable) ────────────────────
        if offers_data:
            fba_sellers = [s for s in offers_data if s["is_fba"] and not s["is_amazon"]]
            if len(fba_sellers) == 1:
                seller_name = fba_sellers[0]["seller_name"].lower().strip()
                # Check if seller name matches or contains brand
                if brand_lower and (
                    brand_lower in seller_name or
                    seller_name in brand_lower or
                    _fuzzy_brand_match(brand_lower, seller_name)
                ):
                    return {
                        "is_private_label": True,
                        "confidence": "definitive",
                        "reason": f"Only FBA seller '{fba_sellers[0]['seller_name']}' matches brand '{brand}'",
                    }
            if len(fba_sellers) >= 2:
                return {
                    "is_private_label": False,
                    "confidence": "definitive",
                    "reason": f"{len(fba_sellers)} independent FBA sellers found",
                }

        # ── Tier 2: CSV-based seller counts ──────────────────────────────
        # IMPORTANT: CSV indices 34/35 are notoriously unreliable without
        # offers=20 (expensive). They often show "1" for products that
        # actually have many sellers. Only use as a weak signal.
        if fba_seller_count is not None:
            if fba_seller_count >= 2:
                return {
                    "is_private_label": False,
                    "confidence": "strong",
                    "reason": f"{fba_seller_count} FBA sellers on listing",
                }
            # fba_seller_count == 0 or 1: CSV data is unreliable, don't hard-flag
            # Check known brands first
            try:
                from auto_ungated_brands import is_auto_ungated as _is_ungated
                if _is_ungated(brand or ""):
                    return {
                        "is_private_label": False,
                        "confidence": "possible",
                        "reason": f"CSV shows {fba_seller_count} FBA seller(s) but '{brand}' is a known national brand — CSV likely stale",
                    }
            except ImportError:
                pass
            # For unknown brands with 0-1 FBA sellers, flag as "possible" not "definitive"
            return {
                "is_private_label": True,
                "confidence": "possible",
                "reason": f"CSV shows {fba_seller_count} FBA seller(s) (FBM: {fbm_seller_count or 0}) — verify with offers data",
            }

        # ── Tier 3: Heuristic fallback ───────────────────────────────────
        if total_offer_count is not None:
            if total_offer_count <= 1 and not amazon_on_listing:
                return {
                    "is_private_label": True,
                    "confidence": "possible",
                    "reason": f"Only {total_offer_count} total offer(s), no Amazon",
                }
            if total_offer_count >= 3:
                return {
                    "is_private_label": False,
                    "confidence": "possible",
                    "reason": f"{total_offer_count} total offers",
                }

        return {
            "is_private_label": None,  # Unknown
            "confidence": "unknown",
            "reason": "Insufficient data to determine",
        }

    # ── Price Trends ─────────────────────────────────────────────────────

    def extract_price_trends(self, csv_data):
        """Extract price trend data from CSV arrays.

        Returns dict with 30d/90d/180d averages, trend direction, and volatility.
        """
        bb_arr = _csv_at(csv_data, CSV_BUY_BOX_PRICE)
        amz_arr = _csv_at(csv_data, CSV_AMAZON_PRICE)
        price_arr = bb_arr or amz_arr

        if not price_arr:
            return {"trend": "unknown", "avg_30d": None, "avg_90d": None, "avg_180d": None}

        current = _last_valid_price(price_arr)
        avg_30d = _average_price(price_arr, 60)     # ~30 days
        avg_90d = _average_price(price_arr, 180)    # ~90 days
        avg_180d = _average_price(price_arr, 360)   # ~180 days

        # Determine trend direction
        trend = "stable"
        if current and avg_30d:
            pct_change = (current - avg_30d) / avg_30d * 100
            if pct_change > 10:
                trend = "rising"
            elif pct_change < -10:
                trend = "falling"

        # Volatility: coefficient of variation over last 90 days
        volatility = None
        if price_arr:
            values = []
            pairs = list(zip(price_arr[::2], price_arr[1::2]))
            for _, val in pairs[-180:]:
                if val >= 0:
                    values.append(val / 100.0)
            if len(values) >= 5:
                mean = sum(values) / len(values)
                if mean > 0:
                    variance = sum((v - mean) ** 2 for v in values) / len(values)
                    volatility = round((variance ** 0.5) / mean * 100, 1)

        # Historical low detection
        at_historical_low = False
        if current and price_arr:
            all_prices = [price_arr[i] / 100.0 for i in range(1, len(price_arr), 2) if price_arr[i] >= 0]
            if all_prices:
                hist_low = min(all_prices)
                at_historical_low = current <= hist_low * 1.05  # within 5% of all-time low

        return {
            "current": current,
            "avg_30d": avg_30d,
            "avg_90d": avg_90d,
            "avg_180d": avg_180d,
            "trend": trend,
            "volatility_pct": volatility,
            "at_historical_low": at_historical_low,
        }

    # ── Out-of-Stock Deals ───────────────────────────────────────────────

    def get_oos_deals(self, category=0, domain=1, price_range=(500, 5000),
                      min_bsr=1, max_bsr=100000, count=150):
        """Find Amazon listings where FBA sellers have dropped off (out-of-stock).

        This is the highest-margin OA signal: products still available at retail
        but with no/few Amazon sellers = you enter as sole seller.

        Uses POST /deal endpoint with isOutOfStock=True.

        Args:
            category: Keepa category ID (0 = all)
            domain: 1 = Amazon.com
            price_range: (min_cents, max_cents)
            min_bsr: Minimum BSR (ensures demand)
            max_bsr: Maximum BSR (ensures it's not a dead listing)
            count: Max results (up to 150 per request)

        Cost: 5 tokens per request.
        Returns: list of deal dicts with ASIN, title, prices, OOS metadata.
        """
        self._rate_limit()
        selection = {
            "page": 0,
            "domainId": domain,
            "excludeCategories": [],
            "includeCategories": [category] if category else [],
            "priceTypes": [0, 1, 18],  # Amazon price, New 3P, Buy Box
            "salesRankRange": [min_bsr, max_bsr],
            "currentRange": list(price_range),
            "isLowest": False,
            "isLowestOffer": False,
            "isOutOfStock": True,
            "titleSearch": "",
            "isRangeEnabled": True,
            "isFilterEnabled": True,
            "hasReviews": True,
            "isPrimeExclusive": False,
            "mustHaveAmazonOffer": False,
            "mustNotHaveAmazonOffer": True,
            "sortType": 3,  # Sort by delta percentage
            "dateRange": 1,  # Last 7 days
        }

        try:
            r = requests.post(
                f"{self.BASE_URL}/deal",
                params={"key": self.api_key, "domain": domain},
                json=selection,
                timeout=30,
            )
            if r.status_code != 200:
                print(f"[keepa] OOS Deals HTTP {r.status_code}: {r.text[:200]}",
                      file=sys.stderr)
                return []
            data = r.json()
            self.tokens_left = data.get("tokensLeft")
        except Exception as e:
            print(f"[keepa] OOS Deals request error: {e}", file=sys.stderr)
            return []

        deal_items = data.get("deals", {}).get("dr", [])

        deals = []
        for d in deal_items[:count]:
            asin = d.get("asin", "")
            title = d.get("title", "")
            current = d.get("current", [])

            # Get last known price (Buy Box or New 3P)
            last_price = 0
            for idx in [18, 1, 0]:  # Buy Box, New 3P, Amazon
                if isinstance(current, list) and len(current) > idx:
                    val = current[idx]
                    if isinstance(val, (int, float)) and val > 0:
                        last_price = val / 100.0
                        break

            if last_price <= 0:
                continue

            # Category
            cat_name = ""
            cat_tree = d.get("categoryTree")
            if cat_tree and isinstance(cat_tree, list):
                cat_name = cat_tree[-1].get("name", "") if cat_tree else ""

            # Review count from stats
            review_count = None
            stats = d.get("stats", {}) or {}
            if stats.get("current") and len(stats["current"]) > 31:
                rc = stats["current"][31]
                if isinstance(rc, (int, float)) and rc > 0:
                    review_count = int(rc)

            deals.append({
                "asin": asin,
                "title": title,
                "last_known_price": round(last_price, 2),
                "category": cat_name,
                "bsr": d.get("salesRank") or 0,
                "review_count": review_count,
                "image": d.get("image", ""),
                "is_oos": True,
            })

        print(f"[keepa] OOS Deals API returned {len(deals)} items (cost: 5 tokens)",
              file=sys.stderr)
        return deals

    def get_seller_count_history(self, asin, domain=1):
        """Get FBA seller count time-series for an ASIN to estimate OOS duration.

        Extracts CSV index 34 (FBA seller count) over time.

        Args:
            asin: Amazon ASIN
            domain: 1 = Amazon.com

        Returns:
            dict with days_oos, last_fba_count, trend, history (list of {date, count})
        """
        data = self._request("product", {
            "domain": domain,
            "asin": asin,
            "history": 1,
            "stats": 90,
        })
        if not data or not data.get("products"):
            return {"days_oos": None, "last_fba_count": None, "trend": "unknown"}

        raw = data["products"][0]
        csv_data = raw.get("csv", [])
        fba_arr = _csv_at(csv_data, CSV_FBA_SELLER_COUNT)

        if not fba_arr or len(fba_arr) < 4:
            return {"days_oos": None, "last_fba_count": None, "trend": "unknown"}

        # Parse time-series: [keepa_timestamp, count, keepa_timestamp, count, ...]
        keepa_epoch = 1293840000  # 2011-01-01 00:00 UTC in unix seconds
        pairs = list(zip(fba_arr[::2], fba_arr[1::2]))

        history = []
        for ts_keepa, count in pairs:
            if count < 0:
                count = 0  # Keepa uses -1 for no data
            unix_ts = keepa_epoch + (ts_keepa * 60)
            history.append({"timestamp": unix_ts, "fba_count": count})

        # Determine how long it's been at 0 FBA sellers
        days_oos = None
        if history:
            last_count = history[-1]["fba_count"]
            if last_count == 0:
                # Walk backwards to find when it went to 0
                oos_start = history[-1]["timestamp"]
                for entry in reversed(history):
                    if entry["fba_count"] > 0:
                        break
                    oos_start = entry["timestamp"]
                days_oos = round((time.time() - oos_start) / 86400, 1)

        # Trend: compare last count to 30-day average
        last_fba = history[-1]["fba_count"] if history else None
        recent_counts = [h["fba_count"] for h in history[-60:]]  # ~30 days
        avg_recent = sum(recent_counts) / len(recent_counts) if recent_counts else 0

        trend = "stable"
        if last_fba is not None and avg_recent > 0:
            if last_fba < avg_recent * 0.5:
                trend = "declining"
            elif last_fba > avg_recent * 1.5:
                trend = "increasing"

        return {
            "days_oos": days_oos,
            "last_fba_count": last_fba,
            "avg_30d_fba_count": round(avg_recent, 1),
            "trend": trend,
            "history_length": len(history),
        }

    # ── Warehouse / A2A Deals ──────────────────────────────────────────────

    def get_warehouse_deals(self, domain=1, price_range=(1000, 10000),
                            max_bsr=200000, min_discount_pct=40, count=150):
        """Find Amazon Warehouse deals where used/renewed price is significantly
        below the new Buy Box price.

        Uses Keepa Deals API filtered for used price type.

        Args:
            domain: 1 = Amazon.com
            price_range: New price range in cents
            max_bsr: Maximum BSR
            min_discount_pct: Minimum discount from new to used (e.g. 40 = 40% off)
            count: Max results

        Cost: 5 tokens per request.
        Returns: list of deal dicts with new_price, used_price, discount_pct.
        """
        self._rate_limit()
        selection = {
            "page": 0,
            "domainId": domain,
            "excludeCategories": [],
            "includeCategories": [],
            "priceTypes": [2],  # Used price
            "salesRankRange": [1, max_bsr],
            "currentRange": list(price_range),
            "isLowest": False,
            "isLowestOffer": True,  # At lowest used price
            "isOutOfStock": False,
            "titleSearch": "",
            "isRangeEnabled": True,
            "isFilterEnabled": True,
            "hasReviews": True,
            "isPrimeExclusive": False,
            "mustHaveAmazonOffer": False,
            "mustNotHaveAmazonOffer": False,
            "sortType": 3,
            "dateRange": 0,  # Last 24h
        }

        try:
            r = requests.post(
                f"{self.BASE_URL}/deal",
                params={"key": self.api_key, "domain": domain},
                json=selection,
                timeout=30,
            )
            if r.status_code != 200:
                print(f"[keepa] Warehouse Deals HTTP {r.status_code}: {r.text[:200]}",
                      file=sys.stderr)
                return []
            data = r.json()
            self.tokens_left = data.get("tokensLeft")
        except Exception as e:
            print(f"[keepa] Warehouse Deals request error: {e}", file=sys.stderr)
            return []

        deal_items = data.get("deals", {}).get("dr", [])

        deals = []
        for d in deal_items[:count]:
            asin = d.get("asin", "")
            title = d.get("title", "")
            current = d.get("current", [])

            # Get used price (index 2) and new price (index 18 Buy Box, or 1 New 3P)
            used_price = 0
            new_price = 0

            if isinstance(current, list):
                if len(current) > 2 and isinstance(current[2], (int, float)) and current[2] > 0:
                    used_price = current[2] / 100.0
                for idx in [18, 1, 0]:
                    if len(current) > idx and isinstance(current[idx], (int, float)) and current[idx] > 0:
                        new_price = current[idx] / 100.0
                        break

            if used_price <= 0 or new_price <= 0:
                continue

            discount_pct = round((1 - used_price / new_price) * 100, 1)
            if discount_pct < min_discount_pct:
                continue

            cat_name = ""
            cat_tree = d.get("categoryTree")
            if cat_tree and isinstance(cat_tree, list):
                cat_name = cat_tree[-1].get("name", "") if cat_tree else ""

            deals.append({
                "asin": asin,
                "title": title,
                "new_price": round(new_price, 2),
                "used_price": round(used_price, 2),
                "discount_pct": discount_pct,
                "potential_profit": round(new_price - used_price, 2),
                "category": cat_name,
                "bsr": d.get("salesRank") or 0,
                "image": d.get("image", ""),
            })

        print(f"[keepa] Warehouse Deals API returned {len(deals)} items (cost: 5 tokens)",
              file=sys.stderr)
        return deals

    # ── Product Finder ─────────────────────────────────────────────────────

    def product_finder(self, domain=1, min_price_drop_pct=30, max_bsr=100000,
                       price_range=(1000, 5000), min_sellers=3, max_sellers=15,
                       category=0, count=150):
        """Query Amazon's entire catalog for arbitrage windows.

        Uses Keepa Product Finder API (/query) to find products where price
        has dropped significantly, indicating potential arbitrage opportunities.

        Args:
            domain: 1 = Amazon.com
            min_price_drop_pct: Minimum % price drop over 90 days
            max_bsr: Maximum BSR (ensures demand)
            price_range: (min_cents, max_cents) for current price
            min_sellers: Minimum FBA sellers (avoids private label)
            max_sellers: Maximum FBA sellers (avoids saturation)
            category: Keepa category ID (0 = all)
            count: Max results (up to 150)

        Cost: 5 tokens per request.
        Returns: list of product dicts matching the criteria.
        """
        self._rate_limit()
        selection = {
            "domainId": domain,
            "productType": [0],  # 0 = standard product
            "current_BUY_BOX_SHIPPING_gte": price_range[0],
            "current_BUY_BOX_SHIPPING_lte": price_range[1],
            "salesRankRange_gte": 1,
            "salesRankRange_lte": max_bsr,
            "current_COUNT_NEW_gte": min_sellers,
            "current_COUNT_NEW_lte": max_sellers,
            "deltaPercent_BUY_BOX_SHIPPING_90_lte": -min_price_drop_pct,
            "isAmazon_gte": 0,
            "isAmazon_lte": 0,  # Amazon NOT on listing
            "hasReviews_gte": 1,
            "perPage": min(count, 150),
            "page": 0,
            "sort": [["current_SALES", "asc"]],  # Best BSR first
        }

        if category:
            selection["rootCategory"] = category

        try:
            import json as _json
            r = requests.post(
                f"{self.BASE_URL}/query",
                params={
                    "key": self.api_key,
                    "domain": domain,
                    "selection": _json.dumps(selection),
                },
                timeout=60,
            )
            if r.status_code != 200:
                print(f"[keepa] Product Finder HTTP {r.status_code}: {r.text[:200]}",
                      file=sys.stderr)
                return []
            data = r.json()
            self.tokens_left = data.get("tokensLeft")
        except Exception as e:
            print(f"[keepa] Product Finder request error: {e}", file=sys.stderr)
            return []

        asins = data.get("asinList", [])
        if not asins:
            print("[keepa] Product Finder returned 0 results", file=sys.stderr)
            return []

        print(f"[keepa] Product Finder returned {len(asins)} ASINs (cost: 5 tokens)",
              file=sys.stderr)

        # Fetch product details for the found ASINs (batch lookup)
        products = []
        for i in range(0, len(asins), 100):
            batch = asins[i:i + 100]
            batch_results = self.get_products_batch(batch, domain=domain, stats=90)
            products.extend(batch_results)

        return products

    # ── Buy Box Distribution ───────────────────────────────────────────────

    def get_buy_box_distribution(self, asin, domain=1):
        """Get Buy Box ownership distribution for an ASIN.

        Requires offers=20 to get seller-level Buy Box percentages.

        Args:
            asin: Amazon ASIN
            domain: 1 = Amazon.com

        Cost: 21 tokens (product + offers).
        Returns: dict with distribution {seller_name: pct}, amazon_pct, dominant_seller.
        """
        product = self.get_product(asin, domain=domain, offers=20, stats=180)
        if not product or not product.get("offers_data"):
            return {"distribution": {}, "amazon_pct": 0, "dominant_seller": None}

        distribution = {}
        amazon_pct = 0
        for seller in product["offers_data"]:
            name = seller.get("seller_name", "Unknown")
            pct = seller.get("buy_box_percentage")
            if pct is not None:
                distribution[name] = pct
                if seller.get("is_amazon"):
                    amazon_pct = pct

        # Find dominant seller
        dominant = None
        max_pct = 0
        for name, pct in distribution.items():
            if pct and pct > max_pct:
                max_pct = pct
                dominant = name

        return {
            "distribution": distribution,
            "amazon_pct": amazon_pct,
            "dominant_seller": dominant,
            "dominant_pct": max_pct,
            "total_sellers": len(distribution),
        }

    # ── Stock Check (Target Redsky) ──────────────────────────────────────

    @staticmethod
    def check_target_stock(tcin, store_id="1375"):
        """Check if a Target product is in stock via Redsky fiats_v1 API.

        Free, no auth required. Returns dict with in_stock, quantity, store_id.
        """
        try:
            url = "https://redsky.target.com/redsky_aggregations/v1/web/fiats_v1"
            params = {
                "key": "ff457966e64d5e877fdbad070f276d18ecec4a01",
                "tcin": tcin,
                "store_id": store_id,
                "pricing_store_id": store_id,
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code != 200:
                return {"in_stock": None, "error": f"HTTP {r.status_code}"}

            data = r.json()
            product_data = data.get("data", {}).get("product", {})
            fulfillment = product_data.get("fulfillment", {})

            # Check shipping / store pickup availability
            shipping = fulfillment.get("shipping_options", {})
            store_options = fulfillment.get("store_options", [])

            is_available_shipping = shipping.get("availability_status") == "IN_STOCK"
            is_available_store = any(
                opt.get("order_pickup", {}).get("availability_status") == "IN_STOCK"
                for opt in store_options
            ) if store_options else False

            return {
                "in_stock": is_available_shipping or is_available_store,
                "shipping_available": is_available_shipping,
                "store_pickup_available": is_available_store,
                "store_id": store_id,
            }
        except Exception as e:
            return {"in_stock": None, "error": str(e)}


    def get_bsr_drops(self, product_data: dict) -> dict:
        """Count BSR rank drops from Keepa CSV index 3 (proxy for sales velocity).

        Each BSR decrease = at least one sale occurred.
        Returns drop counts for 30d/60d/90d windows and an est_sales_monthly proxy.
        """
        try:
            csv = product_data.get("csv", [])
            if not csv or len(csv) <= 3 or not csv[3]:
                return {"drops_30d": 0, "drops_60d": 0, "drops_90d": 0, "est_sales_monthly": 0}

            bsr_array = csv[3]  # [ts, val, ts, val, ...]
            keepa_now = int(time.time() / 60) - 21564000
            cutoff_90d = keepa_now - (90 * 24 * 60)
            cutoff_60d = keepa_now - (60 * 24 * 60)
            cutoff_30d = keepa_now - (30 * 24 * 60)

            drops_30d = drops_60d = drops_90d = 0
            prev_val = None

            for i in range(0, len(bsr_array) - 1, 2):
                ts = bsr_array[i]
                val = bsr_array[i + 1]
                if val <= 0:  # -1 = no data, -2 = OOS
                    prev_val = None
                    continue
                if ts < cutoff_90d:
                    prev_val = val
                    continue
                if prev_val is not None and val < prev_val:
                    # BSR dropped = sale occurred
                    if ts >= cutoff_30d:
                        drops_30d += 1
                        drops_60d += 1
                        drops_90d += 1
                    elif ts >= cutoff_60d:
                        drops_60d += 1
                        drops_90d += 1
                    else:
                        drops_90d += 1
                prev_val = val

            return {
                "drops_30d": drops_30d,
                "drops_60d": drops_60d,
                "drops_90d": drops_90d,
                "est_sales_monthly": drops_30d,
            }
        except Exception as e:
            print(f"[keepa] get_bsr_drops error: {e}", file=sys.stderr)
            return {"drops_30d": 0, "drops_60d": 0, "drops_90d": 0, "est_sales_monthly": 0}

    def get_amazon_oos_pct(self, product_data: dict, days: int = 90) -> float:
        """Return fraction of time Amazon was OOS in the last N days.

        0.0 = always in stock, 1.0 = always OOS.
        Uses CSV index 0 (Amazon price history); -1 or -2 = OOS/no data.
        """
        try:
            csv = product_data.get("csv", [])
            if not csv or not csv[0]:
                return 1.0  # no data = assume OOS

            amazon_array = csv[0]
            keepa_now = int(time.time() / 60) - 21564000
            cutoff = keepa_now - (days * 24 * 60)

            in_stock_count = oos_count = 0
            for i in range(0, len(amazon_array) - 1, 2):
                ts = amazon_array[i]
                val = amazon_array[i + 1]
                if ts < cutoff:
                    continue
                if val > 0:
                    in_stock_count += 1
                else:
                    oos_count += 1

            total = in_stock_count + oos_count
            if total == 0:
                return 1.0
            return round(oos_count / total, 3)
        except Exception as e:
            print(f"[keepa] get_amazon_oos_pct error: {e}", file=sys.stderr)
            return 1.0

    def get_brand_catalog(self, brand_name: str, max_asins: int = 200) -> list:
        """Fetch all ASINs for a brand from Keepa Product Finder.

        Returns a list of dicts: [{asin, title, current_bsr, amazon_in_stock, category}]
        Cost: 5 tokens per query + 1 token per ASIN fetched.
        """
        try:
            import json as _json
            per_page = min(max_asins, 100)
            selection = {
                "domainId": 1,
                "brand": brand_name,
                "current_COUNT_NEW_range": [1, -1],
                "perPage": per_page,
                "page": 0,
                "sort": [["current_SALES", "asc"]],
            }
            self._rate_limit()
            params = {
                "key": self.api_key,
                "domain": 1,
                "selection": _json.dumps(selection),
            }
            url = f"{self.BASE_URL}/query"
            r = requests.post(url, params=params, timeout=60)
            if r.status_code != 200:
                print(f"[keepa] get_brand_catalog HTTP {r.status_code}: {r.text[:200]}",
                      file=sys.stderr)
                return []
            data = r.json()
            self.tokens_left = data.get("tokensLeft")
            asins = data.get("asinList", [])[:max_asins]
            if not asins:
                return []

            print(f"[keepa] Brand catalog '{brand_name}': {len(asins)} ASINs (fetching details...)",
                  file=sys.stderr)

            results = []
            for i in range(0, len(asins), 100):
                batch = asins[i:i + 100]
                batch_products = self.get_products_batch(batch, domain=1, stats=1)
                for p in batch_products:
                    results.append({
                        "asin": p.get("asin", ""),
                        "title": p.get("title", ""),
                        "current_bsr": p.get("bsr"),
                        "amazon_in_stock": p.get("amazon_on_listing", False),
                        "category": p.get("category", ""),
                    })
            return results
        except Exception as e:
            print(f"[keepa] get_brand_catalog error: {e}", file=sys.stderr)
            return []


def _fuzzy_brand_match(brand, seller_name):
    """Check if brand and seller name are fuzzy matches (common abbreviations, LLC removal, etc.)."""
    # Remove common suffixes
    for suffix in [" llc", " inc", " corp", " ltd", " co", " company",
                   " enterprises", " group", " brands", " direct"]:
        brand = brand.replace(suffix, "")
        seller_name = seller_name.replace(suffix, "")

    # Remove punctuation
    import re
    brand = re.sub(r"[^a-z0-9]", "", brand)
    seller_name = re.sub(r"[^a-z0-9]", "", seller_name)

    if not brand or not seller_name:
        return False

    # Direct containment
    return brand in seller_name or seller_name in brand
