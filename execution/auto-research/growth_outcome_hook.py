#!/usr/bin/env python3
"""
growth_outcome_hook.py — PostToolUse hook that auto-logs business outcomes.

Detects when revenue-generating scripts complete and logs the outcome
to the growth optimizer's outcomes.json.

Outcomes tracked:
  - lead_generated: run_scraper.py completed
  - product_sourced: source.py completed
  - audit_sent: generate_business_audit.py completed
  - script_success/script_error: any execution/ script run

Called by PostToolUse hook in .claude/settings.local.json.

Usage (hook):
    python3 execution/auto-research/growth_outcome_hook.py "$TOOL_NAME" "$TOOL_INPUT" "$EXIT_CODE"

Usage (manual):
    python3 execution/auto-research/growth_outcome_hook.py --log <type> <details>
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

OUTCOMES_PATH = Path(__file__).parent / "growth-optimizer" / "outcomes.json"

# Map scripts to outcome types
SCRIPT_OUTCOMES = {
    "run_scraper.py": "lead_generated",
    "filter_icp.py": "lead_generated",
    "generate_emails.py": "lead_contacted",
    "outreach_sequencer.py": "lead_contacted",
    "generate_business_audit.py": "audit_sent",
    "source.py": "product_sourced",
    "multi_retailer_search.py": "product_sourced",
    "calculate_fba_profitability.py": "product_sourced",
}


def load_outcomes():
    if OUTCOMES_PATH.exists():
        try:
            return json.loads(OUTCOMES_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_outcomes(entries):
    OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTCOMES_PATH.write_text(json.dumps(entries, indent=2, default=str))


def detect_script(command):
    """Extract script name from a bash command."""
    if not command:
        return None
    # Match python execution/script.py or python3 execution/script.py
    match = re.search(r'(?:python3?)\s+(?:execution/)?(\w+\.py)', command)
    if match:
        return match.group(1)
    return None


def log_outcome(outcome_type, details, success=True):
    """Log a business outcome."""
    entries = load_outcomes()
    entry = {
        "type": outcome_type,
        "details": details,
        "success": success,
        "timestamp": datetime.now().isoformat(),
    }
    entries.append(entry)
    save_outcomes(entries)
    return entry


def handle_hook(tool_name, tool_input, exit_code=None):
    """Handle a PostToolUse hook call."""
    if tool_name != "Bash":
        return

    command = tool_input if isinstance(tool_input, str) else str(tool_input)
    script = detect_script(command)
    if not script:
        return

    success = exit_code in (None, "0", 0)

    # Check for specific outcome types
    outcome_type = SCRIPT_OUTCOMES.get(script)
    if outcome_type:
        log_outcome(outcome_type, {"script": script, "command": command[:200]}, success)
    elif script.endswith(".py") and "execution/" in command:
        # Track general script health
        otype = "script_success" if success else "script_error"
        log_outcome(otype, {"script": script, "command": command[:200]}, success)


def main():
    import argparse

    if len(sys.argv) >= 3 and sys.argv[1] != "--log" and sys.argv[1] != "--stats":
        # Called as hook: tool_name, tool_input, [exit_code]
        tool_name = sys.argv[1]
        tool_input = sys.argv[2] if len(sys.argv) > 2 else ""
        exit_code = sys.argv[3] if len(sys.argv) > 3 else None
        handle_hook(tool_name, tool_input, exit_code)
        return

    parser = argparse.ArgumentParser(description="Growth outcome logger")
    parser.add_argument("--log", nargs=2, metavar=("TYPE", "DETAILS"),
                       help="Manual log: <outcome_type> <details>")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.stats:
        entries = load_outcomes()
        if not entries:
            print("No outcome data.")
            return
        from collections import Counter
        counts = Counter(e["type"] for e in entries)
        print("\nGrowth Outcomes:")
        for otype, count in counts.most_common():
            print("  {}: {}".format(otype, count))
        return

    if args.log:
        entry = log_outcome(args.log[0], args.log[1])
        print("Logged: {} — {}".format(args.log[0], args.log[1]))
        return

    parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never crash a hook
        pass
