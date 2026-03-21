#!/usr/bin/env python3
"""
Storefront Monitor (SaaS Edition) — reads tracked sellers from Supabase,
checks for new products, sends Nova DMs to individual students.

Runs as a cron job every 15 minutes.

Usage:
    python execution/storefront_monitor_saas.py run
    python execution/storefront_monitor_saas.py run --dry-run
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import logging
import requests
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# -- Config -------------------------------------------------------------------
# Load from fba-saas .env.local
SUPABASE_URL = ""
SUPABASE_SERVICE_KEY = ""
DISCORD_BOT_TOKEN = ""

FBA_SAAS_ENV = Path("/Users/SabboOpenClawAI/Documents/fba-saas/.env.local")
if not FBA_SAAS_ENV.exists():
    FBA_SAAS_ENV = Path("/Users/sabbojb/Documents/fba-saas/.env.local")
if FBA_SAAS_ENV.exists():
    for line in FBA_SAAS_ENV.read_text().splitlines():
        if line.startswith("NEXT_PUBLIC_SUPABASE_URL="):
            SUPABASE_URL = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
            SUPABASE_SERVICE_KEY = line.split("=", 1)[1].strip()

NOMAD_ENV = Path(__file__).parent.parent / ".env"
if NOMAD_ENV.exists():
    for line in NOMAD_ENV.read_text().splitlines():
        if line.startswith("DISCORD_BOT_TOKEN="):
            DISCORD_BOT_TOKEN = line.split("=", 1)[1].strip()

POLL_INTERVAL_MINUTES = int(os.environ.get("STALKER_POLL_MINUTES", "15"))


def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def get_all_tracked_sellers():
    """Get all tracked sellers across all students, grouped by seller_id."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/tracked_sellers",
        headers=supabase_headers(),
        params={
            "select": "id,user_id,seller_id,seller_name,monitoring_enabled,status",
            "monitoring_enabled": "eq.true",
        },
    )
    if resp.status_code != 200:
        logger.error("Failed to fetch tracked sellers: %s", resp.text)
        return []
    return resp.json()


def get_user_discord_id(user_id):
    """Get a user's discord_user_id from Supabase."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/users",
        headers=supabase_headers(),
        params={"select": "discord_user_id", "id": f"eq.{user_id}"},
    )
    if resp.status_code == 200 and resp.json():
        return resp.json()[0].get("discord_user_id")
    return None


def get_known_asins_for_seller(seller_id):
    """Get ASINs we've already alerted on for this seller (last 30 days)."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/seller_alerts",
        headers=supabase_headers(),
        params={
            "select": "asin",
            "seller_id": f"eq.{seller_id}",
            "created_at": f"gte.{(datetime.utcnow().replace(day=1)).isoformat()}",
        },
    )
    if resp.status_code == 200:
        return set(a["asin"] for a in resp.json())
    return set()


def scrape_storefront_asins(seller_id):
    """Scrape Amazon storefront for current ASINs (newest first)."""
    url = f"https://www.amazon.com/s?me={seller_id}&sort=date-desc-rank"
    ua_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]
    headers = {
        "User-Agent": random.choice(ua_pool),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        from bs4 import BeautifulSoup

        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        asins = []
        for tag in soup.select("[data-asin]"):
            asin = tag.get("data-asin", "").strip()
            if asin and len(asin) == 10 and asin not in asins:
                asins.append(asin)
        return asins[:50]
    except Exception as exc:
        logger.error("Scrape error for %s: %s", seller_id, exc)
        return []


def get_product_info(asin):
    """Quick Keepa lookup for product name + price."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from keepa_client import KeepaClient

        kc = KeepaClient()
        product = kc.get_product(asin)
        if product:
            return {
                "name": product.get("title") or product.get("name") or asin,
                "price": product.get("amazon_price") or product.get("buyBoxPrice"),
                "bsr": product.get("sales_rank"),
                "bsr_drops_30d": int(product.get("bsr_drops_30d") or 0),
                "fba_sellers": product.get("fba_seller_count"),
                "amazon_on_listing": bool(product.get("amazon_on_listing", False)),
                "category": product.get("category"),
            }
    except Exception:
        pass
    return {
        "name": asin,
        "price": None,
        "bsr": None,
        "bsr_drops_30d": 0,
        "fba_sellers": None,
        "amazon_on_listing": False,
        "category": None,
    }


def grade_product(info):
    """Grade A/B/C based on Amazon signals."""
    score = 0
    bsr = info.get("bsr")
    drops = info.get("bsr_drops_30d", 0)
    sellers = info.get("fba_sellers")
    amazon = info.get("amazon_on_listing", False)

    if bsr and bsr < 3000:
        score += 3
    elif bsr and bsr < 10000:
        score += 2
    elif bsr and bsr < 50000:
        score += 1

    if drops >= 30:
        score += 2
    elif drops >= 10:
        score += 1

    if sellers is not None:
        if 2 <= sellers <= 8:
            score += 2
        elif sellers and sellers > 20:
            score -= 2

    if not amazon:
        score += 2
    else:
        score -= 3

    if score >= 6:
        return "A"
    if score >= 3:
        return "B"
    return "C"


def insert_seller_alert(user_id, seller_id, asin, info, grade):
    """Insert alert into Supabase seller_alerts table."""
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/seller_alerts",
        headers={**supabase_headers(), "Prefer": "return=minimal"},
        json={
            "user_id": user_id,
            "seller_id": seller_id,
            "asin": asin,
            "product_name": info.get("name"),
            "amazon_price": info.get("price"),
            "grade": grade,
            "bsr": info.get("bsr"),
            "bsr_drops_30d": info.get("bsr_drops_30d"),
            "fba_sellers": info.get("fba_sellers"),
            "amazon_on_listing": info.get("amazon_on_listing", False),
            "stage": "complete",
        },
    )
    return resp.status_code in (200, 201)


def send_discord_dm(discord_user_id, embed):
    """Send a DM to a user via Nova bot."""
    if not DISCORD_BOT_TOKEN or not discord_user_id:
        return False
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    # Create DM channel
    resp = requests.post(
        "https://discord.com/api/v10/users/@me/channels",
        headers=headers,
        json={"recipient_id": discord_user_id},
    )
    if resp.status_code != 200:
        logger.warning(
            "Failed to create DM channel for %s: %s", discord_user_id, resp.status_code
        )
        return False

    channel_id = resp.json().get("id")
    if not channel_id:
        return False

    # Send message
    resp2 = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers=headers,
        json={"embeds": [embed]},
    )
    return resp2.status_code in (200, 201)


GRADE_COLORS = {"A": 0x00C851, "B": 0xFFBB33, "C": 0xFF4444}


def build_alert_embed(seller_name, asin, info, grade):
    """Build Discord embed for the DM alert."""
    price_str = f"${info['price']:.2f}" if info.get("price") else "--"
    bsr_str = f"{info['bsr']:,}" if info.get("bsr") else "--"
    drops_str = (
        f" ({info['bsr_drops_30d']} drops/mo)" if info.get("bsr_drops_30d") else ""
    )
    sellers_str = (
        f"{info['fba_sellers']} FBA sellers"
        if info.get("fba_sellers") is not None
        else ""
    )
    amazon_str = (
        "Amazon on listing"
        if info.get("amazon_on_listing")
        else "Amazon NOT on listing"
    )

    grade_labels = {
        "A": "GRADE A -- BUY POTENTIAL",
        "B": "GRADE B -- MAYBE",
        "C": "GRADE C -- SKIP",
    }

    desc = (
        f"**{info.get('name', asin)}**\n`{asin}` | {price_str}\n\n"
        f"BSR {bsr_str}{drops_str} | {sellers_str} | {amazon_str}"
    )

    return {
        "title": f"{grade_labels.get(grade, grade)} -- {seller_name}",
        "description": desc,
        "url": f"https://www.amazon.com/dp/{asin}",
        "color": GRADE_COLORS.get(grade, 0x9B59B6),
        "footer": {"text": "24/7 Profits -- Storefront Stalker"},
        "timestamp": datetime.utcnow().isoformat(),
    }


def update_seller_last_active(seller_id):
    """Update last_active_at for all tracked_sellers rows with this seller_id."""
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/tracked_sellers",
        headers={**supabase_headers(), "Prefer": "return=minimal"},
        params={"seller_id": f"eq.{seller_id}"},
        json={
            "last_active_at": datetime.utcnow().isoformat(),
            "status": "active",
        },
    )


def run_monitor_cycle(dry_run=False):
    """Main monitoring cycle -- check all tracked sellers for new products."""
    sellers = get_all_tracked_sellers()
    if not sellers:
        logger.info("No tracked sellers found")
        return

    # Group by seller_id (multiple students may track the same seller)
    seller_groups = {}
    for s in sellers:
        sid = s["seller_id"]
        seller_groups.setdefault(sid, []).append(s)

    logger.info(
        "Checking %d unique sellers (%d total subscriptions)",
        len(seller_groups),
        len(sellers),
    )

    total_alerts = 0

    for seller_id, subscribers in seller_groups.items():
        seller_name = subscribers[0].get("seller_name") or seller_id
        known_asins = get_known_asins_for_seller(seller_id)

        current_asins = scrape_storefront_asins(seller_id)
        if not current_asins:
            continue

        new_asins = [a for a in current_asins if a not in known_asins]
        if not new_asins:
            continue

        logger.info("%s: %d new products found", seller_name, len(new_asins))
        update_seller_last_active(seller_id)

        for asin in new_asins:
            info = get_product_info(asin)
            grade = grade_product(info)
            embed = build_alert_embed(seller_name, asin, info, grade)

            for sub in subscribers:
                user_id = sub["user_id"]

                if dry_run:
                    logger.info(
                        "  [DRY] Would alert user %s about %s (Grade %s)",
                        user_id,
                        asin,
                        grade,
                    )
                    continue

                # Save alert to Supabase
                insert_seller_alert(user_id, seller_id, asin, info, grade)
                total_alerts += 1

                # DM via Nova
                discord_id = get_user_discord_id(user_id)
                if discord_id:
                    sent = send_discord_dm(discord_id, embed)
                    if sent:
                        logger.info(
                            "  DM sent to %s for %s (Grade %s)",
                            discord_id,
                            asin,
                            grade,
                        )
                    else:
                        logger.warning("  DM failed for %s", discord_id)

            # Rate limit between ASINs
            time.sleep(1)

        # Jitter between sellers
        time.sleep(random.uniform(2, 5))

    logger.info("Cycle complete: %d alerts sent", total_alerts)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Storefront Monitor (SaaS Edition)")
    sub = parser.add_subparsers(dest="cmd")
    run_p = sub.add_parser("run", help="Run one monitor cycle")
    run_p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.cmd == "run":
        run_monitor_cycle(dry_run=args.dry_run)
    else:
        parser.print_help()
