#!/usr/bin/env python3
"""
Script: save_session.py
Purpose: Capture and persist Claude Code session context to shared memory so nothing is lost between sessions
Inputs:  --note "key context to save" (optional manual note)
         --auto (reads session-log.txt and saves recent activity automatically)
Outputs: Appends to /Users/Shared/antigravity/memory/global/session-history.md
"""

import argparse
import collections
import os
import sys
from pathlib import Path
from datetime import datetime

SESSION_LOG = Path.home() / ".claude" / "session-log.txt"
MEMORY_ROOT = Path("/Users/Shared/antigravity/memory")
SESSION_HISTORY = MEMORY_ROOT / "global" / "session-history.md"
MAX_LOG_LINES = 50  # how many recent log lines to capture on --auto


def get_recent_log(n=MAX_LOG_LINES) -> str:
    """Read last N lines from session-log.txt."""
    if not SESSION_LOG.exists():
        return "(no session log found)"
    lines = SESSION_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
    recent = list(collections.deque(lines, maxlen=n))
    return "\n".join(recent) if recent else "(session log is empty)"


LOCAL_SESSION_HISTORY = Path.home() / ".claude" / "session-history.md"


def append_to_history(entry: str):
    """Append a formatted entry to session-history.md. Falls back to local if shared is not writable."""
    targets = []

    # Try shared path first (cross-user)
    try:
        MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
        (MEMORY_ROOT / "global").mkdir(parents=True, exist_ok=True)
        targets.append(SESSION_HISTORY)
    except PermissionError:
        pass

    # Always write to local as well (guaranteed writable)
    LOCAL_SESSION_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    targets.append(LOCAL_SESSION_HISTORY)

    for target in targets:
        # Initialize file with header if it doesn't exist
        if not target.exists():
            target.write_text(
                "# Session History — SabboOS\n\n"
                "> Running log of all Claude Code sessions. "
                "Read this at the start of any session to restore context.\n\n",
                encoding="utf-8"
            )
            try:
                os.chmod(target, 0o660)
            except PermissionError:
                pass

        try:
            with open(target, "a", encoding="utf-8") as f:
                f.write(entry)
            print(f"[save_session] ✓ Context saved to {target}")
        except PermissionError:
            print(f"[save_session] ⚠ Can't write to {target} (permission denied, skipping)")


def auto_save():
    """Auto-capture session activity from session-log and save to history."""
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    recent_log = get_recent_log()

    entry = f"""
---

## Session — {date}

### Files modified this session
```
{recent_log}
```

### Status
Auto-captured on session close. For detailed context, check the session above or review the files modified.

"""
    append_to_history(entry)

    # Clear session log after saving so next session starts fresh
    if SESSION_LOG.exists():
        SESSION_LOG.write_text("", encoding="utf-8")
    print(f"[save_session] Session log cleared for fresh start next session.")


def manual_save(note: str):
    """Save a manual note/context entry."""
    date = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"""
---

## Note — {date}

{note}

"""
    append_to_history(entry)


def main():
    parser = argparse.ArgumentParser(description="Save Claude Code session context to persistent memory")
    parser.add_argument("--note", help="Save a specific note or context snippet to memory")
    parser.add_argument("--auto", action="store_true", help="Auto-capture session log on session close")
    parser.add_argument("--read", action="store_true", help="Print the last 20 session history entries")
    args = parser.parse_args()

    if args.read:
        if SESSION_HISTORY.exists():
            lines = SESSION_HISTORY.read_text(encoding="utf-8").splitlines()
            recent = list(collections.deque(lines, maxlen=100))
            print("\n".join(recent))
        else:
            print("No session history yet.")
        return

    if args.note:
        manual_save(args.note)
        return

    if args.auto:
        auto_save()
        return

    print("Usage: save_session.py --note 'context' | --auto | --read")
    sys.exit(1)


if __name__ == "__main__":
    main()
