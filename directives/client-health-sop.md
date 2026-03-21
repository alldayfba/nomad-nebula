# Client Health Monitor SOP
> directives/client-health-sop.md | Version 1.0

---

## Purpose

Track agency client engagement and health scores. Surface at-risk clients before they churn. Feed retention data into CEO constraint waterfall and auto-dispatch retention sequences via outreach agent.

---

## Trigger

- CEO daily brief (automated at-risk check)
- User says "client health" or "at-risk clients"
- Any client engagement signal received
- Weekly review cycle

---

## Script

`execution/client_health_monitor.py`

**DB:** `.tmp/agency/client_health.db`

---

## Commands

### Add a client
```bash
python execution/client_health_monitor.py add-client --name "ClientX" --mrr 10000
python execution/client_health_monitor.py add-client --name "ClientY" --mrr 5000 --start-date 2026-01-15
```

### Log engagement signals
```bash
python execution/client_health_monitor.py log-signal --client "ClientX" --type call_attended
python execution/client_health_monitor.py log-signal --client "ClientX" --type payment_received --value 10000
python execution/client_health_monitor.py log-signal --client "ClientX" --type feedback_positive --notes "Loved the new campaign results"
```

Valid signal types: `email_open`, `email_reply`, `call_attended`, `call_missed`, `call_rescheduled`, `payment_received`, `payment_late`, `payment_failed`, `feedback_positive`, `feedback_negative`, `feedback_neutral`, `slack_active`, `slack_inactive`, `deliverable_sent`, `deliverable_approved`, `deliverable_revision`

### Health report (all clients)
```bash
python execution/client_health_monitor.py health-report
```

### At-risk clients only
```bash
python execution/client_health_monitor.py at-risk
```

### Single client detail
```bash
python execution/client_health_monitor.py client-detail --client "ClientX"
```

### Refresh all scores
```bash
python execution/client_health_monitor.py refresh
```

### Export
```bash
python execution/client_health_monitor.py export --format json
```

---

## Health Score Algorithm

5 dimensions, weighted:
| Dimension | Weight | What It Measures |
|---|---|---|
| Engagement | 25% | Email opens, deliverable approvals, Slack activity |
| Responsiveness | 20% | Reply speed, call attendance |
| Payment | 25% | On-time payments, no failures |
| Satisfaction | 20% | Feedback signals (positive vs negative) |
| Tenure | 10% | How long they've been a client |

### Penalty Rules
- 2+ consecutive missed calls → -10 points
- Late payment → -10 points
- No contact in 14+ days → -15 points

### Thresholds
| Score | Status | Action |
|---|---|---|
| 60-100 | Healthy | Normal operations |
| 30-59 | At-Risk | CEO notified + outreach-agent dispatched (retention sequence) |
| 0-29 | Critical | **URGENT CEO alert** + Sabbo direct contact + outreach-agent |

---

## CEO Dispatch Integration

| Condition | Dispatch |
|---|---|
| Client health < 60 | `outreach-agent` → retention sequence via `outreach_sequencer.py` |
| Client health < 30 | **URGENT: Sabbo direct** + `outreach-agent` |

---

## Self-Annealing

- If clients consistently score in a narrow range: review signal types being logged
- If at-risk alerts are too frequent: check if penalty rules need tuning
- Log all churn events to learn which signals predicted churn earliest

---

*Client Health Monitor SOP v1.0 — 2026-02-21*
