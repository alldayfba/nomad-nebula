#!/usr/bin/env python3
"""
memory_file_change.py — PostToolUse hook for tracking file changes.

Receives file path as argument. If in a tracked directory, creates a
lightweight event memory. Target: <500ms.

Usage (called by PostToolUse hook in ~/.claude/settings.json):
    python3 execution/memory_file_change.py "/path/to/modified/file"
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Directories worth tracking
TRACKED_DIRS = {"directives", "execution", "SabboOS", "bots", "clients", ".claude"}

# Skip patterns (too noisy)
SKIP_PATTERNS = {".tmp", "__pycache__", ".pyc", "node_modules", ".git", "session-log"}


def main():
    if len(sys.argv) < 2:
        return

    file_path = sys.argv[1]
    if not file_path or file_path == "?":
        return

    # Skip noisy paths
    for skip in SKIP_PATTERNS:
        if skip in file_path:
            return

    # Check if in tracked directory
    parts = Path(file_path).parts
    is_tracked = any(d in parts for d in TRACKED_DIRS)
    if not is_tracked:
        return

    # Import lazily (speed matters in hooks)
    from execution.memory_store import MemoryStore, DB_PATH

    filename = os.path.basename(file_path)

    # Categorize
    if "directive" in file_path.lower():
        category = "agent"
    elif "execution" in file_path.lower():
        category = "technical"
    elif "SabboOS" in file_path.lower() or "bots" in file_path.lower():
        category = "agent"
    elif "client" in file_path.lower():
        category = "client"
    else:
        category = "general"

    store = MemoryStore(DB_PATH)
    store.add(
        type="event",
        category=category,
        title="File modified: {}".format(filename),
        content="Path: {}\nTimestamp: {}".format(file_path, datetime.now().isoformat()),
        source="file_change_hook",
        tags="file_change",
        skip_dedup=True,
    )

    # Notify OpenClaw so it has context on what Claude Code just built
    from execution.openclaw_bridge import notify_build
    notify_build(file_path, category, "File modified: {}".format(filename))

    # Instantly refresh CC_KNOWLEDGE.md so OC sees new tools/agents/directives immediately
    try:
        from execution.export_cc_memory_to_oc import export
        export(quick=False)
    except Exception:
        pass  # Never crash a hook


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never crash a hook
        pass
