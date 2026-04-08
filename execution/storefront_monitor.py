from __future__ import annotations
"""
Storefront Monitor — watches trusted Amazon seller storefronts for new product additions.

Stage 1: instant Discord alert when a watched seller adds a new ASIN.
Stage 2: background pipeline (Keepa deep-fetch + retailer scan + profitability)
         then edits the original Discord message with a final grade.

Features:
- Seller accuracy score: tracks confirmed BUY rate per seller, auto-updates from feedback
- Convergence alert: if 3+ watched sellers add the same ASIN within 24h -> HOT DEAL alert
- Retirement detection: flags sellers quiet for 30+ days
- Jitter: randomized poll interval +/-2 min to avoid bot-detection patterns

CLI:
    python execution/storefront_monitor.py run
    python execution/storefront_monitor.py watch --interval 15
    python execution/storefront_monitor.py add --seller-id A1B2C3 --name "My Seller"
    python execution/storefront_monitor.py list
    python execution/storefront_monitor.py remove --seller-id A1B2C3
"""

import json
import os
import random
import sys
import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
POLL_INTERVAL_MINUTES = int(os.environ.get("STALKER_POLL_MINUTES", "15"))
JITTER_SECONDS = 120  # +/-2 min randomization
CONVERGENCE_THRESHOLD = 3  # sellers adding same ASIN within window -> HOT DEAL
CONVERGENCE_WINDOW_HOURS = 24
RETIREMENT_DAYS = 30  # seller flagged quiet after this many days of inactivity
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
USE_KEEPA_API = os.environ.get("STOREFRONT_USE_KEEPA", "1").lower() in ("1", "true", "yes")


def _get_db():
    from results_db import ResultsDB
    return ResultsDB()


# ── Discord helpers ──────────────────────────────────────────────────────────

def _send_discord_webhook(embed: dict) -> Optional[str]:
    """Post an embed to Discord via webhook. Returns message_id string if successful."""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("[monitor] DISCORD_WEBHOOK_URL not set -- skipping alert")
        return None
    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL + "?wait=true",
            json={"embeds": [embed]},
            timeout=10,
        )
        if resp.status_code in (200, 204):
            try:
                return str(resp.json().get("id", ""))
            except Exception:
                return None
        logger.warning("[monitor] Discord webhook returned %s", resp.status_code)
    except Exception as exc:
        logger.error("[monitor] Discord send error: %s", exc)
    return None


def _edit_discord_message(message_id: str, embed: dict) -> bool:
    """Edit an existing Discord webhook message in-place."""
    if not DISCORD_WEBHOOK_URL or not message_id:
        return False
    # URL format: https://discord.com/api/webhooks/{webhook_id}/{token}
    parts = DISCORD_WEBHOOK_URL.rstrip("/").split("/")
    if len(parts) < 2:
        return False
    webhook_id = parts[-2]
    webhook_token = parts[-1]
    edit_url = f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}"
    try:
        resp = requests.patch(edit_url, json={"embeds": [embed]}, timeout=10)
        return resp.status_code in (200, 204)
    except Exception as exc:
        logger.error("[monitor] Discord edit error: %s", exc)
        return False


# ── Embed builders ───────────────────────────────────────────────────────────

GRADE_COLORS = {"A": 0x00C851, "B": 0xFFBB33, "C": 0xFF4444, "?": 0x9B59B6}
GRADE_LABELS = {
    "A": "GRADE A -- BUY POTENTIAL",
    "B": "GRADE B -- MAYBE",
    "C": "GRADE C -- SKIP",
    "?": "ANALYZING...",
}


def _build_stage1_embed(seller_name: str, asin: str, product_name: str,
                        amazon_price: Optional[float]) -> dict:
    price_str = f"${amazon_price:.2f}" if amazon_price else "--"
    return {
        "title": f"NEW: {seller_name} added a product",
        "description": (
            f"**{product_name}**\n`{asin}` - {price_str}\n\n"
            "Analyzing -- grade incoming..."
        ),
        "color": GRADE_COLORS["?"],
        "footer": {"text": "Storefront Monitor - 24/7 Profits"},
        "timestamp": datetime.utcnow().isoformat(),
    }


def _build_stage2_embed(
    seller_name: str, asin: str, product_name: str,
    grade: str, profit: Optional[float], roi: Optional[float],
    retailer: Optional[str], buy_link: Optional[str],
    amazon_price: Optional[float], bsr: Optional[int],
    bsr_drops: Optional[int], fba_sellers: Optional[int],
    amazon_on_listing: bool, skip_reason: Optional[str] = None,
    convergence_count: int = 1,
) -> dict:
    hot = convergence_count >= CONVERGENCE_THRESHOLD
    grade_label = GRADE_LABELS.get(grade, "?")
    if hot:
        extra = f" (+{convergence_count - 1} other sellers)"
        title = f"HOT DEAL -- {seller_name}{extra}"
    else:
        title = f"{grade_label} -- {seller_name}"

    price_str = f"${amazon_price:.2f}" if amazon_price else "--"
    bsr_str = f"{bsr:,}" if bsr else "--"
    drops_str = f"down {bsr_drops}/mo" if bsr_drops else ""
    sellers_str = f"{fba_sellers} FBA sellers" if fba_sellers is not None else ""
    amazon_str = "Amazon on listing" if amazon_on_listing else "Amazon NOT on listing"

    if grade in ("A", "B") and profit is not None and roi is not None and retailer:
        desc = (
            f"**{product_name}**\n`{asin}`\n\n"
            f"**Buy at {retailer}:** Profit **${profit:.2f}** - ROI **{roi:.0f}%**\n"
            f"BSR {bsr_str} {drops_str} - {sellers_str} - {amazon_str}"
        )
        if buy_link:
            desc += f"\n[Buy Link]({buy_link})"
    elif grade in ("A", "B") and not retailer:
        max_cost_est = float(round((amazon_price or 0) * 0.55, 2)) if amazon_price else None
        max_str = f"Max buy cost ~${max_cost_est:.2f}" if max_cost_est else ""
        desc = (
            f"**{product_name}**\n`{asin}` - Amazon {price_str}\n\n"
            f"BSR {bsr_str} {drops_str} - {sellers_str} - {amazon_str}\n"
            f"{max_str} -- no retail source found yet"
        )
    else:
        reason = skip_reason or "Low BSR velocity or high competition"
        desc = (
            f"**{product_name}**\n`{asin}` - Amazon {price_str}\n\n"
            f"BSR {bsr_str} - {sellers_str} - {amazon_str}\n"
            f"*{reason}*"
        )

    return {
        "title": title,
        "description": desc,
        "url": f"https://www.amazon.com/dp/{asin}",
        "color": GRADE_COLORS.get(grade, GRADE_COLORS["?"]),
        "footer": {"text": "Storefront Monitor - 24/7 Profits"},
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Keepa API storefront fetch ───────────────────────────────────────────────

def _fetch_storefront_keepa(seller_id: str) -> list:
    """Fetch seller storefront via Keepa API /seller?storefront=1 endpoint.

    Returns a list of dicts: [{'asin': str, 'last_seen': int|None}, ...]
    Cost: 10 tokens per seller.
    """
    try:
        from keepa_client import KeepaClient
        client = KeepaClient()
        seller_data = client.get_seller_info(seller_id, storefront=True)
        if not seller_data:
            logger.warning("[monitor] Keepa seller API returned no data for %s", seller_id)
            return []

        asins = seller_data.get("asinList", [])
        last_seen = seller_data.get("asinListLastSeen", [])

        products = []
        for i, asin in enumerate(asins):
            if asin and isinstance(asin, str) and len(asin) == 10:
                products.append({
                    "asin": asin,
                    "last_seen": last_seen[i] if i < len(last_seen) else None,
                })
        logger.info("[monitor] Keepa storefront for %s: %d ASINs", seller_id, len(products))
        return products
    except Exception as exc:
        logger.error("[monitor] Keepa storefront fetch failed for %s: %s", seller_id, exc)
        return []


def _parse_seller_analytics(seller_data: dict) -> dict:
    """Extract rich analytics from a raw Keepa seller object."""
    if not seller_data:
        return {}
    try:
        from keepa_client import KeepaClient
        client = KeepaClient()
        return client.parse_seller(seller_data)
    except Exception as exc:
        logger.error("[monitor] Failed to parse seller analytics: %s", exc)
        return {}


def _discover_competitors(seller_id: str) -> list:
    """Discover competing sellers from a seller's Keepa data.

    Returns list of dicts: [{'seller_id': str, 'seller_name': str}, ...]
    Cost: 1 token (uses the seller endpoint without storefront).
    """
    try:
        from keepa_client import KeepaClient
        client = KeepaClient()
        seller_data = client.get_seller_info(seller_id, storefront=False)
        if not seller_data:
            return []
        competitors = seller_data.get("competitors", [])
        if not competitors:
            return []
        results = []
        for comp in competitors:
            if isinstance(comp, dict):
                comp_id = comp.get("sellerId", "")
                comp_name = comp.get("sellerName", "")
            elif isinstance(comp, str):
                comp_id = comp
                comp_name = ""
            else:
                continue
            if comp_id:
                results.append({"seller_id": comp_id, "seller_name": comp_name})
        logger.info("[monitor] Discovered %d competitors for seller %s", len(results), seller_id)
        return results
    except Exception as exc:
        logger.error("[monitor] Competitor discovery failed for %s: %s", seller_id, exc)
        return []


def fetch_storefront_asins(seller_id: str, use_keepa: bool = True) -> list:
    """Fetch storefront ASINs using Keepa API (preferred) or HTTP scrape (fallback).

    Args:
        seller_id: Amazon seller ID
        use_keepa: If True, use Keepa /seller?storefront=1 (10 tokens).
                   If False or Keepa fails, fall back to HTTP scrape.

    Returns: List of ASIN strings.
    """
    if use_keepa and USE_KEEPA_API:
        products = _fetch_storefront_keepa(seller_id)
        if products:
            return [p["asin"] for p in products]
        logger.info("[monitor] Keepa storefront empty/failed for %s, falling back to scrape", seller_id)
    return scrape_storefront_asins(seller_id)


# ── Amazon scraper (fallback) ────────────────────────────────────────────────

def scrape_storefront_asins(seller_id: str) -> list:
    """Lightweight HTTP scrape of a seller storefront sorted by newest arrivals.

    Returns a list of up to 50 ASIN strings. Uses requests + BeautifulSoup
    (no Playwright) to stay fast and low-cost.
    """
    url = f"https://www.amazon.com/s?me={seller_id}&sort=date-desc-rank"
    ua_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    ]
    headers = {
        "User-Agent": random.choice(ua_pool),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.warning("[monitor] Storefront %s returned HTTP %s", seller_id, resp.status_code)
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        asins = []
        for tag in soup.select("[data-asin]"):
            asin = tag.get("data-asin", "").strip()
            if asin and len(asin) == 10 and asin not in asins:
                asins.append(asin)
        return asins[:50]
    except Exception as exc:
        logger.error("[monitor] Scrape error for %s: %s", seller_id, exc)
        return []


def _get_product_name_price(asin: str):
    """Quick Keepa lookup for product name + current price.

    Returns (name, price) -- both may be None/asin fallback if Keepa unavailable.
    """
    try:
        from keepa_client import KeepaClient
        kc = KeepaClient()
        product = kc.get_product(asin)
        if product:
            name = product.get("title") or product.get("name") or asin
            price = product.get("amazon_price") or product.get("buyBoxPrice")
            return name, price
    except Exception:
        pass
    return asin, None


# ── Grading logic (Amazon-side signals only) ─────────────────────────────────

def _grade_from_amazon_signals(
    bsr: Optional[int], bsr_drops_30d: int, fba_seller_count: Optional[int],
    amazon_on_listing: bool, category: Optional[str],
) -> str:
    """Return A / B / C grade based on demand/competition signals from Keepa."""
    score = 0

    if bsr and bsr < 3000:
        score += 3
    elif bsr and bsr < 10000:
        score += 2
    elif bsr and bsr < 50000:
        score += 1

    if bsr_drops_30d >= 30:
        score += 2
    elif bsr_drops_30d >= 10:
        score += 1

    if fba_seller_count is not None:
        if 2 <= fba_seller_count <= 8:
            score += 2
        elif fba_seller_count > 20:
            score -= 2

    if not amazon_on_listing:
        score += 2
    else:
        score -= 3

    risky_keywords = ["aerosol", "automotive", "chemical", "battery", "explosive"]
    if category and any(kw in category.lower() for kw in risky_keywords):
        score -= 2

    if score >= 6:
        return "A"
    if score >= 3:
        return "B"
    return "C"


# ── Stage 2 background pipeline ──────────────────────────────────────────────

def _run_stage2(
    seller_id: str, seller_name: str, asin: str,
    product_name: str, amazon_price: Optional[float],
    message_id: Optional[str], alert_id: int,
) -> None:
    """Run in a background thread: Keepa deep-fetch + retailer scan -> edit Discord message."""
    try:
        db = _get_db()

        bsr = None
        bsr_drops_30d = 0
        fba_sellers = None
        amazon_on_listing = False
        category = None

        # Keepa deep fetch
        try:
            from keepa_client import KeepaClient
            kc = KeepaClient()
            product = kc.get_product(asin)
            if product:
                bsr = product.get("sales_rank")
                bsr_drops_30d = int(product.get("bsr_drops_30d") or 0)
                fba_sellers = product.get("fba_seller_count")
                amazon_on_listing = bool(product.get("amazon_on_listing", False))
                category = product.get("category")
                if not amazon_price:
                    amazon_price = product.get("amazon_price") or product.get("buyBoxPrice")
                if not product_name or product_name == asin:
                    product_name = product.get("title") or product.get("name") or asin
        except Exception as exc:
            logger.warning("[monitor] Keepa fetch failed for %s: %s", asin, exc)

        # Initial grade from Amazon signals
        grade = _grade_from_amazon_signals(
            bsr, bsr_drops_30d, fba_sellers, amazon_on_listing, category
        )

        profit = None
        roi = None
        retailer_name = None
        buy_link = None
        skip_reason = None

        # Retailer scan only for A/B grades (save resources on C)
        if grade in ("A", "B"):
            try:
                import subprocess
                source_script = os.path.join(os.path.dirname(__file__), "source.py")
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                result = subprocess.run(
                    [sys.executable, source_script, "asin", "--asin", asin, "--max-results", "3"],
                    capture_output=True, text=True, timeout=120, cwd=project_root,
                )
                if result.returncode == 0 and result.stdout:
                    raw = json.loads(result.stdout)
                    products_found = raw.get("products", [])
                    if products_found:
                        best = max(
                            products_found,
                            key=lambda p: (p.get("profitability") or {}).get("roi_percent", 0),
                        )
                        prof = best.get("profitability", {})
                        profit = prof.get("profit_per_unit")
                        roi = prof.get("roi_percent")
                        retailer_name = best.get("retailer")
                        buy_link = best.get("url") or best.get("product_url")
                        verdict = prof.get("verdict", "SKIP")
                        if verdict == "SKIP":
                            grade = "C"
                            skip_reason = prof.get("skip_reason", "Below profit threshold")
                        elif verdict == "BUY":
                            grade = "A"
                        else:
                            grade = "B"
            except subprocess.TimeoutExpired:
                logger.warning("[monitor] Retailer scan timed out for %s", asin)
            except Exception as exc:
                logger.error("[monitor] Retailer scan error for %s: %s", asin, exc)

        # Convergence check
        convergence_count = db.count_recent_asin_alerts(asin, hours=CONVERGENCE_WINDOW_HOURS)

        # Persist results
        db.update_storefront_alert(
            alert_id=alert_id, grade=grade, profit=profit, roi=roi,
            retailer=retailer_name, buy_link=buy_link,
            bsr=bsr, bsr_drops_30d=bsr_drops_30d, fba_sellers=fba_sellers,
            amazon_on_listing=amazon_on_listing, skip_reason=skip_reason,
            stage="complete",
        )
        db.update_storefront_last_active(seller_id, had_new_product=True)

        # Step 13: Write to unified scan_results for cross-mode querying
        try:
            from storefront_stalker import normalize_to_schema_b
            schema_b = normalize_to_schema_b({
                "asin": asin, "title": product_name, "price": amazon_price,
                "sales_rank": bsr, "fba_seller_count": fba_sellers,
                "amazon_on_listing": amazon_on_listing,
                "deal_score": {"A": 80, "B": 60, "C": 40, "?": 20}.get(grade, 20),
            }, seller_id=seller_id)
            schema_b["estimated_profit"] = profit
            schema_b["estimated_roi"] = roi
            schema_b["source_url"] = buy_link or f"https://www.amazon.com/dp/{asin}"
            schema_b["source_retailer"] = retailer_name or f"Storefront Monitor ({seller_id})"
            schema_b["mode"] = "storefront_monitor"
            db.insert_scan_result(schema_b, mode="storefront_monitor")
        except Exception as exc:
            logger.debug("[monitor] Schema B write failed for %s: %s", asin, exc)

        # Build final embed
        embed = _build_stage2_embed(
            seller_name=seller_name, asin=asin, product_name=product_name,
            grade=grade, profit=profit, roi=roi,
            retailer=retailer_name, buy_link=buy_link,
            amazon_price=amazon_price, bsr=bsr,
            bsr_drops=bsr_drops_30d, fba_sellers=fba_sellers,
            amazon_on_listing=amazon_on_listing, skip_reason=skip_reason,
            convergence_count=convergence_count,
        )

        # Edit the Stage 1 Discord message
        if message_id:
            _edit_discord_message(message_id, embed)

        # Separate HOT DEAL blast if convergence threshold crossed
        if convergence_count >= CONVERGENCE_THRESHOLD:
            hot_embed = dict(embed)
            hot_embed["title"] = (
                f"HOT DEAL -- {convergence_count} sellers added the same product!"
            )
            _send_discord_webhook(hot_embed)

        logger.info("[monitor] Stage 2 complete for %s -- grade %s", asin, grade)

    except Exception as exc:
        logger.error("[monitor] Stage 2 error for ASIN %s: %s", asin, exc)


# ── Main poll cycle ──────────────────────────────────────────────────────────

def run_monitor_cycle() -> None:
    """Check every tracked storefront for new products. Main cron entry point."""
    db = _get_db()
    storefronts = db.get_tracked_storefronts()

    if not storefronts:
        logger.info("[monitor] No storefronts tracked yet")
        return

    logger.info("[monitor] Checking %d storefronts", len(storefronts))

    for sf in storefronts:
        seller_id = sf["seller_id"]
        seller_name = sf["seller_name"]
        known_asins = set(json.loads(sf.get("known_asins_json") or "[]"))

        try:
            current_asins = fetch_storefront_asins(seller_id, use_keepa=USE_KEEPA_API)
        except Exception as exc:
            logger.error("[monitor] Failed to fetch storefront %s: %s", seller_id, exc)
            continue

        if not current_asins:
            continue

        new_asins = [a for a in current_asins if a not in known_asins]

        # Retirement status update
        _check_and_update_retirement(db, sf, bool(new_asins))

        # Always update the known ASIN set
        updated_known = list(known_asins | set(current_asins))
        db.update_storefront_known_asins(seller_id, updated_known)

        # Competitor auto-discovery: suggest new sellers to watch
        if USE_KEEPA_API and new_asins:
            try:
                competitors = _discover_competitors(seller_id)
                tracked_ids = {s["seller_id"] for s in storefronts}
                for comp in competitors:
                    if comp["seller_id"] not in tracked_ids:
                        logger.info(
                            "[monitor] Suggested new seller to watch: %s (%s) — "
                            "competitor of %s",
                            comp.get("seller_name", "?"), comp["seller_id"], seller_name,
                        )
            except Exception as exc:
                logger.debug("[monitor] Competitor discovery skipped for %s: %s", seller_id, exc)

        for asin in new_asins:
            logger.info("[monitor] New ASIN %s from seller %s", asin, seller_name)

            product_name, amazon_price = _get_product_name_price(asin)

            # Stage 1: instant Discord ping
            stage1_embed = _build_stage1_embed(seller_name, asin, product_name, amazon_price)
            message_id = _send_discord_webhook(stage1_embed)

            alert_id = db.insert_storefront_alert(
                seller_id=seller_id, asin=asin, product_name=product_name,
                amazon_price=amazon_price, discord_message_id=message_id,
                stage="stage1",
            )

            # Stage 2: background deep analysis
            t = threading.Thread(
                target=_run_stage2,
                args=(seller_id, seller_name, asin, product_name,
                      amazon_price, message_id, alert_id),
                daemon=True,
            )
            t.start()

        # Small jitter between sellers to avoid pattern detection
        time.sleep(random.uniform(2, 6))


def _check_and_update_retirement(db: object, sf: dict, had_new_product: bool) -> None:
    """Mark seller quiet or retired if they haven't added products recently."""
    if had_new_product:
        db.update_storefront_status(sf["seller_id"], "active")
        return
    last_active_str = sf.get("last_active_at")
    if not last_active_str:
        return
    try:
        last_active = datetime.fromisoformat(last_active_str)
        days_quiet = (datetime.utcnow() - last_active).days
        if days_quiet >= RETIREMENT_DAYS:
            db.update_storefront_status(sf["seller_id"], "retired")
            logger.info(
                "[monitor] Seller %s marked retired (%d days quiet)",
                sf["seller_name"], days_quiet,
            )
        elif days_quiet >= 14:
            db.update_storefront_status(sf["seller_id"], "quiet")
    except (ValueError, TypeError):
        pass


def update_seller_accuracy(seller_id: str, was_profitable: bool) -> None:
    """Update seller accuracy from student feedback (BUY confirmed or not)."""
    db = _get_db()
    db.update_storefront_accuracy(seller_id, was_profitable)


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Storefront Monitor -- watches seller storefronts")
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Run one monitor cycle now")
    run_p.add_argument("--no-keepa", action="store_true",
                       help="Force HTTP scrape instead of Keepa API")

    watch_p = sub.add_parser("watch", help="Poll continuously on an interval")
    watch_p.add_argument("--interval", type=int, default=POLL_INTERVAL_MINUTES,
                         help="Poll interval in minutes (default: 15)")
    watch_p.add_argument("--no-keepa", action="store_true",
                         help="Force HTTP scrape instead of Keepa API")

    add_p = sub.add_parser("add", help="Add a seller storefront to watch")
    add_p.add_argument("--seller-id", required=True, help="Amazon seller ID")
    add_p.add_argument("--name", required=True, help="Human-readable seller nickname")
    add_p.add_argument("--notes", default="", help="Optional notes")

    sub.add_parser("list", help="List all tracked storefronts")

    remove_p = sub.add_parser("remove", help="Remove a seller from the watchlist")
    remove_p.add_argument("--seller-id", required=True)

    args = parser.parse_args()

    if args.cmd == "run":
        if getattr(args, "no_keepa", False):
            USE_KEEPA_API = False
        run_monitor_cycle()

    elif args.cmd == "watch":
        if getattr(args, "no_keepa", False):
            USE_KEEPA_API = False
        logger.info(
            "[monitor] Starting watch loop -- %d min interval (+/-%ds jitter) [keepa=%s]",
            args.interval, JITTER_SECONDS, USE_KEEPA_API,
        )
        while True:
            run_monitor_cycle()
            jitter = random.randint(-JITTER_SECONDS, JITTER_SECONDS)
            sleep_secs = max(60, args.interval * 60 + jitter)
            logger.info("[monitor] Next check in %ds", sleep_secs)
            time.sleep(sleep_secs)

    elif args.cmd == "add":
        db = _get_db()
        db.add_tracked_storefront(args.seller_id, args.name, args.notes)
        print(f"Added: {args.name} ({args.seller_id})")

    elif args.cmd == "list":
        db = _get_db()
        rows = db.get_tracked_storefronts()
        if not rows:
            print("No storefronts tracked.")
        for sf in rows:
            acc = sf.get("accuracy_score", 0)
            print(
                f"  {sf['seller_name']:30s}  {sf['seller_id']:16s}  "
                f"acc:{acc:.0%}  status:{sf.get('status', 'active')}"
            )

    elif args.cmd == "remove":
        db = _get_db()
        db.remove_tracked_storefront(args.seller_id)
        print(f"Removed {args.seller_id}")

    else:
        parser.print_help()
