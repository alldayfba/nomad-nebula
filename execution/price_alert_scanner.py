from __future__ import annotations
"""
Price Alert Scanner — Cron job that checks watched ASINs across retailers.
Runs every 30 minutes. When a retailer price drops to a student's max_cost,
sends Discord webhook notification.

Usage:
    python execution/price_alert_scanner.py

Schedule via launchd or cron:
    */30 * * * * cd /path/to/nomad-nebula && source .venv/bin/activate && python execution/price_alert_scanner.py
"""
import os
import sys
import json
import logging
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def send_discord_alert(webhook_url: str, asin: str, retailer: str, retailer_price: float,
                        max_cost: float, roi_est: float, product_name: str, buy_url: str) -> bool:
    """Send a Discord webhook notification for a price alert."""
    if not webhook_url:
        logger.warning(f"No webhook URL for alert on {asin}")
        return False

    embed = {
        "title": f"Price Alert: {product_name[:60]}",
        "color": 0x00FF00,  # Green
        "fields": [
            {"name": "ASIN", "value": f"[{asin}](https://amazon.com/dp/{asin})", "inline": True},
            {"name": "Retailer", "value": retailer, "inline": True},
            {"name": "Retail Price", "value": f"${retailer_price:.2f}", "inline": True},
            {"name": "Your Max Cost", "value": f"${max_cost:.2f}", "inline": True},
            {"name": "Est. ROI", "value": f"{roi_est:.0f}%", "inline": True},
            {"name": "Buy Now", "value": f"[Retailer Link]({buy_url})", "inline": True},
        ],
        "footer": {"text": "24/7 Profits — Price Alert System"},
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        resp = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
        return resp.status_code == 204
    except Exception as e:
        logger.error(f"Discord webhook failed: {e}")
        return False


def run_price_alert_scan():
    """Main scanner loop — check all active watches."""
    try:
        from results_db import SourcingResultsDB
    except ImportError:
        logger.error("Could not import SourcingResultsDB")
        return

    db = SourcingResultsDB()
    watches = db.get_active_watches() if hasattr(db, 'get_active_watches') else []

    if not watches:
        logger.info("No active price watches. Exiting.")
        return

    logger.info(f"Checking {len(watches)} active price watches...")

    # Group by ASIN to batch retailer searches
    asin_watches: dict[str, list] = {}
    for watch in watches:
        asin = watch["asin"]
        if asin not in asin_watches:
            asin_watches[asin] = []
        asin_watches[asin].append(watch)

    try:
        from keepa_client import KeepaClient
        keepa = KeepaClient(os.getenv("KEEPA_API_KEY"))
    except Exception as e:
        logger.warning(f"Keepa unavailable for price alerts: {e}")
        keepa = None

    alerts_sent = 0
    for asin, watchers in asin_watches.items():
        min_max_cost = min(w["max_cost"] for w in watchers)

        # Search top retailers for this ASIN
        # Use existing source.py asin mode via subprocess for reliability
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "execution/source.py", "asin", "--asin", asin, "--max", "5", "--output", "json"],
                capture_output=True, text=True, timeout=120, cwd=os.path.dirname(os.path.dirname(__file__))
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                products = data.get("products", [])
                for product in products:
                    retail_price = product.get("buy_cost", 999)
                    retailer = product.get("source_retailer", "Unknown")
                    buy_url = product.get("source_url", "")
                    product_name = product.get("name", product.get("amazon_title", asin))

                    for watcher in watchers:
                        if retail_price <= watcher["max_cost"]:
                            roi_est = product.get("estimated_roi", 0)
                            sent = send_discord_alert(
                                watcher.get("discord_webhook", ""),
                                asin, retailer, retail_price,
                                watcher["max_cost"], roi_est, product_name, buy_url
                            )
                            if sent:
                                alerts_sent += 1
                                # Update last_notified
                                try:
                                    db.conn.execute(
                                        "UPDATE price_watches SET last_notified=? WHERE id=?",
                                        (datetime.now().isoformat(), watcher["id"])
                                    )
                                    db.conn.commit()
                                except Exception:
                                    pass
        except Exception as e:
            logger.warning(f"Error scanning ASIN {asin}: {e}")

    logger.info(f"Price alert scan complete. Sent {alerts_sent} alerts.")


if __name__ == "__main__":
    run_price_alert_scan()
