# Agent-to-Agent Communication Protocol SOP

> Version 1.0 | Based on Kabrin's CEO → sub-agent delegation pattern

## Purpose

Enable structured communication between agents via a shared inbox/outbox system. The CEO agent delegates tasks, sub-agents report results, and findings are shared across agents without manual copy-paste.

## Architecture

```
/Users/Shared/antigravity/
├── inbox/                 # Tasks waiting for agents to pick up
│   ├── CEO-to-outreach-001.json
│   ├── CEO-to-content-002.json
│   └── sourcing-to-CEO-003.json
├── outbox/                # Completed results
│   ├── outreach-result-001.json
│   ├── content-result-002.json
│   └── sourcing-result-003.json
└── memory/
    └── agent-comms/       # Communication logs
        └── comms-log.jsonl
```

## Message Format

```json
{
    "id": "MSG-2026-03-16-001",
    "from": "CEO",
    "to": "outreach",
    "type": "task",
    "priority": "high",
    "subject": "Send Dream 100 batch to 25 dental clinics",
    "body": "Use the miami-dentists.csv lead list. Extract brand voice for each. Generate full Dream 100 package. Submit for approval before sending.",
    "attachments": [".tmp/leads/miami-dentists.csv"],
    "due": "2026-03-16T18:00:00",
    "status": "pending",
    "created": "2026-03-16T09:00:00"
}
```

## Message Types

| Type | Direction | Purpose |
|---|---|---|
| `task` | CEO → agent | Assign work |
| `result` | agent → CEO | Report completed work |
| `finding` | agent → agent | Share discovery (e.g., sourcing finds a deal → outreach gets notified) |
| `alert` | agent → CEO | Flag an issue (budget exceeded, error, anomaly) |
| `status` | agent → CEO | Progress update |
| `approval_request` | agent → CEO | Request approval for gated action |

## How Agents Use This

### Sending a Message

```python
from execution.agent_comms import send_message
send_message(
    from_agent="sourcing",
    to_agent="CEO",
    msg_type="finding",
    subject="Hot deal found: Jellycat plush 45% ROI",
    body="ASIN B0XXXXXXXX, buy $12, sell $22, ROI 45%, BSR 1,200 in Toys",
)
```

### Checking Inbox

```python
from execution.agent_comms import check_inbox
messages = check_inbox(agent="outreach")
for msg in messages:
    print(f"{msg['from']}: {msg['subject']}")
```

### Completing a Task

```python
from execution.agent_comms import complete_task
complete_task(
    message_id="MSG-2026-03-16-001",
    result="Sent 25 Dream 100 packages. 3 opened within 1 hour.",
    attachments=[".tmp/dream100/batch-results.json"],
)
```

## CEO Delegation Pattern

1. CEO identifies a goal (e.g., "Generate 50 leads this week")
2. CEO breaks into sub-tasks
3. CEO sends `task` messages to relevant agents
4. Agents execute and send `result` messages back
5. CEO aggregates results, updates brain.md
6. If an agent finds something relevant to another agent, it sends a `finding` message

## Cross-Agent Findings

| From | To | Example |
|---|---|---|
| sourcing → outreach | "New brand partnership opportunity with Jellycat — they're ungateable and selling well" |
| content → ads-copy | "This hook format got 3x engagement on IG — test as ad hook" |
| outreach → CEO | "5 prospects opened Dream 100 doc — schedule follow-up calls" |
| ads-copy → content | "Competitor running this angle successfully — create organic version" |
| CEO → all | "New client onboarded: Mike Walker. All agents update client context." |

## Execution Script

```bash
# Send a message
python execution/agent_comms.py send \
    --from CEO --to outreach --type task \
    --subject "Dream 100 batch" --body "Send to miami dentists list"

# Check inbox
python execution/agent_comms.py inbox --agent outreach

# Complete a task
python execution/agent_comms.py complete --id MSG-2026-03-16-001 --result "Done. 25 sent."

# View communication log
python execution/agent_comms.py log --last 20
```

## Known Issues

<!-- Append issues discovered during use below this line -->
