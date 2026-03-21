#!/usr/bin/env python3
"""
Script: auto_outreach_engine.py
Purpose: Background queue processor that reads queued touchpoints from the
         student coaching DB and sends them via Discord REST API. This is the
         missing piece that makes the CSM system operational -- without it,
         intervention DMs are queued but never sent.

         Supports DMs (via DM channel creation) and guild channel messages.
         Enforces a per-student weekly limit (max 2 automated messages per week,
         celebrations excluded) to prevent spam.

Inputs:  CLI subcommands
Outputs: Sent Discord messages, updated touchpoint statuses

CLI:
    python execution/auto_outreach_engine.py process [--dry-run] [--limit 50]
    python execution/auto_outreach_engine.py status
    python execution/auto_outreach_engine.py history --student "Talha"
    python execution/auto_outreach_engine.py clear-stale [--days 7]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed. Run: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"
GUILD_ID = "1185214150222286849"
DISCORD_API = "https://discord.com/api/v10"
WEEKLY_DM_LIMIT = 2
RATE_LIMIT_SECONDS = 2


# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Open SQLite connection with WAL mode and foreign keys."""
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Discord Helpers ───────────────────────────────────────────────────────────

def _get_headers() -> dict | None:
    """Return Discord bot auth headers, or None if no token."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        return None
    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }


def _truncate(content: str, limit: int = 2000) -> str:
    """Truncate content to Discord's character limit."""
    if len(content) > limit:
        return content[: limit - 3] + "..."
    return content


def send_dm(discord_user_id: str, content: str) -> tuple[bool, str]:
    """Send a DM by creating a DM channel then posting a message."""
    headers = _get_headers()
    if not headers:
        return False, "no_token"

    content = _truncate(content)

    # Create DM channel
    resp = requests.post(
        f"{DISCORD_API}/users/@me/channels",
        headers=headers,
        json={"recipient_id": str(discord_user_id)},
        timeout=15,
    )
    if resp.status_code != 200:
        return False, f"dm_channel_failed_{resp.status_code}"

    dm_channel_id = resp.json()["id"]

    # Send message
    resp2 = requests.post(
        f"{DISCORD_API}/channels/{dm_channel_id}/messages",
        headers=headers,
        json={"content": content},
        timeout=15,
    )
    if resp2.status_code == 200:
        return True, "200"
    return False, str(resp2.status_code)


def send_channel_message(channel_id: str, content: str) -> tuple[bool, str]:
    """Send a message to a specific Discord channel."""
    headers = _get_headers()
    if not headers:
        return False, "no_token"

    content = _truncate(content)

    resp = requests.post(
        f"{DISCORD_API}/channels/{channel_id}/messages",
        headers=headers,
        json={"content": content},
        timeout=15,
    )
    if resp.status_code == 200:
        return True, "200"
    return False, str(resp.status_code)


def find_student_channel(student_name: str) -> str | None:
    """Find a student's private channel by first-name prefix matching."""
    headers = _get_headers()
    if not headers:
        return None

    # Remove Content-Type for GET request
    get_headers = {"Authorization": headers["Authorization"]}
    resp = requests.get(
        f"{DISCORD_API}/guilds/{GUILD_ID}/channels",
        headers=get_headers,
        timeout=15,
    )
    if resp.status_code != 200:
        return None

    first_name = student_name.split()[0].lower()
    for ch in resp.json():
        ch_name = ch.get("name", "").lower()
        # Look for channels with the student's name and graduation cap emoji
        if first_name in ch_name:
            raw_name = ch.get("name", "")
            if "\U0001f393" in raw_name or "grad" in ch_name or "student" in ch_name:
                return ch["id"]

    # Fallback: just match on first name if no emoji-tagged channel found
    for ch in resp.json():
        ch_name = ch.get("name", "").lower()
        if first_name in ch_name:
            return ch["id"]

    return None


# ── CLI Commands ──────────────────────────────────────────────────────────────

def process_queue(dry_run: bool = False, limit: int = 50) -> dict:
    """Process queued touchpoints: send DMs and channel messages via Discord."""
    conn = get_db()
    try:
        queued = conn.execute(
            """
            SELECT t.id, t.student_id, t.type, t.channel, t.message, t.status,
                   s.name, s.discord_user_id, s.discord_channel_id
            FROM touchpoints t
            JOIN students s ON s.id = t.student_id
            WHERE t.status = 'queued'
              AND t.channel IN ('discord', 'discord_dm', 'discord_channel')
            ORDER BY t.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        if not queued:
            print("No queued touchpoints to process.")
            return {"sent": 0, "skipped": 0, "failed": 0, "total": 0}

        mode_label = "[DRY RUN] " if dry_run else ""
        print(f"\n{mode_label}Processing {len(queued)} queued touchpoints...")
        print("=" * 60)

        sent = 0
        skipped = 0
        failed = 0

        for tp in queued:
            # Per-student weekly limit (celebrations excluded)
            recent_count = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM touchpoints
                WHERE student_id = ? AND status = 'sent'
                  AND sent_at >= date('now', '-7 days')
                  AND type NOT IN ('celebration')
                """,
                (tp["student_id"],),
            ).fetchone()["cnt"]

            if recent_count >= WEEKLY_DM_LIMIT:
                skipped += 1
                print(
                    f"  SKIP {tp['name']}: already sent {recent_count} this week"
                )
                continue

            if dry_run:
                msg_preview = tp["message"][:80]
                print(
                    f"  [DRY RUN] -> {tp['name']} ({tp['channel']}): "
                    f"{msg_preview}..."
                )
                sent += 1
                continue

            # Send based on channel type
            success = False
            error_msg = ""

            channel = tp["channel"]

            # Normalize: bare "discord" → DM if user_id exists, else channel
            if channel == "discord":
                if tp["discord_user_id"]:
                    channel = "discord_dm"
                elif tp["discord_channel_id"]:
                    channel = "discord_channel"
                else:
                    # Try to find a channel by name as last resort
                    channel = "discord_channel"

            if channel == "discord_dm" and tp["discord_user_id"]:
                success, error_msg = send_dm(
                    tp["discord_user_id"], tp["message"]
                )
            elif channel == "discord_channel":
                channel_id = tp["discord_channel_id"]
                if not channel_id:
                    channel_id = find_student_channel(tp["name"])
                if channel_id:
                    success, error_msg = send_channel_message(
                        channel_id, tp["message"]
                    )
                else:
                    error_msg = "no_channel_found"
            elif channel == "discord_dm" and not tp["discord_user_id"]:
                error_msg = "no_discord_user_id"
            else:
                error_msg = f"unsupported_channel_{tp['channel']}"

            now = datetime.utcnow().isoformat()
            if success:
                conn.execute(
                    "UPDATE touchpoints SET status = 'sent', sent_at = ? WHERE id = ?",
                    (now, tp["id"]),
                )
                sent += 1
                print(f"  SENT -> {tp['name']}: {tp['type']}")
            else:
                conn.execute(
                    "UPDATE touchpoints SET status = 'failed' WHERE id = ?",
                    (tp["id"],),
                )
                failed += 1
                print(f"  FAIL -> {tp['name']}: {error_msg}")

            conn.commit()
            time.sleep(RATE_LIMIT_SECONDS)

        print(
            f"\nResults: {sent} sent, {skipped} skipped (weekly limit), "
            f"{failed} failed, {len(queued)} total"
        )
        return {
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
            "total": len(queued),
        }
    finally:
        conn.close()


def show_status() -> None:
    """Show queue status with counts by status and recent sends."""
    conn = get_db()
    try:
        counts = conn.execute(
            """
            SELECT status, COUNT(*) as cnt
            FROM touchpoints
            GROUP BY status
            ORDER BY cnt DESC
            """
        ).fetchall()

        print("\nOUTREACH ENGINE STATUS")
        print("=" * 40)
        total = 0
        for row in counts:
            print(f"  {row['status']:12s} -- {row['cnt']}")
            total += row["cnt"]
        if not counts:
            print("  (no touchpoints in database)")
        print(f"  {'TOTAL':12s} -- {total}")

        # Recent sends
        recent = conn.execute(
            """
            SELECT t.sent_at, s.name, t.type, t.message
            FROM touchpoints t
            JOIN students s ON s.id = t.student_id
            WHERE t.status = 'sent'
            ORDER BY t.sent_at DESC
            LIMIT 10
            """
        ).fetchall()

        if recent:
            print(f"\nLAST 10 SENDS")
            print("-" * 40)
            for r in recent:
                ts = r["sent_at"][:16] if r["sent_at"] else "?"
                msg = r["message"][:50]
                print(f"  {ts} -> {r['name']}: {r['type']} -- {msg}...")
    finally:
        conn.close()


def show_history(student_name: str) -> None:
    """Show touchpoint history for a specific student."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE name LIKE ?",
            (f"%{student_name}%",),
        ).fetchone()

        if not student:
            print(f"Student not found: {student_name}")
            return

        touchpoints = conn.execute(
            """
            SELECT * FROM touchpoints
            WHERE student_id = ?
            ORDER BY id DESC
            LIMIT 20
            """,
            (student["id"],),
        ).fetchall()

        print(f"\nTOUCHPOINT HISTORY: {student['name']}")
        print("=" * 60)

        if not touchpoints:
            print("  (no touchpoints recorded)")
            return

        status_icons = {
            "queued": "[QUEUED]",
            "sent": "[SENT]",
            "delivered": "[DELIVERED]",
            "responded": "[RESPONDED]",
            "failed": "[FAILED]",
            "expired": "[EXPIRED]",
        }

        for tp in touchpoints:
            icon = status_icons.get(tp["status"], "[?]")
            print(
                f"  {icon} {tp['status']:10s} | {tp['type']:15s} | {tp['channel']:15s}"
            )
            print(f"    {tp['message'][:80]}...")
            if tp["sent_at"]:
                print(f"    Sent: {tp['sent_at'][:16]}")
            if tp["response_at"]:
                print(f"    Responded: {tp['response_at'][:16]}")
            print()
    finally:
        conn.close()


def clear_stale(days: int = 7) -> None:
    """Mark old unsent touchpoints as expired.

    Uses a created_at column if available, otherwise falls back to
    rowid-based approximation (~50 touchpoints per day).
    """
    conn = get_db()
    try:
        # Check if touchpoints table has a created_at column
        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(touchpoints)").fetchall()
        ]

        if "created_at" in columns:
            result = conn.execute(
                """
                UPDATE touchpoints SET status = 'expired'
                WHERE status = 'queued'
                  AND created_at < datetime('now', ? || ' days')
                """,
                (f"-{days}",),
            )
        else:
            # Fallback: rowid-based approximation
            max_id_row = conn.execute(
                "SELECT MAX(id) as max_id FROM touchpoints"
            ).fetchone()
            max_id = max_id_row["max_id"] if max_id_row["max_id"] else 0
            cutoff = max_id - (days * 50)
            if cutoff < 0:
                cutoff = 0
            conn.execute(
                """
                UPDATE touchpoints SET status = 'expired'
                WHERE status = 'queued'
                  AND CAST(id AS INTEGER) < ?
                """,
                (cutoff,),
            )

        conn.commit()
        count = conn.execute("SELECT changes()").fetchone()[0]
        print(f"Expired {count} stale touchpoints (older than ~{days} days)")
    finally:
        conn.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto Outreach Engine -- process queued student touchpoints via Discord"
    )
    sub = parser.add_subparsers(dest="command")

    # process
    p_process = sub.add_parser("process", help="Process queued touchpoints (send DMs)")
    p_process.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without sending",
    )
    p_process.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max touchpoints to process (default: 50)",
    )

    # status
    sub.add_parser("status", help="Show queue status")

    # history
    p_history = sub.add_parser("history", help="Touchpoint history for a student")
    p_history.add_argument(
        "--student",
        required=True,
        help="Student name (partial match)",
    )

    # clear-stale
    p_clear = sub.add_parser("clear-stale", help="Expire old unsent touchpoints")
    p_clear.add_argument(
        "--days",
        type=int,
        default=7,
        help="Age threshold in days (default: 7)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "process":
        process_queue(dry_run=args.dry_run, limit=args.limit)
    elif args.command == "status":
        show_status()
    elif args.command == "history":
        show_history(args.student)
    elif args.command == "clear-stale":
        clear_stale(days=args.days)


if __name__ == "__main__":
    main()
