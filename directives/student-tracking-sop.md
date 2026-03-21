# Student Progress Tracking SOP
> directives/student-tracking-sop.md | Version 1.0

---

## Purpose

Track Amazon FBA coaching students through 10 milestones from enrollment to $10K month. Detect stuck students early. Auto-dispatch support via sourcing agent and amazon agent. Feed fulfillment data into CEO constraint waterfall.

---

## Trigger

- CEO daily brief (automated at-risk check)
- User says "student progress" or "at-risk students"
- Weekly coaching review
- Student milestone update received

---

## Script

`execution/student_tracker.py`

**DB:** `.tmp/coaching/students.db`

---

## Commands

### Add a student
```bash
python execution/student_tracker.py add-student --name "John" --tier A --start-date 2026-02-01
python execution/student_tracker.py add-student --name "Sarah" --tier B --capital 15000
```

Tiers: A (beginner, $5K-$20K capital), B (existing seller, plateaued), C (investor)

### Update milestone
```bash
python execution/student_tracker.py update-milestone --student "John" --milestone product_selected
```

Milestones (in order): `enrolled`, `niche_selected`, `product_selected`, `supplier_contacted`, `sample_received`, `listing_created`, `listing_live`, `first_sale`, `profitable_month`, `10k_month`

### Log check-in
```bash
python execution/student_tracker.py check-in --student "John" --type weekly_call --summary "On track, sourcing samples" --mood positive
```

### At-risk students
```bash
python execution/student_tracker.py at-risk
```

### Cohort report
```bash
python execution/student_tracker.py cohort-report
```

### Single student detail
```bash
python execution/student_tracker.py student-detail --student "John"
```

---

## Milestone Expected Days (by Tier)

| Milestone | Tier A | Tier B | Tier C |
|---|---|---|---|
| enrolled → niche_selected | 7 | 3 | 5 |
| niche_selected → product_selected | 14 | 7 | 10 |
| product_selected → supplier_contacted | 7 | 5 | 5 |
| supplier_contacted → sample_received | 21 | 14 | 14 |
| sample_received → listing_created | 14 | 7 | 10 |
| listing_created → listing_live | 7 | 3 | 5 |
| listing_live → first_sale | 21 | 14 | 14 |
| first_sale → profitable_month | 30 | 21 | 30 |
| profitable_month → 10k_month | 60 | 45 | 60 |

**Stuck threshold:** 1.5x expected days on any milestone.

---

## CEO Dispatch Integration

| Condition | Dispatch |
|---|---|
| Stuck on `product_selected` >14d | `sourcing-agent` → reverse sourcing for their niche |
| Stuck on `listing_live` >14d | `amazon-agent` → listing review and optimization |
| Any student at-risk | `amazon-agent` via `student_tracker.py at-risk` |
| >15% of students at-risk | CEO constraint: "Delivery is the constraint" |

---

## Recommended Interventions (by Milestone)

| Milestone Stuck | Intervention |
|---|---|
| niche_selected | 1-on-1 niche selection call, provide 3 pre-vetted niches |
| product_selected | Dispatch sourcing agent for reverse sourcing |
| supplier_contacted | Share vetted supplier list, review Alibaba approach |
| sample_received | Follow up with supplier, check shipping status |
| listing_created | Amazon agent listing review |
| listing_live | Debug listing issues, check Brand Registry |
| first_sale | PPC audit, pricing review, listing optimization |
| profitable_month | P&L analysis, margin improvement strategies |

---

## Self-Annealing

- If expected days are consistently off: adjust per-tier benchmarks
- Track which interventions actually unstick students → prefer those
- If a milestone has >50% stuck rate across cohort: review teaching for that stage

---

*Student Progress Tracking SOP v1.0 — 2026-02-21*
