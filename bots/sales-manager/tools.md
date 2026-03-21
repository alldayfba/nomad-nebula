# Sales Manager Bot — Tools
> bots/sales-manager/tools.md | Version 1.0

---

## Access Policy

This bot operates under principle of least privilege. All access is scoped to sales operations data. Authentication via environment variables in `.env`. Never expose credentials in outputs.

---

## 247growth Dashboard Client (PRIMARY)

**Purpose:** Bridge to the 247growth.org dashboard — single source of truth for all live sales data
**Access type:** Read (all endpoints) / Write (none — dashboard is read-only from nomad-nebula)
**Script:** `execution/dashboard_client.py`
**Usage:**
```bash
# CLI
python execution/dashboard_client.py kpi
python execution/dashboard_client.py team
python execution/dashboard_client.py funnel --offer coaching
python execution/dashboard_client.py scorecard
python execution/dashboard_client.py report
python execution/dashboard_client.py commissions
python execution/dashboard_client.py submissions --role closer
python execution/dashboard_client.py submissions --role sdr
python execution/dashboard_client.py calls
python execution/dashboard_client.py health
python execution/dashboard_client.py noshow
python execution/dashboard_client.py objections
python execution/dashboard_client.py roster
python execution/dashboard_client.py utm
python execution/dashboard_client.py journey --contact-id <id>
python execution/dashboard_client.py contacts --query "<name>"
```
**Env vars:** `DASHBOARD_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DASHBOARD_ORG_ID`

---

## Pipeline Analytics

**Purpose:** Local pipeline funnel tracking and bottleneck detection
**Access type:** Read / Write (local SQLite)
**Script:** `execution/pipeline_analytics.py`
**Usage:** `python execution/pipeline_analytics.py report --period weekly`
**Note:** Secondary to dashboard_client.py for live data. Use for offline analysis or when dashboard is unavailable.

---

## Client Health Monitor

**Purpose:** Client retention scoring and at-risk detection
**Access type:** Read
**Script:** `execution/client_health_monitor.py`
**Usage:** `python execution/client_health_monitor.py`
**Note:** Feeds CSM coaching decisions. 5-dimension health score (Engagement, Responsiveness, Payment, Satisfaction, Tenure).

---

## Outreach Sequencer

**Purpose:** Trigger multi-touch follow-up sequences for non-closes
**Access type:** Read / Write
**Script:** `execution/outreach_sequencer.py`
**Usage:** `python execution/outreach_sequencer.py --mode followup --contact "<name>"`
**Directive:** `directives/outreach-sequencer-sop.md`

---

## Research Prospect

**Purpose:** Pre-call research automation for closers
**Access type:** Read (web scraping)
**Script:** `execution/research_prospect.py`
**Usage:** `python execution/research_prospect.py --name "<prospect>" --company "<company>"`

---

## CRM (GoHighLevel)

**Purpose:** Lead pipeline, contact management, call dispositions
**Access type:** Read via 247growth GHL sync (`/api/sync/ghl`). No direct GHL API access from this bot.
**Note:** All GHL data flows through 247growth dashboard → accessed via `dashboard_client.py`

---

## Call Recording Platform

**Purpose:** Call transcripts for AI QC system
**Access type:** Read only
**Platform:** Fathom (or manual upload)
**Note:** Transcripts are used for call coaching and script adherence scoring

---

## File System

**Purpose:** Read/write working files
**Access type:** Read/Write (scoped)
**Allowed paths:**
- `bots/sales-manager/` — Bot config files
- `.tmp/sales-manager/` — Daily reports, scorecards, coaching notes
- `SabboOS/` — Business OS docs (read), CHANGELOG (append)
- `directives/` — SOPs (read)
- `clients/` — Client scripts (read)
- `bots/creators/` — Creator brain files (read)

---

## What This Bot Cannot Access

- Payment processors (Stripe, Whop) — no direct access
- Ad accounts (Meta, Google) — that's the ads-copy bot's domain
- Client accounts directly — use dashboard or CRM
- Production databases — use dashboard_client.py API layer
- Other bots' config files — read-only at best
- Credentials or API keys — only via env vars, never in outputs

---

## API Budget

- Monthly token ceiling: Follow `directives/api-cost-management-sop.md`
- Sonnet is default for all analysis/coaching
- Haiku for data aggregation
- Opus reserved for script writing (approval required)

---

*Sales Manager Bot Tools v1.0 — 2026-03-16*
