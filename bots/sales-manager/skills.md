# Sales Manager Bot — Skills
> bots/sales-manager/skills.md | Version 1.0

---

## Purpose

This file catalogs every skill the Sales Manager bot can execute. Each skill references specific SOPs, scripts, and data sources. Skills are invoked by trigger phrases or scheduled execution.

---

## Owned Claude Code Skills (Slash Commands)

| Skill | Slash Command | Directive | Script |
|---|---|---|---|
| Sales Prep | `/sales-prep` | — | `execution/research_prospect.py` |
| Pipeline Analytics | `/pipeline-analytics` | `directives/pipeline-analytics-sop.md` | `execution/pipeline_analytics.py` |
| Follow-Up | `/follow-up` | `directives/outreach-sequencer-sop.md` | `execution/outreach_sequencer.py` |

---

## Skill: EOD Review

**When to use:** After 5 PM daily, or when Sabbo says "review EOD"
**Reference in order:**
1. `execution/dashboard_client.py submissions` → Pull closer + SDR submissions
2. `execution/dashboard_client.py health` → Submission compliance scores
3. `SabboOS/Sales_Team_Playbook.md` Phase 8 → KPI targets
4. `bots/sales-manager/memory.md` → Historical baselines

**Output standard:** Per-rep RAG scorecard (table format) + team aggregate + flags for missing/below-threshold

---

## Skill: Daily Training Session

**When to use:** At 8:00 AM daily, or when Sabbo says "training block" / "train the team"
**Reference in order:**
1. Check day-of-week → select topic from Hormozi rotation
2. `SabboOS/Sales_Team_Playbook.md` Phase 4 → Training block structure
3. Load relevant creator brain for today's topic:
   - Mon: `bots/creators/johnny-mau-brain.md` (pre-frame)
   - Tue: `bots/creators/alex-hormozi-brain.md` (discovery)
   - Wed: Active scripts for the relevant offer
   - Thu: `.tmp/24-7-profits-sales-optimization.md` (objection battle cards)
   - Fri: Most recent call recording for game film
4. Active closing scripts for role-play scenarios

**Output standard:** 30-min session plan with manager talking points, 2-3 role-play scenarios, practice pair assignments

---

## Skill: Role Play Generation

**When to use:** On-demand for objection handling practice
**Reference in order:**
1. `.tmp/24-7-profits-sales-optimization.md` → Objection battle cards (Deliverable 2)
2. `bots/creators/johnny-mau-brain.md` → Pre-frame psychology + NLP techniques
3. `clients/kd-amazon-fba/scripts/closing-call-script.md` → Active closer script
4. `bots/sales-manager/memory.md` → Most common objections from real calls

**Output standard:** Scenario description, prospect persona (name, situation, likely objections), ideal handling path, 3 variations of closing questions

---

## Skill: Call Coaching

**When to use:** After call recording review, or when Sabbo says "call coaching for [name]"
**Reference in order:**
1. Call transcript (provided or from recording platform)
2. Active script for the offer (Amazon OS or Agency OS)
3. `.tmp/creators/hormozi-docx-extractions/sales-manager-guide-1.md` → Coaching tracker format
4. `bots/sales-manager/memory.md` → Rep's past coaching notes

**Output standard:** Timestamped feedback (what happened at each stage), action items (specific, measurable), what to replicate (positive reinforcement), what to fix (1-2 items max per session)

---

## Skill: Rep Scorecard

**When to use:** Weekly (Monday), or when Sabbo says "sales scorecard" / "who's underperforming"
**Reference in order:**
1. `execution/dashboard_client.py scorecard` → Weekly performance data
2. `SabboOS/Sales_Team_Playbook.md` Phase 8 → KPI targets
3. `bots/sales-manager/memory.md` → Historical performance, trend data

**Output standard:** Per-rep performance table with RAG status, rank order by revenue, trend arrows (up/down/flat vs prior week), coaching recommendations for AMBER/RED reps

---

## Skill: Hiring & Onboarding

**When to use:** When expanding the team, or when Sabbo says "hire a [role]" / "onboard [name]"
**Reference in order:**
1. `SabboOS/Sales_Team_Playbook.md` Phase 2 (hiring) + Phase 3 (onboarding)
2. `.tmp/creators/hormozi-docx-extractions/sales-rep-onboarding-sop-templates-1.md`
3. `.tmp/creators/hormozi-docx-extractions/sales-rep-interview-doc-breakdown.md`
4. `bots/creators/tim-luong-brain.md` → Scaling stages + when to hire

**Output standard:**
- Hiring: Job post, interview scorecard, role-play scenarios, trial period rubric, comp offer
- Onboarding: 2-week day-by-day plan, milestone criteria, Black Marker schedule, shadow assignments

---

## Skill: Revenue Forecast

**When to use:** When Sabbo asks "sales forecast" or CEO Agent requests projection
**Reference in order:**
1. `execution/dashboard_client.py kpi` → Current MTD data
2. `execution/dashboard_client.py funnel` → Pipeline velocity
3. `bots/sales-manager/memory.md` → Historical close rates, seasonal patterns

**Output standard:** 30/60/90-day revenue projection per offer, confidence intervals (conservative/expected/optimistic), key assumptions listed, risks flagged

---

## Skill: Commission Calculator

**When to use:** End of month, or when Sabbo says "commission report"
**Reference in order:**
1. `execution/dashboard_client.py commissions` → Commission data from 247growth
2. `SabboOS/Sales_Team_Playbook.md` Phase 1 → Comp structures
3. `bots/sales-manager/memory.md` → Historical payouts

**Output standard:** Per-rep breakdown (base + commission + bonuses - clawbacks = total), team total, comparison to prior month

---

## Skill: Constraint Detection

**When to use:** When Sabbo asks "what's the bottleneck?" / "sales constraint"
**Reference in order:**
1. `execution/dashboard_client.py funnel` → Full funnel data
2. `execution/dashboard_client.py noshow` → No-show analysis
3. `SabboOS/Agents/SalesManager.md` → Constraint waterfall
4. `bots/creators/jeremy-haynes-brain.md` → Bottleneck analysis framework

**Output standard:** First constraint identified in the waterfall, data supporting the diagnosis, recommended fix, expected impact

---

## Allocated SOPs

*(Auto-populated by allocate_sops.py — references to ingested SOPs for this bot)*

---

*Sales Manager Bot Skills v1.0 — 2026-03-16*
