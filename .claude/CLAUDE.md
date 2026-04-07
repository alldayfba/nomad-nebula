# nomad-nebula — Project Context

## What This Project Is

Growth automation platform powering two businesses: **Agency OS** (done-for-you growth agency, $5K–$25K/mo retainers) and **Amazon OS** (FBA coaching, $3K–$10K programs). Started as a B2B lead gen scraper, now a full-stack engine covering lead generation, FBA sourcing across 300+ retailers, business intelligence dashboards, AI agent management, competitor intelligence, content batching, and multi-channel outreach.

### Core Capabilities
| Capability | Key Scripts | Web Route |
|---|---|---|
| **B2B Lead Gen** | `scraper.py`, `execution/filter_icp.py` | `POST /scrape`, `POST /export` |
| **Business Audit (4-asset)** | `execution/generate_business_audit.py` | `POST /audit/generate` (SSE) |
| **FBA Sourcing (8 modes)** | `execution/source.py` (CLI), `execution/multi_retailer_search.py` | `POST /sourcing/run`, `/sourcing/search`, `/sourcing/cli` |
| **Profitability Calc** | `execution/calculate_fba_profitability.py`, `execution/keepa_client.py` | (called internally) |
| **Student Success (CSM)** | `execution/student_health_monitor.py`, `execution/student_saas_sync.py` | `GET /ceo/api/students` |
| **Pipeline Analytics** | `execution/pipeline_analytics.py`, `execution/client_health_monitor.py` | `GET /ceo/api/pipeline` |
| **Agent Management** | `execution/training_officer_scan.py`, `execution/apply_proposal.py` | `GET /dashboard`, `POST /dashboard/api/scan` |
| **CEO Command Center** | `execution/send_morning_briefing.py`, `execution/update_ceo_brain.py` | `GET /ceo` |
| **Project Manager** | `execution/project_manager.py` | `GET /projects`, `/projects/api/*` |
| **Competitor Intel** | `execution/competitive_intel_cron.py`, `execution/scrape_competitor_ads.py` | (cron / CLI) |
| **Content Engine** | `execution/content_engine.py` | (CLI) |
| **Outreach Sequences** | `execution/outreach_sequencer.py`, `execution/generate_emails.py` | (CLI) |
| **Deal Scanning** | `execution/deal_scanner.py`, `execution/always_be_scanning.py` | (cron / CLI) |
| **Video Editor** | `execution/video_editor.py`, `execution/video_caption_renderer.py` | (CLI) |

### Stack
- **Backend:** Python + Flask (port 5050), Playwright (headless Chromium), BeautifulSoup
- **Data:** SQLite (sourcing results), Google Sheets/Docs/Drive (deliverables)
- **APIs:** Anthropic (Claude), Keepa (Amazon data, Pro tier), GHL (CRM), Discord (webhooks)
- **Deployment:** Modal (serverless webhooks), local dev with `.venv/`
- **Advanced:** Faster Whisper (voice-to-text), PyObjC (macOS native), yt-dlp (YouTube)
- **Virtual envs:** `.venv/` (Python 3.9), `.venv314/` (Python 3.14)

### Quick Start
```bash
source .venv/bin/activate && python app.py
# Web UI: http://localhost:5050
# Routes: / (leads), /sourcing (FBA), /audit (audits), /dashboard (agents), /ceo (command center), /projects (PM)
```

### Key CLI Commands
```bash
# B2B lead scrape
python execution/run_scraper.py --query "dentists" --location "Miami FL" --max 30

# FBA sourcing (8 modes: brand, category, retailer, scan, asin, oos, a2a, finder)
python execution/source.py brand --brand "Jellycat" --max-results 20
python execution/source.py scan --mode clearance
python execution/source.py asin --asin B0XXXXXXXX

# Multi-retailer product search
python execution/multi_retailer_search.py --query "Jellycat plush" --mode search

# Business audit generation
python execution/generate_business_audit.py --business "Acme Corp" --website "acme.com"

# Morning briefing
python execution/send_morning_briefing.py

# Agent health scan
python execution/training_officer_scan.py
```

### FBA Sourcing — Zero-Token-First Principle
1. **FREE:** Scrape 300+ retailers via Playwright (0 Keepa tokens)
2. **CHEAP:** Verify top candidates on Amazon via Keepa search (~1 token/ea)
3. **EXPENSIVE:** Deep verify with offers data (~21 tokens/ea) — optional

Retailer coverage: 15 Tier-1 (custom selectors: Walmart, Target, CVS, etc.) + 85+ Tier-2 (generic JSON-LD). Registry: `execution/retailer_registry.py`, selectors: `execution/retailer_configs.py`.

### Flask Routes Summary
| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Lead gen UI |
| `/scrape` | POST | Google Maps scrape |
| `/export` | POST | CSV export |
| `/audit` | GET | Audit generator UI |
| `/audit/generate` | POST | Generate 4-asset package (SSE) |
| `/sourcing` | GET | Sourcing UI (3 tabs) |
| `/sourcing/run` | POST | Single-URL sourcing pipeline |
| `/sourcing/search` | POST | Multi-retailer search |
| `/sourcing/cli` | POST | CLI mode (8 sourcing modes) |
| `/sourcing/history` | GET | SQLite results query |
| `/sourcing/retailers` | GET | Dry-run retailer list |
| `/api/health` | GET | Health check |
| `/api/sourcing` | POST | JSON API (used by SaaS scraper-service) |
| `/dashboard` | GET | Training Officer UI |
| `/dashboard/api/*` | GET/POST | Agent health, proposals, quality |
| `/projects` | GET | Project Manager UI |
| `/projects/api/*` | GET/POST | Project health, blockers, workload, congruence, timeline |
| `/ceo` | GET | CEO Command Center UI |
| `/ceo/api/*` | GET/POST | Pipeline, clients, students, brain health, project status |

### Directory Quick Reference
| Directory | Purpose | Count |
|---|---|---|
| `execution/` | Deterministic Python scripts | 97+ |
| `directives/` | SOPs (living instruction docs) | 37 |
| `bots/` | Specialized agent configs + memory | 9 agents |
| `bots/creators/` | Creator strategy brain files | 14+ |
| `SabboOS/` | Business OS docs + agent definitions | Agency_OS, Amazon_OS, 8 agents |
| `clients/` | Per-client workspaces | kd-amazon-fba |
| `templates/` | Flask HTML (index, sourcing, audit, dashboard, ceo, projects) | 7 |
| `.tmp/` | Intermediate files (regenerable) | — |

### Agent System
10 specialized bots in `bots/` (each has identity, heartbeat, skills, tools, memory files):
- **ads-copy** — Ad creative generation
- **content** — Content brainstorming + batching
- **outreach** — Email/SMS sequence design
- **sourcing** — FBA sourcing optimization
- **amazon** — Amazon mechanics + PPC
- **csm** — Student success monitoring, churn prevention, fulfillment automation
- **project-manager** — Project tracking, milestones, health scoring, congruence
- **video-editor** — Programmatic video editing (FFmpeg + Pillow + faster-whisper)
- **creators** — Creator strategy tracking (14+ brain files, auto-refreshed every 30 days)
- **clients** — Per-client context (template)

Training Officer manages proposal lifecycle: detect → review → approve/reject → apply. Dashboard at `/dashboard`.

## Claude Code Skills (Slash Commands)

17+ skills available in `.claude/skills/` — invoke via `/skill-name`:

**Tier 1 (Revenue Generators):**
| Skill | Trigger | Directive | Script |
|---|---|---|---|
| `/lead-gen` | "find leads", "scrape" | `lead-gen-sop.md` | `run_scraper.py` |
| `/cold-email` | "generate emails" | `email-generation-sop.md` | `generate_emails.py` |
| `/business-audit` | "audit this business" | `business-audit-sop.md` | `generate_business_audit.py` |
| `/dream100` | "gammadoc", "dream 100" | `dream100-sop.md` | `run_dream100.py` |
| `/source-products` | "find products", "source" | `amazon-sourcing-sop.md` | `source.py` |
| `/vsl` | "write vsl", "video sales letter" | `jeremy-haynes-vsl-sop.md` | `generate_vsl.py` |
| `/build-site` | "build website", "deploy site" | `WebBuild.md` | `push_to_github.py` |
| `/frontend-design` | "build ui", "build component", "build page", "design this", "make it look good" | `frontend-design-sop.md` | — (agent-driven, shadcn MCP + magic dry MCP) |
| `/video-edit` | "edit video", "add captions", "auto-edit", "color grade", "make a short", "reframe" | `video-editing-sop.md` | `video_editor.py` |

**Tier 2 (Operational Intelligence):**
| Skill | Trigger | Directive | Script |
|---|---|---|---|
| `/morning-brief` | "morning brief" | `morning-briefing-sop.md` | `send_morning_briefing.py` |
| `/client-health` | "client health" | `client-health-sop.md` | `client_health_monitor.py` |
| `/pipeline-analytics` | "bottleneck", "funnel" | `pipeline-analytics-sop.md` | `pipeline_analytics.py` |
| `/outreach-sequence` | "outreach sequence" | `outreach-sequencer-sop.md` | `outreach_sequencer.py` |
| `/follow-up` | "follow up", "nurture pipeline" | `outreach-sequencer-sop.md` | `outreach_sequencer.py` |
| `/sales-prep` | "prep for call", "sales prep" | — | `research_prospect.py` |
| `/project-status` | "project status", "where are we" | `project-manager-sop.md` | `project_manager.py` |

**Tier 3 (Supporting):**
| Skill | Trigger | Directive | Script |
|---|---|---|---|
| `/content-engine` | "generate content" | `content-engine-sop.md` | `content_engine.py` |
| `/student-onboard` | "onboard student" | `student-onboarding-sop.md` | `upload_onboarding_gdoc.py` |
| `/competitor-intel` | "competitor ads" | `ads-competitor-research-sop.md` | `scrape_competitor_ads.py` |
| `/student-health` | "student health", "at-risk", "churn risk" | `csm-sop.md` | `student_health_monitor.py` |
| `/deal-drop` | "deal drop", "format deals" | — | `format_deal_drop.py` |

**Orchestration:**
| Skill | Trigger | What |
|---|---|---|
| `/auto-outreach` | "auto outreach" | End-to-end: scrape → filter → email → send |
| `/auto-research` | "auto research" | Self-improving experiment pipeline (Karpathy pattern) |
| `/parallel-explore` | "explore approaches", "which approach", "best way to build", "parallel explore", "compare approaches" | Build 3 competing implementations in `.tmp/explore/`, test all, rate, promote winner |

**Scheduled skills config:** `.claude/scheduled-skills.yaml` | Runner: `execution/run_scheduled_skills.py`

**Quality:**
| Skill | Trigger | What |
|---|---|---|
| `/code-review` | "review this code", "fresh eyes", "code review" | Fresh-context subagent review: Implement → Review → Resolve |

**Scale & Infrastructure:**
| Script | Purpose |
|---|---|
| `extract_brand_voice.py` | Auto-scrape YT/IG/LinkedIn/website → brand voice markdown |
| `approval_gate.py` | Agent proposes → human approves → agent executes |
| `multichannel_outreach.py` | Send across IG DMs, X DMs, email with rate limiting |
| `voice_memo_generator.py` | Eleven Labs voice cloning + personalized audio memos |
| `agent_comms.py` | Agent-to-agent inbox/outbox communication protocol |
| `launch_chrome.sh` / `kill_chrome.sh` | Multi-Chrome parallel browser instances |

**Subagents:** `.claude/agents/` — scoped-tool agents (researcher, executor, reviewer, resolver, documenter). Trigger documenter automatically after any self-annealing session where a script in `execution/` changed — it reads the updated script and the corresponding directive, then closes the gap between what the code does and what the SOP says.

**Directives:** `agent-execution-loop-sop.md` (PTMRO), `auto-research-sop.md` (experiments), `code-review-sop.md` (verification loops), `approval-gate-sop.md` (safety gates), `brand-voice-extraction-sop.md` (voice profiling), `dream100-at-scale-sop.md` (4-agent concurrent pipeline), `multi-chrome-sop.md` (parallel browsers), `agent-communication-sop.md` (inter-agent messaging), `search-routing-sop.md` (3-tier search decision tree), `response-style-sop.md` (4 style modes), `output-quality-injections.md` (quality gates for client/student output), `cloud-monitoring-sop.md` (Discord notifications on all Modal jobs), `parallel-exploration-sop.md` (3-approach temp folder pattern)

**Meta skill:** `/doe` — routes any task through the DOE framework.

Skills reference directives at runtime (never duplicate content). Spec: `.claude/skills/_skillspec.md`.

## Built-in Claude Code Commands

These are native Claude Code features (not custom skills). Use them directly:

| Command | Purpose |
|---|---|
| `/init` | Auto-generate optimized CLAUDE.md by scanning entire workspace — creates knowledge-compressed summary |
| `/insights` | Analyze all conversation history for global patterns, generates HTML report with high-ROI learnings |
| `/context` | Show current context window usage breakdown (system prompt %, tools %, available space) |
| Agent Teams | Native multi-agent orchestration — team lead + specialist agents with direct inter-agent communication. Use for complex tasks requiring parallel specialized work. |

**When to use:**
- `/init` — when setting up a new project or after major restructuring
- `/insights` — every 4-5 projects to extract cross-project patterns for global CLAUDE.md
- `/context` — when debugging token usage or optimizing system prompt size
- Agent Teams — for tasks needing 3+ specialized agents working together (e.g., research + build + review)

## Memory System v3.0 — SQLite + FTS5 (MANDATORY)

Source of truth is **`/Users/Shared/antigravity/memory/ceo/memory.db`** (SQLite with FTS5 BM25 search). brain.md is now a generated export.

### Per-Prompt Protocol (EVERY response)

Scan this interaction for signals (decisions, preferences, learnings, errors, ideas, people, assets, corrections). If ANY signal found, store it immediately:

```bash
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula python3 execution/memory_store.py add \
    --type <type> --category <category> \
    --title "<one-line summary>" \
    --content "<full detail>" \
    --tags "<comma,separated>"
```

**Types:** decision, learning, preference, event, asset, person, error, correction, idea
**Categories:** agency, amazon, sourcing, sales, content, technical, agent, client, student, general

For corrections to existing knowledge:
```bash
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula python3 execution/memory_store.py update \
    --search "<what to find>" --content "<new info>" --reason "<why changed>"
```

### Session Start Protocol

Run at the beginning of every session to load relevant context:
```bash
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula python3 execution/memory_boot.py
```

### Auto-Retrieval (before task-relevant responses)

Before responding to tasks, search for relevant memories:
- Client/student name mentioned → `memory_recall.py --query "<name>" --type person`
- Technical decision needed → `memory_recall.py --query "<topic>" --type decision,learning`
- Error/bug encountered → `memory_recall.py --query "<error>" --type error,learning`
- Strategy question → `memory_recall.py --query "<topic>" --type decision,preference`

```bash
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula python3 execution/memory_recall.py --query "<query>" [--type <type>] --limit 5
```

### Per-File-Change Protocol (Automatic)

File changes in tracked directories (directives/, execution/, SabboOS/, bots/, clients/) are automatically captured by the PostToolUse hook → `memory_file_change.py`. No manual action needed.

### Session Close (Automatic)

Stop hook runs `memory_session_close.py` + `memory_maintenance.py` automatically. No manual action needed.

### Memory Tools Reference
| Script | Purpose |
|---|---|
| `memory_store.py` | Add/update/merge/delete/search/stats |
| `memory_recall.py` | Search with BM25 ranking + recency/access boost |
| `memory_boot.py` | Session start context loader |
| `memory_export.py` | Generate brain.md from DB |
| `memory_maintenance.py` | Integrity, archive, decay, dedup |
| `memory_migrate.py` | One-time import from brain.md (already run) |
| `memory_session_close.py` | Stop hook — session context + file events |
| `memory_file_change.py` | PostToolUse hook — tracked file changes |

**Nothing is too small to capture. If it happened, the DB knows about it.**

## Self-Modifying Rules Protocol
When the user corrects you, rejects an approach, or you hit a bug from a wrong assumption:
1. Fix the immediate issue
2. Append a new rule to the `## Learned Rules` section at the bottom of this file
3. Format: `[number]. [CATEGORY] Always/Never do X because Y.`
4. Rules are numbered sequentially — check the last number before appending
5. Check for duplicates — don't add a rule that already exists
6. Categories: FRONTEND, BACKEND, COPY, WORKFLOW, TOOLING, DATA, SECURITY, GENERAL

Full SOP: `directives/learned-rules-sop.md`

## Reverse Prompting Protocol
For complex tasks (client deliverables, campaigns, new features):
Before executing, ask 3-5 clarifying questions to fill gaps in required fields.
Only skip if the user explicitly says "just do it" or provides comprehensive context.
If a prompt contract exists for the task, check required fields against what was provided.
Contracts live in `execution/prompt_contracts/contracts/`.

Full SOP: `directives/reverse-prompting-sop.md`

## Prompt Contracts
Before generating client-facing output, check if a contract exists in `execution/prompt_contracts/contracts/`.
If it does, validate your output against it before returning.
Available contracts: lead_gen_email, ad_script, vsl_section, business_audit, sourcing_report.

Full SOP: `directives/prompt-contracts-sop.md`

## Auto-Routing Protocol (MANDATORY)

Before responding, scan the current task against these triggers. If a trigger matches, run the corresponding tool **automatically** — don't ask, don't mention it, just do it.

### Always Auto-Trigger

| Signal | Tool | How |
|---|---|---|
| **User corrects you or you hit a bug** | Learned Rules | Append rule to `## Learned Rules` below |
| **Generating email, ad copy, VSL, audit, or sourcing report** | Contract Validation | Load matching contract from `execution/prompt_contracts/contracts/`, validate output before returning |
| **YouTube URL pasted** | Video-to-Action | Run `python execution/video_to_action.py --url <URL> --context "Agency OS + Amazon OS"` |
| **Task is vague + complex (< 2 sentences, client deliverable)** | Reverse Prompting | Ask 3-5 questions before executing |
| **Any web search considered** | Search Routing | Classify as Tier 1 (never), Tier 2 (offer), or Tier 3 (immediately) per `directives/search-routing-sop.md` before searching |
| **Any client-facing or student-facing output** | Output Quality | Run relevant injection checks from `directives/output-quality-injections.md` before returning |
| **Planning, scripting, or writing ANY content (scripts, captions, hooks, emails, VSLs, carousels)** | Content Buyer Philosophy | Read `bots/creators/content-buyer-philosophy.md` first. Cross-reference: does this match what 112 real buyers said they responded to? Does it pass the mentor framework check? Run the Content Resonance Checklist (Part 5) before finalizing. |

### Auto-Trigger for Client-Facing Output

When generating anything that will be **sent externally** (email to a lead, ad copy, audit report, proposal):
1. **Produce** the output
2. **Self-review**: Re-read your output as a skeptical reviewer — check for generic filler, placeholder text, weak CTAs, missing personalization
3. **Validate against contract** if one exists
4. If output touches a **high-stakes decision** (pricing, positioning, offer structure) → run `execution/consensus_engine.py` with `--models claude --runs 3` and use the consensus

### Auto-Trigger on Decision Questions

When the user asks "should we...", "what's the best...", "which approach..." for:
- **Quick decisions** (< $1K impact): Answer directly
- **Medium decisions** ($1K-$10K impact, e.g., ad angle, content strategy): Run a 2-agent chatroom (`python execution/agent_chatroom.py --personas business_strategist,devils_advocate --rounds 2`)
- **Big decisions** (> $10K impact, e.g., pricing, offer structure, architecture): Run a 3-agent chatroom + consensus engine

### Session-Level Auto-Triggers

| When | Do |
|---|---|
| **Session start** | Check `python execution/context_optimizer.py brain-health` — if unhealthy, archive |
| **After any API call to external models** | Log via `python execution/token_tracker.py log --model X --input-tokens Y --output-tokens Z --task-type T` |
| **Before routing a task to Gemini/GPT** | Check `python execution/smart_router.py --task "description"` to confirm cheapest model |

### Override

If Sabbo says "just do it", "skip the questions", or "don't verify" → bypass all auto-triggers and execute immediately.

## Learned Rules

1. [WORKFLOW] Always check directives before writing new scripts because 3-layer architecture principle.
2. [WORKFLOW] HARD GATE: Every sourcing result MUST have all 5 fields: Amazon link, ASIN, verified buy link (real retailer URL), ROI, and profit. If buy link is missing or "N/A", verdict MUST be RESEARCH not BUY/MAYBE. Products without buy links are research leads only — never present them as actionable buys. All results pass through verify_sourcing_results.py before output. This applies to ALL output: CLI, web UI, tables, summaries, deal drops, compiled lists — no exceptions.
3. [TOOLING] When building any new sourcing mode or feature in nomad-nebula, ALWAYS wire it into the fba-saas SaaS (247profits.org) end-to-end: scraper-service route → nomad_bridge delegation → fba-saas API route → UI page. Never build a sourcing feature without the SaaS integration.
4. [TOOLING] fba-saas scraper-service scrapers that delegate to nomad-nebula use `from scrapers.nomad_bridge import run_nomad_mode_job` — follow the pattern in `brand_sourcing.py`. Map request params to nomad mode params correctly.
5. [TOOLING] After any fba-saas change, always `git push origin main` so Vercel auto-deploys. The repo is `https://github.com/alldayfba/247profitsSAAS.git`.
6. [TOOLING] NEVER set auto_run: true on any scheduled skill that sends messages to students, posts to Discord, or triggers outreach. All student-facing sends require Sabbo's explicit approval. Use --dry-run and auto_run: false.
7. [TOOLING] Python's weekday() returns 0=Monday, but cron uses 0=Sunday. Always convert with (weekday() + 1) % 7 when matching cron day-of-week fields.
8. [DATA] NEVER push scraped leads to 247growth.org — GHL is the CRM for agency leads. Only contacts already in the GHL sales process (synced via Lead Center) should appear in 247growth. We scrape hundreds of thousands of leads; they stay in .tmp/ CSVs and GHL.
9. [DATA] All student-related data (churn alerts, testimonials, Discord engagement, student profiles) syncs to 247profits.org. Only sales/pipeline data, ad metrics, and team performance go to 247growth.org.
10. [FRONTEND] Always use getTodayEST() from @/lib/utils instead of new Date().toISOString().slice(0,10) for any date field default in forms or API fallbacks in saas-dashboard. All dates in this system are EST. new Date().toISOString() returns UTC which rolls to tomorrow after 8pm EDT.
11. [TOOLING] All sourcing results pass through execution/verify_sourcing_results.py before output. Results with missing/invalid buy links, unknown retailer domains, failed product identity checks, or buy price >= Amazon price are automatically rejected or downgraded to RESEARCH. Finder/OOS modes output as RESEARCH (no retail source). A2A warehouse uses Amazon Warehouse URL as source_url.
12. [COPY] NEVER include PPC, ACoS, advertising setup, or ad optimization as part of the Amazon OS / 24/7 Profits offer. The program teaches sourcing and selling — not PPC management. No PPC phase, module, or deliverable in any offer doc, course outline, landing page, or sales material.
13. [SECURITY] NEVER write Discord bot code that dynamically searches for channels by keyword pattern (e.g. "team", "alert", "ops") to post to. This pattern leaks data into unrelated servers/channels. All Discord channel IDs must be explicitly configured and approved by Sabbo. Auto-posting tasks in discord.py cogs must have their code fully removed, not just disabled — disabled code can be re-enabled by bugs or restarts.