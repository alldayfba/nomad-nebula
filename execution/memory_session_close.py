#!/usr/bin/env python3
"""
memory_session_close.py — Stop hook script for session close.

Reads session-log.txt, creates a session_context record, and generates
event memories for significant file changes.

Usage (called by Stop hook in ~/.claude/settings.json):
    python3 execution/memory_session_close.py
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from execution.memory_store import MemoryStore, DB_PATH

SESSION_LOG = Path.home() / ".claude" / "session-log.txt"

# Directories that matter for memory tracking
TRACKED_DIRS = {"directives", "execution", "SabboOS", "bots", "clients", "templates", ".claude"}


def main():
    store = MemoryStore(DB_PATH)

    # Read session log
    if not SESSION_LOG.exists():
        return

    text = SESSION_LOG.read_text(errors="replace").strip()
    if not text:
        return

    lines = text.split("\n")
    file_mods = []
    commands = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Parse file modifications
        mod_match = re.match(r'\[[\d:]+\]\s*File modified:\s*(.+)', line)
        if mod_match:
            file_mods.append(mod_match.group(1).strip())
            continue
        # Parse commands
        cmd_match = re.match(r'\[[\d:]+\]\s*Ran:\s*(.+)', line)
        if cmd_match:
            commands.append(cmd_match.group(1).strip())

    # Create session context
    session_id = "session-{}".format(datetime.now().strftime("%Y%m%d-%H%M%S"))

    # Infer topics from file paths
    topics = set()
    for f in file_mods:
        parts = Path(f).parts
        for part in parts:
            if part in TRACKED_DIRS:
                topics.add(part)

    # Build summary
    summary_parts = []
    if file_mods:
        summary_parts.append("{} files modified".format(len(file_mods)))
    if commands:
        summary_parts.append("{} commands run".format(len(commands)))
    summary = "; ".join(summary_parts) if summary_parts else "No tracked activity"

    store.create_session(
        session_id=session_id,
        topics=", ".join(sorted(topics)),
        summary=summary,
        files_modified=file_mods,
    )

    # Create event memories for significant file changes
    for f in file_mods:
        # Only track files in important directories
        rel_parts = Path(f).parts
        is_tracked = any(d in rel_parts for d in TRACKED_DIRS)
        if not is_tracked:
            continue

        filename = os.path.basename(f)
        # Categorize
        if "directive" in f.lower():
            category = "agent"
        elif "execution" in f.lower():
            category = "technical"
        elif "SabboOS" in f.lower() or "bots" in f.lower():
            category = "agent"
        elif "client" in f.lower():
            category = "client"
        else:
            category = "general"

        store.add(
            type="event",
            category=category,
            title="File modified: {}".format(filename),
            content="Path: {}\nSession: {}".format(f, session_id),
            source="session_close",
            source_session=session_id,
            tags="file_change",
            skip_dedup=True,  # File changes are always new events
        )

    # Clear session log for next session
    try:
        SESSION_LOG.write_text("")
    except OSError:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never crash the Stop hook — fail silently
        pass
