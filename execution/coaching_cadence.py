#!/usr/bin/env python3
"""
Script: coaching_cadence.py
Purpose: Manage structured coaching delivery for the Amazon FBA coaching program.
         Generates call agendas from student data, provides accountability prompts,
         posts daily group challenges, and sends messages to Discord channels.
Inputs:  CLI subcommands
Outputs: Formatted agendas, prompts, challenges; Discord messages via REST API

CLI:
    python execution/coaching_cadence.py generate-agenda --date 2026-03-20
    python execution/coaching_cadence.py weekly-schedule --week-of 2026-03-18
    python execution/coaching_cadence.py accountability --day monday
    python execution/coaching_cadence.py challenge --day tuesday
    python execution/coaching_cadence.py send-accountability --day monday --channel-id 1250966307021656115
    python execution/coaching_cadence.py send-challenge --day friday --channel-id 1250966307021656115
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"

# ── 12-Week Topic Rotation ───────────────────────────────────────────────────

WEEKLY_TOPICS = {
    1: {"topic": "Account Setup & SellerAmp Walkthrough", "focus": "Getting started right"},
    2: {"topic": "First Storefront Stalk — Live Sourcing Demo", "focus": "Finding your first products"},
    3: {"topic": "Product Evaluation Deep-Dive", "focus": "SellerAmp, Keepa, ROI analysis"},
    4: {"topic": "Sourcing Systems & Deal Stacking", "focus": "Building repeatable sourcing workflows"},
    5: {"topic": "Supplier Outreach & Negotiation", "focus": "Wholesale and brand direct"},
    6: {"topic": "Listing Optimization", "focus": "Titles, bullets, keywords, images"},
    7: {"topic": "Launch Strategy & PPC Basics", "focus": "Getting first sales"},
    8: {"topic": "PPC Optimization", "focus": "ACOS, bids, campaign structure"},
    9: {"topic": "Scaling: VA Hiring & Automation", "focus": "Systems for growth"},
    10: {"topic": "Advanced Sourcing — Wholesale", "focus": "Wholesale accounts, MOQs"},
    11: {"topic": "Brand Direct & Inventory Management", "focus": "Building relationships"},
    12: {"topic": "90-Day Review & Graduation Planning", "focus": "What's next"},
}

# ── Call Schedule by Program Phase ────────────────────────────────────────────

CALL_SCHEDULE = {
    # Weeks 1-4: Two group calls per week
    "phase_1": {"weeks": range(1, 5), "tuesday": "group", "thursday": "group"},
    # Weeks 5-8: Tuesday group, Thursday biweekly 1:1
    "phase_2": {"weeks": range(5, 9), "tuesday": "group", "thursday": "biweekly_1on1"},
    # Weeks 9-12: Tuesday group only
    "phase_3": {"weeks": range(9, 13), "tuesday": "group", "thursday": None},
}

# ── Accountability Prompts ────────────────────────────────────────────────────

ACCOUNTABILITY_PROMPTS = {
    "monday": [
        "\U0001f3af **Monday Focus** \u2014 What\u2019s your #1 goal this week? Drop it below \U0001f447",
        "\U0001f3af **New Week Energy** \u2014 What product are you sourcing this week? Share below \U0001f447",
        "\U0001f3af **Monday Check-in** \u2014 Where are you on your 90-day roadmap? Drop your milestone below \U0001f447",
    ],
    "wednesday": [
        "\U0001f4ca **Midweek Check** \u2014 How\u2019s the week going? What did you accomplish so far?",
        "\U0001f4ca **Hump Day Report** \u2014 Share one thing you learned this week \U0001f447",
        "\U0001f4ca **Wednesday Win** \u2014 What\u2019s one small win you had this week? No win is too small \U0001f447",
    ],
    "friday": [
        "\U0001f3c6 **Friday Flex** \u2014 Share your biggest win this week! Screenshots welcome \U0001f4f8",
        "\U0001f3c6 **Week in Review** \u2014 What did you accomplish? What\u2019s the plan for next week?",
        "\U0001f3c6 **End of Week** \u2014 Rate your effort this week 1-10. Be honest. What would make next week a 10?",
    ],
}

# ── Daily Group Challenges ────────────────────────────────────────────────────

DAILY_CHALLENGES = {
    "monday": "\U0001f50d **Sourcing Challenge** \u2014 Find 3 products with 30%+ ROI today. Post your best find below!",
    "tuesday": "\U0001f4de **Outreach Day** \u2014 Contact 2 new wholesale suppliers today. Share your email template!",
    "wednesday": "\U0001f4ca **Analysis Day** \u2014 Review your top 5 products\u2019 Keepa charts. Which one has the best trend?",
    "thursday": "\U0001f4a1 **Learn Something New** \u2014 Watch 1 course module you haven\u2019t seen yet. Share what you learned!",
    "friday": "\U0001f4f8 **Screenshot Friday** \u2014 Share a screenshot of something you\u2019re proud of this week!",
    "saturday": "\U0001f3ea **Retail Arbitrage Day** \u2014 Hit a local store (Walmart, Target, CVS). Post your best find!",
    "sunday": "\U0001f4cb **Sunday Planning** \u2014 Write down your top 3 priorities for next week. Post them here for accountability!",
}

VALID_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Connect to the coaching students database. Returns a connection with Row factory."""
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_student_week(start_date_str: str, reference_date: datetime) -> int:
    """Calculate which program week a student is in (1-indexed, capped at 12)."""
    start = datetime.strptime(start_date_str, "%Y-%m-%d")
    delta = (reference_date - start).days
    week = max(1, (delta // 7) + 1)
    return min(week, 12)


def get_call_type(week: int, weekday: str) -> str | None:
    """Return the call type for a given program week and weekday."""
    for phase_info in CALL_SCHEDULE.values():
        if week in phase_info["weeks"]:
            return phase_info.get(weekday)
    return None


def send_discord_message(channel_id: str, content: str) -> bool:
    """Send a message to a Discord channel via REST API."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not set in .env", file=sys.stderr)
        return False
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    resp = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers=headers,
        json={"content": content},
        timeout=15,
    )
    if resp.status_code in (200, 201):
        print(f"Message sent to channel {channel_id}")
        return True
    print(f"ERROR: Discord API returned {resp.status_code}: {resp.text}", file=sys.stderr)
    return False


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_generate_agenda(args: argparse.Namespace) -> None:
    """Generate a structured coaching call agenda for the given date."""
    target_date = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    weekday = target_date.strftime("%A").lower()

    conn = get_db()

    # Pull active students with their start dates
    students = conn.execute(
        "SELECT id, name, start_date, current_milestone, status FROM students WHERE status = 'active'"
    ).fetchall()

    if not students:
        print("No active students found.")
        conn.close()
        return

    # Group students by their current program week
    week_groups: dict[int, list[dict]] = {}
    for s in students:
        week = get_student_week(s["start_date"], target_date)
        week_groups.setdefault(week, []).append({
            "name": s["name"],
            "week": week,
            "milestone": s["current_milestone"] or "unknown",
            "id": s["id"],
        })

    # Pull recent frustrated/disengaged signals (last 7 days)
    seven_days_ago = (target_date - timedelta(days=7)).strftime("%Y-%m-%d")
    frustrated_rows = conn.execute(
        """
        SELECT es.student_id, s.name, es.signal_type, es.notes, es.created_at
        FROM engagement_signals es
        JOIN students s ON s.id = es.student_id
        WHERE es.signal_type IN ('mood_frustrated', 'mood_disengaged', 'call_missed', 'assignment_missing')
        AND es.created_at >= ?
        ORDER BY es.created_at DESC
        """,
        (seven_days_ago,),
    ).fetchall()

    # Pull recent check-ins for common blockers
    recent_checkins = conn.execute(
        """
        SELECT ci.student_id, s.name, ci.summary AS notes, ci.mood, ci.date AS created_at
        FROM check_ins ci
        JOIN students s ON s.id = ci.student_id
        WHERE ci.date >= ?
        ORDER BY ci.date DESC
        LIMIT 20
        """,
        (seven_days_ago,),
    ).fetchall()

    # Pull recent milestone completions for celebrations
    celebrations = conn.execute(
        """
        SELECT es.student_id, s.name, es.signal_type, es.notes, es.created_at
        FROM engagement_signals es
        JOIN students s ON s.id = es.student_id
        WHERE es.signal_type IN ('milestone_completed', 'first_sale', 'profitable_product', 'revenue_milestone', 'screenshot_shared')
        AND es.created_at >= ?
        ORDER BY es.created_at DESC
        """,
        (seven_days_ago,),
    ).fetchall()

    conn.close()

    # ── Build the agenda ──────────────────────────────────────────────────

    lines = []
    lines.append("=" * 60)
    lines.append(f"  COACHING CALL AGENDA  |  {target_date.strftime('%A, %B %d, %Y')}")
    lines.append("=" * 60)
    lines.append("")

    # Determine the dominant week for today's topic
    # Use the week with the most students, or the median
    if week_groups:
        dominant_week = max(week_groups, key=lambda w: len(week_groups[w]))
        topic_info = WEEKLY_TOPICS.get(dominant_week, {"topic": "Open Q&A", "focus": "Student-driven"})
        lines.append(f"TOPIC (Week {dominant_week}):  {topic_info['topic']}")
        lines.append(f"FOCUS:  {topic_info['focus']}")
    else:
        lines.append("TOPIC:  Open Q&A")
    lines.append("")

    # Call type
    for week_num in sorted(week_groups.keys()):
        call_type = get_call_type(week_num, weekday)
        if call_type:
            lines.append(f"  Week {week_num} students ({len(week_groups[week_num])}): {call_type} call")
        else:
            lines.append(f"  Week {week_num} students ({len(week_groups[week_num])}): no scheduled call today")
    lines.append("")

    # Student roster by week
    lines.append("-" * 40)
    lines.append("STUDENT ROSTER BY WEEK")
    lines.append("-" * 40)
    for week_num in sorted(week_groups.keys()):
        names = [s["name"] for s in week_groups[week_num]]
        milestones = set(s["milestone"] for s in week_groups[week_num])
        lines.append(f"  Week {week_num}: {', '.join(names)}")
        lines.append(f"    Milestones in progress: {', '.join(milestones)}")
    lines.append("")

    # At-risk / frustrated students to check in with
    lines.append("-" * 40)
    lines.append("STUDENTS TO CALL ON (at-risk / frustrated)")
    lines.append("-" * 40)
    if frustrated_rows:
        seen = set()
        for row in frustrated_rows:
            if row["name"] not in seen:
                seen.add(row["name"])
                note = f" -- {row['notes']}" if row["notes"] else ""
                lines.append(f"  * {row['name']} ({row['signal_type']}){note}")
    else:
        lines.append("  None flagged this week.")
    lines.append("")

    # Common blockers from check-ins
    lines.append("-" * 40)
    lines.append("RECENT BLOCKERS / QUESTIONS")
    lines.append("-" * 40)
    if recent_checkins:
        for ci in recent_checkins[:10]:
            note = ci["notes"] or "(no notes)"
            mood_tag = f" [{ci['mood']}]" if ci["mood"] else ""
            lines.append(f"  - {ci['name']}{mood_tag}: {note}")
    else:
        lines.append("  No recent check-ins.")
    lines.append("")

    # Celebrations
    lines.append("-" * 40)
    lines.append("CELEBRATIONS")
    lines.append("-" * 40)
    if celebrations:
        for c in celebrations:
            note = c["notes"] or c["signal_type"].replace("_", " ").title()
            lines.append(f"  * {c['name']}: {note}")
    else:
        lines.append("  No recent milestones to celebrate.")
    lines.append("")
    lines.append("=" * 60)

    output = "\n".join(lines)
    print(output)

    if args.json:
        result = {
            "date": target_date.strftime("%Y-%m-%d"),
            "weekday": weekday,
            "dominant_week": dominant_week if week_groups else None,
            "topic": topic_info if week_groups else None,
            "student_count": len(students),
            "week_groups": {k: [s["name"] for s in v] for k, v in week_groups.items()},
            "at_risk": [r["name"] for r in frustrated_rows] if frustrated_rows else [],
            "celebrations": [c["name"] for c in celebrations] if celebrations else [],
        }
        print("\n--- JSON ---")
        print(json.dumps(result, indent=2))


def cmd_weekly_schedule(args: argparse.Namespace) -> None:
    """Show the full weekly call schedule for a given week."""
    week_start = datetime.strptime(args.week_of, "%Y-%m-%d") if args.week_of else datetime.now()
    # Align to Monday
    week_start = week_start - timedelta(days=week_start.weekday())

    conn = get_db()
    students = conn.execute(
        "SELECT id, name, start_date, current_milestone, status FROM students WHERE status = 'active'"
    ).fetchall()
    conn.close()

    lines = []
    lines.append("=" * 60)
    lines.append(f"  WEEKLY SCHEDULE  |  Week of {week_start.strftime('%B %d, %Y')}")
    lines.append("=" * 60)
    lines.append("")

    for day_offset in range(7):
        day = week_start + timedelta(days=day_offset)
        day_name = day.strftime("%A").lower()
        day_label = day.strftime("%A, %B %d")

        lines.append(f"--- {day_label} ---")

        # Check for calls (Tuesday / Thursday)
        if day_name in ("tuesday", "thursday"):
            week_calls = {}
            for s in students:
                w = get_student_week(s["start_date"], day)
                call_type = get_call_type(w, day_name)
                if call_type:
                    week_calls.setdefault((w, call_type), []).append(s["name"])

            if week_calls:
                for (w, ct), names in sorted(week_calls.items()):
                    topic = WEEKLY_TOPICS.get(w, {}).get("topic", "Open Q&A")
                    lines.append(f"  CALL ({ct}): Week {w} \u2014 {topic}")
                    lines.append(f"    Students: {', '.join(names)}")
            else:
                lines.append("  No calls scheduled.")
        else:
            lines.append("  No calls scheduled.")

        # Accountability prompts (Mon/Wed/Fri)
        if day_name in ACCOUNTABILITY_PROMPTS:
            lines.append(f"  ACCOUNTABILITY: {ACCOUNTABILITY_PROMPTS[day_name][0][:60]}...")

        # Daily challenge
        if day_name in DAILY_CHALLENGES:
            lines.append(f"  CHALLENGE: {DAILY_CHALLENGES[day_name][:60]}...")

        lines.append("")

    print("\n".join(lines))


def cmd_accountability(args: argparse.Namespace) -> None:
    """Get today's accountability prompt (random from pool)."""
    day = args.day.lower()
    if day not in ACCOUNTABILITY_PROMPTS:
        valid = ", ".join(ACCOUNTABILITY_PROMPTS.keys())
        print(f"ERROR: No accountability prompts for '{day}'. Valid days: {valid}", file=sys.stderr)
        sys.exit(1)
    prompt = random.choice(ACCOUNTABILITY_PROMPTS[day])
    print(prompt)


def cmd_challenge(args: argparse.Namespace) -> None:
    """Get today's group challenge."""
    day = args.day.lower()
    if day not in DAILY_CHALLENGES:
        valid = ", ".join(DAILY_CHALLENGES.keys())
        print(f"ERROR: No challenge for '{day}'. Valid days: {valid}", file=sys.stderr)
        sys.exit(1)
    print(DAILY_CHALLENGES[day])


def cmd_send_accountability(args: argparse.Namespace) -> None:
    """Send an accountability prompt to a Discord channel."""
    day = args.day.lower()
    if day not in ACCOUNTABILITY_PROMPTS:
        valid = ", ".join(ACCOUNTABILITY_PROMPTS.keys())
        print(f"ERROR: No accountability prompts for '{day}'. Valid days: {valid}", file=sys.stderr)
        sys.exit(1)
    prompt = random.choice(ACCOUNTABILITY_PROMPTS[day])
    print(f"Sending to channel {args.channel_id}:\n{prompt}\n")
    ok = send_discord_message(args.channel_id, prompt)
    sys.exit(0 if ok else 1)


def cmd_send_challenge(args: argparse.Namespace) -> None:
    """Send a daily challenge to a Discord channel."""
    day = args.day.lower()
    if day not in DAILY_CHALLENGES:
        valid = ", ".join(DAILY_CHALLENGES.keys())
        print(f"ERROR: No challenge for '{day}'. Valid days: {valid}", file=sys.stderr)
        sys.exit(1)
    challenge = DAILY_CHALLENGES[day]
    print(f"Sending to channel {args.channel_id}:\n{challenge}\n")
    ok = send_discord_message(args.channel_id, challenge)
    sys.exit(0 if ok else 1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Coaching cadence manager -- agendas, accountability, challenges, Discord posts."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # generate-agenda
    p_agenda = sub.add_parser("generate-agenda", help="Generate a call agenda for a given date")
    p_agenda.add_argument("--date", help="Date in YYYY-MM-DD format (default: today)")
    p_agenda.add_argument("--json", action="store_true", help="Also output JSON summary")
    p_agenda.set_defaults(func=cmd_generate_agenda)

    # weekly-schedule
    p_week = sub.add_parser("weekly-schedule", help="Show full week schedule")
    p_week.add_argument("--week-of", help="Any date in the target week, YYYY-MM-DD (default: this week)")
    p_week.set_defaults(func=cmd_weekly_schedule)

    # accountability
    p_acc = sub.add_parser("accountability", help="Get an accountability prompt")
    p_acc.add_argument("--day", required=True, choices=["monday", "wednesday", "friday"],
                       help="Day of week")
    p_acc.set_defaults(func=cmd_accountability)

    # challenge
    p_ch = sub.add_parser("challenge", help="Get a daily challenge")
    p_ch.add_argument("--day", required=True, choices=VALID_DAYS, help="Day of week")
    p_ch.set_defaults(func=cmd_challenge)

    # send-accountability
    p_sa = sub.add_parser("send-accountability", help="Post accountability prompt to Discord")
    p_sa.add_argument("--day", required=True, choices=["monday", "wednesday", "friday"],
                      help="Day of week")
    p_sa.add_argument("--channel-id", required=True, help="Discord channel ID")
    p_sa.set_defaults(func=cmd_send_accountability)

    # send-challenge
    p_sc = sub.add_parser("send-challenge", help="Post daily challenge to Discord")
    p_sc.add_argument("--day", required=True, choices=VALID_DAYS, help="Day of week")
    p_sc.add_argument("--channel-id", required=True, help="Discord channel ID")
    p_sc.set_defaults(func=cmd_send_challenge)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
