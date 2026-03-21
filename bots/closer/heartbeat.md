# Closer Bot — Heartbeat
> bots/closer/heartbeat.md | Version 1.0

---

## Purpose

This file is the Closer's status dashboard. It tracks what is currently running, what is queued, what is done today, and what is blocked. Updated on every heartbeat cycle (60-minute intervals during business hours, 8 AM – 5 PM).

---

## Current Status

```
Last heartbeat: [TIMESTAMP]
Status: IDLE
Current task: none
Next scheduled task: 08:00 — Morning signal scan
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

| Time | Task | Tool / Source |
|---|---|---|
| 08:00 | Morning signal scan (Discord, IG, YouTube) | Manual scan + `filter_icp.py` |
| 08:30 | ICP qualification batch on overnight signals | `filter_icp.py --batch` |
| 09:00 | Booking outreach for qualified leads | `multichannel_outreach.py` |
| 10:00 | VSL routing for warm-but-not-ready leads | `outreach_sequencer.py --mode nurture` |
| 12:00 | Stale lead review (> 3 days no touchpoint) | `pipeline_analytics.py stale --days 3` |
| 13:00 | Pipeline stage sync + CRM update | `dashboard_client.py contacts` + GHL |
| 13:30 | Pre-call research brief for tomorrow's calls | `research_prospect.py` |
| 13:45 | Handoff briefs to Sales Manager | `.tmp/closer/handoff-{name}.md` |
| 14:00 | Follow-up execution (no-close + no-show) | `outreach_sequencer.py` |
| 16:30 | Daily pipeline report + CEO summary | `pipeline_analytics.py report` |
| 17:00 | Memory.md update — patterns, conversion data | `bots/closer/memory.md` |

---

## Health Check

Run on every heartbeat:

- [ ] New signals from Discord scanned and classified?
- [ ] New IG comments/DMs checked and actioned?
- [ ] New YouTube comments reviewed?
- [ ] All qualified leads have a next action and a date?
- [ ] Any lead > 3 days without a touchpoint? (Flag immediately)
- [ ] Tomorrow's booked calls have research briefs ready?
- [ ] GHL CRM stages updated to reflect today's interactions?
- [ ] Any leads awaiting ICP qualification for > 4 hours?
- [ ] Any "Called → No Close" from today without a follow-up sequence triggered?
- [ ] Any "Called → No Show" from today without a rebook attempt?
- [ ] Memory.md updated with today's new leads, pass rate, and conversion patterns?
- [ ] CEO daily pipeline summary sent?

---

## Signal Source Status

Checked on every morning heartbeat:

| Source | Last Checked | New Signals Found | Status |
|---|---|---|---|
| Discord (sourcing channel) | [TIMESTAMP] | 0 | — |
| Discord (general) | [TIMESTAMP] | 0 | — |
| Discord (DMs) | [TIMESTAMP] | 0 | — |
| Instagram (comments) | [TIMESTAMP] | 0 | — |
| Instagram (DMs) | [TIMESTAMP] | 0 | — |
| YouTube (comments) | [TIMESTAMP] | 0 | — |

---

## Pipeline Snapshot (Updated Hourly)

```
Aware:          0  leads
Engaged:        0  leads
Qualified:      0  leads
VSL Routed:     0  leads
Booked:         0  calls
Called → Closed: 0  this week
Called → No Close: 0  pending follow-up
Called → No Show: 0  pending rebook
Cold Archive:   0  leads
```

---

*Last updated: 2026-03-16*
