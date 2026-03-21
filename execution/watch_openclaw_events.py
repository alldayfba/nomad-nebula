#!/usr/bin/env python3
"""
watch_openclaw_events.py — OC → CC sync daemon.

Watches two sources for new OpenClaw activity and stores it in Claude Code's memory.db:

  1. /Users/SabboOpenClawAI/.openclaw/workspace/main/memory/
     OpenClaw session-memory hook writes YYYY-MM-DD-slug.md files here on /new or /reset.

  2. /Users/Shared/antigravity/memory/sync/event-bus/oc/
     OpenClaw hook scripts write JSON events here.

Runs as launchd daemon on sabbojb (com.sabbo.openclaw-sync).
Poll interval: 30 seconds.

Usage:
    python3 execution/watch_openclaw_events.py          # run as daemon
    python3 execution/watch_openclaw_events.py --once   # single scan + exit
"""
from __future__ import annotations

import fcntl
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT     = Path(__file__).parent.parent
OC_SESSION_DIR   = Path("/Users/SabboOpenClawAI/.openclaw/workspace/main/memory")
OC_SESSIONS_DIR  = Path("/Users/SabboOpenClawAI/.openclaw/agents/main/sessions")
OC_WORKSPACE     = Path("/Users/SabboOpenClawAI/.openclaw/workspace/main")
OC_HEARTBEAT_MD  = OC_WORKSPACE / "HEARTBEAT.md"
EVENT_BUS_OC     = Path("/Users/Shared/antigravity/memory/sync/event-bus/oc")
EVENT_BUS_CC     = Path("/Users/Shared/antigravity/memory/sync/event-bus/cc")
PROCESSED_LOG    = Path("/Users/Shared/antigravity/memory/sync/event-bus/.processed_oc.json")
OC_LAST_MSG_FILE = Path("/Users/Shared/antigravity/memory/sync/oc-last-message.json")
LOG_FILE         = Path("/Users/sabbojb/.claude/openclaw-sync.log")

POLL_INTERVAL        = 30   # seconds
MAX_PROCESSED        = 2000  # MED-2: cap processed set size
CC_BUS_MAX_AGE_DAYS  = 7     # MED-1: delete cc/ files older than this
MEMORY_EXPORT_EVERY  = 10    # export CC memory to OC workspace every N poll cycles

sys.path.insert(0, str(PROJECT_ROOT))


# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    # MIN-5: use UTC timestamps for consistency with bridge
    ts   = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _rotate_log() -> None:
    """MIN-2: rotate log file when it exceeds 5 MB."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 5 * 1024 * 1024:
            backup = LOG_FILE.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            LOG_FILE.rename(backup)
    except Exception:
        pass


# ── Processed-file tracking ───────────────────────────────────────────────────

def load_processed() -> set:
    if PROCESSED_LOG.exists():
        try:
            return set(json.loads(PROCESSED_LOG.read_text()))
        except Exception:
            pass
    return set()


def save_processed(processed: set) -> None:
    # CRIT-2: exclusive lock; MED-2: cap entries
    PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_LOG.touch(exist_ok=True)
    trimmed = sorted(processed)[-MAX_PROCESSED:]
    with open(PROCESSED_LOG, "r+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(trimmed, indent=2))
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


# ── Memory store helper ───────────────────────────────────────────────────────

def store_entry(entry: dict) -> None:
    from execution.memory_store import MemoryStore, DB_PATH
    store = MemoryStore(DB_PATH)
    store.add(
        type=entry.get("type", "event"),
        category=entry.get("category", "general"),
        title=entry["title"],
        content=entry.get("content", ""),
        source=entry.get("source", "openclaw"),
        tags=entry.get("tags", "openclaw"),
    )


# ── Source 1: OpenClaw session memory (.md files) ────────────────────────────

def scan_session_memory(processed: set) -> int:
    """Read new YYYY-MM-DD-slug.md files from OC session memory dir."""
    if not OC_SESSION_DIR.exists():
        return 0

    stored = 0
    for md_file in sorted(OC_SESSION_DIR.glob("*.md")):
        key = f"session:{md_file.name}"
        if key in processed:
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            if not content.strip():
                processed.add(key)
                continue

            # Parse filename: YYYY-MM-DD-slug.md
            stem  = md_file.stem   # e.g. "2026-03-16-vendor-pitch"
            parts = stem.split("-", 3)
            date  = "-".join(parts[:3]) if len(parts) >= 3 else "unknown"
            slug  = parts[3].replace("-", " ") if len(parts) == 4 else stem

            title   = f"OpenClaw session [{date}]: {slug}"
            body    = content[:2000] + ("…" if len(content) > 2000 else "")

            entry = {
                "type":     "event",
                "category": "general",
                "title":    title,
                "content":  body,
                "source":   "openclaw_session",
                "tags":     "openclaw,session,conversation",
            }
            store_entry(entry)
            processed.add(key)
            stored += 1
            log(f"Synced OC session: {md_file.name}")

        except Exception as e:
            log(f"Error reading {md_file.name}: {e}")

    return stored


# ── Source 2: OpenClaw event bus JSON files ───────────────────────────────────

def scan_event_bus(processed: set) -> int:
    """Read new JSON events from event-bus/oc/."""
    if not EVENT_BUS_OC.exists():
        return 0

    stored = 0
    for json_file in sorted(EVENT_BUS_OC.glob("*.json")):
        key = f"bus:{json_file.name}"
        if key in processed:
            continue

        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))

            # Validate minimal required fields
            if not data.get("title"):
                processed.add(key)
                continue

            entry = {
                "type":     data.get("type", "event"),
                "category": data.get("category", "general"),
                "title":    data["title"],
                "content":  data.get("content", json.dumps(data, indent=2)[:1000]),
                "source":   data.get("source", "openclaw"),
                "tags":     data.get("tags", "openclaw"),
            }
            store_entry(entry)
            processed.add(key)
            stored += 1
            log(f"Synced OC event: {json_file.name}")

        except Exception as e:
            log(f"Error reading {json_file.name}: {e}")

    return stored


# ── MED-1: CC event bus cleanup ───────────────────────────────────────────────

def cleanup_cc_event_bus() -> None:
    """Delete cc/ event bus files older than CC_BUS_MAX_AGE_DAYS to prevent unbounded growth."""
    if not EVENT_BUS_CC.exists():
        return
    try:
        cutoff = time.time() - (CC_BUS_MAX_AGE_DAYS * 86400)
        deleted = 0
        for f in EVENT_BUS_CC.glob("*.json"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
            except Exception:
                pass
        if deleted:
            log(f"Cleaned up {deleted} old cc/ event bus files")
    except Exception as e:
        log(f"CC bus cleanup error: {e}")


# ── Live OC last-message tracker ─────────────────────────────────────────────

def track_latest_oc_message() -> None:
    """Read the most recent user message from OC's live session JSONL and write
    it to OC_LAST_MSG_FILE so Claude Code always knows what Sabbo last said to OC."""
    if not OC_SESSIONS_DIR.exists():
        return
    try:
        # Find most recently modified .jsonl (active session)
        jsonl_files = [
            f for f in OC_SESSIONS_DIR.glob("*.jsonl")
            if not f.name.endswith(".deleted" + f.suffix)
            and ".deleted." not in f.name
        ]
        if not jsonl_files:
            return
        latest = max(jsonl_files, key=lambda f: f.stat().st_mtime)

        # Walk lines in reverse to find the last user message
        lines = latest.read_text(encoding="utf-8", errors="ignore").splitlines()
        last_user_msg = None
        last_ts = None
        for raw in reversed(lines):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                msg = obj.get("message", {})
                if msg.get("role") == "user":
                    content = msg.get("content", [])
                    text = ""
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text = part.get("text", "")
                                break
                    else:
                        text = str(content)
                    # Strip OC metadata preamble
                    if "Conversation info (untrusted metadata)" in text:
                        text = text.split("```\n\n", 1)[-1].strip()
                    if text:
                        last_user_msg = text
                        last_ts = obj.get("timestamp", "")
                        break
            except Exception:
                continue

        if not last_user_msg:
            return

        payload = {
            "last_message": last_user_msg,
            "timestamp": last_ts,
            "session_file": latest.name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        OC_LAST_MSG_FILE.parent.mkdir(parents=True, exist_ok=True)
        OC_LAST_MSG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    except Exception as e:
        log(f"track_latest_oc_message error: {e}")


# ── GAP-1: Live heartbeat stamp ───────────────────────────────────────────────

def update_heartbeat() -> None:
    """Stamp this daemon's last-poll time into HEARTBEAT.md so OC sees live status."""
    if not OC_HEARTBEAT_MD.exists():
        return
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        content = OC_HEARTBEAT_MD.read_text(encoding="utf-8")
        # Update the openclaw-sync row's Last Check cell
        content = re.sub(
            r"(openclaw-sync daemon\s*\|[^|]*\|)[^\n]*",
            rf"\1 ✓ running | last poll {ts}",
            content,
        )
        OC_HEARTBEAT_MD.write_text(content, encoding="utf-8")
    except Exception:
        pass  # Never crash the daemon over a heartbeat write


# ── Main loop ─────────────────────────────────────────────────────────────────

_poll_count = 0


def run_once() -> int:
    global _poll_count
    _poll_count += 1

    processed = load_processed()
    n  = scan_session_memory(processed)
    n += scan_event_bus(processed)
    if n:
        save_processed(processed)
    cleanup_cc_event_bus()      # MED-1
    update_heartbeat()          # GAP-1
    track_latest_oc_message()   # always know what Sabbo last said to OC

    # Export full CC memory to OC workspace every MEMORY_EXPORT_EVERY cycles
    if _poll_count % MEMORY_EXPORT_EVERY == 1:  # also runs on first cycle
        try:
            from execution.export_cc_memory_to_oc import export
            count = export()
            if count:
                log(f"CC memory exported to OC workspace: {count} entries")
        except Exception as e:
            log(f"CC memory export error: {e}")

    return n


def main() -> None:
    once = "--once" in sys.argv

    _rotate_log()  # MIN-2: rotate before first write

    log("watch_openclaw_events.py started")
    log(f"Watching session memory: {OC_SESSION_DIR}")
    log(f"Watching event bus:      {EVENT_BUS_OC}")

    if once:
        n = run_once()
        log(f"Scan complete: {n} new entries synced")
        return

    while True:
        try:
            n = run_once()
            if n:
                log(f"Synced {n} new OpenClaw entries to memory.db")
        except Exception as e:
            log(f"ERROR: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
