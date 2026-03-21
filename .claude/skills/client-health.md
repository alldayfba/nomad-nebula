---
name: client-health
description: Track agency client health scores and surface at-risk clients before they churn
trigger: when user says "client health", "at-risk clients", "check clients", "client status", "churn risk"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Client Health Monitor

## Directive
Read `directives/client-health-sop.md` for the full SOP before proceeding.

## Goal
Track agency client engagement, compute health scores (0-100), and surface at-risk clients before they churn.

## Inputs
Depends on the action:

**Health report (most common):** No inputs needed
**Add client:** name (required), mrr (required), start_date (optional)
**Log signal:** client name, signal type, optional value/notes

## Commands

### Health report (default action)
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/client_health_monitor.py health-report
```

### Add a client
```bash
python execution/client_health_monitor.py add-client --name "{name}" --mrr {mrr}
```

### Log engagement signal
```bash
python execution/client_health_monitor.py log-signal --client "{name}" --type {signal_type}
```

Valid signal types: `email_open`, `email_reply`, `call_attended`, `call_missed`, `call_rescheduled`, `payment_received`, `payment_late`, `payment_failed`, `feedback_positive`, `feedback_negative`, `feedback_neutral`, `slack_active`, `slack_inactive`, `deliverable_sent`, `deliverable_approved`, `deliverable_revision`

## Output
- Health scores per client (0-100, 5 dimensions)
- At-risk flags for clients below threshold
- DB stored at `.tmp/agency/client_health.db`

## Self-Annealing
If execution fails:
1. Check if `.tmp/agency/` directory exists
2. If DB is corrupted, delete and re-initialize
3. Fix the script, update directive Known Issues
4. Log fix in `SabboOS/CHANGELOG.md`
