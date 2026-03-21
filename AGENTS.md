# nomad-nebula — Agent Configuration

---

## CEO Layer (Master Routing)

The CEO agent sits above all other agents. It loads business context, detects the active constraint, and dispatches to the correct specialist.

| Trigger | Agent | Action |
|---|---|---|
| "CEO brief" / "daily brief" | `ceo` | Load context → constraint detection → output daily brief |
| "Weekly review" | `ceo` | Load context → 7-section weekly review |
| "What's the constraint?" | `ceo` | Constraint waterfall → single constraint |
| "What should I do today?" | `ceo` | Constraint + single action |
| CPL > target → detected | `ceo` → `ads-copy-agent` | Route to ads specialist |
| Close/show rate low → detected | `ceo` → `outreach-agent` | Route to outreach specialist |
| Low leads → detected | `ceo` → `lead-gen-agent` | Route to lead gen specialist |
| Students at risk → detected | `ceo` → `amazon-agent` | Route to Amazon specialist |
| VSL / content needed | `ceo` → `content-agent` | Route to content specialist |

## Specialized Agents

| Agent | Trigger phrases | Core skills |
|---|---|---|
| `ads-copy-agent` | "write Meta ads", "run competitor research", "morning briefing", "write VSL", "landing page copy" | Ad copy, VSL, landing pages, email copy, competitor research |
| `lead-gen-agent` | "scrape [niche] in [location]", "filter leads by ICP", "generate emails", "run the full pipeline" | Scraping, ICP scoring, email generation |
| `outreach-agent` | "run Dream 100 for [name]", "research [prospect]", "close rate is low", "show rate is low" | Dream 100, follow-up sequences, close/show rate recovery |
| `content-agent` | "write content for [platform]", "build content calendar", "repurpose this", "build the VSL" | Organic content, VSL, landing pages, brand voice |
| `amazon-agent` | "students at risk", "check fulfillment", "coaching session", "refund request" | Fulfillment, student success, coaching ops |

## SOP Mass Upload Flow

Drop any training file into `/Users/Shared/antigravity/memory/uploads/` then:
```bash
python execution/allocate_sops.py
```
System auto-classifies and routes each file to the correct agent's `skills.md`.
See: `directives/sop-allocation-sop.md`

---

## Project
B2B Lead Generation Tool — scrapes Google Maps for business contacts, filters by ICP, generates outreach assets (emails, ad scripts, VSLs), and runs hyper-personalized Dream 100 outreach campaigns.

## DOE Routing

| Task | Layer | How |
|------|-------|-----|
| "run the lead gen" | Orchestration | Read `directives/lead-gen-sop.md`, run `execution/run_scraper.py` |
| "run competitor research" | Orchestration | Read `directives/ads-competitor-research-sop.md`, run `execution/scrape_competitor_ads.py` |
| "scrape competitor ads" | Execution | Run `execution/scrape_competitor_ads.py --business [agency\|coaching]` |
| "send morning briefing" | Execution | Run `execution/send_morning_briefing.py` |
| "morning brief" | Execution | Run `execution/send_morning_briefing.py --dry-run` |
| "build client profile for [name]" | Orchestration | Read `directives/client-brand-voice-sop.md`, run `execution/scrape_client_profile.py` |
| "add client [name]" | Orchestration | Run `scrape_client_profile.py`, then create `bots/clients/[name].md` from template |
| "train the ads bot" | Directive | Read `directives/agent-training-sop.md` and follow phases |
| "set up a new bot" | Directive | Read `directives/agent-training-sop.md` |
| "ingest docs" | Execution | Run `execution/ingest_docs.py` |
| "add [doc] to memory" | Execution | `cp [doc] /Users/Shared/antigravity/memory/uploads/ && python execution/ingest_docs.py` |
| "scrape [query] in [location]" | Execution | Run `execution/run_scraper.py` directly |
| "filter leads by ICP" | Execution | Run `execution/filter_icp.py` |
| "score these leads" | Execution | Run `execution/filter_icp.py` |
| "generate emails" | Execution | Run `execution/generate_emails.py` |
| "write outreach emails" | Execution | Run `execution/generate_emails.py` |
| "generate ad scripts" | Execution | Run `execution/generate_ad_scripts.py` |
| "write Meta ads" | Execution | Run `execution/generate_ad_scripts.py --platform meta` |
| "write YouTube ads" | Execution | Run `execution/generate_ad_scripts.py --platform youtube` |
| "generate VSL" | Execution | Run `execution/generate_vsl.py` |
| "write VSL script" | Execution | Run `execution/generate_vsl.py` |
| "run full pipeline" | Orchestration | scrape → filter_icp → generate_emails (in order) |
| "export results" | Execution | Run `execution/run_scraper.py --output` |
| "update the scraping SOP" | Directive | Edit `directives/lead-gen-sop.md` |
| "update the ICP" | Directive | Edit `ICP_DEFINITION` in `execution/filter_icp.py` + update `directives/icp-filter-sop.md` |
| "update the email style" | Directive | Edit `SENDER_CONTEXT` in `execution/generate_emails.py` + update `directives/email-generation-sop.md` |
| "add a new execution step" | Executor agent | Create script in `execution/` |

---

## Dream 100 Routing

| Task | Layer | How |
|------|-------|-----|
| "run dream 100 for [name]" | Orchestration | Read `directives/dream100-sop.md`, run `execution/run_dream100.py` |
| "research [prospect/website]" | Execution | Run `execution/research_prospect.py` |
| "build dream 100 assets for [name]" | Execution | Run `execution/generate_dream100_assets.py` |
| "assemble the gammadoc" | Execution | Run `execution/assemble_gammadoc.py` |
| "run dream 100 batch" | Execution | Run `execution/run_dream100.py --batch prospects.csv` |
| "update dream 100 sop" | Directive | Edit `directives/dream100-sop.md` |
| "update case studies" | Directive | Edit `YOUR_CASE_STUDIES` in `execution/assemble_gammadoc.py` |
| "update booking link" | Directive | Edit `YOUR_BOOKING_LINK` in `execution/assemble_gammadoc.py` |

## Dream 100 Pipeline (in order)

```bash
# Option A: Full pipeline (one command)
python execution/run_dream100.py \
  --name "Prospect Name" \
  --website "https://their-site.com" \
  --niche "their niche" \
  --offer "what they sell" \
  --platform "meta"

# Option B: Step by step
# 1. Research
python execution/research_prospect.py --name "Name" --website "URL" --niche "niche" --offer "offer"

# 2. Generate assets (using research output)
python execution/generate_dream100_assets.py --research .tmp/research_<name>_<ts>.json --prospect-name "Name"

# 3. Assemble GammaDoc
python execution/assemble_gammadoc.py --research .tmp/research_<name>.json --assets .tmp/assets_<name>.json --prospect-name "Name"

# Option C: Batch (CSV of prospects)
python execution/run_dream100.py --batch prospects.csv
# CSV format: name,website,niche,offer,platform
```

## Dream 100 Follow-Up Sequence

Most sales close at touch 4-7. After sending the GammaDoc:

| Touch | Timing | Type |
|---|---|---|
| 1 | Day 0 | Send GammaDoc link |
| 2 | Open trigger | "Just saw you opened it" — send immediately |
| 3 | Day 3 | New insight or relevant stat |
| 4 | Day 7 | Similar client result |
| 5 | Day 14 | Quick question about their challenge |
| 6 | Day 21 | Case study |
| 7 | Day 30 | Final touch |

---

## Full Lead Gen Pipeline (in order)
```bash
# 1. Scrape
python execution/run_scraper.py --query "[niche]" --location "[market]" --max 50

# 2. Filter by ICP
python execution/filter_icp.py --input .tmp/leads_<ts>.csv

# 3. Generate emails
python execution/generate_emails.py --input .tmp/filtered_leads_<ts>.csv

# 4a. Generate Meta ad scripts
python execution/generate_ad_scripts.py --input .tmp/filtered_leads_<ts>.csv --platform meta

# 4b. Generate YouTube ad scripts
python execution/generate_ad_scripts.py --input .tmp/filtered_leads_<ts>.csv --platform youtube

# 5. Generate VSL (use --single for targeted use)
python execution/generate_vsl.py --input .tmp/filtered_leads_<ts>.csv --single "[business name]"
```

## Stack
- Flask app: `app.py` (port 5050)
- Scraper: `scraper.py` (Playwright + BeautifulSoup)
- Claude API: `anthropic` (ICP filter + asset generation)
- Virtual env: `.venv/`
- Env vars: `.env` (ANTHROPIC_API_KEY required for filter + generation scripts)

## Run the app
```bash
source .venv/bin/activate
python app.py
```

## DOE Layers

**Directives** → `/directives/`
- `lead-gen-sop.md` — scraping workflow
- `icp-filter-sop.md` — ICP scoring and filtering
- `email-generation-sop.md` — outreach email generation
- `asset-generation-sop.md` — ad scripts and VSL generation
- `dream100-sop.md` — Dream 100 hyper-personalized outreach pipeline
- `openclaw-handoff-sop.md` — OpenClaw task handoff protocol
- `knowledge-ingestion-sop.md` — document ingestion to shared memory
- `ads-competitor-research-sop.md` — Meta Ad Library competitor monitoring
- `morning-briefing-sop.md` — 8am daily ads briefing format and delivery
- `api-cost-management-sop.md` — LLM routing rules (Gemini Pro/Flash/Opus)
- `agent-training-sop.md` — how to onboard and train a new specialized bot
- `security-guardrails-sop.md` — access rules, hardware setup, incident response
- `client-brand-voice-sop.md` — how to build a client profile from scraped content

**Execution scripts** → `/execution/`
- `run_scraper.py` — scrape Google Maps → CSV
- `filter_icp.py` — score and filter leads by ICP
- `generate_emails.py` — personalized outreach emails per lead
- `generate_ad_scripts.py` — Meta/YouTube ad scripts per lead industry
- `generate_vsl.py` — full VSL script per lead industry
- `run_dream100.py` — Dream 100 master pipeline (research → assets → GammaDoc)
- `research_prospect.py` — scrape and analyze a prospect's website
- `generate_dream100_assets.py` — build deliverables FOR the prospect's business
- `assemble_gammadoc.py` — assemble the final GammaDoc markdown
- `ingest_docs.py` — document ingestion to shared memory
- `watch_inbox.py` — OpenClaw task watcher daemon
- `scrape_competitor_ads.py` — scrape Meta Ad Library for competitor intel
- `send_morning_briefing.py` — compile and send daily 8am ads briefing
- `scrape_client_profile.py` — scrape client website/Instagram/YouTube for brand voice

**Bot files** → `/bots/`
- `ads-copy/` — Ads & Copy Bot (active): identity, memory, skills, heartbeat, tools
- `content/` — Content Bot (stub, configure after ads-copy is stable)
- `outreach/` — Outreach Bot (stub, configure after content bot)
- `clients/` — Per-client brand voice files + `_template.md`

**Orchestration** → This file + global `doe-orchestrator` agent
