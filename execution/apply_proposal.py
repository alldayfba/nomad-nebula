#!/usr/bin/env python3
"""
Script: apply_proposal.py
Purpose: CLI to approve, reject, or batch-process Training Officer proposals
         without needing a Claude session.

Usage:
  python execution/apply_proposal.py --approve TP-2026-02-21-001
  python execution/apply_proposal.py --reject TP-2026-02-21-001 --reason "Too generic"
  python execution/apply_proposal.py --approve-all
  python execution/apply_proposal.py --approve-theme outreach
  python execution/apply_proposal.py --reject-theme ads --reason "Not needed yet"
  python execution/apply_proposal.py --list
  python execution/apply_proposal.py --show TP-2026-02-21-001
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula"
))

TMP_DIR = PROJECT_ROOT / ".tmp" / "training-officer"
PROPOSALS_DIR = TMP_DIR / "proposals"
LEARNINGS_FILE = TMP_DIR / "learnings.md"
CHANGELOG = PROJECT_ROOT / "SabboOS" / "CHANGELOG.md"


def load_env():
    """Load .env file."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def parse_proposal(filepath: Path) -> dict:
    """Parse a proposal YAML file into a dict."""
    content = filepath.read_text()
    info = {"file": filepath.name, "id": filepath.stem, "path": filepath, "raw": content}
    in_proposed_content = False
    proposed_lines = []

    for line in content.splitlines():
        if line.startswith("proposed_content:"):
            in_proposed_content = True
            continue
        elif in_proposed_content:
            if line.startswith("# RISK") or line.startswith("risk_level:"):
                in_proposed_content = False
            elif line.startswith("  "):
                proposed_lines.append(line[2:])  # Remove 2-space indent
            continue

        if line.startswith("target_agent:"):
            info["agent"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
        elif line.startswith("target_file:"):
            info["target_file"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
        elif line.startswith("upgrade_type:"):
            info["type"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
        elif line.startswith("title:"):
            info["title"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
        elif line.startswith("status:"):
            info["status"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()
        elif line.startswith("theme:"):
            info["theme"] = line.split('"')[1] if '"' in line else line.split(":")[1].strip()

    info["proposed_content"] = "\n".join(proposed_lines).strip()
    return info


def list_proposals(status_filter: Optional[str] = "pending") -> list:
    """List proposals, optionally filtered by status."""
    proposals = []
    if not PROPOSALS_DIR.exists():
        return proposals
    for f in sorted(PROPOSALS_DIR.glob("TP-*.yaml")):
        info = parse_proposal(f)
        if status_filter is None or info.get("status") == status_filter:
            proposals.append(info)
    return proposals


def update_proposal_status(proposal_path: Path, new_status: str):
    """Update the status field in a proposal YAML file."""
    content = proposal_path.read_text()
    content = re.sub(r'status:\s*"[^"]*"', f'status: "{new_status}"', content)
    proposal_path.write_text(content)


def backup_before_apply(target: str, pid: str):
    """Create a rollback backup before applying a proposal."""
    try:
        import subprocess
        script = PROJECT_ROOT / "execution" / "proposal_rollback.py"
        python = str(PROJECT_ROOT / ".venv" / "bin" / "python3")
        subprocess.run([python, str(script), "--backup", target, "--proposal-id", pid],
                       capture_output=True, text=True, timeout=10)
    except Exception:
        pass  # Backup is best-effort, don't block apply


def notify_ceo_brain(action: str, pid: str, title: str, agent: str):
    """Write proposal events to CEO brain.md for continuous learning."""
    brain_path = Path("/Users/Shared/antigravity/memory/ceo/brain.md")
    if not brain_path.exists():
        return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"| {now} | {action} | {pid} | {title[:60]} | {agent} |\n"
        with open(brain_path, "a") as f:
            f.write(entry)
    except Exception:
        pass  # Best-effort


def detect_cascade(proposal: dict):
    """After applying a proposal, check if downstream agents are affected."""
    target = proposal.get("target_file", "")
    pid = proposal.get("id", "?")
    proposed = proposal.get("proposed_content", "")

    # Import skill ownership to check if applied content mentions other agents' domains
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "execution"))
        from training_officer_scan import SKILL_OWNERSHIP, AGENT_REGISTRY
    except ImportError:
        return

    text = proposed.lower()
    cascades = []
    current_agent = proposal.get("agent", "")

    for skill, owner in SKILL_OWNERSHIP.items():
        if skill in text and owner != current_agent:
            cascades.append((skill, owner))

    if cascades:
        print(f"  [CASCADE] {pid} may affect:")
        for skill, owner in cascades[:5]:
            print(f"    → '{skill}' owned by {owner}")
        print(f"  Consider running a Training Officer scan to generate follow-up proposals.")


def apply_proposal(proposal: dict) -> bool:
    """Apply a proposal by appending its content to the target file."""
    target = proposal.get("target_file", "")
    proposed = proposal.get("proposed_content", "")
    title = proposal.get("title", "Untitled")
    pid = proposal.get("id", "?")
    agent = proposal.get("agent", "?")

    if not target or not proposed:
        print(f"  [SKIP] {pid}: Missing target_file or proposed_content")
        return False

    # Resolve target file path
    target_path = PROJECT_ROOT / target
    if target.endswith("/"):
        target_path = PROJECT_ROOT / target / "skills.md"

    if not target_path.exists():
        print(f"  [SKIP] {pid}: Target file not found: {target_path}")
        return False

    # Step 1: Backup before modifying
    backup_before_apply(target, pid)

    # Step 2: Apply the content
    existing = target_path.read_text()
    section_header = f"\n\n---\n\n## {title} ({pid})\n\n"
    target_path.write_text(existing + section_header + proposed + "\n")

    # Step 3: Notify CEO brain
    notify_ceo_brain("PROPOSAL_APPLIED", pid, title, agent)

    # Step 4: Check for cascading effects
    detect_cascade(proposal)

    print(f"  [APPLIED] {pid} → {target}")
    return True


def record_rejection(proposal_id: str, reason: str):
    """Record a rejection learning."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"| {now} | {proposal_id} | {reason} |"

    if not LEARNINGS_FILE.exists():
        header = """# Training Officer — Rejection Learnings
> Auto-populated when proposals are rejected. Used to improve future proposals.

| Date | Proposal | Reason |
|---|---|---|
"""
        LEARNINGS_FILE.write_text(header + entry + "\n")
    else:
        with open(LEARNINGS_FILE, "a") as f:
            f.write(entry + "\n")


def log_changelog(entries: list):
    """Append entries to CHANGELOG."""
    if not entries or not CHANGELOG.exists():
        return
    today = datetime.now().strftime("%Y-%m-%d")
    with open(CHANGELOG, "a") as f:
        for entry in entries:
            f.write(f"| {today} | `execution/apply_proposal.py` | {entry} |\n")


def main():
    parser = argparse.ArgumentParser(description="Apply or reject Training Officer proposals")
    parser.add_argument("--approve", type=str, help="Approve and apply a specific proposal ID")
    parser.add_argument("--reject", type=str, help="Reject a specific proposal ID")
    parser.add_argument("--reason", type=str, default="No reason given", help="Rejection reason")
    parser.add_argument("--approve-all", action="store_true", help="Approve all pending proposals")
    parser.add_argument("--approve-theme", type=str, help="Approve all pending proposals with this theme")
    parser.add_argument("--reject-theme", type=str, help="Reject all pending proposals with this theme")
    parser.add_argument("--list", action="store_true", help="List pending proposals")
    parser.add_argument("--show", type=str, help="Show a specific proposal")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    args = parser.parse_args()

    load_env()

    # ── List ──
    if args.list:
        pending = list_proposals("pending")
        if not pending:
            print("[apply-proposal] No pending proposals.")
            return
        print(f"\n[apply-proposal] {len(pending)} pending proposal(s):\n")
        for p in pending:
            theme = f"[{p.get('theme', '?')}]"
            print(f"  {p['id']:25s} | {p.get('agent', '?'):15s} | {theme:15s} | {p.get('title', 'Untitled')}")
        print()
        return

    # ── Show ──
    if args.show:
        pf = PROPOSALS_DIR / f"{args.show}.yaml"
        if not pf.exists():
            print(f"[apply-proposal] Not found: {args.show}")
            sys.exit(1)
        print(pf.read_text())
        return

    # ── Approve single ──
    if args.approve:
        pf = PROPOSALS_DIR / f"{args.approve}.yaml"
        if not pf.exists():
            print(f"[apply-proposal] Not found: {args.approve}")
            sys.exit(1)
        proposal = parse_proposal(pf)
        if proposal.get("status") != "pending":
            print(f"[apply-proposal] {args.approve} is not pending (status: {proposal.get('status')})")
            return
        if args.dry_run:
            print(f"[DRY RUN] Would approve and apply: {args.approve}")
            return
        if apply_proposal(proposal):
            update_proposal_status(pf, "applied")
            log_changelog([f"Applied {args.approve}: {proposal.get('title', '?')} → {proposal.get('agent', '?')}"])
        return

    # ── Reject single ──
    if args.reject:
        pf = PROPOSALS_DIR / f"{args.reject}.yaml"
        if not pf.exists():
            print(f"[apply-proposal] Not found: {args.reject}")
            sys.exit(1)
        if args.dry_run:
            print(f"[DRY RUN] Would reject: {args.reject} — {args.reason}")
            return
        proposal = parse_proposal(pf)
        update_proposal_status(pf, "rejected")
        record_rejection(args.reject, args.reason)
        notify_ceo_brain("PROPOSAL_REJECTED", args.reject, proposal.get("title", "?"), proposal.get("agent", "?"))
        print(f"[apply-proposal] Rejected {args.reject}: {args.reason}")
        return

    # ── Approve all ──
    if args.approve_all:
        pending = list_proposals("pending")
        if not pending:
            print("[apply-proposal] No pending proposals.")
            return
        print(f"[apply-proposal] Approving {len(pending)} proposals...")
        applied = 0
        changelog_entries = []
        for p in pending:
            if args.dry_run:
                print(f"  [DRY RUN] Would apply: {p['id']} → {p.get('agent', '?')}")
                continue
            if apply_proposal(p):
                update_proposal_status(p["path"], "applied")
                changelog_entries.append(f"Applied {p['id']}: {p.get('title', '?')} → {p.get('agent', '?')}")
                applied += 1
        if not args.dry_run:
            log_changelog(changelog_entries)
            print(f"\n[apply-proposal] Applied {applied}/{len(pending)} proposals.")
        return

    # ── Approve by theme ──
    if args.approve_theme:
        pending = list_proposals("pending")
        themed = [p for p in pending if p.get("theme", "").lower() == args.approve_theme.lower()]
        if not themed:
            print(f"[apply-proposal] No pending proposals with theme: {args.approve_theme}")
            return
        print(f"[apply-proposal] Approving {len(themed)} '{args.approve_theme}' proposals...")
        applied = 0
        changelog_entries = []
        for p in themed:
            if args.dry_run:
                print(f"  [DRY RUN] Would apply: {p['id']} → {p.get('agent', '?')}")
                continue
            if apply_proposal(p):
                update_proposal_status(p["path"], "applied")
                changelog_entries.append(f"Applied {p['id']}: {p.get('title', '?')} → {p.get('agent', '?')}")
                applied += 1
        if not args.dry_run:
            log_changelog(changelog_entries)
            print(f"\n[apply-proposal] Applied {applied}/{len(themed)} proposals.")
        return

    # ── Reject by theme ──
    if args.reject_theme:
        pending = list_proposals("pending")
        themed = [p for p in pending if p.get("theme", "").lower() == args.reject_theme.lower()]
        if not themed:
            print(f"[apply-proposal] No pending proposals with theme: {args.reject_theme}")
            return
        print(f"[apply-proposal] Rejecting {len(themed)} '{args.reject_theme}' proposals...")
        for p in themed:
            if args.dry_run:
                print(f"  [DRY RUN] Would reject: {p['id']}")
                continue
            update_proposal_status(p["path"], "rejected")
            record_rejection(p["id"], args.reason)
            print(f"  [REJECTED] {p['id']}: {args.reason}")
        return

    # No action specified
    parser.print_help()


if __name__ == "__main__":
    main()
