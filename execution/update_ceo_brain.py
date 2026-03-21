#!/usr/bin/env python3
"""
Script: update_ceo_brain.py
Purpose: Auto-update CEO brain.md at session close by parsing session-log.txt
         Runs via Stop hook in ~/.claude/settings.json (or manually)

What it does:
1. Reads ~/.claude/session-log.txt (captured by PostToolUse hooks)
2. Parses file modifications and commands from the session
3. Categorizes changes (directives, execution, agents, bots, etc.)
4. Appends relevant entries to brain.md sections
5. Updates Meta timestamps
6. Creates daily backup (keeps last 7)
"""

import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

SESSION_LOG = Path.home() / ".claude" / "session-log.txt"
BRAIN_PATH = Path("/Users/Shared/antigravity/memory/ceo/brain.md")
BACKUP_DIR = Path("/Users/Shared/antigravity/memory/ceo/backups")
PROJECT_ROOT = os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula"
)

# Categories for file changes
CATEGORIES = {
    "directives/": "Directives (SOPs)",
    "execution/": "Execution Scripts",
    "SabboOS/Agents/": "Agent Directives",
    "SabboOS/": "SabboOS",
    "bots/": "Bot Configs",
    "clients/": "Clients",
    "templates/": "Templates",
    ".claude/": "Claude Config",
}


def parse_session_log():
    """Parse session-log.txt into structured events."""
    if not SESSION_LOG.exists():
        return {"files_modified": [], "commands_run": [], "raw_lines": 0}

    content = SESSION_LOG.read_text(encoding="utf-8", errors="ignore")
    lines = content.strip().splitlines()

    files_modified = []
    commands_run = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Parse file modifications: [HH:MM:SS] File modified: /path/to/file
        file_match = re.match(r'\[[\d:]+\]\s+File modified:\s*(.+)', line)
        if file_match:
            filepath = file_match.group(1).strip()
            if filepath and filepath != "?":
                files_modified.append(filepath)
            continue

        # Parse commands: [HH:MM:SS] Ran: command text
        cmd_match = re.match(r'\[[\d:]+\]\s+Ran:\s*(.+)', line)
        if cmd_match:
            cmd = cmd_match.group(1).strip()
            if cmd:
                commands_run.append(cmd)

    return {
        "files_modified": files_modified,
        "commands_run": commands_run,
        "raw_lines": len(lines),
    }


def categorize_file(filepath):
    """Determine which brain.md category a file belongs to."""
    for prefix, category in CATEGORIES.items():
        if prefix in filepath:
            return category
    return "Other"


def deduplicate_files(files):
    """Remove duplicate file paths, keep order."""
    seen = set()
    result = []
    for f in files:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


def generate_brain_update(session_data):
    """Generate the brain.md update text from session data."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    files = deduplicate_files(session_data["files_modified"])
    commands = session_data["commands_run"]

    if not files and not commands:
        return None  # Nothing to update

    # Group files by category
    by_category = {}
    for f in files:
        cat = categorize_file(f)
        by_category.setdefault(cat, []).append(f)

    # Build the session summary entry
    lines = []
    lines.append(f"\n### {date_str} {time_str} — Auto-captured session")

    if files:
        lines.append(f"- {len(files)} files modified across {len(by_category)} categories")
        for cat, cat_files in sorted(by_category.items()):
            file_names = [Path(f).name for f in cat_files]
            lines.append(f"  - **{cat}**: {', '.join(file_names)}")

    if commands:
        # Only log interesting commands (skip simple reads)
        interesting = [c for c in commands if len(c) > 10]
        if interesting:
            lines.append(f"- {len(interesting)} commands executed")

    return "\n".join(lines) + "\n"


def generate_asset_entries(session_data):
    """Generate Asset Registry entries for new/modified files."""
    files = deduplicate_files(session_data["files_modified"])
    if not files:
        return None

    entries = []
    for f in files:
        # Only track significant files (skip .tmp, backups, logs)
        if ".tmp/" in f or ".bak" in f or "session-log" in f:
            continue
        cat = categorize_file(f)
        if cat == "Other":
            continue
        basename = Path(f).name
        entries.append(f"- `{basename}` — modified {datetime.now().strftime('%Y-%m-%d')}")

    return entries if entries else None


def update_brain_meta(content):
    """Update the Meta section timestamps."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Update Last Session
    content = re.sub(
        r'Last Session: .+',
        f'Last Session: {now_str}',
        content
    )

    # Increment total sessions
    match = re.search(r'Total Sessions Tracked: (\d+)', content)
    if match:
        count = int(match.group(1)) + 1
        content = re.sub(
            r'Total Sessions Tracked: \d+',
            f'Total Sessions Tracked: {count}',
            content
        )

    return content


def append_to_section(content, section_header, new_text):
    """Append text to a specific section in brain.md (before the next --- separator)."""
    # Find the section
    pattern = rf'(## {re.escape(section_header)}\n.*?)((?=\n---\n)|\Z)'
    match = re.search(pattern, content, re.DOTALL)

    if match:
        insert_point = match.end(1)
        content = content[:insert_point] + "\n" + new_text + content[insert_point:]

    return content


def create_backup():
    """Create a daily backup of brain.md, keep last 7."""
    if not BRAIN_PATH.exists():
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    backup_path = BACKUP_DIR / f"brain.md.bak-{date_str}"

    # Only backup once per day
    if not backup_path.exists():
        shutil.copy2(BRAIN_PATH, backup_path)

    # Clean old backups (keep last 7)
    backups = sorted(BACKUP_DIR.glob("brain.md.bak-*"))
    while len(backups) > 7:
        backups[0].unlink()
        backups.pop(0)


def main():
    # Ensure brain directory exists
    BRAIN_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not BRAIN_PATH.exists():
        print("[update_ceo_brain] brain.md not found — skipping")
        return

    # Create daily backup
    create_backup()

    # Parse session log
    session_data = parse_session_log()

    if session_data["raw_lines"] == 0:
        print("[update_ceo_brain] Empty session log — nothing to update")
        return

    # Read current brain
    brain_content = BRAIN_PATH.read_text(encoding="utf-8", errors="ignore")

    # Update Meta timestamps
    brain_content = update_brain_meta(brain_content)

    # Generate and append session summary
    session_summary = generate_brain_update(session_data)
    if session_summary:
        brain_content = append_to_section(brain_content, "Session Summaries", session_summary)

    # Write updated brain
    BRAIN_PATH.write_text(brain_content, encoding="utf-8")

    files_count = len(deduplicate_files(session_data["files_modified"]))
    print(f"[update_ceo_brain] Brain updated: {files_count} file changes captured, meta timestamps refreshed")


if __name__ == "__main__":
    main()
