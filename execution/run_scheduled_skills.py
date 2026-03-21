#!/usr/bin/env python3
"""
run_scheduled_skills.py — Scheduled Skills Runner

Reads .claude/scheduled-skills.yaml and runs any skills whose cron schedule
matches the current time. Designed to be called by launchd, Modal cron, or
GitHub Actions on a regular interval (e.g., every minute or every 15 minutes).

Usage:
    # Check what's due and run it
    python execution/run_scheduled_skills.py run

    # List all scheduled skills
    python execution/run_scheduled_skills.py list

    # Dry run (show what would execute without running)
    python execution/run_scheduled_skills.py run --dry-run

    # Force run a specific skill
    python execution/run_scheduled_skills.py force --skill morning-brief
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / ".claude" / "scheduled-skills.yaml"
STATE_PATH = PROJECT_ROOT / ".tmp" / "scheduled-skills-state.json"
LOG_PATH = PROJECT_ROOT / ".tmp" / "skill-runs.json"


def load_config():
    """Load scheduled skills configuration."""
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_state():
    """Load last-run timestamps for each skill."""
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state):
    """Persist last-run timestamps."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def log_run(skill_name, script, success, duration_s, output=""):
    """Log skill run to skill-runs.json for Training Officer tracking."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    runs = []
    if LOG_PATH.exists():
        with open(LOG_PATH) as f:
            runs = json.load(f)
    runs.append({
        "skill": skill_name,
        "script": script,
        "timestamp": datetime.now().isoformat(),
        "success": success,
        "duration_s": round(duration_s, 2),
        "output_preview": output[:500] if output else "",
    })
    # Keep last 500 runs
    runs = runs[-500:]
    with open(LOG_PATH, "w") as f:
        json.dump(runs, f, indent=2)


def cron_matches_now(cron_expr):
    """Check if a cron expression matches the current minute.

    Supports: minute hour day_of_month month day_of_week
    Supports: *, specific numbers, */N, comma-separated lists
    """
    now = datetime.now()
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False

    fields = [
        (parts[0], now.minute, 0, 59),
        (parts[1], now.hour, 0, 23),
        (parts[2], now.day, 1, 31),
        (parts[3], now.month, 1, 12),
        (parts[4], (now.weekday() + 1) % 7, 0, 6),  # Convert Python weekday (0=Mon) to cron (0=Sun)
    ]

    for i, (expr, current, low, high) in enumerate(fields):
        if not _field_matches(expr, current, low, high, is_dow=(i == 4)):
            return False
    return True


def _field_matches(expr, current, low, high, is_dow=False):
    """Check if a single cron field matches.

    Args:
        expr: Cron field expression (e.g., "0", "*/5", "1,3,5", "1-7").
        current: Current value to check.
        low: Minimum valid value for this field.
        high: Maximum valid value for this field.
        is_dow: If True, normalize 7 to 0 (cron treats both as Sunday).
    """
    if expr == "*":
        return True
    # Handle */N
    if expr.startswith("*/"):
        step = int(expr[2:])
        return current % step == 0
    # Handle comma-separated values and ranges
    values = set()
    for part in expr.split(","):
        if "-" in part:
            a, b = part.split("-")
            values.update(range(int(a), int(b) + 1))
        else:
            values.add(int(part))
    # In cron day-of-week, 7 is also Sunday (same as 0)
    if is_dow and 7 in values:
        values.add(0)
    return current in values


def run_skill(schedule_entry, dry_run=False, skip_expensive=False):
    """Execute a scheduled skill.

    Args:
        schedule_entry: Dict from scheduled-skills.yaml.
        dry_run: Print command without executing.
        skip_expensive: If True, skip entries marked expensive: true.
    """
    skill = schedule_entry["skill"]
    script = schedule_entry["script"]
    args = schedule_entry.get("args", "")
    desc = schedule_entry.get("description", "")
    is_expensive = schedule_entry.get("expensive", False)

    if skip_expensive and is_expensive:
        print(f"  [BUDGET] Skipping expensive skill: {skill}")
        return False

    cmd = f"cd {PROJECT_ROOT} && source .venv/bin/activate && python {script}"
    if args:
        cmd += f" {args}"

    if dry_run:
        label = " [expensive]" if is_expensive else ""
        print(f"  [DRY RUN]{label} Would execute: {cmd}")
        return True

    print(f"  Running: {cmd}")
    start = datetime.now()
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300,
            executable="/bin/zsh"
        )
        duration = (datetime.now() - start).total_seconds()
        success = result.returncode == 0
        output = result.stdout if success else result.stderr
        log_run(skill, script, success, duration, output)
        if success:
            print(f"  ✓ {skill} completed in {duration:.1f}s")
        else:
            print(f"  ✗ {skill} failed: {result.stderr[:200]}")
        return success
    except subprocess.TimeoutExpired:
        duration = (datetime.now() - start).total_seconds()
        log_run(skill, script, False, duration, "TIMEOUT")
        print(f"  ✗ {skill} timed out after 300s")
        return False


def cmd_list(config):
    """List all scheduled skills."""
    print("Scheduled Skills:")
    print(f"{'Skill':<25} {'Cron':<20} {'Auto':<6} {'Description'}")
    print("-" * 90)
    for s in config.get("schedules", []):
        auto = "✓" if s.get("auto_run", False) else "✗"
        print(f"{s['skill']:<25} {s['cron']:<20} {auto:<6} {s.get('description', '')}")


def check_budget_status():
    """Run token_tracker budget check and return (skip_expensive, block_all).

    Returns:
        skip_expensive (bool): True if CRITICAL threshold reached — skip expensive skills.
        block_all (bool): True if EXCEEDED threshold reached — block all skills.
    """
    try:
        result = subprocess.run(
            [sys.executable, "execution/token_tracker.py", "budget"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=PROJECT_ROOT,
        )
        output = result.stdout + result.stderr
    except Exception as e:
        print(f"  [BUDGET] Warning: could not check budget ({e}). Proceeding.")
        return False, False

    if "EXCEEDED" in output:
        return True, True
    if "CRITICAL" in output:
        return True, False
    return False, False


def cmd_run(config, dry_run=False):
    """Run all skills whose cron matches current time."""
    # --- Budget enforcement ---
    skip_expensive, block_all = check_budget_status()
    if block_all:
        print("Daily budget exceeded — skipping all scheduled runs")
        return
    if skip_expensive:
        print("  [BUDGET] WARNING: budget CRITICAL — expensive skills will be skipped this cycle")

    state = load_state()
    now = datetime.now()
    ran = 0

    for s in config.get("schedules", []):
        if not s.get("auto_run", False):
            continue
        if not cron_matches_now(s["cron"]):
            continue

        # Prevent double-runs within same minute
        key = f"{s['skill']}_{s.get('args', '')}"
        last_run = state.get(key)
        if last_run:
            last_dt = datetime.fromisoformat(last_run)
            if (now - last_dt).total_seconds() < 55:
                continue

        print(f"[{now.strftime('%H:%M')}] Skill due: {s['skill']}")
        success = run_skill(s, dry_run=dry_run, skip_expensive=skip_expensive)
        if not dry_run:
            state[key] = now.isoformat()
            ran += 1

    if not dry_run:
        save_state(state)
    if ran > 0 or dry_run:
        print(f"\nRan {ran} skill(s).")
    # Silent when 0 matches to avoid flooding launchd logs


def cmd_force(config, skill_name):
    """Force-run a specific skill regardless of schedule."""
    for s in config.get("schedules", []):
        if s["skill"] == skill_name:
            print(f"Force-running: {skill_name}")
            run_skill(s)
            return
    print(f"Skill '{skill_name}' not found in scheduled-skills.yaml")


def main():
    parser = argparse.ArgumentParser(description="Scheduled Skills Runner")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all scheduled skills")

    run_p = sub.add_parser("run", help="Run due skills")
    run_p.add_argument("--dry-run", action="store_true")

    force_p = sub.add_parser("force", help="Force-run a specific skill")
    force_p.add_argument("--skill", required=True)

    args = parser.parse_args()
    config = load_config()

    if args.command == "list":
        cmd_list(config)
    elif args.command == "run":
        cmd_run(config, dry_run=args.dry_run)
    elif args.command == "force":
        cmd_force(config, args.skill)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
