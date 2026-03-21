#!/usr/bin/env python3
"""
Script: proposal_rollback.py
Purpose: Version control for agent files. Creates backups before proposals
         are applied, tracks lineage, and supports targeted rollback.

Usage:
  python execution/proposal_rollback.py --backup SabboOS/Agents/CEO.md
  python execution/proposal_rollback.py --rollback TP-2026-02-21-001
  python execution/proposal_rollback.py --history SabboOS/Agents/CEO.md
  python execution/proposal_rollback.py --list
  python execution/proposal_rollback.py --diff TP-2026-02-21-001

Flow:
  1. Before apply_proposal.py applies a proposal, it calls --backup
  2. Backup stored in .tmp/training-officer/backups/ with metadata
  3. If proposal causes issues, --rollback restores the file
  4. --history shows all proposals applied to a file with timestamps
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula"
))

TMP_DIR = PROJECT_ROOT / ".tmp" / "training-officer"
BACKUPS_DIR = TMP_DIR / "backups"
LINEAGE_FILE = TMP_DIR / "proposal-lineage.json"
PROPOSALS_DIR = TMP_DIR / "proposals"


def ensure_dirs():
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def load_lineage() -> dict:
    """Load proposal lineage tracking."""
    if LINEAGE_FILE.exists():
        return json.loads(LINEAGE_FILE.read_text())
    return {"files": {}, "proposals": {}}


def save_lineage(lineage: dict):
    LINEAGE_FILE.write_text(json.dumps(lineage, indent=2, default=str))


def file_hash(filepath: Path) -> str:
    """Compute short hash of file content."""
    if filepath.exists():
        return hashlib.md5(filepath.read_bytes()).hexdigest()[:8]
    return "none"


def backup_file(filepath_str: str, proposal_id: Optional[str] = None) -> str:
    """Create a backup of a file before modification."""
    filepath = PROJECT_ROOT / filepath_str
    if not filepath.exists():
        print(f"[rollback] File not found: {filepath_str}")
        return ""

    now = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = filepath_str.replace("/", "__")
    backup_name = f"{now}__{safe_name}"
    if proposal_id:
        backup_name = f"{now}__{proposal_id}__{safe_name}"

    backup_path = BACKUPS_DIR / backup_name
    shutil.copy2(filepath, backup_path)

    # Update lineage
    lineage = load_lineage()
    if filepath_str not in lineage["files"]:
        lineage["files"][filepath_str] = []

    entry = {
        "timestamp": datetime.now().isoformat(),
        "backup_file": backup_name,
        "proposal_id": proposal_id,
        "hash_before": file_hash(filepath),
    }
    lineage["files"][filepath_str].append(entry)

    if proposal_id:
        lineage["proposals"][proposal_id] = {
            "target_file": filepath_str,
            "backup_file": backup_name,
            "timestamp": datetime.now().isoformat(),
            "status": "backed_up",
        }

    save_lineage(lineage)
    print(f"[rollback] Backed up {filepath_str} → {backup_name}")
    return backup_name


def rollback_proposal(proposal_id: str) -> bool:
    """Rollback a specific proposal by restoring the backup."""
    lineage = load_lineage()
    proposal_info = lineage.get("proposals", {}).get(proposal_id)

    if not proposal_info:
        print(f"[rollback] No backup found for proposal: {proposal_id}")
        return False

    backup_name = proposal_info.get("backup_file")
    target_file = proposal_info.get("target_file")
    backup_path = BACKUPS_DIR / backup_name

    if not backup_path.exists():
        print(f"[rollback] Backup file missing: {backup_name}")
        return False

    target_path = PROJECT_ROOT / target_file

    # Create a backup of the CURRENT state before rolling back
    current_backup = backup_file(target_file, proposal_id=f"pre-rollback-{proposal_id}")

    # Restore
    shutil.copy2(backup_path, target_path)

    # Update lineage
    proposal_info["status"] = "rolled_back"
    proposal_info["rolled_back_at"] = datetime.now().isoformat()
    save_lineage(lineage)

    # Update proposal status
    proposal_path = PROPOSALS_DIR / f"{proposal_id}.yaml"
    if proposal_path.exists():
        content = proposal_path.read_text()
        import re
        content = re.sub(r'status:\s*"[^"]*"', 'status: "rolled_back"', content)
        proposal_path.write_text(content)

    print(f"[rollback] Restored {target_file} from before {proposal_id}")
    print(f"[rollback] Current state backed up as: {current_backup}")
    return True


def show_history(filepath_str: str):
    """Show all proposals applied to a file."""
    lineage = load_lineage()
    history = lineage.get("files", {}).get(filepath_str, [])

    if not history:
        print(f"[rollback] No history for: {filepath_str}")
        return

    print(f"\n[rollback] History for {filepath_str}:\n")
    print(f"  {'Timestamp':<20s} {'Proposal':<30s} {'Hash':<10s}")
    print(f"  {'─' * 60}")

    for entry in history:
        ts = entry.get("timestamp", "?")[:19]
        pid = entry.get("proposal_id", "manual")
        h = entry.get("hash_before", "?")
        print(f"  {ts:<20s} {pid:<30s} {h}")

    print()


def list_backups():
    """List all available backups."""
    lineage = load_lineage()
    proposals = lineage.get("proposals", {})

    if not proposals:
        print("[rollback] No backups recorded.")
        return

    print(f"\n[rollback] {len(proposals)} backup(s):\n")
    print(f"  {'Proposal':<30s} {'Target File':<40s} {'Status':<15s} {'Timestamp':<20s}")
    print(f"  {'─' * 105}")

    for pid, info in sorted(proposals.items()):
        print(f"  {pid:<30s} {info.get('target_file', '?'):<40s} {info.get('status', '?'):<15s} {info.get('timestamp', '?')[:19]}")
    print()


def show_diff(proposal_id: str):
    """Show what a proposal changed by diffing backup vs current."""
    lineage = load_lineage()
    proposal_info = lineage.get("proposals", {}).get(proposal_id)

    if not proposal_info:
        print(f"[rollback] No backup found for: {proposal_id}")
        return

    backup_path = BACKUPS_DIR / proposal_info["backup_file"]
    target_path = PROJECT_ROOT / proposal_info["target_file"]

    if not backup_path.exists():
        print(f"[rollback] Backup file missing")
        return

    if not target_path.exists():
        print(f"[rollback] Target file no longer exists")
        return

    # Simple line diff
    old_lines = backup_path.read_text().splitlines()
    new_lines = target_path.read_text().splitlines()

    print(f"\n[rollback] Diff for {proposal_id}:")
    print(f"  File: {proposal_info['target_file']}")
    print(f"  Before: {len(old_lines)} lines")
    print(f"  After:  {len(new_lines)} lines")
    print(f"  Delta:  {len(new_lines) - len(old_lines):+d} lines\n")

    # Show added lines (simple — lines in new but not old)
    old_set = set(old_lines)
    added = [l for l in new_lines if l not in old_set and l.strip()]
    if added:
        print(f"  Added lines ({len(added)}):")
        for line in added[:20]:
            print(f"    + {line[:100]}")
        if len(added) > 20:
            print(f"    ... and {len(added) - 20} more")
    print()


def main():
    parser = argparse.ArgumentParser(description="Proposal Rollback Engine")
    parser.add_argument("--backup", type=str, help="Backup a file (relative to project root)")
    parser.add_argument("--proposal-id", type=str, help="Proposal ID for backup tracking")
    parser.add_argument("--rollback", type=str, help="Rollback a specific proposal")
    parser.add_argument("--history", type=str, help="Show history for a file")
    parser.add_argument("--list", action="store_true", help="List all backups")
    parser.add_argument("--diff", type=str, help="Show diff for a proposal")
    args = parser.parse_args()

    ensure_dirs()

    if args.backup:
        backup_file(args.backup, args.proposal_id)
    elif args.rollback:
        rollback_proposal(args.rollback)
    elif args.history:
        show_history(args.history)
    elif args.list:
        list_backups()
    elif args.diff:
        show_diff(args.diff)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
