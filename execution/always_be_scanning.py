#!/usr/bin/env python3
"""
Script: always_be_scanning.py
Purpose: Always-Be-Scanning (ABS) orchestrator — cycles through multiple scan
         types on a rotating schedule, aggregates results into a daily digest,
         and sends alerts via Telegram.

Inspired by Tactical Arbitrage's "Always Be Scanning" mode and Nepeto's
continuous deal feed.

Scan rotation:
  Every 4h:   OOS opportunity scan
  Every 6h:   Keepa deal hunter
  Every 6h:   Stock monitor
  Every 12h:  Category clearance scan
  Every 24h:  Brand watchlist scan
  Every 24h:  A2A warehouse flip scan

Usage:
  python execution/always_be_scanning.py run          # Run one cycle (all due scans)
  python execution/always_be_scanning.py schedule      # Show scan schedule
  python execution/always_be_scanning.py watch --brand "CeraVe"  # Add brand to watchlist
  python execution/always_be_scanning.py watch --list  # List brand watchlist
  python execution/always_be_scanning.py digest --days 1  # View daily digest
  python execution/always_be_scanning.py reset         # Reset all scan timestamps

Cron (run every 4 hours):
  0 */4 * * * cd /Users/Shared/antigravity/projects/nomad-nebula && .venv/bin/python execution/always_be_scanning.py run 2>> .tmp/sourcing/abs_cron.log
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python3"
ABS_DB = TMP_DIR / "abs_scanner.db"
WATCHLIST_FILE = TMP_DIR / "abs_brand_watchlist.json"

# ── Scan Schedule ────────────────────────────────────────────────────────────

SCAN_SCHEDULE = [
    {
        "name": "oos_scan",
        "label": "Out-of-Stock Opportunities",
        "interval_hours": 4,
        "command": ["execution/source.py", "oos", "--count", "30", "--max-bsr", "100000",
                     "--reverse-source", "--max-retailers", "10"],
    },
    {
        "name": "keepa_deals",
        "label": "Keepa Deal Hunter",
        "interval_hours": 6,
        "command": ["execution/keepa_deal_hunter.py", "scan", "--alert"],
    },
    {
        "name": "stock_monitor",
        "label": "Stock Monitor",
        "interval_hours": 6,
        "command": ["execution/stock_monitor.py", "check", "--alert"],
    },
    {
        "name": "clearance_scan",
        "label": "Category Clearance Scan",
        "interval_hours": 12,
        "command": ["execution/multi_retailer_search.py", "clearance",
                     "--category", "Grocery", "--max-retailers", "10"],
    },
    {
        "name": "brand_watchlist",
        "label": "Brand Watchlist Scan",
        "interval_hours": 24,
        "command": None,  # Dynamic — runs source.py brand for each watchlist brand
    },
    {
        "name": "a2a_warehouse",
        "label": "A2A Warehouse Flips",
        "interval_hours": 24,
        "command": ["execution/source.py", "a2a", "--type", "warehouse", "--count", "30"],
    },
]


# ── Database ─────────────────────────────────────────────────────────────────

def _init_db():
    """Initialize SQLite DB for tracking scan runs and results."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ABS_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT DEFAULT 'running',
            results_count INTEGER DEFAULT 0,
            buy_count INTEGER DEFAULT 0,
            error TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_digest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            scan_name TEXT NOT NULL,
            asin TEXT,
            title TEXT,
            verdict TEXT,
            buy_cost REAL,
            amazon_price REAL,
            roi_percent REAL,
            profit_per_unit REAL,
            source TEXT
        )
    """)
    conn.commit()
    return conn


def _get_last_run(conn, scan_name):
    """Get the timestamp of the last successful run for a scan type."""
    row = conn.execute(
        "SELECT completed_at FROM scan_runs WHERE scan_name=? AND status='completed' "
        "ORDER BY completed_at DESC LIMIT 1",
        (scan_name,)
    ).fetchone()
    if row and row[0]:
        try:
            return datetime.fromisoformat(row[0])
        except (ValueError, TypeError):
            return None
    return None


def _record_run_start(conn, scan_name):
    """Record a scan run starting."""
    now = datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO scan_runs (scan_name, started_at) VALUES (?, ?)",
        (scan_name, now)
    )
    conn.commit()
    return cursor.lastrowid


def _record_run_complete(conn, run_id, results_count=0, buy_count=0, error=None):
    """Record a scan run completing."""
    now = datetime.now().isoformat()
    status = "completed" if error is None else "error"
    conn.execute(
        "UPDATE scan_runs SET completed_at=?, status=?, results_count=?, buy_count=?, error=? "
        "WHERE id=?",
        (now, status, results_count, buy_count, error, run_id)
    )
    conn.commit()


# ── Brand Watchlist ──────────────────────────────────────────────────────────

def load_watchlist():
    """Load brand watchlist."""
    if not WATCHLIST_FILE.exists():
        return []
    with open(WATCHLIST_FILE) as f:
        data = json.load(f)
    return data.get("brands", [])


def save_watchlist(brands):
    """Save brand watchlist."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_FILE, "w") as f:
        json.dump({"brands": brands, "updated": datetime.now().isoformat()}, f, indent=2)


def add_to_watchlist(brand_name, retailers="target,walmart,walgreens,cvs,costco"):
    """Add a brand to the ABS watchlist."""
    brands = load_watchlist()
    # Dedup
    existing = [b["name"].lower() for b in brands]
    if brand_name.lower() in existing:
        print(f"[abs] Brand '{brand_name}' already in watchlist.", file=sys.stderr)
        return
    brands.append({
        "name": brand_name,
        "retailers": retailers,
        "added": datetime.now().isoformat(),
    })
    save_watchlist(brands)
    print(f"[abs] Added '{brand_name}' to watchlist ({len(brands)} total).", file=sys.stderr)


# ── Scan Execution ───────────────────────────────────────────────────────────

def _run_command(command):
    """Run a sourcing command via subprocess and return stdout."""
    full_cmd = [str(VENV_PYTHON)] + command
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min max per scan
            cwd=str(PROJECT_ROOT),
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout after 600s", 1
    except Exception as e:
        return "", str(e), 1


def run_scan(scan_config, conn):
    """Execute a single scan type and record results."""
    name = scan_config["name"]
    label = scan_config["label"]

    run_id = _record_run_start(conn, name)
    print(f"[abs] Running: {label} ({name})...", file=sys.stderr)

    if name == "brand_watchlist":
        # Special case: run source.py brand for each watchlist brand
        brands = load_watchlist()
        if not brands:
            print("[abs] No brands in watchlist. Use: always_be_scanning.py watch --brand 'X'",
                  file=sys.stderr)
            _record_run_complete(conn, run_id, error="Empty watchlist")
            return 0, 0

        total_results = 0
        total_buys = 0
        for brand in brands:
            cmd = ["execution/source.py", "brand", brand["name"],
                   "--retailers", brand.get("retailers", "target,walmart,walgreens"),
                   "--max", "20"]
            stdout, stderr, rc = _run_command(cmd)
            if rc == 0:
                # Count results from stdout (look for "products found" line)
                for line in stderr.split("\n"):
                    if "products found" in line.lower():
                        try:
                            count = int(line.split()[1])
                            total_results += count
                        except (ValueError, IndexError):
                            pass
                    if "BUY" in line:
                        total_buys += 1
            else:
                print(f"[abs] Brand scan '{brand['name']}' failed: {stderr[:200]}",
                      file=sys.stderr)

        _record_run_complete(conn, run_id, total_results, total_buys)
        return total_results, total_buys

    else:
        # Standard scan: run the command
        command = scan_config["command"]
        if not command:
            _record_run_complete(conn, run_id, error="No command configured")
            return 0, 0

        stdout, stderr, rc = _run_command(command)

        if rc != 0:
            error_msg = stderr[:500] if stderr else "Unknown error"
            print(f"[abs] {label} FAILED: {error_msg}", file=sys.stderr)
            _record_run_complete(conn, run_id, error=error_msg)
            return 0, 0

        # Parse results count from stderr
        results_count = 0
        buy_count = 0
        for line in (stderr + stdout).split("\n"):
            if "products found" in line.lower() or "returned" in line.lower():
                try:
                    nums = [int(w) for w in line.split() if w.isdigit()]
                    if nums:
                        results_count = max(nums)
                except (ValueError, IndexError):
                    pass
            if "BUY" in line or "OOS_OPPORTUNITY" in line:
                buy_count += 1

        _record_run_complete(conn, run_id, results_count, buy_count)
        print(f"[abs] {label}: {results_count} results, {buy_count} buys", file=sys.stderr)
        return results_count, buy_count


# ── Main Commands ────────────────────────────────────────────────────────────

def cmd_run():
    """Run all due scans based on schedule."""
    conn = _init_db()
    now = datetime.now()

    total_results = 0
    total_buys = 0
    scans_run = 0

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[abs] Always-Be-Scanning — {now.strftime('%Y-%m-%d %H:%M')}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    for scan in SCAN_SCHEDULE:
        last_run = _get_last_run(conn, scan["name"])
        interval = timedelta(hours=scan["interval_hours"])

        if last_run and (now - last_run) < interval:
            next_due = last_run + interval
            print(f"[abs] SKIP {scan['label']}: next due {next_due.strftime('%H:%M')} "
                  f"(last ran {last_run.strftime('%H:%M')})", file=sys.stderr)
            continue

        results, buys = run_scan(scan, conn)
        total_results += results
        total_buys += buys
        scans_run += 1

    # Send digest if we found anything
    if total_buys > 0:
        _send_digest_alert(total_results, total_buys, scans_run)

    # Auto-ingest new results into review queue for morning QA
    try:
        from sourcing_review_queue import get_db as rq_db, ingest_dir
        rq_conn = rq_db()
        queued = ingest_dir(rq_conn)
        if queued > 0:
            print(f"[abs] Queued {queued} products for morning review.", file=sys.stderr)
        rq_conn.close()
    except Exception as e:
        print(f"[abs] Review queue ingest skipped: {e}", file=sys.stderr)

    print(f"\n[abs] Cycle complete: {scans_run} scans, {total_results} results, "
          f"{total_buys} buys.", file=sys.stderr)
    conn.close()


def cmd_schedule():
    """Show the current scan schedule with last run times."""
    conn = _init_db()
    now = datetime.now()

    print(f"\nABS Scan Schedule — {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}")
    print(f"{'Scan':<30} {'Interval':>10} {'Last Run':>16} {'Next Due':>16} {'Status':>8}")
    print(f"{'-'*70}")

    for scan in SCAN_SCHEDULE:
        last_run = _get_last_run(conn, scan["name"])
        interval = timedelta(hours=scan["interval_hours"])

        if last_run:
            next_due = last_run + interval
            is_due = now >= next_due
            status = "DUE" if is_due else "OK"
            last_str = last_run.strftime("%m/%d %H:%M")
            next_str = next_due.strftime("%m/%d %H:%M")
        else:
            status = "NEVER"
            last_str = "never"
            next_str = "now"

        print(f"  {scan['label']:<28} {scan['interval_hours']:>8}h "
              f"{last_str:>16} {next_str:>16} {status:>8}")

    # Brand watchlist
    brands = load_watchlist()
    print(f"\nBrand Watchlist: {len(brands)} brands")
    for b in brands:
        print(f"  - {b['name']} (retailers: {b.get('retailers', 'default')})")

    conn.close()


def cmd_digest(days=1):
    """Show results digest for the last N days."""
    conn = _init_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    rows = conn.execute(
        "SELECT scan_name, started_at, status, results_count, buy_count, error "
        "FROM scan_runs WHERE started_at >= ? ORDER BY started_at DESC",
        (cutoff,)
    ).fetchall()

    print(f"\nABS Digest — Last {days} day(s)")
    print(f"{'='*70}")

    if not rows:
        print("  No scans in this period.")
        conn.close()
        return

    total_results = 0
    total_buys = 0
    for row in rows:
        scan_name, started, status, results, buys, error = row
        total_results += results or 0
        total_buys += buys or 0
        status_icon = "OK" if status == "completed" else "ERR"
        print(f"  [{status_icon}] {scan_name:<25} {started[:16]} "
              f"results={results or 0} buys={buys or 0}"
              f"{' ERROR: ' + (error or '')[:50] if error else ''}")

    print(f"\n  Total: {len(rows)} scans, {total_results} results, {total_buys} BUY products")
    conn.close()


def cmd_reset():
    """Reset all scan timestamps (force re-run on next cycle)."""
    conn = _init_db()
    conn.execute("DELETE FROM scan_runs")
    conn.commit()
    conn.close()
    print("[abs] All scan timestamps reset. Next cycle will run all scans.", file=sys.stderr)


# ── Alerts ───────────────────────────────────────────────────────────────────

def _send_digest_alert(total_results, total_buys, scans_run):
    """Send a Telegram alert with the scan digest."""
    try:
        from sourcing_alerts import send_telegram_alert
    except ImportError:
        print("[abs] WARNING: sourcing_alerts.py not available for Telegram.", file=sys.stderr)
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    message = (
        f"🔍 ABS Scan Complete — {now}\n\n"
        f"Scans run: {scans_run}\n"
        f"Total results: {total_results}\n"
        f"BUY products: {total_buys}\n\n"
        f"Check results: python execution/always_be_scanning.py digest --days 1"
    )

    success = send_telegram_alert(message)
    if success:
        print("[abs] Telegram digest alert sent.", file=sys.stderr)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Always-Be-Scanning (ABS) orchestrator"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Run all due scans")
    sub.add_parser("schedule", help="Show scan schedule")
    sub.add_parser("reset", help="Reset all scan timestamps")

    p_digest = sub.add_parser("digest", help="View results digest")
    p_digest.add_argument("--days", type=int, default=1, help="Days to look back (default: 1)")

    p_watch = sub.add_parser("watch", help="Manage brand watchlist")
    p_watch.add_argument("--brand", type=str, help="Brand name to add")
    p_watch.add_argument("--retailers", type=str, default="target,walmart,walgreens,cvs,costco",
                         help="Retailers for this brand")
    p_watch.add_argument("--list", action="store_true", help="List watchlist")
    p_watch.add_argument("--remove", type=str, help="Remove brand by name")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run()
    elif args.command == "schedule":
        cmd_schedule()
    elif args.command == "digest":
        cmd_digest(args.days)
    elif args.command == "reset":
        cmd_reset()
    elif args.command == "watch":
        if args.list:
            brands = load_watchlist()
            print(f"\nBrand Watchlist ({len(brands)} brands):")
            for b in brands:
                print(f"  - {b['name']} | retailers: {b.get('retailers', 'default')} "
                      f"| added: {b.get('added', '?')[:10]}")
        elif args.remove:
            brands = load_watchlist()
            brands = [b for b in brands if b["name"].lower() != args.remove.lower()]
            save_watchlist(brands)
            print(f"[abs] Removed '{args.remove}' from watchlist.", file=sys.stderr)
        elif args.brand:
            add_to_watchlist(args.brand, args.retailers)
        else:
            print("Use --brand, --list, or --remove", file=sys.stderr)


if __name__ == "__main__":
    main()
