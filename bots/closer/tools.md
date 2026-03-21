# Closer Bot — Tools
> bots/closer/tools.md | Version 1.0

---

## Access Policy

This bot operates under principle of least privilege. All access is scoped to prospecting and pipeline operations. Authentication via environment variables in `.env`. Never expose credentials in outputs. Never handle payment, enrollment, or production database writes directly.

---

## ICP Filter (PRIMARY QUALIFICATION TOOL)

**Purpose:** Run leads against Amazon OS ICP criteria — capital, motivation, timeline, time, coachability
**Access type:** Read / Write (local qualification log)
**Script:** `execution/filter_icp.py`
**Usage:**
```bash
# Qualify a single lead
python execution/filter_icp.py --lead "<name or handle>" --offer amazon

# Batch qualify a list
python execution/filter_icp.py --file .tmp/closer/leads-batch.csv --offer amazon

# View ICP pass rate stats
python execution/filter_icp.py --stats --days 30

# Output qualification result with tier tag
python execution/filter_icp.py --lead "<name>" --offer amazon --output json
```
**Note:** Run this on every lead before any outreach. No exceptions.

---

## Outreach Sequencer

**Purpose:** Generate and schedule multi-touch nurture, follow-up, and re-engagement sequences
**Access type:** Read / Write (sequence queue)
**Script:** `execution/outreach_sequencer.py`
**Directive:** `directives/outreach-sequencer-sop.md`
**Usage:**
```bash
# VSL nurture sequence (warm-but-not-ready)
python execution/outreach_sequencer.py --mode nurture --contact "<name>" --sequence vsl-30day

# Pre-call show rate confirmation sequence
python execution/outreach_sequencer.py --mode confirm --contact "<name>"

# Post-call no-close follow-up
python execution/outreach_sequencer.py --mode no-close --contact "<name>"

# No-show rebook sequence
python execution/outreach_sequencer.py --mode no-show --contact "<name>"

# Cold re-engagement (60+ day archive)
python execution/outreach_sequencer.py --mode reactivate --contact "<name>"
```

---

## Prospect Research

**Purpose:** Automated pre-call research brief for closer handoff
**Access type:** Read (web scraping, CRM data)
**Script:** `execution/research_prospect.py`
**Usage:**
```bash
python execution/research_prospect.py --name "<prospect name>" --context "amazon-fba"
python execution/research_prospect.py --name "<name>" --company "<company>" --context "amazon-fba"
```
**Output:** Saves research brief to `.tmp/closer/research-{name}-{date}.md` — automatically formatted for Sales Manager handoff

---

## Pipeline Analytics

**Purpose:** Pipeline stage tracking, velocity analysis, stale lead detection, constraint identification
**Access type:** Read / Write (local SQLite)
**Script:** `execution/pipeline_analytics.py`
**Directive:** `directives/pipeline-analytics-sop.md`
**Usage:**
```bash
# Full pipeline report
python execution/pipeline_analytics.py report --period daily

# Stale lead detection (leads with no touchpoint > N days)
python execution/pipeline_analytics.py stale --days 3

# Stage velocity analysis
python execution/pipeline_analytics.py velocity --period weekly

# Bottleneck detection
python execution/pipeline_analytics.py bottleneck
```

---

## Email Generation

**Purpose:** Personalized outreach email generation for warm leads
**Access type:** Read / Write (output to .tmp/)
**Script:** `execution/generate_emails.py`
**Directive:** `directives/email-generation-sop.md`
**Usage:**
```bash
# Generate warm outreach batch
python execution/generate_emails.py --offer amazon --segment warm --output .tmp/closer/emails-{date}.md

# Generate single personalized email
python execution/generate_emails.py --contact "<name>" --stage qualified --offer amazon

# Generate re-engagement email
python execution/generate_emails.py --contact "<name>" --mode reactivate
```

---

## Multichannel Outreach

**Purpose:** Deliver outreach messages across Instagram DM, email, and SMS
**Access type:** Read / Write (with rate limiting)
**Script:** `execution/multichannel_outreach.py`
**Usage:**
```bash
# Send across IG DM + email
python execution/multichannel_outreach.py --contact "<name>" --channel ig,email

# Send personalized DM only
python execution/multichannel_outreach.py --contact "<name>" --channel ig --message "<text>"

# Batch send (respects rate limits)
python execution/multichannel_outreach.py --file .tmp/closer/outreach-batch.csv --channel email
```
**Rate limits:** Follow rules in `directives/outreach-sequencer-sop.md`. Warm signals get personal messages. Never blast.
**Env vars:** `INSTAGRAM_ACCESS_TOKEN`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`

---

## 247growth Dashboard Client

**Purpose:** CRM and pipeline data from 247growth.org — booked calls, contact history, lead journey
**Access type:** Read (no writes from this bot — CRM updates happen via GHL directly or through dashboard)
**Script:** `execution/dashboard_client.py`
**Usage:**
```bash
# Booked calls today/tomorrow
python execution/dashboard_client.py calls

# Search for a contact
python execution/dashboard_client.py contacts --query "<name>"

# Full lead journey for a contact
python execution/dashboard_client.py journey --contact-id <id>

# Funnel analytics (pipeline stage counts)
python execution/dashboard_client.py funnel --offer coaching
```
**Env vars:** `DASHBOARD_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DASHBOARD_ORG_ID`

---

## CRM (GoHighLevel)

**Purpose:** Lead pipeline management, contact records, call dispositions, pipeline stage tracking
**Access type:** Read via 247growth GHL sync. Write via GHL web or API for stage moves and contact creation.
**Note:** This bot creates contacts in GHL for qualified leads and moves pipeline stages. It does NOT handle enrollments, payment confirmations, or program access.
**Env vars:** `GHL_API_KEY`, `GHL_LOCATION_ID`

---

## Google Sheets

**Purpose:** Lead list management, batch qualification results, ICP pass rate tracking
**Access type:** Read / Write
**Usage:** Lead lists from scraper.py are stored in Sheets. Qualification results and pipeline snapshots exported to Sheets for CEO visibility.
**Env vars:** `GOOGLE_SHEETS_CREDENTIALS`, `GOOGLE_SPREADSHEET_ID`

---

## File System

**Purpose:** Read/write working files for pipeline operations
**Access type:** Read/Write (scoped)
**Allowed paths:**
- `bots/closer/` — Bot config files (read/write)
- `.tmp/closer/` — Pipeline snapshots, lead batches, research briefs, follow-up plans
- `SabboOS/` — Business OS docs (read only), CHANGELOG (append only)
- `directives/` — SOPs (read only)
- `clients/kd-amazon-fba/` — Scripts and email sequences (read only)
- `bots/creators/` — Creator brain files (read only)

---

## What This Bot Cannot Access

- Payment processors (Stripe, Whop) — no access
- Ad accounts (Meta, Google) — ads-copy bot's domain
- Production databases — use dashboard_client.py API layer
- Enrollment or program access systems — CSM bot's domain
- Other bots' config files — read-only at best
- Credentials or API keys — only via env vars, never in outputs
- Call recordings — Sales Manager handles QC on call content

---

## API Budget

- Monthly token ceiling: Follow `directives/api-cost-management-sop.md`
- Haiku for signal scanning, ICP batch classification, CRM data parsing
- Sonnet for outreach writing, pipeline analysis, follow-up scripts
- Opus reserved for high-value close scripts (Tier A/B/C late-stage — approval required)

---

*Closer Bot Tools v1.0 — 2026-03-16*
