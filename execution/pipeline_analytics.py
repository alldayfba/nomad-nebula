#!/usr/bin/env python3
"""
Script: pipeline_analytics.py
Purpose: Track the full sales funnel for both businesses (agency + coaching).
         Calculates conversion rates at each step and identifies the single
         biggest bottleneck by comparing against benchmarks.
         Feeds the CEO constraint waterfall with real data.
Inputs:  CLI subcommands
Outputs: Funnel reports, bottleneck analysis, JSON export for CEO Command Center

CLI:
    python execution/pipeline_analytics.py import --step leads --count 50 --date 2026-02-21 --business agency
    python execution/pipeline_analytics.py import --step revenue --count 1 --revenue 10000 --date 2026-02-21
    python execution/pipeline_analytics.py report --period weekly [--business agency]
    python execution/pipeline_analytics.py bottleneck [--business agency]
    python execution/pipeline_analytics.py funnel [--period weekly] [--business agency]
    python execution/pipeline_analytics.py export --format json
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".tmp" / "analytics" / "pipeline.db"

# ── Funnel Definition ────────────────────────────────────────────────────────

FUNNEL_STEPS = [
    "leads", "icp_qualified", "emails_sent", "replies",
    "calls_booked", "shows", "closes", "revenue"
]

BENCHMARKS = {
    "agency": {
        "leads->icp_qualified": 0.40,
        "icp_qualified->emails_sent": 0.90,
        "emails_sent->replies": 0.05,
        "replies->calls_booked": 0.30,
        "calls_booked->shows": 0.65,
        "shows->closes": 0.20,
    },
    "coaching": {
        "leads->icp_qualified": 0.35,
        "icp_qualified->emails_sent": 0.90,
        "emails_sent->replies": 0.05,
        "replies->calls_booked": 0.35,
        "calls_booked->shows": 0.65,
        "shows->closes": 0.25,
    },
}

# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS funnel_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step TEXT NOT NULL,
    count INTEGER NOT NULL,
    revenue REAL DEFAULT 0,
    business TEXT DEFAULT 'agency',
    date TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversion_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    period_start TEXT NOT NULL,
    from_step TEXT NOT NULL,
    to_step TEXT NOT NULL,
    from_count INTEGER,
    to_count INTEGER,
    rate REAL,
    business TEXT DEFAULT 'agency',
    calculated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_step ON funnel_events(step);
CREATE INDEX IF NOT EXISTS idx_events_date ON funnel_events(date);
CREATE INDEX IF NOT EXISTS idx_events_biz ON funnel_events(business);
"""


# ── Database Connection ──────────────────────────────────────────────────────

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


# ── Core Functions ───────────────────────────────────────────────────────────

def import_event(step, count, date, business="agency", revenue=0, source="manual", notes=None):
    if step not in FUNNEL_STEPS:
        raise ValueError(f"Invalid step '{step}'. Must be one of: {FUNNEL_STEPS}")

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO funnel_events (step, count, revenue, business, date, source, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (step, count, revenue, business, date, source, notes,
              datetime.utcnow().isoformat()))
        conn.commit()
        return {"step": step, "count": count, "date": date, "business": business}
    finally:
        conn.close()


def get_funnel_data(period="weekly", business=None, start_date=None, end_date=None):
    conn = get_db()
    try:
        if end_date is None:
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
        if start_date is None:
            days = {"daily": 1, "weekly": 7, "monthly": 30, "quarterly": 90}.get(period, 7)
            start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        query = """
            SELECT step, SUM(count) AS total_count, SUM(revenue) AS total_revenue
            FROM funnel_events
            WHERE date >= ? AND date <= ?
        """
        params = [start_date, end_date]

        if business:
            query += " AND business = ?"
            params.append(business)

        query += " GROUP BY step ORDER BY step"
        rows = conn.execute(query, params).fetchall()

        result = {}
        for row in rows:
            result[row["step"]] = {
                "count": row["total_count"],
                "revenue": round(row["total_revenue"], 2),
            }
        return result
    finally:
        conn.close()


def calculate_conversions(period="weekly", business=None):
    data = get_funnel_data(period=period, business=business)
    if not data:
        return []

    conversions = []
    for i in range(len(FUNNEL_STEPS) - 1):
        from_step = FUNNEL_STEPS[i]
        to_step = FUNNEL_STEPS[i + 1]
        if to_step == "revenue":
            continue

        from_count = data.get(from_step, {}).get("count", 0)
        to_count = data.get(to_step, {}).get("count", 0)
        rate = round(to_count / from_count, 4) if from_count > 0 else 0

        conversions.append({
            "from_step": from_step,
            "to_step": to_step,
            "from_count": from_count,
            "to_count": to_count,
            "rate": rate,
            "rate_pct": round(rate * 100, 1),
        })

    # Store in DB
    biz = business or "agency"
    now = datetime.utcnow()
    days = {"daily": 1, "weekly": 7, "monthly": 30}.get(period, 7)
    period_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = get_db()
    try:
        for c in conversions:
            conn.execute("""
                INSERT INTO conversion_rates
                    (period, period_start, from_step, to_step, from_count, to_count, rate, business, calculated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (period, period_start, c["from_step"], c["to_step"],
                  c["from_count"], c["to_count"], c["rate"], biz, now.isoformat()))
        conn.commit()
    finally:
        conn.close()

    return conversions


def find_bottleneck(period="weekly", business=None):
    conversions = calculate_conversions(period=period, business=business)
    if not conversions:
        return {"bottleneck": None, "message": "No funnel data available."}

    biz = business or "agency"
    benchmarks = BENCHMARKS.get(biz, BENCHMARKS["agency"])

    worst_gap = 0
    bottleneck = None

    for c in conversions:
        key = f"{c['from_step']}->{c['to_step']}"
        benchmark = benchmarks.get(key, 0.5)
        gap = benchmark - c["rate"]

        if gap > worst_gap:
            worst_gap = gap
            bottleneck = {
                "step": key,
                "from_step": c["from_step"],
                "to_step": c["to_step"],
                "current_rate": c["rate_pct"],
                "benchmark_rate": round(benchmark * 100, 1),
                "gap": round(gap * 100, 1),
                "from_count": c["from_count"],
                "to_count": c["to_count"],
            }

    if bottleneck is None:
        return {"bottleneck": None, "message": "All funnel steps at or above benchmark."}

    return bottleneck


def generate_report(period="weekly", business=None):
    data = get_funnel_data(period=period, business=business)
    conversions = calculate_conversions(period=period, business=business)
    bottleneck = find_bottleneck(period=period, business=business)

    biz_label = (business or "all").upper()
    lines = [
        f"═══ PIPELINE REPORT ({period.upper()}) — {biz_label} ═══",
        "",
        "FUNNEL:",
    ]

    for step in FUNNEL_STEPS:
        d = data.get(step, {"count": 0, "revenue": 0})
        rev_str = f"  (${d['revenue']:,.2f})" if d["revenue"] > 0 else ""
        lines.append(f"  {step:<18} {d['count']:>6}{rev_str}")

    lines.append("")
    lines.append("CONVERSION RATES:")
    biz = business or "agency"
    benchmarks = BENCHMARKS.get(biz, BENCHMARKS["agency"])

    for c in conversions:
        key = f"{c['from_step']}->{c['to_step']}"
        bench = benchmarks.get(key, 0)
        bench_pct = round(bench * 100, 1)
        status = "OK" if c["rate"] >= bench else "LOW"
        lines.append(f"  {key:<35} {c['rate_pct']:>5}% (bench: {bench_pct}%) [{status}]")

    lines.append("")
    if bottleneck and bottleneck.get("step"):
        lines.append(f"BOTTLENECK: {bottleneck['step']}")
        lines.append(f"  Current: {bottleneck['current_rate']}% | Benchmark: {bottleneck['benchmark_rate']}% | Gap: -{bottleneck['gap']}%")
    else:
        lines.append("BOTTLENECK: None — all steps at or above benchmark")

    return "\n".join(lines)


def export_to_json(period="weekly"):
    result = {}
    for biz in ["agency", "coaching"]:
        data = get_funnel_data(period=period, business=biz)
        conversions = calculate_conversions(period=period, business=biz)
        bottleneck = find_bottleneck(period=period, business=biz)
        result[biz] = {
            "funnel": data,
            "conversions": conversions,
            "bottleneck": bottleneck,
        }
    return result


# ── CLI Handlers ─────────────────────────────────────────────────────────────

def cli_import(args):
    try:
        result = import_event(
            step=args.step,
            count=args.count,
            date=args.date or datetime.utcnow().strftime("%Y-%m-%d"),
            business=args.business,
            revenue=args.revenue,
            source=args.source,
            notes=args.notes,
        )
        print(f"[pipeline_analytics] Imported: {result['step']} = {result['count']} ({result['business']}, {result['date']})")
    except ValueError as e:
        print(f"[pipeline_analytics] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_report(args):
    report = generate_report(period=args.period, business=args.business)
    print(report)


def cli_bottleneck(args):
    result = find_bottleneck(period=args.period, business=args.business)
    print(json.dumps(result, indent=2))


def cli_funnel(args):
    data = get_funnel_data(period=args.period, business=args.business)
    if not data:
        print("[pipeline_analytics] No funnel data found.", file=sys.stderr)
        sys.exit(0)

    print(f"\n  FUNNEL ({args.period.upper()}):")
    prev_count = None
    for step in FUNNEL_STEPS:
        d = data.get(step, {"count": 0})
        count = d["count"]
        conv = ""
        if prev_count and prev_count > 0 and count > 0:
            conv = f"  ({round(count / prev_count * 100, 1)}%)"
        bar = "█" * min(int(count / max(max(dd.get("count", 1) for dd in data.values()), 1) * 40), 40)
        print(f"  {step:<18} {bar} {count:>6}{conv}")
        prev_count = count
    print()


def cli_export(args):
    result = export_to_json(period=args.period)
    if args.format == "json":
        print(json.dumps(result, indent=2))


# ── CLI Parser ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Analytics — track funnel, find bottlenecks, feed CEO constraint waterfall"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # import
    p_imp = subparsers.add_parser("import", help="Import a funnel event")
    p_imp.add_argument("--step", required=True, choices=FUNNEL_STEPS, help="Funnel step")
    p_imp.add_argument("--count", type=int, required=True, help="Count for this step")
    p_imp.add_argument("--date", default=None, help="Date (YYYY-MM-DD, default: today)")
    p_imp.add_argument("--business", default="agency", choices=["agency", "coaching"], help="Business unit")
    p_imp.add_argument("--revenue", type=float, default=0, help="Revenue amount (for 'revenue' step)")
    p_imp.add_argument("--source", default="manual", help="Data source (manual, scraper, sheets, api)")
    p_imp.add_argument("--notes", default=None, help="Optional notes")
    p_imp.set_defaults(func=cli_import)

    # report
    p_rep = subparsers.add_parser("report", help="Generate pipeline report")
    p_rep.add_argument("--period", default="weekly", choices=["daily", "weekly", "monthly", "quarterly"])
    p_rep.add_argument("--business", default=None, choices=["agency", "coaching"])
    p_rep.set_defaults(func=cli_report)

    # bottleneck
    p_bn = subparsers.add_parser("bottleneck", help="Find the single biggest bottleneck")
    p_bn.add_argument("--period", default="weekly", choices=["daily", "weekly", "monthly", "quarterly"])
    p_bn.add_argument("--business", default=None, choices=["agency", "coaching"])
    p_bn.set_defaults(func=cli_bottleneck)

    # funnel
    p_fn = subparsers.add_parser("funnel", help="Visual funnel display")
    p_fn.add_argument("--period", default="weekly", choices=["daily", "weekly", "monthly", "quarterly"])
    p_fn.add_argument("--business", default=None, choices=["agency", "coaching"])
    p_fn.set_defaults(func=cli_funnel)

    # export
    p_ex = subparsers.add_parser("export", help="Export pipeline data as JSON")
    p_ex.add_argument("--format", default="json", choices=["json"])
    p_ex.add_argument("--period", default="weekly", choices=["daily", "weekly", "monthly", "quarterly"])
    p_ex.set_defaults(func=cli_export)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
