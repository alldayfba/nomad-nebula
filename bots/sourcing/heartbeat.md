# Sourcing Bot — Heartbeat
> bots/sourcing/heartbeat.md | Version 2.0

---

## Purpose

You read this file every 60 minutes. It tells you your current state, what's pending, and whether you're on track. Update it when tasks complete or new tasks come in.

---

## Current Status

```
Last heartbeat: 2026-03-16 12:00
Status: IDLE
Current task: none
Next scheduled task: On-demand sourcing requests
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
| On-demand | Product sourcing requests from Sabbo |
| On-demand | Batch ASIN checks, clearance scans |
| Cron (if configured) | Scheduled sourcing runs, price tracking, deal hunting |

---

## Health Check

On each heartbeat, verify:
- [ ] Keepa API key active (check `.env` → KEEPA_API_KEY)
- [ ] Playwright browsers functional
- [ ] No flags unresolved for more than 24 hours
- [ ] SQLite DB accessible at `.tmp/sourcing/price_tracker.db`

If any check fails, log to Flags section and message Sabbo.

---

*Last updated: 2026-03-16*
