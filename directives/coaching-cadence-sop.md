# Coaching Cadence — SOP
> directives/coaching-cadence-sop.md | Version 1.0

---

## Purpose

Structure the coaching delivery system for Amazon OS. Replace ad-hoc calls with a predictable schedule, topic rotation, and between-call accountability system.

## Inputs

- Student data from `execution/student_health_monitor.py`
- Milestone data from `execution/student_tracker.py`
- Discord channel IDs from `.env`

## Tools

| Tool | Script | Purpose |
|---|---|---|
| Coaching Cadence | `execution/coaching_cadence.py` | Call agendas, accountability prompts, challenges |
| Student Health Monitor | `execution/student_health_monitor.py` | At-risk students for call agenda |
| Discord REST API | Bot token in .env | Post messages to channels |

## Call Schedule

| Weeks | Cadence | Format |
|---|---|---|
| 1-4 | Tue + Thu (1hr each) | Group coaching calls |
| 5-8 | Tue group + Thu biweekly 1:1 (30min) | Mix of group and personal |
| 9-12 | Tue group only | Tapering toward graduation |

## 12-Week Topic Rotation

| Week | Topic | Focus |
|---|---|---|
| 1 | Account Setup & SellerAmp Walkthrough | Getting started right |
| 2 | First Storefront Stalk — Live Sourcing Demo | Finding first products |
| 3 | Product Evaluation Deep-Dive | SellerAmp, Keepa, ROI |
| 4 | Sourcing Systems & Deal Stacking | Repeatable workflows |
| 5 | Supplier Outreach & Negotiation | Wholesale and brand direct |
| 6 | Listing Optimization | Titles, bullets, keywords |
| 7 | Launch Strategy & PPC Basics | Getting first sales |
| 8 | PPC Optimization | ACOS, bids, structure |
| 9 | Scaling: VA Hiring & Automation | Systems for growth |
| 10 | Advanced Sourcing — Wholesale | Wholesale accounts, MOQs |
| 11 | Brand Direct & Inventory Management | Building relationships |
| 12 | 90-Day Review & Graduation Planning | What's next |

## Between-Call Accountability

| Day | Type | Channel |
|---|---|---|
| Monday | Weekly focus prompt | #ic-groupchat |
| Tuesday | Group call day | — |
| Wednesday | Midweek check-in prompt | #ic-groupchat |
| Thursday | Group call day (or 1:1) | — |
| Friday | Win collection prompt | #ic-groupchat |
| Saturday | Retail arbitrage challenge | #ic-groupchat |
| Sunday | Weekly planning prompt | #ic-groupchat |

## Daily Execution

### Pre-Call (30min before)
```bash
python execution/coaching_cadence.py generate-agenda --date today
```
Post agenda in #ic-call-calendar.

### Accountability (automated)
```bash
python execution/coaching_cadence.py send-accountability --day [today] --channel-id [ic-groupchat-id]
```

### Challenges (automated)
```bash
python execution/coaching_cadence.py send-challenge --day [today] --channel-id [ic-groupchat-id]
```

## Self-Annealing

Track which prompts get the most responses. After 4 weeks, rotate out low-engagement prompts and replace with high-engagement ones. The CSM memory file tracks this.

---

*Coaching Cadence SOP v1.0 — 2026-03-16*
