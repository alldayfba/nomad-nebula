# Ads & Copy Bot — Heartbeat
> bots/ads-copy/heartbeat.md | Version 1.0

---

## Purpose

You read this file every 60 minutes. It tells you your current state, what's pending, and whether you're on track. Update it when tasks complete or new tasks come in.

---

## Current Status

```
Last heartbeat: 2026-03-26
Status: IDLE
Current task: none
Next scheduled task: Morning briefing at 08:00
```

---

## Task Queue

Tasks waiting to be done. Process in order. Remove when complete.

```
[ ] [TASK] — [added by: Sabbo | system] — [priority: high/normal]
```

---

## In Progress

```
[ ] [TASK] — started [TIMESTAMP] — ETA: [estimate or "unknown"]
```

---

## Completed Today

Running log of what's been done. Clears at midnight.

```
[TIMESTAMP] — [TASK] — [result: done / approved / rejected]
```

---

## Pending Approvals

Work sent to Sabbo that hasn't been reviewed yet. Do not re-do these until feedback arrives.

```
[TIMESTAMP] — [ASSET TYPE] — [sent via: Telegram / email / file]
```

---

## Flags

Issues that need Sabbo's attention. Do not proceed past a flag without resolution.

```
⚠ [DATE] — [ISSUE] — [what you need to continue]
```

---

## Daily Schedule

| Time | Task |
|---|---|
| 08:00 | Run competitor research scrape → send morning briefing |
| On-demand | Copy requests from Sabbo |
| 60-min intervals | Read this file, update status, process queue |

---

## Health Check

On each heartbeat, verify:
- [ ] API keys still active (check `tools.md` → API section)
- [ ] Morning briefing was sent today (check Completed Today above)
- [ ] No flags unresolved for more than 24 hours
- [ ] LLM spend within budget (check `tools.md` → API Budget)

If any check fails, log to Flags section and message Sabbo.

---

*Last updated: 2026-03-26*
