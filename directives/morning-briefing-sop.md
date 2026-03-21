# Morning Briefing SOP
> directives/morning-briefing-sop.md | Version 1.0

---

## Purpose

Every morning at 8:00 AM, Sabbo receives one briefing that covers everything needed to make the highest-leverage decisions for the day. No checking 5 dashboards. One read, then act.

---

## Trigger

- **Scheduled:** 08:00 daily (set up via cron or heartbeat)
- **On-demand:** Sabbo says "send me the briefing" or "morning brief"

---

## Script

```bash
source .venv/bin/activate
python execution/send_morning_briefing.py
```

---

## Briefing Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SABBO ADS BRIEF — {WEEKDAY}, {DATE}  |  08:00
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶ TOP INSIGHT TODAY
[Single most important finding — one sentence. The thing Sabbo needs to act on first.]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AGENCY — COMPETITOR INTEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[COMPETITOR 1]
  Longest-running ad:  [hook / angle — how long running]
  New this week:       [description or "none"]
  Format trend:        [video / static / carousel]
  Key angle:           [what pain point or promise they're leading with]

[COMPETITOR 2]
  ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COACHING — COMPETITOR INTEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[COMPETITOR 1]
  Longest-running ad:  [hook / angle — how long running]
  New this week:       [description or "none"]
  Format trend:        [video / static / carousel]
  Key angle:           [what pain point or promise they're leading with]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PLATFORM TRENDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Meta:   [Any notable format or targeting shift observed]
Other:  [YouTube / LinkedIn if applicable]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AD INTELLIGENCE — TOP PERFORMERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Top 3 highest-impression ads found across all competitors]

#1: [Competitor] — [Impressions estimate]
  Hook:      [First 2-3 seconds / opening line]
  Angle:     [Pain point or promise]
  Format:    [Video / Static / Carousel]
  Runtime:   [How long this ad has been active]
  Takeaway:  [What we should test based on this]

#2: ...
#3: ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NIGHTLY DELEGATION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Summary of what the CEO agent delegated overnight]
Tasks dispatched: [count]
Deliverables ready for QC: [count]

Ready now:
- [Deliverable 1] — [agent that produced it]
- [Deliverable 2] — [agent that produced it]

Needs your attention:
- [Item requiring Sabbo's decision]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RECOMMENDED TEST THIS WEEK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[One specific creative or copy test to run, based on the intel above.]
Business: [Agency / Coaching]
Test:     [What to test — hook, angle, format, audience]
Rationale: [Why — what competitor signal or trend supports this]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
End of Brief | Generated {TIMESTAMP}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Delivery

Send via the method configured in `bots/ads-copy/tools.md` → Morning Briefing Delivery.

After sending, log completion in `bots/ads-copy/heartbeat.md` → Completed Today.

---

## Quality Check Before Sending

- [ ] TOP INSIGHT is a specific, actionable observation — not a vague summary
- [ ] Every competitor entry has at least one real finding (no "no data" placeholders without explanation)
- [ ] RECOMMENDED TEST is tied to actual intel found today, not a generic suggestion
- [ ] Briefing is under 500 words — concise enough to read in 2 minutes

---

## Known Issues

- If competitor scrape fails, note it in briefing and send anyway with available data
- If no new ads found for a competitor, note "No changes since last check" — don't skip them

---

*Last updated: 2026-02-20*
