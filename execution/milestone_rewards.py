#!/usr/bin/env python3
"""
Script: milestone_rewards.py
Purpose: Auto-assigns Discord roles and posts celebrations when Amazon FBA
         students hit milestones. Tracks reward grants via engagement_signals
         to avoid duplicates. Supports manual grants and full roster scans.
Inputs:  CLI subcommands
Outputs: Discord DMs, role assignments, celebration channel posts

CLI:
    python execution/milestone_rewards.py check --student "Gabe"
    python execution/milestone_rewards.py grant --student "Gabe" --milestone first_sale
    python execution/milestone_rewards.py scan
    python execution/milestone_rewards.py roles
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
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
CELEBRATION_CHANNEL_ID = os.getenv("CELEBRATION_CHANNEL_ID", "")

MILESTONE_REWARDS = {
    "niche_selected": {
        "celebration": "**{name}** just locked in their niche! The journey begins.",
        "role_name": None,
        "unlock": "Access to #new-product-lead channel",
        "dm": (
            "Nice work picking your niche, {name}! You now have access to our "
            "weekly product drops. Check #new-product-lead every Monday for fresh finds."
        ),
    },
    "product_selected": {
        "celebration": "**{name}** found their first product! The hunt is over -- time to source!",
        "role_name": None,
        "unlock": None,
        "dm": (
            "Great pick, {name}! Next step: source it. Check the Supplier "
            "Outreach module if you haven't already."
        ),
    },
    "first_sale": {
        "celebration": (
            "**{name}** just made their FIRST SALE on Amazon! "
            "This is the moment everything changes. Congratulations!"
        ),
        "role_name": "First Sale",
        "unlock": "1:1 strategy call with Sabbo",
        "dm": (
            "CONGRATULATIONS {name}! Your first sale is HUGE. You've officially "
            "done what most people only dream about. As a reward, you've unlocked "
            "a 1:1 strategy call with Sabbo to plan your next moves. DM me to schedule!"
        ),
    },
    "profitable_month": {
        "celebration": (
            "**{name}** just hit a PROFITABLE MONTH! The system is working. "
            "This is what consistency looks like!"
        ),
        "role_name": "Profitable",
        "unlock": "Invitation to Continuation Inner Circle ($597/mo)",
        "dm": (
            "You're profitable, {name}! That puts you in the top 20% of Amazon "
            "sellers. You've unlocked an invitation to the Inner Circle -- ongoing "
            "support, advanced masterclasses, and monthly 1:1s. Want details?"
        ),
    },
    "10k_month": {
        "celebration": (
            "**{name}** just hit **$10,000 IN A SINGLE MONTH** on Amazon! "
            "This is ELITE. From Day 1 to five figures -- absolute legend!"
        ),
        "role_name": "$10K Club",
        "unlock": "Mastermind invitation + case study feature",
        "dm": (
            "YOU DID IT, {name}! $10K month! You've unlocked two things:\n\n"
            "1. **Mastermind invitation** -- Join our $10K+ operators circle "
            "(small group, advanced strategies)\n"
            "2. **Case study feature** -- We'd love to feature your story. Interested?\n\n"
            "Seriously proud of you. Let's keep scaling!"
        ),
    },
}

# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Connect to the shared coaching DB."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _has_been_rewarded(conn: sqlite3.Connection, student_id: int, milestone: str) -> bool:
    """Check if a reward was already granted (tracked via engagement_signals)."""
    row = conn.execute("""
        SELECT id FROM engagement_signals
        WHERE student_id = ? AND signal_type = 'reward_granted' AND value = ?
        LIMIT 1
    """, (student_id, milestone)).fetchone()
    return row is not None


def _record_reward(conn: sqlite3.Connection, student_id: int, milestone: str) -> None:
    """Record that a reward has been granted."""
    now = datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO engagement_signals
            (student_id, signal_type, channel, value, date, notes, created_at)
        VALUES (?, 'reward_granted', 'system', ?, ?, ?, ?)
    """, (student_id, milestone, now[:10], f"Milestone reward: {milestone}", now))


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


def send_channel_message(channel_id: str, content: str) -> tuple[bool, str | int]:
    """Post a message to a Discord channel."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        return False, "no_token"
    if requests is None:
        return False, "no_requests_lib"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    if len(content) > 2000:
        content = content[:1997] + "..."
    resp = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers=headers,
        json={"content": content},
    )
    return resp.status_code == 200, resp.status_code


def assign_discord_role(guild_id: str, user_id: str, role_name: str) -> bool:
    """Find a role by name and assign it to a user."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token or requests is None:
        print(f"    Could not assign role '{role_name}' -- no token or requests lib")
        return False
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}

    # Get all roles
    resp = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers)
    if resp.status_code != 200:
        print(f"    Could not fetch roles (HTTP {resp.status_code})")
        return False

    role_id = None
    for role in resp.json():
        if role["name"] == role_name:
            role_id = role["id"]
            break

    if not role_id:
        print(f"    Role '{role_name}' not found -- create it in Discord first")
        return False

    # Assign role
    resp = requests.put(
        f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
        headers=headers,
    )
    return resp.status_code == 204


# ── Core Logic ────────────────────────────────────────────────────────────────

def grant_reward(
    conn: sqlite3.Connection,
    student: sqlite3.Row,
    milestone: str,
    dry_run: bool = False,
) -> bool:
    """Grant a milestone reward to a student. Returns True if granted."""
    reward = MILESTONE_REWARDS.get(milestone)
    if not reward:
        print(f"  Unknown milestone: {milestone}")
        return False

    if _has_been_rewarded(conn, student["id"], milestone):
        print(f"  {student['name']}: Already rewarded for {milestone}")
        return False

    first_name = student["name"].split()[0]
    print(f"\n  Granting '{milestone}' reward to {student['name']}:")

    if dry_run:
        print(f"    [DRY RUN] DM: {reward['dm'].format(name=first_name)[:80]}...")
        if reward["role_name"]:
            print(f"    [DRY RUN] Role: {reward['role_name']}")
        if reward["celebration"]:
            print(f"    [DRY RUN] Celebration: {reward['celebration'].format(name=student['name'])[:80]}...")
        return True

    # 1. Send DM
    if student["discord_user_id"]:
        ok, code = send_dm(student["discord_user_id"], reward["dm"].format(name=first_name))
        print(f"    DM: {'sent' if ok else f'failed ({code})'}")
        time.sleep(1)
    else:
        print(f"    DM: skipped (no discord_user_id)")

    # 2. Assign role
    if reward["role_name"] and student["discord_user_id"]:
        role_ok = assign_discord_role(GUILD_ID, student["discord_user_id"], reward["role_name"])
        print(f"    Role '{reward['role_name']}': {'assigned' if role_ok else 'failed'}")
        time.sleep(1)

    # 3. Post celebration
    channel = CELEBRATION_CHANNEL_ID or (student["discord_channel_id"] if student["discord_channel_id"] else "")
    if channel and reward["celebration"]:
        celebration_msg = reward["celebration"].format(name=student["name"])
        ok, code = send_channel_message(channel, celebration_msg)
        print(f"    Celebration: {'posted' if ok else f'failed ({code})'}")

    # 4. Log unlock
    if reward["unlock"]:
        print(f"    Unlock: {reward['unlock']}")

    # 5. Record in DB
    _record_reward(conn, student["id"], milestone)
    conn.commit()

    return True


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_check(args: argparse.Namespace) -> None:
    """Show what rewards a student has earned and what is pending."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE name LIKE ?", (f"%{args.student}%",)
        ).fetchone()
        if not student:
            print(f"Student not found: {args.student}")
            return

        # Get completed milestones
        completed = conn.execute("""
            SELECT milestone, completed_date FROM milestones
            WHERE student_id = ? AND status = 'completed'
            ORDER BY completed_date
        """, (student["id"],)).fetchall()

        completed_set = {r["milestone"] for r in completed}

        print(f"\n  REWARDS FOR: {student['name']}")
        print("=" * 50)

        for milestone, reward in MILESTONE_REWARDS.items():
            is_completed = milestone in completed_set
            is_rewarded = _has_been_rewarded(conn, student["id"], milestone)

            if is_completed and is_rewarded:
                status = "GRANTED"
            elif is_completed and not is_rewarded:
                status = "PENDING (earned but not yet granted)"
            else:
                status = "not yet earned"

            role_label = f" | Role: {reward['role_name']}" if reward["role_name"] else ""
            unlock_label = f" | Unlock: {reward['unlock']}" if reward["unlock"] else ""
            print(f"  {milestone:20s} [{status}]{role_label}{unlock_label}")
        print()
    finally:
        conn.close()


def cmd_grant(args: argparse.Namespace) -> None:
    """Manually trigger a reward for a student."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE name LIKE ?", (f"%{args.student}%",)
        ).fetchone()
        if not student:
            print(f"Student not found: {args.student}")
            return

        grant_reward(conn, student, args.milestone)
    finally:
        conn.close()


def cmd_scan(args: argparse.Namespace) -> None:
    """Scan all students for milestones that haven't been rewarded yet."""
    conn = get_db()
    try:
        milestone_keys = tuple(MILESTONE_REWARDS.keys())
        placeholders = ",".join("?" * len(milestone_keys))

        completed = conn.execute(f"""
            SELECT m.student_id, m.milestone, s.name, s.discord_user_id,
                   s.discord_channel_id
            FROM milestones m
            JOIN students s ON s.id = m.student_id
            WHERE m.status = 'completed'
              AND m.milestone IN ({placeholders})
        """, milestone_keys).fetchall()

        pending = []
        for c in completed:
            if not _has_been_rewarded(conn, c["student_id"], c["milestone"]):
                pending.append(c)

        if not pending:
            print("No pending rewards found. All milestones have been rewarded.")
            return

        print(f"\n  PENDING REWARDS ({len(pending)})")
        print("=" * 50)

        dry_run = getattr(args, "dry_run", False)
        granted = 0
        for p in pending:
            student = conn.execute(
                "SELECT * FROM students WHERE id = ?", (p["student_id"],)
            ).fetchone()
            if student and grant_reward(conn, student, p["milestone"], dry_run=dry_run):
                granted += 1
                time.sleep(2)  # Rate limit between students

        print(f"\n  {granted} reward(s) {'would be ' if dry_run else ''}granted.")
    finally:
        conn.close()


def cmd_roles(args: argparse.Namespace) -> None:
    """List all milestone roles and who has them."""
    conn = get_db()
    try:
        print("\n  MILESTONE ROLES")
        print("=" * 50)

        for milestone, reward in MILESTONE_REWARDS.items():
            if not reward["role_name"]:
                continue

            # Who has been rewarded this milestone?
            holders = conn.execute("""
                SELECT s.name FROM engagement_signals es
                JOIN students s ON s.id = es.student_id
                WHERE es.signal_type = 'reward_granted' AND es.value = ?
            """, (milestone,)).fetchall()

            names = ", ".join(h["name"] for h in holders) if holders else "(none)"
            print(f"  {reward['role_name']:20s} ({milestone}): {names}")
        print()
    finally:
        conn.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-assign Discord roles and celebrate student milestones."
    )
    subs = parser.add_subparsers(dest="command")

    # check
    p_check = subs.add_parser("check", help="Show rewards status for a student")
    p_check.add_argument("--student", required=True, help="Student name (partial match)")

    # grant
    p_grant = subs.add_parser("grant", help="Manually grant a milestone reward")
    p_grant.add_argument("--student", required=True, help="Student name")
    p_grant.add_argument("--milestone", required=True,
                         help=f"Milestone: {', '.join(MILESTONE_REWARDS.keys())}")

    # scan
    p_scan = subs.add_parser("scan", help="Scan all students for unrewarded milestones")
    p_scan.add_argument("--dry-run", action="store_true", help="Preview without sending")

    # roles
    subs.add_parser("roles", help="List milestone roles and holders")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "check": cmd_check,
        "grant": cmd_grant,
        "scan": cmd_scan,
        "roles": cmd_roles,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
