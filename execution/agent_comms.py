#!/usr/bin/env python3
"""
agent_comms.py — Agent-to-agent communication protocol.

Structured inbox/outbox system for agents to delegate tasks,
share findings, and report results without manual copy-paste.

Usage:
    # Send a task from CEO to outreach
    python execution/agent_comms.py send \
        --from CEO --to outreach --type task \
        --subject "Send Dream 100 batch" \
        --body "Use miami-dentists.csv. Generate full packages."

    # Check inbox
    python execution/agent_comms.py inbox --agent outreach

    # Complete a task
    python execution/agent_comms.py complete \
        --id MSG-2026-03-16-001 \
        --result "Sent 25 packages. 3 opened within 1 hour."

    # View recent communication log
    python execution/agent_comms.py log --last 20

    # Programmatic:
    from execution.agent_comms import send_message, check_inbox, complete_task
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

INBOX_DIR = Path("/Users/Shared/antigravity/inbox")
OUTBOX_DIR = Path("/Users/Shared/antigravity/outbox")
COMMS_LOG = Path("/Users/Shared/antigravity/memory/agent-comms/comms-log.jsonl")

VALID_TYPES = ["task", "result", "finding", "alert", "status", "approval_request"]
VALID_AGENTS = ["CEO", "outreach", "content", "ads-copy", "sourcing", "amazon",
                "creators", "webbuild", "mediabuyer", "codesec", "training-officer",
                "project-manager"]


def _ensure_dirs():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    COMMS_LOG.parent.mkdir(parents=True, exist_ok=True)


def _next_id():
    """Generate next message ID."""
    today = datetime.now().strftime("%Y-%m-%d")
    prefix = "MSG-{}-".format(today)

    existing = []
    for d in [INBOX_DIR, OUTBOX_DIR]:
        for f in d.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                mid = data.get("id", "")
                if mid.startswith(prefix):
                    seq = int(mid.split("-")[-1])
                    existing.append(seq)
            except (json.JSONDecodeError, ValueError):
                pass

    next_seq = max(existing) + 1 if existing else 1
    return "{}{:03d}".format(prefix, next_seq)


def _log(message):
    """Append to communication log."""
    _ensure_dirs()
    with open(COMMS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(message) + "\n")


# ── Public API ──────────────────────────────────────────────────────────────

def send_message(from_agent, to_agent, msg_type="task", subject="",
                 body="", priority="normal", attachments=None, due=None):
    """Send a message from one agent to another."""
    _ensure_dirs()
    msg_id = _next_id()

    message = {
        "id": msg_id,
        "from": from_agent,
        "to": to_agent,
        "type": msg_type,
        "priority": priority,
        "subject": subject,
        "body": body,
        "attachments": attachments or [],
        "due": due,
        "status": "pending",
        "created": datetime.now().isoformat(),
    }

    # Save to inbox
    filename = "{}-to-{}-{}.json".format(from_agent, to_agent, msg_id.split("-")[-1])
    path = INBOX_DIR / filename
    path.write_text(json.dumps(message, indent=2), encoding="utf-8")

    # Log
    _log({"event": "sent", "id": msg_id, "from": from_agent, "to": to_agent,
          "type": msg_type, "subject": subject, "timestamp": message["created"]})

    return msg_id


def check_inbox(agent):
    """Get all pending messages for an agent."""
    _ensure_dirs()
    messages = []
    for f in sorted(INBOX_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            if data.get("to") == agent and data.get("status") == "pending":
                messages.append(data)
        except (json.JSONDecodeError, KeyError):
            pass
    return messages


def complete_task(message_id, result="", attachments=None):
    """Mark a task as complete and move to outbox."""
    _ensure_dirs()

    # Find the message in inbox
    source_file = None
    message = None
    for f in INBOX_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if data.get("id") == message_id:
                source_file = f
                message = data
                break
        except json.JSONDecodeError:
            pass

    if not message:
        return {"error": "Message not found: {}".format(message_id)}

    # Update status
    message["status"] = "completed"
    message["completed_at"] = datetime.now().isoformat()
    message["result"] = result
    message["result_attachments"] = attachments or []

    # Move to outbox
    outbox_file = OUTBOX_DIR / "{}-result.json".format(message_id)
    outbox_file.write_text(json.dumps(message, indent=2), encoding="utf-8")

    # Remove from inbox
    if source_file:
        source_file.unlink()

    # Log
    _log({"event": "completed", "id": message_id, "result_preview": result[:200],
          "timestamp": message["completed_at"]})

    return message


def get_log(last_n=20):
    """Get recent communication log entries."""
    if not COMMS_LOG.exists():
        return []

    lines = COMMS_LOG.read_text().strip().split("\n")
    entries = []
    for line in lines[-last_n:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


def broadcast(from_agent, msg_type, subject, body, to_agents=None):
    """Send a message to multiple agents."""
    if to_agents is None:
        to_agents = [a for a in VALID_AGENTS if a != from_agent]

    ids = []
    for agent in to_agents:
        mid = send_message(from_agent, agent, msg_type, subject, body)
        ids.append(mid)
    return ids


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Agent-to-agent communication")
    sub = parser.add_subparsers(dest="command")

    # send
    p_send = sub.add_parser("send", help="Send a message")
    p_send.add_argument("--from", dest="from_agent", required=True)
    p_send.add_argument("--to", dest="to_agent", required=True)
    p_send.add_argument("--type", default="task", choices=VALID_TYPES)
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body", default="")
    p_send.add_argument("--priority", default="normal", choices=["low", "normal", "high", "urgent"])

    # inbox
    p_inbox = sub.add_parser("inbox", help="Check agent inbox")
    p_inbox.add_argument("--agent", required=True)

    # complete
    p_complete = sub.add_parser("complete", help="Complete a task")
    p_complete.add_argument("--id", required=True)
    p_complete.add_argument("--result", default="")

    # log
    p_log = sub.add_parser("log", help="View communication log")
    p_log.add_argument("--last", type=int, default=20)

    # broadcast
    p_broadcast = sub.add_parser("broadcast", help="Send to all agents")
    p_broadcast.add_argument("--from", dest="from_agent", required=True)
    p_broadcast.add_argument("--type", default="alert", choices=VALID_TYPES)
    p_broadcast.add_argument("--subject", required=True)
    p_broadcast.add_argument("--body", default="")

    args = parser.parse_args()

    if args.command == "send":
        mid = send_message(args.from_agent, args.to_agent, args.type,
                           args.subject, args.body, args.priority)
        print("Sent: {} ({} → {})".format(mid, args.from_agent, args.to_agent))

    elif args.command == "inbox":
        messages = check_inbox(args.agent)
        if not messages:
            print("No pending messages for {}.".format(args.agent))
        else:
            print("{} pending message(s) for {}:".format(len(messages), args.agent))
            for m in messages:
                print("  {} | {} | {} | {}".format(
                    m["id"], m["from"], m["type"], m["subject"][:50]))

    elif args.command == "complete":
        result = complete_task(args.id, args.result)
        if "error" in result:
            print("ERROR: {}".format(result["error"]))
        else:
            print("Completed: {}".format(args.id))

    elif args.command == "log":
        entries = get_log(args.last)
        for e in entries:
            print("  {} | {} | {}".format(
                e.get("timestamp", "")[:19], e.get("event"), e.get("subject", e.get("id", ""))))

    elif args.command == "broadcast":
        ids = broadcast(args.from_agent, args.type, args.subject, args.body)
        print("Broadcast sent to {} agents.".format(len(ids)))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
