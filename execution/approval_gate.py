#!/usr/bin/env python3
"""
approval_gate.py — Agent approval gate system.

Agents propose actions, humans review and approve/reject.
Prevents runaway automation by gating high-risk actions.

Usage:
    # Create a proposal
    python execution/approval_gate.py propose \
        --agent outreach \
        --action "Send 25 Dream 100 emails to dental clinics" \
        --risk review_before_send \
        --cost "$0.50"

    # List pending proposals
    python execution/approval_gate.py list

    # Approve a proposal
    python execution/approval_gate.py approve --id AP-2026-03-16-001

    # Reject a proposal
    python execution/approval_gate.py reject --id AP-2026-03-16-001 --reason "Too many recipients"

    # Check if a specific proposal is approved
    python execution/approval_gate.py check --id AP-2026-03-16-001

    # Programmatic:
    from execution.approval_gate import create_proposal, is_approved, list_pending
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

BASE_DIR = Path(__file__).parent.parent / ".tmp" / "approvals"
PENDING_DIR = BASE_DIR / "pending"
APPROVED_DIR = BASE_DIR / "approved"
REJECTED_DIR = BASE_DIR / "rejected"

RISK_LEVELS = ["auto_approve", "review_before_send", "requires_explicit_approval"]


def _ensure_dirs():
    for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _next_id():
    """Generate next proposal ID: AP-YYYY-MM-DD-NNN."""
    _ensure_dirs()
    today = datetime.now().strftime("%Y-%m-%d")
    prefix = "AP-{}-".format(today)

    existing = []
    for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR]:
        for f in d.glob("{}*.yaml".format(prefix)):
            try:
                seq = int(f.stem.split("-")[-1])
                existing.append(seq)
            except ValueError:
                pass

    next_seq = max(existing) + 1 if existing else 1
    return "{}{:03d}".format(prefix, next_seq)


def _write_yaml(path, data):
    """Write YAML file (or fallback to simple format)."""
    with open(path, "w", encoding="utf-8") as f:
        if yaml:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        else:
            for k, v in data.items():
                f.write("{}: {}\n".format(k, v))


def _read_yaml(path):
    """Read YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        if yaml:
            return yaml.safe_load(f)
        else:
            data = {}
            for line in f:
                if ": " in line:
                    k, v = line.split(": ", 1)
                    data[k.strip()] = v.strip()
            return data


# ── Public API ──────────────────────────────────────────────────────────────

def create_proposal(agent, action, risk_level="review_before_send",
                    cost="$0", details=None):
    """Create a new approval proposal. Returns proposal ID."""
    _ensure_dirs()
    proposal_id = _next_id()

    proposal = {
        "id": proposal_id,
        "agent": agent,
        "action": action,
        "risk_level": risk_level,
        "timestamp": datetime.now().isoformat(),
        "estimated_cost": cost,
        "details": details or "",
        "status": "pending",
    }

    path = PENDING_DIR / "{}.yaml".format(proposal_id)
    _write_yaml(path, proposal)
    return proposal_id


def list_pending():
    """List all pending proposals."""
    _ensure_dirs()
    proposals = []
    for f in sorted(PENDING_DIR.glob("AP-*.yaml")):
        proposals.append(_read_yaml(f))
    return proposals


def list_all():
    """List proposals across all states."""
    _ensure_dirs()
    result = {"pending": [], "approved": [], "rejected": []}
    for state, d in [("pending", PENDING_DIR), ("approved", APPROVED_DIR), ("rejected", REJECTED_DIR)]:
        for f in sorted(d.glob("AP-*.yaml")):
            result[state].append(_read_yaml(f))
    return result


def approve(proposal_id):
    """Approve a pending proposal. Moves file to approved/."""
    _ensure_dirs()
    src = PENDING_DIR / "{}.yaml".format(proposal_id)
    if not src.exists():
        return {"error": "Proposal not found: {}".format(proposal_id)}

    data = _read_yaml(src)
    data["status"] = "approved"
    data["approved_at"] = datetime.now().isoformat()

    dst = APPROVED_DIR / "{}.yaml".format(proposal_id)
    _write_yaml(dst, data)
    src.unlink()
    return data


def reject(proposal_id, reason=""):
    """Reject a pending proposal. Moves file to rejected/."""
    _ensure_dirs()
    src = PENDING_DIR / "{}.yaml".format(proposal_id)
    if not src.exists():
        return {"error": "Proposal not found: {}".format(proposal_id)}

    data = _read_yaml(src)
    data["status"] = "rejected"
    data["rejected_at"] = datetime.now().isoformat()
    data["rejection_reason"] = reason

    dst = REJECTED_DIR / "{}.yaml".format(proposal_id)
    _write_yaml(dst, data)
    src.unlink()
    return data


def is_approved(proposal_id):
    """Check if a proposal has been approved."""
    path = APPROVED_DIR / "{}.yaml".format(proposal_id)
    return path.exists()


def approve_all():
    """Approve all pending proposals. Returns count."""
    pending = list_pending()
    count = 0
    for p in pending:
        approve(p["id"])
        count += 1
    return count


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Agent approval gate system")
    sub = parser.add_subparsers(dest="command")

    # propose
    p_propose = sub.add_parser("propose", help="Create a new proposal")
    p_propose.add_argument("--agent", required=True)
    p_propose.add_argument("--action", required=True)
    p_propose.add_argument("--risk", default="review_before_send", choices=RISK_LEVELS)
    p_propose.add_argument("--cost", default="$0")
    p_propose.add_argument("--details", default="")

    # list
    sub.add_parser("list", help="List pending proposals")
    sub.add_parser("list-all", help="List all proposals")

    # approve
    p_approve = sub.add_parser("approve", help="Approve a proposal")
    p_approve.add_argument("--id", required=True)

    # approve-all
    sub.add_parser("approve-all", help="Approve all pending proposals")

    # reject
    p_reject = sub.add_parser("reject", help="Reject a proposal")
    p_reject.add_argument("--id", required=True)
    p_reject.add_argument("--reason", default="")

    # check
    p_check = sub.add_parser("check", help="Check if a proposal is approved")
    p_check.add_argument("--id", required=True)

    args = parser.parse_args()

    if args.command == "propose":
        pid = create_proposal(args.agent, args.action, args.risk, args.cost, args.details)
        print("Proposal created: {}".format(pid))

    elif args.command == "list":
        pending = list_pending()
        if not pending:
            print("No pending proposals.")
        else:
            print("{} pending proposal(s):".format(len(pending)))
            for p in pending:
                print("  {} | {} | {} | {}".format(
                    p.get("id"), p.get("agent"), p.get("action", "")[:60], p.get("risk_level")))

    elif args.command == "list-all":
        all_p = list_all()
        for state in ["pending", "approved", "rejected"]:
            items = all_p[state]
            if items:
                print("\n{} ({}):".format(state.upper(), len(items)))
                for p in items:
                    print("  {} | {} | {}".format(p.get("id"), p.get("agent"), p.get("action", "")[:60]))

    elif args.command == "approve":
        result = approve(args.id)
        if "error" in result:
            print("ERROR: {}".format(result["error"]))
        else:
            print("Approved: {}".format(args.id))

    elif args.command == "approve-all":
        count = approve_all()
        print("Approved {} proposal(s).".format(count))

    elif args.command == "reject":
        result = reject(args.id, args.reason)
        if "error" in result:
            print("ERROR: {}".format(result["error"]))
        else:
            print("Rejected: {} — {}".format(args.id, args.reason))

    elif args.command == "check":
        if is_approved(args.id):
            print("APPROVED: {}".format(args.id))
        else:
            print("NOT APPROVED: {}".format(args.id))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
