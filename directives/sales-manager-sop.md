# Sales Manager SOP
> directives/sales-manager-sop.md | Version 1.0

---

## Purpose

Execute the daily, weekly, and monthly operating rhythm for the sales organization. This SOP covers the Sales Manager agent's core protocols for managing setters, closers, and CSMs across both Agency OS and Amazon OS.

---

## Trigger

- User says: "run the sales manager", "sales standup", "review EOD", "sales scorecard"
- CEO Agent delegation to Sales Manager
- Scheduled: daily at 07:30 AM (when scheduled skills are active)

---

## Agent

- **Primary:** Sales Manager (`SabboOS/Agents/SalesManager.md`)
- **Reports to:** CEO Agent (`SabboOS/Agents/CEO.md`)
- **Bot config:** `bots/sales-manager/`

---

## Data Source

**Primary:** 247growth.org dashboard via `execution/dashboard_client.py`

All live sales data (team performance, submissions, pipeline, commissions, contacts) comes from the dashboard. The dashboard_client.py script wraps the API and falls back to direct Supabase queries.

**Required env vars:**
```
DASHBOARD_URL=https://247growth.org
NEXT_PUBLIC_SUPABASE_URL=<supabase-url>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
DASHBOARD_ORG_ID=<org-id>
```

---

## Daily Protocol

### 1. Morning Standup (07:30 AM — 15 min)

**Data pull:**
```bash
python execution/dashboard_client.py kpi
python execution/dashboard_client.py funnel
python execution/dashboard_client.py calls
```

**Generate standup agenda:**
- Yesterday's wins (closes, revenue, notable deals)
- Today's targets (calls scheduled, pipeline value)
- Energy check (who's hot, who needs support)
- Pipeline alerts (at-risk deals, follow-ups due)

**Reference:** `SabboOS/Sales_Team_Playbook.md` Phase 4

---

### 2. Daily Training Block (08:00 AM — 30 min)

**Rotation (Hormozi framework):**
| Day | Topic | Primary Reference |
|---|---|---|
| Monday | Intro/Opening | `bots/creators/johnny-mau-brain.md` |
| Tuesday | Discovery | `bots/creators/alex-hormozi-brain.md` |
| Wednesday | Pitch/Presentation | Active offer scripts |
| Thursday | Close/Objection Handling | `.tmp/24-7-profits-sales-optimization.md` |
| Friday | Game Film | Most recent real call recording |

**Format:**
1. Manager demonstrates the technique (2 min)
2. Team practices in pairs (20 min)
3. Group debrief — what worked, what didn't (8 min)

**Rules:** 80% practice / 20% theory. Rotate partners. Record for absent reps.

---

### 3. Pre-Call Prep (08:30 AM)

**Data pull:**
```bash
python execution/dashboard_client.py calls
```

For each scheduled call, verify the closer has:
- Pre-call research completed (via `execution/research_prospect.py`)
- Prospect's application data reviewed
- Relevant case studies ready
- Script variant matched to prospect tier

---

### 4. EOD Report Collection (05:00 PM)

**Data pull:**
```bash
python execution/dashboard_client.py submissions --role closer
python execution/dashboard_client.py submissions --role sdr
python execution/dashboard_client.py health
```

**Process:**
1. Check submission compliance — flag any reps who haven't submitted
2. Compare each rep's actuals vs daily targets
3. Generate per-rep RAG scorecard
4. Flag any metric in RED status
5. Update `bots/sales-manager/memory.md` with notable observations

---

### 5. Daily Sales Summary → CEO (05:30 PM)

**Data pull:**
```bash
python execution/dashboard_client.py report
```

**Report format:**
```
DAILY SALES SUMMARY — [DATE]
═══════════════════════════════════
Calls Taken: X | Showed: X | Closed: X | Revenue: $X
Show Rate: X% | Close Rate: X% | Cash Collected: $X
Pipeline Value: $X | Upcoming Calls: X
═══════════════════════════════════
FLAGS: [any RED items or missing submissions]
CONSTRAINT: [first bottleneck in waterfall, if any]
```

Save to `.tmp/sales-manager/daily-report-{date}.md`

---

## Weekly Protocol

### Monday — Weekly Scorecard

**Data pull:**
```bash
python execution/dashboard_client.py scorecard
```

**Generate:** Per-rep scorecard with:
- KPIs vs targets (with RAG status)
- Trend arrows (up/down/flat vs prior week)
- Rank order by revenue
- Coaching recommendations for AMBER/RED reps

Save to `.tmp/sales-manager/scorecard-{date}.md`

---

### Wednesday — 1-on-1 Coaching Agendas

**Priority:** Underperformers first (RED/AMBER status)

**For each 1-on-1, prepare:**
1. Rep's scorecard data
2. 2-3 specific call moments to review (timestamps)
3. Action items from last coaching session (check memory.md)
4. 1-2 focus areas for the coming week

Save coaching notes to `.tmp/sales-manager/coaching-{rep}-{date}.md` and append to `bots/sales-manager/memory.md`

---

### Friday — Game Film + Team Review

**Select:** Best call and worst call of the week
**Format:** Group listen → identify what worked → identify what could improve → apply to next week's training

---

## Monthly Protocol

### Week 1 — Revenue Forecast

**Data pull:**
```bash
python execution/dashboard_client.py kpi
python execution/dashboard_client.py funnel
```

**Generate:** 30/60/90-day revenue projection per offer with:
- Conservative / Expected / Optimistic scenarios
- Key assumptions and risks
- Pipeline velocity trends

---

### Week 2 — Commission Calculation

**Data pull:**
```bash
python execution/dashboard_client.py commissions
```

**Generate:** Per-rep commission breakdown:
- Base + commission + bonuses - clawbacks = total
- Comparison to prior month
- Submit to Sabbo for approval

---

### Week 3 — Team Performance Review

**Decisions:**
- Promote candidates (consistently GREEN, exceeding targets)
- PIP candidates (consistently RED, 2+ weeks below threshold)
- Cut candidates (PIP expired, no improvement)
- Hiring needs (capacity analysis)

All decisions require data backing and Sabbo's approval.

---

### Week 4 — Constraint Report to CEO

**Generate:** Monthly sales constraint analysis:
- First bottleneck in the waterfall
- Supporting data
- Recommended intervention
- Expected impact
- Resources needed

---

## Scripts Used

| Script | Purpose |
|---|---|
| `execution/dashboard_client.py` | PRIMARY — all live data from 247growth.org |
| `execution/pipeline_analytics.py` | Local pipeline analysis (secondary) |
| `execution/client_health_monitor.py` | Client retention scoring |
| `execution/outreach_sequencer.py` | Follow-up sequence triggering |
| `execution/research_prospect.py` | Pre-call research automation |

---

## Reference Files

| File | What It Provides |
|---|---|
| `SabboOS/Sales_Team_Playbook.md` | Master operational reference (all 11 phases) |
| `SabboOS/AllDayFBA_EOD_Tracking.md` | EOD form structure + weekly targets |
| `SabboOS/Agency_OS.md` | Agency sales process + benchmarks |
| `SabboOS/Amazon_OS.md` | Amazon sales process + tier matching |
| `clients/kd-amazon-fba/scripts/closing-call-script.md` | Active closer script |
| `clients/kd-amazon-fba/scripts/setter-outreach-script.md` | Active setter script |
| `.tmp/24-7-profits-sales-optimization.md` | 9-stage script + objection battle cards |
| `bots/creators/alex-hormozi-brain.md` | KPI pairing, hiring, team management |
| `bots/creators/johnny-mau-brain.md` | Pre-frame psychology, NLP, identity selling |
| `bots/creators/tim-luong-brain.md` | Trifecta, AI QC, scaling stages |
| `bots/creators/jeremy-haynes-brain.md` | Bottleneck analysis, buyer spectrum |
| `bots/creators/nik-setting-brain.md` | Profile funnel, show rate optimization |

---

## Guardrails

1. Never skip the daily training block — even if revenue is up
2. Never fire without 2 weeks data + 2 weeks PIP
3. Never change comp without Sabbo's approval
4. Never A/B test scripts on the whole team — split test first
5. All daily reports saved to `.tmp/sales-manager/` for audit trail
6. All coaching notes appended to `bots/sales-manager/memory.md`

---

## Edge Cases

- **Dashboard unavailable:** Fall back to direct Supabase queries via `dashboard_client.py` (automatic)
- **No submissions today:** Flag in daily report, follow up with reps directly
- **New hire first week:** Use onboarding protocol from Playbook Phase 3, not standard daily rhythm
- **Revenue significantly above target:** Do NOT reduce training. Celebrate, but investigate if it's sustainable or one-time.
- **Revenue significantly below target:** Run constraint waterfall FIRST before any personnel changes

---

*Sales Manager SOP v1.0 — 2026-03-16*
