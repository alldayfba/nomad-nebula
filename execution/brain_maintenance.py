#!/usr/bin/env python3
"""
Script: brain_maintenance.py
Purpose: Archive old brain.md entries + generate fast-loading brain-index.json
         Run at boot when brain.md > 3000 lines, or manually via CLI

What it does:
1. Counts entries in each brain.md section
2. Archives session summaries older than 30 days → brain-archive-{month}.md
3. Archives completed delegations → same archive
4. Generates brain-index.json for fast boot loading
5. Reports brain health stats
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

BRAIN_PATH = Path("/Users/Shared/antigravity/memory/ceo/brain.md")
INDEX_PATH = Path("/Users/Shared/antigravity/memory/ceo/brain-index.json")
ARCHIVE_DIR = Path("/Users/Shared/antigravity/memory/ceo/archives")

ARCHIVE_THRESHOLD_DAYS = 30
LINE_THRESHOLD = 3000  # Auto-archive when brain exceeds this


def count_table_rows(content, section_header):
    """Count rows in a markdown table within a section."""
    pattern = rf'## {re.escape(section_header)}\n.*?\n\|.*?\|\n\|[-| ]+\|\n((?:\|.*?\|\n)*)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        rows = match.group(1).strip().splitlines()
        # Filter out placeholder rows like "| — | — |"
        real_rows = [r for r in rows if not re.match(r'^\|\s*—\s*\|', r)]
        return len(real_rows)
    return 0


def count_list_items(content, section_header):
    """Count bullet items in a section."""
    pattern = rf'## {re.escape(section_header)}\n(.*?)(?=\n---|\n## |\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        lines = match.group(1).splitlines()
        return sum(1 for l in lines if l.strip().startswith("- ") or l.strip().startswith("* "))
    return 0


def count_session_summaries(content):
    """Count ### session summary entries."""
    return len(re.findall(r'### \d{4}-\d{2}-\d{2}', content))


def extract_dates_from_summaries(content):
    """Extract dates from session summary headers."""
    dates = []
    for match in re.finditer(r'### (\d{4}-\d{2}-\d{2})', content):
        try:
            dates.append(datetime.strptime(match.group(1), "%Y-%m-%d"))
        except ValueError:
            pass
    return dates


def archive_old_summaries(content):
    """Move session summaries older than 30 days to archive file."""
    cutoff = datetime.now() - timedelta(days=ARCHIVE_THRESHOLD_DAYS)
    now_str = datetime.now().strftime("%Y-%m")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"brain-archive-{now_str}.md"

    # Find the Session Summaries section
    section_pattern = r'(## Session Summaries\n.*?\n)(### .+?)(\n---\n|\Z)'
    section_match = re.search(section_pattern, content, re.DOTALL)

    if not section_match:
        return content, 0

    summaries_section = section_match.group(0)

    # Split into individual summaries
    summary_pattern = r'(### \d{4}-\d{2}-\d{2}.*?)(?=### \d{4}-\d{2}-\d{2}|\n---\n|\Z)'
    summaries = re.findall(summary_pattern, summaries_section, re.DOTALL)

    to_archive = []
    to_keep = []

    for summary in summaries:
        date_match = re.search(r'### (\d{4}-\d{2}-\d{2})', summary)
        if date_match:
            try:
                summary_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                if summary_date < cutoff:
                    to_archive.append(summary.strip())
                else:
                    to_keep.append(summary.strip())
            except ValueError:
                to_keep.append(summary.strip())
        else:
            to_keep.append(summary.strip())

    if not to_archive:
        return content, 0

    # Write archived summaries
    archive_header = f"# CEO Brain Archive — {now_str}\n\n> Archived session summaries older than {ARCHIVE_THRESHOLD_DAYS} days.\n\n---\n\n"
    archive_content = archive_header + "\n\n".join(to_archive) + "\n"

    if archive_path.exists():
        existing = archive_path.read_text(encoding="utf-8")
        archive_content = existing + "\n\n" + "\n\n".join(to_archive) + "\n"

    archive_path.write_text(archive_content, encoding="utf-8")

    # Rebuild summaries section with only kept entries
    new_section = "## Session Summaries\n\n> Brief record of what happened each session.\n\n"
    new_section += "\n\n".join(to_keep) + "\n"

    # Replace old section
    content = re.sub(
        r'## Session Summaries\n.*?(?=\n---\n[^|]|\Z)',
        new_section,
        content,
        flags=re.DOTALL
    )

    return content, len(to_archive)


def generate_index(content):
    """Generate brain-index.json for fast boot loading."""
    line_count = len(content.splitlines())

    # Extract Meta info
    last_boot_match = re.search(r'Last Boot: (.+)', content)
    last_session_match = re.search(r'Last Session: (.+)', content)
    sessions_match = re.search(r'Total Sessions Tracked: (\d+)', content)

    index = {
        "generated_at": datetime.now().isoformat(),
        "last_boot": last_boot_match.group(1).strip() if last_boot_match else "unknown",
        "last_session": last_session_match.group(1).strip() if last_session_match else "unknown",
        "total_sessions": int(sessions_match.group(1)) if sessions_match else 0,
        "brain_lines": line_count,
        "needs_archive": line_count > LINE_THRESHOLD,
        "sections": {
            "decisions": count_table_rows(content, "Decisions Log"),
            "preferences": count_list_items(content, "Preferences"),
            "learnings": count_table_rows(content, "Learnings"),
            "delegation_history": count_table_rows(content, "Delegation History"),
            "training_officer_queue": count_table_rows(content, "Training Officer Queue"),
            "error_patterns": count_table_rows(content, "Error Patterns"),
            "people": count_table_rows(content, "People & Relationships"),
            "ideas_backlog": count_table_rows(content, "Ideas Backlog"),
            "session_summaries": count_session_summaries(content),
        },
        "archive_files": sorted([
            str(f.name) for f in ARCHIVE_DIR.glob("brain-archive-*.md")
        ]) if ARCHIVE_DIR.exists() else [],
    }

    return index


def print_health_report(index):
    """Print brain health stats."""
    print("╔══════════════════════════════════════════════════╗")
    print("║  CEO BRAIN HEALTH REPORT                         ║")
    print("╚══════════════════════════════════════════════════╝")
    print()
    print(f"  Brain size:           {index['brain_lines']} lines")
    print(f"  Last boot:            {index['last_boot']}")
    print(f"  Last session:         {index['last_session']}")
    print(f"  Total sessions:       {index['total_sessions']}")
    print(f"  Needs archive:        {'YES' if index['needs_archive'] else 'No'}")
    print()
    print("  Section counts:")
    for section, count in index["sections"].items():
        label = section.replace("_", " ").title()
        print(f"    {label:.<30} {count}")
    print()
    if index["archive_files"]:
        print(f"  Archive files:        {len(index['archive_files'])}")
        for af in index["archive_files"]:
            print(f"    - {af}")
    print()
    print("──────────────────────────────────────────────────")


def main():
    if not BRAIN_PATH.exists():
        print("[brain_maintenance] brain.md not found — nothing to do")
        return

    content = BRAIN_PATH.read_text(encoding="utf-8", errors="ignore")
    line_count = len(content.splitlines())
    archived_count = 0

    # Check if archiving needed
    if "--archive" in sys.argv or line_count > LINE_THRESHOLD:
        content, archived_count = archive_old_summaries(content)
        if archived_count > 0:
            BRAIN_PATH.write_text(content, encoding="utf-8")
            print(f"[brain_maintenance] Archived {archived_count} old session summaries")

    # Always generate index
    index = generate_index(content)
    INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"[brain_maintenance] brain-index.json updated ({index['brain_lines']} lines)")

    # Print report if requested
    if "--report" in sys.argv or "--health" in sys.argv:
        print_health_report(index)

    # Warn if brain is getting large
    if index["needs_archive"]:
        print(f"[brain_maintenance] WARNING: Brain is {index['brain_lines']} lines. Run with --archive to prune.")


if __name__ == "__main__":
    main()
