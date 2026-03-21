#!/usr/bin/env python3
"""
Script: exit_interview.py
Purpose: Manages exit interview + win-back flow for churning Amazon FBA students.
         Sequences personalized touchpoints over 14 days, logs churn reasons,
         offers pause options, and generates weekly churn analysis reports.
Inputs:  CLI subcommands
Outputs: Win-back DMs (Discord), churn reports, pause offers

CLI:
    python execution/exit_interview.py start --student "Name"
    python execution/exit_interview.py send-next
    python execution/exit_interview.py log-reason --student "Name" --reason financial [--details "Lost job"]
    python execution/exit_interview.py offer-pause --student "Name" --months 1
    python execution/exit_interview.py report
    python execution/exit_interview.py status
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

# ── Constants ─────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"
GUILD_ID = "1185214150222286849"

WIN_BACK_SEQUENCE = [
    {
        "day": 0,
        "type": "no_judgment",
        "message": (
            "Hey {name}, I noticed you've been quiet lately. No judgment "
            "-- just checking in. How are things going? If Amazon isn't the "
            "right fit right now, that's totally okay. But if there's something "
            "specific holding you back, I'd love to help. What's going on?"
        ),
    },
    {
        "day": 3,
        "type": "success_story",
        "message": (
            "Hey {name}, just wanted to share -- {success_name} started in a "
            "similar spot and just hit {success_milestone}. Sometimes all it "
            "takes is one breakthrough. If you want to hop on a quick call to "
            "reset your strategy, I'm here. No sales pitch, just support."
        ),
    },
    {
        "day": 7,
        "type": "personal_sabbo",
        "message": (
            "Hey {name}, Sabbo here personally. I know the Amazon journey isn't "
            "easy -- I've been through the exact same struggles. I'd hate for "
            "you to leave right before the breakthrough. Can we do a 15-min call "
            "this week? I'll look at your account and give you a clear action "
            "plan. No strings attached."
        ),
    },
    {
        "day": 14,
        "type": "final_offer",
        "message": (
            "Hey {name}, last check-in from me. I want you to know the door "
            "is always open. If you ever want to pick things back up, just DM "
            "me and we'll figure out a plan. Wishing you all the best!"
        ),
    },
]

CHURN_REASONS = {
    "financial": "financial",
    "time": "time",
    "frustrated": "frustrated",
    "no_results": "no_results",
    "other": "other",
    "pause_request": "pause_request",
}

# ── Database ──────────────────────────────────────────────────────────────────

ALTER_COLUMNS = [
    ("status", "TEXT DEFAULT 'active'"),
    ("last_touchpoint_day", "INTEGER DEFAULT 0"),
    ("details", "TEXT"),
]


def get_db() -> sqlite3.Connection:
    """Connect to the shared coaching DB and ensure exit-interview schema exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Add columns to churn_events if missing."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(churn_events)").fetchall()}
    for col_name, col_type in ALTER_COLUMNS:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE churn_events ADD COLUMN {col_name} {col_type}")
    conn.commit()


# ── Discord Helpers ───────────────────────────────────────────────────────────

def send_dm(discord_user_id: str, content: str) -> tuple[bool, str | int]:
    """Send a DM to a Discord user via bot token."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        return False, "no_token"
    if requests is None:
        return False, "no_requests_lib"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    resp = requests.post(
        "https://discord.com/api/v10/users/@me/channels",
        headers=headers,
        json={"recipient_id": str(discord_user_id)},
    )
    if resp.status_code != 200:
        return False, resp.status_code
    dm_id = resp.json()["id"]
    if len(content) > 2000:
        content = content[:1997] + "..."
    resp2 = requests.post(
        f"https://discord.com/api/v10/channels/{dm_id}/messages",
        headers=headers,
        json={"content": content},
    )
    return resp2.status_code == 200, resp2.status_code


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_student(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    """Find a student by partial name match."""
    return conn.execute(
        "SELECT * FROM students WHERE name LIKE ?", (f"%{name}%",)
    ).fetchone()


def _get_success_story(conn: sqlite3.Connection) -> tuple[str, str]:
    """Get a recent success story for the win-back message."""
    row = conn.execute("""
        SELECT s.name, m.milestone
        FROM milestones m
        JOIN students s ON s.id = m.student_id
        WHERE m.status = 'completed'
          AND m.milestone IN ('first_sale', 'profitable_month', '10k_month')
        ORDER BY m.completed_date DESC
        LIMIT 1
    """).fetchone()
    if row:
        milestone_labels = {
            "first_sale": "their first sale",
            "profitable_month": "a profitable month",
            "10k_month": "$10K in a single month",
        }
        return row["name"].split()[0], milestone_labels.get(row["milestone"], row["milestone"])
    return "a student", "their first sale"


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_start(args: argparse.Namespace) -> None:
    """Start a win-back sequence for a student."""
    conn = get_db()
    try:
        student = _find_student(conn, args.student)
        if not student:
            print(f"Student not found: {args.student}")
            return

        # Check if already in an active win-back sequence
        existing = conn.execute(
            "SELECT * FROM churn_events WHERE student_id = ? AND status = 'active'",
            (student["id"],),
        ).fetchone()
        if existing:
            print(f"Already in win-back sequence (started {existing['date']})")
            return

        now = datetime.utcnow().isoformat()
        first_name = student["name"].split()[0]

        # Create churn event
        conn.execute("""
            INSERT INTO churn_events
                (student_id, reason_category, date, status, last_touchpoint_day)
            VALUES (?, 'unknown', ?, 'active', 0)
        """, (student["id"], now))

        # Queue first touchpoint
        first = WIN_BACK_SEQUENCE[0]
        message = first["message"].format(name=first_name)
        conn.execute("""
            INSERT INTO touchpoints (student_id, type, channel, message, status)
            VALUES (?, 'win_back', 'discord_dm', ?, 'queued')
        """, (student["id"], message))

        conn.commit()
        print(f"Started win-back sequence for {student['name']}")
        print(f"  First touchpoint queued (Day 0 — {first['type']})")
    finally:
        conn.close()


def cmd_send_next(args: argparse.Namespace) -> None:
    """Send the next pending touchpoint in all active win-back sequences."""
    conn = get_db()
    try:
        active = conn.execute("""
            SELECT ce.*, s.name, s.discord_user_id
            FROM churn_events ce
            JOIN students s ON s.id = ce.student_id
            WHERE ce.status = 'active'
        """).fetchall()

        if not active:
            print("No active win-back sequences.")
            return

        sent_count = 0
        for event in active:
            current_day = event["last_touchpoint_day"] or 0

            # Find next step in the sequence
            next_step = None
            for step in WIN_BACK_SEQUENCE:
                if step["day"] > current_day:
                    next_step = step
                    break

            if next_step is None:
                # Sequence complete
                conn.execute(
                    "UPDATE churn_events SET status = 'completed' WHERE id = ?",
                    (event["id"],),
                )
                print(f"  {event['name']}: Sequence completed (all touchpoints sent)")
                continue

            # Check if enough days have elapsed
            event_date = datetime.fromisoformat(event["date"])
            days_elapsed = (datetime.utcnow() - event_date).days
            if days_elapsed < next_step["day"]:
                remaining = next_step["day"] - days_elapsed
                print(f"  {event['name']}: Next touchpoint (Day {next_step['day']}) "
                      f"in {remaining} day(s)")
                continue

            # Build message
            first_name = event["name"].split()[0]
            success_name, success_milestone = _get_success_story(conn)
            message = next_step["message"].format(
                name=first_name,
                success_name=success_name,
                success_milestone=success_milestone,
            )

            # Send DM
            if event["discord_user_id"]:
                ok, code = send_dm(event["discord_user_id"], message)
                status = "sent" if ok else "failed"
                if not ok:
                    print(f"  {event['name']}: DM failed (code: {code})")
            else:
                status = "no_discord"
                print(f"  {event['name']}: No Discord user ID — message queued only")

            # Record touchpoint
            now = datetime.utcnow().isoformat()
            conn.execute("""
                INSERT INTO touchpoints (student_id, type, channel, message, status, sent_at)
                VALUES (?, 'win_back', 'discord_dm', ?, ?, ?)
            """, (event["student_id"], message, status, now if status == "sent" else None))

            # Update churn event
            conn.execute("""
                UPDATE churn_events
                SET last_touchpoint_day = ?, win_back_attempted = 1
                WHERE id = ?
            """, (next_step["day"], event["id"]))

            conn.commit()
            sent_count += 1
            print(f"  {event['name']}: Sent Day {next_step['day']} ({next_step['type']})")

        print(f"\n{sent_count} touchpoint(s) sent across {len(active)} active sequence(s).")
    finally:
        conn.close()


def cmd_log_reason(args: argparse.Namespace) -> None:
    """Log the churn reason from an exit interview."""
    reason = args.reason.lower()
    if reason not in CHURN_REASONS:
        print(f"Invalid reason. Valid: {', '.join(CHURN_REASONS.keys())}")
        return

    conn = get_db()
    try:
        student = _find_student(conn, args.student)
        if not student:
            print(f"Student not found: {args.student}")
            return

        # Find active churn event
        event = conn.execute(
            "SELECT * FROM churn_events WHERE student_id = ? AND status = 'active' "
            "ORDER BY date DESC LIMIT 1",
            (student["id"],),
        ).fetchone()
        if not event:
            # Also check completed events without a reason
            event = conn.execute(
                "SELECT * FROM churn_events WHERE student_id = ? AND reason_category = 'unknown' "
                "ORDER BY date DESC LIMIT 1",
                (student["id"],),
            ).fetchone()
        if not event:
            print(f"No churn event found for {student['name']}. Run 'start' first.")
            return

        details_text = args.details if args.details else None
        conn.execute("""
            UPDATE churn_events
            SET reason_category = ?, reason_detail = ?, exit_interview_done = 1, details = ?
            WHERE id = ?
        """, (CHURN_REASONS[reason], details_text, details_text, event["id"]))
        conn.commit()

        print(f"Logged churn reason for {student['name']}: {reason}")
        if details_text:
            print(f"  Details: {details_text}")
    finally:
        conn.close()


def cmd_offer_pause(args: argparse.Namespace) -> None:
    """Offer a pause instead of cancellation."""
    conn = get_db()
    try:
        student = _find_student(conn, args.student)
        if not student:
            print(f"Student not found: {args.student}")
            return

        months = args.months or 1
        resume_date = (datetime.utcnow() + timedelta(days=months * 30)).strftime("%Y-%m-%d")
        first_name = student["name"].split()[0]

        message = (
            f"Hey {first_name}, totally understand if now isn't the right time. "
            f"How about we pause your membership for {months} month(s)? "
            f"You'd pick back up on {resume_date} with your full progress saved "
            f"-- same group, same support, zero extra cost. Would that help?"
        )

        # Send DM
        if student["discord_user_id"]:
            ok, code = send_dm(student["discord_user_id"], message)
            if ok:
                print(f"Pause offer sent to {student['name']} ({months} month(s), resume {resume_date})")
            else:
                print(f"DM failed (code: {code}) -- message below:")
                print(f"  {message}")
        else:
            print(f"No Discord ID for {student['name']}. Pause offer message:")
            print(f"  {message}")

        # Record touchpoint
        conn.execute("""
            INSERT INTO touchpoints (student_id, type, channel, message, status, sent_at)
            VALUES (?, 'pause_offer', 'discord_dm', ?, ?, ?)
        """, (
            student["id"],
            message,
            "sent" if student["discord_user_id"] else "manual",
            datetime.utcnow().isoformat(),
        ))

        # Log reason as pause_request if there is an active churn event
        conn.execute("""
            UPDATE churn_events
            SET reason_category = 'pause_request',
                details = ?
            WHERE student_id = ? AND status = 'active'
        """, (f"Offered {months}-month pause, resume {resume_date}", student["id"]))

        conn.commit()
    finally:
        conn.close()


def cmd_report(args: argparse.Namespace) -> None:
    """Weekly churn analysis report."""
    conn = get_db()
    try:
        # Group by reason
        reasons = conn.execute("""
            SELECT ce.reason_category, COUNT(*) as cnt,
                   GROUP_CONCAT(s.name, ', ') as names
            FROM churn_events ce
            JOIN students s ON s.id = ce.student_id
            WHERE ce.reason_category != 'unknown'
            GROUP BY ce.reason_category
            ORDER BY cnt DESC
        """).fetchall()

        no_reason = conn.execute(
            "SELECT COUNT(*) as cnt FROM churn_events WHERE reason_category = 'unknown'"
        ).fetchone()["cnt"]

        print("\n  CHURN ANALYSIS REPORT")
        print("=" * 50)
        total_with_reason = 0
        for r in reasons:
            total_with_reason += r["cnt"]
            print(f"  {r['reason_category']:20s} -- {r['cnt']} students ({r['names']})")
        if no_reason:
            print(f"  {'unknown':20s} -- {no_reason} students (no exit interview completed)")

        # Win-back success rate
        total = conn.execute("SELECT COUNT(*) as cnt FROM churn_events").fetchone()["cnt"]
        saved = conn.execute(
            "SELECT COUNT(*) as cnt FROM churn_events WHERE win_back_result = 'saved'"
        ).fetchone()["cnt"]
        if total > 0:
            print(f"\n  Win-back success rate: {saved}/{total} ({saved / total * 100:.0f}%)")

        # Active sequences
        active = conn.execute(
            "SELECT COUNT(*) as cnt FROM churn_events WHERE status = 'active'"
        ).fetchone()["cnt"]
        print(f"  Active win-back sequences: {active}")
        print()
    finally:
        conn.close()


def cmd_status(args: argparse.Namespace) -> None:
    """Show all active win-back sequences."""
    conn = get_db()
    try:
        active = conn.execute("""
            SELECT ce.*, s.name, s.discord_user_id
            FROM churn_events ce
            JOIN students s ON s.id = ce.student_id
            WHERE ce.status = 'active'
            ORDER BY ce.date DESC
        """).fetchall()

        if not active:
            print("No active win-back sequences.")
            return

        print(f"\n  ACTIVE WIN-BACK SEQUENCES ({len(active)})")
        print("=" * 60)
        for event in active:
            current_day = event["last_touchpoint_day"] or 0
            days_elapsed = (datetime.utcnow() - datetime.fromisoformat(event["date"])).days

            # Find next step
            next_step = None
            for step in WIN_BACK_SEQUENCE:
                if step["day"] > current_day:
                    next_step = step
                    break

            status_label = "COMPLETE" if next_step is None else f"Day {next_step['day']} ({next_step['type']})"
            reason = event["reason_category"] if event["reason_category"] != "unknown" else "?"

            print(f"  {event['name']:25s} | Started: {event['date'][:10]} | "
                  f"Day {days_elapsed} | Last sent: Day {current_day} | "
                  f"Next: {status_label} | Reason: {reason}")
        print()
    finally:
        conn.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exit interview + win-back flow for churning students."
    )
    subs = parser.add_subparsers(dest="command")

    # start
    p_start = subs.add_parser("start", help="Start win-back sequence for a student")
    p_start.add_argument("--student", required=True, help="Student name (partial match)")

    # send-next
    subs.add_parser("send-next", help="Send next pending touchpoints in all active sequences")

    # log-reason
    p_reason = subs.add_parser("log-reason", help="Log churn reason from exit interview")
    p_reason.add_argument("--student", required=True, help="Student name")
    p_reason.add_argument("--reason", required=True,
                          help=f"Reason: {', '.join(CHURN_REASONS.keys())}")
    p_reason.add_argument("--details", default=None, help="Additional details")

    # offer-pause
    p_pause = subs.add_parser("offer-pause", help="Offer pause instead of cancellation")
    p_pause.add_argument("--student", required=True, help="Student name")
    p_pause.add_argument("--months", type=int, default=1, help="Months to pause (default: 1)")

    # report
    subs.add_parser("report", help="Weekly churn analysis report")

    # status
    subs.add_parser("status", help="Show all active win-back sequences")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "start": cmd_start,
        "send-next": cmd_send_next,
        "log-reason": cmd_log_reason,
        "offer-pause": cmd_offer_pause,
        "report": cmd_report,
        "status": cmd_status,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
