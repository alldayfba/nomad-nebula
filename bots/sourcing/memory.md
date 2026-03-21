# Sourcing Bot -- Memory
> bots/sourcing/memory.md | Version 1.0

---

## Purpose

This file is your persistent memory. You read it on every heartbeat check and update it when Sabbo approves or rejects work. This is how you improve over time without losing context.

---

## Approved Work Log

When Sabbo approves a sourcing run, deal recommendation, or pipeline result, log it here. This defines your quality bar.

Format:
```
### [DATE] -- [MODE] -- [BRAND/RETAILER]
What it was: [1-line description]
Why it worked: [Sabbo's feedback or inferred reason]
Key element to repeat: [retailer, threshold, strategy, etc.]
```

---

## Rejected Work Log

When Sabbo rejects a recommendation or flags a bad result, log it here. This defines what to avoid.

Format:
```
### [DATE] -- [MODE] -- [BRAND/RETAILER]
What failed: [1-line description]
Why it failed: [Sabbo's feedback]
What to do differently: [specific correction]
```

---

## Retailer Learnings

Running log of retailer-specific findings (scraping issues, best sections, selector changes).

Format:
```
### [DATE] -- [RETAILER]
Finding: [what was discovered]
Impact: [scraping fix, new clearance URL, selector update, etc.]
```

---

## Filter Calibration Log

Track when filter thresholds are adjusted and why (min ROI, min profit, BSR cap, seller count).

Format:
```
### [DATE] -- [FILTER]
Previous value: [old threshold]
New value: [new threshold]
Reason: [why it was changed]
```

---

## Pipeline Performance Log

Track scan results over time to measure hit rate and pipeline health.

Format:
```
### [DATE] -- [MODE] -- [COUNT]
Products scraped: [N]
Matched to Amazon: [N]
BUY verdicts: [N]
MAYBE verdicts: [N]
Notes: [any anomalies or observations]
```

---

*Last updated: 2026-03-16*
