#!/usr/bin/env python3
"""
Script: scrape_cardbear.py
Purpose: Scrape CardBear.com for gift card discount rates, store in SQLite,
         detect high-discount opportunities, and optionally trigger sourcing.
Inputs:  Subcommands: scrape, top, history, trigger-sourcing
Outputs: SQLite records, stdout JSON, optional Telegram alerts

CLI:
    python execution/scrape_cardbear.py scrape
    python execution/scrape_cardbear.py top [--min-discount 10] [--limit 20]
    python execution/scrape_cardbear.py history --retailer "Walmart" --days 30
    python execution/scrape_cardbear.py trigger-sourcing [--min-discount 10] [--dry-run]
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / ".tmp" / "sourcing" / "price_tracker.db"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python3"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ─── CardBear retailer name → sourcing URL mapping ─────────────────────────
# Maps CardBear retailer labels to clearance/deals URLs for auto-sourcing.
CARDBEAR_TO_SOURCING_URL = {
    "Walmart": "https://www.walmart.com/browse/clearance",
    "Target": "https://www.target.com/c/clearance",
    "Home Depot": "https://www.homedepot.com/b/Savings-Center/N-5yc1vZc2Hd",
    "CVS": "https://www.cvs.com/shop/deals",
    "Walgreens": "https://www.walgreens.com/store/store/sale/N=361377",
    "Costco": "https://www.costco.com/CatalogSearch?keyword=clearance",
}

# ─── Gift Card SQLite Schema ───────────────────────────────────────────────

GIFT_CARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS gift_card_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer_name TEXT NOT NULL,
    cardbear_url TEXT,
    discount_percent REAL NOT NULL,
    scraped_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gift_card_latest (
    retailer_name TEXT PRIMARY KEY,
    discount_percent REAL NOT NULL,
    cardbear_url TEXT,
    first_seen TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    previous_discount REAL
);

CREATE INDEX IF NOT EXISTS idx_gcr_retailer ON gift_card_rates(retailer_name);
CREATE INDEX IF NOT EXISTS idx_gcr_date ON gift_card_rates(scraped_at);
CREATE INDEX IF NOT EXISTS idx_gcl_discount ON gift_card_latest(discount_percent DESC);
"""


# ─── Database ───────────────────────────────────────────────────────────────

def get_db():
    """Get database connection with gift card tables created."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(GIFT_CARD_SCHEMA)
    return conn


# ─── Parsing ────────────────────────────────────────────────────────────────

def _parse_discount(text):
    """Parse '13% off' or '13.5% off' to float 13.0 or 13.5. Returns 0.0 if unparseable."""
    if not text:
        return 0.0
    match = re.search(r'([\d.]+)\s*%', str(text))
    return float(match.group(1)) if match else 0.0


def _extract_retailer_json(html):
    """Extract the embedded retailer JSON array from CardBear's page source.

    CardBear embeds all retailer data as a JavaScript array in the page.
    Each entry has: label, url, imgurl, discount.
    """
    # Extract individual retailer objects using regex
    # Each entry: {"label":"Name", "url":"...", "imgurl":"...", "discount":"X% off"}
    pattern = r'\{\s*"label"\s*:\s*"([^"]*?)"\s*,\s*"url"\s*:\s*"([^"]*?)"\s*,\s*"imgurl"\s*:\s*"([^"]*?)"\s*,\s*"discount"\s*:\s*"([^"]*?)"\s*\}'
    matches = re.findall(pattern, html)
    if matches:
        return [
            {"label": m[0], "url": m[1], "imgurl": m[2], "discount": m[3]}
            for m in matches
        ]

    # Fallback: try to find a full JSON array
    array_match = re.search(r'\[\s*\{[^{]*?"label".*?\}\s*\]', html, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ─── Core Scraper ───────────────────────────────────────────────────────────

def scrape_cardbear():
    """Fetch CardBear main page, extract gift card discount rates, store in SQLite.

    Returns dict with: retailers_scraped, retailers_with_discount, new_highs.
    """
    url = "https://www.cardbear.com"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    print(f"[cardbear] Fetching {url}...", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[cardbear] ERROR fetching CardBear: {e}", file=sys.stderr)
        raise

    retailers = _extract_retailer_json(html)
    if not retailers:
        raise RuntimeError("Could not find retailer JSON on CardBear page. "
                           "Site structure may have changed — update _extract_retailer_json().")

    now = datetime.utcnow().isoformat()
    conn = get_db()
    new_highs = []
    stored_count = 0

    try:
        for r in retailers:
            name = (r.get("label") or "").strip()
            cb_url = r.get("url", "")
            if cb_url and not cb_url.startswith("http"):
                cb_url = f"https://www.cardbear.com{cb_url}"
            discount = _parse_discount(r.get("discount", ""))

            if not name:
                continue
            if discount <= 0:
                # Still track that we saw it (with 0 discount) in latest table
                conn.execute("""
                    INSERT INTO gift_card_latest (retailer_name, discount_percent, cardbear_url, first_seen, last_updated, previous_discount)
                    VALUES (?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(retailer_name) DO UPDATE SET
                        previous_discount = gift_card_latest.discount_percent,
                        discount_percent = 0,
                        cardbear_url = excluded.cardbear_url,
                        last_updated = excluded.last_updated
                """, (name, 0, cb_url, now, now))
                continue

            # Check for discount increase
            prev = conn.execute(
                "SELECT discount_percent FROM gift_card_latest WHERE retailer_name = ?",
                (name,)
            ).fetchone()

            if prev and discount > prev["discount_percent"] and prev["discount_percent"] > 0:
                new_highs.append({
                    "retailer": name,
                    "old_discount": prev["discount_percent"],
                    "new_discount": discount,
                })

            # Insert history row
            conn.execute("""
                INSERT INTO gift_card_rates (retailer_name, cardbear_url, discount_percent, scraped_at)
                VALUES (?, ?, ?, ?)
            """, (name, cb_url, discount, now))

            # Upsert latest
            conn.execute("""
                INSERT INTO gift_card_latest (retailer_name, discount_percent, cardbear_url, first_seen, last_updated, previous_discount)
                VALUES (?, ?, ?, ?, ?, NULL)
                ON CONFLICT(retailer_name) DO UPDATE SET
                    previous_discount = gift_card_latest.discount_percent,
                    discount_percent = excluded.discount_percent,
                    cardbear_url = excluded.cardbear_url,
                    last_updated = excluded.last_updated
            """, (name, discount, cb_url, now, now))

            stored_count += 1

        conn.commit()
    finally:
        conn.close()

    result = {
        "retailers_scraped": len(retailers),
        "retailers_with_discount": stored_count,
        "new_highs": new_highs,
        "scraped_at": now,
    }

    print(f"[cardbear] Scraped {len(retailers)} retailers, "
          f"{stored_count} with active discounts.", file=sys.stderr)
    if new_highs:
        print(f"[cardbear] {len(new_highs)} discount increase(s) detected!", file=sys.stderr)

    return result


# ─── Query Functions (importable by other scripts) ─────────────────────────

def get_gift_card_discount(retailer_name):
    """Look up current gift card discount for a retailer. Returns float or 0.0.

    Performs exact match first, then case-insensitive partial match.
    This function is imported by calculate_fba_profitability.py.
    """
    conn = get_db()
    try:
        # Exact match
        row = conn.execute(
            "SELECT discount_percent FROM gift_card_latest WHERE retailer_name = ?",
            (retailer_name,)
        ).fetchone()
        if row and row["discount_percent"] > 0:
            return row["discount_percent"]

        # Partial match (case-insensitive)
        rows = conn.execute(
            "SELECT retailer_name, discount_percent FROM gift_card_latest WHERE discount_percent > 0"
        ).fetchall()

        name_lower = retailer_name.lower()
        for r in rows:
            r_lower = r["retailer_name"].lower()
            if r_lower in name_lower or name_lower in r_lower:
                return r["discount_percent"]

        return 0.0
    finally:
        conn.close()


def get_top_discounts(min_discount=5.0, limit=50):
    """Return list of retailers with highest current discounts.

    Returns list of dicts: retailer_name, discount_percent, cardbear_url, last_updated.
    """
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT retailer_name, discount_percent, cardbear_url, last_updated
            FROM gift_card_latest
            WHERE discount_percent >= ?
            ORDER BY discount_percent DESC
            LIMIT ?
        """, (min_discount, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_discount_history(retailer_name, days=30):
    """Get gift card discount history for a retailer over the last N days."""
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT retailer_name, discount_percent, scraped_at
            FROM gift_card_rates
            WHERE retailer_name = ? AND scraped_at >= ?
            ORDER BY scraped_at ASC
        """, (retailer_name, cutoff)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── Alerting ───────────────────────────────────────────────────────────────

def _send_high_discount_alert(new_highs, all_top):
    """Send Telegram alert when discount rates increase or are notably high."""
    try:
        # Import from sibling module
        alerts_path = Path(__file__).parent / "sourcing_alerts.py"
        if not alerts_path.exists():
            print("[cardbear] sourcing_alerts.py not found — skipping alert.", file=sys.stderr)
            return False

        import importlib.util
        spec = importlib.util.spec_from_file_location("sourcing_alerts", alerts_path)
        sourcing_alerts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sourcing_alerts)
        send_telegram = sourcing_alerts.send_telegram_alert
    except Exception as e:
        print(f"[cardbear] Could not load sourcing_alerts: {e}", file=sys.stderr)
        return False

    lines = [
        f"GIFT CARD ALERT -- {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 32,
        "",
    ]

    if new_highs:
        lines.append(f"DISCOUNT INCREASES ({len(new_highs)}):")
        for h in sorted(new_highs, key=lambda x: x["new_discount"], reverse=True):
            lines.append(f"  {h['retailer']}: {h['old_discount']}% -> {h['new_discount']}%")
        lines.append("")

    lines.append("TOP 10 DISCOUNTS:")
    for r in all_top[:10]:
        lines.append(f"  {r['retailer_name']}: {r['discount_percent']}% off")

    lines.append("")
    lines.append("Use --auto-giftcard in sourcing pipeline to apply these discounts.")

    return send_telegram("\n".join(lines))


# ─── Auto-Sourcing Trigger ─────────────────────────────────────────────────

def trigger_sourcing(min_discount=10.0, dry_run=True, max_products=30, min_roi=30):
    """For high-discount retailers that match known configs, trigger sourcing runs.

    Args:
        min_discount: Minimum gift card discount % to consider.
        dry_run: If True, only print recommendations. If False, run the pipeline.
        max_products: Max products per sourcing run.
        min_roi: Minimum ROI threshold.

    Returns:
        List of dicts with retailer info and action taken.
    """
    top = get_top_discounts(min_discount=min_discount, limit=50)
    actions = []

    for entry in top:
        name = entry["retailer_name"]
        discount = entry["discount_percent"]

        # Check if we have a sourcing URL for this retailer
        sourcing_url = None
        for cb_name, url in CARDBEAR_TO_SOURCING_URL.items():
            if cb_name.lower() in name.lower() or name.lower() in cb_name.lower():
                sourcing_url = url
                break

        if not sourcing_url:
            continue

        action = {
            "retailer": name,
            "discount_percent": discount,
            "sourcing_url": sourcing_url,
            "action": "dry_run" if dry_run else "triggered",
        }

        if dry_run:
            print(f"[cardbear] RECOMMEND: {name} has {discount}% gift card discount", file=sys.stderr)
            print(f"  Run: python execution/run_sourcing_pipeline.py "
                  f"--url \"{sourcing_url}\" --auto-giftcard --auto-cashback "
                  f"--max-products {max_products}", file=sys.stderr)
        else:
            print(f"[cardbear] TRIGGERING sourcing for {name} ({discount}% gift card)...",
                  file=sys.stderr)
            python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
            cmd = [
                python, str(PROJECT_ROOT / "execution" / "run_sourcing_pipeline.py"),
                "--url", sourcing_url,
                "--auto-giftcard",
                "--auto-cashback",
                "--max-products", str(max_products),
                "--min-roi", str(min_roi),
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                if result.returncode == 0:
                    action["action"] = "success"
                    print(f"[cardbear] Sourcing complete for {name}.", file=sys.stderr)
                else:
                    action["action"] = "failed"
                    action["error"] = result.stderr[-500:] if result.stderr else "Unknown error"
                    print(f"[cardbear] Sourcing FAILED for {name}: {result.stderr[-200:]}",
                          file=sys.stderr)
            except subprocess.TimeoutExpired:
                action["action"] = "timeout"
                print(f"[cardbear] Sourcing TIMED OUT for {name}.", file=sys.stderr)

        actions.append(action)

    if not actions:
        print(f"[cardbear] No known retailers found with >= {min_discount}% gift card discount.",
              file=sys.stderr)

    return actions


# ─── CLI ────────────────────────────────────────────────────────────────────

def cli_scrape(args):
    """CLI: Scrape CardBear and store rates."""
    result = scrape_cardbear()
    print(json.dumps(result, indent=2))

    # Send alert if there are new highs or if explicitly requested
    if result["new_highs"] or args.alert:
        top = get_top_discounts(min_discount=5.0, limit=10)
        if top:
            _send_high_discount_alert(result["new_highs"], top)


def cli_top(args):
    """CLI: Show top gift card discounts."""
    top = get_top_discounts(min_discount=args.min_discount, limit=args.limit)
    if not top:
        print(f"No retailers with >= {args.min_discount}% discount found.", file=sys.stderr)
        sys.exit(0)

    print(json.dumps(top, indent=2))
    print(f"\n{len(top)} retailer(s) with >= {args.min_discount}% discount.", file=sys.stderr)


def cli_history(args):
    """CLI: Show discount history for a retailer."""
    history = get_discount_history(args.retailer, days=args.days)
    if not history:
        print(f"No discount history for '{args.retailer}' in the last {args.days} days.",
              file=sys.stderr)
        sys.exit(0)
    print(json.dumps(history, indent=2))


def cli_trigger(args):
    """CLI: Trigger sourcing for high-discount retailers."""
    actions = trigger_sourcing(
        min_discount=args.min_discount,
        dry_run=args.dry_run,
        max_products=args.max_products,
        min_roi=args.min_roi,
    )
    print(json.dumps(actions, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="CardBear Gift Card Discount Scraper — scrape, track, and auto-source"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scrape
    p_scrape = subparsers.add_parser("scrape", help="Scrape CardBear for current gift card discounts")
    p_scrape.add_argument("--alert", action="store_true",
                          help="Send Telegram alert even if no new highs")
    p_scrape.set_defaults(func=cli_scrape)

    # top
    p_top = subparsers.add_parser("top", help="Show top gift card discounts")
    p_top.add_argument("--min-discount", type=float, default=5.0,
                       help="Minimum discount %% to show (default: 5)")
    p_top.add_argument("--limit", type=int, default=20,
                       help="Max results (default: 20)")
    p_top.set_defaults(func=cli_top)

    # history
    p_history = subparsers.add_parser("history", help="Show discount history for a retailer")
    p_history.add_argument("--retailer", required=True, help="Retailer name (e.g., 'Walmart')")
    p_history.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")
    p_history.set_defaults(func=cli_history)

    # trigger-sourcing
    p_trigger = subparsers.add_parser("trigger-sourcing",
                                       help="Auto-trigger sourcing for high-discount retailers")
    p_trigger.add_argument("--min-discount", type=float, default=10.0,
                           help="Min gift card discount %% to trigger (default: 10)")
    p_trigger.add_argument("--dry-run", action="store_true", default=True,
                           help="Only print recommendations (default)")
    p_trigger.add_argument("--execute", action="store_true",
                           help="Actually run the sourcing pipeline")
    p_trigger.add_argument("--max-products", type=int, default=30,
                           help="Max products per sourcing run (default: 30)")
    p_trigger.add_argument("--min-roi", type=float, default=30,
                           help="Min ROI threshold (default: 30)")
    p_trigger.set_defaults(func=cli_trigger)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle --execute overriding --dry-run
    if hasattr(args, "execute") and args.execute:
        args.dry_run = False

    args.func(args)


if __name__ == "__main__":
    main()
