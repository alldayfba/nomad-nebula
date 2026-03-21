# Closer Bot — Memory
> bots/closer/memory.md | Version 1.0

---

## Purpose

Persistent memory for prospecting and pipeline operations. This file compounds in value over time — every lead batch, ICP pass rate, booking pattern, objection signal, and conversion insight gets logged here. Read on every boot. Updated daily after the pipeline report and after every significant event (new signal pattern, conversion rate shift, objection emergence, source quality change).

---

## Lead Volume Log

*(Last 30 days — most recent first)*

```
### Format:
### [WEEK OF: YYYY-MM-DD]
New signals found:       X
ICP pass rate:           X% (X passed / X total)
Booked calls:            X
Show rate:               X%
Conversion to enrolled:  X%

Top signal sources this week:
  - Discord: X signals (X% pass rate)
  - Instagram: X signals (X% pass rate)
  - YouTube: X signals (X% pass rate)

Notable patterns: [anything unusual — high/low pass rate, new objection type, source quality shift]
```

*(No data yet — populate weekly)*

---

## Signal Source Performance

*(Track which channels produce highest-quality leads over time)*

```
### Format:
### [DATE RANGE]
| Source | Signals Found | ICP Pass Rate | Booking Rate | Show Rate | Notes |
|---|---|---|---|---|---|
| Discord sourcing | X | X% | X% | X% | |
| Discord general | X | X% | X% | X% | |
| Instagram comments | X | X% | X% | X% | |
| Instagram DMs | X | X% | X% | X% | |
| YouTube comments | X | X% | X% | X% | |
| Referrals (CSM) | X | X% | X% | X% | |
| Outbound batch | X | X% | X% | X% | |
```

*(No data yet — populate monthly)*

---

## ICP Gate Failure Patterns

*(Track which gates fail most — tells you where lead quality or sourcing is weak)*

```
### Format:
### [MONTH YYYY]
| Gate | Fail Count | Fail Rate | Common Reasons |
|---|---|---|---|
| Gate 1: Capital | X | X% | "don't have it yet", "borrowing", under $3K |
| Gate 2: Motivation | X | X% | passive income seekers, vague goals |
| Gate 3: Timeline | X | X% | "next year", "just researching" |
| Gate 4: Time | X | X% | under 5hrs/week, travel constraints |
| Gate 5: Coachability | X | X% | defensive, resistant to questions |
```

*(No data yet — populate monthly)*

---

## Objection Log

*(Recurring objections from prospects before the call — use for ICP and outreach refinement)*

```
### Format:
### [DATE] — [STAGE: Engaged/Qualified/Booked] — [OBJECTION TYPE]
**What they said:** [exact or paraphrased language]
**Context:** [where in the conversation it came up]
**How it was handled:** [script used, or what happened]
**Outcome:** [booked / VSL routed / disqualified]
**Pattern flag:** [if this is the 3rd+ time this objection appeared, flag it]
```

*(No objections logged yet)*

---

## Booking Message Performance

*(Track which DM/email hooks and CTAs produce the highest booking rate)*

```
### Format:
### [DATE] — [CHANNEL: IG DM / Email / SMS] — [MESSAGE VARIANT]
**Hook used:** [first line of message]
**CTA used:** [what the ask was]
**Sent to:** X leads (Tier A/B/C mix)
**Booked:** X (X% booking rate)
**Decision:** keep / modify / replace
**Notes:** [what worked, what didn't]
```

*(No message tests yet)*

---

## VSL Performance Log

*(Track engagement and conversion from leads routed to VSL)*

```
### Format:
### [DATE RANGE]
Leads routed to VSL:     X
VSL completion rate:     X% (if trackable)
Day 7 follow-up response: X%
Booked after VSL nurture: X (X% conversion)
Average days to book:    X days

Notable patterns: [any correlation between tier/source and VSL conversion]
```

*(No data yet — populate monthly)*

---

## Win Log

*(Deals that enrolled — what led to the booking and close)*

```
### Format:
### [DATE] — [TIER: A/B/C] — [PROGRAM: $X / payment plan]
**Lead source:** [Discord / IG / YouTube / referral]
**Signal that started it:** [what they said or did]
**ICP gates:** [all pass / flag noted]
**Days from signal to booking:** X days
**Days from booking to close:** X days
**What worked in outreach:** [specific hook or message]
**Closer who handled the call:** [rep name]
**Notes for replication:** [what to do the same next time]
```

*(No wins logged yet)*

---

## Loss Log

*(Deals that didn't close — use to refine ICP filter and follow-up sequences)*

```
### Format:
### [DATE] — [TIER: A/B/C] — [OUTCOME: No Close / No Show / Disqualified post-call]
**Lead source:** [Discord / IG / YouTube / referral]
**ICP gates:** [all pass / which gates flagged]
**Objection raised on call (from Sales Manager):** [type]
**Follow-up attempts:** X (X% response rate)
**Final disposition:** [archived / re-engaged / lost]
**Root cause:** [was this a qualification miss? wrong tier? wrong timing?]
**Fix applied:** [ICP gate change / outreach tweak / none]
```

*(No losses logged yet)*

---

## Re-Engagement Campaign Log

*(Track results from cold archive reactivations)*

```
### Format:
### [CAMPAIGN DATE] — [SEGMENT: e.g., "30-day no-close" / "60-day archive"]
Leads contacted: X
Response rate:   X%
Booked:          X
Closed:          X
Best-performing message: [subject line or hook]
```

*(No campaigns run yet)*

---

## Stale Lead Patterns

*(Recurring reasons leads go cold — use for process improvement)*

```
### Format:
### [DATE] — [PATTERN]
**Observation:** [what caused leads to stall at a specific stage]
**Stage where it happens:** [Engaged / Qualified / VSL Routed / Booked]
**Volume:** X leads affected
**Fix applied:** [touchpoint timing change / message change / ICP gate tightened]
**Result:** [improvement or still investigating]
```

*(No patterns identified yet)*

---

## System Learnings

*(Anything that changed how the pipeline is run — protocol updates, tool discoveries, edge cases)*

```
### Format:
### [DATE] — [CATEGORY: ICP / Outreach / Sequencing / VSL / Booking / Follow-up]
**What was learned:** [specific finding]
**What changed:** [protocol or script update]
**Reference updated:** [which file was updated, if any]
```

*(No learnings logged yet)*

---

*Last updated: 2026-03-16*
