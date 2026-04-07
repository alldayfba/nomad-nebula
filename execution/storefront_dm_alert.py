#!/usr/bin/env python3
"""
Storefront DM Alert — scans a seller's storefront and sends structured
product data directly to Sabbo's Discord DMs via the Nova bot.

Usage:
    python execution/storefront_dm_alert.py --seller A119C0H7LPP19N
    python execution/storefront_dm_alert.py --seller A119C0H7LPP19N --watch  # poll every 15 min
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
SABBO_DISCORD_ID = "333610222146813957"
POLL_MINUTES = int(os.environ.get("STALKER_POLL_MINUTES", "15"))
SEEN_FILE = Path(__file__).parent.parent / ".tmp" / "storefront_seen_asins.json"
API_BASE = "https://discord.com/api/v10"

UA_POOL = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]


# ── Discord DM helpers ──────────────────────────────────────────────────────

def _headers():
    return {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}


def _get_dm_channel() -> str:
    """Open/get DM channel with Sabbo."""
    resp = requests.post(
        f"{API_BASE}/users/@me/channels",
        headers=_headers(),
        json={"recipient_id": SABBO_DISCORD_ID},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _send_dm(channel_id: str, content: str = "", embeds: list = None):
    """Send a message to the DM channel."""
    payload = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds
    resp = requests.post(
        f"{API_BASE}/channels/{channel_id}/messages",
        headers=_headers(),
        json=payload,
        timeout=10,
    )
    if resp.status_code == 429:
        retry_after = resp.json().get("retry_after", 2)
        logger.warning("Rate limited, waiting %.1fs", retry_after)
        time.sleep(retry_after + 0.5)
        return _send_dm(channel_id, content, embeds)
    resp.raise_for_status()
    return resp.json()


# ── Amazon scraper ──────────────────────────────────────────────────────────

def scrape_storefront(seller_id: str, max_pages: int = 20) -> list[dict]:
    """Scrape seller storefront via Playwright (bypasses Amazon bot detection).

    Falls back to requests if Playwright unavailable.
    Returns list of {asin, title, price, url}.
    """
    try:
        return _scrape_storefront_playwright(seller_id, max_pages)
    except Exception as exc:
        logger.warning("Playwright scrape failed (%s), falling back to requests", exc)
        return _scrape_storefront_requests(seller_id, max_pages)


def _scrape_storefront_playwright(seller_id: str, max_pages: int) -> list[dict]:
    """Playwright-based scraper — handles Amazon bot detection."""
    from playwright.sync_api import sync_playwright

    products = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})

        for pg in range(1, max_pages + 1):
            url = f"https://www.amazon.com/s?me={seller_id}&sort=date-desc-rank&page={pg}"
            try:
                page.goto(url, timeout=15000)
                page.wait_for_timeout(2000)
            except Exception as exc:
                logger.warning("Playwright page %d error: %s", pg, exc)
                break

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            found_on_page = 0

            for item in soup.select("[data-asin]"):
                asin = item.get("data-asin", "").strip()
                if not asin or len(asin) != 10 or asin in seen:
                    continue
                seen.add(asin)

                title_el = item.select_one("h2 a span") or item.select_one("h2 span")
                title = title_el.get_text(strip=True) if title_el else asin

                price = None
                price_whole = item.select_one(".a-price-whole")
                price_frac = item.select_one(".a-price-fraction")
                if price_whole:
                    try:
                        whole = price_whole.get_text(strip=True).replace(",", "").rstrip(".")
                        frac = price_frac.get_text(strip=True) if price_frac else "00"
                        price = float(f"{whole}.{frac}")
                    except ValueError:
                        pass

                rating_el = item.select_one(".a-icon-alt")
                rating = rating_el.get_text(strip=True) if rating_el else None

                review_el = item.select_one(".a-size-base.s-underline-text")
                reviews = review_el.get_text(strip=True).replace(",", "") if review_el else None

                products.append({
                    "asin": asin,
                    "title": title[:80],
                    "price": price,
                    "rating": rating,
                    "reviews": reviews,
                    "url": f"https://www.amazon.com/dp/{asin}",
                })
                found_on_page += 1

            logger.info("Page %d: found %d products (total: %d)", pg, found_on_page, len(products))
            if found_on_page == 0:
                break
            time.sleep(random.uniform(1.5, 3.0))

        browser.close()

    return products


def _scrape_storefront_requests(seller_id: str, max_pages: int) -> list[dict]:
    """Fallback requests-based scraper (may get blocked by Amazon after page 1)."""
    products = []
    seen = set()

    for page in range(1, max_pages + 1):
        url = f"https://www.amazon.com/s?me={seller_id}&sort=date-desc-rank&page={page}"
        headers = {
            "User-Agent": random.choice(UA_POOL),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning("Page %d returned %d", page, resp.status_code)
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            found_on_page = 0

            for item in soup.select("[data-asin]"):
                asin = item.get("data-asin", "").strip()
                if not asin or len(asin) != 10 or asin in seen:
                    continue
                seen.add(asin)

                title_el = item.select_one("h2 a span") or item.select_one("h2 span")
                title = title_el.get_text(strip=True) if title_el else asin

                price = None
                price_whole = item.select_one(".a-price-whole")
                price_frac = item.select_one(".a-price-fraction")
                if price_whole:
                    try:
                        whole = price_whole.get_text(strip=True).replace(",", "").rstrip(".")
                        frac = price_frac.get_text(strip=True) if price_frac else "00"
                        price = float(f"{whole}.{frac}")
                    except ValueError:
                        pass

                rating_el = item.select_one(".a-icon-alt")
                rating = rating_el.get_text(strip=True) if rating_el else None

                review_el = item.select_one(".a-size-base.s-underline-text")
                reviews = review_el.get_text(strip=True).replace(",", "") if review_el else None

                products.append({
                    "asin": asin,
                    "title": title[:80],
                    "price": price,
                    "rating": rating,
                    "reviews": reviews,
                    "url": f"https://www.amazon.com/dp/{asin}",
                })
                found_on_page += 1

            logger.info("Page %d: found %d products (total: %d)", page, found_on_page, len(products))
            if found_on_page == 0:
                break
            time.sleep(random.uniform(2.5, 4.0))

        except Exception as exc:
            logger.error("Scrape error page %d: %s", page, exc)
            break

    return products


# ── Keepa enrichment (optional) ────────────────────────────────────────────

def enrich_with_keepa(products: list[dict]) -> list[dict]:
    """Add BSR, FBA sellers, category from Keepa if available."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from keepa_client import KeepaClient
        kc = KeepaClient()
    except Exception:
        logger.info("Keepa not available, skipping enrichment")
        return products

    for p in products:
        try:
            data = kc.get_product(p["asin"])
            if data:
                p["bsr"] = data.get("salesRank") or data.get("sales_rank")
                p["category"] = data.get("categoryTree", [{}])[-1].get("name") if data.get("categoryTree") else data.get("category")
                p["fba_sellers"] = data.get("fba_seller_count")
                p["buy_box"] = data.get("buyBoxPrice") or data.get("amazon_price") or p.get("price")
                p["bsr_drops_30"] = data.get("bsr_drops_30d")
            time.sleep(0.5)
        except Exception as exc:
            logger.warning("Keepa error for %s: %s", p["asin"], exc)

    return products


# ── Embed builder ───────────────────────────────────────────────────────────

def build_product_embed(product: dict, index: int, total: int, seller_id: str) -> dict:
    """Build a rich Discord embed for one product."""
    asin = product["asin"]
    title = product["title"]
    price = product.get("buy_box") or product.get("price")
    bsr = product.get("bsr")
    category = product.get("category", "—")
    fba = product.get("fba_sellers")
    drops = product.get("bsr_drops_30")

    fields = [
        {"name": "ASIN", "value": f"`{asin}`", "inline": True},
        {"name": "Buy Box", "value": f"${price:.2f}" if price else "—", "inline": True},
        {"name": "Category", "value": str(category)[:50], "inline": True},
    ]

    if bsr is not None:
        fields.append({"name": "BSR", "value": f"{bsr:,}" if isinstance(bsr, (int, float)) else str(bsr), "inline": True})
    if fba is not None:
        fields.append({"name": "FBA Sellers", "value": str(fba), "inline": True})
    if drops is not None:
        fields.append({"name": "BSR Drops (30d)", "value": str(drops), "inline": True})

    fields.append({"name": "Amazon Link", "value": f"[View on Amazon](https://www.amazon.com/dp/{asin})", "inline": False})

    return {
        "title": f"📦 {title}",
        "url": f"https://www.amazon.com/dp/{asin}",
        "color": 0x00C851 if bsr and isinstance(bsr, (int, float)) and bsr < 100000 else 0xFFBB33,
        "fields": fields,
        "footer": {"text": f"Product {index}/{total} | Seller {seller_id} | Storefront Stalker"},
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Seen ASIN tracking ─────────────────────────────────────────────────────

def _load_seen(seller_id: str) -> set:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SEEN_FILE.exists():
        data = json.loads(SEEN_FILE.read_text())
        return set(data.get(seller_id, []))
    return set()


def _save_seen(seller_id: str, asins: set):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if SEEN_FILE.exists():
        data = json.loads(SEEN_FILE.read_text())
    data[seller_id] = list(asins)
    SEEN_FILE.write_text(json.dumps(data, indent=2))


# ── Main ────────────────────────────────────────────────────────────────────

def run_scan(seller_id: str, enrich: bool = True, only_new: bool = False):
    """Scan seller storefront and DM all products to Sabbo."""
    logger.info("Scanning storefront: %s", seller_id)
    products = scrape_storefront(seller_id)

    if not products:
        logger.warning("No products found for seller %s", seller_id)
        return

    seen = _load_seen(seller_id)

    if only_new:
        new_products = [p for p in products if p["asin"] not in seen]
        if not new_products:
            logger.info("No new products found for %s", seller_id)
            return
        products = new_products
        logger.info("Found %d NEW products", len(products))

    if enrich:
        logger.info("Enriching %d products with Keepa...", len(products))
        products = enrich_with_keepa(products)

    # Send to Discord DMs
    logger.info("Opening DM channel with Sabbo...")
    dm_channel = _get_dm_channel()

    # Header message
    _send_dm(dm_channel, content=(
        f"**🔍 Storefront Scan: `{seller_id}`**\n"
        f"{'🆕 New products only' if only_new else '📋 Full catalog'} | "
        f"**{len(products)} products** found\n"
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'─' * 40}"
    ))
    time.sleep(1)

    # Send products in batches of 5 embeds per message (Discord limit = 10)
    batch_size = 5
    for i in range(0, len(products), batch_size):
        batch = products[i:i + batch_size]
        embeds = [
            build_product_embed(p, i + j + 1, len(products), seller_id)
            for j, p in enumerate(batch)
        ]
        _send_dm(dm_channel, embeds=embeds)
        time.sleep(1.5)

    # Update seen ASINs
    all_asins = seen | {p["asin"] for p in products}
    _save_seen(seller_id, all_asins)

    logger.info("Done! Sent %d products to Sabbo's DMs", len(products))


def watch(seller_id: str):
    """Poll every POLL_MINUTES for new products."""
    logger.info("Starting watch mode for %s (every %d min)", seller_id, POLL_MINUTES)

    # Initial full scan
    run_scan(seller_id, enrich=True, only_new=False)

    while True:
        jitter = random.randint(-120, 120)
        sleep_sec = POLL_MINUTES * 60 + jitter
        logger.info("Sleeping %d seconds until next poll...", sleep_sec)
        time.sleep(sleep_sec)

        try:
            run_scan(seller_id, enrich=True, only_new=True)
        except Exception as exc:
            logger.error("Watch cycle error: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Storefront DM Alert")
    parser.add_argument("--seller", required=True, help="Amazon seller ID")
    parser.add_argument("--watch", action="store_true", help="Poll continuously for new products")
    parser.add_argument("--no-keepa", action="store_true", help="Skip Keepa enrichment")
    parser.add_argument("--only-new", action="store_true", help="Only send products not seen before")
    args = parser.parse_args()

    if not BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not set in .env")
        sys.exit(1)

    if args.watch:
        watch(args.seller)
    else:
        run_scan(args.seller, enrich=not args.no_keepa, only_new=args.only_new)
