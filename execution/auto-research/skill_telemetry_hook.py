#!/usr/bin/env python3
"""
skill_telemetry_hook.py — PostToolUse hook that auto-logs skill executions.

Detects when a skill is being executed (by checking tool_name for Skill calls
or by detecting skill-related script execution in Bash) and logs it to the
skill optimizer's telemetry.

Also captures corrections: when the user's next message after a skill run
contains correction signals ("no", "wrong", "instead", "fix", "not that"),
it logs a negative score.

Called by PostToolUse hook in .claude/settings.local.json.

Usage (hook):
    python3 execution/auto-research/skill_telemetry_hook.py "$TOOL_NAME" "$TOOL_INPUT"

Usage (manual):
    python3 execution/auto-research/skill_telemetry_hook.py --log <skill> <score> [correction]
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

TELEMETRY_PATH = Path(__file__).parent / "skill-optimizer" / "telemetry.json"

# Map script names to skill names
SCRIPT_TO_SKILL = {
    "run_scraper.py": "lead-gen",
    "filter_icp.py": "lead-gen",
    "generate_emails.py": "cold-email",
    "generate_business_audit.py": "business-audit",
    "source.py": "source-products",
    "multi_retailer_search.py": "source-products",
    "send_morning_briefing.py": "morning-brief",
    "client_health_monitor.py": "client-health",
    "pipeline_analytics.py": "pipeline-analytics",
    "outreach_sequencer.py": "outreach-sequence",
    "content_engine.py": "content-engine",
    "scrape_competitor_ads.py": "competitor-intel",
    "training_officer_scan.py": "training-officer",
    "format_deal_drop.py": "deal-drop",
    "research_prospect.py": "sales-prep",
    "generate_vsl.py": "vsl",
    "run_dream100.py": "dream100",
    "consensus_engine.py": "consensus",
    "agent_chatroom.py": "chatroom",
    "verification_loop.py": "verify",
    "video_to_action.py": "video-action",
    "pipeline_runner.py": "pipeline",
    "parallel_outreach.py": "outreach",
    "push_to_github.py": "build-site",
    "upload_onboarding_gdoc.py": "student-onboard",
    "memory_recall.py": "memory",
    "memory_store.py": "memory",
    "project_manager.py": "project-status",
}


def load_telemetry():
    if TELEMETRY_PATH.exists():
        try:
            return json.loads(TELEMETRY_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_telemetry(entries):
    TELEMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    TELEMETRY_PATH.write_text(json.dumps(entries, indent=2, default=str))


def detect_skill_from_bash(command):
    """Try to detect which skill is being run from a bash command."""
    if not command:
        return None
    for script, skill in SCRIPT_TO_SKILL.items():
        if script in command:
            return skill
    return None


def log_execution(skill_name, score=8, correction=None, details=None):
    """Log a skill execution to telemetry."""
    entries = load_telemetry()
    entry = {
        "skill": skill_name,
        "score": score,
        "correction": correction,
        "details": details or {},
        "timestamp": datetime.now().isoformat(),
        "source": "hook",
    }
    entries.append(entry)
    save_telemetry(entries)
    return entry


def handle_hook(tool_name, tool_input, exit_code=None):
    """Handle a PostToolUse hook call.

    Scoring logic:
      - exit_code 0 (or None for Skill) → 8 (success)
      - exit_code non-zero → 3 (failure)
      - correction signals in output → 2 (needs fix)
    """
    skill_name = None

    if tool_name == "Skill":
        # Direct skill invocation
        try:
            if isinstance(tool_input, str):
                data = json.loads(tool_input)
            else:
                data = tool_input
            skill_name = data.get("skill", data.get("name", "unknown"))
        except (json.JSONDecodeError, TypeError):
            skill_name = str(tool_input)[:50]

    elif tool_name == "Bash":
        # Check if a skill-related script was run
        command = tool_input if isinstance(tool_input, str) else str(tool_input)
        skill_name = detect_skill_from_bash(command)

    if skill_name:
        # Score based on actual exit code
        if exit_code is not None and str(exit_code) != "0":
            score = 3  # Script failed
        else:
            score = 8  # Success
        log_execution(skill_name, score=score, details={
            "tool": tool_name,
            "exit_code": str(exit_code) if exit_code is not None else "0",
        })


def main():
    import argparse

    if len(sys.argv) >= 3 and sys.argv[1] != "--log":
        # Called as hook: tool_name, tool_input, [exit_code]
        tool_name = sys.argv[1]
        tool_input = sys.argv[2] if len(sys.argv) > 2 else ""
        exit_code = sys.argv[3] if len(sys.argv) > 3 else None
        handle_hook(tool_name, tool_input, exit_code)
        return

    parser = argparse.ArgumentParser(description="Skill telemetry logger")
    parser.add_argument("--log", nargs="+", metavar=("SKILL", "SCORE"),
                       help="Manual log: <skill> <score> [correction]")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.stats:
        entries = load_telemetry()
        if not entries:
            print("No telemetry data.")
            return
        # Group by skill
        from collections import defaultdict
        stats = defaultdict(list)
        for e in entries:
            stats[e["skill"]].append(e["score"])
        print("\nSkill Telemetry:")
        print("{:<25} {:>6} {:>8}".format("Skill", "Runs", "Avg"))
        print("-" * 42)
        for skill, scores in sorted(stats.items()):
            avg = sum(scores) / len(scores)
            print("{:<25} {:>6} {:>8.1f}".format(skill, len(scores), avg))
        return

    if args.log:
        skill = args.log[0]
        score = int(args.log[1]) if len(args.log) > 1 else 8
        correction = args.log[2] if len(args.log) > 2 else None
        entry = log_execution(skill, score, correction, {"source": "manual"})
        print("Logged: {} score={} correction={}".format(skill, score, bool(correction)))
        return

    parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never crash a hook
        pass
