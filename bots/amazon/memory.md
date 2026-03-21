# Amazon Bot -- Memory
> bots/amazon/memory.md | Version 1.0

---

## Purpose

This file is your persistent memory. You read it on every heartbeat check and update it when Sabbo approves or rejects work. This is how you improve over time without losing context.

---

## Approved Work Log

When Sabbo approves a sourcing recommendation, PPC strategy, or listing optimization, log it here. This defines your quality bar.

Format:
```
### [DATE] -- [ASSET TYPE] -- [CONTEXT]
What it was: [1-line description]
Why it worked: [Sabbo's feedback or inferred reason]
Key element to repeat: [strategy, threshold, angle, etc.]
```

---

## Rejected Work Log

When Sabbo rejects or asks for a redo, log it here. This defines what to avoid.

Format:
```
### [DATE] -- [ASSET TYPE] -- [CONTEXT]
What failed: [1-line description]
Why it failed: [Sabbo's feedback]
What to do differently: [specific correction]
```

---

## Sourcing Learnings

Running log of what works and what does not in product sourcing. Updated as scan results are reviewed.

Format:
```
### [DATE] -- [BRAND/CATEGORY]
Finding: [what was discovered]
Outcome: [BUY / SKIP / lesson learned]
Implication: [threshold change, new watchlist entry, strategy shift]
```

---

## PPC & Listing Learnings

Learnings from Amazon PPC campaigns and listing optimization experiments.

Format:
```
### [DATE] -- [ASIN or Campaign]
What was tested: [description]
Result: [metrics or qualitative outcome]
What to do next: [action item]
```

---

## Student Coaching Notes

Notes from coaching sessions that inform future recommendations.

Format:
```
### [DATE] -- [STUDENT NAME or TIER]
Topic: [what was discussed]
Key takeaway: [what the student needed]
Pattern to watch for: [recurring issue or question]
```

---

*Last updated: 2026-03-16*
