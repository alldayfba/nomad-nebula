#!/usr/bin/env python3
"""Ops tracker — deadlines, builds, sales, content, fulfillment pipeline."""
from __future__ import annotations

import argparse
import datetime
import os
import re

OPS_FILE = "/Users/Shared/antigravity/memory/deadlines.md"

SECTIONS = {
    "build": "Active Builds & Projects",
    "deadline": "Deadlines & Events",
    "sales": "Sales & Marketing Pipeline",
    "content": "Content Pipeline",
    "fulfillment": "Fulfillment & Client Work",
}

STATUS_ICONS = {
    "todo": "📋 TODO",
    "wip": "🔨 WIP",
    "blocked": "🚫 BLOCKED",
    "review": "👀 REVIEW",
    "done": "✅ DONE",
}


def now():
    return datetime.datetime.now()


def today():
    return now().date()


def _read_file() -> list[str]:
    if not os.path.exists(OPS_FILE):
        return []
    with open(OPS_FILE, "r") as f:
        return f.readlines()


def _write_file(lines: list[str]):
    with open(OPS_FILE, "w") as f:
        f.writelines(lines)


def _find_section_end(lines: list[str], section_name: str) -> int:
    """Find the line index to append to for a given section."""
    in_section = False
    last_table_line = -1
    for i, line in enumerate(lines):
        if section_name in line:
            in_section = True
            continue
        if in_section:
            if line.startswith("|") and "---" not in line and "Status" not in line and "Date" not in line:
                last_table_line = i
            elif line.startswith("##") and in_section:
                # Hit next section — insert before it
                return last_table_line + 1 if last_table_line > 0 else i
    return last_table_line + 1 if last_table_line > 0 else len(lines)


def _find_section_table_start(lines: list[str], section_name: str) -> int:
    """Find the separator line (|---|) for a section to insert after."""
    in_section = False
    for i, line in enumerate(lines):
        if section_name in line:
            in_section = True
            continue
        if in_section and "---" in line and line.startswith("|"):
            return i + 1
    return len(lines)


def add_build(name: str, scope: str = "", target: str = "—", notes: str = "", status: str = "todo"):
    icon = STATUS_ICONS.get(status.lower(), STATUS_ICONS["todo"])
    lines = _read_file()
    insert_at = _find_section_end(lines, SECTIONS["build"])
    new_line = f"| {icon} | {name} | {scope} | {target} | {notes} |\n"
    lines.insert(insert_at, new_line)
    _write_file(lines)
    print(f"Added build: {name} [{scope}] — {icon}")


def add_deadline(date_str: str, event: str, scope: str = "", notes: str = ""):
    date = _parse_date(date_str)
    if not date:
        print(f"Could not parse date: {date_str}")
        return
    lines = _read_file()
    insert_at = _find_section_end(lines, SECTIONS["deadline"])
    new_line = f"| {date.strftime('%Y-%m-%d')} | {event} | {scope} | {notes} |\n"
    lines.insert(insert_at, new_line)
    _write_file(lines)
    days_left = (date - today()).days
    countdown = "TODAY" if days_left == 0 else f"TOMORROW" if days_left == 1 else f"in {days_left}d"
    print(f"Added deadline: {event} on {date.strftime('%Y-%m-%d')} ({countdown})")


def add_sales(task: str, scope: str = "", due: str = "—", notes: str = "", status: str = "todo"):
    icon = STATUS_ICONS.get(status.lower(), STATUS_ICONS["todo"])
    lines = _read_file()
    insert_at = _find_section_end(lines, SECTIONS["sales"])
    due_str = due if due == "—" else (_parse_date(due) or due)
    if isinstance(due_str, datetime.date):
        due_str = due_str.strftime("%Y-%m-%d")
    new_line = f"| {icon} | {task} | {scope} | {due_str} | {notes} |\n"
    lines.insert(insert_at, new_line)
    _write_file(lines)
    print(f"Added sales task: {task} — {icon}")


def add_content(piece: str, platform: str = "", due: str = "—", notes: str = "", status: str = "todo"):
    icon = STATUS_ICONS.get(status.lower(), STATUS_ICONS["todo"])
    lines = _read_file()
    insert_at = _find_section_end(lines, SECTIONS["content"])
    due_str = due if due == "—" else (_parse_date(due) or due)
    if isinstance(due_str, datetime.date):
        due_str = due_str.strftime("%Y-%m-%d")
    new_line = f"| {icon} | {piece} | {platform} | {due_str} | {notes} |\n"
    lines.insert(insert_at, new_line)
    _write_file(lines)
    print(f"Added content: {piece} [{platform}] — {icon}")


def add_fulfillment(client: str, task: str, due: str = "—", notes: str = "", status: str = "todo"):
    icon = STATUS_ICONS.get(status.lower(), STATUS_ICONS["todo"])
    lines = _read_file()
    insert_at = _find_section_end(lines, SECTIONS["fulfillment"])
    due_str = due if due == "—" else (_parse_date(due) or due)
    if isinstance(due_str, datetime.date):
        due_str = due_str.strftime("%Y-%m-%d")
    new_line = f"| {icon} | {client} | {task} | {due_str} | {notes} |\n"
    lines.insert(insert_at, new_line)
    _write_file(lines)
    print(f"Added fulfillment: {client} — {task} — {icon}")


def update_status(keyword: str, new_status: str):
    """Update status of any item matching keyword."""
    icon = STATUS_ICONS.get(new_status.lower())
    if not icon:
        print(f"Unknown status: {new_status}. Use: {', '.join(STATUS_ICONS.keys())}")
        return
    lines = _read_file()
    updated = False
    for i, line in enumerate(lines):
        if keyword.lower() in line.lower() and line.startswith("|") and "---" not in line:
            # Replace the status icon (first column after |)
            parts = line.split("|")
            for si in STATUS_ICONS.values():
                if si in parts[1]:
                    parts[1] = f" {icon} "
                    lines[i] = "|".join(parts)
                    updated = True
                    print(f"Updated: {keyword} → {icon}")
                    break
            if updated:
                break
    if updated:
        _write_file(lines)
    else:
        print(f"No item matching '{keyword}' found.")


def remove(keyword: str):
    """Remove an item by keyword."""
    lines = _read_file()
    new_lines = []
    removed = False
    for line in lines:
        if keyword.lower() in line.lower() and line.startswith("|") and "---" not in line and "Status" not in line and "Date" not in line:
            removed = True
            print(f"Removed: {line.strip()}")
        else:
            new_lines.append(line)
    if removed:
        _write_file(new_lines)
    else:
        print(f"No item matching '{keyword}' found.")


def overview():
    """Full ops overview with countdowns."""
    lines = _read_file()

    print("=" * 60)
    print(f"  OPS TRACKER — {today().strftime('%A %B %d, %Y')}")
    print("=" * 60)

    current_section = ""
    for line in lines:
        if line.startswith("## "):
            current_section = line.strip().replace("## ", "")
            print(f"\n{current_section}")
            print("-" * 40)
        elif line.startswith("|") and "---" not in line and "Status" not in line and "Date" not in line:
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p]
            if not parts:
                continue

            # Add countdown for date fields
            display = line.strip()
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", line)
            if date_match:
                try:
                    d = datetime.datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
                    days_left = (d - today()).days
                    if days_left == 0:
                        display += "  ← TODAY"
                    elif days_left == 1:
                        display += "  ← TOMORROW"
                    elif 0 < days_left <= 7:
                        display += f"  ← {days_left}d"
                    elif days_left < 0:
                        display += f"  ← {abs(days_left)}d OVERDUE"
                except ValueError:
                    pass

            print(f"  {display}")


def quick_countdown() -> str:
    """One-line summary for status line: nearest deadline + active item counts."""
    lines = _read_file()

    wip_count = 0
    todo_count = 0
    nearest_deadline = None
    nearest_days = 999

    for line in lines:
        if "🔨 WIP" in line:
            wip_count += 1
        if "📋 TODO" in line:
            todo_count += 1

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        if date_match and line.startswith("|") and "---" not in line and "Date" not in line:
            try:
                d = datetime.datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
                days_left = (d - today()).days
                if 0 <= days_left < nearest_days:
                    # Extract event name (second column)
                    parts = [p.strip() for p in line.split("|")]
                    parts = [p for p in parts if p]
                    event_name = parts[1] if len(parts) > 1 else "event"
                    nearest_deadline = event_name
                    nearest_days = days_left
            except ValueError:
                pass

    blocked_count = 0
    for line in lines:
        if "🚫 BLOCKED" in line:
            blocked_count += 1

    result = f"{wip_count} active · {todo_count} queued · {blocked_count} blocked"

    if nearest_deadline and nearest_days <= 3:
        if nearest_days == 0:
            result += f" | TODAY → {nearest_deadline}"
        elif nearest_days == 1:
            result += f" | TOMORROW → {nearest_deadline}"
        else:
            result += f" | {nearest_days}d → {nearest_deadline}"

    return result


def _parse_date(date_str: str) -> datetime.date | None:
    """Parse flexible date formats."""
    date_str = date_str.strip()

    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m/%d", "%B %d, %Y", "%B %d %Y", "%B %d",
                "%b %d, %Y", "%b %d %Y", "%b %d"]:
        try:
            d = datetime.datetime.strptime(date_str, fmt).date()
            if d.year == 1900:
                d = d.replace(year=today().year)
                if d < today():
                    d = d.replace(year=today().year + 1)
            return d
        except ValueError:
            pass

    days_of_week = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    lower = date_str.lower().replace("next ", "")
    if lower in days_of_week:
        target_day = days_of_week[lower]
        current_day = today().weekday()
        days_ahead = (target_day - current_day) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today() + datetime.timedelta(days=days_ahead)

    match = re.match(r"in (\d+) days?", date_str.lower())
    if match:
        return today() + datetime.timedelta(days=int(match.group(1)))

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ops tracker")
    sub = parser.add_subparsers(dest="action")

    # Add commands
    p_build = sub.add_parser("add-build")
    p_build.add_argument("name")
    p_build.add_argument("--scope", "-s", default="")
    p_build.add_argument("--target", "-t", default="—")
    p_build.add_argument("--notes", "-n", default="")
    p_build.add_argument("--status", default="todo")

    p_deadline = sub.add_parser("add-deadline")
    p_deadline.add_argument("--date", "-d", required=True)
    p_deadline.add_argument("--event", "-e", required=True)
    p_deadline.add_argument("--scope", "-s", default="")
    p_deadline.add_argument("--notes", "-n", default="")

    p_sales = sub.add_parser("add-sales")
    p_sales.add_argument("task")
    p_sales.add_argument("--scope", "-s", default="")
    p_sales.add_argument("--due", "-d", default="—")
    p_sales.add_argument("--notes", "-n", default="")
    p_sales.add_argument("--status", default="todo")

    p_content = sub.add_parser("add-content")
    p_content.add_argument("piece")
    p_content.add_argument("--platform", "-p", default="")
    p_content.add_argument("--due", "-d", default="—")
    p_content.add_argument("--notes", "-n", default="")
    p_content.add_argument("--status", default="todo")

    p_fulfill = sub.add_parser("add-fulfillment")
    p_fulfill.add_argument("client")
    p_fulfill.add_argument("--task", "-t", required=True)
    p_fulfill.add_argument("--due", "-d", default="—")
    p_fulfill.add_argument("--notes", "-n", default="")
    p_fulfill.add_argument("--status", default="todo")

    p_update = sub.add_parser("update")
    p_update.add_argument("keyword")
    p_update.add_argument("--status", "-s", required=True)

    p_remove = sub.add_parser("remove")
    p_remove.add_argument("keyword")

    sub.add_parser("overview")
    sub.add_parser("quick")

    args = parser.parse_args()

    if args.action == "add-build":
        add_build(args.name, args.scope, args.target, args.notes, args.status)
    elif args.action == "add-deadline":
        add_deadline(args.date, args.event, args.scope, args.notes)
    elif args.action == "add-sales":
        add_sales(args.task, args.scope, args.due, args.notes, args.status)
    elif args.action == "add-content":
        add_content(args.piece, args.platform, args.due, args.notes, args.status)
    elif args.action == "add-fulfillment":
        add_fulfillment(args.client, args.task, args.due, args.notes, args.status)
    elif args.action == "update":
        update_status(args.keyword, args.status)
    elif args.action == "remove":
        remove(args.keyword)
    elif args.action == "overview":
        overview()
    elif args.action == "quick":
        print(quick_countdown())
    else:
        parser.print_help()
