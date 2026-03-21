#!/usr/bin/env python3
"""
Script: generate_case_study.py
Purpose: Generate a formatted markdown case study from a student's DB data.
         Pulls milestones, testimonials, and engagement signals to build a
         factual narrative. No LLM calls -- purely data-driven.
Inputs:  --student (name), --output (optional path)
Outputs: Markdown case study file + stdout

CLI:
    python execution/generate_case_study.py --student "Mark"
    python execution/generate_case_study.py --student "Mark" --output .tmp/case-studies/mark-case-study.md
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / ".tmp" / "case-studies"

# Milestone display names for readable output
MILESTONE_LABELS = {
    "enrolled": "Enrolled in Program",
    "niche_selected": "Niche Selected",
    "product_selected": "Product Selected",
    "supplier_contacted": "Supplier Contacted",
    "sample_received": "Sample Received",
    "listing_created": "Listing Created",
    "listing_live": "Listing Live on Amazon",
    "first_sale": "First Sale",
    "profitable_month": "First Profitable Month",
    "10k_month": "$10K Month",
}

TIER_LABELS = {
    "A": "Beginner ($5K-$20K capital)",
    "B": "Existing Seller (plateaued)",
    "C": "Investor",
}

# Starting-point descriptions based on tier
STARTING_DESCRIPTIONS = {
    "A": "Complete Beginner",
    "B": "Plateaued Seller",
    "C": "Investor with Capital",
}


def get_db() -> sqlite3.Connection:
    """Return a connection to the students DB."""
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
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


def get_milestone_events(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    """Get milestone_completed engagement signals in chronological order."""
    rows = conn.execute(
        "SELECT signal_type, date, notes, value FROM engagement_signals "
        "WHERE student_id = ? AND signal_type = 'milestone_completed' "
        "ORDER BY date ASC",
        (student_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_testimonials(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    """Get all testimonials for a student (prefer approved/published with content)."""
    rows = conn.execute(
        "SELECT type, milestone, content, media_url, status FROM testimonials "
        "WHERE student_id = ? AND content IS NOT NULL AND content != '' "
        "ORDER BY CASE status "
        "  WHEN 'published' THEN 1 WHEN 'approved' THEN 2 "
        "  WHEN 'received' THEN 3 ELSE 4 END",
        (student_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_key_moments(conn: sqlite3.Connection, student_id: int) -> list[dict]:
    """Get notable engagement signals (wins, breakthroughs)."""
    win_types = (
        "first_sale", "profitable_product", "revenue_milestone",
        "screenshot_shared", "mood_positive",
    )
    placeholders = ",".join("?" for _ in win_types)
    rows = conn.execute(
        f"SELECT signal_type, date, notes FROM engagement_signals "
        f"WHERE student_id = ? AND signal_type IN ({placeholders}) "
        f"ORDER BY date ASC",
        (student_id, *win_types),
    ).fetchall()
    return [dict(r) for r in rows]


def days_between(date_str_a: str, date_str_b: str) -> int:
    """Calculate days between two ISO date strings."""
    try:
        a = datetime.fromisoformat(date_str_a.split("T")[0])
        b = datetime.fromisoformat(date_str_b.split("T")[0])
        return abs((b - a).days)
    except (ValueError, AttributeError):
        return 0


def week_number(start_date: str, event_date: str) -> int:
    """Calculate which week an event falls in relative to start date."""
    days = days_between(start_date, event_date)
    return max(1, (days // 7) + 1)


def generate_case_study(student: dict, milestones: list, testimonials: list,
                        key_moments: list) -> str:
    """Build the markdown case study from data."""
    name = student["name"]
    tier = student["tier"] or "A"
    start_date = student["start_date"]
    current_milestone = student["current_milestone"] or "enrolled"
    capital = student["capital"]

    starting_point = STARTING_DESCRIPTIONS.get(tier, "New Student")
    current_label = MILESTONE_LABELS.get(current_milestone, current_milestone)

    lines = []

    # ── Title ──
    lines.append(f"# Case Study: {name} -- From {starting_point} to {current_label}")
    lines.append("")

    # ── The Starting Point ──
    lines.append("## The Starting Point")
    lines.append("")
    start_display = start_date[:10] if start_date else "Unknown"
    lines.append(f"- **Joined:** {start_display}")
    tier_label = TIER_LABELS.get(tier, tier)
    lines.append(f"- **Tier:** {tier} ({tier_label})")
    if capital:
        lines.append(f"- **Starting capital:** ${capital:,.0f}")
    lines.append("- **Goal:** Hit $10K/month on Amazon")
    lines.append("")

    # ── The Journey ──
    lines.append("## The Journey")
    lines.append("")

    if milestones:
        for m in milestones:
            event_date = m.get("date", "")
            milestone_name = m.get("value") or m.get("notes") or "milestone"
            label = MILESTONE_LABELS.get(milestone_name, milestone_name)
            wk = week_number(start_date, event_date) if start_date and event_date else "?"
            context = m.get("notes", "")

            entry = f"- **Week {wk}:** {label}"
            if context and context != milestone_name:
                entry += f" -- {context}"
            lines.append(entry)
    else:
        # Fall back to current milestone if no events
        lines.append(f"- Currently at: **{current_label}**")
        if start_date:
            days_in = days_between(start_date, datetime.utcnow().isoformat())
            lines.append(f"- Days in program: {days_in}")

    # Add key moments that aren't milestone events
    if key_moments:
        lines.append("")
        lines.append("### Notable Moments")
        lines.append("")
        for km in key_moments:
            signal = km["signal_type"].replace("_", " ").title()
            date_str = km["date"][:10] if km["date"] else ""
            notes = km.get("notes", "")
            entry = f"- {signal}"
            if date_str:
                entry += f" ({date_str})"
            if notes:
                entry += f" -- {notes}"
            lines.append(entry)

    lines.append("")

    # ── The Results ──
    lines.append("## The Results")
    lines.append("")
    lines.append(f"- **Current milestone:** {current_label}")
    if start_date:
        days_elapsed = days_between(start_date, datetime.utcnow().isoformat())
        lines.append(f"- **Time in program:** {days_elapsed} days")
    if milestones:
        last_milestone = milestones[-1]
        last_label = MILESTONE_LABELS.get(
            last_milestone.get("value", ""), last_milestone.get("value", "")
        )
        if start_date and last_milestone.get("date"):
            days_to = days_between(start_date, last_milestone["date"])
            lines.append(f"- **Time to {last_label}:** {days_to} days")
    lines.append("")

    # ── In Their Own Words ──
    text_testimonials = [t for t in testimonials if t.get("content")]
    if text_testimonials:
        lines.append("## In Their Own Words")
        lines.append("")
        for t in text_testimonials:
            lines.append(f"> \"{t['content']}\"")
            if t.get("milestone"):
                label = MILESTONE_LABELS.get(t["milestone"], t["milestone"])
                lines.append(f"> -- On reaching: {label}")
            lines.append("")

    # ── Key Takeaways ──
    lines.append("## Key Takeaways")
    lines.append("")

    takeaways = _generate_takeaways(student, milestones, current_milestone, tier)
    for i, takeaway in enumerate(takeaways, 1):
        lines.append(f"{i}. {takeaway}")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated {datetime.utcnow().strftime('%Y-%m-%d')} from program data.*")
    lines.append("")

    return "\n".join(lines)


def _generate_takeaways(student: dict, milestones: list, current_milestone: str,
                        tier: str) -> list[str]:
    """Generate factual takeaways based on data patterns."""
    takeaways = []
    start_date = student["start_date"]

    # Takeaway 1: Speed/progress
    if milestones and start_date:
        first_event = milestones[0]
        days_to_first = days_between(start_date, first_event.get("date", ""))
        if days_to_first <= 14:
            takeaways.append(
                f"Fast starter -- hit first milestone within {days_to_first} days of enrollment."
            )
        else:
            takeaways.append(
                f"Steady progression through {len(milestones)} milestones since enrollment."
            )
    else:
        takeaways.append("Currently progressing through the program milestones.")

    # Takeaway 2: Tier-specific
    if tier == "A":
        takeaways.append(
            "Started with zero Amazon experience and built a real business from scratch."
        )
    elif tier == "B":
        takeaways.append(
            "Broke through a sales plateau using the structured coaching framework."
        )
    elif tier == "C":
        takeaways.append(
            "Leveraged capital efficiently with guided product selection and launch strategy."
        )

    # Takeaway 3: Current state
    label = MILESTONE_LABELS.get(current_milestone, current_milestone)
    if current_milestone in ("profitable_month", "10k_month"):
        takeaways.append(
            f"Now at the '{label}' stage -- proof the system delivers real results."
        )
    elif current_milestone in ("first_sale", "listing_live"):
        takeaways.append(
            f"Already at '{label}' -- momentum is building toward profitability."
        )
    else:
        takeaways.append(
            f"Currently at '{label}' -- on track with the 90-day roadmap."
        )

    return takeaways


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a markdown case study from student data"
    )
    parser.add_argument("--student", required=True, help="Student name")
    parser.add_argument("--output", help="Output file path (default: .tmp/case-studies/{name}.md)")
    args = parser.parse_args()

    conn = get_db()
    try:
        student = find_student(conn, args.student)
        if not student:
            print(f"ERROR: Student '{args.student}' not found in database")
            sys.exit(1)

        student_dict = dict(student)
        milestones = get_milestone_events(conn, student["id"])
        testimonials = get_testimonials(conn, student["id"])
        key_moments = get_key_moments(conn, student["id"])

        case_study = generate_case_study(student_dict, milestones, testimonials, key_moments)

        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            safe_name = student["name"].lower().replace(" ", "-")
            output_path = DEFAULT_OUTPUT_DIR / f"{safe_name}-case-study.md"

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        output_path.write_text(case_study, encoding="utf-8")
        print(f"Case study saved to: {output_path}")
        print()

        # Also print to stdout
        print(case_study)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
