#!/usr/bin/env python3
"""
Script: price_tracker.py
Purpose: SQLite-based price tracking database for FBA sourcing agent.
         Stores sourcing results over time, tracks price history for ASINs,
         detects price drops/trends, and queries historical data.
Inputs:  CLI subcommands or imported functions
Outputs: Alerts, stats, price history (stdout JSON or return values)

CLI:
    python execution/price_tracker.py import --results path/to/results.json
    python execution/price_tracker.py history --asin B08XYZ1234 --days 90
    python execution/price_tracker.py alerts [--all]
    python execution/price_tracker.py stats
    python execution/price_tracker.py drops --days 7 --min-drop 10
    python execution/price_tracker.py trending --days 30
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".tmp" / "sourcing" / "price_tracker.db"

# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL,
    name TEXT,
    retailer TEXT,
    category TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    UNIQUE(asin)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    retail_price REAL,
    sale_price REAL,
    amazon_price REAL,
    buy_cost REAL,
    profit_per_unit REAL,
    roi_percent REAL,
    fba_seller_count INTEGER,
    sales_rank INTEGER,
    verdict TEXT,
    source_url TEXT,
    FOREIGN KEY (asin) REFERENCES products(asin)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0,
    FOREIGN KEY (asin) REFERENCES products(asin)
);

CREATE INDEX IF NOT EXISTS idx_price_history_asin ON price_history(asin);
CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(recorded_at);
CREATE INDEX IF NOT EXISTS idx_alerts_unack ON alerts(acknowledged, created_at);
"""


# ── Database Connection ──────────────────────────────────────────────────────

def get_db():
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


# ── Core Functions ───────────────────────────────────────────────────────────

def store_sourcing_results(results_json_path):
    """Import a completed sourcing results JSON into the database.

    For each product:
    - Upsert into products table
    - Insert new price_history row
    - Generate alerts for price drops, new BUY verdicts, ROI increases,
      and competition changes

    Returns a list of alert dicts generated during this import.
    """
    results_path = Path(results_json_path)
    with open(results_path) as f:
        data = json.load(f)

    products = data.get("products", [])
    if not products:
        return []

    now = datetime.utcnow().isoformat()
    conn = get_db()
    new_alerts = []

    try:
        for p in products:
            amz = p.get("amazon", {}) or {}
            prof = p.get("profitability", {}) or {}
            asin = amz.get("asin")

            if not asin:
                continue

            name = p.get("name", "")
            retailer = p.get("retailer", "")
            category = amz.get("category", "")
            verdict = prof.get("verdict", "")
            retail_price = _to_float(p.get("retail_price") or p.get("price"))
            sale_price = _to_float(p.get("sale_price"))
            amazon_price = _to_float(prof.get("sell_price") or amz.get("price"))
            buy_cost = _to_float(prof.get("buy_cost"))
            profit_per_unit = _to_float(prof.get("profit_per_unit"))
            roi_percent = _to_float(prof.get("roi_percent"))
            fba_seller_count = _to_int(amz.get("fba_seller_count") or amz.get("seller_count"))
            sales_rank = _to_int(amz.get("sales_rank"))
            source_url = p.get("retail_url", "")

            # ── Upsert product ───────────────────────────────────────────
            conn.execute("""
                INSERT INTO products (asin, name, retailer, category, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(asin) DO UPDATE SET
                    name = COALESCE(excluded.name, products.name),
                    retailer = COALESCE(excluded.retailer, products.retailer),
                    category = COALESCE(excluded.category, products.category),
                    last_seen = excluded.last_seen
            """, (asin, name, retailer, category, now, now))

            # ── Get previous record for comparison ───────────────────────
            prev = conn.execute("""
                SELECT verdict, retail_price, roi_percent, fba_seller_count
                FROM price_history
                WHERE asin = ?
                ORDER BY recorded_at DESC
                LIMIT 1
            """, (asin,)).fetchone()

            # ── Insert price history ─────────────────────────────────────
            conn.execute("""
                INSERT INTO price_history
                    (asin, recorded_at, retail_price, sale_price, amazon_price,
                     buy_cost, profit_per_unit, roi_percent, fba_seller_count,
                     sales_rank, verdict, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (asin, now, retail_price, sale_price, amazon_price,
                  buy_cost, profit_per_unit, roi_percent, fba_seller_count,
                  sales_rank, verdict, source_url))

            # ── Generate alerts ──────────────────────────────────────────
            if prev:
                prev_verdict = prev["verdict"]
                prev_retail = prev["retail_price"]
                prev_roi = prev["roi_percent"]
                prev_sellers = prev["fba_seller_count"]

                # New BUY verdict
                if verdict == "BUY" and prev_verdict in ("SKIP", "MAYBE"):
                    alert = _create_alert(
                        conn, asin, "new_buy",
                        f"{name or asin} changed from {prev_verdict} to BUY "
                        f"(ROI: {roi_percent}%, Profit: ${profit_per_unit})",
                        now
                    )
                    new_alerts.append(alert)

                # Price drop
                if prev_retail and retail_price and prev_retail > 0:
                    drop_pct = ((prev_retail - retail_price) / prev_retail) * 100
                    if drop_pct >= 10:
                        alert = _create_alert(
                            conn, asin, "price_drop",
                            f"{name or asin} retail price dropped {drop_pct:.1f}% "
                            f"(${prev_retail:.2f} -> ${retail_price:.2f})",
                            now
                        )
                        new_alerts.append(alert)

                # ROI increase
                if prev_roi is not None and roi_percent is not None:
                    roi_delta = roi_percent - prev_roi
                    if roi_delta >= 20:
                        alert = _create_alert(
                            conn, asin, "roi_increase",
                            f"{name or asin} ROI increased by {roi_delta:.1f} points "
                            f"({prev_roi:.1f}% -> {roi_percent:.1f}%)",
                            now
                        )
                        new_alerts.append(alert)

                # Competition change
                if prev_sellers is not None and fba_seller_count is not None:
                    seller_delta = abs(fba_seller_count - prev_sellers)
                    if seller_delta >= 3:
                        direction = "increased" if fba_seller_count > prev_sellers else "decreased"
                        alert = _create_alert(
                            conn, asin, "competition_change",
                            f"{name or asin} FBA sellers {direction} by {seller_delta} "
                            f"({prev_sellers} -> {fba_seller_count})",
                            now
                        )
                        new_alerts.append(alert)

        conn.commit()
    finally:
        conn.close()

    return new_alerts


def get_price_history(asin, days=90):
    """Get price history for an ASIN over the last N days."""
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT ph.*, p.name
            FROM price_history ph
            JOIN products p ON p.asin = ph.asin
            WHERE ph.asin = ? AND ph.recorded_at >= ?
            ORDER BY ph.recorded_at ASC
        """, (asin, cutoff)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_price_drop_alerts(days=7, min_drop_percent=10):
    """Find ASINs where retail price dropped significantly vs. previous record."""
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        # Get the two most recent price records per ASIN within the window
        rows = conn.execute("""
            WITH ranked AS (
                SELECT asin, retail_price, recorded_at,
                       ROW_NUMBER() OVER (PARTITION BY asin ORDER BY recorded_at DESC) AS rn
                FROM price_history
                WHERE recorded_at >= ?
                  AND retail_price IS NOT NULL
            )
            SELECT
                cur.asin,
                p.name,
                prev.retail_price AS prev_price,
                cur.retail_price AS cur_price,
                ROUND(((prev.retail_price - cur.retail_price) / prev.retail_price) * 100, 1) AS drop_pct,
                cur.recorded_at
            FROM ranked cur
            JOIN ranked prev ON cur.asin = prev.asin AND prev.rn = 2
            JOIN products p ON p.asin = cur.asin
            WHERE cur.rn = 1
              AND prev.retail_price > 0
              AND ((prev.retail_price - cur.retail_price) / prev.retail_price) * 100 >= ?
            ORDER BY drop_pct DESC
        """, (cutoff, min_drop_percent)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_trending_buys(days=30, min_occurrences=3):
    """Find ASINs that have appeared as BUY verdict multiple times."""
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT
                ph.asin,
                p.name,
                COUNT(*) AS buy_count,
                ROUND(AVG(ph.roi_percent), 1) AS avg_roi,
                ROUND(AVG(ph.profit_per_unit), 2) AS avg_profit,
                MAX(ph.recorded_at) AS last_seen
            FROM price_history ph
            JOIN products p ON p.asin = ph.asin
            WHERE ph.verdict = 'BUY'
              AND ph.recorded_at >= ?
            GROUP BY ph.asin
            HAVING COUNT(*) >= ?
            ORDER BY buy_count DESC, avg_roi DESC
        """, (cutoff, min_occurrences)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_alerts(unacknowledged_only=True, limit=50):
    """Get recent alerts."""
    conn = get_db()
    try:
        if unacknowledged_only:
            rows = conn.execute("""
                SELECT a.*, p.name
                FROM alerts a
                JOIN products p ON p.asin = a.asin
                WHERE a.acknowledged = 0
                ORDER BY a.created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT a.*, p.name
                FROM alerts a
                JOIN products p ON p.asin = a.asin
                ORDER BY a.created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def acknowledge_alert(alert_id):
    """Mark an alert as acknowledged."""
    conn = get_db()
    try:
        conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def get_stats():
    """Return summary stats: total ASINs tracked, total records, avg ROI of BUY products, etc."""
    conn = get_db()
    try:
        stats = {}

        row = conn.execute("SELECT COUNT(*) AS cnt FROM products").fetchone()
        stats["total_asins"] = row["cnt"]

        row = conn.execute("SELECT COUNT(*) AS cnt FROM price_history").fetchone()
        stats["total_records"] = row["cnt"]

        row = conn.execute("""
            SELECT
                COUNT(*) AS buy_records,
                ROUND(AVG(roi_percent), 1) AS avg_roi,
                ROUND(AVG(profit_per_unit), 2) AS avg_profit,
                ROUND(MIN(buy_cost), 2) AS min_buy_cost,
                ROUND(MAX(buy_cost), 2) AS max_buy_cost
            FROM price_history
            WHERE verdict = 'BUY'
        """).fetchone()
        stats["buy_records"] = row["buy_records"]
        stats["avg_buy_roi"] = row["avg_roi"]
        stats["avg_buy_profit"] = row["avg_profit"]
        stats["min_buy_cost"] = row["min_buy_cost"]
        stats["max_buy_cost"] = row["max_buy_cost"]

        row = conn.execute("""
            SELECT COUNT(*) AS cnt FROM alerts WHERE acknowledged = 0
        """).fetchone()
        stats["unacknowledged_alerts"] = row["cnt"]

        row = conn.execute("""
            SELECT COUNT(DISTINCT asin) AS cnt
            FROM price_history
            WHERE recorded_at >= ?
        """, ((datetime.utcnow() - timedelta(days=7)).isoformat(),)).fetchone()
        stats["active_asins_7d"] = row["cnt"]

        row = conn.execute("""
            SELECT MIN(recorded_at) AS earliest, MAX(recorded_at) AS latest
            FROM price_history
        """).fetchone()
        stats["earliest_record"] = row["earliest"]
        stats["latest_record"] = row["latest"]

        return stats
    finally:
        conn.close()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_float(val):
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_int(val):
    """Safely convert a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _create_alert(conn, asin, alert_type, message, created_at):
    """Insert an alert row and return it as a dict."""
    cursor = conn.execute("""
        INSERT INTO alerts (asin, alert_type, message, created_at)
        VALUES (?, ?, ?, ?)
    """, (asin, alert_type, message, created_at))
    return {
        "id": cursor.lastrowid,
        "asin": asin,
        "alert_type": alert_type,
        "message": message,
        "created_at": created_at,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def cli_import(args):
    """CLI handler: import sourcing results."""
    results_path = Path(args.results)
    if not results_path.exists():
        print(f"Error: file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    alerts = store_sourcing_results(str(results_path))
    print(json.dumps({
        "imported": True,
        "source": str(results_path),
        "alerts_generated": len(alerts),
        "alerts": alerts,
    }, indent=2))


def cli_history(args):
    """CLI handler: show price history for an ASIN."""
    history = get_price_history(args.asin, days=args.days)
    if not history:
        print(f"No price history found for {args.asin} in the last {args.days} days.",
              file=sys.stderr)
        sys.exit(0)
    print(json.dumps(history, indent=2))


def cli_alerts(args):
    """CLI handler: show alerts."""
    unack_only = not args.all
    alerts = get_all_alerts(unacknowledged_only=unack_only)
    if not alerts:
        print("No alerts found.", file=sys.stderr)
        sys.exit(0)
    print(json.dumps(alerts, indent=2))


def cli_stats(args):
    """CLI handler: show database stats."""
    stats = get_stats()
    print(json.dumps(stats, indent=2))


def cli_drops(args):
    """CLI handler: show price drops."""
    drops = get_price_drop_alerts(days=args.days, min_drop_percent=args.min_drop)
    if not drops:
        print(f"No price drops >= {args.min_drop}% found in the last {args.days} days.",
              file=sys.stderr)
        sys.exit(0)
    print(json.dumps(drops, indent=2))


def cli_trending(args):
    """CLI handler: show trending BUY ASINs."""
    trending = get_trending_buys(days=args.days)
    if not trending:
        print(f"No trending BUY ASINs found in the last {args.days} days.",
              file=sys.stderr)
        sys.exit(0)
    print(json.dumps(trending, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="FBA Price Tracker — SQLite-based sourcing history and alerts"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # import
    p_import = subparsers.add_parser("import", help="Import sourcing results JSON")
    p_import.add_argument("--results", required=True, help="Path to results JSON file")
    p_import.set_defaults(func=cli_import)

    # history
    p_history = subparsers.add_parser("history", help="Show price history for an ASIN")
    p_history.add_argument("--asin", required=True, help="ASIN to look up")
    p_history.add_argument("--days", type=int, default=90, help="Look back N days (default: 90)")
    p_history.set_defaults(func=cli_history)

    # alerts
    p_alerts = subparsers.add_parser("alerts", help="Show price alerts")
    p_alerts.add_argument("--all", action="store_true", help="Include acknowledged alerts")
    p_alerts.set_defaults(func=cli_alerts)

    # stats
    p_stats = subparsers.add_parser("stats", help="Show database summary stats")
    p_stats.set_defaults(func=cli_stats)

    # drops
    p_drops = subparsers.add_parser("drops", help="Show recent price drops")
    p_drops.add_argument("--days", type=int, default=7, help="Look back N days (default: 7)")
    p_drops.add_argument("--min-drop", type=float, default=10,
                         help="Minimum drop percentage (default: 10)")
    p_drops.set_defaults(func=cli_drops)

    # trending
    p_trending = subparsers.add_parser("trending", help="Show trending BUY ASINs")
    p_trending.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")
    p_trending.set_defaults(func=cli_trending)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
