#!/usr/bin/env python3
"""
Script: self_healing_engine.py
Purpose: The system's immune system. Monitors script executions for errors,
         captures stack traces, identifies root causes, and generates fix
         proposals via the Training Officer pipeline.

Usage:
  python execution/self_healing_engine.py --watch         # Monitor error log in real-time
  python execution/self_healing_engine.py --scan           # Scan recent errors
  python execution/self_healing_engine.py --report         # Error pattern report
  python execution/self_healing_engine.py --wrap "python execution/some_script.py --args"

The --wrap mode is the most powerful: it wraps ANY script execution,
captures errors, auto-generates fix proposals, and updates directives.

Flow:
  1. Script fails → error captured to .tmp/training-officer/errors/
  2. Self-healing engine analyzes stack trace
  3. Matches error to responsible script + agent
  4. Generates a Training Proposal with fix suggestion
  5. If fix is simple (import missing, path wrong), auto-fix + log
  6. If complex, escalate via proposal for Sabbo review
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula"
))

TMP_DIR = PROJECT_ROOT / ".tmp" / "training-officer"
ERRORS_DIR = TMP_DIR / "errors"
PROPOSALS_DIR = TMP_DIR / "proposals"
LEARNINGS_FILE = TMP_DIR / "learnings.md"
ERROR_LOG = TMP_DIR / "error-log.json"

# Map scripts to their owning agents
SCRIPT_AGENT_MAP = {
    "run_scraper.py": "lead-gen",
    "filter_icp.py": "lead-gen",
    "generate_emails.py": "outreach",
    "generate_ad_scripts.py": "ads-copy",
    "generate_vsl.py": "content",
    "research_prospect.py": "outreach",
    "generate_dream100_assets.py": "outreach",
    "assemble_gammadoc.py": "outreach",
    "generate_business_audit.py": "CEO",
    "run_dream100.py": "outreach",
    "scrape_competitor_ads.py": "ads-copy",
    "scrape_client_profile.py": "content",
    "training_officer_scan.py": "CEO",
    "apply_proposal.py": "CEO",
    "agent_quality_tracker.py": "CEO",
    "competitive_intel_cron.py": "CEO",
    "run_sourcing_pipeline.py": "sourcing",
    "scrape_retail_products.py": "sourcing",
    "match_amazon_products.py": "sourcing",
    "calculate_fba_profitability.py": "sourcing",
    "price_tracker.py": "sourcing",
    "scheduled_sourcing.py": "sourcing",
    "sourcing_alerts.py": "sourcing",
    "reverse_sourcing.py": "sourcing",
    "batch_asin_checker.py": "sourcing",
    "storefront_stalker.py": "sourcing",
    "inventory_tracker.py": "amazon",
    "scrape_cardbear.py": "sourcing",
    "export_to_sheets.py": "sourcing",
    "watch_inbox.py": "CEO",
    "allocate_sops.py": "CEO",
    "send_morning_briefing.py": "CEO",
    "update_ceo_brain.py": "CEO",
    "brain_maintenance.py": "CEO",
    "save_session.py": "CEO",
}

# Known auto-fixable error patterns
AUTO_FIX_PATTERNS = [
    {
        "pattern": r"ModuleNotFoundError: No module named '(\w+)'",
        "fix_type": "missing_module",
        "action": "pip install {module}",
    },
    {
        "pattern": r"FileNotFoundError: \[Errno 2\] No such file or directory: '(.+)'",
        "fix_type": "missing_file",
        "action": "mkdir -p {parent_dir}",
    },
    {
        "pattern": r"PermissionError: \[Errno 13\] Permission denied: '(.+)'",
        "fix_type": "permission",
        "action": "chmod 755 {path}",
    },
    {
        "pattern": r"json\.decoder\.JSONDecodeError",
        "fix_type": "bad_json",
        "action": "Regenerate or validate JSON file",
    },
    {
        "pattern": r"ANTHROPIC_API_KEY.*(not set|empty|missing)",
        "fix_type": "missing_env",
        "action": "Check .env file for ANTHROPIC_API_KEY",
    },
]


def ensure_dirs():
    for d in [ERRORS_DIR, PROPOSALS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_env():
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_error_log() -> list:
    if ERROR_LOG.exists():
        return json.loads(ERROR_LOG.read_text())
    return []


def save_error_log(errors: list):
    ERROR_LOG.write_text(json.dumps(errors[-500:], indent=2, default=str))


def identify_script(error_text: str) -> tuple:
    """Extract the failing script name and line from a stack trace."""
    # Look for execution/ script references
    matches = re.findall(r'File ".*?/execution/(\w+\.py)", line (\d+)', error_text)
    if matches:
        return matches[-1]  # Last frame is usually the actual error
    # Fall back to any .py reference
    matches = re.findall(r'File ".*?/(\w+\.py)", line (\d+)', error_text)
    if matches:
        return matches[-1]
    return ("unknown.py", "0")


def classify_error(error_text: str) -> dict:
    """Classify an error and determine if it's auto-fixable."""
    for pattern in AUTO_FIX_PATTERNS:
        match = re.search(pattern["pattern"], error_text, re.IGNORECASE)
        if match:
            return {
                "auto_fixable": True,
                "fix_type": pattern["fix_type"],
                "action": pattern["action"],
                "match": match.group(0),
                "groups": match.groups(),
            }
    return {"auto_fixable": False, "fix_type": "unknown", "action": None}


def attempt_auto_fix(classification: dict, error_text: str) -> bool:
    """Attempt to auto-fix simple errors. Returns True if fixed."""
    fix_type = classification.get("fix_type")
    groups = classification.get("groups", ())

    if fix_type == "missing_module" and groups:
        module = groups[0]
        print(f"[self-healing] Auto-fix: Installing missing module '{module}'...")
        python = str(PROJECT_ROOT / ".venv" / "bin" / "pip")
        result = subprocess.run([python, "install", module], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[self-healing] Installed {module} successfully.")
            return True
        print(f"[self-healing] Failed to install {module}: {result.stderr[-100:]}")

    elif fix_type == "missing_file" and groups:
        filepath = Path(groups[0])
        parent = filepath.parent
        if str(PROJECT_ROOT) in str(parent) or str(parent).startswith("/Users/Shared"):
            print(f"[self-healing] Auto-fix: Creating directory {parent}")
            parent.mkdir(parents=True, exist_ok=True)
            return True

    elif fix_type == "permission" and groups:
        filepath = groups[0]
        if str(PROJECT_ROOT) in filepath or filepath.startswith("/Users/Shared"):
            print(f"[self-healing] Auto-fix: Fixing permissions on {filepath}")
            os.chmod(filepath, 0o755)
            return True

    return False


def generate_fix_proposal(script_name: str, line_num: str, error_text: str,
                          classification: dict) -> Optional[str]:
    """Generate a Training Proposal for the error."""
    agent = SCRIPT_AGENT_MAP.get(script_name, "CEO")
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    existing = list(PROPOSALS_DIR.glob(f"TP-{today}-*.yaml"))
    seq = len(existing) + 1
    pid = f"TP-{today}-{seq:03d}"

    # Truncate error for proposal
    error_preview = error_text[-500:] if len(error_text) > 500 else error_text

    content = f"""# Training Proposal: {pid}

proposal_id: "{pid}"
created: "{now}"
status: "pending"
theme: "error-fix"

# WHO
target_agent: "{agent}"
target_file: "execution/{script_name}"

# WHAT
upgrade_type: "tool"
title: "Fix error in {script_name}:{line_num}"
description: |
  Script {script_name} failed at line {line_num}.
  Error type: {classification.get('fix_type', 'unknown')}
  Auto-fixable: {classification.get('auto_fixable', False)}

# WHY
trigger: "Self-healing engine error detection"
evidence: |
  {error_preview}
expected_impact: "Restore {script_name} to working state"

# HOW
change_type: "fix"
proposed_content: |
  Error in execution/{script_name} at line {line_num}:
  {classification.get('match', error_preview[:200])}
  Suggested fix: {classification.get('action', 'Manual investigation required')}

# RISK
risk_level: "medium"
rollback_plan: "Revert execution/{script_name} to previous version"
dependencies: []
"""
    proposal_path = PROPOSALS_DIR / f"{pid}.yaml"
    proposal_path.write_text(content)
    return pid


def record_error(script_name: str, line_num: str, error_text: str,
                 classification: dict, auto_fixed: bool, proposal_id: Optional[str]):
    """Log the error for pattern analysis."""
    errors = load_error_log()
    errors.append({
        "timestamp": datetime.now().isoformat(),
        "script": script_name,
        "line": line_num,
        "error_type": classification.get("fix_type", "unknown"),
        "auto_fixable": classification.get("auto_fixable", False),
        "auto_fixed": auto_fixed,
        "proposal_id": proposal_id,
        "error_preview": error_text[-300:],
    })
    save_error_log(errors)


def wrap_execution(cmd_str: str):
    """Wrap a script execution, capture errors, auto-heal."""
    parts = cmd_str.split()
    print(f"[self-healing] Wrapping: {cmd_str}")

    result = subprocess.run(parts, capture_output=True, text=True, cwd=str(PROJECT_ROOT))

    if result.returncode == 0:
        print(result.stdout)
        return

    # Error occurred
    error_text = result.stderr + "\n" + result.stdout
    print(f"[self-healing] Error detected!")
    print(error_text[-500:])

    script_name, line_num = identify_script(error_text)
    classification = classify_error(error_text)

    print(f"[self-healing] Script: {script_name}:{line_num}")
    print(f"[self-healing] Type: {classification['fix_type']}")
    print(f"[self-healing] Auto-fixable: {classification['auto_fixable']}")

    auto_fixed = False
    proposal_id = None

    if classification["auto_fixable"]:
        auto_fixed = attempt_auto_fix(classification, error_text)
        if auto_fixed:
            print(f"[self-healing] Auto-fixed! Retrying...")
            retry = subprocess.run(parts, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
            if retry.returncode == 0:
                print(retry.stdout)
                print(f"[self-healing] Retry successful after auto-fix.")
            else:
                print(f"[self-healing] Retry failed. Generating proposal...")
                proposal_id = generate_fix_proposal(script_name, line_num, error_text, classification)

    if not auto_fixed:
        proposal_id = generate_fix_proposal(script_name, line_num, error_text, classification)
        if proposal_id:
            print(f"[self-healing] Generated fix proposal: {proposal_id}")

    record_error(script_name, line_num, error_text, classification, auto_fixed, proposal_id)

    # Save error detail file
    error_file = ERRORS_DIR / f"error-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{script_name}.txt"
    error_file.write_text(error_text)


def scan_recent_errors():
    """Scan error log for patterns."""
    errors = load_error_log()
    if not errors:
        print("[self-healing] No errors recorded.")
        return

    # Group by script
    by_script = {}
    for e in errors:
        s = e.get("script", "unknown")
        if s not in by_script:
            by_script[s] = []
        by_script[s].append(e)

    print(f"\n[self-healing] Error Summary ({len(errors)} total errors)\n")
    print(f"  {'Script':<35s} {'Count':<7s} {'Auto-Fixed':<12s} {'Last Error':<20s}")
    print(f"  {'─' * 74}")

    for script, errs in sorted(by_script.items(), key=lambda x: -len(x[1])):
        auto_fixed = sum(1 for e in errs if e.get("auto_fixed"))
        last = errs[-1].get("timestamp", "?")[:16]
        print(f"  {script:<35s} {len(errs):<7d} {auto_fixed:<12d} {last}")

    # Detect repeat offenders (same script, same error type, 3+ times)
    print(f"\n  Repeat offenders (3+ same errors):")
    for script, errs in by_script.items():
        type_counts = {}
        for e in errs:
            t = e.get("error_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        for etype, count in type_counts.items():
            if count >= 3:
                print(f"    {script}: {etype} x{count} — needs structural fix")


def generate_report():
    """Generate full error pattern report."""
    errors = load_error_log()
    if not errors:
        print("[self-healing] No errors recorded.")
        return

    total = len(errors)
    auto_fixed = sum(1 for e in errors if e.get("auto_fixed"))
    proposals = sum(1 for e in errors if e.get("proposal_id"))

    print(f"\n{'=' * 60}")
    print(f"  SELF-HEALING ENGINE REPORT")
    print(f"{'=' * 60}\n")
    print(f"  Total errors captured:      {total}")
    print(f"  Auto-fixed:                 {auto_fixed} ({auto_fixed*100//max(total,1)}%)")
    print(f"  Proposals generated:        {proposals}")
    print(f"  Unresolved:                 {total - auto_fixed - proposals}")

    # Error type breakdown
    type_counts = {}
    for e in errors:
        t = e.get("error_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"\n  By error type:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {t:<25s} {c}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Self-Healing Engine — System immune system")
    parser.add_argument("--wrap", type=str, help="Wrap a command execution with error capture")
    parser.add_argument("--scan", action="store_true", help="Scan recent errors for patterns")
    parser.add_argument("--report", action="store_true", help="Full error pattern report")
    args = parser.parse_args()

    ensure_dirs()
    load_env()

    if args.wrap:
        wrap_execution(args.wrap)
    elif args.scan:
        scan_recent_errors()
    elif args.report:
        generate_report()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
