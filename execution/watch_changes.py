#!/usr/bin/env python3
"""
Script: watch_changes.py
Purpose: Watch key project directories for file changes and write a shared change log.
         Enables bidirectional awareness between OpenClaw and Claude Code.
Inputs:  None (runs as daemon, polls every 10 seconds)
Outputs: /Users/Shared/antigravity/memory/sync/changes.json
"""

import fcntl
import json
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# Directories to watch for changes
WATCH_DIRS = [
    Path("/Users/Shared/antigravity/projects/nomad-nebula/directives"),
    Path("/Users/Shared/antigravity/projects/nomad-nebula/execution"),
    Path("/Users/Shared/antigravity/projects/nomad-nebula/SabboOS"),
    Path("/Users/Shared/antigravity/projects/nomad-nebula/bots"),
    Path("/Users/sabbojb/.openclaw/workspace"),
    Path("/Users/Shared/antigravity/memory"),
]

SYNC_DIR = Path("/Users/Shared/antigravity/memory/sync")
CHANGES_FILE = SYNC_DIR / "changes.json"
POLL_INTERVAL = 10  # seconds
MAX_CHANGES = 100  # keep last N changes
DEBOUNCE_SECONDS = 5  # ignore rapid re-modifications within this window

# File extensions to watch
WATCH_EXTENSIONS = {".md", ".py", ".json", ".txt", ".yaml", ".yml", ".toml"}

# Files/dirs to ignore
IGNORE_PATTERNS = {"__pycache__", ".pyc", ".tmp", "node_modules", ".git", "changes.json", "notifications.json"}

# Telegram notifications
SABBO_CHAT_ID = "2135766059"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
_TELEGRAM_BOT_TOKEN = None
# Cooldown: max 1 alert per category per 5 minutes
_alert_cooldowns = {}  # category -> last_alert_time
ALERT_COOLDOWN_SECONDS = 300

# Directories that warrant Telegram alerts when files are created/modified
IMPORTANT_DIRS = {"directives", "SabboOS", "Agents"}

# Auto-heartbeat: drop a heartbeat task in inbox every 30 min so OpenClaw stays aware
HEARTBEAT_INTERVAL = 1800  # 30 minutes
INBOX_DIR = Path("/Users/Shared/antigravity/inbox")

# Watchdog: check if sibling daemons are alive
WATCHDOG_INTERVAL = 300  # 5 minutes
_last_watchdog_check = 0



def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _load_telegram_token():
    """Load Telegram bot token from OpenClaw config."""
    global _TELEGRAM_BOT_TOKEN
    if _TELEGRAM_BOT_TOKEN:
        return _TELEGRAM_BOT_TOKEN
    try:
        with open(OPENCLAW_CONFIG) as f:
            config = json.load(f)
        _TELEGRAM_BOT_TOKEN = config.get("channels", {}).get("telegram", {}).get("botToken", "")
    except Exception as e:
        log(f"Could not load Telegram token: {e}")
        _TELEGRAM_BOT_TOKEN = ""
    return _TELEGRAM_BOT_TOKEN


def send_telegram_alert(message: str, category: str = "general"):
    """Push a notification to Sabbo via Telegram with cooldown."""
    now = time.time()
    if category in _alert_cooldowns and (now - _alert_cooldowns[category]) < ALERT_COOLDOWN_SECONDS:
        log(f"Telegram alert throttled (cooldown): {category}")
        return
    token = _load_telegram_token()
    if not token:
        log("Telegram alert skipped: no bot token")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": SABBO_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        _alert_cooldowns[category] = now
        log(f"Telegram alert sent: {message[:60]}...")
    except Exception as e:
        log(f"Telegram alert failed: {e}")


def is_important_change(filepath: str, action: str) -> bool:
    """Determine if a file change warrants a Telegram alert."""
    # New files in important directories
    for d in IMPORTANT_DIRS:
        if f"/{d}/" in filepath and action == "created":
            return True
    # Deleted files are always notable
    if action == "deleted":
        return True
    return False


def drop_heartbeat_task():
    """Drop a heartbeat task in the inbox so OpenClaw checks sync files."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    task = {
        "task": "reindex",
        "agent": "auto-heartbeat",
        "hours": 1,
        "description": "Auto-scheduled sync check",
    }
    task_file = INBOX_DIR / f"auto-heartbeat-{ts}.json"
    try:
        with open(task_file, "w") as f:
            json.dump(task, f, indent=2)
        os.chmod(task_file, 0o660)
        log(f"Auto-heartbeat dropped: {task_file.name}")
    except Exception as e:
        log(f"Auto-heartbeat failed: {e}")


def check_daemon_health():
    """Check if sibling daemons are alive and alert if not."""
    global _last_watchdog_check
    now = time.time()
    if (now - _last_watchdog_check) < WATCHDOG_INTERVAL:
        return
    _last_watchdog_check = now

    import subprocess
    try:
        result = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=10
        )
        output = result.stdout
        daemons = {
            "com.sabbo.inbox-watcher": "Inbox Watcher",
            "com.sabbo.change-watcher": "Change Watcher",
        }
        dead = []
        for label, name in daemons.items():
            if label not in output:
                dead.append(name)
            else:
                for line in output.splitlines():
                    if label in line:
                        parts = line.split()
                        # launchctl list format: PID ExitCode Label
                        # If PID is "-", daemon is not running
                        if parts[0] == "-":
                            dead.append(f"{name} (exit code: {parts[1]})")
                        break

        if dead:
            send_telegram_alert(
                f"*Daemon Health Alert*\n"
                f"Down: {', '.join(dead)}\n"
                f"Run `launchctl kickstart` to restart.",
                category="watchdog"
            )
    except Exception as e:
        log(f"Watchdog check failed: {e}")


def should_ignore(path: Path) -> bool:
    """Check if a file should be ignored."""
    for part in path.parts:
        if part in IGNORE_PATTERNS:
            return True
    if path.suffix not in WATCH_EXTENSIONS:
        return True
    return False


def scan_files(dirs: list) -> dict:
    """Build a dict of file_path -> (mtime, size) for all watched files."""
    snapshot = {}
    for watch_dir in dirs:
        if not watch_dir.exists():
            continue
        for f in watch_dir.rglob("*"):
            if f.is_file() and not should_ignore(f):
                try:
                    stat = f.stat()
                    snapshot[str(f)] = (stat.st_mtime, stat.st_size)
                except (OSError, PermissionError):
                    pass
    return snapshot


def load_changes() -> list:
    """Load existing changes from the sync file."""
    if CHANGES_FILE.exists():
        try:
            with open(CHANGES_FILE) as f:
                data = json.load(f)
                return data.get("recentChanges", [])
        except (json.JSONDecodeError, KeyError):
            pass
    return []


def save_changes(changes: list):
    """Write changes to the sync file."""
    SYNC_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "lastUpdated": datetime.now().isoformat(),
        "recentChanges": changes[-MAX_CHANGES:],
    }
    with open(CHANGES_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(data, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    try:
        os.chmod(CHANGES_FILE, 0o660)
    except PermissionError:
        pass


def detect_source(filepath: str) -> str:
    """Guess whether the change came from Claude Code or OpenClaw."""
    if "/.openclaw/" in filepath or "/antigravity/memory/" in filepath:
        return "openclaw"
    return "claude-code"


def main():
    log("watch_changes.py started")
    log(f"Watching {len(WATCH_DIRS)} directories")
    log(f"Output: {CHANGES_FILE}")

    # Initialize with current state
    previous_snapshot = scan_files(WATCH_DIRS)
    changes = load_changes()
    recent_debounce = {}  # filepath -> last_recorded_time

    log(f"Initial scan: {len(previous_snapshot)} files tracked")

    last_heartbeat_time = time.time()

    while True:
        time.sleep(POLL_INTERVAL)
        current_snapshot = scan_files(WATCH_DIRS)
        now = time.time()
        new_changes = []

        # Auto-heartbeat: drop a reindex task every 30 min
        if (now - last_heartbeat_time) >= HEARTBEAT_INTERVAL:
            drop_heartbeat_task()
            last_heartbeat_time = now

        # Watchdog: check sibling daemons every 5 min
        check_daemon_health()

        # Check for new or modified files
        for filepath, (mtime, size) in current_snapshot.items():
            if filepath not in previous_snapshot:
                # New file
                if filepath in recent_debounce and (now - recent_debounce[filepath]) < DEBOUNCE_SECONDS:
                    continue
                new_changes.append({
                    "file": filepath,
                    "action": "created",
                    "timestamp": datetime.fromtimestamp(mtime).isoformat(),
                    "source": detect_source(filepath),
                    "size": size,
                })
                recent_debounce[filepath] = now
            else:
                old_mtime, old_size = previous_snapshot[filepath]
                if mtime != old_mtime:
                    # Modified file
                    if filepath in recent_debounce and (now - recent_debounce[filepath]) < DEBOUNCE_SECONDS:
                        continue
                    new_changes.append({
                        "file": filepath,
                        "action": "modified",
                        "timestamp": datetime.fromtimestamp(mtime).isoformat(),
                        "source": detect_source(filepath),
                        "size": size,
                    })
                    recent_debounce[filepath] = now

        # Check for deleted files
        for filepath in previous_snapshot:
            if filepath not in current_snapshot:
                new_changes.append({
                    "file": filepath,
                    "action": "deleted",
                    "timestamp": datetime.now().isoformat(),
                    "source": "unknown",
                    "size": 0,
                })

        if new_changes:
            changes.extend(new_changes)
            changes = changes[-MAX_CHANGES:]
            save_changes(changes)

            important_changes = []
            for c in new_changes:
                log(f"{c['action'].upper()}: {c['file']}")
                if is_important_change(c["file"], c["action"]):
                    important_changes.append(c)

            # Batch alert for important changes
            if important_changes:
                lines = []
                for ic in important_changes[:5]:  # max 5 per alert
                    fname = Path(ic["file"]).name
                    lines.append(f"  {ic['action'].upper()}: `{fname}`")
                msg = f"*File Changes Detected*\n" + "\n".join(lines)
                if len(important_changes) > 5:
                    msg += f"\n  ...and {len(important_changes) - 5} more"
                send_telegram_alert(msg, category="file_changes")

            # Alert if batch is unusually large (>10 changes at once)
            if len(new_changes) > 10:
                send_telegram_alert(
                    f"*Batch Update*: {len(new_changes)} files changed in one cycle",
                    category="batch_update"
                )

        previous_snapshot = current_snapshot

        # Clean up old debounce entries (older than 60s)
        recent_debounce = {k: v for k, v in recent_debounce.items() if (now - v) < 60}


if __name__ == "__main__":
    main()
