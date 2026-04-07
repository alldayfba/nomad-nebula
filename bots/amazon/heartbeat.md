# Amazon FBA Bot — Heartbeat
> bots/amazon/heartbeat.md | Version 2.0

---

## Purpose

You read this file every 60 minutes. It tells you your current state, what's pending, and whether you're on track. Update it when tasks complete or new tasks come in.

---

## Current Status

```
Last heartbeat: 2026-03-26 08:46
Status: IDLE
Current task: none
Next scheduled task: On-demand FBA tasks
```

---

## Task Queue

Tasks waiting to be done. Process in order. Remove when complete.

```
[ ] No tasks queued
```

---

## In Progress

```
No tasks in progress
```

---

## Completed Today

Running log of what's been done. Clears at midnight.

```
No tasks completed yet today
```

---

## Pending Approvals

Work sent to Sabbo that hasn't been reviewed yet.

```
No pending approvals
```

---

## Flags

Issues that need Sabbo's attention.

```
No flags
```

---

## Daily Schedule

| Time | Task |
|---|---|
| Daily | Monitor inventory levels, flag stockout risks |
| Weekly | PPC performance review, listing optimization opportunities |
| On-demand | Product sourcing runs, supplier evaluations, student coaching |

---

## Health Check

On each heartbeat, verify:
- [ ] Keepa API key active (check `.env` → KEEPA_API_KEY)
- [ ] Amazon Seller Central access functional
- [ ] No flags unresolved for more than 24 hours
- [ ] LLM spend within budget (Haiku for routine, Sonnet for analysis)

If any check fails, log to Flags section and message Sabbo.

---

## Task Queue Format

```yaml
task_id: ""
type: "sourcing | inventory | ppc | listing"
priority: "high | normal | low"
status: "pending | in_progress | completed"
input: {}
output: {}
created_at: ""
completed_at: ""
```

---

*Last updated: 2026-03-26*
