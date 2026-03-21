# Testimonial Engine — SOP
> directives/testimonial-engine-sop.md | Version 1.0

---

## Purpose

Systematically capture student wins as marketing material. Auto-request testimonials at key milestones, manage the collection pipeline, and generate case studies for ads, VSL, and sales calls.

## Tools

| Tool | Script | Purpose |
|---|---|---|
| Testimonial Engine | `execution/testimonial_engine.py` | Request, collect, approve, publish testimonials |
| Case Study Generator | `execution/generate_case_study.py` | Generate formatted case studies from student data |
| Discord REST API | Bot token | Send DM requests to students |

## Auto-Request Triggers

| Milestone | Type Requested | Timing |
|---|---|---|
| `first_sale` | Screenshot | 1 hour after milestone logged |
| `listing_live` | Screenshot | 2 hours after |
| `profitable_month` | Written (2-3 sentences) | 24 hours after |
| `10k_month` | Video (60 seconds) | 48 hours after |

## Video Testimonial Questions

1. Where were you before the program?
2. What specific results have you gotten?
3. What would you tell someone considering joining?
4. What surprised you most about the process?

## Pipeline Stages

`requested` → `received` → `approved` → `published`

## Daily Execution

```bash
# Auto-scan and request (run daily)
python execution/testimonial_engine.py auto-request

# Check pipeline
python execution/testimonial_engine.py pipeline

# Generate case study from student data
python execution/generate_case_study.py --student "Mark"
```

## Referral Program

- Commission: 10% of first payment (~$500 avg)
- Code format: REF-{FIRSTNAME}-{4DIGITS}
- Payment: 30 days after referred student's first payment clears
- Tiers: 1 = standard | 3 in 12mo = + free Continuation month | 5+ = Ambassador

## Output Channels

- **Website:** Landing page testimonials
- **Ads:** Meta/Google ad creative
- **Discord:** #winners-circle + #ic-wins
- **VSL:** Video testimonial compilation
- **Sales calls:** Case study PDFs for pre-call nurture

---

*Testimonial Engine SOP v1.0 — 2026-03-16*
