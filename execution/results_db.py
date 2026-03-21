#!/usr/bin/env python3
"""
Script: results_db.py
Purpose: SQLite database for persisting sourcing scan results. Enables:
         - Querying historical deals ("show me BUY deals from last 7 days")
         - Deduplication across runs (same ASIN found again = skip or update)
         - Performance tracking (how many BUYs per mode, avg ROI trends)

Usage:
  from results_db import ResultsDB

  db = ResultsDB()
  db.save_results("scan_123", "brand", results_list)
  recent = db.query_results(days=7, verdict="BUY", min_roi=30)
  is_dup = db.is_recent_duplicate("B08XYZ1234", days=3)

CLI:
  python execution/results_db.py query --days 7 --verdict BUY
  python execution/results_db.py stats
  python execution/results_db.py export --days 30 --output results.json
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / ".tmp" / "sourcing" / "results.db"


class ResultsDB:
    """SQLite wrapper for sourcing results persistence."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(str(self.db_path)) as conn:
            # Fix 3.3 — WAL mode for concurrent write safety
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.commit()

            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    asin TEXT,
                    title TEXT,
                    retailer TEXT,
                    buy_cost REAL,
                    sell_price REAL,
                    profit REAL,
                    roi REAL,
                    verdict TEXT,
                    match_confidence REAL,
                    bsr INTEGER,
                    source_url TEXT,
                    amazon_url TEXT,
                    raw_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_asin
                ON scan_results(asin)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_verdict
                ON scan_results(verdict, created_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_scan
                ON scan_results(scan_id)
            """)

            # Fix 3.4 — price_watches table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_watches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    asin TEXT NOT NULL,
                    max_cost REAL NOT NULL,
                    notify_channel TEXT DEFAULT 'discord',
                    discord_webhook TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    last_checked TEXT,
                    last_notified TEXT,
                    active INTEGER DEFAULT 1
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_price_watches_asin ON price_watches(asin)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_price_watches_active ON price_watches(active)")

            # Fix 3.5 — retailer_price_history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS retailer_price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    retailer TEXT NOT NULL,
                    url TEXT NOT NULL,
                    product_name TEXT,
                    asin TEXT,
                    price REAL NOT NULL,
                    original_price REAL,
                    discount_pct REAL,
                    scraped_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_retailer_url ON retailer_price_history(retailer, url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_asin ON retailer_price_history(asin)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_scraped ON retailer_price_history(scraped_at)")

            # ── Storefront Stalker tables ────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tracked_storefronts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id TEXT UNIQUE NOT NULL,
                    seller_name TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    status TEXT DEFAULT 'active',
                    known_asins_json TEXT DEFAULT '[]',
                    alert_count INTEGER DEFAULT 0,
                    accuracy_hits INTEGER DEFAULT 0,
                    accuracy_total INTEGER DEFAULT 0,
                    accuracy_score REAL DEFAULT 0.0,
                    last_active_at TEXT,
                    last_checked_at TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    added_by TEXT DEFAULT 'manual'
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS storefront_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id TEXT NOT NULL,
                    asin TEXT NOT NULL,
                    product_name TEXT,
                    amazon_price REAL,
                    grade TEXT DEFAULT '?',
                    profit REAL,
                    roi REAL,
                    retailer TEXT,
                    buy_link TEXT,
                    bsr INTEGER,
                    bsr_drops_30d INTEGER,
                    fba_sellers INTEGER,
                    amazon_on_listing INTEGER DEFAULT 0,
                    skip_reason TEXT,
                    discord_message_id TEXT,
                    stage TEXT DEFAULT 'stage1',
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (seller_id) REFERENCES tracked_storefronts(seller_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sf_alerts_seller ON storefront_alerts(seller_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sf_alerts_asin ON storefront_alerts(asin, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sf_alerts_grade ON storefront_alerts(grade)")

    def save_results(self, scan_id, mode, results):
        """Save a list of sourcing results to the database.

        Args:
            scan_id: Unique scan identifier (e.g., timestamp or UUID).
            mode: Scan mode (brand, category, oos, a2a, finder, etc.).
            results: List of result dicts (Schema B from source.py).

        Returns:
            Number of results saved.
        """
        if not results:
            return 0

        rows = []
        for r in results:
            prof = r.get("profitability", {})
            rows.append((
                scan_id,
                mode,
                r.get("asin", ""),
                r.get("amazon_title") or r.get("name", ""),
                r.get("source_retailer") or r.get("retailer", ""),
                r.get("buy_cost") or prof.get("buy_cost"),
                r.get("amazon_price") or prof.get("sell_price"),
                r.get("estimated_profit") or prof.get("profit_per_unit"),
                r.get("estimated_roi") or prof.get("roi_percent"),
                r.get("verdict") or prof.get("verdict", ""),
                r.get("match_confidence", 0),
                r.get("bsr"),
                r.get("source_url") or r.get("buy_url", ""),
                r.get("amazon_url", ""),
                json.dumps(r, default=str),
            ))

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executemany("""
                INSERT INTO scan_results
                (scan_id, mode, asin, title, retailer, buy_cost, sell_price,
                 profit, roi, verdict, match_confidence, bsr, source_url,
                 amazon_url, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)

        return len(rows)

    def query_results(self, days=7, verdict=None, min_roi=None, mode=None,
                      limit=100):
        """Query historical results with filters.

        Returns:
            List of dicts with result data.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        query = "SELECT * FROM scan_results WHERE created_at >= ?"
        params = [cutoff]

        if verdict:
            query += " AND verdict = ?"
            params.append(verdict)
        if min_roi is not None:
            query += " AND roi >= ?"
            params.append(min_roi)
        if mode:
            query += " AND mode = ?"
            params.append(mode)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def is_recent_duplicate(self, asin, days=3):
        """Check if an ASIN was found recently (dedup)."""
        if not asin:
            return False
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM scan_results WHERE asin = ? AND created_at >= ?",
                (asin, cutoff),
            ).fetchone()
        return row[0] > 0

    def stats(self):
        """Return summary statistics."""
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]
            buys = conn.execute(
                "SELECT COUNT(*) FROM scan_results WHERE verdict = 'BUY'"
            ).fetchone()[0]
            modes = conn.execute(
                "SELECT mode, COUNT(*) as cnt FROM scan_results GROUP BY mode ORDER BY cnt DESC"
            ).fetchall()
            avg_roi = conn.execute(
                "SELECT AVG(roi) FROM scan_results WHERE verdict = 'BUY' AND roi IS NOT NULL"
            ).fetchone()[0]
            recent_7d = conn.execute(
                "SELECT COUNT(*) FROM scan_results WHERE created_at >= ?",
                ((datetime.now() - timedelta(days=7)).isoformat(),),
            ).fetchone()[0]

        return {
            "total_results": total,
            "buy_count": buys,
            "modes": {m: c for m, c in modes},
            "avg_buy_roi": round(avg_roi, 1) if avg_roi else 0,
            "results_last_7d": recent_7d,
        }


    # Fix 3.6 — Helper methods for new tables

    def add_price_watch(self, student_id: str, asin: str, max_cost: float, discord_webhook=None):
        """Add an ASIN to a student's price watch list. Returns the watch ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "INSERT OR REPLACE INTO price_watches (student_id, asin, max_cost, discord_webhook) VALUES (?,?,?,?)",
                (student_id, asin, max_cost, discord_webhook)
            )
            return cursor.lastrowid

    def get_active_watches(self) -> list:
        """Get all active price watches for the alert scanner."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT id, student_id, asin, max_cost, discord_webhook FROM price_watches WHERE active=1"
            ).fetchall()
            return [{"id": r[0], "student_id": r[1], "asin": r[2], "max_cost": r[3], "discord_webhook": r[4]} for r in rows]

    def record_price(self, retailer: str, url: str, product_name: str, price: float,
                      original_price=None, asin=None) -> None:
        """Record a scraped price to history for clearance tracking."""
        discount_pct = None
        if original_price and original_price > 0:
            discount_pct = round((original_price - price) / original_price * 100, 1)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO retailer_price_history (retailer, url, product_name, asin, price, original_price, discount_pct) VALUES (?,?,?,?,?,?,?)",
                (retailer, url, product_name, asin, price, original_price, discount_pct)
            )

    # ── Storefront Stalker methods ─────────────────────────────────────────

    def add_tracked_storefront(self, seller_id: str, seller_name: str, notes: str = "") -> int:
        """Add a seller storefront to the watch list. Returns row id."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO tracked_storefronts (seller_id, seller_name, notes) VALUES (?,?,?)",
                (seller_id, seller_name, notes),
            )
            return cursor.lastrowid

    def remove_tracked_storefront(self, seller_id: str) -> None:
        """Remove a seller from the watch list."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM tracked_storefronts WHERE seller_id = ?", (seller_id,))

    def get_tracked_storefronts(self) -> list:
        """Return all tracked storefronts (excluding removed)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tracked_storefronts WHERE status != 'removed' ORDER BY seller_name"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_storefront_known_asins(self, seller_id: str, asins_list: list) -> None:
        """Update the known ASINs JSON for a storefront."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE tracked_storefronts SET known_asins_json = ?, last_checked_at = datetime('now') WHERE seller_id = ?",
                (json.dumps(asins_list), seller_id),
            )

    def update_storefront_status(self, seller_id: str, status: str) -> None:
        """Update storefront status (active / quiet / retired)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE tracked_storefronts SET status = ? WHERE seller_id = ?",
                (status, seller_id),
            )

    def update_storefront_last_active(self, seller_id: str, had_new_product: bool = False) -> None:
        """Update last_checked_at, and last_active_at if new product found."""
        with sqlite3.connect(str(self.db_path)) as conn:
            if had_new_product:
                conn.execute(
                    "UPDATE tracked_storefronts SET last_active_at = datetime('now'), last_checked_at = datetime('now') WHERE seller_id = ?",
                    (seller_id,),
                )
            else:
                conn.execute(
                    "UPDATE tracked_storefronts SET last_checked_at = datetime('now') WHERE seller_id = ?",
                    (seller_id,),
                )

    def update_storefront_accuracy(self, seller_id: str, was_profitable: bool) -> None:
        """Increment accuracy counters and recalculate accuracy score."""
        with sqlite3.connect(str(self.db_path)) as conn:
            if was_profitable:
                conn.execute(
                    "UPDATE tracked_storefronts SET accuracy_hits = accuracy_hits + 1, accuracy_total = accuracy_total + 1, "
                    "accuracy_score = CAST(accuracy_hits + 1 AS REAL) / CAST(accuracy_total + 1 AS REAL) WHERE seller_id = ?",
                    (seller_id,),
                )
            else:
                conn.execute(
                    "UPDATE tracked_storefronts SET accuracy_total = accuracy_total + 1, "
                    "accuracy_score = CAST(accuracy_hits AS REAL) / CAST(accuracy_total + 1 AS REAL) WHERE seller_id = ?",
                    (seller_id,),
                )

    def insert_storefront_alert(self, seller_id: str, asin: str, product_name: str = "",
                                 amazon_price: float = None, discord_message_id: str = None,
                                 stage: str = "stage1") -> int:
        """Insert a new storefront alert. Returns the alert id."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "INSERT INTO storefront_alerts (seller_id, asin, product_name, amazon_price, discord_message_id, stage) "
                "VALUES (?,?,?,?,?,?)",
                (seller_id, asin, product_name, amazon_price, discord_message_id, stage),
            )
            # Increment alert count on the storefront
            conn.execute(
                "UPDATE tracked_storefronts SET alert_count = alert_count + 1 WHERE seller_id = ?",
                (seller_id,),
            )
            return cursor.lastrowid

    def update_storefront_alert(self, alert_id: int, grade: str = None, profit: float = None,
                                 roi: float = None, retailer: str = None, buy_link: str = None,
                                 bsr: int = None, bsr_drops_30d: int = None,
                                 fba_sellers: int = None, amazon_on_listing: bool = False,
                                 skip_reason: str = None, stage: str = "complete") -> None:
        """Update a storefront alert with Stage 2 analysis results."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE storefront_alerts SET grade=?, profit=?, roi=?, retailer=?, buy_link=?, "
                "bsr=?, bsr_drops_30d=?, fba_sellers=?, amazon_on_listing=?, skip_reason=?, stage=? "
                "WHERE id=?",
                (grade, profit, roi, retailer, buy_link, bsr, bsr_drops_30d, fba_sellers,
                 1 if amazon_on_listing else 0, skip_reason, stage, alert_id),
            )

    def count_recent_asin_alerts(self, asin: str, hours: int = 24) -> int:
        """Count how many storefront alerts exist for this ASIN in the last N hours (convergence detection)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM storefront_alerts WHERE asin = ? AND created_at >= datetime('now', ?)",
                (asin, f"-{hours} hours"),
            ).fetchone()
        return row[0] if row else 0

    def get_storefront_alerts(self, limit: int = 50, grade: str = None,
                               seller_id: str = None, since_id: int = None) -> list:
        """Query storefront alerts with optional filters."""
        query = "SELECT sa.*, ts.seller_name FROM storefront_alerts sa LEFT JOIN tracked_storefronts ts ON sa.seller_id = ts.seller_id WHERE 1=1"
        params = []
        if grade:
            query += " AND sa.grade = ?"
            params.append(grade)
        if seller_id:
            query += " AND sa.seller_id = ?"
            params.append(seller_id)
        if since_id:
            query += " AND sa.id > ?"
            params.append(since_id)
        query += " ORDER BY sa.created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_stalker_stats(self) -> dict:
        """Return dashboard stats for the storefront stalker."""
        with sqlite3.connect(str(self.db_path)) as conn:
            total_sellers = conn.execute(
                "SELECT COUNT(*) FROM tracked_storefronts WHERE status != 'removed'"
            ).fetchone()[0]
            total_alerts = conn.execute(
                "SELECT COUNT(*) FROM storefront_alerts"
            ).fetchone()[0]
            alerts_today = conn.execute(
                "SELECT COUNT(*) FROM storefront_alerts WHERE created_at >= date('now')"
            ).fetchone()[0]
            grade_a_today = conn.execute(
                "SELECT COUNT(*) FROM storefront_alerts WHERE grade = 'A' AND created_at >= date('now')"
            ).fetchone()[0]
            avg_acc = conn.execute(
                "SELECT AVG(accuracy_score) FROM tracked_storefronts WHERE accuracy_total > 0"
            ).fetchone()[0]
            convergence_events = conn.execute(
                "SELECT COUNT(DISTINCT asin) FROM storefront_alerts "
                "WHERE created_at >= datetime('now', '-24 hours') "
                "GROUP BY asin HAVING COUNT(*) >= 3"
            ).fetchall()
        return {
            "total_sellers": total_sellers,
            "total_alerts": total_alerts,
            "alerts_today": alerts_today,
            "grade_a_today": grade_a_today,
            "avg_accuracy": round(avg_acc * 100, 1) if avg_acc else 0,
            "convergence_events_24h": len(convergence_events),
        }

    def record_rejection(self, asin: str, retail_title: str, amazon_title: str,
                          retailer: str, issues: list, fix_suggestion: str,
                          match_method: str = "", match_confidence: float = 0) -> None:
        """Record a product review rejection for feedback analysis."""
        try:
            from feedback_engine import record_rejection as _rec
            _rec(asin, retail_title, amazon_title, retailer, issues, fix_suggestion, match_method, match_confidence)
        except Exception:
            pass

    def record_student_outcome(self, asin: str, retailer: str, predicted_roi: float,
                                 actual_roi: float, feedback_type: str, notes: str = "") -> None:
        """Record a student's real-world outcome for prediction accuracy tracking."""
        try:
            from feedback_engine import record_student_outcome as _rec
            _rec(asin, retailer, predicted_roi, actual_roi, feedback_type, notes)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Sourcing results database")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_query = sub.add_parser("query", help="Query historical results")
    p_query.add_argument("--days", type=int, default=7)
    p_query.add_argument("--verdict", default=None)
    p_query.add_argument("--min-roi", type=float, default=None)
    p_query.add_argument("--mode", default=None)
    p_query.add_argument("--limit", type=int, default=50)

    sub.add_parser("stats", help="Show database statistics")

    p_export = sub.add_parser("export", help="Export results to JSON")
    p_export.add_argument("--days", type=int, default=30)
    p_export.add_argument("--output", "-o", default=None)

    args = parser.parse_args()
    db = ResultsDB()

    if args.cmd == "query":
        results = db.query_results(
            days=args.days, verdict=args.verdict,
            min_roi=args.min_roi, mode=args.mode, limit=args.limit,
        )
        for r in results:
            print(f"  {r['verdict']:>5} | {r['asin']:<12} | ${r['profit'] or 0:>6.2f} | "
                  f"{r['roi'] or 0:>5.0f}% | {r['title'][:40]} | {r['mode']} | {r['created_at'][:16]}")
        print(f"\n  {len(results)} results found.")

    elif args.cmd == "stats":
        s = db.stats()
        print(f"\n  Sourcing Results Database")
        print(f"  {'=' * 40}")
        print(f"  Total results: {s['total_results']}")
        print(f"  BUY verdicts:  {s['buy_count']}")
        print(f"  Avg BUY ROI:   {s['avg_buy_roi']}%")
        print(f"  Last 7 days:   {s['results_last_7d']}")
        print(f"  By mode:")
        for mode, count in s["modes"].items():
            print(f"    {mode}: {count}")

    elif args.cmd == "export":
        results = db.query_results(days=args.days, limit=10000)
        output = args.output or str(
            PROJECT_ROOT / ".tmp" / "sourcing" / f"export_{datetime.now().strftime('%Y%m%d')}.json"
        )
        with open(output, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"  Exported {len(results)} results to {output}")


if __name__ == "__main__":
    main()
