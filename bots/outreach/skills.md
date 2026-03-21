# Outreach Bot — Skills
> bots/outreach/skills.md | Version 2.0

---

## Purpose

This file tells you which resources to pull for which task. When you receive an outreach request, match it to the skill category below, then reference every listed SOP and training file before executing.

---

## Owned Claude Code Skills (Slash Commands)

These skills are owned by this agent. When invoked via `/skill-name`, this agent's context and SOPs are the authority.

| Skill | Invocation | What It Does |
|---|---|---|
| Cold Email | `/cold-email` | Generate personalized cold outreach emails for filtered lead CSVs |
| Dream 100 | `/dream100` | Build hyper-personalized GammaDoc outreach packages |
| Outreach Sequence | `/outreach-sequence` | Create and manage multi-touch personalized outreach sequences |
| Follow-Up | `/follow-up` | Nurture existing CRM pipeline conversations with contextual follow-ups |
| Sales Prep | `/sales-prep` | Generate pre-call prospect brief pulling all existing data into one doc |

**Skill files:** `.claude/skills/cold-email.md`, `.claude/skills/dream100.md`, `.claude/skills/outreach-sequence.md`, `.claude/skills/follow-up.md`, `.claude/skills/sales-prep.md`

When any of these skills run, they read the directive first, then execute the script. If a skill fails, the self-annealing protocol fixes the script AND updates the directive.

---

## Skill: Dream 100 (Full Pipeline)

**When to use:** Hyper-personalized outreach for a specific prospect.

**Reference in order:**
1. `directives/dream100-sop.md` — full process
2. `SabboOS/Agency_OS.md` → offer, ICP, proof points
3. `bots/clients/[client].md` → brand voice (if available)
4. Any `[outreach]` tagged files in Allocated SOPs below

**Pipeline:**
```bash
python execution/run_dream100.py \
  --name "Prospect Name" \
  --website "https://their-site.com" \
  --niche "their niche" \
  --offer "what they sell"
```

**Output:** `.tmp/gammadoc_<name>_<ts>.md`

---

## Skill: Cold Email / Outreach Sequences

**When to use:** Writing personalized cold emails for a list of leads.

**Reference in order:**
1. `directives/email-generation-sop.md`
2. Relevant OS file → ICP, offer, tone
3. Any `[outreach]` or `[cold-email]` tagged files below

**Script:** `execution/generate_emails.py --input .tmp/filtered_leads_<ts>.csv`

**Output standard:**
- Subject: specific, curiosity-driven, no clickbait
- Body: one idea per email, reference something specific about the prospect
- CTA: one action, clear, low-friction (not "schedule a call" — "reply with yes")

---

## Skill: Follow-Up Sequence

**When to use:** Building a multi-touch follow-up after initial outreach.

**Reference:** `AGENTS.md` → Dream 100 Follow-Up Sequence section

| Touch | Timing | Type |
|---|---|---|
| 1 | Day 0 | Send GammaDoc / initial value |
| 2 | Open trigger | "Just saw you opened it" |
| 3 | Day 3 | New insight or relevant stat |
| 4 | Day 7 | Similar client result |
| 5 | Day 14 | Quick question about their challenge |
| 6 | Day 21 | Case study |
| 7 | Day 30 | Final touch |

Most sales close at touch 4–7. Write all 7 before sending touch 1.

---

## Skill: Close Rate Recovery (Constraint from CEO)

**When to use:** CEO agent identifies close rate below threshold.

**Reference:**
1. `SabboOS/Agents/CEO.md` → Optimization Recommendations Bank → Close Rate section
2. Any `[sales]` or `[closing]` tagged files below

**Actions (ranked by speed):**
1. Review last 5 lost calls → identify top 3 objection patterns
2. Rewrite closing sequence to address each objection directly
3. Add specific guarantee to the offer
4. Restructure price presentation (anchor, then reveal)
5. Rewrite pre-call email to set frame before they join

Output: draft revised closing sequence for Sabbo's review.

---

## Skill: Show Rate Recovery (Constraint from CEO)

**When to use:** CEO agent identifies show rate below 65%.

**Reference:** `SabboOS/Agents/CEO.md` → Optimization Recommendations Bank → Show Rate section

**Actions:**
1. Add 1-hour reminder text/email
2. Send pre-call video (2–3 min VSL teaser)
3. Test moving calls to highest-converting time slot
4. Shorten gap between booking and call (aim for < 3 days)

---

## Skill: Dream 100 Full Pipeline (TP-009)

**DREAM 100 HYPER-PERSONALIZED OUTREACH:**
1. Research prospect (website, offer, funnel gaps, brand assets) → `research_prospect.py`
2. Generate 7+ custom deliverables (Meta hooks, VSL script, email sequence, landing page headlines, confirmation copy) → `generate_dream100_assets.py`
3. Assemble branded GammaDoc (header, system overview, free deliverables, implementation roadmap, credibility proof) → `assemble_gammadoc.py`
4. Send GammaDoc + personalized context email → request book call only after they engage

Inputs: --name, --website, --niche, --offer, --platform | Master runner: `execution/run_dream100.py`

---

## LLM Routing Rules (TP-014)

- **Haiku:** Lead research/data processing
- **Sonnet:** Email generation, competitor research, standard outreach drafts
- **Opus:** Only for high-stakes copy review if explicitly requested by Sabbo
- **Heartbeat checks:** Always use Gemini Flash, never Claude models
- **Cost awareness:** Monitor against $50–$100 monthly ceiling. Alert at 80%.

---

## Competitive Intelligence & Positioning (TP-020)

- **Competitive Positioning**: Use competitive intelligence from Training Officer analysis to differentiate pitch. Reference specific market gaps we fill versus named competitors.
- **Dynamic Messaging**: Adapt outreach templates based on real-time competitive intel briefings. Personalize value prop to prospect's likely pain points vs. competitor solutions.

---

## Dream 100 Asset Generation (TP-024)

After filtering prospects with `filter_icp.py`, generate paid ad scripts and VSL assets:
- Run `python execution/generate_ad_scripts.py --input .tmp/filtered_leads.csv --platform [meta|youtube]`
- Run `python execution/generate_vsl.py --input .tmp/filtered_leads.csv --single` for one niche at a time
- Ad scripts follow platform-specific structures (Meta: hook→agitation→tease→CTA; YouTube: hook→credentials→problem→solution→CTA)
- VSL follows Jeremy Haynes method: summary→hook→credibility→buying motives→offer with price→objections→qualification→CTA
- Always state price in VSL. Never use value stacks.

---

## VSL & Call Funnel Expertise (TP-032)

Understand Jeremy Haynes' VSL framework — minimal landing pages (headline + VSL video + embedded scheduler) designed to answer buyer questions in exact sequence. Use VSL call funnels for high-intent prospects: cold traffic → VSL page → confirmation page → sales call. Recommend VSL approach when prospect shows buyer signals; emphasize video's role in replicating 1-on-1 sales conversation without back-and-forth. Avoid page clutter; every element must serve the VSL's conversion goal.

---

## Business Audit Integration (TP-044)

Before sending cold outreach emails, use the Business Audit Generator (`execution/generate_business_audit.py` or `/audit` endpoint) to create a personalized audit package for each prospect. Include the Google Drive folder link in your outreach message. The 4-asset package (audit doc, landing page, ad angles, email) serves as social proof and removes friction from the discovery call. Typical workflow: (1) Generate audit (~90s), (2) Share Drive link in outreach, (3) Follow up after 3 days if no reply.

---

## Skill: Prospect Research

**When to use:** Building context on a specific prospect before outreach.

**Script:** `execution/research_prospect.py --name "Name" --website "URL" --niche "niche" --offer "offer"`
**Output:** `.tmp/research_<name>_<ts>.json`

---

## Allocated SOPs

*This section is auto-populated by `execution/allocate_sops.py` when new training files are uploaded.*
*Each entry below is a reference to an ingested document — read it before executing the tagged task type.*

<!-- New SOP references will be appended below this line by allocate_sops.py -->

---

## [$100M Playbook - Closing (1).pdf] — Allocated 2026-02-20
**Domain:** closing
**Summary:** A training playbook by Alex Hormozi on closing techniques and objection handling strategies designed to convert customer "nos" into sales through addressing blame-based resistance.
**Source:** `/Users/sabbojb/$100M Playbook - Closing (1).pdf`
**Usage:** Reference this document when handling [closing] tasks. Read the source file for full content.

---

## [$100M Playbook - Fast Cash.pdf] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A business playbook by Alex Hormozi on rapid cash extraction strategies from existing businesses, covering offer structures, sales sequences, and persuasion frameworks applicable across business models.
**Source:** `/Users/sabbojb/$100M Playbook - Fast Cash.pdf`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [$100M Playbook - Lead Nurture.pdf] — Allocated 2026-02-20
**Domain:** outreach
**Summary:** A playbook by Alex Hormozi on lead nurture strategies designed to increase lead response rates, meeting scheduling, and attendance through targeted outreach and persuasive communication techniques.
**Source:** `/Users/sabbojb/$100M Playbook - Lead Nurture.pdf`
**Usage:** Reference this document when handling [outreach] tasks. Read the source file for full content.

---

## [$100M Playbook - Price Raise.pdf] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A playbook teaching strategies and frameworks for raising prices on existing customers while retaining them, including a structured letter template and objection handling techniques.
**Source:** `/Users/sabbojb/$100M Playbook - Price Raise.pdf`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Agency Yap Doc (1).pdf] — Allocated 2026-02-20
**Domain:** outreach
**Summary:** This document outlines a complete B2B marketing agency system for acquiring local business clients, covering lead scraping via SMS outreach through tools like Appify and GoHighLevel, scheduling appointments, presenting offers, and closing deals.
**Source:** `/Users/sabbojb/Agency Yap Doc (1).pdf`
**Usage:** Reference this document when handling [outreach] tasks. Read the source file for full content.

---

## [B2B Sales Call Framework (2).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A B2B sales call framework that guides sellers through six phases—from initial rapport-building through information gathering, strategy presentation, and closing—designed to identify prospect needs and pitch tailored solutions.
**Source:** `/Users/sabbojb/B2B Sales Call Framework (2).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Closer Script Framework (1).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A structured closer script framework using discovery questions, future pacing, and inaction questions to move prospects toward a buying decision on a sales call.
**Source:** `/Users/sabbojb/Closer Script Framework (1).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [DM SETTING BREAKDOWN.docx] — Allocated 2026-02-20
**Domain:** outreach
**Summary:** A framework and scripted examples for qualifying and setting appointments with prospects via direct message, focusing on uncovering commitment, urgency, and budget before transitioning to a sales call.
**Source:** `/Users/sabbojb/DM SETTING BREAKDOWN.docx`
**Usage:** Reference this document when handling [outreach] tasks. Read the source file for full content.

---

## [EOD_EOC Closer + Setter Report Questions (3).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** Daily end-of-day reporting templates for sales closers and setters that track pipeline metrics, call outcomes, and performance feedback to monitor sales team activity and results.
**Source:** `/Users/sabbojb/EOD_EOC Closer + Setter Report Questions (3).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Niksetting profile funnel video (2).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A training video script explaining the three-part funnel mechanism (top-of-funnel traffic, middle-funnel conversion, proof of concept) and how to optimize messaging and ICP targeting to improve sales team performance and close rates.
**Source:** `/Users/sabbojb/Niksetting profile funnel video (2).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Post Call Show Rate Booking Process (1).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A post-booking process workflow that standardizes confirmation touchpoints, engagement checks, and no-show handling to ensure appointment attendance and client readiness for consultation calls.
**Source:** `/Users/sabbojb/Post Call Show Rate Booking Process (1).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Pre-call Nurture Email + SMS  (1).docx] — Allocated 2026-02-20
**Domain:** outreach
**Summary:** A collection of email and SMS templates designed to nurture leads before sales calls, confirm appointments, handle no-shows, and disqualify prospects.
**Source:** `/Users/sabbojb/Pre-call Nurture Email + SMS  (1).docx`
**Usage:** Reference this document when handling [outreach] tasks. Read the source file for full content.

---

## [Sales Calls 2 (2).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A recorded sales call where a mentor (Rocky Yadav) qualifies a prospect interested in Amazon FBA mentorship, discussing their sourcing challenges, current employment situation, and goals to scale Amazon as a primary income source.
**Source:** `/Users/sabbojb/Sales Calls 2 (2).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Sales Manager Guide (1).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A management guide for sales leaders covering daily routines, one-on-one coaching, and group meeting frameworks to develop rep performance and drive sales results.
**Source:** `/Users/sabbojb/Sales Manager Guide (1).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Sales Rep Interview Doc Breakdown.docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A comprehensive interview framework for sales hiring that covers pre-call preparation, on-call questioning structure, role-specific details, and next-steps communication to evaluate candidate fit and close them into the hiring pipeline.
**Source:** `/Users/sabbojb/Sales Rep Interview Doc Breakdown.docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Sales Rep Onboarding + SOP Templates (1).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** Comprehensive onboarding and standard operating procedures for sales team members (setters and closers) covering account setup, CRM usage, lead management, booking processes, and role-specific frameworks.
**Source:** `/Users/sabbojb/Sales Rep Onboarding + SOP Templates (1).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Sales calls (3).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A recorded sales call between a founder and a prospect discussing FBA business progress, product sourcing methods (OA/RA), and sales results to determine how coaching/mentorship can help scale the business.
**Source:** `/Users/sabbojb/Sales calls (3).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Setting Scripts  (1).docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** Call scripts for qualifying leads and setting sales calls, covering discovery questions, objection handling, and booking procedures for a business coaching offer.
**Source:** `/Users/sabbojb/Setting Scripts  (1).docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [Tie Downs (1).docx] — Allocated 2026-02-20
**Domain:** closing
**Summary:** A sales framework document detailing tie-down techniques (financial qualification, partner confirmation, and pre-call video commitment) used to improve show rates and prepare prospects for closing calls.
**Source:** `/Users/sabbojb/Tie Downs (1).docx`
**Usage:** Reference this document when handling [closing] tasks. Read the source file for full content.

---

## [Upsell Framework Setting_Closing.docx] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A framework for conducting setting and closing calls that uses problem awareness questioning to understand customer needs and transition into upselling advanced program offerings.
**Source:** `/Users/sabbojb/Upsell Framework Setting_Closing.docx`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [document_pdf.pdf] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A buyer persona and ICP analysis document for a $10K Amazon FBA mentorship program that segments ideal customers by psychological levers, purchase readiness, and objection patterns to inform sales and coaching delivery strategy.
**Source:** `/Users/sabbojb/document_pdf.pdf`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.

---

## [$100M Playbook - Pricing.pdf] — Allocated 2026-02-20
**Domain:** sales
**Summary:** A pricing strategy guide that teaches business owners how to increase profit through three core levers: customer acquisition, purchase frequency, and price optimization, along with foundational pricing models and rules.
**Source:** `/Users/sabbojb/$100M Playbook - Pricing.pdf`
**Usage:** Reference this document when handling [sales] tasks. Read the source file for full content.


---

## Agent-to-Agent Communication Protocol Integration (TP-2026-03-16-001)

**Agent Communication Protocol Integration:**


---

## Add Prompt Contract Validation to Outreach Email Generation (TP-2026-03-16-005)

**Prompt Contract Integration:** Before delivering any cold email, validate against `execution/prompt_contracts/contracts/lead_gen_email.yaml`. Run validation via `python execution/prompt_contracts/validate_contract.py`. If output fails validation, auto-revise (max 2 iterations) or flag for user review. Ensure all required sections present, no placeholder text, and tone/word constraints met.


---

## Add Approval Gate Protocol to Outreach Agent Skills (TP-2026-03-16-007)

## Approval Gate Protocol


---

## Auto-Research Pipeline for Cold Outreach Optimization (TP-2026-03-16-008)

## Auto-Research for Outreach


---

## Add Outreach Sequencer SOP execution capability to outreach agent (TP-2026-03-16-010)

OUTREACH SEQUENCER SOP: Execute via `python execution/outreach_sequencer.py`. Key commands: (1) create-sequence --leads CSV --template [dream100|cold_email|warm_followup], (2) next-touches --due [today|DATE], (3) mark-sent/mark-replied/mark-booked for pipeline tracking, (4) stats for reporting, (5) export for analysis. HARD RULE: All copy must reference specific prospect data—no mass blasts. Dream 100 uses 7-touch 30-day sequence; cold_email uses 4-touch 14-day. Store sequences in .tmp/outreach/sequences.db. Always personalize using prospect CSV data + sender context.


---

## Add Agent Routing Table as Skill Ownership Reference (TP-2026-03-16-011)

## Skill Ownership (per agent-routing-table.md)


---

## Implement Learned Rules SOP for outreach agent error correction (TP-2026-03-16-017)

## Learned Rules Execution


---

## Student At-Risk Outreach Triggers & Dream 100 Intervention (TP-2026-03-16-019)

**At-Risk Student Outreach Protocol:**


---

## Add Brand Voice Extraction Pre-Step to Outreach Workflow (TP-2026-03-16-021)

**Brand Voice Extraction (Pre-Outreach Step):**


---

## Creator Intelligence Scraping for Dream 100 List Building (TP-2026-03-16-022)

**Creator Intelligence Scraping** — Use `creator-intel-sop.md` to reverse-engineer Dream 100 prospects' frameworks from YouTube + Instagram. Run `scrape_creator_intel.py` → `build_creator_brain.py` to generate brain docs capturing their positioning, offer strategies, and terminology. Reference these docs when crafting cold outreach angles and personalizing Dream 100 pitch sequences.


---

## Dream 100 at Scale: 4-Agent Concurrent Pipeline SOP (TP-2026-03-16-025)

### Dream 100 at Scale Pipeline
 - VSL Script Agent (using `jeremy-haynes-vsl-sop.md`)
 - Email Sequence Agent (3-touch flow per `email-generation-sop.md`)
 - Ad Creative Agent (3 angles: pain, curiosity, authority)
 - Landing Page Agent (headline, proof, CTA matched to brand voice)


---

## Dream 100 + Cold Outreach Strategy from Client Research Phase (TP-2026-03-16-026)

**OUTREACH AGENT RESPONSIBILITIES (Post-Phase 1 Research):**


---

## Implement Verification Loops for Cold Outreach & Dream 100 Campaigns (TP-2026-03-16-028)

**Verification Loop Protocol for Outreach:**


---

## Brand Discovery & Contact Research Tool for Cold Outreach (TP-2026-03-16-033)

**Brand Discovery Tool**: Use `python execution/brand_outreach.py discover --brand "[target_brand]"` to extract brand contacts, websites, and contact info. Chain with email generation via `--email --template cold_intro` to create personalized outreach. Track replies with `--reply` and manage pipeline status with `--status`. Supports batch discovery from `--brands-file` for scaling Dream 100 campaigns.


---

## Add smart_router tool for cost-optimized outreach task routing (TP-2026-03-16-036)

**Smart Router Integration**: Use `route_task()` to classify outreach work before execution. Route scraping/parsing/lead validation to Tier 1 (Haiku/Flash). Route email drafts and content to Tier 2 (Sonnet/GPT-4.1-mini). Reserve Tier 3 (Opus) for high-stakes Dream 100 personalization and complex multi-prospect research.


---

## Self-Healing Error Detection for Outreach Scripts (TP-2026-03-16-042)

**Error Self-Healing Integration**: Use `python execution/self_healing_engine.py --wrap "python execution/[outreach_script].py [args]"` to wrap any outreach script execution. Automatically captures stack traces, proposes fixes for common errors (missing APIs, path issues, data format problems), and escalates complex failures to Training Officer review. Check `.tmp/training-officer/proposals/` for generated fix suggestions.


---

## Add Approval Gate Integration for High-Risk Outreach Campaigns (TP-2026-03-16-045)

Before executing large outreach campaigns:


---

## Multi-Channel Outreach Orchestration & Rate-Limited Sequencing (TP-2026-03-16-054)

**Multi-Channel Outreach Execution**: Can orchestrate personalized cold outreach across Instagram DMs, Twitter DMs, email, and contact forms using the multichannel_outreach tool. Supports:


---

## Memory Store Integration for Dream 100 & Cold Outreach Tracking (TP-2026-03-16-060)

## Memory Store Integration


---

## Dream 100 Hyper-Personalized Outreach SOP + Phase-Gated Execution (TP-2026-03-16-065)

**Dream 100 Outreach Protocol:**


---

## Creator Brain Synthesis: Extract Dream 100 & Cold Outreach Angles (TP-2026-03-16-066)

CREATOR BRAIN INTEGRATION:


---

## Inbox/Outbox Message Protocol for CEO Task Delegation (TP-2026-03-16-067)

**Agent-to-Agent Communication:**


---

## API Cost Management: Enforce Haiku for routine tasks, Sonnet for email generation (TP-2026-03-16-069)

## LLM Routing (Cost Management)


---

## Training Officer SOP Integration for Outreach Agent Scanning (TP-2026-03-16-071)

## Training & Upgrades


---

## Prompt Contracts SOP - Add Contract Validation to Outreach Workflows (TP-2026-03-16-079)

PROMPT CONTRACTS: Before finalizing any cold email, validate output against `execution/prompt_contracts/contracts/lead_gen_email.yaml`. Run: `python execution/prompt_contracts/validate_contract.py --contract lead_gen_email.yaml --output [email_file]`. Task is complete only when validation returns PASS. If validation fails, auto-revise per contract constraints (max 2 attempts) or flag the user with specific violations.


---

## Dream 100 Asset Stack Generation — Ad & VSL Scripts (TP-2026-03-16-082)

### Dream 100 Asset Generation


---

## VSL Call Funnel Strategy for High-Intent Sales Calls (TP-2026-03-16-086)

VSL Call Funnel Strategy: A VSL (Video Sales Letter) funnel bridges cold traffic to qualified sales calls. Structure: Cold outreach → VSL page (headline + embedded video + application) → Confirmation sequence → Sales call. Key outreach principle: use Dream 100 lists and cold campaigns to drive traffic to VSL pages rather than direct-to-call pitches. VSL pre-qualifies buyers and answers objections async, so inbound calls are higher-intent. Customize VSL messaging to buyer type (problem-aware, solution-aware, skeptical) to maximize relevance and application submissions.


---

## Approval Gate Integration: Gate outreach sends before execution (TP-2026-03-16-090)

## Approval Gate Requirement


---

## Auto-Research Pipeline for Cold Email & Outreach Optimization (TP-2026-03-16-092)

**Auto-Research Capability**: Run autonomous cold email optimization loops using the Auto Research SOP pattern. For each outreach campaign, establish baseline metrics (reply rate, meeting booked %), generate hypotheses about subject line/hook improvements, deploy A/B variants, harvest results after 24-48h, and update baseline with winner. Log learnings to resources.md to compound improvements. Requires: (1) objective metric (reply %), (2) changeable input (email copy/subject), (3) email platform API access (Instantly, Apollo, etc). Orchestrator runs every 24h to cycle new experiments.


---

## Agent Communication Protocol Integration for Task Delegation (TP-2026-03-16-093)

# Agent Communication Integration


---

## Cold Outreach Cadence & Pipeline Tracking Integration (TP-2026-03-16-094)

**Dashboard Integration for Outreach Sequencing:**


---

## Outreach Sequencer SOP Integration & Pipeline Management (TP-2026-03-16-100)

OUTREACH SEQUENCER CAPABILITY:


---

## Add Dream 100 Campaign Execution & Tracking Skill to Outreach (TP-2026-03-16-1002)

## Skill: Dream 100 Campaign Execution


---

## Agent Routing Table Reference Integration (TP-2026-03-16-102)

OWNED DIRECTIVES: dream100-sop.md, email-generation-sop.md | OWNED SCRIPTS: generate_emails.py, research_prospect.py, generate_dream100_assets.py, assemble_gammadoc.py, run_dream100.py | SECONDARY ROLE: business-audit-sop.md (delivery), ads-competitor-research-sop.md (positioning input) | CROSS-AGENT DEPENDENCIES: CEO (delegation/approval), ads-copy (positioning), content (brand voice) | DO NOT OWN: VSL scripts, ad creative, landing pages, sourcing, lead generation pipelines


---

## Add Dream 100 & Cold Outreach Skills Reference to Outreach Agent (TP-2026-03-16-1021)

Add to outreach agent skills documentation:


---

## Add Sales Memory Tracking to Outreach Agent Context (TP-2026-03-16-1024)

**Memory Reference:** Before drafting outreach sequences, review /bots/sales-manager/memory.md for:


---

## Add Follow-Up Sequencing Skill to Outreach Agent (TP-2026-03-16-1025)

| Follow-Up Sequencing | `/follow-up` | `directives/outreach-sequencer-sop.md` | `execution/outreach_sequencer.py` |


---

## Hormozi's Wealth Distribution & Pareto Targeting for Dream 100 (TP-2026-03-16-1026)

HORMOZI'S PROSPECT PRIORITIZATION FRAMEWORK:


---

## Jeremy Haynes Buyer Psychology & Sales Strategy Context (TP-2026-03-16-1027)

## Jeremy Haynes Sales Psychology & Outreach Philosophy


---

## Operator-Coach Credibility Framework for Cold Outreach & Dream 100 (TP-2026-03-16-1028)

**Outreach Trust Anchors (Use in Cold DMs, Dream 100, Sales Calls):**


---

## Dashboard Client Integration for Cold Outreach Research & Targeting (TP-2026-03-16-103)

Tool: Dashboard Contact Lookup


---

## Johnny Mau Pre-Frame Psychology for High-Ticket Cold Outreach (TP-2026-03-16-1030)

## Johnny Mau Pre-Frame Psychology System
- Identity positioning: Lead with outcome proof, not credentials
- Objection pre-emption: Address common rejections in outreach copy
- Certainty signaling: Use specific numbers ($X profit, X% close rate) to establish authority


---

## Ben Bader's Shovel Seller Positioning for High-Value Client Targeting (TP-2026-03-16-1031)

SHOVEL SELLER POSITIONING (Ben Bader Model):


---

## Trust-Based Positioning for Cold Outreach & Dream 100 Sequencing (TP-2026-03-16-1033)

TRUST-FIRST OUTREACH PRINCIPLE:


---

## Dream 100 + Cold Outreach Framework from Creator Playbooks (TP-2026-03-16-1034)

### Creator-Attributed Cold Outreach + Dream 100 Framework


---

## Revenue-Share Partnership Positioning for Dream 100 & Cold Outreach (TP-2026-03-16-1035)

**Revenue-Share Partnership Model (NOT Retainer):**


---

## Fulfillment-First Positioning: Reframe Cold Outreach Around Proof & Results (TP-2026-03-16-1036)

**Fulfillment-First Outreach Framework:**


---

## Add Category of One & 3S Offer Framework to Dream 100 Targeting (TP-2026-03-16-1037)

## Category of One for Dream 100 Selection


---

## Dream 100 + High-Ticket Agency Positioning Framework (TP-2026-03-16-1040)

AGENCY OUTREACH POSITIONING (High-Ticket $15K-$25K/mo):


---

## Add AI-Tell Blacklist & Copy Quality Standards to Outreach Context (TP-2026-03-16-1046)

## Copy Quality Enforcement


---

## Add Pre-Launch Activation SOP to Outreach Agent Context (TP-2026-03-16-1047)

## Pre-Activation Constraints


---

## Add Memory-Driven Learning Loop to Outreach Agent (TP-2026-03-16-1048)

On every outreach task, consult memory.md first. Reference Approved Work Log for successful patterns (hooks, tone, CTAs). Check Rejected Work Log to avoid past mistakes. Review Prospect Insights to match messaging to ICP segment. Log all completed work—approvals to Approved Log, rejections to Rejected Log. Track performance metrics in Outreach Performance Log. Build Objection Library from sales call outcomes.


---

## Add Sales Prep Output Standard & CRM Integration Checkpoint (TP-2026-03-16-1049)

**Output standard:**


---

## Add Sequencer Command Reference & Pipeline Tracking SOP (TP-2026-03-16-1050)

## Outreach Sequencer Workflow


---

## Add Setter Outreach Script & Post-Booking Follow-up SOP (TP-2026-03-16-1051)

POST-BOOKING SETTER OUTREACH SOP:


---

## Add Post-Booking Video Outreach SOP to Increase Show Rates (TP-2026-03-16-1054)

POST-BOOKING VIDEO OUTREACH SEQUENCE:


---

## Add Closing Call Discovery Framework to Outreach SOP (TP-2026-03-16-1055)

**Closing Call Pre-Qualification Checklist:**


---

## Sales Call Framework: Discovery-First Model with Objection Handling (TP-2026-03-16-1056)

**Sales Call SOP (Proven 2026-03-08):**


---

## Add AI-tell word ban list to outreach identity (TP-2026-03-16-1057)

BANNED AI-TELL WORDS (use natural alternatives):


---

## Add Cold Email Optimizer & LinkedIn Scraper to Outreach Pipeline (TP-2026-03-16-1058)

INCOMING TOOLS (Under Development):


---

## Price Reveal Protocol — Never Share Before Discovery Call (TP-2026-03-16-1061)

**Price Reveal Protocol (PERMANENT):**


---

## Add /auto-outreach Orchestration Skill to Outreach Agent (TP-2026-03-16-1063)

- **Skill: /auto-outreach** — End-to-end autonomous outreach orchestration. Chains: prospect scraping → filter by Dream 100 + ICP → generate personalized cold emails via /cold-email → execute /follow-up sequences → log results to CRM. Loops continuously, learns from reply rates. Owner: outreach. Depends: /cold-email, /follow-up, /sales-prep, /deal-drop.


---

## Multi-Channel Outreach Execution + Dream 100 at Scale Pipeline (TP-2026-03-16-1068)

**New Tools Available:**


---

## Dream 100 Positioning Framework: AI-Powered Sourcing as Access Differentiator (TP-2026-03-16-1071)

## Positioning Framework for Outreach


---

## EOC Form Validation & Silent Error Handling for Sales Outreach (TP-2026-03-16-1073)

## EOC Form Submission Troubleshooting


---

## Segment Prospects by Purchase Intent: Tool-Only vs. Coaching Buyers (TP-2026-03-16-1074)

PROSPECT SEGMENTATION RULE:


---

## Add Creator Intelligence Framework to Dream 100 Targeting (TP-2026-03-16-1076)

**Dream 100 Creator Intelligence Layer:**


---

## AI + Amazon Positioning: Dream 100 & Cold Outreach Playbook (TP-2026-03-16-1077)

DREAM 100 CRITERIA — AI + Amazon First-Mover Play:


---

## Price Gating Protocol: Never Reveal Cost Before Discovery Call (TP-2026-03-16-1078)

**Price Gating Protocol (PERMANENT):**


---

## Dream 100 + Cold Outreach: AI-Powered Sourcing Differentiation Framework (TP-2026-03-16-1083)

### AI-Powered Sourcing Differentiation (Outreach Positioning)


---

## Tool-Only vs. Mentorship Sales Segmentation Strategy (TP-2026-03-16-1084)

**Tool-Only vs. Mentorship Segmentation:**


---

## Sales Call Framework: Discovery-First, Price-Last Structure (TP-2026-03-16-1086)

SALES CALL PLAYBOOK (from Mike Walker close):


---

## Sales Call Framework: Discovery→Dollarize→Demo→Close Structure (TP-2026-03-16-1087)

**Sales Call SOP (35-40 min target):**


---

## Add Business Audit Package Generation to Outreach Arsenal (TP-2026-03-16-109)

**Business Audit Generator Tool**: Generate personalized 4-asset audit packages (1-page audit, landing page, 3 ad angles, outreach email) for any B2B prospect in <90 seconds via http://localhost:5050/audit or CLI. Use before cold outreach to warm leads, demonstrate operator-level thinking, and share via Google Drive link. Each audit costs ~$0.08-0.15 and includes marketing gap analysis, personalized messaging angles, and ready-to-send email copy.


---

## Lead CSV Integration & Outreach Tool Sequencing (TP-2026-03-16-115)

## Lead CSV Import & Sequencing (TP-015)


---

## Multi-touch sequence management and execution tracking (TP-2026-03-16-118)

**Multi-touch Sequence Management**: Use `outreach_sequencer.py` to create templated sequences (dream100, cold_email, warm_intro) with scheduled touchpoints. Commands: `create-sequence` (load leads + template), `next-touches --due today` (get due actions), `mark-sent/replied/booked` (track progress), `stats` (conversion metrics). Supports email, LinkedIn DM, follow-ups, and breakup emails. Export sequences as JSON for reporting.


---

## SOP Allocation Process for Outreach Training Materials (TP-2026-03-16-119)

## SOP Allocation Workflow


---

## Implement Learned Rules SOP for Outreach Agent (TP-2026-03-16-124)

## Learned Rules


---

## Student At-Risk Outreach Triggers for Coaching Cohorts (TP-2026-03-16-128)

## At-Risk Student Outreach Trigger


---

## Add Brand Voice Extraction to Pre-Outreach Workflow (TP-2026-03-16-131)

**Brand Voice Pre-Flight**: Before generating personalized outreach, cold emails, or Dream 100 assets, check if a brand voice profile exists in `.tmp/brand-voices/{prospect-slug}.md`. If missing, request extraction via `extract_brand_voice.py` with prospect website + social handles. Include the extracted voice profile in content prompts to ensure all outputs (subject lines, email opens, sales hooks) match their communication style, tone, and language patterns.


---

## Creator Intelligence Scraping for Dream 100 Research & Positioning (TP-2026-03-16-133)

**Creator Intelligence Scraping**: Use creator-intel-sop.md to reverse-engineer target creators before outreach. Run `scrape_creator_intel.py` + `build_creator_brain.py` to generate brain docs for Dream 100 targets, cold outreach prospects, or positioning research. Output: `bots/creators/{name}-brain.md` with frameworks, terminology, strategies, and examples for use in personalized pitches and positioning arguments.


---

## Add verification_loop tool for cold email validation before send (TP-2026-03-16-138)

**Verification Loop Tool**: Use `run_verification_loop(task, producer_model, reviewer_model, contract_path)` to auto-review cold emails, sales sequences, and Dream 100 pitches. Pass contract YAML for validation rules. Producer generates → Reviewer checks → Max 3 revision cycles. Best for: cold outreach quality assurance, sales script validation, lead gen email polishing.


---

## Dream 100 + Cold Outreach SOP from Client Onboarding Pipeline (TP-2026-03-16-141)

## Outreach Execution (Phase 2 Downstream)


---

## Email Generation SOP — Personalized Cold Outreach at Scale (TP-2026-03-16-143)

## Email Generation Workflow


---

## Add Dream 100 Benchmark Testing to Outreach Agent Quality Checks (TP-2026-03-16-144)

Quality Benchmarks (via agent_benchmark.py):


---

## Student Onboarding Trigger Recognition for Dream 100 Follow-ups (TP-2026-03-16-154)

When you see 'onboard this student' or student onboarding documents generated, note the student's tier (A/B/C) and motivation type (income_replacement/scaling/asset_building). Use this context to suggest: (1) Dream 100 list seeding with Amazon influencers/mentors matching their tier, (2) Pre-kickoff outreach warming sequences, (3) Case study outreach leveraging their specific goal. Flag tier C students for premium partner outreach.


---

## Voice Memo Generation Tool for Personalized Cold Outreach Follow-ups (TP-2026-03-16-159)

**Voice Memo Generation**: Generate personalized audio follow-ups using Eleven Labs voice cloning. Clone your voice from audio samples, then batch-generate memos from lead lists with custom templates. Supports CLI usage (generate, clone, batch operations) or programmatic integration. Outputs MP3 files for direct insertion into email sequences or ManyChat flows. Configuration: ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env.


---

## Brand Contact Discovery & Personalized Cold Outreach Automation (TP-2026-03-16-160)

**Brand Discovery & Cold Outreach Tool**: Discover brand contacts via web scraping and public records. Generate personalized cold emails using dynamic templates. Track outreach status (discovered→contacted→replied→approved). Manage followups by date. Export pipeline metrics. Supports bulk discovery from brand lists, web results, or single-brand deep research.


---

## Quality Drift Detection for Outreach Email Performance (TP-2026-03-16-164)

After each Dream 100 or cold outreach email campaign, log quality scores using: `python execution/agent_quality_tracker.py --score outreach --output "[email_type]" --rating [1-10] --notes "[specific_feedback]"`


---

## Dream 100 Outreach SOP: Hyper-Personalized Prospect Assets & GammaDoc Pipeline (TP-2026-03-16-166)

DREAM 100 OUTREACH PIPELINE:


---

## Dream 100 Asset Generation Tool Integration (TP-2026-03-16-167)

TOOL: generate_dream100_assets.py


---

## Agent-to-Agent Communication Protocol Integration for Outreach (TP-2026-03-16-168)

**Agent Communication Protocol Integration:**


---

## API Cost Management: Enforce Tier-2 Sonnet for Outreach Tasks (TP-2026-03-16-171)

**API Cost Routing (Outreach Agent)**


---

## Training Officer SOP Integration for Outreach Agent (TP-2026-03-16-174)

## Training Officer Integration


---

## Add smart_router task classification to outreach workflows (TP-2026-03-16-175)

**Tool: Smart Router Integration**


---

## Add Cold Email Validation & Personalization Rules to Outreach Agent (TP-2026-03-16-184)

COLD EMAIL VALIDATION RULES:


---

## Implement Prompt Contracts for Outreach Deliverables (TP-2026-03-16-185)

## Prompt Contracts


---

## VSL Call Funnel Integration for High-Intent Sales Sequences (TP-2026-03-16-196)

VSL Call Funnel Structure: Cold traffic → VSL page (headline + VSL + embedded scheduler) → Confirmation page → Sales call → Close. Your outreach should prime targets for the VSL by: (1) Creating curiosity/relevance in initial cold message, (2) Driving to VSL page rather than booking call directly, (3) Using confirmation page sequence to increase call show-up, (4) Timing follow-ups post-VSL before call window closes. Jeremy Haynes principle: VSL replicates real sales conversation without counterparty feedback—your outreach sequences should mirror this by progressively answering buyer questions before the live call.


---

## Self-Healing Engine Integration for Outreach Script Error Recovery (TP-2026-03-16-197)

## Self-Healing Error Integration


---

## Add Claude Sonnet 4.6 email generation to outreach playbook (TP-2026-03-16-200)

**Cold Email Generation Tool:**


---

## Memory Migration Tool Context for Outreach Prospect Data (TP-2026-03-16-202)

You have access to a memory migration system (memory_migrate.py) that parses outreach session snapshots, prospect interactions, and campaign decisions into a searchable SQLite database. Use MemoryStore queries to retrieve: past cold outreach sequences, Dream 100 prospect engagement notes, decision logs about outreach strategy, and campaign performance learnings. This allows you to reference successful patterns from prior outreach work.


---

## Add Approval Gate Protocol to Outreach Agent (TP-2026-03-16-206)

## Approval Gate Protocol


---

## Approval Gate Integration for High-Risk Outreach Actions (TP-2026-03-16-211)

APPROVAL GATE INTEGRATION:


---

## Cold Outreach Sequencing & Pipeline Tracking from Sales Manager Data (TP-2026-03-16-213)

**Data Integration:** Access 247growth.org dashboard via `execution/dashboard_client.py` to check prospect pipeline status before cold outreach campaigns. Run `python execution/dashboard_client.py funnel` to identify warm inbound leads and avoid redundant cold touches. Use `execution/research_prospect.py` to pull application data and prospect context before Dream 100 or cold email sequences. Sync outreach cadence with Sales Manager's pre-call prep and EOD reporting to ensure warm handoffs to closers.


---

## Outreach Sequencer SOP: Multi-touch pipeline management with personalized sequences (TP-2026-03-16-221)

**Outreach Sequencer Commands:**


---

## Agent Routing Table: Formalize Outreach Skill Ownership (TP-2026-03-16-224)

## Skill Ownership (from Agent Routing Table v1.0)


---

## Dream 100 Prospect Intelligence Tool Integration (TP-2026-03-16-226)

**Dream 100 Prospect Research Tool**: Execute `research_prospect.py --name [prospect] --website [url] --niche [niche] --offer [offer_desc]` to automatically extract: current offer/CTA, funnel type (VSL/webinar/application/direct), brand colors & logo, social proof signals, marketing gaps, and key copy. Output saved as JSON. Use before drafting Dream 100 cold outreach sequences to identify personalization angles and positioning gaps.


---

## Add Business Audit as Pre-Outreach Warmup Tool (TP-2026-03-16-239)

**Business Audit Generator** — Pre-outreach warming tool. Use at `http://localhost:5050/audit` or CLI to generate 4-asset packages (1-page audit, landing page, 3 ad angles, personalized email) for B2B prospects in 60–90 seconds (~$0.08–0.15 cost). Outputs shared Google Drive folder. Deploy BEFORE cold email blasts to warm leads and demonstrate deep research. CLI: `python execution/generate_business_audit.py --name "[Business]" --website "[URL]" --category "[Industry]" --address "[Location]"` — include audit link in first cold outreach for 2-3x better response rates.


---

## Lead Generation SOP Integration & CSV Outreach Workflows (TP-2026-03-16-246)

## Lead Generation & CSV Intake


---

## Multi-channel outreach orchestration with rate limiting and batch sends (TP-2026-03-16-247)

**Multi-channel Outreach Tool:**


---

## SOP Allocation Workflow for Outreach Training Materials (TP-2026-03-16-250)

## SOP: Training Material Allocation


---

## Implement Learned Rules SOP for outreach agent (TP-2026-03-16-258)

## Learned Rules


---

## Brand Voice Extraction Pre-Outreach: Match prospect tone automatically (TP-2026-03-16-269)

**Brand Voice Extraction (Pre-Outreach)**


---

## Creator Intelligence Scraping for Dream 100 Research (TP-2026-03-16-271)

**Creator Intelligence Tool:** Use `scrape_creator_intel.py` + `build_creator_brain.py` to reverse-engineer any Dream 100 prospect's content (YouTube/Instagram) into a comprehensive brain doc. Input: creator slug, channel URL, focus areas. Output: `bots/creators/{name}-brain.md`. Use before cold outreach to: extract their positioning language, identify their core frameworks, find specific examples to reference, spot messaging gaps where your offer fits. Typical runtime: 8-10 min for 50 YouTube videos + 30 reels.


---

## Memory Store Integration for Dream 100 & Outreach Campaign Tracking (TP-2026-03-16-275)

MEMORY_STORE_INTEGRATION:


---

## AutomationBuilder — Add Outreach Workflow Automation Patterns (TP-2026-03-16-276)

### Automation-Ready Outreach Tasks


---

## Dream 100 + Cold Outreach Integration from Client Onboarding Research (TP-2026-03-16-282)

**Outreach Research Integration (from Client Onboarding):**


---

## Add Account Diagnostics Context for Outreach Handoff (TP-2026-03-16-283)

**HANDOFF SIGNALS TO OUTREACH AGENT:**


---

## Creator Intelligence Synthesis for Dream 100 List Building (TP-2026-03-16-286)

Creator Brain Synthesis: Use build_creator_brain.py to extract positioning frameworks, offer architecture, funnel strategies, and messaging patterns from YouTube/Instagram creator transcripts. Output becomes a structured reference for crafting Dream 100 cold outreach by identifying: (1) their core positioning pillars, (2) psychological triggers they use, (3) offer stacking patterns, (4) exact language/terminology they use with their audience. Maps directly to personalization angles for sales sequences.


---

## Email Generation SOP: Personalized Cold Outreach via Claude (TP-2026-03-16-287)

## Email Generation Workflow


---

## Auto-SOP Classification & Skills Routing System (TP-2026-03-16-292)

**Auto-SOP Integration:** Files uploaded to /memory/uploads are auto-classified by domain (outreach, sales, closing). Outreach-tagged SOPs are automatically appended to skills.md via allocate_sops.py. Processed files moved to /processed with receipt log. Supports .md, .txt, .pdf, .docx formats.


---

## Implement Verification Loops for Cold Outreach Deliverables (TP-2026-03-16-293)

## Verification Loop Protocol


---

## Dream 100 Hyper-Personalized Outreach SOP with Phase Gates (TP-2026-03-16-294)

DREAM 100 OUTREACH PIPELINE:


---

## Enable Outreach Agent to Receive & Execute CEO-Delegated Tasks (TP-2026-03-16-298)

**Agent-to-Agent Task Execution:**


---

## Dream 100 + Competitive Intel Framework for AllDayFBA Outreach (TP-2026-03-16-300)

COMPETITIVE POSITIONING FOR DREAM 100 OUTREACH:


---

## LLM routing rules for outreach tasks (Haiku→Sonnet→Opus tiers) (TP-2026-03-16-302)

**LLM Routing for Outreach:**


---

## Mechanism Positioning in Dream 100 & Cold Outreach Messaging (TP-2026-03-16-304)

MECHANISM POSITIONING FOR OUTREACH:


---

## Add DM Outreach Framework & CRM Tracking SOP to Outreach Agent (TP-2026-03-16-316)

## DM Outreach SOP (Warm Leads)


---

## Add Prompt Contract Validation to Outreach Workflows (TP-2026-03-16-319)

When generating cold emails, follow the contract at `execution/prompt_contracts/contracts/lead_gen_email.yaml`. Before returning output: (1) Verify all required sections are present, (2) Check no placeholder text remains, (3) Validate word count and tone constraints. If validation fails, auto-revise up to 2 times before flagging the user. Reference this contract in every email generation task.


---

## Sales Playbook Integration: Close Rates, Scripts & Dream 100 Strategy (TP-2026-03-16-320)

CLOSE RATE TARGETS & MESSAGING:


---

## Brand Discovery & Contact Research Tool for Cold Outreach Campaigns (TP-2026-03-16-321)

**Brand Outreach Tool** — Automates direct-to-brand sourcing campaigns: discover brand contact info via web scraping, generate templated cold intro emails personalized by brand/category, send/track replies, update prospect status (discovered→contacted→replied→approved), manage followups by days-since-contact, and export pipeline CSV. CLI: `python execution/brand_outreach.py discover --brand "Anker"` | `email --brand-id 5 --template cold_intro` | `send ...` | `reply ...` | `status --brand-id 5 --set approved` | `followups --days 7` | `pipeline` | `list --status contacted` | `export --output brands.csv`


---

## Dream 100 Asset Stack Generation for Cold Outreach Sequences (TP-2026-03-16-324)

## Dream 100 Asset Stack Generation


---

## EOD Sales Tracking Integration for Outreach Performance Measurement (TP-2026-03-16-325)

## Sales Data Integration


---

## Dream 100 Asset Generation Tool Integration for Outreach (TP-2026-03-16-331)

TOOL: generate_dream100_assets.py


---

## VSL Call Funnel Integration for Cold Outreach & Sales Calls (TP-2026-03-16-333)

VSL Call Funnel Context: A VSL (Video Sales Letter) funnel is a sales infrastructure consisting of: cold traffic → VSL page (headline + video + embedded application) → confirmation page → sales call → close. When planning outreach, Dream 100 sequences, or sales call campaigns, reference that the VSL pre-qualifies prospects by answering their core objections in sequence, reducing friction on the sales call. The outreach agent should use this model when advising on call scheduling, prospect positioning, and multi-touch Dream 100 sequences that feed into VSL-based offers.


---

## Add smart_router task routing to outreach workflows (TP-2026-03-16-339)

**Tool: Smart Router Integration**


---

## Add Approval Gate SOP to Outreach Agent Context (TP-2026-03-16-344)

## Approval Gate Workflow (Required)


---

## Add Cold Outreach Cadence & Pipeline Tracking to Outreach Agent (TP-2026-03-16-351)

## Outreach Cadence Protocol


---

## Multi-touch Outreach Sequencing with Personalized Pipeline Tracking (TP-2026-03-16-363)

**Outreach Sequencer Tool:** Execute multi-touch personalized sequences via `python execution/outreach_sequencer.py`. Commands: `create-sequence --leads CSV --template [dream100|cold_email|warm_followup]` (generates personalized copy per prospect), `next-touches --due [today|DATE]` (view pending touches), `mark-sent/replied/booked` (track pipeline), `stats` (response/book rates). Hard rule: every message must reference prospect-specific data (name, website, niche). Templates: Dream 100 (7 touches/30 days, mixed email+LinkedIn), Cold Email (4 touches/14 days), Warm Followup (3 touches/10 days). DB: `.tmp/outreach/sequences.db`. LLM: Claude Sonnet 4.6.


---

## Add Dream 100 List Validation & GammaDoc Integration to Outreach (TP-2026-03-16-365)

Dream 100 List Validation: Before launching cold outreach campaigns, validate prospect lists for: (1) duplicate entries, (2) complete contact information (email, LinkedIn, phone), (3) company relevance scoring. Integrate GammaDoc research framework to enrich each prospect with: personalization vectors, pain points, decision-maker hierarchy, and custom angle recommendations.


---

## Hormozi Wealth Distribution & Pareto Targeting Framework for Outreach (TP-2026-03-16-366)

**Hormozi Wealth Targeting Principle:**


---

## Routing Table Authority: Skill-based SOP Ownership & Delegation (TP-2026-03-16-367)

**Routing Authority:**


---

## Sales Pipeline Intelligence via Dashboard Data Access (TP-2026-03-16-372)

• Access DashboardClient to query sales funnel, contact journey, and UTM attribution before cold outreach campaigns


---

## Claude Sonnet 4.6 Email Generation with Token Cost Tracking (TP-2026-03-16-376)

**Cold Email Generation Tool (generate_emails.py)**


---

## Add Business Audit Generation to Outreach Pre-Qualification Toolkit (TP-2026-03-16-381)

**Business Audit Generator** — Pre-outreach qualification tool. Generate personalized audit packages (1-page audit doc, landing page, 3 ad angles, outreach email) in 60–90 seconds via http://localhost:5050/audit or CLI. Use to warm cold leads before Dream 100 or cold outreach campaigns. Inputs: business name, website, category, phone, address, rating, owner name. Outputs uploaded to Google Drive folder (shared link). Cost: ~$0.08–0.15 per audit. Always generate audit first for high-value prospects; include Drive link in initial outreach to demonstrate operator thinking.


---

## Memory Migration Tool Access for Prospect & Campaign Data (TP-2026-03-16-382)

You have access to memory_migrate.py, a tool that parses and migrates prospect lists, campaign decisions, and outreach learnings into a searchable SQLite memory store. When building cold outreach sequences or Dream 100 strategies, reference stored decisions and learnings about prospect targeting, messaging approaches, and campaign outcomes from previous efforts.


---

## Add approval_gate integration for high-risk outreach campaigns (TP-2026-03-16-387)

Before executing bulk outreach:


---

## Lead CSV Import & Outreach Sequence Routing (TP-2026-03-16-389)

## CSV Lead Intake & Routing (TP-015)


---

## SOP Allocation System Integration for Outreach Agent Training (TP-2026-03-16-395)

## Training Material Allocation


---

## Add Learned Rules SOP to outreach agent workflow (TP-2026-03-16-402)

## Learned Rules


---

## Dream 100 Research Tool Integration for Prospect Intelligence (TP-2026-03-16-403)

**Dream 100 Research Tool**: Before drafting outreach, run research_prospect.py on target's website to extract: current offer/CTA, funnel type (VSL/webinar/application/direct), brand colors, logo, social proof signals, marketing gaps, and key copy. Use findings to personalize cold email hooks (e.g., "I noticed you're running a VSL funnel but missing email nurture—here's how we filled that gap for [similar client]"). Store research output in .tmp/ for reference during campaign creation.


---

## Student At-Risk Outreach: Dream 100 Re-engagement for Stuck Coaching Clients (TP-2026-03-16-406)

**At-Risk Student Re-Engagement (Dream 100 Model)**


---

## Multi-touch sequence orchestration and tracking capabilities (TP-2026-03-16-407)

Multi-touch outreach sequencer: Create templated sequences (dream100, cold_email) from qualified lead lists. Manage touchpoint scheduling across email, LinkedIn DM, and follow-up channels. Track prospect responses (replied, booked) and sequence progress. Generate sequence statistics (touches sent, reply rate, booking rate) and export sequence data as JSON for CRM integration.


---

## Add brand-voice extraction to outreach pre-work checklist (TP-2026-03-16-412)

**Before Dream 100 outreach or personalized cold email:** Run brand voice extraction via `/extract-voice --name "[Prospect]" --website/youtube/instagram/linkedin [source]` to generate `.tmp/brand-voices/{slug}.md`. Always include the extracted brand voice markdown as context when drafting outreach assets to ensure tone, language patterns, and communication style match the prospect's authentic voice.


---

## Creator Intelligence Scraping for Dream 100 Research & Prospect Profiling (TP-2026-03-16-415)

**Creator Intelligence Scraping** — Use `creator-intel-sop.md` pipeline to reverse-engineer Dream 100 prospects' intellectual frameworks from YouTube + Instagram. Run `scrape_creator_intel.py` to extract transcripts/captions, then `build_creator_brain.py` to synthesize comprehensive brain docs. Output captures frameworks, strategies, terminology, examples—enabling personalized cold outreach that references prospect's actual positioning and mechanisms.


---

## VSL Script Generation for Dream 100 Personalization (TP-2026-03-16-418)

VSL Script Generation Tool: Use generate_vsl.py to auto-generate personalized Video Sales Letter scripts for Dream 100 leads. Inputs: lead CSV (business_name, industry, estimated revenue). Output: industry-targeted VSL broken into 9 beats (Hook → Problem → Agitation → Solution → Credibility → Offer → Proof → Objections → CTA). Use in email sequences: embed VSL script hook as opening line, or reference full script in follow-up. Example: 'I created a 90-second VSL tailored to [Industry] founders stuck at $X plateau—showing exactly how we've helped [Competitor] scale from $X to $Y.'


---

## Multi-Channel Outreach Orchestration & Rate Limit Management (TP-2026-03-16-422)

MULTI-CHANNEL OUTREACH TOOL:


---

## Session context loader for outreach continuity and decision recall (TP-2026-03-16-425)

- Load session boot context via `memory_boot.py` at start


---

## Google Drive Asset Management for Dream 100 & Outreach Campaigns (TP-2026-03-16-428)

**Google Drive Upload Tool**: Use upload_to_gdrive.py to create shared Drive folders containing outreach assets:


---

## Email Generation SOP: Personalized Cold Outreach at Scale (TP-2026-03-16-431)

## Email Generation Workflow


---

## Verification Loop Tool for Cold Outreach Quality Assurance (TP-2026-03-16-441)

**Verification Loop Tool**: Run cold email/sequence drafts through a 2-step review cycle (producer generates → reviewer validates against task requirements and compliance rules → max 1 revision if needed). Use this before finalizing Dream 100 campaigns, cold outreach sequences, or sales assets. Validates: personalization depth, subject line effectiveness, compliance tone, call-to-action clarity, and brand voice consistency.


---

## Memory Store Integration for Outreach Campaign Tracking (TP-2026-03-16-449)

# Memory Store Integration
- dream_100_list: 'persons with sales,agency tags'
- outreach_sequence: 'decision records for cold campaigns'
- prospect_response: 'learning records from engagement patterns'
- contact_history: 'event records timestamped per prospect'


---

## Benchmark-Driven Quality Feedback Loop for Outreach Agent (TP-2026-03-16-454)

ACCESS: Weekly benchmark reports from agent_benchmark.py --report to review outreach-dream100 and outreach-follow-up test scores. ON FAILURE: Review generated proposals in .tmp/training-officer/proposals/ for specific gaps in prospect research depth, email hook relevance, or CTA clarity. ADJUST: Refine Dream 100 prospect research checklist, personalization prompts, and follow-up timing based on min_score deltas (target: 7+).


---

## Brand Discovery & Contact Research Tool for Cold Outreach Pipeline (TP-2026-03-16-458)

Brand Discovery & Pipeline Management: Use `brand_outreach.py` to discover brand contacts (discover --brand "[NAME]"), generate personalized cold intro emails (email --brand-id [ID] --template cold_intro), send outreach (send --brand-id [ID]), track replies (reply --brand-id [ID]), update pipeline status (status --brand-id [ID] --set [approved|rejected|contacted]), request followups (followups --days 7), and export prospect lists (export --output brands.csv). Maintains SQLite pipeline DB with discovery date, contact info, template history, and conversion metrics.


---

## Instant Business Audit as Dream 100 Outreach Tool (TP-2026-03-16-463)

**Instant Business Audit Tool**: Generate complete prospect packages including website audit, personalized landing page, 3 ad angles, and outreach copy. Usage: `run_audit(business_dict)` returns shareable Google Drive folder with all assets. Use this before sending Dream 100 outreach—reference audit findings in your email to prove you've done research and understand their specific pain points.


---

## Dream 100 GammaDoc Assembly Pipeline Tool Integration (TP-2026-03-16-465)

TOOL: assemble_gammadoc.py — Generates Gamma.app-ready markdown for Dream 100 outreach. Requires research JSON (brand/positioning) + assets JSON (hooks/scripts/copy). Outputs .tmp/gammadoc_<name>_<ts>.md. Usage: python execution/assemble_gammadoc.py --assets <file> --prospect-name "Name" [--research <file>]. Includes branded headers, meta hooks, YouTube/email sequences, case studies, and booking CTAs per Kabrin framework.


---

## Auto-classify & route SOPs to agent skills.md files (TP-2026-03-16-467)

## SOP Auto-Classification Tool


---

## Route outreach tasks to optimal cost-efficient models via smart_router (TP-2026-03-16-475)

**Tool: Smart Router**


---

## Dream 100 Pipeline Orchestration & Batch Processing (TP-2026-03-16-480)

Dream 100 Pipeline Orchestrator (run_dream100.py):


---

## Voice Memo Generation for Personalized Follow-up Outreach (TP-2026-03-16-483)

**Voice Memo Generation**: Use `voice_memo_generator.py` to create personalized audio follow-ups. Clone your voice once, then batch-generate memos from lead lists with custom templates. Syntax: `generate_voice_memo(text, voice_id)` or CLI batch mode with CSV. Outputs MP3s ready for email/Slack delivery. Dramatically increases open rates in cold outreach and Dream 100 follow-up sequences.


---

## Quality Drift Detection & Auto-Improvement Proposals for Outreach (TP-2026-03-16-491)

Add to outreach agent SOP:


---

## Add Claude Sonnet 4.6 email generation with token tracking (TP-2026-03-16-497)

**Cold Email Generator Tool**


---

## Memory Migration Tool Integration for Outreach History (TP-2026-03-16-503)

Can query memory_store.py to retrieve:


---

## Agent-to-Agent Task Delegation via Structured Comms Protocol (TP-2026-03-16-507)

## Agent Communication Protocol


---

## Add Cold Email Generation Skill with Personalization & CTA Standards (TP-2026-03-16-508)

**Cold Email Generation (B2B Lead Gen)**


---

## Approval Gate Integration for High-Risk Outreach Campaigns (TP-2026-03-16-512)

Before executing outreach campaigns >10 recipients or >$5 cost, use the approval_gate tool:
proposal_id = create_proposal(
  agent='outreach',
  action=f'Send {count} emails to {segment}',
  risk_level='review_before_send',
  cost=total_cost
)
if not is_approved(proposal_id):
  return {'status': 'blocked', 'proposal_id': proposal_id}


---

## Dream 100 List Scanning & Qualification Framework (TP-2026-03-16-518)

## Dream 100 List Qualification


---

## Add dashboard_client integration for real-time sales funnel & lead data (TP-2026-03-16-525)

**Dashboard Query Access (Outreach)**


---

## Dream 100 Hyper-Personalized Outreach SOP with Phase-Gated Execution (TP-2026-03-16-533)

DREAM 100 OUTREACH PIPELINE:


---

## Agent Communication Protocol: Inbox/Outbox Task Management (TP-2026-03-16-537)

**Task Management via Agent Communication Protocol:**


---

## LLM Model Routing for Cost-Efficient Outreach Tasks (TP-2026-03-16-542)

## LLM Model Routing (API Cost Management)


---

## Multi-Channel Outreach Orchestration & Rate-Limit Management (TP-2026-03-16-544)

**Multi-Channel Outreach Orchestration**: Execute cold outreach across Instagram DMs, Twitter DMs, email, and contact forms with built-in rate limiting. Supports batch CSV sends, channel rotation, and ramp-up scheduling. Commands: `send_outreach()` for single prospects, `batch_send()` for CSV campaigns, `check_rate_limit()` for compliance tracking. Integrates with Dream 100 workflows and includes follow-up scheduling per Kabrin's multi-channel patterns.


---

## Training Officer SOP Integration for Outreach Agent Upgrades (TP-2026-03-16-545)

### Training Officer Integration


---

## Add Prompt Contract Validation to Outreach Deliverables (TP-2026-03-16-557)

When generating cold emails, Dream 100 outreach sequences, or sales copy:


---

## Multi-touch Sequence Management & Automation for Dream 100 Campaigns (TP-2026-03-16-571)

### Multi-Touch Sequence Orchestration


---

## Add Approval Gate Protocol for Outreach Actions (TP-2026-03-16-580)

## Approval Gate Protocol


---

## Memory System Integration for Prospect & Campaign Tracking (TP-2026-03-16-582)

# Memory System for Prospect & Campaign Tracking


---

## VSL Script Integration for High-Value Cold Outreach Sequences (TP-2026-03-16-583)

VSL Script Deployment: When executing cold outreach to founder-led 7-8 fig businesses, recommend embedding a VSL (Video Sales Letter) script into the sequence. Use the 9-beat framework (Hook → Problem → Agitation → Solution → Credibility → Offer → Proof → Objection Handling → CTA). VSL scripts significantly outperform text-only cold emails. Keep scripts conversational, specific (numbers > claims), and focused on the prospect's exact pain point. Reference the generate_vsl.py tool to produce industry-specific scripts at scale for Dream 100 lists.


---

## Auto-Research Loop for Cold Outreach Campaign Optimization (TP-2026-03-16-585)

**Auto-Research for Outreach Campaigns**


---

## Add Cold Outreach Sequencing & Pipeline Tracking to Outreach Agent (TP-2026-03-16-589)

**Cold Outreach Sequencing Protocol:**


---

## Add memory boot context to outreach pre-call briefing (TP-2026-03-16-594)

**Pre-Campaign Memory Check**: Before launching cold outreach or Dream 100 sequences, load session boot context via `memory_boot.py --verbose`. Review Recent Decisions (past 7 days) to avoid re-pitching rejected prospects. Check Active Corrections for messaging shifts. Reference Key Preferences for tone/channel alignment in outreach copy.


---

## Google Drive automation for Dream 100 & outreach asset distribution (TP-2026-03-16-599)

**Google Drive Uploader Tool**: Automates creation of shared Google Drive folders containing setter outreach scripts, closing call scripts, email sequences, and SMS workflows. Use when you need to: (1) package outreach collateral for a Dream 100 list, (2) share scripts with sales team members, (3) distribute email/SMS sequences to a prospect group. Requires service_account.json and GOOGLE_SHARE_EMAIL env var. Outputs results to gdrive_upload_results.json.


---

## Outreach Sequencer Tool: Multi-touch pipeline management with personalized copy (TP-2026-03-16-601)

**Outreach Sequencer Tool:** Execute multi-touch outreach sequences using `python execution/outreach_sequencer.py`. Commands: `create-sequence --leads CSV --template [dream100|cold_email|warm_followup]`, `next-touches --due [today|DATE]`, `mark-sent --touch-id ID`, `mark-replied --prospect-id ID --notes TEXT`, `mark-booked --prospect-id ID`, `stats`, `list-sequences`, `export --format json`. Hard rule: Every message must reference something specific about the prospect—no mass blasts. Dream 100 (7 touches/30 days) uses initial value delivery + LinkedIn soft touches + case studies + social proof. Cold Email (4 touches/14 days) uses intro + proof + new angle + breakup. Warm Followup (3 touches/10 days) for re-engagement.


---

## GammaDoc Assembly Tool — Dream 100 Presentation Automation (TP-2026-03-16-603)

**GammaDoc Assembly (Dream 100):** Execute assemble_gammadoc.py to auto-generate Gamma.app presentations. Takes research JSON (brand, positioning, offer details) + assets JSON (hooks, scripts, copy) → outputs branded markdown. Structure: header (logo + colors) → system overview → FREE DELIVERABLES block (3 Meta hooks, YouTube script, 3-email sequence, landing headlines, VSL hook + problem, confirmation copy) → case studies → single booking CTA. Usage: `python execution/assemble_gammadoc.py --research [file] --assets [file] --prospect-name "Name"`. Output: `.tmp/gammadoc_<name>_<ts>.md` (paste directly into Gamma).


---

## Agent Routing Table Reference for Outreach Ownership Clarity (TP-2026-03-16-605)

Reference: agent-routing-table.md (directives/agent-routing-table.md)


---

## Auto-classify & route SOPs to agent skills.md via allocate_sops.py (TP-2026-03-16-606)

## SOP Auto-Routing Integration


---

## Add Business Audit as Pre-Outreach Intelligence Tool (TP-2026-03-16-620)

**Business Audit Generator** (Pre-outreach Intel Tool)


---

## CEO Boot Sequence + Persistent Memory Integration for Outreach Agent (TP-2026-03-16-622)

**CEO Context Inheritance** — At session start, load: /Users/Shared/antigravity/memory/ceo/brain.md (CEO decisions, active priorities, delegation log). Cross-reference your Dream 100 list and cold outreach sequences against CEO's current strategic focus. If a prospect appears in CEO's delegation log as high-priority, escalate engagement intensity. Sync your campaign learnings back to CEO brain after each outreach cycle.


---

## Add Sales Manager Data Pulls to Outreach Agent Context (TP-2026-03-16-625)

**Data Context for Outreach Campaigns:**


---

## Add automation-triggered outreach workflows to outreach agent (TP-2026-03-16-628)

## Automation-Powered Outreach


---

## Lead CSV Import & Outreach Tool Integration (TP-2026-03-16-631)

**Lead CSV Import & Routing:**


---

## Extract positioning intelligence for outreach targeting and messaging (TP-2026-03-16-632)

**Input: Positioning Brief from WebBuild Agent**


---

## Add Dream 100 benchmark testing to outreach agent quality assurance (TP-2026-03-16-633)

You are benchmarked weekly on Dream 100 outreach quality. Key benchmark criteria: (1) Research-backed personalization (reference specific prospect gaps, not generic praise), (2) Value prop clarity (why you specifically help them), (3) CTA specificity (avoid 'schedule a call'—use concrete next steps), (4) SOP compliance (follow Dream 100 framework). Min quality score: 7/10. Failures trigger optimization proposals.


---

## SOP Allocation Process: Enable Outreach Agent to Ingest Training Materials (TP-2026-03-16-638)

## SOP Allocation Process


---

## Add Media Buyer → Outreach Agent Handoff Protocol (TP-2026-03-16-639)

## Handoff Protocol: MediaBuyer → Outreach Agent


---

## Instant Business Audit as Done-For-You Outreach Tool (TP-2026-03-16-644)

**Instant Business Audit Tool**: Run `generate_business_audit.py` to create personalized audit packages for Dream 100 targets. Outputs: (1) 1-page audit document (Google Doc), (2) custom landing page (HTML), (3) 3 ad angles, (4) personalized cold outreach message, (5) shareable folder link. Use as attachment or preview link in cold email to establish credibility and open conversation. Best for: high-intent B2B outreach, qualified Dream 100 campaigns, follow-up sequences.


---

## Self-Modifying Rules System for Outreach Agent (TP-2026-03-16-649)

## Learned Rules


---

## Dream 100 + Sales Funnel Qualification Framework (TP-2026-03-16-657)

QUALIFICATION FRAMEWORK FOR OUTREACH:


---

## Auto-extract prospect brand voice before personalized outreach (TP-2026-03-16-660)

**Brand Voice Extraction (Pre-Outreach)**


---

## Creator Intelligence Research SOP for Dream 100 Prospect Profiling (TP-2026-03-16-664)

**Creator Intelligence Research** — Use creator-intel-sop.md to build comprehensive brain docs on Dream 100 prospects before outreach. Run `scrape_creator_intel.py` (YouTube + Instagram) then `build_creator_brain.py` to extract their frameworks, mechanisms, strategies, and terminology. Output feeds directly into personalized cold email/DM templates that reference their own intellectual frameworks. Best for: positioning offers, understanding their customer funnel, identifying strategic alignment points.


---

## Dream 100 Targeting for High-Ticket Coach Niche (TP-2026-03-16-665)

DREAM 100 TARGETING FOR ALLDAYFBA OUTREACH:


---

## Mechanism Positioning for Dream 100 & Cold Outreach Messaging (TP-2026-03-16-669)

MECHANISM POSITIONING FOR OUTREACH:


---

## Dream 100 Pipeline Orchestration & Batch Processing Capability (TP-2026-03-16-671)

Dream 100 Pipeline Orchestration:


---

## Auto-Outreach Orchestration Skill for Cold Email Pipeline (TP-2026-03-16-673)

**Skill: `/auto-outreach`** (Orchestration)


---

## Voice Memo Generation for Personalized Cold Outreach Follow-ups (TP-2026-03-16-678)

- Voice Memo Generation: Generate personalized audio follow-ups using Eleven Labs voice cloning. Create custom voice messages for Dream 100 targets and cold outreach sequences. Batch-generate from lead lists with template personalization. Supports voice cloning from audio samples and programmatic integration into outreach workflows.


---

## Dream 100 + Cold Outreach Sequencing from Client Research Outputs (TP-2026-03-16-680)

PHASE 2.5 — OUTREACH PREPARATION (New)


---

## Add Dream 100 List Validation & Segmentation Framework (TP-2026-03-16-681)

**Dream 100 List Validation & Segmentation**


---

## Email Generation SOP: Personalized Cold Outreach Workflow (TP-2026-03-16-685)

**Email Generation Workflow:**


---

## Amazon FBA High-Ticket Coaching Positioning & Dream 100 Targeting (TP-2026-03-16-688)

AMAZON COACHING OFFER CONTEXT:


---

## Quality Drift Detection & Auto-Improvement Prompts for Outreach (TP-2026-03-16-689)

Tool: Quality Score Feedback Loop


---

## Implement Verification Loop for Cold Outreach & Sales Deliverables (TP-2026-03-16-690)

## Verification Loop Protocol for Outreach


---

## Add CRM Pipeline Tracking & Disposition Management to Outreach SOP (TP-2026-03-16-691)

**CRM Pipeline Structure for Outreach:**


---

## Sales Team Playbook: Org Structure & Pre-Hire Foundations for Outreach (TP-2026-03-16-694)

SALES ORG CONTEXT: SabboOS serves two offers (Amazon OS + Agency OS). Revenue thresholds for hiring: $0-$100K (founder closes), $100-$300K (1-2 closers, founder manages), $300K+ (3+ closers, dedicated manager). Pre-hire requirements: founder must close 20-30 deals, achieve 40-60% close rate on warm leads, document winning script, build pre-call nurture (80% sold before call). Qualification rule: don't pitch team-building until prospect has organic sales dialed ($100K+/mo minimum). Dream 100 + cold outreach should identify founder-stage vs. scaling-stage prospects.


---

## Student Onboarding Trigger Recognition for Outreach Follow-ups (TP-2026-03-16-707)

When a student has been onboarded via the Student Onboarding SOP, reference their tier classification (A/B/C) and enrollment milestone in follow-up sequences. Example: For Tier A students, emphasize the first 30-day foundation phase in kickoff reminders. For Tier B sellers, frame follow-ups around systems upgrades. For Tier C investors, highlight portfolio diversification angle. Avoid generic "congrats on enrollment" messaging—personalize to their documented motivation type (income_replacement, scaling, or asset_building).


---

## Grade Agent Output Integration for Outreach Quality Feedback Loop (TP-2026-03-16-708)

## Quality Grading Integration


---

## Add Lead-Gen Email Prompt Contract & Output Validation (TP-2026-03-16-710)

Load lead_gen_email.yaml prompt contract for all cold outreach tasks. Validate outputs against: (1) No placeholder text, (2) Personalized subject + opening hook, (3) Specific CTA (not 'let me know'), (4) 80-200 word count, (5) All 5 sections present. On validation fail, auto-revise max 2 attempts. Reject outputs with generic salutations, corporate-speak, or template language. For missing inputs (pain_points, contact_name), ask user before proceeding.


---

## Cold Outreach Sequencing & Follow-up SOP (TP-2026-03-16-720)

**Cold Outreach Sequence SOP:**


---

## Multi-touch sequence management and tracking capability (TP-2026-03-16-734)

• Can create multi-touch sequences from qualified leads using templates (dream100, cold_email, warm_intro)


---

## Add skill_telemetry_hook integration for outreach execution tracking (TP-2026-03-16-742)

Monitor skill telemetry for: outreach-sequence, parallel_outreach, dream100, cold-email. When user provides corrections ("no", "wrong", "too aggressive", "not personalized"), log negative scores to optimize future outreach patterns. Track success rates on Dream 100 targeting and email personalization for continuous improvement.


---

## Route outreach tasks to optimal models based on complexity & cost (TP-2026-03-16-747)

from execution.smart_router import route_task


---

## VSL Script Generation Tool for High-Value Lead Qualification (TP-2026-03-16-749)

VSL Script Generation Tool: Use generate_vsl.py to create personalized Video Sales Letter scripts for high-value leads. Inputs: lead CSV (name, business, industry). Output: structured VSL following proven framework (Hook → Problem → Agitation → Solution → Proof → Offer → CTA). Optimized for founder-led B2B service pitches ($5K–$25K retainer range). Command: python generate_vsl.py --input leads.csv --single [business_name]. Use for Dream 100 outreach, cold email sequences, and sales presentations.


---

## Add Competitor Intel skill reference for outreach prospecting (TP-2026-03-16-758)

**Skill: Competitor Research for Outreach**


---

## Verification Loop Integration for Outreach Quality Control (TP-2026-03-16-784)

**Verification Loop Tool**: Use `run_verification_loop(task, producer_model, reviewer_model, contract_path)` to generate and iteratively refine cold emails, sales sequences, and Dream 100 outreach. Supports Claude, Gemini, and OpenAI. Returns final approved output after up to 3 review cycles. Example: `run_verification_loop(task='Write cold email for SaaS founder', producer_model='claude', reviewer_model='gemini', contract_path='lead_gen_email.yaml')` — validates against conversion hooks, personalization depth, and CTA clarity.


---

## Benchmark-Driven Quality Monitoring for Dream 100 & Outreach (TP-2026-03-16-803)

### Benchmark Testing


---

## Hormozi Dream 100 & High-Value Prospect Targeting Framework (TP-2026-03-16-806)

HORMOZI PROSPECT TARGETING:


---

## Jeremy Haynes Buyer Psychology & Sales Mechanics for Cold Outreach (TP-2026-03-16-810)

**Jeremy Haynes Sales Psychology & Close Mechanics:**


---

## Instant Business Audit Package Generation for Dream 100 Targeting (TP-2026-03-16-814)

**Instant Business Audit Tool**: Generate complete prospect packages including:


---

## Operator-Coach Credibility Anchor for Cold Outreach & Dream 100 (TP-2026-03-16-816)

OPERATOR-COACH DIFFERENTIATION FRAMEWORK:


---

## Johnny Mau Pre-Frame Psychology for Cold Outreach Sequences (TP-2026-03-16-823)

## Johnny Mau Pre-Frame Psychology System


---

## Add Ben Bader's 'One Client Changes Everything' Framework to Outreach Strategy (TP-2026-03-16-827)

**Ben Bader High-Value Targeting Principle**: One premium client can replace 15-20 low-value clients. Focus Dream 100 outreach on info/coaching creators with existing audiences (10K+ followers minimum). Lead with operator/shovel-seller positioning, not service provider. Emphasize revshare upside ($10K-$100K+/mo potential) over hourly rates. Reference case study snowball effect: first big win → referrals → inbound. Avoid volume metrics in pitch; emphasize 'one John Ham moment' narrative.


---

## Trust-Based Outreach Framework: Replace Hype with Proof Sequences (TP-2026-03-16-835)

TRUST-FIRST OUTREACH PRINCIPLE:


---

## Dream 100 + Cold Outreach Frameworks from Creator Playbooks (TP-2026-03-16-839)

DREAM 100 + COLD OUTREACH FRAMEWORKS (from sabbo-growth-os-brain.md):


---

## Voice Memo Generation for Personalized Outreach Follow-ups (TP-2026-03-16-842)

VOICE MEMO GENERATION: Use voice_memo_generator.py to create personalized audio follow-ups. Generate voice memos for Dream 100 targets, cold outreach sequences, and sales follow-ups. Clone your voice once, then batch-generate personalized memos from lead lists. Memos stored in .tmp/voice-memos/. Command: `python execution/voice_memo_generator.py generate --text "[personalized message]" --voice-id "[your_voice_id]"` or batch mode with CSV.


---

## Revenue-Share Partnership Positioning for Dream 100 Outreach (TP-2026-03-16-843)

**Revenue Share Partnership Model**: Pierre operates on ~20% revenue share (15-25% range), NOT retainers. Only partners with info product businesses. Position as 'we run your entire marketing/sales infrastructure (copy, funnels, VSLs, sales team, email) and we win when you win.' Key qualifier: prospect must have existing revenue/product. Disqualify: service businesses, non-info-product models, founders seeking hourly labor. Dream 100 targets should be info product founders in growth phase ($20K-$500K/mo range).


---

## Dream 100 Qualification: Intentionality-First Prospect Filtering (TP-2026-03-16-847)

**Dream 100 Intentionality Filter**: Before adding a prospect, document: (1) Specific reason they align with the offer, (2) Their current pain point we solve, (3) Proof they have budget/authority. Remove prospects that can't pass all 3. Prioritize warm intros and credible referrals over cold lists. Quality Dream 100 (50-100 highly-qualified targets) outperforms quantity (500+ cold names). Each outreach should feel personalized, not templated.


---

## Category of One Positioning for Dream 100 & Cold Outreach Precision (TP-2026-03-16-850)

**Category of One Qualification (Dream 100 Filter):** Before building a prospect list, apply this niche-down sequence: Industry → Geography → Revenue/Size → Specific Pain → Your Unique Mechanism. Example: "Marketing agency" → "Phoenix only" → "$50K+/mo revenue" → "needs TikTok ads" → "your DFY model." Reject broad niches. Only outreach to prospects where client has zero direct competitors in their specific segment.


---

## Multi-channel Outreach Orchestration Tool Integration (TP-2026-03-16-852)

**Multi-Channel Outreach Execution**: You can now send personalized cold outreach across Instagram DMs, Twitter/X DMs, email, and contact forms using the `multichannel_outreach` tool. Features include: batch sending from prospect lists (CSV), automatic rate-limit enforcement (50 IG/day, 50 Twitter/day, 100 email/day max), channel rotation to avoid detection, follow-up scheduling, and daily send tracking. Use for Dream 100 campaigns, cold outreach sequences, and prospect nurturing. Syntax: `send_outreach(name, email, instagram, twitter, message)` or `batch_send(csv_path, template, channels=['ig','email','twitter'])`.


---

## Creator Brain Synthesis: Extract Dream 100 & Cold Outreach Angles from Creator Intel (TP-2026-03-16-866)

**Creator Brain Extraction for Outreach:**


---

## GammaDoc Assembly Pipeline — Dream 100 Deliverable Automation (TP-2026-03-16-867)

**GammaDoc Assembly Tool** — Use `assemble_gammadoc.py` to convert prospect research + assets into branded Gamma.app documents for Dream 100 outreach. Structure: branded header → system overview → FREE DELIVERABLES (Meta hooks, YouTube script, email sequence, landing page headlines, VSL hook, confirmation copy) → case studies → booking CTA. Command: `python execution/assemble_gammadoc.py --research <json> --assets <json> --prospect-name "Name"`. Outputs ready-to-paste markdown. Update YOUR_CASE_STUDIES and YOUR_BOOKING_LINK before deployment.


---

## Add GammaDoc Cold Email Framework to Outreach Skills (TP-2026-03-16-887)

**GammaDoc Cold Email Framework**: Structured 3-part email sequence (hook → value prop → social proof) designed for high-ticket Dream 100 targeting. Uses pattern interrupts, specific pain point callouts, and one-click CTAs. Optimize subject lines for 5-word max, personalize with company research, A/B test templates across Dream 100 lists.


---

## Add dashboard_client tool for real-time sales & outreach metrics (TP-2026-03-16-889)

**Dashboard Integration Tool**: Access live 247growth.org metrics via dashboard_client:


---

## Add grade_agent_output.py Integration to Outreach Skills (TP-2026-03-16-894)

## Evaluation Awareness


---

## Multi-touch sequence management and tracking for Dream 100 & cold outreach (TP-2026-03-16-900)

You have access to outreach_sequencer.py for managing multi-touch sequences:


---

## VSL Script Generation for Cold Outreach Sequences (TP-2026-03-16-904)

Tool: generate_vsl.py — Generate personalized Video Sales Letter scripts for cold outreach


---

## Add memory_boot.py context loading to outreach session init (TP-2026-03-16-907)

**Session Init:** Load memory_boot.py context at conversation start


---

## Google Drive Funnel Document Upload & Sharing Automation (TP-2026-03-16-908)

TOOL: google_drive_uploader — Upload markdown scripts (setter outreach, closing calls, email sequences) and HTML funnel pages to Google Drive folders using service account auth. Requires: service_account.json at project root, GOOGLE_SHARE_EMAIL env var. Returns: Drive folder URL and file links for prospect sharing. Use for: deploying Dream 100 prospect packs, sharing outreach collateral with sales teams, version-controlling scripts.


---

## Verification Loop Tool for Cold Email Quality Assurance (TP-2026-03-16-913)

VERIFICATION LOOP TOOL: Use verification_loop.py to quality-check cold emails and sales sequences before sending.
from execution.verification_loop import run_verification_loop
result = run_verification_loop(
  task="Write cold email for [prospect type]",
  producer="claude",
  reviewer="claude",
  contract="execution/prompt_contracts/lead_gen_email.yaml"
)


---

## Add Dream 100 Email Benchmarking & Quality Gates to Outreach SOP (TP-2026-03-16-917)

## Dream 100 Email Quality Benchmarks


---

## Instant Business Audit Package Generation for Prospect Research (TP-2026-03-16-920)

**Prospect Audit Generation Tool**: Before outreach, run `generate_business_audit.run_audit(prospect_dict)` to create: (1) Website analysis & insights, (2) 1-page business audit (Google Doc), (3) Personalized landing page (HTML), (4) 3 Meta-style ad angles, (5) Custom outreach message, (6) Shareable folder link. Returns audit_result with all artifacts + shareable URL. Use for Dream 100 warm intros and qualified cold outreach campaigns.


---

## Voice Memo Generation for Personalized Dream 100 & Cold Outreach Follow-ups (TP-2026-03-16-926)

## Voice Memo Generation


---

## Quality Drift Detection & Auto-Proposal Generation for Outreach (TP-2026-03-16-929)

Tool: Quality Tracker & Drift Detection


---

## Cold Outreach Email Generation with Strict Personalization & Quality Gates (TP-2026-03-16-934)

LEAD_GEN_EMAIL_CONTRACT:


---

## Add skill_telemetry_hook integration to outreach execution tracking (TP-2026-03-16-942)

After executing outreach skills (parallel_outreach.py, generate_emails.py, run_dream100.py, research_prospect.py, outreach_sequencer.py), log to telemetry:
- Skill name (outreach, cold-email, dream100, sales-prep, outreach-sequence)
- Execution score (default 8, reduced to 2-3 if user correction detected)
- Correction signals: watch for "didn't work", "wrong approach", "bad subject", "poor timing" in user follow-up
- Auto-score from script exit codes when available


---

## CEO Agent v2.0 — Add Outreach Delegation Patterns to Memory Protocol (TP-2026-03-16-978)

**Outreach Agent Delegation Protocol**


---

## Add Sales Manager KPI Framework to Outreach Pre-Call Qualification (TP-2026-03-16-979)

**KPI-Driven Outreach Sequencing**: Prioritize Dream 100 and cold outreach based on sales calendar utilization (target 70–75%). Flag prospects for immediate outreach if team calendar < 60%. Sequence warm intros before cold outreach. Every outreach sequence must support the 60-second inbound response rule by pre-qualifying intent level.


---

## Automation Trigger Recognition for Outreach Workflows (TP-2026-03-16-980)

### Automation Trigger Recognition


---

## Add Media Buyer → Outreach Handoff Protocol (TP-2026-03-16-982)

## Handoff to Outreach Agent


---

## Dream 100 & Cold Outreach Strategy for Premium B2B SaaS Founders (TP-2026-03-16-986)

**DREAM 100 TARGETING CRITERIA (Agency OS)**


---

## Dream 100 & Competitive Positioning for AllDayFBA Outreach (TP-2026-03-16-988)

COMPETITIVE OUTREACH CONTEXT:


---

## Mechanism Positioning for Dream 100 & Cold Outreach Angles (TP-2026-03-16-989)

## Mechanism Positioning for Outreach


---

## Amazon FBA Dream 100 & Cold Outreach Targeting Framework (TP-2026-03-16-994)

## OUTREACH TARGETING FRAMEWORK


---

## Add CRM tracking + DM outreach templates to sales execution (TP-2026-03-16-995)

EXECUTION CONTEXT — Sales Calendar March 2026:


---

## Sales Team Org Structure & Revenue Thresholds for Outreach Scaling (TP-2026-03-16-996)

REVENUE-STAGE OUTREACH CALIBRATION:


---

## Add Sales Metrics Tracking to Outreach Performance Coaching (TP-2026-03-16-997)

OUTREACH PERFORMANCE DIAGNOSIS:
