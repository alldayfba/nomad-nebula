# Training Officer Bot — Heartbeat
> bots/training-officer/heartbeat.md | Version 1.0

---

## Purpose

You read this file on every scan cycle. It tells you your current state, what's pending, and whether you're on track. Update it when scans complete or proposals are approved/rejected.

---

## Current Status

```
Last heartbeat: 2026-03-26
Status: ACTIVE
Current task: none
Next scheduled task: Daily scan on next trigger
```

---

## Task Queue

Tasks waiting to be done. Process in order. Remove when complete.

```
[ ] Initial full system scan — added by: system — priority: normal
```

---

## In Progress

```
(none)
```

---

## Completed Today

Running log of what's been done. Clears at midnight.

```
2026-03-16 — Bot directory created — result: done
```

---

## Pending Approvals

Proposals sent to Sabbo that haven't been reviewed yet.

```
(none)
```

---

## Flags

Issues that need Sabbo's attention. Do not proceed past a flag without resolution.

```
(none)
```

---

## Scan Schedule

| Trigger | Action |
|---|---|
| Manual ("run the training officer") | Full scan + report |
| New files in directives/, execution/, bots/ | Change detection + proposals |
| CEO brief generated | Constraint analysis |
| On-demand | Specific agent review, grading, proposals |

---

## Health Check

On each heartbeat, verify:
- [ ] All agent directories have current files (identity, heartbeat, memory, skills, tools)
- [ ] No proposals pending for more than 7 days without review
- [ ] No agent marked stale (14+ days without updates despite system changes)
- [ ] Grade history is being recorded for graded outputs

If any check fails, log to Flags section and message Sabbo.

---

*Last updated: 2026-03-26*
