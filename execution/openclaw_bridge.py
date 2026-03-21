#!/usr/bin/env python3
"""
openclaw_bridge.py — Bidirectional sync between Claude Code and OpenClaw.

Channels:
  CC → OC: Claude Code file changes/builds are written to:
             1. OpenClaw workspace MEMORY.md (loaded on every agent bootstrap)
             2. Shared event bus cc/ dir (audit trail, CC-readable history)

  OC → CC: OpenClaw session memory files are watched by watch_openclaw_events.py,
             which reads them and stores in memory.db via memory_store.py.
             Also: watch_inbox.py handles sync_memory task type for explicit pushes.

Usage:
    # From memory_file_change.py (PostToolUse hook):
    python3 execution/openclaw_bridge.py notify --file "/path/to/file" --title "Built X" --category technical

    # Standalone event write:
    python3 execution/openclaw_bridge.py event --type decision --title "X" --content "Y" --tags "a,b"
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT        = Path(__file__).parent.parent
OC_WORKSPACE        = Path("/Users/SabboOpenClawAI/.openclaw/workspace/main")
OC_MEMORY_MD        = OC_WORKSPACE / "MEMORY.md"
OC_SESSION_MEMORY   = OC_WORKSPACE / "memory"
EVENT_BUS_CC        = Path("/Users/Shared/antigravity/memory/sync/event-bus/cc")
EVENT_BUS_OC        = Path("/Users/Shared/antigravity/memory/sync/event-bus/oc")
PROCESSED_LOG       = Path("/Users/Shared/antigravity/memory/sync/event-bus/.processed_oc.json")

# Max entries to keep in OpenClaw MEMORY.md CC section (rolling window)
MAX_CC_ENTRIES      = 30


# ── CC → OC: notify OpenClaw of a Claude Code build/file change ──────────────

def notify_build(file_path: str, category: str, title: str, summary: str = "") -> None:
    """Write a build event into OpenClaw's MEMORY.md and the shared event bus."""
    now = datetime.now(timezone.utc)
    ts  = now.strftime("%Y-%m-%d %H:%M UTC")
    ts_file = now.strftime("%Y%m%d_%H%M%S_%f")

    # 1. Append to OpenClaw MEMORY.md (rolling, max MAX_CC_ENTRIES)
    _update_oc_memory_md(ts, title, file_path, category, summary)

    # 2. Write to shared event bus (audit trail)
    event = {
        "source":    "claude_code",
        "timestamp": now.isoformat(),
        "type":      "build",
        "category":  category,
        "title":     title,
        "file":      file_path,
        "summary":   summary,
    }
    event_file = EVENT_BUS_CC / f"{ts_file}-build.json"
    _write_json(event_file, event)


def write_event(event_type: str, title: str, content: str, tags: str = "") -> None:
    """Write an arbitrary Claude Code event to the shared bus (decisions, learnings, etc.)."""
    now = datetime.now(timezone.utc)
    ts_file = now.strftime("%Y%m%d_%H%M%S_%f")

    event = {
        "source":    "claude_code",
        "timestamp": now.isoformat(),
        "type":      event_type,
        "title":     title,
        "content":   content,
        "tags":      tags,
    }
    event_file = EVENT_BUS_CC / f"{ts_file}-{event_type}.json"
    _write_json(event_file, event)

    # Also inject into OpenClaw MEMORY.md for context awareness
    ts = now.strftime("%Y-%m-%d %H:%M UTC")
    _update_oc_memory_md(ts, title, "", event_type, content)


def _update_oc_memory_md(ts: str, title: str, file_path: str, category: str, summary: str) -> None:
    """Maintain a rolling Claude Code context section in OpenClaw's MEMORY.md."""
    try:
        OC_MEMORY_MD.parent.mkdir(parents=True, exist_ok=True)
        OC_MEMORY_MD.touch(exist_ok=True)

        cc_header  = "## Claude Code — Recent Activity\n"
        cc_marker  = "<!-- cc-activity-start -->"
        cc_end     = "<!-- cc-activity-end -->"

        # Build the new entry line
        file_part = f" · `{Path(file_path).name}`" if file_path else ""
        new_entry = f"- `{ts}` [{category}] {title}{file_part}"
        if summary:
            new_entry += f"\n  > {summary[:120]}"

        # CRIT-1: exclusive lock for the entire read-modify-write cycle
        with open(OC_MEMORY_MD, "r+", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                existing = fh.read()

                if cc_marker in existing and cc_end in existing:
                    pre  = existing[:existing.index(cc_marker)]
                    body = existing[existing.index(cc_marker)+len(cc_marker):existing.index(cc_end)]
                    post = existing[existing.index(cc_end)+len(cc_end):]

                    lines = [l for l in body.strip().splitlines() if l.strip() and not l.startswith("#")]
                    lines = [new_entry] + lines
                    # Trim to MAX_CC_ENTRIES — keep continuation lines (  >) with their parent
                    entry_count = 0
                    kept: list[str] = []
                    for l in lines:
                        if l.startswith("- `"):
                            entry_count += 1
                            if entry_count > MAX_CC_ENTRIES:
                                break
                        kept.append(l)

                    new_body = "\n".join(kept)
                    new_content = f"{pre}{cc_marker}\n{cc_header}\n{new_body}\n{cc_end}{post}"
                else:
                    section = (
                        f"\n{cc_marker}\n"
                        f"{cc_header}\n"
                        f"{new_entry}\n"
                        f"{cc_end}\n"
                    )
                    new_content = (existing.rstrip() + "\n" + section) if existing.strip() else section

                fh.seek(0)
                fh.truncate()
                fh.write(new_content)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

        OC_MEMORY_MD.chmod(0o664)

    except Exception as e:
        sys.stderr.write(f"openclaw_bridge warning: {e}\n")  # MIN-4: never silently swallow


# ── OC → CC: read OpenClaw session memory files and store in memory.db ───────

def sync_oc_sessions(dry_run: bool = False) -> list[dict]:
    """
    Scan OC session memory dir for new files, parse them, return list of entries.
    Caller (watch_openclaw_events.py) stores them in memory.db.
    Marks processed files in PROCESSED_LOG.
    """
    processed = _load_processed()
    new_entries = []

    if not OC_SESSION_MEMORY.exists():
        return []

    for md_file in sorted(OC_SESSION_MEMORY.glob("*.md")):
        key = f"session:{md_file.name}"  # MED-4: match daemon's key format
        if key in processed:
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            entry = _parse_session_memory(md_file.name, content)
            if entry:
                new_entries.append(entry)
                if not dry_run:
                    processed.add(key)
        except Exception:
            pass

    if not dry_run and new_entries:
        _save_processed(processed)

    return new_entries


def _parse_session_memory(filename: str, content: str) -> dict | None:
    """Parse an OpenClaw session memory file into a memory_store entry."""
    if not content.strip():
        return None

    # Extract date from filename: YYYY-MM-DD-slug.md
    parts = filename.replace(".md", "").split("-", 3)
    date_str = "-".join(parts[:3]) if len(parts) >= 3 else "unknown"

    # Use filename slug as title, content as body
    slug = parts[3] if len(parts) == 4 else filename.replace(".md", "")
    title = f"OpenClaw session: {slug} ({date_str})"

    # Truncate very long sessions to first 2000 chars
    body = content[:2000] + ("..." if len(content) > 2000 else "")

    return {
        "type":     "event",
        "category": "general",
        "title":    title,
        "content":  body,
        "source":   "openclaw_session",
        "tags":     "openclaw,session,conversation",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    path.chmod(0o664)


def _load_processed() -> set:
    if PROCESSED_LOG.exists():
        try:
            return set(json.loads(PROCESSED_LOG.read_text()))
        except Exception:
            pass
    return set()


def _save_processed(processed: set) -> None:
    # CRIT-2: exclusive lock; MED-2: cap at 2000 entries
    PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_LOG.touch(exist_ok=True)
    trimmed = sorted(processed)[-2000:]
    with open(PROCESSED_LOG, "r+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(trimmed, indent=2))
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="openclaw_bridge — CC ↔ OC sync")
    sub = parser.add_subparsers(dest="cmd")

    # notify: CC → OC file change
    p_notify = sub.add_parser("notify", help="Notify OpenClaw of a CC build")
    p_notify.add_argument("--file",     default="")
    p_notify.add_argument("--title",    default="File modified")
    p_notify.add_argument("--category", default="technical")
    p_notify.add_argument("--summary",  default="")

    # event: CC → OC arbitrary event
    p_event = sub.add_parser("event", help="Write an event to the shared bus")
    p_event.add_argument("--type",    default="event")
    p_event.add_argument("--title",   required=True)
    p_event.add_argument("--content", default="")
    p_event.add_argument("--tags",    default="")

    # sync: OC → CC (print new session entries, used by watcher)
    p_sync = sub.add_parser("sync", help="Sync new OC session memory to CC")
    p_sync.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.cmd == "notify":
        notify_build(args.file, args.category, args.title, args.summary)
        print(f"✓ Notified OpenClaw: {args.title}")

    elif args.cmd == "event":
        write_event(args.type, args.title, args.content, args.tags)
        print(f"✓ Event written: {args.title}")

    elif args.cmd == "sync":
        entries = sync_oc_sessions(dry_run=args.dry_run)
        print(json.dumps(entries, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
