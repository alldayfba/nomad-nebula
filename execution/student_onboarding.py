#!/usr/bin/env python3
"""
Script: student_onboarding.py
Purpose: Automate the full onboarding flow when a new Amazon FBA coaching student
         enrolls. Creates Discord channel, assigns role, sends intro message,
         registers in student tracker DB, creates first milestones, and logs
         the onboarding as an engagement signal.
Inputs:  CLI subcommands
Outputs: Discord channel + role, DB registration, engagement log

CLI:
    python execution/student_onboarding.py onboard --name "John Smith" --discord-id 123456789 --tier A --capital 10000 [--email john@email.com]
    python execution/student_onboarding.py onboard --name "Jane Doe" --discord-id 987654321 --tier B
    python execution/student_onboarding.py status                  # Show recent onboardings
    python execution/student_onboarding.py verify --name "John"    # Verify channel + role + DB entry exist
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

# Import milestone definitions from student_tracker
sys.path.insert(0, str(Path(__file__).parent))
from student_tracker import MILESTONE_ORDER

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"

# ── Discord Constants ────────────────────────────────────────────────────────

GUILD_ID = "1185214150222286849"
STUDENT_ROLE_ID = "1245057306987855964"
INNER_CIRCLE_CATEGORY_ID = None  # Auto-detected from existing channels

# Channel references for the welcome message
CHANNELS = {
    "seller_central_course": "1374640092886470707",
    "selleramp_course": "1374642072866258995",
    "introductions": "1250966307021656115",
    "group_calls": "1336369248330584196",
    "all_courses": "1194999099162902559",
}

WELCOME_MESSAGE = """**Welcome to 24/7 Profits, {name}!**

You're officially in. This is your private 1:1 channel — use it to ask questions, share progress, and get direct support.

**Your 90-Day Roadmap starts NOW. Here's what to do first:**

**Week 1 Checklist:**
1. Watch the **Seller Central Course** → <#{seller_central_course}>
2. Watch the **SellerAmp Course** → <#{selleramp_course}>
3. Set up your Amazon Seller Account (if you haven't)
4. Install SellerAmp SAS + Keepa browser extensions
5. Sign up for Rakuten/TopCashBack for cashback on purchases
6. Introduce yourself in <#{introductions}>

**Group Calls:** Tuesday + Thursday — check <#{group_calls}> for times
**All Courses:** <#{all_courses}>
**Questions:** Drop them right here in this channel anytime

**Your first goal:** Find your first product within 2 weeks. We'll help you every step of the way.

Let's get it!"""


# ── Database Connection ──────────────────────────────────────────────────────

def get_db():
    """Connect to the shared coaching DB."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Discord Helpers ──────────────────────────────────────────────────────────

def _get_headers():
    """Return Discord bot auth headers."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        return None
    return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def _detect_category_id(headers):
    """Find the Inner Circle category ID from existing student channels."""
    global INNER_CIRCLE_CATEGORY_ID
    if INNER_CIRCLE_CATEGORY_ID:
        return INNER_CIRCLE_CATEGORY_ID

    resp = requests.get(
        f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels",
        headers=headers,
    )
    if resp.status_code != 200:
        print(f"[ERROR] Failed to list channels: {resp.status_code}")
        return None

    channels = resp.json()
    for ch in channels:
        # Look for existing student channels (prefixed with graduation cap emoji)
        name = ch.get("name", "")
        if name.startswith("\U0001f393") and ch.get("parent_id"):
            INNER_CIRCLE_CATEGORY_ID = ch["parent_id"]
            return INNER_CIRCLE_CATEGORY_ID

    # Fallback: look for a category named with "inner circle" or "students"
    for ch in channels:
        if ch.get("type") == 4:  # category channel
            lower_name = ch.get("name", "").lower()
            if "inner circle" in lower_name or "student" in lower_name:
                INNER_CIRCLE_CATEGORY_ID = ch["id"]
                return INNER_CIRCLE_CATEGORY_ID

    return None


def create_student_channel(student_name, discord_user_id):
    """Create a private channel for a new student in the Inner Circle category."""
    if not requests:
        print("[WARN] requests not installed, skipping Discord channel creation")
        return None

    headers = _get_headers()
    if not headers:
        print("[WARN] DISCORD_BOT_TOKEN not set, skipping Discord channel creation")
        return None

    category_id = _detect_category_id(headers)

    channel_name = f"\U0001f393\u2503{student_name.lower().replace(' ', '-')}"

    payload = {
        "name": channel_name,
        "type": 0,  # text channel
        "permission_overwrites": [
            # @everyone cannot see
            {
                "id": GUILD_ID,
                "type": 0,
                "deny": str(1 << 10),  # VIEW_CHANNEL denied
            },
            # Student can see + send
            {
                "id": str(discord_user_id),
                "type": 1,
                "allow": str((1 << 10) | (1 << 11)),  # VIEW + SEND
            },
        ],
    }

    if category_id:
        payload["parent_id"] = category_id

    resp = requests.post(
        f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels",
        headers=headers,
        json=payload,
    )

    if resp.status_code in (200, 201):
        channel = resp.json()
        print(f"  [OK] Created channel #{channel['name']} (ID: {channel['id']})")
        return channel
    else:
        print(f"[ERROR] Failed to create channel: {resp.status_code} {resp.text}")
        return None


def assign_student_role(discord_user_id):
    """Assign the 24/7 Profits Student role to a Discord user."""
    if not requests:
        print("[WARN] requests not installed, skipping role assignment")
        return False

    headers = _get_headers()
    if not headers:
        print("[WARN] DISCORD_BOT_TOKEN not set, skipping role assignment")
        return False

    resp = requests.put(
        f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{discord_user_id}/roles/{STUDENT_ROLE_ID}",
        headers=headers,
    )

    if resp.status_code == 204:
        print(f"  [OK] Assigned Student role to user {discord_user_id}")
        return True
    else:
        print(f"[ERROR] Failed to assign role: {resp.status_code} {resp.text}")
        return False


def send_welcome_message(channel_id, student_name):
    """Send the intro message in the student's new channel."""
    if not requests:
        print("[WARN] requests not installed, skipping welcome message")
        return None

    headers = _get_headers()
    if not headers:
        print("[WARN] DISCORD_BOT_TOKEN not set, skipping welcome message")
        return None

    message = WELCOME_MESSAGE.format(name=student_name, **CHANNELS)

    resp = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers=headers,
        json={"content": message},
    )

    if resp.status_code in (200, 201):
        print(f"  [OK] Welcome message sent in channel {channel_id}")
        return resp.json().get("id")
    else:
        print(f"[ERROR] Failed to send welcome: {resp.status_code} {resp.text}")
        return None


# ── Core Functions ───────────────────────────────────────────────────────────

def onboard_student(name, discord_id, tier, capital=None, email=None):
    """
    Full onboarding flow:
    1. Create Discord channel
    2. Assign student role
    3. Send welcome message
    4. Register in student tracker DB
    5. Create initial milestones
    6. Log engagement signal
    """
    if tier not in ("A", "B", "C"):
        raise ValueError(f"Invalid tier '{tier}'. Must be A, B, or C.")

    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    target_date = (now + timedelta(days=90)).strftime("%Y-%m-%d")

    results = {
        "name": name,
        "discord_id": discord_id,
        "tier": tier,
        "steps": {},
    }

    # Step 1: Create Discord channel
    print(f"\n[1/6] Creating Discord channel for {name}...")
    channel = create_student_channel(name, discord_id)
    channel_id = channel["id"] if channel else None
    results["steps"]["channel_created"] = channel_id is not None
    results["channel_id"] = channel_id

    # Step 2: Assign student role
    print(f"[2/6] Assigning student role...")
    role_ok = assign_student_role(discord_id)
    results["steps"]["role_assigned"] = role_ok

    # Step 3: Send welcome message
    print(f"[3/6] Sending welcome message...")
    if channel_id:
        msg_id = send_welcome_message(channel_id, name)
        results["steps"]["welcome_sent"] = msg_id is not None
    else:
        print("  [SKIP] No channel created, skipping welcome message")
        results["steps"]["welcome_sent"] = False

    # Step 4: Register in student tracker DB
    print(f"[4/6] Registering in student tracker...")
    conn = get_db()
    try:
        # Check if student already exists
        existing = conn.execute(
            "SELECT * FROM students WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()

        if existing:
            print(f"  [WARN] Student '{name}' already exists (ID: {existing['id']}). Updating Discord info.")
            conn.execute(
                "UPDATE students SET discord_user_id = ?, discord_channel_id = ? WHERE id = ?",
                (str(discord_id), channel_id, existing["id"]),
            )
            student_id = existing["id"]
            results["steps"]["db_registered"] = True
            results["db_status"] = "updated"
        else:
            conn.execute(
                """INSERT INTO students
                   (name, email, tier, capital, start_date, target_date, status,
                    current_milestone, health_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', 'enrolled', 100, ?)""",
                (name, email, tier, capital, today, target_date, now.isoformat()),
            )
            student = conn.execute(
                "SELECT id FROM students WHERE name = ?", (name,)
            ).fetchone()
            student_id = student["id"]

            # Set Discord fields (columns added by student_health_monitor)
            try:
                conn.execute(
                    "UPDATE students SET discord_user_id = ?, discord_channel_id = ? WHERE id = ?",
                    (str(discord_id), channel_id, student_id),
                )
            except sqlite3.OperationalError:
                pass  # discord columns may not exist yet

            results["steps"]["db_registered"] = True
            results["db_status"] = "created"

        print(f"  [OK] Student registered (ID: {student_id})")

        # Step 5: Create initial milestones
        print(f"[5/6] Creating milestones...")
        if not existing:
            # enrolled milestone (completed)
            conn.execute(
                """INSERT INTO milestones
                   (student_id, milestone, started_date, completed_date,
                    days_on_milestone, status)
                   VALUES (?, 'enrolled', ?, ?, 0, 'completed')""",
                (student_id, today, today),
            )
            # niche_selected milestone (in_progress)
            next_ms = MILESTONE_ORDER[1]
            conn.execute(
                """INSERT INTO milestones
                   (student_id, milestone, started_date, status)
                   VALUES (?, ?, ?, 'in_progress')""",
                (student_id, next_ms, today),
            )
            conn.execute(
                "UPDATE students SET current_milestone = ? WHERE id = ?",
                (next_ms, student_id),
            )
            print(f"  [OK] Created 'enrolled' (completed) + '{next_ms}' (in_progress)")
            results["steps"]["milestones_created"] = True
        else:
            print(f"  [SKIP] Student already existed, milestones unchanged")
            results["steps"]["milestones_created"] = False

        # Step 6: Log engagement signal
        print(f"[6/6] Logging onboarding signal...")
        try:
            conn.execute(
                """INSERT INTO engagement_signals
                   (student_id, signal_type, channel, value, date, notes, created_at)
                   VALUES (?, 'onboarded', 'system', 'true', ?, ?, ?)""",
                (
                    student_id,
                    today,
                    f"Tier {tier}, capital={capital}, discord={discord_id}",
                    now.isoformat(),
                ),
            )
            print(f"  [OK] Engagement signal logged")
            results["steps"]["signal_logged"] = True
        except sqlite3.OperationalError:
            print(f"  [SKIP] engagement_signals table not available")
            results["steps"]["signal_logged"] = False

        conn.commit()
        results["student_id"] = student_id
        results["start_date"] = today
        results["target_date"] = target_date

    finally:
        conn.close()

    # Summary
    ok_count = sum(1 for v in results["steps"].values() if v)
    total_count = len(results["steps"])
    print(f"\n{'='*50}")
    print(f"  ONBOARDING COMPLETE: {ok_count}/{total_count} steps succeeded")
    print(f"  Student: {name} (Tier {tier})")
    print(f"  Discord: {discord_id}")
    if channel_id:
        print(f"  Channel: {channel_id}")
    print(f"  Program: {today} -> {target_date} (90 days)")
    print(f"{'='*50}\n")

    return results


def show_status():
    """Show recent onboardings (students added in the last 30 days)."""
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        students = conn.execute(
            """SELECT * FROM students
               WHERE created_at >= ?
               ORDER BY created_at DESC""",
            (cutoff,),
        ).fetchall()

        if not students:
            print("No students onboarded in the last 30 days.")
            return []

        print(f"\n{'='*70}")
        print(f"  RECENT ONBOARDINGS (last 30 days) — {len(students)} student(s)")
        print(f"{'='*70}\n")

        results = []
        for s in students:
            d = dict(s)
            discord_id = d.get("discord_user_id", "N/A")
            channel_id = d.get("discord_channel_id", "N/A")

            start = datetime.strptime(s["start_date"], "%Y-%m-%d")
            days_in = (datetime.utcnow() - start).days

            print(f"  {s['name']} (Tier {s['tier']}) — Day {days_in}")
            print(f"    Status: {s['status']} | Milestone: {s['current_milestone']} | Health: {s['health_score']}")
            print(f"    Discord User: {discord_id} | Channel: {channel_id}")
            print(f"    Start: {s['start_date']} | Target: {s['target_date']}")
            print()
            results.append(d)

        return results
    finally:
        conn.close()


def verify_student(student_name):
    """Verify that a student's onboarding is complete: DB entry, Discord channel, role."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE name LIKE ? COLLATE NOCASE",
            (f"%{student_name}%",),
        ).fetchone()

        if not student:
            print(f"[ERROR] No student found matching '{student_name}'")
            return None

        s = dict(student)
        discord_id = s.get("discord_user_id")
        channel_id = s.get("discord_channel_id")

        checks = {
            "db_entry": True,
            "has_discord_id": discord_id is not None and discord_id != "",
            "has_channel_id": channel_id is not None and channel_id != "",
            "has_milestones": False,
            "discord_role": None,
            "discord_channel_exists": None,
        }

        # Check milestones
        milestones = conn.execute(
            "SELECT * FROM milestones WHERE student_id = ?", (student["id"],)
        ).fetchall()
        checks["has_milestones"] = len(milestones) > 0

        # Check Discord role (if we have a discord_id and requests is available)
        if discord_id and requests:
            headers = _get_headers()
            if headers:
                resp = requests.get(
                    f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{discord_id}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    member = resp.json()
                    checks["discord_role"] = STUDENT_ROLE_ID in member.get("roles", [])
                else:
                    checks["discord_role"] = False

                # Check channel exists
                if channel_id:
                    resp = requests.get(
                        f"https://discord.com/api/v10/channels/{channel_id}",
                        headers=headers,
                    )
                    checks["discord_channel_exists"] = resp.status_code == 200

        print(f"\n{'='*50}")
        print(f"  VERIFICATION: {student['name']}")
        print(f"{'='*50}\n")

        for check, result in checks.items():
            if result is True:
                icon = "[OK]"
            elif result is False:
                icon = "[FAIL]"
            elif result is None:
                icon = "[SKIP]"
            else:
                icon = "[??]"
            print(f"  {icon} {check}")

        all_ok = all(v is True for v in checks.values() if v is not None)
        print(f"\n  Overall: {'PASS' if all_ok else 'ISSUES DETECTED'}\n")

        return {"student": dict(student), "checks": checks, "pass": all_ok}
    finally:
        conn.close()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Automate student onboarding for Amazon FBA coaching"
    )
    sub = parser.add_subparsers(dest="command")

    # onboard
    p_onboard = sub.add_parser("onboard", help="Onboard a new student")
    p_onboard.add_argument("--name", required=True, help="Student full name")
    p_onboard.add_argument(
        "--discord-id", required=True, type=int, help="Discord user ID"
    )
    p_onboard.add_argument(
        "--tier", required=True, choices=["A", "B", "C"], help="Student tier"
    )
    p_onboard.add_argument(
        "--capital", type=float, default=None, help="Starting capital"
    )
    p_onboard.add_argument("--email", default=None, help="Student email")

    # status
    sub.add_parser("status", help="Show recent onboardings")

    # verify
    p_verify = sub.add_parser("verify", help="Verify onboarding completeness")
    p_verify.add_argument("--name", required=True, help="Student name (partial match)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "onboard":
        onboard_student(
            name=args.name,
            discord_id=args.discord_id,
            tier=args.tier,
            capital=args.capital,
            email=args.email,
        )

    elif args.command == "status":
        show_status()

    elif args.command == "verify":
        verify_student(args.name)


if __name__ == "__main__":
    main()
