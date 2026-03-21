#!/usr/bin/env python3
"""
Script: accountability_pods.py
Purpose: Auto-matches Amazon FBA students into accountability pods based on
         milestone proximity. Manages pod lifecycle: creation, weekly check-ins,
         leaderboard scoring, and monthly rotation.
Inputs:  CLI subcommands
Outputs: Pod assignments, Discord DMs (check-in prompts), leaderboard reports

CLI:
    python execution/accountability_pods.py match [--size 3]
    python execution/accountability_pods.py list
    python execution/accountability_pods.py leaderboard
    python execution/accountability_pods.py send-checkin [--dry-run]
    python execution/accountability_pods.py rotate
    python execution/accountability_pods.py my-pod --student "Name"
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from collections import defaultdict
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

MILESTONE_GROUPS = {
    "early": ["enrolled", "niche_selected", "product_selected"],
    "sourcing": ["supplier_contacted", "first_order", "listing_live"],
    "selling": ["first_sale", "optimizing", "profitable_month"],
    "scaling": ["scaling", "va_hired", "10k_month"],
}

POD_NAMES = [
    "Alpha Sellers", "Profit Pirates", "Source Squad", "FBA Force",
    "Deal Hunters", "Launch Crew", "Scale Squad", "ROI Rangers",
    "BSR Bandits", "Ungating Gang", "Margin Makers", "Listing Legends",
    "Box Breakers", "Prime Movers", "Revenue Rockets", "Niche Knights",
    "Arbitrage Army", "Catalog Crew", "Rank Risers", "Cash Flow Clan",
]

POD_CHECKIN_PROMPTS = [
    (
        "**Pod Check-in Time!** How did your week go?\n\n"
        "What did you accomplish?\n"
        "What's blocking you?\n"
        "What's your #1 goal for next week?\n\n"
        "Tag your pod members and hold each other accountable!"
    ),
    (
        "**Weekly Pod Update!** Quick round:\n\n"
        "1. One win from this week (big or small)\n"
        "2. One thing you're stuck on\n"
        "3. One thing you'll do by next check-in\n\n"
        "Let's hear it!"
    ),
    (
        "**Pod Accountability!** Time to check in:\n\n"
        "Did you hit last week's goal?\n"
        "What's the plan this week?\n"
        "What's one tip you'd share with your pod?\n\n"
        "Remember: your pod is counting on you!"
    ),
]

ROTATION_INTERVAL_DAYS = 28  # Rotate pods every 4 weeks

# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Connect to the shared coaching DB and ensure pod tables exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_pods_tables(conn)
    return conn


def _ensure_pods_tables(conn: sqlite3.Connection) -> None:
    """Create pods and pod_checkins tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            group_stage TEXT NOT NULL,
            member_ids TEXT NOT NULL,
            created_at TEXT NOT NULL,
            rotated_at TEXT,
            status TEXT DEFAULT 'active'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pod_checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pod_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            message TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (pod_id) REFERENCES pods(id),
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)
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


# ── Core Logic ────────────────────────────────────────────────────────────────

def _get_milestone_group(milestone: str | None) -> str | None:
    """Return the group name for a given milestone, or None."""
    if not milestone:
        return None
    for group_name, milestones in MILESTONE_GROUPS.items():
        if milestone in milestones:
            return group_name
    return None


def _pick_pod_name(conn: sqlite3.Connection) -> str:
    """Pick a pod name that isn't currently in use."""
    used = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM pods WHERE status = 'active'"
        ).fetchall()
    }
    available = [n for n in POD_NAMES if n not in used]
    if not available:
        # All names used, generate a numbered fallback
        return f"Pod #{conn.execute('SELECT COUNT(*) as c FROM pods').fetchone()['c'] + 1}"
    return random.choice(available)


def match_pods(conn: sqlite3.Connection, pod_size: int = 3) -> list[dict]:
    """Match students into accountability pods of 2-3 at similar stages."""
    students = conn.execute("""
        SELECT id, name, discord_user_id, current_milestone
        FROM students WHERE status IN ('active', 'at_risk')
    """).fetchall()

    # Group by milestone group
    groups = defaultdict(list)
    ungrouped = []
    for s in students:
        group = _get_milestone_group(s["current_milestone"])
        if group:
            groups[group].append(s)
        else:
            ungrouped.append(s)

    # If there are ungrouped students, add them to the closest group or "early"
    if ungrouped:
        groups["early"].extend(ungrouped)

    # Within each group, create pods
    pods = []
    for group_name, members in groups.items():
        random.shuffle(members)
        for i in range(0, len(members), pod_size):
            pod_members = members[i : i + pod_size]
            if len(pod_members) < 2:
                # Not enough for a pod -- try to merge with previous pod
                if pods and pods[-1]["group"] == group_name:
                    pods[-1]["members"].extend(pod_members)
                elif len(pod_members) == 1 and pods:
                    # Attach solo student to the most recent pod of any group
                    pods[-1]["members"].extend(pod_members)
                continue

            pods.append({
                "group": group_name,
                "members": pod_members,
                "name": _pick_pod_name(conn),
                "created_at": datetime.utcnow().isoformat(),
            })

    return pods


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_match(args: argparse.Namespace) -> None:
    """Create new pod assignments."""
    conn = get_db()
    try:
        pod_size = args.size or 3

        # Deactivate old pods
        old_count = conn.execute(
            "SELECT COUNT(*) as c FROM pods WHERE status = 'active'"
        ).fetchone()["c"]
        if old_count > 0:
            conn.execute("UPDATE pods SET status = 'archived' WHERE status = 'active'")
            print(f"Archived {old_count} existing pod(s).")

        pods = match_pods(conn, pod_size)

        if not pods:
            print("Not enough active students to form pods (need at least 2).")
            return

        for pod in pods:
            member_ids = [m["id"] for m in pod["members"]]
            conn.execute("""
                INSERT INTO pods (name, group_stage, member_ids, created_at, status)
                VALUES (?, ?, ?, ?, 'active')
            """, (pod["name"], pod["group"], json.dumps(member_ids), pod["created_at"]))

        conn.commit()

        print(f"\n  NEW POD ASSIGNMENTS ({len(pods)} pods)")
        print("=" * 60)
        for pod in pods:
            names = ", ".join(m["name"] for m in pod["members"])
            print(f"  {pod['name']:20s} [{pod['group']:10s}] -- {names}")
        print()
    finally:
        conn.close()


def cmd_list(args: argparse.Namespace) -> None:
    """Show all active pods."""
    conn = get_db()
    try:
        pods = conn.execute(
            "SELECT * FROM pods WHERE status = 'active' ORDER BY group_stage, name"
        ).fetchall()

        if not pods:
            print("No active pods. Run 'match' to create them.")
            return

        print(f"\n  ACTIVE PODS ({len(pods)})")
        print("=" * 60)
        for pod in pods:
            member_ids = json.loads(pod["member_ids"])
            members = []
            for mid in member_ids:
                s = conn.execute(
                    "SELECT name, current_milestone FROM students WHERE id = ?", (mid,)
                ).fetchone()
                if s:
                    members.append(f"{s['name']} ({s['current_milestone']})")
            names = ", ".join(members) if members else "(empty)"
            age_days = (datetime.utcnow() - datetime.fromisoformat(pod["created_at"])).days
            print(f"  {pod['name']:20s} [{pod['group_stage']:10s}] "
                  f"Age: {age_days}d | Members: {names}")
        print()
    finally:
        conn.close()


def cmd_leaderboard(args: argparse.Namespace) -> None:
    """Pod leaderboard -- which pod is most active (by check-ins)."""
    conn = get_db()
    try:
        pods = conn.execute(
            "SELECT * FROM pods WHERE status = 'active' ORDER BY name"
        ).fetchall()

        if not pods:
            print("No active pods.")
            return

        board = []
        for pod in pods:
            member_ids = json.loads(pod["member_ids"])
            checkin_count = conn.execute(
                "SELECT COUNT(*) as c FROM pod_checkins WHERE pod_id = ?",
                (pod["id"],),
            ).fetchone()["c"]

            # Also count engagement signals for pod members in last 7 days
            placeholders = ",".join("?" * len(member_ids))
            week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()[:10]
            signals = conn.execute(f"""
                SELECT COUNT(*) as c FROM engagement_signals
                WHERE student_id IN ({placeholders}) AND date >= ?
            """, (*member_ids, week_ago)).fetchone()["c"]

            score = checkin_count * 10 + signals
            board.append({
                "name": pod["name"],
                "group": pod["group_stage"],
                "checkins": checkin_count,
                "signals": signals,
                "score": score,
                "members": len(member_ids),
            })

        board.sort(key=lambda x: x["score"], reverse=True)

        print("\n  POD LEADERBOARD")
        print("=" * 60)
        for i, pod in enumerate(board, 1):
            medal = {1: "[1st]", 2: "[2nd]", 3: "[3rd]"}.get(i, f"[{i}th]")
            print(f"  {medal:6s} {pod['name']:20s} [{pod['group']:10s}] "
                  f"Score: {pod['score']:4d} | Check-ins: {pod['checkins']} | "
                  f"Activity: {pod['signals']} | Members: {pod['members']}")
        print()
    finally:
        conn.close()


def cmd_send_checkin(args: argparse.Namespace) -> None:
    """Send weekly check-in prompts to all active pods."""
    dry_run = args.dry_run
    conn = get_db()
    try:
        pods = conn.execute(
            "SELECT * FROM pods WHERE status = 'active'"
        ).fetchall()

        if not pods:
            print("No active pods.")
            return

        prompt = random.choice(POD_CHECKIN_PROMPTS)
        sent = 0

        for pod in pods:
            member_ids = json.loads(pod["member_ids"])
            members = []
            for mid in member_ids:
                s = conn.execute(
                    "SELECT name, discord_user_id FROM students WHERE id = ?", (mid,)
                ).fetchone()
                if s:
                    members.append(s)

            if len(members) < 2:
                continue

            names = ", ".join(m["name"].split()[0] for m in members)
            full_prompt = f"**Pod: {pod['name']}** ({names})\n\n{prompt}"

            if dry_run:
                print(f"[DRY RUN] Pod '{pod['name']}': {full_prompt[:100]}...")
                sent += 1
                continue

            # Send DM to each pod member
            for m in members:
                if m["discord_user_id"]:
                    ok, code = send_dm(m["discord_user_id"], full_prompt)
                    status = "sent" if ok else f"failed ({code})"
                    print(f"  {pod['name']} -> {m['name']}: {status}")
                    time.sleep(2)  # Rate limit
            sent += 1

        print(f"\n{'[DRY RUN] ' if dry_run else ''}{sent} pod check-in(s) "
              f"{'would be ' if dry_run else ''}sent.")
    finally:
        conn.close()


def cmd_rotate(args: argparse.Namespace) -> None:
    """Rotate pods that are older than ROTATION_INTERVAL_DAYS."""
    conn = get_db()
    try:
        cutoff = (datetime.utcnow() - timedelta(days=ROTATION_INTERVAL_DAYS)).isoformat()
        stale = conn.execute("""
            SELECT * FROM pods WHERE status = 'active' AND created_at < ?
        """, (cutoff,)).fetchall()

        if not stale:
            print(f"No pods older than {ROTATION_INTERVAL_DAYS} days. Nothing to rotate.")
            return

        print(f"Found {len(stale)} pod(s) older than {ROTATION_INTERVAL_DAYS} days.")

        # Archive stale pods
        for pod in stale:
            conn.execute("""
                UPDATE pods SET status = 'archived', rotated_at = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), pod["id"]))

        conn.commit()
        print(f"Archived {len(stale)} stale pod(s).")

        # Re-match
        pods = match_pods(conn)
        if not pods:
            print("Not enough students to form new pods.")
            return

        for pod in pods:
            member_ids = [m["id"] for m in pod["members"]]
            conn.execute("""
                INSERT INTO pods (name, group_stage, member_ids, created_at, status)
                VALUES (?, ?, ?, ?, 'active')
            """, (pod["name"], pod["group"], json.dumps(member_ids), pod["created_at"]))

        conn.commit()

        print(f"Created {len(pods)} new pod(s):")
        for pod in pods:
            names = ", ".join(m["name"] for m in pod["members"])
            print(f"  {pod['name']:20s} [{pod['group']:10s}] -- {names}")
        print()
    finally:
        conn.close()


def cmd_my_pod(args: argparse.Namespace) -> None:
    """Show a student's current pod."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE name LIKE ?", (f"%{args.student}%",)
        ).fetchone()
        if not student:
            print(f"Student not found: {args.student}")
            return

        pods = conn.execute(
            "SELECT * FROM pods WHERE status = 'active'"
        ).fetchall()

        found = False
        for pod in pods:
            member_ids = json.loads(pod["member_ids"])
            if student["id"] in member_ids:
                found = True
                members = []
                for mid in member_ids:
                    s = conn.execute(
                        "SELECT name, current_milestone, health_score FROM students WHERE id = ?",
                        (mid,),
                    ).fetchone()
                    if s:
                        you = " (you)" if mid == student["id"] else ""
                        members.append(
                            f"    {s['name']}{you} -- {s['current_milestone']} "
                            f"(health: {s['health_score']})"
                        )

                age_days = (datetime.utcnow() - datetime.fromisoformat(pod["created_at"])).days
                checkins = conn.execute(
                    "SELECT COUNT(*) as c FROM pod_checkins WHERE pod_id = ?",
                    (pod["id"],),
                ).fetchone()["c"]

                print(f"\n  {student['name']}'s Pod: {pod['name']}")
                print(f"  Stage: {pod['group_stage']} | Age: {age_days} days | "
                      f"Check-ins: {checkins}")
                print(f"  Members:")
                for m in members:
                    print(m)
                print()
                break

        if not found:
            print(f"{student['name']} is not in any active pod. Run 'match' to assign pods.")
    finally:
        conn.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Accountability pods for Amazon FBA coaching students."
    )
    subs = parser.add_subparsers(dest="command")

    # match
    p_match = subs.add_parser("match", help="Create new pod assignments")
    p_match.add_argument("--size", type=int, default=3, help="Pod size (default: 3)")

    # list
    subs.add_parser("list", help="Show all active pods")

    # leaderboard
    subs.add_parser("leaderboard", help="Pod leaderboard by activity")

    # send-checkin
    p_checkin = subs.add_parser("send-checkin", help="Send weekly check-in prompts")
    p_checkin.add_argument("--dry-run", action="store_true", help="Preview without sending")

    # rotate
    subs.add_parser("rotate", help="Rotate pods older than 4 weeks")

    # my-pod
    p_mypod = subs.add_parser("my-pod", help="Show a student's current pod")
    p_mypod.add_argument("--student", required=True, help="Student name (partial match)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "match": cmd_match,
        "list": cmd_list,
        "leaderboard": cmd_leaderboard,
        "send-checkin": cmd_send_checkin,
        "rotate": cmd_rotate,
        "my-pod": cmd_my_pod,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
