#!/usr/bin/env python3
"""
Script: graduation_flow.py
Purpose: Manage the Day 75-90 graduation sequence for Amazon FBA coaching students.
         Automates review scheduling, upsell presentation, follow-ups, and
         graduation celebration. Tracks conversions to backend subscriptions.
Inputs:  CLI subcommands
Outputs: Graduation pipeline, touchpoint sends, conversion tracking, MRR reports

CLI:
    python execution/graduation_flow.py check                    # List students in Day 60-90 window
    python execution/graduation_flow.py start --student "Mark"   # Start graduation flow for a student
    python execution/graduation_flow.py status                   # All active graduation flows
    python execution/graduation_flow.py send-next                # Send next pending touchpoint for all active flows
    python execution/graduation_flow.py convert --student "Mark" --offer retainer --revenue 597
    python execution/graduation_flow.py graduate --student "Mark"  # Mark as graduated (no upsell)
    python execution/graduation_flow.py backend-report           # All backend subscriptions + MRR
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"

# ── Graduation Sequence ─────────────────────────────────────────────────────

GRADUATION_SEQUENCE = [
    {
        "day": 75,
        "type": "review_dm",
        "message": (
            "Hey {name}! We're at Day 75 of your 90-day journey. Let's review "
            "your progress — I'd love to schedule a quick call this week to "
            "celebrate your wins and talk about what's next. When works for you?"
        ),
    },
    {
        "day": 80,
        "type": "offer_dm",
        "message": (
            "Hey {name}, following up from our chat. Most students who continue "
            "past 90 days see 3-5x the growth in months 4-6. Here's what the "
            "Inner Circle includes:\n\n"
            "✅ Weekly group calls (permanent)\n"
            "✅ Monthly 1:1 with me (30 min)\n"
            "✅ Your private channel stays open\n"
            "✅ Lead Finder product sourcing access\n"
            "✅ Monthly advanced masterclass\n"
            "✅ Priority deal alerts\n\n"
            "**$597/month, no contract, cancel anytime.**\n\n"
            "Want me to set you up?"
        ),
    },
    {
        "day": 83,
        "type": "faq_dm",
        "message": (
            "Hey {name}, just following up. A few questions students usually ask:\n\n"
            "**Q: What if I'm not ready?**\n"
            "A: If you've made progress in 90 days, you'll make more with continued "
            "support. Most students who pause lose momentum.\n\n"
            "**Q: Can I re-join later?**\n"
            "A: Yes, but your momentum and private channel history are valuable. "
            "Pausing means rebuilding.\n\n"
            "**Q: What's different from the core program?**\n"
            "A: You keep everything + get advanced content, monthly 1:1s, and "
            "priority sourcing leads.\n\n"
            "Let me know if you have any questions!"
        ),
    },
    {
        "day": 85,
        "type": "urgency_dm",
        "message": (
            "Hey {name}, your 90-day access wraps up in 5 days. If you want to "
            "continue with the Inner Circle ($597/mo), let's get you set up this "
            "week so there's no gap. Otherwise, I'll make sure your graduation is "
            "celebrated properly! Either way, I'm proud of your progress."
        ),
    },
    {
        "day": 87,
        "type": "final_dm",
        "message": (
            "Hey {name}, 3 days left. Are you continuing with the Inner Circle, "
            "or graduating? No pressure either way — just want to make sure we "
            "handle the transition right."
        ),
    },
    {
        "day": 90,
        "type": "graduation",
        "message": (
            "**GRADUATION DAY** — {name} has completed the 24/7 Profits 90-day "
            "program! From Day 1 to today, this is what happens when you put in "
            "the work. Congratulations!"
        ),
    },
]

VALID_OFFER_TYPES = ["retainer", "mastermind", "ppc", "va_placement"]

# ── Touchpoints Schema (extends student_health_monitor) ─────────────────────

GRAD_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS graduation_touchpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    graduation_flow_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    day_number INTEGER NOT NULL,
    touchpoint_type TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    sent_at TEXT,
    discord_message_id TEXT,
    FOREIGN KEY (graduation_flow_id) REFERENCES graduation_flows(id),
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE INDEX IF NOT EXISTS idx_grad_tp_flow ON graduation_touchpoints(graduation_flow_id);
CREATE INDEX IF NOT EXISTS idx_grad_tp_status ON graduation_touchpoints(status);
"""


# ── Database Connection ──────────────────────────────────────────────────────

def get_db():
    """Connect to the shared coaching DB and ensure graduation schema exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(GRAD_SCHEMA_SQL)
    return conn


# ── Discord Helpers ──────────────────────────────────────────────────────────

def send_discord_dm(discord_user_id, message):
    """Send a DM to a Discord user via the REST API."""
    if not requests:
        print("[WARN] requests not installed, skipping Discord DM")
        return None

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("[WARN] DISCORD_BOT_TOKEN not set, skipping Discord DM")
        return None

    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}

    # Open DM channel
    resp = requests.post(
        "https://discord.com/api/v10/users/@me/channels",
        headers=headers,
        json={"recipient_id": str(discord_user_id)},
    )
    if resp.status_code not in (200, 201):
        print(f"[ERROR] Failed to open DM channel: {resp.status_code} {resp.text}")
        return None

    dm_channel_id = resp.json().get("id")

    # Send message
    resp = requests.post(
        f"https://discord.com/api/v10/channels/{dm_channel_id}/messages",
        headers=headers,
        json={"content": message},
    )
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    else:
        print(f"[ERROR] Failed to send DM: {resp.status_code} {resp.text}")
        return None


def send_discord_message(channel_id, message):
    """Send a message to a Discord channel via the REST API."""
    if not requests:
        print("[WARN] requests not installed, skipping Discord message")
        return None

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("[WARN] DISCORD_BOT_TOKEN not set, skipping Discord message")
        return None

    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    resp = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers=headers,
        json={"content": message},
    )
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    else:
        print(f"[ERROR] Failed to send message: {resp.status_code} {resp.text}")
        return None


# ── Core Functions ───────────────────────────────────────────────────────────

def check_graduation_pipeline():
    """List all students in the Day 60-100 window, flagging graduation readiness."""
    conn = get_db()
    try:
        students = conn.execute(
            "SELECT * FROM students WHERE status IN ('active', 'at_risk')"
        ).fetchall()

        pipeline = []
        now = datetime.utcnow()

        for s in students:
            start = datetime.strptime(s["start_date"], "%Y-%m-%d")
            days_in = (now - start).days

            if 60 <= days_in <= 100:
                existing = conn.execute(
                    "SELECT * FROM graduation_flows WHERE student_id = ?",
                    (s["id"],),
                ).fetchone()

                pipeline.append({
                    "student_id": s["id"],
                    "name": s["name"],
                    "tier": s["tier"],
                    "days_in_program": days_in,
                    "start_date": s["start_date"],
                    "current_milestone": s["current_milestone"],
                    "health_score": s["health_score"],
                    "graduation_flow": dict(existing) if existing else None,
                    "flow_status": existing["status"] if existing else "not_started",
                })

        # Sort by days_in_program descending (closest to graduation first)
        pipeline.sort(key=lambda x: x["days_in_program"], reverse=True)
        return pipeline
    finally:
        conn.close()


def start_graduation_flow(student_name):
    """Start the Day 75-90 graduation sequence for a student."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE name = ? COLLATE NOCASE",
            (student_name,),
        ).fetchone()
        if not student:
            raise ValueError(f"Student '{student_name}' not found.")

        # Check if flow already exists
        existing = conn.execute(
            "SELECT * FROM graduation_flows WHERE student_id = ? AND status = 'active'",
            (student["id"],),
        ).fetchone()
        if existing:
            raise ValueError(
                f"Graduation flow already active for '{student_name}' "
                f"(started {existing['started_at']})"
            )

        now = datetime.utcnow().isoformat()

        # Create graduation flow
        conn.execute(
            """INSERT INTO graduation_flows (student_id, started_at, status)
               VALUES (?, ?, 'active')""",
            (student["id"], now),
        )
        flow = conn.execute(
            "SELECT * FROM graduation_flows WHERE student_id = ? ORDER BY id DESC LIMIT 1",
            (student["id"],),
        ).fetchone()

        # Pre-generate all touchpoints as pending
        for step in GRADUATION_SEQUENCE:
            msg = step["message"].format(name=student["name"])
            conn.execute(
                """INSERT INTO graduation_touchpoints
                   (graduation_flow_id, student_id, day_number, touchpoint_type, message, status)
                   VALUES (?, ?, ?, ?, ?, 'pending')""",
                (flow["id"], student["id"], step["day"], step["type"], msg),
            )

        conn.commit()
        return {
            "flow_id": flow["id"],
            "student": student["name"],
            "student_id": student["id"],
            "started_at": now,
            "touchpoints_created": len(GRADUATION_SEQUENCE),
        }
    finally:
        conn.close()


def get_active_flows():
    """Return all active graduation flows with student details."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT gf.*, s.name, s.tier, s.start_date, s.current_milestone,
                      s.health_score, s.discord_user_id, s.discord_channel_id
               FROM graduation_flows gf
               JOIN students s ON gf.student_id = s.id
               WHERE gf.status = 'active'
               ORDER BY gf.started_at"""
        ).fetchall()

        flows = []
        now = datetime.utcnow()
        for r in rows:
            start = datetime.strptime(r["start_date"], "%Y-%m-%d")
            days_in = (now - start).days

            # Count touchpoints
            sent = conn.execute(
                "SELECT COUNT(*) as c FROM graduation_touchpoints WHERE graduation_flow_id = ? AND status = 'sent'",
                (r["id"],),
            ).fetchone()["c"]
            pending = conn.execute(
                "SELECT COUNT(*) as c FROM graduation_touchpoints WHERE graduation_flow_id = ? AND status = 'pending'",
                (r["id"],),
            ).fetchone()["c"]

            # Next pending touchpoint
            next_tp = conn.execute(
                """SELECT * FROM graduation_touchpoints
                   WHERE graduation_flow_id = ? AND status = 'pending'
                   ORDER BY day_number LIMIT 1""",
                (r["id"],),
            ).fetchone()

            flows.append({
                "flow_id": r["id"],
                "student": r["name"],
                "tier": r["tier"],
                "days_in_program": days_in,
                "health_score": r["health_score"],
                "started_at": r["started_at"],
                "touchpoints_sent": sent,
                "touchpoints_pending": pending,
                "next_touchpoint": {
                    "day": next_tp["day_number"],
                    "type": next_tp["touchpoint_type"],
                } if next_tp else None,
            })

        return flows
    finally:
        conn.close()


def send_next_touchpoints():
    """For each active flow, send the next pending touchpoint if the student is on/past that day."""
    conn = get_db()
    results = []
    try:
        flows = conn.execute(
            """SELECT gf.*, s.name, s.start_date, s.discord_user_id, s.discord_channel_id
               FROM graduation_flows gf
               JOIN students s ON gf.student_id = s.id
               WHERE gf.status = 'active'"""
        ).fetchall()

        now = datetime.utcnow()

        for flow in flows:
            start = datetime.strptime(flow["start_date"], "%Y-%m-%d")
            days_in = (now - start).days

            # Get next pending touchpoint
            tp = conn.execute(
                """SELECT * FROM graduation_touchpoints
                   WHERE graduation_flow_id = ? AND status = 'pending'
                   ORDER BY day_number LIMIT 1""",
                (flow["id"],),
            ).fetchone()

            if not tp:
                continue

            # Only send if student is on or past the touchpoint day
            if days_in < tp["day_number"]:
                results.append({
                    "student": flow["name"],
                    "action": "skipped",
                    "reason": f"Day {days_in}, touchpoint is Day {tp['day_number']}",
                })
                continue

            # Determine send method
            discord_msg_id = None
            if tp["touchpoint_type"] == "graduation":
                # Graduation announcement goes to the student's channel
                if flow["discord_channel_id"]:
                    discord_msg_id = send_discord_message(
                        flow["discord_channel_id"], tp["message"]
                    )
                else:
                    print(f"  [INFO] No channel for {flow['name']}, printing message:")
                    print(f"  {tp['message']}")
            else:
                # DMs go directly to the student
                if flow["discord_user_id"]:
                    discord_msg_id = send_discord_dm(
                        flow["discord_user_id"], tp["message"]
                    )
                else:
                    print(f"  [INFO] No discord_user_id for {flow['name']}, printing message:")
                    print(f"  {tp['message']}")

            # Mark as sent
            conn.execute(
                """UPDATE graduation_touchpoints
                   SET status = 'sent', sent_at = ?, discord_message_id = ?
                   WHERE id = ?""",
                (now.isoformat(), discord_msg_id, tp["id"]),
            )

            # Log engagement signal if table exists
            try:
                conn.execute(
                    """INSERT INTO engagement_signals
                       (student_id, signal_type, channel, value, date, notes, created_at)
                       VALUES (?, ?, 'discord', ?, ?, ?, ?)""",
                    (
                        flow["student_id"],
                        f"graduation_{tp['touchpoint_type']}",
                        "sent",
                        now.strftime("%Y-%m-%d"),
                        f"Day {tp['day_number']} touchpoint",
                        now.isoformat(),
                    ),
                )
            except sqlite3.OperationalError:
                pass  # engagement_signals table may not exist yet

            conn.commit()

            results.append({
                "student": flow["name"],
                "action": "sent",
                "touchpoint_type": tp["touchpoint_type"],
                "day": tp["day_number"],
                "discord_sent": discord_msg_id is not None,
            })

        return results
    finally:
        conn.close()


def convert_student(student_name, offer_type, revenue):
    """Record a student accepting a backend offer after graduation flow."""
    if offer_type not in VALID_OFFER_TYPES:
        raise ValueError(
            f"Invalid offer type '{offer_type}'. Valid: {VALID_OFFER_TYPES}"
        )

    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE name = ? COLLATE NOCASE",
            (student_name,),
        ).fetchone()
        if not student:
            raise ValueError(f"Student '{student_name}' not found.")

        # Find active graduation flow
        flow = conn.execute(
            "SELECT * FROM graduation_flows WHERE student_id = ? AND status = 'active'",
            (student["id"],),
        ).fetchone()
        if not flow:
            raise ValueError(
                f"No active graduation flow for '{student_name}'. "
                "Start one with: graduation_flow.py start --student \"{}\""
                .format(student_name)
            )

        now = datetime.utcnow()

        # Update graduation flow
        conn.execute(
            """UPDATE graduation_flows
               SET status = 'converted', offer_presented = ?, offer_accepted = ?,
                   new_revenue = ?, completed_at = ?
               WHERE id = ?""",
            (
                json.dumps(VALID_OFFER_TYPES),
                offer_type,
                revenue,
                now.isoformat(),
                flow["id"],
            ),
        )

        # Create backend subscription
        conn.execute(
            """INSERT INTO backend_subscriptions
               (student_id, offer_type, monthly_revenue, start_date, status)
               VALUES (?, ?, ?, ?, 'active')""",
            (student["id"], offer_type, revenue, now.strftime("%Y-%m-%d")),
        )

        # Update student status
        conn.execute(
            "UPDATE students SET status = 'continuation' WHERE id = ?",
            (student["id"],),
        )

        conn.commit()

        return {
            "student": student["name"],
            "offer_type": offer_type,
            "monthly_revenue": revenue,
            "status": "converted",
            "subscription_start": now.strftime("%Y-%m-%d"),
        }
    finally:
        conn.close()


def graduate_student(student_name):
    """Mark a student as graduated (no upsell accepted)."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE name = ? COLLATE NOCASE",
            (student_name,),
        ).fetchone()
        if not student:
            raise ValueError(f"Student '{student_name}' not found.")

        now = datetime.utcnow()

        # Find active graduation flow
        flow = conn.execute(
            "SELECT * FROM graduation_flows WHERE student_id = ? AND status = 'active'",
            (student["id"],),
        ).fetchone()

        if flow:
            conn.execute(
                """UPDATE graduation_flows
                   SET status = 'graduated', completed_at = ?
                   WHERE id = ?""",
                (now.isoformat(), flow["id"]),
            )
        else:
            # Create a completed flow record even if one wasn't started
            conn.execute(
                """INSERT INTO graduation_flows
                   (student_id, started_at, status, completed_at)
                   VALUES (?, ?, 'graduated', ?)""",
                (student["id"], now.isoformat(), now.isoformat()),
            )

        # Update student status
        conn.execute(
            "UPDATE students SET status = 'graduated' WHERE id = ?",
            (student["id"],),
        )

        conn.commit()

        return {
            "student": student["name"],
            "status": "graduated",
            "completed_at": now.isoformat(),
        }
    finally:
        conn.close()


def backend_report():
    """Generate a report of all backend subscriptions and MRR."""
    conn = get_db()
    try:
        # Active subscriptions
        subs = conn.execute(
            """SELECT bs.*, s.name as student_name, s.tier
               FROM backend_subscriptions bs
               JOIN students s ON bs.student_id = s.id
               ORDER BY bs.start_date DESC"""
        ).fetchall()

        active_subs = [dict(s) for s in subs if s["status"] == "active"]
        cancelled_subs = [dict(s) for s in subs if s["status"] == "cancelled"]
        paused_subs = [dict(s) for s in subs if s["status"] == "paused"]

        total_mrr = sum(s["monthly_revenue"] for s in active_subs)

        # Conversion rate
        total_flows = conn.execute(
            "SELECT COUNT(*) as c FROM graduation_flows WHERE status IN ('converted', 'graduated')"
        ).fetchone()["c"]
        converted_flows = conn.execute(
            "SELECT COUNT(*) as c FROM graduation_flows WHERE status = 'converted'"
        ).fetchone()["c"]
        conversion_rate = (
            (converted_flows / total_flows * 100) if total_flows > 0 else 0
        )

        # MRR by offer type
        mrr_by_offer = {}
        for s in active_subs:
            offer = s["offer_type"]
            mrr_by_offer[offer] = mrr_by_offer.get(offer, 0) + s["monthly_revenue"]

        return {
            "total_mrr": total_mrr,
            "active_subscriptions": len(active_subs),
            "cancelled_subscriptions": len(cancelled_subs),
            "paused_subscriptions": len(paused_subs),
            "conversion_rate_pct": round(conversion_rate, 1),
            "total_graduated": total_flows,
            "total_converted": converted_flows,
            "mrr_by_offer": mrr_by_offer,
            "subscriptions": active_subs,
        }
    finally:
        conn.close()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Manage Day 75-90 graduation flows for coaching students"
    )
    sub = parser.add_subparsers(dest="command")

    # check
    sub.add_parser("check", help="List students in Day 60-90 window")

    # start
    p_start = sub.add_parser("start", help="Start graduation flow for a student")
    p_start.add_argument("--student", required=True, help="Student name")

    # status
    sub.add_parser("status", help="All active graduation flows")

    # send-next
    sub.add_parser("send-next", help="Send next pending touchpoint for all active flows")

    # convert
    p_conv = sub.add_parser("convert", help="Record student accepting backend offer")
    p_conv.add_argument("--student", required=True, help="Student name")
    p_conv.add_argument(
        "--offer", required=True, choices=VALID_OFFER_TYPES, help="Offer type"
    )
    p_conv.add_argument(
        "--revenue", required=True, type=float, help="Monthly revenue amount"
    )

    # graduate
    p_grad = sub.add_parser("graduate", help="Mark student as graduated (no upsell)")
    p_grad.add_argument("--student", required=True, help="Student name")

    # backend-report
    sub.add_parser("backend-report", help="All backend subscriptions + MRR")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "check":
        pipeline = check_graduation_pipeline()
        if not pipeline:
            print("No students in the Day 60-100 graduation window.")
            return

        print(f"\n{'='*70}")
        print(f"  GRADUATION PIPELINE — {len(pipeline)} student(s)")
        print(f"{'='*70}\n")

        for p in pipeline:
            status_icon = {
                "not_started": "[ ]",
                "active": "[~]",
                "converted": "[$$]",
                "graduated": "[OK]",
            }.get(p["flow_status"], "[?]")

            print(
                f"  {status_icon} {p['name']} (Tier {p['tier']}) — "
                f"Day {p['days_in_program']}, "
                f"Milestone: {p['current_milestone']}, "
                f"Health: {p['health_score']}"
            )
            if p["graduation_flow"]:
                print(f"      Flow: {p['flow_status']} (started {p['graduation_flow']['started_at'][:10]})")
            else:
                print("      Flow: Not started")
            print()

    elif args.command == "start":
        result = start_graduation_flow(args.student)
        print(f"\nGraduation flow started for {result['student']}:")
        print(f"  Flow ID: {result['flow_id']}")
        print(f"  Touchpoints created: {result['touchpoints_created']}")
        print(f"  Started at: {result['started_at']}")

    elif args.command == "status":
        flows = get_active_flows()
        if not flows:
            print("No active graduation flows.")
            return

        print(f"\n{'='*70}")
        print(f"  ACTIVE GRADUATION FLOWS — {len(flows)}")
        print(f"{'='*70}\n")

        for f in flows:
            print(f"  {f['student']} (Tier {f['tier']}) — Day {f['days_in_program']}")
            print(f"    Health: {f['health_score']} | Sent: {f['touchpoints_sent']} | Pending: {f['touchpoints_pending']}")
            if f["next_touchpoint"]:
                print(f"    Next: Day {f['next_touchpoint']['day']} ({f['next_touchpoint']['type']})")
            else:
                print("    Next: All touchpoints sent")
            print()

    elif args.command == "send-next":
        results = send_next_touchpoints()
        if not results:
            print("No active flows to process.")
            return

        print(f"\n{'='*70}")
        print(f"  TOUCHPOINT SEND RESULTS")
        print(f"{'='*70}\n")

        for r in results:
            if r["action"] == "sent":
                discord_tag = "via Discord" if r.get("discord_sent") else "printed only"
                print(f"  [SENT] {r['student']} — Day {r['day']} {r['touchpoint_type']} ({discord_tag})")
            else:
                print(f"  [SKIP] {r['student']} — {r['reason']}")

    elif args.command == "convert":
        result = convert_student(args.student, args.offer, args.revenue)
        print(f"\nStudent converted to backend:")
        print(f"  Student: {result['student']}")
        print(f"  Offer: {result['offer_type']}")
        print(f"  Monthly: ${result['monthly_revenue']:.2f}")
        print(f"  Start: {result['subscription_start']}")

    elif args.command == "graduate":
        result = graduate_student(args.student)
        print(f"\nStudent graduated:")
        print(f"  Student: {result['student']}")
        print(f"  Status: {result['status']}")
        print(f"  Completed: {result['completed_at'][:10]}")

    elif args.command == "backend-report":
        report = backend_report()
        print(f"\n{'='*70}")
        print(f"  BACKEND SUBSCRIPTION REPORT")
        print(f"{'='*70}\n")
        print(f"  Total MRR:       ${report['total_mrr']:,.2f}")
        print(f"  Active Subs:     {report['active_subscriptions']}")
        print(f"  Cancelled:       {report['cancelled_subscriptions']}")
        print(f"  Paused:          {report['paused_subscriptions']}")
        print(f"  Conversion Rate: {report['conversion_rate_pct']}%")
        print(f"  Total Graduated: {report['total_graduated']}")
        print(f"  Total Converted: {report['total_converted']}")

        if report["mrr_by_offer"]:
            print(f"\n  MRR by Offer Type:")
            for offer, mrr in report["mrr_by_offer"].items():
                print(f"    {offer}: ${mrr:,.2f}")

        if report["subscriptions"]:
            print(f"\n  Active Subscriptions:")
            for s in report["subscriptions"]:
                print(
                    f"    {s['student_name']} (Tier {s['tier']}) — "
                    f"{s['offer_type']} @ ${s['monthly_revenue']:.2f}/mo "
                    f"(since {s['start_date']})"
                )


if __name__ == "__main__":
    main()
