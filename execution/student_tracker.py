#!/usr/bin/env python3
"""
Script: student_tracker.py
Purpose: Track Amazon FBA coaching students through milestones.
         Flags at-risk students (stuck > expected days on any milestone).
         CEO dispatches sourcing agent or amazon agent for stuck students.
Inputs:  CLI subcommands
Outputs: Cohort reports, at-risk alerts, student timelines, JSON export

CLI:
    python execution/student_tracker.py add-student --name "John" --tier A --start-date 2026-02-01 [--capital 10000]
    python execution/student_tracker.py update-milestone --student "John" --milestone product_selected [--notes "Selected yoga mats"]
    python execution/student_tracker.py check-in --student "John" --type weekly_call --summary "On track" --mood positive
    python execution/student_tracker.py at-risk
    python execution/student_tracker.py cohort-report
    python execution/student_tracker.py student-detail --name "John"
    python execution/student_tracker.py export --format json
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"

# ── Milestone Definitions ────────────────────────────────────────────────────

MILESTONE_ORDER = [
    "enrolled", "niche_selected", "product_selected", "supplier_contacted",
    "sample_received", "listing_created", "listing_live", "first_sale",
    "profitable_month", "10k_month"
]

EXPECTED_DAYS = {
    "A": {
        "niche_selected": 7, "product_selected": 14, "supplier_contacted": 21,
        "sample_received": 35, "listing_created": 45, "listing_live": 50,
        "first_sale": 60, "profitable_month": 75, "10k_month": 90,
    },
    "B": {
        "niche_selected": 5, "product_selected": 7, "supplier_contacted": 14,
        "sample_received": 28, "listing_created": 32, "listing_live": 35,
        "first_sale": 45, "profitable_month": 60, "10k_month": 75,
    },
    "C": {
        "niche_selected": 7, "product_selected": 14, "supplier_contacted": 21,
        "sample_received": 35, "listing_created": 40, "listing_live": 45,
        "first_sale": 55, "profitable_month": 70, "10k_month": 90,
    },
}

STUCK_MULTIPLIER = 1.5  # Student is "stuck" if days > expected * this

# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    email TEXT,
    tier TEXT NOT NULL,
    capital REAL,
    start_date TEXT NOT NULL,
    target_date TEXT,
    status TEXT DEFAULT 'active',
    current_milestone TEXT DEFAULT 'enrolled',
    health_score INTEGER DEFAULT 100,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    milestone TEXT NOT NULL,
    started_date TEXT NOT NULL,
    completed_date TEXT,
    days_on_milestone INTEGER DEFAULT 0,
    status TEXT DEFAULT 'in_progress',
    notes TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS check_ins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    summary TEXT,
    action_items TEXT,
    mood TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE INDEX IF NOT EXISTS idx_milestones_student ON milestones(student_id);
CREATE INDEX IF NOT EXISTS idx_milestones_status ON milestones(status);
CREATE INDEX IF NOT EXISTS idx_checkins_student ON check_ins(student_id);
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

def add_student(name, tier, start_date=None, email=None, capital=None, notes=None):
    if tier not in ("A", "B", "C"):
        raise ValueError(f"Invalid tier '{tier}'. Must be A, B, or C.")

    if start_date is None:
        start_date = datetime.utcnow().strftime("%Y-%m-%d")

    target_date = (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=90)).strftime("%Y-%m-%d")

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO students (name, email, tier, capital, start_date, target_date, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, email, tier, capital, start_date, target_date, notes, datetime.utcnow().isoformat()))

        student = conn.execute("SELECT id FROM students WHERE name = ?", (name,)).fetchone()

        # Create initial 'enrolled' milestone as completed
        conn.execute("""
            INSERT INTO milestones (student_id, milestone, started_date, completed_date, days_on_milestone, status)
            VALUES (?, 'enrolled', ?, ?, 0, 'completed')
        """, (student["id"], start_date, start_date))

        # Create next milestone as in_progress
        next_ms = MILESTONE_ORDER[1]
        conn.execute("""
            INSERT INTO milestones (student_id, milestone, started_date, status)
            VALUES (?, ?, ?, 'in_progress')
        """, (student["id"], next_ms, start_date))

        conn.execute("UPDATE students SET current_milestone = ? WHERE id = ?", (next_ms, student["id"]))
        conn.commit()

        row = conn.execute("SELECT * FROM students WHERE name = ?", (name,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_milestone(student_name, milestone, notes=None):
    if milestone not in MILESTONE_ORDER:
        raise ValueError(f"Invalid milestone '{milestone}'. Must be one of: {MILESTONE_ORDER}")

    conn = get_db()
    try:
        student = conn.execute("SELECT * FROM students WHERE name = ?", (student_name,)).fetchone()
        if not student:
            raise ValueError(f"Student '{student_name}' not found.")

        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Complete the current in-progress milestone
        current_ms = conn.execute("""
            SELECT * FROM milestones
            WHERE student_id = ? AND status = 'in_progress'
            ORDER BY id DESC LIMIT 1
        """, (student["id"],)).fetchone()

        if current_ms:
            started = datetime.strptime(current_ms["started_date"], "%Y-%m-%d")
            days = (datetime.utcnow() - started).days
            conn.execute("""
                UPDATE milestones SET completed_date = ?, days_on_milestone = ?, status = 'completed', notes = ?
                WHERE id = ?
            """, (today, days, notes, current_ms["id"]))

        # Mark all milestones up to and including this one as completed
        ms_index = MILESTONE_ORDER.index(milestone)
        for i in range(1, ms_index + 1):
            ms_name = MILESTONE_ORDER[i]
            existing = conn.execute("""
                SELECT id, status FROM milestones
                WHERE student_id = ? AND milestone = ?
            """, (student["id"], ms_name)).fetchone()
            if not existing:
                conn.execute("""
                    INSERT INTO milestones (student_id, milestone, started_date, completed_date, days_on_milestone, status)
                    VALUES (?, ?, ?, ?, 0, 'completed')
                """, (student["id"], ms_name, today, today))
            elif existing["status"] != "completed":
                conn.execute("""
                    UPDATE milestones SET completed_date = ?, status = 'completed' WHERE id = ?
                """, (today, existing["id"]))

        # Create next milestone if exists
        if ms_index + 1 < len(MILESTONE_ORDER):
            next_ms = MILESTONE_ORDER[ms_index + 1]
            existing_next = conn.execute("""
                SELECT id FROM milestones WHERE student_id = ? AND milestone = ?
            """, (student["id"], next_ms)).fetchone()
            if not existing_next:
                conn.execute("""
                    INSERT INTO milestones (student_id, milestone, started_date, status)
                    VALUES (?, ?, ?, 'in_progress')
                """, (student["id"], next_ms, today))
            conn.execute("UPDATE students SET current_milestone = ? WHERE id = ?",
                         (next_ms, student["id"]))
        else:
            conn.execute("UPDATE students SET current_milestone = ?, status = 'graduated' WHERE id = ?",
                         (milestone, student["id"]))

        conn.commit()
        return {"student": student_name, "completed": milestone, "date": today}
    finally:
        conn.close()


def log_check_in(student_name, check_type, summary, action_items=None, mood=None):
    conn = get_db()
    try:
        student = conn.execute("SELECT id FROM students WHERE name = ?", (student_name,)).fetchone()
        if not student:
            raise ValueError(f"Student '{student_name}' not found.")

        today = datetime.utcnow().strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO check_ins (student_id, date, type, summary, action_items, mood)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (student["id"], today, check_type, summary, action_items, mood))
        conn.commit()
        return {"student": student_name, "type": check_type, "date": today}
    finally:
        conn.close()


def get_at_risk():
    conn = get_db()
    try:
        students = conn.execute("SELECT * FROM students WHERE status = 'active'").fetchall()
        at_risk = []

        for s in students:
            tier_expected = EXPECTED_DAYS.get(s["tier"], EXPECTED_DAYS["A"])
            current_ms = conn.execute("""
                SELECT * FROM milestones
                WHERE student_id = ? AND status = 'in_progress'
                ORDER BY id DESC LIMIT 1
            """, (s["id"],)).fetchone()

            if not current_ms:
                continue

            started = datetime.strptime(current_ms["started_date"], "%Y-%m-%d")
            days_on = (datetime.utcnow() - started).days
            expected = tier_expected.get(current_ms["milestone"], 14)
            stuck_threshold = int(expected * STUCK_MULTIPLIER)

            if days_on > stuck_threshold:
                # Check mood from recent check-in
                recent_checkin = conn.execute("""
                    SELECT mood FROM check_ins WHERE student_id = ?
                    ORDER BY date DESC LIMIT 1
                """, (s["id"],)).fetchone()

                at_risk.append({
                    "name": s["name"],
                    "tier": s["tier"],
                    "current_milestone": current_ms["milestone"],
                    "days_on_milestone": days_on,
                    "expected_days": expected,
                    "stuck_threshold": stuck_threshold,
                    "days_over": days_on - stuck_threshold,
                    "start_date": s["start_date"],
                    "target_date": s["target_date"],
                    "recent_mood": recent_checkin["mood"] if recent_checkin else None,
                    "recommended_action": _recommend_action(current_ms["milestone"]),
                })

        # Update student statuses
        for r in at_risk:
            conn.execute("UPDATE students SET status = 'at_risk' WHERE name = ?", (r["name"],))
        conn.commit()

        return sorted(at_risk, key=lambda x: x["days_over"], reverse=True)
    finally:
        conn.close()


def _recommend_action(milestone):
    actions = {
        "niche_selected": "Review niche selection framework with student. Share profitable niche examples.",
        "product_selected": "Dispatch sourcing agent for reverse sourcing in student's niche.",
        "supplier_contacted": "Provide supplier negotiation templates. Review Alibaba messaging.",
        "sample_received": "Check if shipping delays. Confirm supplier sent sample.",
        "listing_created": "Run listing optimization review via amazon agent.",
        "listing_live": "Check listing suppression. Review product photos and A+ content.",
        "first_sale": "Review PPC campaign. Check pricing strategy and Buy Box status.",
        "profitable_month": "Analyze P&L. Optimize PPC ACOS. Consider reorder quantities.",
        "10k_month": "Review product expansion strategy. Consider additional ASINs.",
    }
    return actions.get(milestone, "Schedule 1-on-1 coaching call.")


def cohort_report():
    conn = get_db()
    try:
        students = conn.execute("SELECT * FROM students ORDER BY start_date DESC").fetchall()
        if not students:
            return "No students found."

        lines = [
            "═══ COHORT REPORT ═══",
            "",
            f"{'Student':<20} {'Tier':<5} {'Milestone':<20} {'Days':>5} {'Expected':>9} {'Status':<10} {'Target':<12}",
            "─" * 85,
        ]

        for s in students:
            current_ms = conn.execute("""
                SELECT * FROM milestones
                WHERE student_id = ? AND status = 'in_progress'
                ORDER BY id DESC LIMIT 1
            """, (s["id"],)).fetchone()

            if current_ms:
                started = datetime.strptime(current_ms["started_date"], "%Y-%m-%d")
                days_on = (datetime.utcnow() - started).days
                tier_expected = EXPECTED_DAYS.get(s["tier"], EXPECTED_DAYS["A"])
                expected = tier_expected.get(current_ms["milestone"], 14)
                stuck = days_on > int(expected * STUCK_MULTIPLIER)
                status = "STUCK" if stuck else "ON TRACK"
                ms_name = current_ms["milestone"]
            else:
                days_on = 0
                expected = "-"
                status = s["status"].upper()
                ms_name = s["current_milestone"]

            lines.append(
                f"{s['name']:<20} {s['tier']:<5} {ms_name:<20} {days_on:>5} {str(expected):>9} "
                f"{status:<10} {s['target_date'] or '-':<12}"
            )

        # Summary
        total = len(students)
        active = len([s for s in students if s["status"] == "active"])
        at_risk = len([s for s in students if s["status"] == "at_risk"])
        graduated = len([s for s in students if s["status"] == "graduated"])

        lines.extend([
            "",
            f"Total: {total} | Active: {active} | At-risk: {at_risk} | Graduated: {graduated}",
        ])

        return "\n".join(lines)
    finally:
        conn.close()


def student_detail(name):
    conn = get_db()
    try:
        student = conn.execute("SELECT * FROM students WHERE name = ?", (name,)).fetchone()
        if not student:
            return None

        milestones = conn.execute("""
            SELECT * FROM milestones WHERE student_id = ? ORDER BY id ASC
        """, (student["id"],)).fetchall()

        check_ins = conn.execute("""
            SELECT * FROM check_ins WHERE student_id = ? ORDER BY date DESC LIMIT 10
        """, (student["id"],)).fetchall()

        # Calculate days since start
        start = datetime.strptime(student["start_date"], "%Y-%m-%d")
        days_in_program = (datetime.utcnow() - start).days
        target = datetime.strptime(student["target_date"], "%Y-%m-%d") if student["target_date"] else None
        days_remaining = (target - datetime.utcnow()).days if target else None

        return {
            "student": dict(student),
            "days_in_program": days_in_program,
            "days_remaining": days_remaining,
            "milestones": [dict(m) for m in milestones],
            "check_ins": [dict(c) for c in check_ins],
        }
    finally:
        conn.close()


def export_json():
    conn = get_db()
    try:
        students = conn.execute("SELECT * FROM students ORDER BY start_date DESC").fetchall()
        at_risk = get_at_risk()

        return {
            "students": [dict(s) for s in students],
            "at_risk": at_risk,
            "total": len(students),
            "active": len([s for s in students if s["status"] == "active"]),
            "at_risk_count": len(at_risk),
            "graduated": len([s for s in students if s["status"] == "graduated"]),
            "generated_at": datetime.utcnow().isoformat(),
        }
    finally:
        conn.close()


# ── CLI Handlers ─────────────────────────────────────────────────────────────

def cli_add_student(args):
    try:
        result = add_student(args.name, args.tier, args.start_date, args.email, args.capital, args.notes)
        print(f"[student_tracker] Added: {result['name']} (Tier {result['tier']}, target: {result['target_date']})")
    except (ValueError, sqlite3.IntegrityError) as e:
        print(f"[student_tracker] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_update_milestone(args):
    try:
        result = update_milestone(args.student, args.milestone, args.notes)
        print(f"[student_tracker] {result['student']} completed: {result['completed']} on {result['date']}")
    except ValueError as e:
        print(f"[student_tracker] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_check_in(args):
    try:
        result = log_check_in(args.student, args.type, args.summary, args.action_items, args.mood)
        print(f"[student_tracker] Check-in logged for {result['student']} ({result['type']})")
    except ValueError as e:
        print(f"[student_tracker] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_at_risk(args):
    at_risk = get_at_risk()
    if not at_risk:
        print("[student_tracker] No at-risk students.")
        return
    for r in at_risk:
        print(f"  [{r['days_over']}d over] {r['name']} (Tier {r['tier']}) — stuck on {r['current_milestone']} "
              f"({r['days_on_milestone']}d, expected {r['expected_days']}d)")
        print(f"    Action: {r['recommended_action']}")
    print(json.dumps(at_risk, indent=2))


def cli_cohort_report(args):
    print(cohort_report())


def cli_student_detail(args):
    detail = student_detail(args.name)
    if not detail:
        print(f"[student_tracker] Student '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(detail, indent=2, default=str))


def cli_export(args):
    result = export_json()
    print(json.dumps(result, indent=2))


# ── CLI Parser ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Student Progress Tracker — milestones, at-risk detection, cohort reports"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # add-student
    p_add = subparsers.add_parser("add-student", help="Add a new student")
    p_add.add_argument("--name", required=True, help="Student name")
    p_add.add_argument("--tier", required=True, choices=["A", "B", "C"], help="Student tier")
    p_add.add_argument("--start-date", default=None, help="Start date (YYYY-MM-DD)")
    p_add.add_argument("--email", default=None, help="Student email")
    p_add.add_argument("--capital", type=float, default=None, help="Starting capital ($)")
    p_add.add_argument("--notes", default=None, help="Optional notes")
    p_add.set_defaults(func=cli_add_student)

    # update-milestone
    p_ms = subparsers.add_parser("update-milestone", help="Mark a milestone as completed")
    p_ms.add_argument("--student", required=True, help="Student name")
    p_ms.add_argument("--milestone", required=True, choices=MILESTONE_ORDER, help="Milestone name")
    p_ms.add_argument("--notes", default=None, help="Optional notes")
    p_ms.set_defaults(func=cli_update_milestone)

    # check-in
    p_ci = subparsers.add_parser("check-in", help="Log a check-in")
    p_ci.add_argument("--student", required=True, help="Student name")
    p_ci.add_argument("--type", required=True,
                      choices=["weekly_call", "dm_check", "assignment_review", "emergency"],
                      help="Check-in type")
    p_ci.add_argument("--summary", required=True, help="Check-in summary")
    p_ci.add_argument("--action-items", default=None, help="Action items")
    p_ci.add_argument("--mood", default=None,
                      choices=["positive", "neutral", "frustrated", "disengaged"],
                      help="Student mood")
    p_ci.set_defaults(func=cli_check_in)

    # at-risk
    p_ar = subparsers.add_parser("at-risk", help="List at-risk students")
    p_ar.set_defaults(func=cli_at_risk)

    # cohort-report
    p_cr = subparsers.add_parser("cohort-report", help="Full cohort report")
    p_cr.set_defaults(func=cli_cohort_report)

    # student-detail
    p_sd = subparsers.add_parser("student-detail", help="Detailed student view")
    p_sd.add_argument("--name", required=True, help="Student name")
    p_sd.set_defaults(func=cli_student_detail)

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
