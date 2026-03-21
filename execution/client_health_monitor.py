#!/usr/bin/env python3
"""
Script: client_health_monitor.py
Purpose: Track agency client engagement signals and health scores.
         Scores each client 0-100 across 5 dimensions.
         Flags at-risk clients for CEO dispatch → outreach agent retention.
Inputs:  CLI subcommands
Outputs: Health reports, at-risk alerts, JSON export for CEO Command Center

CLI:
    python execution/client_health_monitor.py add-client --name "ClientX" --mrr 10000 [--start-date 2026-01-15]
    python execution/client_health_monitor.py log-signal --client "ClientX" --type call_attended
    python execution/client_health_monitor.py log-signal --client "ClientX" --type payment_late
    python execution/client_health_monitor.py health-report
    python execution/client_health_monitor.py at-risk
    python execution/client_health_monitor.py client-detail --name "ClientX"
    python execution/client_health_monitor.py refresh
    python execution/client_health_monitor.py export --format json
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".tmp" / "agency" / "client_health.db"

# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    mrr REAL NOT NULL,
    start_date TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    health_score INTEGER DEFAULT 100,
    last_contact TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    signal_type TEXT NOT NULL,
    value TEXT DEFAULT 'true',
    date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS health_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    breakdown TEXT,
    date TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE INDEX IF NOT EXISTS idx_signals_client ON signals(client_id);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(date);
CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_snapshots_client ON health_snapshots(client_id);
"""

VALID_SIGNAL_TYPES = [
    "email_open", "email_no_open",
    "call_attended", "call_missed",
    "response_fast", "response_slow", "response_none",
    "payment_on_time", "payment_late",
    "feedback_positive", "feedback_negative",
    "deliverable_sent", "deliverable_approved", "deliverable_revision",
    "meeting_scheduled", "meeting_cancelled",
]

WEIGHTS = {
    "engagement": 25,
    "responsiveness": 20,
    "payment": 25,
    "satisfaction": 20,
    "tenure": 10,
}


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

def add_client(name, mrr, start_date=None, notes=None):
    if start_date is None:
        start_date = datetime.utcnow().strftime("%Y-%m-%d")
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO clients (name, mrr, start_date, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, mrr, start_date, notes, datetime.utcnow().isoformat()))
        conn.commit()
        row = conn.execute("SELECT * FROM clients WHERE name = ?", (name,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def log_signal(client_name, signal_type, value="true", date=None, notes=None):
    if signal_type not in VALID_SIGNAL_TYPES:
        raise ValueError(f"Invalid signal type '{signal_type}'. Valid: {VALID_SIGNAL_TYPES}")

    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")

    conn = get_db()
    try:
        client = conn.execute("SELECT id FROM clients WHERE name = ?", (client_name,)).fetchone()
        if not client:
            raise ValueError(f"Client '{client_name}' not found.")

        conn.execute("""
            INSERT INTO signals (client_id, signal_type, value, date, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (client["id"], signal_type, value, date, notes, datetime.utcnow().isoformat()))

        # Update last_contact for engagement signals
        contact_types = {"call_attended", "email_open", "response_fast", "meeting_scheduled",
                         "feedback_positive", "feedback_negative", "deliverable_approved"}
        if signal_type in contact_types:
            conn.execute("UPDATE clients SET last_contact = ? WHERE id = ?", (date, client["id"]))

        conn.commit()
        return {"client": client_name, "signal": signal_type, "date": date}
    finally:
        conn.close()


def calculate_health_score(client_id):
    conn = get_db()
    try:
        client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if not client:
            return None

        cutoff_14d = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
        cutoff_30d = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")

        signals = conn.execute("""
            SELECT signal_type, COUNT(*) as cnt
            FROM signals WHERE client_id = ? AND date >= ?
            GROUP BY signal_type
        """, (client_id, cutoff_30d)).fetchall()
        sig = {row["signal_type"]: row["cnt"] for row in signals}

        # 1. Engagement (25): call attendance + email engagement in last 14 days
        recent_signals = conn.execute("""
            SELECT signal_type, COUNT(*) as cnt
            FROM signals WHERE client_id = ? AND date >= ?
            GROUP BY signal_type
        """, (client_id, cutoff_14d)).fetchall()
        recent = {row["signal_type"]: row["cnt"] for row in recent_signals}

        calls_attended = recent.get("call_attended", 0)
        calls_missed = recent.get("call_missed", 0)
        total_calls = calls_attended + calls_missed
        call_rate = (calls_attended / total_calls) if total_calls > 0 else 0.5

        emails_opened = recent.get("email_open", 0)
        emails_missed = recent.get("email_no_open", 0)
        total_emails = emails_opened + emails_missed
        email_rate = (emails_opened / total_emails) if total_emails > 0 else 0.5

        engagement_score = round((call_rate * 0.6 + email_rate * 0.4) * WEIGHTS["engagement"])

        # 2. Responsiveness (20): fast vs slow/none responses
        fast = sig.get("response_fast", 0)
        slow = sig.get("response_slow", 0)
        none_resp = sig.get("response_none", 0)
        total_resp = fast + slow + none_resp
        if total_resp > 0:
            resp_score = round(((fast * 1.0 + slow * 0.4 + none_resp * 0.0) / total_resp) * WEIGHTS["responsiveness"])
        else:
            resp_score = round(0.5 * WEIGHTS["responsiveness"])

        # 3. Payment (25): on-time vs late
        on_time = sig.get("payment_on_time", 0)
        late = sig.get("payment_late", 0)
        total_pay = on_time + late
        if total_pay > 0:
            pay_score = round((on_time / total_pay) * WEIGHTS["payment"])
        else:
            pay_score = WEIGHTS["payment"]  # No data = assume good

        # Immediate penalty for late payment
        if late > 0:
            pay_score = max(0, pay_score - 10)

        # 4. Satisfaction (20): positive vs negative feedback
        pos = sig.get("feedback_positive", 0)
        neg = sig.get("feedback_negative", 0)
        total_fb = pos + neg
        if total_fb > 0:
            sat_score = round((pos / total_fb) * WEIGHTS["satisfaction"])
        else:
            sat_score = round(0.6 * WEIGHTS["satisfaction"])  # No feedback = slightly below neutral

        # 5. Tenure (10): months as client
        try:
            start = datetime.strptime(client["start_date"], "%Y-%m-%d")
            months = max(1, (datetime.utcnow() - start).days // 30)
            tenure_score = min(round(months / 12 * WEIGHTS["tenure"]), WEIGHTS["tenure"])
        except (ValueError, TypeError):
            tenure_score = round(0.5 * WEIGHTS["tenure"])

        total = engagement_score + resp_score + pay_score + sat_score + tenure_score

        # No-contact penalty: if last_contact > 14 days ago
        if client["last_contact"]:
            try:
                last = datetime.strptime(client["last_contact"], "%Y-%m-%d")
                days_since = (datetime.utcnow() - last).days
                if days_since > 14:
                    total = max(0, total - 15)
            except (ValueError, TypeError):
                pass

        # Consecutive missed calls penalty
        recent_call_signals = conn.execute("""
            SELECT signal_type FROM signals
            WHERE client_id = ? AND signal_type IN ('call_attended', 'call_missed')
            ORDER BY date DESC, id DESC LIMIT 3
        """, (client_id,)).fetchall()
        consecutive_missed = 0
        for s in recent_call_signals:
            if s["signal_type"] == "call_missed":
                consecutive_missed += 1
            else:
                break
        if consecutive_missed >= 2:
            total = max(0, total - 10)

        total = max(0, min(100, total))

        breakdown = {
            "engagement": engagement_score,
            "responsiveness": resp_score,
            "payment": pay_score,
            "satisfaction": sat_score,
            "tenure": tenure_score,
        }

        # Save snapshot
        today = datetime.utcnow().strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO health_snapshots (client_id, score, breakdown, date)
            VALUES (?, ?, ?, ?)
        """, (client_id, total, json.dumps(breakdown), today))

        # Update client record
        status = "active"
        if total < 30:
            status = "critical"
        elif total < 60:
            status = "at_risk"

        conn.execute("""
            UPDATE clients SET health_score = ?, status = ? WHERE id = ?
        """, (total, status, client_id))
        conn.commit()

        return {"score": total, "breakdown": breakdown, "status": status}
    finally:
        conn.close()


def refresh_all_scores():
    conn = get_db()
    try:
        clients = conn.execute("SELECT id, name FROM clients WHERE status != 'churned'").fetchall()
    finally:
        conn.close()

    results = []
    for c in clients:
        score_data = calculate_health_score(c["id"])
        if score_data:
            results.append({"name": c["name"], **score_data})
    return results


def get_at_risk():
    refresh_all_scores()
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM clients
            WHERE status IN ('at_risk', 'critical')
            ORDER BY health_score ASC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_client_detail(name):
    conn = get_db()
    try:
        client = conn.execute("SELECT * FROM clients WHERE name = ?", (name,)).fetchone()
        if not client:
            return None

        signals = conn.execute("""
            SELECT signal_type, date, notes FROM signals
            WHERE client_id = ? ORDER BY date DESC LIMIT 20
        """, (client["id"],)).fetchall()

        snapshots = conn.execute("""
            SELECT score, breakdown, date FROM health_snapshots
            WHERE client_id = ? ORDER BY date DESC LIMIT 10
        """, (client["id"],)).fetchall()

        return {
            "client": dict(client),
            "recent_signals": [dict(s) for s in signals],
            "score_history": [dict(s) for s in snapshots],
        }
    finally:
        conn.close()


def health_report():
    results = refresh_all_scores()
    if not results:
        return "No clients found."

    lines = [
        "═══ CLIENT HEALTH REPORT ═══",
        "",
        f"{'Client':<25} {'Score':>6} {'Status':<10} {'E':>3} {'R':>3} {'P':>3} {'S':>3} {'T':>3}",
        "─" * 65,
    ]

    for r in sorted(results, key=lambda x: x["score"]):
        b = r["breakdown"]
        status_icon = {"active": "OK", "at_risk": "WARN", "critical": "CRIT"}.get(r["status"], "?")
        lines.append(
            f"{r['name']:<25} {r['score']:>5}  {status_icon:<10} "
            f"{b['engagement']:>3} {b['responsiveness']:>3} {b['payment']:>3} "
            f"{b['satisfaction']:>3} {b['tenure']:>3}"
        )

    at_risk = [r for r in results if r["status"] in ("at_risk", "critical")]
    lines.append("")
    lines.append(f"At-risk clients: {len(at_risk)}/{len(results)}")
    for r in at_risk:
        level = "CRITICAL" if r["status"] == "critical" else "AT RISK"
        lines.append(f"  [{level}] {r['name']} — score {r['score']}")

    return "\n".join(lines)


def export_json():
    results = refresh_all_scores()
    conn = get_db()
    try:
        clients = conn.execute("SELECT * FROM clients ORDER BY health_score ASC").fetchall()
        return {
            "clients": [dict(c) for c in clients],
            "at_risk_count": len([r for r in results if r.get("status") in ("at_risk", "critical")]),
            "total_mrr": sum(c["mrr"] for c in clients if c["status"] != "churned"),
            "at_risk_mrr": sum(c["mrr"] for c in clients if c["status"] in ("at_risk", "critical")),
            "generated_at": datetime.utcnow().isoformat(),
        }
    finally:
        conn.close()


# ── CLI Handlers ─────────────────────────────────────────────────────────────

def cli_add_client(args):
    try:
        result = add_client(args.name, args.mrr, args.start_date, args.notes)
        print(f"[client_health] Added client: {result['name']} (MRR: ${result['mrr']:,.0f})")
    except sqlite3.IntegrityError:
        print(f"[client_health] Error: client '{args.name}' already exists.", file=sys.stderr)
        sys.exit(1)


def cli_log_signal(args):
    try:
        result = log_signal(args.client, args.type, args.value, args.date, args.notes)
        print(f"[client_health] Logged: {result['client']} — {result['signal']} on {result['date']}")
    except ValueError as e:
        print(f"[client_health] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_health_report(args):
    print(health_report())


def cli_at_risk(args):
    at_risk = get_at_risk()
    if not at_risk:
        print("[client_health] No at-risk clients.")
        return
    print(json.dumps(at_risk, indent=2))


def cli_client_detail(args):
    detail = get_client_detail(args.name)
    if not detail:
        print(f"[client_health] Client '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(detail, indent=2, default=str))


def cli_refresh(args):
    results = refresh_all_scores()
    print(f"[client_health] Refreshed {len(results)} client scores.")
    for r in results:
        print(f"  {r['name']}: {r['score']} ({r['status']})")


def cli_export(args):
    result = export_json()
    print(json.dumps(result, indent=2))


# ── CLI Parser ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Client Health Monitor — track engagement, score clients, flag churn risk"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # add-client
    p_add = subparsers.add_parser("add-client", help="Add a new client")
    p_add.add_argument("--name", required=True, help="Client name")
    p_add.add_argument("--mrr", type=float, required=True, help="Monthly recurring revenue ($)")
    p_add.add_argument("--start-date", default=None, help="Start date (YYYY-MM-DD)")
    p_add.add_argument("--notes", default=None, help="Optional notes")
    p_add.set_defaults(func=cli_add_client)

    # log-signal
    p_sig = subparsers.add_parser("log-signal", help="Log an engagement signal")
    p_sig.add_argument("--client", required=True, help="Client name")
    p_sig.add_argument("--type", required=True, choices=VALID_SIGNAL_TYPES, help="Signal type")
    p_sig.add_argument("--value", default="true", help="Signal value")
    p_sig.add_argument("--date", default=None, help="Date (YYYY-MM-DD)")
    p_sig.add_argument("--notes", default=None, help="Optional notes")
    p_sig.set_defaults(func=cli_log_signal)

    # health-report
    p_hr = subparsers.add_parser("health-report", help="Client health report")
    p_hr.set_defaults(func=cli_health_report)

    # at-risk
    p_ar = subparsers.add_parser("at-risk", help="List at-risk clients")
    p_ar.set_defaults(func=cli_at_risk)

    # client-detail
    p_cd = subparsers.add_parser("client-detail", help="Detailed client view")
    p_cd.add_argument("--name", required=True, help="Client name")
    p_cd.set_defaults(func=cli_client_detail)

    # refresh
    p_ref = subparsers.add_parser("refresh", help="Recalculate all health scores")
    p_ref.set_defaults(func=cli_refresh)

    # export
    p_ex = subparsers.add_parser("export", help="Export as JSON")
    p_ex.add_argument("--format", default="json", choices=["json"])
    p_ex.set_defaults(func=cli_export)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
