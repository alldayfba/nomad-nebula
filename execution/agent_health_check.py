#!/usr/bin/env python3
"""
agent_health_check.py — Detect stale agents across the system.

Checks Training Officer, CodeSec, and all bot heartbeats for staleness.
Flags agents inactive >7 days as "stale", >14 days as "critical".

Usage:
    python execution/agent_health_check.py            # Full JSON report
    python execution/agent_health_check.py --quick     # One-line summary
    python execution/agent_health_check.py --alert     # Non-zero exit if any critical
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula",
))

STALE_THRESHOLD_DAYS = 7
CRITICAL_THRESHOLD_DAYS = 14

# ISO date pattern (YYYY-MM-DD with optional time)
DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}(?::\d{2})?))?")


def parse_date(text: str) -> datetime | None:
    """Extract the most recent date from text."""
    matches = DATE_PATTERN.findall(text)
    if not matches:
        return None
    # Each match is (date_part, time_part). Pick the latest.
    best = None
    for date_str, time_str in matches:
        try:
            if time_str:
                dt = datetime.fromisoformat("{}T{}".format(date_str, time_str))
            else:
                dt = datetime.fromisoformat(date_str)
            if best is None or dt > best:
                best = dt
        except ValueError:
            continue
    return best


def check_scan_file(path: Path, agent_name: str, field: str = "last_scan") -> dict | None:
    """Check a last-scan.json file for staleness."""
    if not path.exists():
        return {
            "agent": agent_name,
            "source": str(path.relative_to(PROJECT_ROOT)),
            "last_active": None,
            "days_since_active": None,
            "status": "critical",
            "note": "scan file not found",
        }
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {
            "agent": agent_name,
            "source": str(path.relative_to(PROJECT_ROOT)),
            "last_active": None,
            "days_since_active": None,
            "status": "critical",
            "note": "scan file unreadable",
        }

    raw = data.get(field) or data.get("scan_date")
    if not raw:
        return {
            "agent": agent_name,
            "source": str(path.relative_to(PROJECT_ROOT)),
            "last_active": None,
            "days_since_active": None,
            "status": "critical",
            "note": "no timestamp field found",
        }

    dt = parse_date(str(raw))
    if dt is None:
        return {
            "agent": agent_name,
            "source": str(path.relative_to(PROJECT_ROOT)),
            "last_active": None,
            "days_since_active": None,
            "status": "critical",
            "note": "unparseable date: {}".format(raw),
        }

    return _build_entry(agent_name, str(path.relative_to(PROJECT_ROOT)), dt)


def check_heartbeat(path: Path) -> dict | None:
    """Check a bot heartbeat.md file for staleness."""
    agent_name = path.parent.name
    if not path.exists():
        return None

    try:
        content = path.read_text()
    except OSError:
        return None

    # Skip bots that are explicitly not active
    lower = content.lower()
    if "not active" in lower or "not yet" in lower:
        # Still report them, but with a note
        return {
            "agent": agent_name,
            "source": str(path.relative_to(PROJECT_ROOT)),
            "last_active": None,
            "days_since_active": None,
            "status": "inactive",
            "note": "bot not yet activated",
        }

    # Check for "never" or "N/A" heartbeat
    if "last heartbeat: never" in lower or "last heartbeat: n/a" in lower:
        return {
            "agent": agent_name,
            "source": str(path.relative_to(PROJECT_ROOT)),
            "last_active": None,
            "days_since_active": None,
            "status": "critical",
            "note": "never ran",
        }

    # Try to extract a date
    dt = parse_date(content)
    if dt is None:
        # Fall back to file modification time
        mtime = path.stat().st_mtime
        dt = datetime.fromtimestamp(mtime)
        return _build_entry(agent_name, str(path.relative_to(PROJECT_ROOT)), dt, note="date from file mtime")

    return _build_entry(agent_name, str(path.relative_to(PROJECT_ROOT)), dt)


def _build_entry(agent: str, source: str, dt: datetime, note: str | None = None) -> dict:
    """Build a health entry from a parsed datetime."""
    now = datetime.now()
    delta = now - dt
    days = delta.days

    if days >= CRITICAL_THRESHOLD_DAYS:
        status = "critical"
    elif days >= STALE_THRESHOLD_DAYS:
        status = "stale"
    else:
        status = "current"

    entry = {
        "agent": agent,
        "source": source,
        "last_active": dt.strftime("%Y-%m-%d %H:%M"),
        "days_since_active": days,
        "status": status,
    }
    if note:
        entry["note"] = note
    return entry


def run_health_check() -> list[dict]:
    """Run full agent health check. Returns list of agent health entries."""
    results = []

    # 1. Training Officer — .tmp/training-officer/last-scan.json
    to_path = PROJECT_ROOT / ".tmp" / "training-officer" / "last-scan.json"
    entry = check_scan_file(to_path, "training-officer", field="last_scan")
    if entry:
        results.append(entry)

    # 2. CodeSec — .tmp/codesec/last-scan.json
    cs_path = PROJECT_ROOT / ".tmp" / "codesec" / "last-scan.json"
    entry = check_scan_file(cs_path, "codesec", field="last_scan")
    if entry:
        results.append(entry)

    # 3. All bot heartbeats — bots/*/heartbeat.md
    # Skip agents already covered by scan files above
    scan_agents = {r["agent"] for r in results}
    bots_dir = PROJECT_ROOT / "bots"
    if bots_dir.exists():
        for bot_dir in sorted(bots_dir.iterdir()):
            if not bot_dir.is_dir():
                continue
            # Skip non-agent directories
            if bot_dir.name in ("creators", "clients"):
                continue
            # Skip if already covered by a scan file
            if bot_dir.name in scan_agents:
                continue
            hb = bot_dir / "heartbeat.md"
            if hb.exists():
                entry = check_heartbeat(hb)
                if entry:
                    results.append(entry)

    return results


def format_quick(results: list[dict]) -> str:
    """One-line summary."""
    stale = sum(1 for r in results if r["status"] == "stale")
    critical = sum(1 for r in results if r["status"] == "critical")
    current = sum(1 for r in results if r["status"] == "current")
    inactive = sum(1 for r in results if r["status"] == "inactive")

    parts = []
    if critical:
        parts.append("{} critical".format(critical))
    if stale:
        parts.append("{} stale".format(stale))
    if current:
        parts.append("{} current".format(current))
    if inactive:
        parts.append("{} inactive".format(inactive))

    summary = ", ".join(parts) if parts else "no agents found"

    # List critical agents by name
    if critical:
        names = [r["agent"] for r in results if r["status"] == "critical"]
        summary += " [CRITICAL: {}]".format(", ".join(names))

    return "Agent health: {}".format(summary)


def main():
    parser = argparse.ArgumentParser(description="Agent staleness detection")
    parser.add_argument("--quick", action="store_true", help="One-line summary")
    parser.add_argument("--alert", action="store_true", help="Non-zero exit if any agent is critical")
    args = parser.parse_args()

    results = run_health_check()

    if args.quick:
        print(format_quick(results))
    else:
        print(json.dumps(results, indent=2))

    if args.alert:
        has_critical = any(r["status"] == "critical" for r in results)
        sys.exit(1 if has_critical else 0)


if __name__ == "__main__":
    main()
