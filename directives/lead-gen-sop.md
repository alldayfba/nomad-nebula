# Lead Generation SOP

## Purpose
Scrape Google Maps for B2B business leads matching a query and location, then export results to CSV for outreach.

## Trigger
Run whenever new leads are needed for agency prospecting or client campaigns.

## Inputs
- `query` — what to search (e.g., "roofing companies", "dental clinics")
- `location` — city or region (e.g., "Austin TX", "Miami FL")
- `max_results` — how many listings to pull (default: 20)
- `fetch_emails` — whether to visit each website and extract emails (default: true, slower)

## Steps
1. Activate the virtual environment: `source .venv/bin/activate`
2. Run the scraper via the web UI at `http://localhost:5050` OR via CLI: `python execution/run_scraper.py --query "X" --location "Y" --max 20`
3. Review results in the UI table
4. Click Export → downloads `b2b_leads.csv`
5. Load CSV into your outreach tool (Apollo, Instantly, etc.)

## Outputs
- `b2b_leads.csv` with columns: business_name, owner_name, category, phone, email, website, address, rating, maps_url

## Known Issues & Warnings
- Google Maps rate-limits aggressive scraping — keep `max_results` under 50 per run
- `fetch_emails` = true significantly increases run time (visits each website)
- Some businesses block scrapers; email extraction will return N/A for those
- Playwright requires Chromium installed: `playwright install chromium`

## Last Updated
2026-02-21

---

## LLM Routing Rules (TP-015)

**Default model:** Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- Lead scraping and CSV processing
- ICP scoring and lead classification
- Data formatting and transforms
- Lead list deduplication

**Exception:** Escalate to Claude Sonnet 4.6 only for complex lead narrative synthesis or competitive positioning analysis. Never use Opus without explicit instruction.

---

## Ad Scripts & VSL Production (TP-025)

- Generate Meta/YouTube ad scripts targeting filtered lead segments using hook → agitation → solution → CTA framework
- Produce VSL scripts (Jeremy Haynes method) for landing pages: summary + hook + credibility + buying motives + offer + objections + qualification + CTA
- Always run asset generation after ICP filtering to ensure relevance
- VSL is token-heavy: use --single flag for one business/industry at a time
- Reference `directives/jeremy-haynes-vsl-sop.md` for authoritative VSL methodology (state price, no value stacks)

---

## Morning Briefing Integration (TP-027)

Each day at 08:00, consume the generated Morning Briefing from `directives/morning-briefing-sop.md`. Use TOP INSIGHT to adjust lead scoring weights. Route leads matching the RECOMMENDED TEST profile to dedicated nurture sequences. Flag competitor angles in lead research to surface differentiation points in outreach copy.

---

## VSL & DSL Funnel Expertise (TP-033)

Understand and implement Jeremy Haynes' VSL (Video Sales Letter) and DSL (Deck Sales Letter) call funnels for lead generation. Core framework: Cold Traffic → VSL Page (Headline + VSL + Embedded Application) → Confirmation Page (testimonials, breakout videos) → Sales Call. Effective VSLs answer buyer questions in exact sequence without counterparty response, replicate real sales conversations, and must minimize page friction. VSL pages use minimal design (headline, video, application only) to maximize play rate and lead quality.

---

## ICP Filtering (TP-035)

**Pre-Asset Generation:** After lead scraping, filter raw CSV through Claude-based ICP scorer before running email/VSL generation. Command: `python execution/filter_icp.py --input <csv> --threshold <1-10>`. ICP targets founder-led service/ecom/coaching with 4+ rating, website, real phone/email, and revenue plateau pain. Threshold 6 (default) is balanced; raise to 8 for stricter. Outputs `icp_score`, `icp_include`, `icp_reason` columns. Cost: ~$0.60 per 1K leads. Always filter before asset generation — unfiltered leads dilute ROI.

---

## Competitor Ad Intelligence (TP-039)

Before building lead-gen campaigns, review the latest Competitor Intelligence Log in `bots/ads-copy/memory.md`. Prioritize:
- Ad hooks running 30+ days (proven winners)
- Pain points and mechanisms appearing across 3+ competitor creatives
- Format breakdown (video vs. static) for your target audience segment
- CTAs that convert (extract from longest-running ads)

Apply these signals to hook selection and audience targeting — don't replicate, but learn the angle.

---

## Business Audit Generation (TP-045)

**Business Audit Generation Tool:** Call `execution/generate_business_audit.py` to create 4-asset audit packages (1-page audit doc, landing page, 3 ad angles, personalized email) for B2B prospects. Inputs: business_name (required), website, category, phone, address, rating, owner_name. Use UI at `http://localhost:5050/audit` or CLI. Cost: ~$0.10/audit. Outputs: Google Drive folder with all assets + shareable link. Deploy before outreach to warm leads with personalized operator-level analysis.


---

## Pipeline Orchestration & Quality Verification for Lead Gen Workflows (TP-2026-03-16-087)

• Pipeline Sequencing: Chain lead sourcing steps (scrape → filter → enrich → verify) with automatic error handling and step-by-step logging


---

## Session History Context Loading for Continuity & State Awareness (TP-2026-03-16-1089)

**Session Context:** This agent operates within SabboOS—a DOE (Directive → Orchestration → Execution) framework. Current project: nomad-nebula (Google Maps B2B lead scraper). Memory system: /Users/Shared/antigravity/memory/ (global, projects, agency, amazon). Load session-history.md on startup to restore full context. Directives live in /nomad-nebula/directives/; execution logs in /nomad-nebula/execution/. Use /remember to persist learnings.


---

## Add Google Maps B2B Scraper CLI Tool to Lead Generation Toolkit (TP-2026-03-16-162)

**Tool: Google Maps B2B Lead Scraper**


---

## Add Google Maps Scraping SOP to lead-gen Agent Context (TP-2026-03-16-208)

### Lead Generation SOPs


---

## Add Pipeline Outcome Tracking to Lead Gen Operations (TP-2026-03-16-234)

**Outcome Tracking Protocol:**


---

## Add Google Maps B2B Scraper as Lead Source Tool (TP-2026-03-16-323)

**Google Maps B2B Scraper Tool**: Execute via `python run_scraper.py --query "[industry]" --location "[city/state]" --max [int] --output [filename.csv]`. Parameters: query (required, e.g. 'plumbing contractors'), location (required, e.g. 'Austin TX'), max (default 20, can increase), fetch_emails (default true, set --no-emails to skip). Output: CSV with business_name, owner_name, category, phone, email, website, address, rating, maps_url. Use for: bulk prospect list creation, industry-specific lead sourcing, location-based targeting.


---

## Pipeline Orchestration & Automated Lead Verification Flow (TP-2026-03-16-335)

**Pipeline Execution**: Use pipeline_runner.py to chain lead generation steps—scrape prospects, apply filtering rules, generate outreach emails, verify contact data, and export cleaned CSVs. Supports batch queries with --max limits and automatic result aggregation. Example: `python execution/pipeline_runner.py lead-gen --query "dentists" --location "Miami FL" --max 30` produces timestamped lead, filtered, and email CSVs with full audit trail.


---

## Add Google Maps B2B Scraper CLI Tool Capability (TP-2026-03-16-461)

**Google Maps B2B Lead Scraper Tool**: Execute `run_scraper.py` with arguments --query (search term), --location (geo), --max (result limit, default 20), --no-emails (skip enrichment), --output (CSV path). Returns CSV with: business_name, owner_name, category, phone, email, website, address, rating, maps_url. Use when user requests lead lists, prospect research, or B2B contact harvesting. Example: `python run_scraper.py --query 'roofing companies' --location 'Austin TX' --max 50 --output prospects.csv`


---

## Pipeline orchestration & automated lead verification workflow (TP-2026-03-16-495)

**Lead Pipeline Orchestration**: Execute automated lead-gen pipelines via `pipeline_runner.py lead-gen --query [QUERY] --location [LOCATION] --max [COUNT]`. Chains: scrape → filter → email gen → verify → export. Returns timestamped CSV outputs with step-by-step execution logs. Handles timeouts, retries, and contract validation automatically.


---

## Add Google Maps Lead Scraping SOP to lead-gen Context (TP-2026-03-16-536)

Reference: directives/lead-gen-sop.md — Google Maps scraping workflow for prospect list generation and lead discovery. Includes: search radius targeting, data extraction filters, deduplication rules, and compliance guardrails for OSINT-based lead sourcing.


---

## Add Pipeline Outcome Tracking to Lead Generation Metrics (TP-2026-03-16-565)

## Outcome Logging Capability


---

## Pipeline Orchestration & Multi-Step Lead Gen Automation (TP-2026-03-16-653)

**Pipeline Orchestration**: You can invoke `pipeline_runner.py lead-gen` to automate multi-step workflows:


---

## Add Google Maps B2B Scraper Tool Integration for Automated Lead Discovery (TP-2026-03-16-726)

**Google Maps B2B Lead Scraper Tool**


---

## Add Google Maps Scraping Workflow to lead-gen SOP Memory (TP-2026-03-16-757)

## Google Maps Scraping Workflow (lead-gen-sop.md)


---

## Add pipeline outcome logging to lead tracking workflow (TP-2026-03-16-799)

When sourcing and researching prospects:


---

## Track lead generation execution outcomes for quality assurance (TP-2026-03-16-802)

Monitor outcomes.json for 'lead_generated' event type to track successful prospect research runs. Extract command parameters (--query values) from successful executions. Use this historical data to refine future search queries, identify high-performing prospect categories, and validate data quality metrics for lead lists.


---

## Pipeline Orchestration & Multi-Step Lead Gen Workflows (TP-2026-03-16-879)

PIPELINE ORCHESTRATION TOOL: Use `python execution/pipeline_runner.py lead-gen --query <QUERY> --location <LOCATION> --max <COUNT>` to run full lead generation pipelines that automatically chain: prospect scraping → qualification filtering → email generation → verification → CSV export. Pipeline auto-logs success/failure per step and outputs timestamped CSVs to .tmp/ directory. Use this for bulk prospecting tasks requiring multiple sequential tools.


---

## Add Google Maps Scraping SOP to lead-gen Memory (TP-2026-03-16-946)

**Google Maps Scraping Workflow (lead-gen-sop.md)**


---

## Add pipeline outcome logging to prospect research workflow (TP-2026-03-16-962)

## Pipeline Outcome Tracking


---

## Track Lead Generation Execution Outcomes for Quality Assurance (TP-2026-03-16-963)

Monitor execution outcomes in outcomes.json for lead_generated events. Log all successful scraper runs with query parameters and timestamps. Use outcome history to identify high-performing query types and avoid duplicate prospect research. Reference success patterns when selecting new prospect segments or industries to target.
