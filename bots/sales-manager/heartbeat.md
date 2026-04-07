# Sales Manager Bot — Heartbeat
> bots/sales-manager/heartbeat.md | Version 1.0

---

## Purpose

This file is your status dashboard. It tracks what you're doing, what's queued, what's done, and what's blocked. Updated on every heartbeat cycle (60-minute intervals during business hours).

---

## Current Status

```
Last heartbeat: 2026-03-26
Status: IDLE
Current task: none
Next scheduled task: 07:30 — Morning standup
```

---

## Task Queue

*(Empty — tasks added as they come in)*

---

## In Progress

*(Nothing currently running)*

---

## Completed Today

*(Empty — entries added as tasks complete)*

```
### Format:
[HH:MM] — [TASK] — [RESULT/NOTES]
```

---

## Pending Approvals

*(Nothing pending Sabbo's review)*

---

## Flags

*(No active flags)*

```
### Format:
[SEVERITY: HIGH/MEDIUM/LOW] — [DESCRIPTION] — [RECOMMENDED ACTION]
```

---

## Daily Schedule

| Time | Task | Data Source |
|---|---|---|
| 07:30 | Morning standup agenda | `dashboard_client.py kpi` + `funnel` |
| 08:00 | Daily training block | Hormozi rotation (day-of-week) |
| 08:30 | Pre-call prep review | `dashboard_client.py calls` |
| 12:00 | Midday pipeline check | `dashboard_client.py funnel` |
| 17:00 | EOD report collection + analysis | `dashboard_client.py submissions` |
| 17:30 | Daily sales summary → CEO | `dashboard_client.py report` |

---

## Health Check

Run on every heartbeat:
- [ ] 247growth dashboard accessible? (`dashboard_client.py kpi` returns data)
- [ ] Pipeline data fresh? (last submission < 24 hours)
- [ ] All reps submitted EOD? (compliance check via `dashboard_client.py health`)
- [ ] No reps below RED threshold for 3+ consecutive days?
- [ ] Daily training session completed?
- [ ] CEO report sent?
- [ ] Memory file updated with today's learnings?

---

*Last updated: 2026-03-26*
