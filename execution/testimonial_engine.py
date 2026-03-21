#!/usr/bin/env python3
"""
Script: testimonial_engine.py
Purpose: Full testimonial lifecycle management for Amazon FBA coaching.
         Request, collect, approve, publish testimonials. Manage referral codes.
         Auto-request testimonials when students hit qualifying milestones.
Inputs:  CLI subcommands
Outputs: Testimonial status reports, Discord DMs, referral dashboards

CLI:
    python execution/testimonial_engine.py request --student "Gabe" --type screenshot --milestone first_sale
    python execution/testimonial_engine.py collect --student "Gabe" --type screenshot --content "First sale screenshot" --media-url "https://..."
    python execution/testimonial_engine.py approve --id 1
    python execution/testimonial_engine.py publish --id 1 --channels "website,ads,discord"
    python execution/testimonial_engine.py status
    python execution/testimonial_engine.py auto-request [--send]
    python execution/testimonial_engine.py pipeline
    python execution/testimonial_engine.py referral-create --student "Gabe"
    python execution/testimonial_engine.py referral-status
    python execution/testimonial_engine.py referral-convert --code "REF-GABE-1234" --name "Sarah" --revenue 5000
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import string
import sys
from datetime import datetime
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Optional: requests for Discord API
try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"

# ── Milestone Trigger Rules ───────────────────────────────────────────────────

MILESTONE_TRIGGERS = {
    "first_sale": {
        "type": "screenshot",
        "message": (
            "Congrats on your first sale! Screenshot that notification "
            "and share it -- you earned this moment!"
        ),
        "delay_hours": 1,
    },
    "listing_live": {
        "type": "screenshot",
        "message": (
            "Your listing is LIVE! Screenshot your listing page -- "
            "this is a milestone worth remembering!"
        ),
        "delay_hours": 2,
    },
    "profitable_month": {
        "type": "text",
        "message": (
            "You just hit a profitable month! Would you mind writing "
            "2-3 sentences about your experience? It helps other people "
            "who are where you were 90 days ago."
        ),
        "delay_hours": 24,
    },
    "10k_month": {
        "type": "video",
        "message": (
            "You hit $10K in a single month. That's incredible. Would you "
            "be open to recording a quick 60-second video about your journey? "
            "Here are 4 simple questions to answer:\n\n"
            "1. Where were you before the program?\n"
            "2. What specific results have you gotten?\n"
            "3. What would you tell someone considering joining?\n"
            "4. What surprised you most about the process?"
        ),
        "delay_hours": 48,
    },
}

VALID_TYPES = ["screenshot", "text", "video", "case_study"]
VALID_STATUSES = ["requested", "received", "approved", "published"]


# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Return a connection to the students DB."""
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def find_student(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    """Find a student by name (case-insensitive partial match)."""
    row = conn.execute(
        "SELECT * FROM students WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT * FROM students WHERE LOWER(name) LIKE LOWER(?)",
        (f"%{name}%",),
    ).fetchone()
    return row


# ── Discord Integration ───────────────────────────────────────────────────────

def send_discord_dm(user_id: str, content: str) -> bool:
    """Send a DM to a Discord user via REST API. Returns True on success."""
    if not HAS_REQUESTS:
        print("  WARNING: requests library not installed, cannot send Discord DM")
        return False

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("  WARNING: DISCORD_BOT_TOKEN not set, cannot send Discord DM")
        return False

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }

    # Create DM channel
    try:
        resp = _requests.post(
            "https://discord.com/api/v10/users/@me/channels",
            headers=headers,
            json={"recipient_id": user_id},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  WARNING: Failed to create DM channel (HTTP {resp.status_code})")
            return False

        dm_channel_id = resp.json()["id"]

        # Send message
        resp = _requests.post(
            f"https://discord.com/api/v10/channels/{dm_channel_id}/messages",
            headers=headers,
            json={"content": content},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            print(f"  Discord DM sent to user {user_id}")
            return True
        else:
            print(f"  WARNING: Failed to send DM (HTTP {resp.status_code})")
            return False
    except Exception as e:
        print(f"  WARNING: Discord API error: {e}")
        return False


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_request(args: argparse.Namespace) -> None:
    """Create a testimonial request for a student."""
    conn = get_db()
    try:
        student = find_student(conn, args.student)
        if not student:
            print(f"ERROR: Student '{args.student}' not found")
            sys.exit(1)

        ttype = args.type
        if ttype not in VALID_TYPES:
            print(f"ERROR: Invalid type '{ttype}'. Valid: {VALID_TYPES}")
            sys.exit(1)

        milestone = args.milestone or student["current_milestone"]
        now = datetime.utcnow().isoformat()

        # Check for existing request
        existing = conn.execute(
            "SELECT id FROM testimonials WHERE student_id = ? AND milestone = ? AND status != 'published'",
            (student["id"], milestone),
        ).fetchone()
        if existing:
            print(f"NOTE: Testimonial already exists for {student['name']} / {milestone} (id={existing['id']})")
            return

        # Get message from triggers or use default
        trigger = MILESTONE_TRIGGERS.get(milestone)
        if trigger:
            message = trigger["message"]
        else:
            message = (
                f"Hey {student['name']}! You've hit the '{milestone}' milestone. "
                f"Would you mind sharing a {ttype} about your experience?"
            )

        conn.execute(
            "INSERT INTO testimonials (student_id, type, milestone, status, requested_at) "
            "VALUES (?, ?, ?, 'requested', ?)",
            (student["id"], ttype, milestone, now),
        )
        conn.commit()

        print(f"Testimonial request created for {student['name']}")
        print(f"  Type: {ttype}")
        print(f"  Milestone: {milestone}")
        print(f"  Message to send:")
        print(f"  ---")
        print(f"  {message}")
        print(f"  ---")

        # Send Discord DM if student has discord_user_id
        if student["discord_user_id"] and args.send:
            send_discord_dm(student["discord_user_id"], message)
    finally:
        conn.close()


def cmd_collect(args: argparse.Namespace) -> None:
    """Mark a testimonial as received with content."""
    conn = get_db()
    try:
        student = find_student(conn, args.student)
        if not student:
            print(f"ERROR: Student '{args.student}' not found")
            sys.exit(1)

        # Find the most recent requested testimonial for this student+type
        row = conn.execute(
            "SELECT id FROM testimonials WHERE student_id = ? AND type = ? AND status = 'requested' "
            "ORDER BY requested_at DESC LIMIT 1",
            (student["id"], args.type),
        ).fetchone()

        now = datetime.utcnow().isoformat()

        if row:
            conn.execute(
                "UPDATE testimonials SET content = ?, media_url = ?, status = 'received', "
                "received_at = ? WHERE id = ?",
                (args.content, args.media_url, now, row["id"]),
            )
            tid = row["id"]
        else:
            # No pending request -- create a new entry directly as received
            conn.execute(
                "INSERT INTO testimonials (student_id, type, content, media_url, status, "
                "requested_at, received_at) VALUES (?, ?, ?, ?, 'received', ?, ?)",
                (student["id"], args.type, args.content, args.media_url, now, now),
            )
            tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.commit()
        print(f"Testimonial collected for {student['name']} (id={tid})")
        print(f"  Type: {args.type}")
        print(f"  Status: received (awaiting approval)")
    finally:
        conn.close()


def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a received testimonial."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT t.*, s.name FROM testimonials t JOIN students s ON t.student_id = s.id "
            "WHERE t.id = ?",
            (args.id,),
        ).fetchone()
        if not row:
            print(f"ERROR: Testimonial id={args.id} not found")
            sys.exit(1)
        if row["status"] not in ("received", "requested"):
            print(f"NOTE: Testimonial is already '{row['status']}'")
            return

        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE testimonials SET status = 'approved', approved_at = ? WHERE id = ?",
            (now, args.id),
        )
        conn.commit()
        print(f"Testimonial id={args.id} approved ({row['name']} / {row['type']})")
    finally:
        conn.close()


def cmd_publish(args: argparse.Namespace) -> None:
    """Publish an approved testimonial to specified channels."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT t.*, s.name FROM testimonials t JOIN students s ON t.student_id = s.id "
            "WHERE t.id = ?",
            (args.id,),
        ).fetchone()
        if not row:
            print(f"ERROR: Testimonial id={args.id} not found")
            sys.exit(1)
        if row["status"] not in ("approved", "received"):
            if row["status"] == "published":
                print(f"NOTE: Testimonial already published to: {row['published_channels']}")
                return
            print(f"ERROR: Testimonial must be approved first (current: {row['status']})")
            sys.exit(1)

        channels = args.channels  # e.g. "website,ads,discord"
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE testimonials SET status = 'published', published_channels = ?, "
            "approved_at = COALESCE(approved_at, ?) WHERE id = ?",
            (channels, now, args.id),
        )
        conn.commit()
        print(f"Testimonial id={args.id} published ({row['name']})")
        print(f"  Channels: {channels}")
    finally:
        conn.close()


def cmd_status(args: argparse.Namespace) -> None:
    """Show all testimonials grouped by status."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT t.id, s.name, t.type, t.milestone, t.status, t.requested_at, "
            "t.received_at, t.approved_at, t.published_channels, t.content "
            "FROM testimonials t JOIN students s ON t.student_id = s.id "
            "ORDER BY CASE t.status "
            "  WHEN 'requested' THEN 1 WHEN 'received' THEN 2 "
            "  WHEN 'approved' THEN 3 WHEN 'published' THEN 4 END, "
            "t.requested_at DESC"
        ).fetchall()

        if not rows:
            print("No testimonials found.")
            return

        current_status = None
        for r in rows:
            if r["status"] != current_status:
                current_status = r["status"]
                print(f"\n{'=' * 60}")
                print(f"  {current_status.upper()} ({sum(1 for x in rows if x['status'] == current_status)})")
                print(f"{'=' * 60}")

            print(f"  [{r['id']}] {r['name']} | {r['type']} | {r['milestone'] or '-'}")
            print(f"       Requested: {r['requested_at'][:10] if r['requested_at'] else '-'}")
            if r["received_at"]:
                print(f"       Received:  {r['received_at'][:10]}")
            if r["approved_at"]:
                print(f"       Approved:  {r['approved_at'][:10]}")
            if r["published_channels"]:
                print(f"       Published: {r['published_channels']}")
            if r["content"]:
                preview = r["content"][:80] + ("..." if len(r["content"]) > 80 else "")
                print(f"       Content:   {preview}")
        print()
    finally:
        conn.close()


def cmd_auto_request(args: argparse.Namespace) -> None:
    """Scan students and auto-request testimonials for qualifying milestones."""
    conn = get_db()
    try:
        students = conn.execute(
            "SELECT * FROM students WHERE status = 'active'"
        ).fetchall()

        if not students:
            print("No active students found.")
            return

        requested_count = 0
        sent_count = 0

        for student in students:
            milestone = student["current_milestone"]
            if milestone not in MILESTONE_TRIGGERS:
                continue

            trigger = MILESTONE_TRIGGERS[milestone]

            # Check if testimonial already requested for this student+milestone
            existing = conn.execute(
                "SELECT id FROM testimonials WHERE student_id = ? AND milestone = ?",
                (student["id"], milestone),
            ).fetchone()
            if existing:
                continue

            now = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO testimonials (student_id, type, milestone, status, requested_at) "
                "VALUES (?, ?, ?, 'requested', ?)",
                (student["id"], trigger["type"], milestone, now),
            )
            requested_count += 1

            message = trigger["message"]
            print(f"  REQUEST: {student['name']} -- {milestone} ({trigger['type']})")

            # Send Discord DM if --send and student has discord_user_id
            if args.send and student["discord_user_id"]:
                if send_discord_dm(student["discord_user_id"], message):
                    sent_count += 1
                else:
                    print(f"    (DM failed, request still saved)")
            elif args.send and not student["discord_user_id"]:
                print(f"    (No discord_user_id for {student['name']}, skipping DM)")

        conn.commit()
        print(f"\nAuto-request complete: {requested_count} new requests, {sent_count} DMs sent")
    finally:
        conn.close()


def cmd_pipeline(args: argparse.Namespace) -> None:
    """Full pipeline view of the testimonial funnel."""
    conn = get_db()
    try:
        # Counts by status
        counts = {}
        for status in VALID_STATUSES:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM testimonials WHERE status = ?", (status,)
            ).fetchone()
            counts[status] = row["c"]

        total = sum(counts.values())
        print("=" * 60)
        print("  TESTIMONIAL PIPELINE")
        print("=" * 60)
        print(f"  Total: {total}")
        print()
        for status in VALID_STATUSES:
            bar_len = int((counts[status] / max(total, 1)) * 30)
            bar = "#" * bar_len + "." * (30 - bar_len)
            print(f"  {status:<12} [{bar}] {counts[status]}")

        # Conversion rates
        print()
        if counts["requested"] + counts["received"] + counts["approved"] + counts["published"] > 0:
            collected = counts["received"] + counts["approved"] + counts["published"]
            approved = counts["approved"] + counts["published"]
            published = counts["published"]
            total_requested = total

            print("  Conversion rates:")
            print(f"    Requested -> Received:  {collected}/{total_requested} ({collected * 100 // max(total_requested, 1)}%)")
            print(f"    Received  -> Approved:  {approved}/{max(collected, 1)} ({approved * 100 // max(collected, 1)}%)")
            print(f"    Approved  -> Published: {published}/{max(approved, 1)} ({published * 100 // max(approved, 1)}%)")

        # By type
        print()
        print("  By type:")
        for ttype in VALID_TYPES:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM testimonials WHERE type = ?", (ttype,)
            ).fetchone()
            if row["c"] > 0:
                print(f"    {ttype:<15} {row['c']}")

        # Pending actions
        print()
        pending_collect = conn.execute(
            "SELECT t.id, s.name, t.type, t.milestone, t.requested_at "
            "FROM testimonials t JOIN students s ON t.student_id = s.id "
            "WHERE t.status = 'requested' ORDER BY t.requested_at"
        ).fetchall()
        if pending_collect:
            print(f"  Awaiting collection ({len(pending_collect)}):")
            for r in pending_collect:
                days_ago = (datetime.utcnow() - datetime.fromisoformat(r["requested_at"])).days
                print(f"    [{r['id']}] {r['name']} -- {r['type']} ({r['milestone']}) -- {days_ago}d ago")

        pending_approve = conn.execute(
            "SELECT t.id, s.name, t.type, t.milestone "
            "FROM testimonials t JOIN students s ON t.student_id = s.id "
            "WHERE t.status = 'received' ORDER BY t.received_at"
        ).fetchall()
        if pending_approve:
            print(f"\n  Awaiting approval ({len(pending_approve)}):")
            for r in pending_approve:
                print(f"    [{r['id']}] {r['name']} -- {r['type']} ({r['milestone']})")

        print()
    finally:
        conn.close()


# ── Referral Commands ─────────────────────────────────────────────────────────

def _generate_referral_code(name: str) -> str:
    """Generate a unique referral code like REF-GABE-1234."""
    suffix = "".join(random.choices(string.digits, k=4))
    clean_name = "".join(c for c in name.upper() if c.isalpha())[:8]
    return f"REF-{clean_name}-{suffix}"


def cmd_referral_create(args: argparse.Namespace) -> None:
    """Generate a referral code for a student."""
    conn = get_db()
    try:
        student = find_student(conn, args.student)
        if not student:
            print(f"ERROR: Student '{args.student}' not found")
            sys.exit(1)

        # Check if student already has an active referral code
        existing = conn.execute(
            "SELECT referral_code FROM referrals WHERE referrer_student_id = ? AND status = 'referred' LIMIT 1",
            (student["id"],),
        ).fetchone()

        # Generate unique code
        for _ in range(10):
            code = _generate_referral_code(student["name"])
            conflict = conn.execute(
                "SELECT id FROM referrals WHERE referral_code = ?", (code,)
            ).fetchone()
            if not conflict:
                break
        else:
            print("ERROR: Could not generate unique referral code after 10 attempts")
            sys.exit(1)

        now = datetime.utcnow().isoformat()
        rate = args.rate if hasattr(args, "rate") and args.rate else 0.10

        # We create a referral entry with placeholder referred info
        # The actual referred person is filled in on conversion
        conn.execute(
            "INSERT INTO referrals (referrer_student_id, referred_name, referral_code, "
            "commission_rate, status, created_at) VALUES (?, ?, ?, ?, 'referred', ?)",
            (student["id"], "(pending)", code, rate, now),
        )
        conn.commit()

        print(f"Referral code created for {student['name']}")
        print(f"  Code: {code}")
        print(f"  Commission rate: {rate * 100:.0f}%")
        if existing:
            print(f"  NOTE: Student also has existing code: {existing['referral_code']}")
    finally:
        conn.close()


def cmd_referral_status(args: argparse.Namespace) -> None:
    """Show all referrals dashboard."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT r.*, s.name as referrer_name FROM referrals r "
            "JOIN students s ON r.referrer_student_id = s.id "
            "ORDER BY r.created_at DESC"
        ).fetchall()

        if not rows:
            print("No referrals found.")
            return

        total_commission = sum(r["commission_amount"] for r in rows)
        paid = sum(r["commission_amount"] for r in rows if r["commission_paid"])
        unpaid = total_commission - paid
        converted = sum(1 for r in rows if r["status"] == "enrolled")

        print("=" * 60)
        print("  REFERRAL DASHBOARD")
        print("=" * 60)
        print(f"  Total referrals: {len(rows)}")
        print(f"  Converted:       {converted}")
        print(f"  Commission total: ${total_commission:,.2f}")
        print(f"  Paid:             ${paid:,.2f}")
        print(f"  Unpaid:           ${unpaid:,.2f}")
        print()

        for r in rows:
            status_icon = "+" if r["status"] == "enrolled" else "-"
            print(f"  [{status_icon}] {r['referral_code']} | Referrer: {r['referrer_name']}")
            print(f"       Referred: {r['referred_name']}")
            print(f"       Status: {r['status']} | Commission: ${r['commission_amount']:,.2f}"
                  f"{' (paid)' if r['commission_paid'] else ''}")
            if r["enrolled_at"]:
                print(f"       Enrolled: {r['enrolled_at'][:10]}")
        print()
    finally:
        conn.close()


def cmd_referral_convert(args: argparse.Namespace) -> None:
    """Convert a referral -- someone enrolled using a referral code."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT r.*, s.name as referrer_name FROM referrals r "
            "JOIN students s ON r.referrer_student_id = s.id "
            "WHERE r.referral_code = ?",
            (args.code,),
        ).fetchone()

        if not row:
            print(f"ERROR: Referral code '{args.code}' not found")
            sys.exit(1)

        if row["status"] == "enrolled":
            print(f"NOTE: Referral already converted for {row['referred_name']}")
            return

        now = datetime.utcnow().isoformat()
        commission = args.revenue * row["commission_rate"]

        conn.execute(
            "UPDATE referrals SET referred_name = ?, status = 'enrolled', "
            "commission_amount = ?, enrolled_at = ? WHERE id = ?",
            (args.name, commission, now, row["id"]),
        )
        if args.email:
            conn.execute(
                "UPDATE referrals SET referred_email = ? WHERE id = ?",
                (args.email, row["id"]),
            )
        conn.commit()

        print(f"Referral converted!")
        print(f"  Code: {args.code}")
        print(f"  Referrer: {row['referrer_name']}")
        print(f"  New student: {args.name}")
        print(f"  Revenue: ${args.revenue:,.2f}")
        print(f"  Commission ({row['commission_rate'] * 100:.0f}%): ${commission:,.2f}")
    finally:
        conn.close()


# ── CLI Setup ─────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Testimonial lifecycle engine + referral management"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # request
    p = sub.add_parser("request", help="Create a testimonial request")
    p.add_argument("--student", required=True, help="Student name")
    p.add_argument("--type", required=True, choices=VALID_TYPES, help="Testimonial type")
    p.add_argument("--milestone", help="Milestone (defaults to current)")
    p.add_argument("--send", action="store_true", help="Send Discord DM")

    # collect
    p = sub.add_parser("collect", help="Mark a testimonial as received")
    p.add_argument("--student", required=True, help="Student name")
    p.add_argument("--type", required=True, choices=VALID_TYPES, help="Testimonial type")
    p.add_argument("--content", required=True, help="Testimonial text content")
    p.add_argument("--media-url", help="URL to screenshot/video")

    # approve
    p = sub.add_parser("approve", help="Approve a received testimonial")
    p.add_argument("--id", required=True, type=int, help="Testimonial ID")

    # publish
    p = sub.add_parser("publish", help="Publish a testimonial to channels")
    p.add_argument("--id", required=True, type=int, help="Testimonial ID")
    p.add_argument("--channels", required=True, help="Comma-separated channels (website,ads,discord)")

    # status
    sub.add_parser("status", help="Show all testimonials by status")

    # auto-request
    p = sub.add_parser("auto-request", help="Scan milestones and auto-request testimonials")
    p.add_argument("--send", action="store_true", help="Send Discord DMs to qualifying students")

    # pipeline
    sub.add_parser("pipeline", help="Full testimonial pipeline view")

    # referral-create
    p = sub.add_parser("referral-create", help="Generate a referral code for a student")
    p.add_argument("--student", required=True, help="Student name")
    p.add_argument("--rate", type=float, default=0.10, help="Commission rate (default 0.10)")

    # referral-status
    sub.add_parser("referral-status", help="Show all referrals dashboard")

    # referral-convert
    p = sub.add_parser("referral-convert", help="Convert a referral (someone enrolled)")
    p.add_argument("--code", required=True, help="Referral code (e.g. REF-GABE-1234)")
    p.add_argument("--name", required=True, help="New student name")
    p.add_argument("--email", help="New student email")
    p.add_argument("--revenue", required=True, type=float, help="Enrollment revenue amount")

    return parser


COMMAND_MAP = {
    "request": cmd_request,
    "collect": cmd_collect,
    "approve": cmd_approve,
    "publish": cmd_publish,
    "status": cmd_status,
    "auto-request": cmd_auto_request,
    "pipeline": cmd_pipeline,
    "referral-create": cmd_referral_create,
    "referral-status": cmd_referral_status,
    "referral-convert": cmd_referral_convert,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handler = COMMAND_MAP.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
