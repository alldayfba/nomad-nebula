#!/usr/bin/env python3
"""
Script: stock_monitor.py
Purpose: Monitor competitor FBA seller stock levels over time using Keepa.
         Alerts when a competitor goes out of stock on a profitable ASIN —
         a stockout is a 3-7 day window to capture Buy Box.
Inputs:  CLI subcommands — watch, check, alerts, history, import
Outputs: Telegram alerts, stdout JSON, SQLite history in price_tracker.db

CLI:
    python execution/stock_monitor.py watch add --asin B08XYZ1234 --name "Widget Pro"
    python execution/stock_monitor.py watch list
    python execution/stock_monitor.py watch remove --asin B08XYZ1234
    python execution/stock_monitor.py watch import --results .tmp/sourcing/results.json
    python execution/stock_monitor.py check [--alert]
    python execution/stock_monitor.py alerts [--days 7]
    python execution/stock_monitor.py history --asin B08XYZ1234 --days 30

Cron (every 6 hours):
    0 */6 * * * .venv/bin/python execution/stock_monitor.py check --alert
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / ".tmp" / "sourcing" / "price_tracker.db"

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY")

# Alert thresholds
COMPETITOR_EXIT_THRESHOLD = 2    # FBA count dropped by this many from baseline
STOCKOUT_BSR_THRESHOLD = 50_000  # Only flag stockout opportunities below this BSR
PRICE_DROP_PCT = 15.0            # Buy box price drop % to trigger alert


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stock_watchlist (
    id INTEGER PRIMARY KEY,
    asin TEXT UNIQUE NOT NULL,
    name TEXT DEFAULT '',
    category TEXT DEFAULT '',
    last_fba_count INTEGER DEFAULT 0,
    last_amazon_on INTEGER DEFAULT 0,
    last_buy_box_price REAL DEFAULT 0,
    baseline_fba_count INTEGER DEFAULT 0,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_checked TEXT,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS stock_history (
    id INTEGER PRIMARY KEY,
    asin TEXT NOT NULL,
    fba_count INTEGER,
    amazon_on INTEGER DEFAULT 0,
    buy_box_price REAL,
    checked_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_alerts (
    id INTEGER PRIMARY KEY,
    asin TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    acknowledged INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_stock_history_asin ON stock_history(asin);
CREATE INDEX IF NOT EXISTS idx_stock_history_checked ON stock_history(checked_at);
CREATE INDEX IF NOT EXISTS idx_stock_alerts_unack ON stock_alerts(acknowledged, detected_at);
"""


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    """Get database connection with WAL mode and stock monitor schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


# ── Keepa Integration ─────────────────────────────────────────────────────────

def _last_valid(csv_list, index):
    """Get last non-negative value from a Keepa CSV array at the given index."""
    if not csv_list or index >= len(csv_list) or not csv_list[index]:
        return None
    arr = csv_list[index]
    for i in range(len(arr) - 1, 0, -2):
        if arr[i] >= 0:
            return arr[i]
    return None


def get_keepa_stock_data(asin):
    """Fetch stock-relevant data from Keepa for a single ASIN.

    Returns dict with keys:
        fba_count, amazon_on, buy_box_price, sales_rank, new_offer_count
    or None on failure / no API key.
    """
    if not KEEPA_API_KEY:
        print("[stock_monitor] ERROR: KEEPA_API_KEY not set in .env", file=sys.stderr)
        return None

    try:
        import requests
        params = {
            "key": KEEPA_API_KEY,
            "domain": "1",  # amazon.com
            "asin": asin,
        }
        resp = requests.get("https://api.keepa.com/product", params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("products"):
            print(f"  [keepa] No product data for {asin}", file=sys.stderr)
            return None

        product = data["products"][0]
        csv_data = product.get("csv", [])

        # CSV index 11 = new offer count
        new_offer_count = _last_valid(csv_data, 11)

        # CSV index 0 = Amazon price (>0 means Amazon is selling)
        amazon_price_raw = _last_valid(csv_data, 0)
        amazon_on = 1 if amazon_price_raw is not None and amazon_price_raw > 0 else 0

        # CSV index 18 = buy box price (in cents)
        buy_box_raw = _last_valid(csv_data, 18)
        buy_box_price = buy_box_raw / 100.0 if buy_box_raw is not None else None

        # FBA seller count (index 34 = Buy Box eligible FBA offers)
        fba_count = _last_valid(csv_data, 34)
        # Fall back to new offer count if fba_count unavailable
        if fba_count is None:
            fba_count = new_offer_count

        sales_rank = product.get("salesRankCurrent")
        if sales_rank is not None and sales_rank < 0:
            sales_rank = None

        return {
            "fba_count": fba_count,
            "amazon_on": amazon_on,
            "buy_box_price": buy_box_price,
            "sales_rank": sales_rank,
            "new_offer_count": new_offer_count,
        }

    except Exception as e:
        print(f"  [keepa error] {asin}: {e}", file=sys.stderr)
        return None


# ── Core: Watch Management ────────────────────────────────────────────────────

def add_to_watchlist(asin, name="", category=""):
    """Add an ASIN to the stock watchlist. No-op if already present (reactivates)."""
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO stock_watchlist (asin, name, category, active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(asin) DO UPDATE SET
                name = COALESCE(NULLIF(excluded.name, ''), stock_watchlist.name),
                category = COALESCE(NULLIF(excluded.category, ''), stock_watchlist.category),
                active = 1
        """, (asin.strip().upper(), name, category))
        conn.commit()
        return True
    finally:
        conn.close()


def remove_from_watchlist(asin):
    """Deactivate an ASIN (soft delete)."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE stock_watchlist SET active = 0 WHERE asin = ?",
            (asin.strip().upper(),)
        )
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def get_watchlist(active_only=True):
    """Return all watched ASINs."""
    conn = get_db()
    try:
        query = "SELECT * FROM stock_watchlist"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY added_at DESC"
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def import_from_results(results_path):
    """Import BUY products from a sourcing results JSON into the watchlist.

    Returns list of added ASINs.
    """
    path = Path(results_path)
    if not path.exists():
        print(f"[stock_monitor] File not found: {path}", file=sys.stderr)
        return []

    with open(path) as f:
        data = json.load(f)

    products = data.get("products", [])
    added = []

    for p in products:
        prof = p.get("profitability", {}) or {}
        amz = p.get("amazon", {}) or {}
        verdict = prof.get("verdict", "")

        if verdict != "BUY":
            continue

        asin = amz.get("asin")
        if not asin:
            continue

        name = p.get("name", "")
        category = amz.get("category", "")
        add_to_watchlist(asin, name=name, category=category)
        added.append(asin)
        print(f"  [watch] Added {asin} — {name[:50]}", file=sys.stderr)

    return added


# ── Core: Stock Check ─────────────────────────────────────────────────────────

def check_all(send_alert=False):
    """Poll Keepa for all active watched ASINs. Record history, detect changes.

    Returns list of alert dicts generated during this run.
    """
    watchlist = get_watchlist(active_only=True)
    if not watchlist:
        print("[stock_monitor] Watchlist is empty.", file=sys.stderr)
        return []

    print(f"[stock_monitor] Checking {len(watchlist)} ASINs...", file=sys.stderr)
    now = datetime.utcnow().isoformat()
    all_alerts = []
    conn = get_db()

    try:
        for entry in watchlist:
            asin = entry["asin"]
            name = entry["name"] or asin
            print(f"  Polling {asin} — {name[:40]}", file=sys.stderr)

            stock = get_keepa_stock_data(asin)
            if stock is None:
                print(f"    [skip] No data returned", file=sys.stderr)
                continue

            fba_count = stock["fba_count"]
            amazon_on = stock["amazon_on"]
            buy_box_price = stock["buy_box_price"]
            sales_rank = stock["sales_rank"]

            # Record history
            conn.execute("""
                INSERT INTO stock_history (asin, fba_count, amazon_on, buy_box_price, checked_at)
                VALUES (?, ?, ?, ?, ?)
            """, (asin, fba_count, amazon_on, buy_box_price, now))

            # Determine baseline — use stored baseline, or set it on first check
            baseline_fba = entry["baseline_fba_count"]
            if baseline_fba == 0 and fba_count is not None:
                baseline_fba = fba_count
                conn.execute(
                    "UPDATE stock_watchlist SET baseline_fba_count = ? WHERE asin = ?",
                    (fba_count, asin)
                )

            prev_fba = entry["last_fba_count"]
            prev_amazon_on = entry["last_amazon_on"]
            prev_buy_box = entry["last_buy_box_price"]

            new_alerts = _detect_alerts(
                conn=conn,
                asin=asin,
                name=name,
                fba_count=fba_count,
                amazon_on=amazon_on,
                buy_box_price=buy_box_price,
                sales_rank=sales_rank,
                prev_fba=prev_fba,
                prev_amazon_on=prev_amazon_on,
                prev_buy_box=prev_buy_box,
                baseline_fba=baseline_fba,
                now=now,
            )
            all_alerts.extend(new_alerts)

            # Update watchlist state
            conn.execute("""
                UPDATE stock_watchlist SET
                    last_fba_count = ?,
                    last_amazon_on = ?,
                    last_buy_box_price = ?,
                    last_checked = ?
                WHERE asin = ?
            """, (
                fba_count if fba_count is not None else entry["last_fba_count"],
                amazon_on,
                buy_box_price if buy_box_price is not None else entry["last_buy_box_price"],
                now,
                asin,
            ))

            if new_alerts:
                types = ", ".join(a["alert_type"] for a in new_alerts)
                print(f"    [alert] {types}", file=sys.stderr)

        conn.commit()
    finally:
        conn.close()

    print(f"[stock_monitor] Done. {len(all_alerts)} new alert(s).", file=sys.stderr)

    if send_alert and all_alerts:
        _send_stock_alerts(all_alerts)

    return all_alerts


def _detect_alerts(conn, asin, name, fba_count, amazon_on, buy_box_price,
                   sales_rank, prev_fba, prev_amazon_on, prev_buy_box,
                   baseline_fba, now):
    """Evaluate stock data against thresholds. Insert and return new alert dicts."""
    alerts = []

    # Only compare when we have a prior check (prev_fba > 0 means we've checked before)
    has_history = prev_fba is not None and prev_fba > 0

    # competitor_exit: FBA count dropped by 2+ from baseline
    if (fba_count is not None and baseline_fba
            and (baseline_fba - fba_count) >= COMPETITOR_EXIT_THRESHOLD):
        alert = _insert_alert(
            conn, asin, "competitor_exit",
            old_value=str(baseline_fba),
            new_value=str(fba_count),
            now=now,
        )
        alerts.append(alert)
        print(f"    competitor_exit: {baseline_fba} -> {fba_count} FBA sellers", file=sys.stderr)

    # amazon_exit: Amazon was on listing, now isn't
    if has_history and prev_amazon_on == 1 and amazon_on == 0:
        alert = _insert_alert(
            conn, asin, "amazon_exit",
            old_value="amazon_on",
            new_value="amazon_off",
            now=now,
        )
        alerts.append(alert)
        print(f"    amazon_exit: Amazon left the listing", file=sys.stderr)

    # stockout_opportunity: FBA count dropped to 0-1 on a high-velocity product
    if (fba_count is not None and fba_count <= 1
            and sales_rank is not None and sales_rank < STOCKOUT_BSR_THRESHOLD
            and has_history and prev_fba > 1):
        alert = _insert_alert(
            conn, asin, "stockout_opportunity",
            old_value=str(prev_fba),
            new_value=str(fba_count),
            now=now,
        )
        alerts.append(alert)
        print(f"    stockout_opportunity: FBA count {prev_fba} -> {fba_count}, BSR {sales_rank}", file=sys.stderr)

    # price_drop: Buy box price dropped >15% from last check
    if (has_history and prev_buy_box and prev_buy_box > 0
            and buy_box_price is not None and buy_box_price > 0):
        drop_pct = ((prev_buy_box - buy_box_price) / prev_buy_box) * 100
        if drop_pct >= PRICE_DROP_PCT:
            alert = _insert_alert(
                conn, asin, "price_drop",
                old_value=f"{prev_buy_box:.2f}",
                new_value=f"{buy_box_price:.2f}",
                now=now,
            )
            alerts.append(alert)
            print(f"    price_drop: ${prev_buy_box:.2f} -> ${buy_box_price:.2f} ({drop_pct:.1f}%)", file=sys.stderr)

    return alerts


def _insert_alert(conn, asin, alert_type, old_value, new_value, now):
    """Insert a stock alert row and return it as a dict."""
    cursor = conn.execute("""
        INSERT INTO stock_alerts (asin, alert_type, old_value, new_value, detected_at)
        VALUES (?, ?, ?, ?, ?)
    """, (asin, alert_type, old_value, new_value, now))
    return {
        "id": cursor.lastrowid,
        "asin": asin,
        "alert_type": alert_type,
        "old_value": old_value,
        "new_value": new_value,
        "detected_at": now,
    }


# ── Core: Read Alerts / History ───────────────────────────────────────────────

def get_alerts(days=7, unacknowledged_only=True):
    """Return stock alerts within the last N days."""
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = """
            SELECT sa.*, sw.name
            FROM stock_alerts sa
            LEFT JOIN stock_watchlist sw ON sw.asin = sa.asin
            WHERE sa.detected_at >= ?
        """
        params = [cutoff]
        if unacknowledged_only:
            query += " AND sa.acknowledged = 0"
        query += " ORDER BY sa.detected_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_stock_history(asin, days=30):
    """Return stock history for an ASIN over the last N days."""
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT sh.*, sw.name
            FROM stock_history sh
            LEFT JOIN stock_watchlist sw ON sw.asin = sh.asin
            WHERE sh.asin = ? AND sh.checked_at >= ?
            ORDER BY sh.checked_at ASC
        """, (asin.strip().upper(), cutoff)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Telegram Alert Formatting ─────────────────────────────────────────────────

def _send_stock_alerts(alerts):
    """Format and send stock alerts via Telegram."""
    try:
        import importlib.util
        alerts_path = PROJECT_ROOT / "execution" / "sourcing_alerts.py"
        spec = importlib.util.spec_from_file_location("sourcing_alerts", alerts_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        send_telegram = mod.send_telegram_alert
    except Exception as e:
        print(f"[stock_monitor] Could not load sourcing_alerts: {e}", file=sys.stderr)
        return False

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"STOCK MONITOR ALERT -- {now_str}",
        "=" * 36,
        "",
    ]

    label_map = {
        "competitor_exit":     "Competitors Leaving",
        "amazon_exit":         "Amazon Left Listing",
        "stockout_opportunity": "Stockout Opportunity",
        "price_drop":          "Buy Box Price Drop",
    }

    for alert in alerts:
        atype = alert["alert_type"]
        asin = alert["asin"]
        label = label_map.get(atype, atype)
        old_val = alert.get("old_value", "")
        new_val = alert.get("new_value", "")

        lines.append(f"[{label}] {asin}")

        if atype == "competitor_exit":
            lines.append(f"  FBA sellers: {old_val} (baseline) -> {new_val} now")
        elif atype == "amazon_exit":
            lines.append("  Amazon.com dropped off the listing")
        elif atype == "stockout_opportunity":
            lines.append(f"  FBA count: {old_val} -> {new_val} | High-velocity ASIN")
        elif atype == "price_drop":
            try:
                drop = ((float(old_val) - float(new_val)) / float(old_val)) * 100
                lines.append(f"  Buy Box: ${old_val} -> ${new_val} ({drop:.1f}% drop)")
            except (ValueError, ZeroDivisionError):
                lines.append(f"  Buy Box: ${old_val} -> ${new_val}")

        lines.append(f"  amazon.com/dp/{asin}")
        lines.append("")

    lines.append(f"Total: {len(alerts)} alert(s) | amazon.com/")
    message = "\n".join(lines)

    return send_telegram(message)


# ── CLI Handlers ──────────────────────────────────────────────────────────────

def cli_watch(args):
    """CLI handler: watch subcommand dispatcher."""
    if args.watch_cmd == "add":
        asin = args.asin.strip().upper()
        add_to_watchlist(asin, name=args.name or "", category=args.category or "")
        print(json.dumps({"added": asin, "name": args.name or ""}))

    elif args.watch_cmd == "remove":
        asin = args.asin.strip().upper()
        removed = remove_from_watchlist(asin)
        print(json.dumps({"removed": asin, "success": removed}))

    elif args.watch_cmd == "list":
        watchlist = get_watchlist(active_only=not args.all)
        print(json.dumps(watchlist, indent=2))

    elif args.watch_cmd == "import":
        added = import_from_results(args.results)
        print(json.dumps({"imported": len(added), "asins": added}, indent=2))

    else:
        print("Unknown watch subcommand. Use: add, remove, list, import", file=sys.stderr)
        sys.exit(1)


def cli_check(args):
    """CLI handler: check all watched ASINs."""
    new_alerts = check_all(send_alert=args.alert)
    print(json.dumps({
        "checked_at": datetime.utcnow().isoformat(),
        "alerts_generated": len(new_alerts),
        "alerts": new_alerts,
    }, indent=2))


def cli_alerts(args):
    """CLI handler: view unacknowledged stock alerts."""
    alerts = get_alerts(days=args.days, unacknowledged_only=not args.all)
    if not alerts:
        print(f"No alerts in the last {args.days} days.", file=sys.stderr)
        sys.exit(0)
    print(json.dumps(alerts, indent=2))


def cli_history(args):
    """CLI handler: view stock level history for an ASIN."""
    history = get_stock_history(args.asin, days=args.days)
    if not history:
        print(f"No history for {args.asin} in the last {args.days} days.", file=sys.stderr)
        sys.exit(0)
    print(json.dumps(history, indent=2))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="FBA Stock Monitor — track competitor stock via Keepa, alert on opportunities"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # watch
    p_watch = subparsers.add_parser("watch", help="Manage the ASIN watchlist")
    watch_sub = p_watch.add_subparsers(dest="watch_cmd", help="Watch actions")

    p_watch_add = watch_sub.add_parser("add", help="Add an ASIN to watchlist")
    p_watch_add.add_argument("--asin", required=True, help="ASIN to watch")
    p_watch_add.add_argument("--name", default="", help="Product name (optional)")
    p_watch_add.add_argument("--category", default="", help="Category (optional)")

    p_watch_remove = watch_sub.add_parser("remove", help="Remove an ASIN from watchlist")
    p_watch_remove.add_argument("--asin", required=True, help="ASIN to remove")

    p_watch_list = watch_sub.add_parser("list", help="List watched ASINs")
    p_watch_list.add_argument("--all", action="store_true", help="Include inactive ASINs")

    p_watch_import = watch_sub.add_parser("import", help="Import BUY products from sourcing results")
    p_watch_import.add_argument("--results", required=True, help="Path to sourcing results JSON")

    p_watch.set_defaults(func=cli_watch)

    # check
    p_check = subparsers.add_parser("check", help="Poll Keepa for all watched ASINs")
    p_check.add_argument("--alert", action="store_true",
                         help="Send Telegram alert if new alerts are detected")
    p_check.set_defaults(func=cli_check)

    # alerts
    p_alerts = subparsers.add_parser("alerts", help="View unacknowledged stock alerts")
    p_alerts.add_argument("--days", type=int, default=7,
                          help="Look back N days (default: 7)")
    p_alerts.add_argument("--all", action="store_true",
                          help="Include acknowledged alerts")
    p_alerts.set_defaults(func=cli_alerts)

    # history
    p_history = subparsers.add_parser("history", help="View stock level history for an ASIN")
    p_history.add_argument("--asin", required=True, help="ASIN to inspect")
    p_history.add_argument("--days", type=int, default=30,
                           help="Look back N days (default: 30)")
    p_history.set_defaults(func=cli_history)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
