# Ads & Copy Bot — Skills
> bots/ads-copy/skills.md | Version 2.0

---

## Purpose

This file tells you which resources to pull for which task. When you receive a copy request, match it to the skill category below, then reference every listed SOP and training file before writing.

---

## Owned Claude Code Skills (Slash Commands)

| Skill | Invocation | What It Does |
|---|---|---|
| Competitor Intel | `/competitor-intel` | Scrape Meta Ad Library for competitor ad activity and surface winning angles |

**Skill file:** `.claude/skills/competitor-intel.md`

When `/competitor-intel` runs, it reads `directives/ads-competitor-research-sop.md`, scrapes competitor ads, and outputs analysis to `.tmp/ads/`. Feeds into morning briefing and ad copy generation.

---

## Skill: Ad Copy

**When to use:** Writing Meta, YouTube, LinkedIn, or Google ad copy.

**Reference in order:**
1. `SabboOS/Agency_OS.md` → Ads section (for agency ads)
2. `SabboOS/Amazon_OS.md` → Ads section (for coaching ads)
3. `SabboOS/Agents/WebBuild.md` → Phase 2D (ad copy variant framework — 3 angles × 3 formats)
4. `memory.md` → Approved Work Log (what's converted before)
5. `memory.md` → Competitor Intelligence Log (what the market is running)

**Output standard:**
- 3 angles minimum: Pain-aware, Result-aware, Mechanism/curiosity
- 3 formats per angle: Video script (30–60s), Static copy, Story/Reel (15–30s)
- Every hook must be specific — no generic openers
- Primary text under 125 characters for static
- Flag top 2 variants as recommended A/B test

---

## Skill: VSL Scripting

**When to use:** Writing a video sales letter script.

**Reference in order:**
1. `SabboOS/Agents/WebBuild.md` → Phase 2C (VSL structure: hook → problem → credibility → mechanism → proof → offer → CTA)
2. `SabboOS/Agency_OS.md` or `Amazon_OS.md` → relevant offer details, proof points, ICP
3. `bots/clients/[client].md` → brand voice if writing for a client
4. `memory.md` → Approved Work Log

**Output standard:**
- Target runtime: 12–20 minutes (~1,800–3,000 words)
- Hook must create pattern interrupt in first 30 seconds
- Proof section: Before → What we did → After (specific numbers, no vague claims)
- Offer section: what they get, investment, guarantee, urgency

---

## Skill: Landing Page Copy

**When to use:** Writing copy for a landing page or VSL page.

**Reference in order:**
1. `SabboOS/Agents/WebBuild.md` → Phase 2A (homepage) and 2B (landing page)
2. `SabboOS/Agency_OS.md` or `Amazon_OS.md` → funnel stage, ICP, promise
3. `memory.md` → Approved Work Log

**Output standard:**
- Above fold: outcome-first headline, who it's for, one CTA
- No nav on conversion pages
- CTA repeated minimum 3× on full-length pages
- FAQ section handles top 5 objections
- Every section ends with a logical next step

---

## Skill: Email Copy

**When to use:** Writing email sequences (nurture, re-engagement, pre-call, post-call).

**Reference in order:**
1. `SabboOS/Agency_OS.md` or `Amazon_OS.md` → email sequence section
2. `bots/clients/[client].md` → voice and audience (if client work)
3. `memory.md` → Approved Work Log

**Output standard:**
- Subject line: specific, curiosity-driven, no clickbait
- Body: one idea per email, max 300 words for nurture, can go longer for pre-call
- CTA: one per email, clear action

---

## Skill: Competitor Research

**When to use:** Morning briefing scrape or on-demand competitor analysis.

**Reference in order:**
1. `directives/ads-competitor-research-sop.md` — full process
2. `directives/morning-briefing-sop.md` — output format
3. `memory.md` → Competitor Intelligence Log (for historical context)

**Output standard:**
- Follow morning briefing format exactly
- Flag the single most important insight at the top
- Always note how long the top ad has been running

---

## Skill: Creative Performance Analysis

**When to use:** Sabbo provides ad performance data and asks what to do with it.

**Process:**
1. Pull from `memory.md` → Approved Work Log and Competitor Intelligence Log for context
2. Identify the metric furthest from target (CPL, CTR, hook rate, close rate from ad)
3. Apply constraint logic: is this a targeting problem, creative problem, or offer problem?
4. Output: one recommendation with specific action, not a list of maybes

---

## Allocated SOPs

*This section is auto-populated by `execution/allocate_sops.py` when new training files are uploaded.*
*Each entry below is a reference to an ingested document — read it before executing the tagged task type.*

<!-- New SOP references will be appended below this line by allocate_sops.py -->

---

*Ads & Copy Bot Skills v1.1 — 2026-02-21*

---

## Skill: Copywriting Frameworks & Memory (TP-003)

**Primary Frameworks:**
- AIDA (Attention → Interest → Desire → Action)
- PAS (Problem → Agitate → Solve)
- Curiosity Gap method for hooks
- Social proof layering (testimonials, case studies, data points)
- Client-specific voice matching (reference brand voice guide before drafting)

**Performance Memory Protocol:**
- Log all delivered copy with: client name, platform, framework used, engagement rate (if available), client feedback
- Flag high-performers (>15% CTR or client approval first-pass)
- Flag rejections with reason codes: tone mismatch, too salesy, unclear CTA, brand voice violation
- Quarterly analysis: which framework + client vertical combinations win most

---

## LLM Routing Rules (TP-012)

- **Haiku (default):** Lead scraping, CSV processing, ICP scoring, formatting, heartbeat checks
- **Sonnet (standard):** Email copy, ad script drafts, competitor research, standard outreach variants
- **Opus (high-stakes only):** Hooks, headline variants, offer angles, final copy review/editing. Only use when explicitly requested or task matches this list exactly.

**Hard rule:** Never default to Opus. Alert on any Opus call that isn't explicitly justified.

---

## AI Safety & Compliance Guardrails (TP-018)

**Compliance Screening:** Before generating ad copy, check if campaign targets healthcare, financial services, gambling, or pharmaceutical sectors. If yes, flag all claims as requiring substantiation and append disclaimer templates. Reject copy containing unqualified health claims, financial guarantees, or odds statements without explicit legal review notation.

---

## VSL & Platform-Specific Scripts (TP-023)

**VSL Script Generation (Jeremy Haynes Method):**
- Generate 10–20 min VSL scripts with sections: Summary (0:00–1:30) → Hook → Credibility → Buying Motives → Offer (price stated) → Objection Handling → Qualification → CTA
- Always state price upfront; never use value stacks or fake discounts
- Pull objection handling from real sales call data
- Use qualification language: "this is for you / not for you"

**Platform-Specific Ad Scripts:**
- Meta: Hook (2–3 sec) → Problem Agitation → Solution Tease → CTA
- YouTube Pre-roll: Hook (5 sec, earn before skip) → Credentials → Problem → Solution → Proof → CTA
- Output columns: ad_hook, ad_body, ad_cta, ad_platform

---

## Morning Briefing Generation (TP-026)

Daily at 08:00 or on-demand, synthesize competitor intel (Agency & Coaching verticals), platform trends, and one specific creative test recommendation into the standard brief format. Include: single top insight, competitor longest-running ads + new creative, format trends, key angles, platform shifts, and one weekly test tied to observed signals. Validate before send: insights are specific & actionable, every competitor entry has real findings, test is grounded in actual intel, and total length is <500 words.

---

## VSL Landing Page Copy Strategy (TP-030)

- Headline must answer: "Is this for me?" and drive curiosity without overselling
- Pre-VSL copy should qualify buyer type and establish pattern interrupt
- Ad copy mirrors VSL's core positioning: solve specific problem for specific buyer in specific timeframe
- Avoid feature-focused copy; lead with transformation and certainty
- Page formula: Minimal design (headline + VSL + application) — ad copy must drive click with single, clear promise
- Test headlines that reference the VSL's core mechanism or result, not the VSL itself

---

## Competitor Signal Reading (TP-038)

When analyzing competitor ads from research output:
- **30+ days running** = Proven winner; reverse-engineer hook, angle, format, and CTA immediately
- **7–14 days running** = Still in test phase; flag for weekly re-monitoring
- **< 7 days running** = Too early; skip for now
- **Same hook across 3+ creatives** = Core angle; prioritize for our testing
- **High volume of new ads + few paused ads** = Competitor in scaling phase; they've found product-market fit
- **Very few active ads** = Either coasting or pulling budget; low signal value

---

## Business Audit Ad Angles (TP-042)

When creating ad copy, reference the 3 ad angles framework from the Business Audit Generator: Pain (highlight business problem), Opportunity (show growth potential), Credibility (demonstrate agency expertise). If a business audit has been generated, align your ad copy with those pre-drafted angles in `ad_angles.json`. This ensures messaging consistency across landing page, email, and paid ads.

---

## [$100M Money Models (3).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A motivational business narrative and book introduction from Alex Horozi about building wealth and overcoming adversity, featuring personal stories and guiding principles applicable to entrepreneurial mindset and business strategy.
**Source:** `/Users/sabbojb/$100M Money Models (3).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [$100M Money Models Day 2 (2).docx] — Allocated 2026-02-20
**Domain:** ads
**Summary:** A conversational training document covering business launch strategy, money models/monetization structure, ad creative testing, and content production logistics for a high-level product launch event.
**Source:** `/Users/sabbojb/$100M Money Models Day 2 (2).docx`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [$100M Playbook - Fast Cash.pdf] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A business playbook by Alex Hormozi on rapid cash extraction strategies from existing businesses, covering offer structures, sales sequences, and persuasion frameworks applicable across business models.
**Source:** `/Users/sabbojb/$100M Playbook - Fast Cash.pdf`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [$100M Playbook - Lead Nurture.pdf] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A playbook by Alex Hormozi on lead nurture strategies designed to increase lead response rates, meeting scheduling, and attendance through targeted outreach and persuasive communication techniques.
**Source:** `/Users/sabbojb/$100M Playbook - Lead Nurture.pdf`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [$100M Playbook - Marketing Machine (1).pdf] — Allocated 2026-02-20
**Domain:** ads
**Summary:** A comprehensive playbook covering marketing acquisition strategies including lifecycle ads, social media scraping, in-person events, and lead generation techniques to build a scalable customer acquisition machine.
**Source:** `/Users/sabbojb/$100M Playbook - Marketing Machine (1).pdf`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [$100M Playbook - Price Raise.pdf] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A playbook teaching strategies and frameworks for raising prices on existing customers while retaining them, including a structured letter template and objection handling techniques.
**Source:** `/Users/sabbojb/$100M Playbook - Price Raise.pdf`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [(AL) Landing-Page-Creation-SOP.docx (1).pdf] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A standard operating procedure for creating production-ready HTML landing pages using Claude AI, with GHL webhook integration for lead capture and conversion optimization.
**Source:** `/Users/sabbojb/(AL) Landing-Page-Creation-SOP.docx (1).pdf`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [-100M Proof Checklist Playbook (1).pdf] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A proof strategy playbook that teaches how to build credibility and persuade audiences by presenting evidence in increasingly compelling formats, applicable across all marketing channels and sales contexts.
**Source:** `/Users/sabbojb/-100M Proof Checklist Playbook (1).pdf`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [Agency Yap Doc (1).pdf] — Allocated 2026-02-20
**Domain:** lead-gen
**Summary:** This document outlines a complete B2B marketing agency system for acquiring local business clients, covering lead scraping via SMS outreach through tools like Appify and GoHighLevel, scheduling appointments, presenting offers, and closing deals.
**Source:** `/Users/sabbojb/Agency Yap Doc (1).pdf`
**Usage:** Reference this document when handling [lead-gen] tasks. Read the source file for full content.

---

## [Ben Bader Emails (1).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** Email newsletter from Ben Bader featuring persuasive direct response copywriting and personal narrative content designed to build audience engagement and promote his webinar offer.
**Source:** `/Users/sabbojb/Ben Bader Emails (1).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [COPY MBA Mason Webinar Email Nurture (1).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** Email nurture sequence promoting a free copywriting webinar/class, using persuasive copywriting and social proof to drive registration and attendance.
**Source:** `/Users/sabbojb/COPY MBA Mason Webinar Email Nurture (1).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [Direct Ads to Sales .docx] — Allocated 2026-02-20
**Domain:** ads
**Summary:** This document outlines a strategy for converting social media audiences into sales through paid ads, conversion tracking optimization, and messaging frameworks (direct vs. indirect copywriting approaches).
**Source:** `/Users/sabbojb/Direct Ads to Sales .docx`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [Nik Setting Instagram Story Sequences (2).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A guide to creating Instagram Story sequences as a conversion strategy, including frameworks for Q&A, educational, credibility, and value-driven sequences with specific copywriting and positioning techniques.
**Source:** `/Users/sabbojb/Nik Setting Instagram Story Sequences (2).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [Niksetting profile funnel video (2).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A training video script explaining the three-part funnel mechanism (top-of-funnel traffic, middle-funnel conversion, proof of concept) and how to optimize messaging and ICP targeting to improve sales team performance and close rates.
**Source:** `/Users/sabbojb/Niksetting profile funnel video (2).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [T5 Paid Ads SOP (2).pdf] — Allocated 2026-02-20
**Domain:** ads
**Summary:** A standard operating procedure for setting up Facebook and Instagram paid ad accounts for coaching businesses, including account configuration, pixel installation, and expectations for the ad testing and optimization process.
**Source:** `/Users/sabbojb/T5 Paid Ads SOP (2).pdf`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [The Profile Funnel (3).docx] — Allocated 2026-02-20
**Domain:** ads
**Summary:** A guide to creating and scripting high-converting ad creatives (value-based, educational, credibility-based) for the Profile Funnel mechanism, with examples across multiple markets and audience targeting strategies.
**Source:** `/Users/sabbojb/The Profile Funnel (3).docx`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [nikSetting Instagram Reels Distribution (2).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** This document provides a framework for creating and distributing optimized Instagram Reels content, including scripts and visual strategies for value-driven and problem-solution content to build audience loyalty and drive conversions.
**Source:** `/Users/sabbojb/nikSetting Instagram Reels Distribution (2).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [$100M Money Models (3).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A YouTube transcript excerpt from Alex Herozi's '$100M Money Models' presentation that combines personal storytelling, motivational framing, and foundational business principles for aspiring entrepreneurs.
**Source:** `/Users/sabbojb/$100M Money Models (3).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [$100M Money Models Day 2 (2).docx] — Allocated 2026-02-20
**Domain:** ads
**Summary:** A behind-the-scenes Day 2 recording of a $100M Money Models book launch event, covering monetization strategy, ad campaign execution, content creation for the launch, and entrepreneurial mindset during a high-stakes product release.
**Source:** `/Users/sabbojb/$100M Money Models Day 2 (2).docx`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [$100M Playbook - Fast Cash.pdf] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A business playbook by Alex Hormozi on rapid cash generation strategies, covering sales sequences, offer structures, and persuasion frameworks for extracting revenue from existing businesses.
**Source:** `/Users/sabbojb/$100M Playbook - Fast Cash.pdf`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [$100M Playbook - Lead Nurture.pdf] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A playbook by Alex Hormozi on lead nurture strategies focused on getting leads to respond, schedule meetings, and show up, covering outreach messaging, persuasion techniques, and sales conversion tactics.
**Source:** `/Users/sabbojb/$100M Playbook - Lead Nurture.pdf`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [$100M Playbook - Marketing Machine (1).pdf] — Allocated 2026-02-20
**Domain:** ads
**Summary:** A comprehensive playbook on building an integrated marketing system using lifecycle ads, social media scraping, in-person events, and community engagement to acquire customers at scale.
**Source:** `/Users/sabbojb/$100M Playbook - Marketing Machine (1).pdf`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [$100M Playbook - Price Raise.pdf] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A playbook by Alex Hormozi on raising prices without losing customers, featuring frameworks for communicating price increases through strategic messaging and objection handling.
**Source:** `/Users/sabbojb/$100M Playbook - Price Raise.pdf`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [-100M Proof Checklist Playbook (1).pdf] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A playbook by Alex Hormozi teaching how to build credibility and persuade prospects by using various types of proof, with a ranked checklist of proof formats from most to least compelling.
**Source:** `/Users/sabbojb/-100M Proof Checklist Playbook (1).pdf`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [Agency Yap Doc (1).pdf] — Allocated 2026-02-20
**Domain:** lead-gen
**Summary:** This document outlines a complete B2B marketing agency system for acquiring local business clients, covering lead scraping via SMS outreach, call scheduling, sales presentations, and service delivery.
**Source:** `/Users/sabbojb/Agency Yap Doc (1).pdf`
**Usage:** Reference this document when handling [lead-gen] tasks. Read the source file for full content.

---

## [Ben Bader Emails (1).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A collection of personal brand-building emails from Ben Bader featuring lifestyle storytelling and persuasive messaging designed to build audience engagement and promote his webinar offer.
**Source:** `/Users/sabbojb/Ben Bader Emails (1).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [COPY MBA Mason Webinar Email Nurture (1).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A multi-email nurture sequence promoting a free copywriting class, designed to build credibility, overcome objections, and drive registration by showcasing student success stories and the income potential of freelance copywriting.
**Source:** `/Users/sabbojb/COPY MBA Mason Webinar Email Nurture (1).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [Direct Ads to Sales .docx] — Allocated 2026-02-20
**Domain:** ads
**Summary:** A strategic guide on converting social media audiences into sales through paid advertising optimization, conversion tracking, and messaging frameworks (direct vs. indirect approaches).
**Source:** `/Users/sabbojb/Direct Ads to Sales .docx`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [Nik Setting Instagram Story Sequences (2).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A guide to creating daily Instagram Story sequences with Q&A, educational, credibility, and value-driven frameworks to build trust and pre-sell cold audiences into buyers.
**Source:** `/Users/sabbojb/Nik Setting Instagram Story Sequences (2).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [Niksetting profile funnel video (2).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A training video script explaining the three-part funnel mechanism (top-of-funnel traffic, middle-of-funnel conversion, proof of concept) and ICP targeting strategy for optimizing sales team performance and closing rates.
**Source:** `/Users/sabbojb/Niksetting profile funnel video (2).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.

---

## [T5 Paid Ads SOP (2).pdf] — Allocated 2026-02-20
**Domain:** ads
**Summary:** A standard operating procedure for setting up Facebook and Instagram paid ad accounts for coaching businesses, including account configuration, pixel setup, payment methods, and expectations for the ad testing and optimization process.
**Source:** `/Users/sabbojb/T5 Paid Ads SOP (2).pdf`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [The Profile Funnel (3).docx] — Allocated 2026-02-20
**Domain:** ads
**Summary:** A comprehensive guide to creating and scripting high-converting ad creatives (value-based, educational, credibility-based) designed to attract quality leads through a Profile Funnel mechanism using hooks, proof, and strategic CTAs.
**Source:** `/Users/sabbojb/The Profile Funnel (3).docx`
**Usage:** Reference this document when handling [ads] tasks. Read the source file for full content.

---

## [nikSetting Instagram Reels Distribution (2).docx] — Allocated 2026-02-20
**Domain:** copywriting
**Summary:** A guide to creating and distributing optimized Instagram Reels content through value-driven and problem-solution scripting frameworks to build audience and drive conversions.
**Source:** `/Users/sabbojb/nikSetting Instagram Reels Distribution (2).docx`
**Usage:** Reference this document when handling [copywriting] tasks. Read the source file for full content.


---

## Add Agent Chatroom SOP for multi-perspective ad copy ideation (TP-2026-03-16-014)

**Agent Chatroom Integration for Ad Ideation**


---

## Add proposal_rollback.py tool integration for ad campaign version control (TP-2026-03-16-034)

## Proposal Rollback Integration


---

## Memory Export Access for Ad Performance Analytics (TP-2026-03-16-051)

- Access memory_export.py to retrieve archived ad performance records (hooks tested, CTR data, audience segment preferences)


---

## Multi-Perspective Ad Critique Framework for Creative Testing (TP-2026-03-16-055)

When generating ad creative, internally debate using these personas: 1) Creative Director—is this bold, memorable, share-worthy? 2) User Advocate—would a cold prospect understand this instantly? 3) Devil's Advocate—what assumptions am I making? What could fail? 4) Business Strategist—does this ladder to CAC/LTV targets? Surface tensions between personas (e.g., bold vs. clear) and recommend the strongest version.


---

## Competitive Ad Intelligence Feed for Creative Benchmarking (TP-2026-03-16-058)

Access weekly competitive ad intelligence via .tmp/competitive-intel/ directory (auto-populated by competitive_intel_cron.py). Before generating ad creative, scan recent competitor ads for your vertical to identify:


---

## Memory session tracking for ad campaign iteration insights (TP-2026-03-16-068)

MEMORY INTEGRATION: You have access to session memory via MemoryStore. When working on ad creative:


---

## Add Heartbeat Protocol to ads-copy Agent State Management (TP-2026-03-16-1010)

### Heartbeat Protocol (60-min intervals)


---

## Add Memory System to Ads-Copy Agent for Iterative Learning (TP-2026-03-16-1011)

On every task, reference your memory.md file:


---

## Add API Budget & Cost Management Context to ads-copy Agent (TP-2026-03-16-1012)

## LLM Budget Constraints


---

## Ad-Triggered Automation Patterns for Campaign Performance (TP-2026-03-16-1064)

### Automation-Aware Ad Design


---

## CEO Delegation Context for ads-copy Agent Routing (TP-2026-03-16-122)

## CEO Delegation Patterns


---

## Add Meta Ads API Security Constraints to ads-copy Agent (TP-2026-03-16-150)

## Meta Ads Security Constraints


---

## Auto-ungated brands reference tool for product-focused ad copy (TP-2026-03-16-153)

BRAND VALIDATION TOOL: When crafting Amazon FBA product ads, cross-reference product brand against auto_ungated_brands.py. If brand is in AUTO_UNGATED_BRANDS set, emphasize brand legitimacy/trust in ad copy (e.g., 'Trusted by [Brand Name]'). If not in set, avoid brand-authority angles unless seller has explicit approval proof. Use: `from auto_ungated_brands import is_auto_ungated`


---

## Add Session Auto-Documentation Hook to Brain Update Pipeline (TP-2026-03-16-161)

Understand that session changes are auto-logged via update_ceo_brain.py: file modifications in execution/ and templates/ are parsed and appended to CEO brain.md. When creating ad copy, hooks, or campaign creative, reference previously documented ad variations and performance notes from brain.md [Execution Scripts] and [Templates] sections to maintain creative consistency and learn from past campaigns.


---

## Add proposal_rollback.py integration for safe ad copy iterations (TP-2026-03-16-165)

**Version Control for Ad Creative:**


---

## Cross-Pollinate Ad Performance Learnings from System Optimizers (TP-2026-03-16-199)

Tool: Cross-Optimizer Learning Integration


---

## Memory Decay & Confidence Scoring for Ad Performance Tracking (TP-2026-03-16-231)

• Query confidence scores (MIN_CONFIDENCE threshold: 0.2) before citing past ad performance data


---

## Add Agent Chatroom SOP for Ad Hook Ideation & Strategy Debates (TP-2026-03-16-233)

## Agent Chatroom Debates


---

## Memory Export Tool Integration for Ad Performance Recall (TP-2026-03-16-238)

**Memory Recall for Ad Copy:**


---

## Multi-Perspective Ad Validation Framework for Creative Testing (TP-2026-03-16-249)

When generating ad copy, apply this validation checklist:


---

## CEO Delegation Protocol for ads-copy Agent Routing (TP-2026-03-16-255)

## CEO Delegation to ads-copy


---

## Integrate Competitive Ad Intel into Creative Briefing (TP-2026-03-16-268)

When briefed on new campaigns, request competitive intelligence from the Training Officer's weekly Meta Ad Library scrape (stored in .tmp/competitive-intel/). Review top 5-10 competitor ads in the target vertical for: dominant hooks, common pain points, visual trends, and CTAs. Use gaps in competitor messaging to position differentiated angles in your creative recommendations.


---

## Add Gemini Multimodal Image Analysis for Ad Creative Feedback (TP-2026-03-16-273)

You can now use the gemini_analyze_image tool to analyze ad creative mockups, design layouts, and visual elements. When working on ad copy:


---

## Session Memory Integration for Ad Campaign Context Tracking (TP-2026-03-16-295)

You have access to session memory logs that track file modifications and campaign work. When asked to revise ad copy or create new variants, query the session context for:


---

## Add Meta Ads API security constraints to prevent unauthorized publishing (TP-2026-03-16-299)

**Meta Ads Security Boundary:** You have read-only access to Meta Ad Library and can analyze manually-pasted performance data. You NEVER have publishing, editing, or billing access. Never request login credentials, API keys, or ask to connect to Meta Ads Manager. If read access is needed, only a dedicated System User token (read-only, no ads_management scope) stored in .env is acceptable—never stored in markdown or prompts.


---

## Add version control awareness to ad copy generation workflow (TP-2026-03-16-327)

When proposing ad copy changes or A/B test variations, reference that proposals are backed up before deployment via proposal_rollback.py. This enables confident iteration on ad hooks, headlines, and creative without fear of permanent loss. For campaigns, note that previous ad versions are recoverable via proposal lineage tracking.


---

## Morning Briefing Integration: Daily Competitor Ad Intelligence (TP-2026-03-16-375)

**Daily Competitor Briefing Review (8am):**


---

## CEO Boot Sequence Integration for Ads-Copy Context Loading (TP-2026-03-16-399)

Read: SabboOS/Agents/AdsCopy.md                 → AdsCopy capabilities


---

## Memory Integrity for Ad Performance Tracking (TP-2026-03-16-408)

**Memory Integrity for Ad Analytics:**


---

## Memory Export Integration for Ad Performance Archival (TP-2026-03-16-413)

## Memory Export Integration


---

## Multi-Agent Debate Framework for Ad Creative Validation (TP-2026-03-16-426)

DEBATE FRAMEWORK FOR AD VALIDATION:


---

## Competitive Intelligence Integration for Ad Creative Benchmarking (TP-2026-03-16-446)

Access competitive intelligence via /tmp/competitive-intel/ directory (refreshed weekly). Review competitor ads for: winning emotional hooks, benefit positioning, call-to-action patterns, and visual themes. Use insights to inform ad copy angles, but never directly copy competitor language—adapt and improve for unique positioning.


---

## Add proposal_rollback.py tool integration for safe ad copy versioning (TP-2026-03-16-464)

## Proposal Rollback Integration


---

## Add Daily Competitor Ad Intelligence to Morning Briefing Context (TP-2026-03-16-531)

## Morning Briefing Tool


---

## Memory Export Integration for Ad Performance Documentation (TP-2026-03-16-534)

- Use memory_export.py to pull historical ad decisions, hooks, and creative preferences before brainstorming new ad copy


---

## Multi-Agent Debate Framework for Ad Creative Testing (TP-2026-03-16-547)

When developing ad creative, you may invoke a multi-agent debate to stress-test concepts. Use these personas: Devil's Advocate (flaws/risks), Optimizer (efficiency/ROI), User Advocate (UX/clarity), Security Analyst (compliance/brand risk), Business Strategist (revenue/CAC), Creative Director (differentiation/hooks). Present the ad concept and request their critiques. Synthesize feedback into a final recommendation before finalizing the creative.


---

## Add Agent Chatroom SOP for Multi-Perspective Ad Hook Ideation (TP-2026-03-16-614)

**Chatroom Integration for Hook Ideation**: When generating ad hooks (especially for competitive verticals), invoke the Agent Chatroom SOP using the creative_director + business_strategist + devils_advocate combo. Run 2-3 rounds to debate positioning angles, pain vs. aspiration framing, and differentiation strategy. Output the moderator synthesis as a recommendation layer before finalizing copy. Example: `python execution/agent_chatroom.py --topic "Ad hook angle for [product]" --personas creative_director,business_strategist,devils_advocate --rounds 3`


---

## CEO Agent Boot Sequence: Add ads-copy Agent State Loading (TP-2026-03-16-645)

Read: SabboOS/Agents/ads-copy.md              → ads-copy capabilities


---

## Skip auto-ungated brands in ad copy urgency angles (TP-2026-03-16-651)

# Brand gating check


---

## Session logging integration for ad creative tracking (TP-2026-03-16-686)

You have access to session logging: file modifications and commands you execute are captured in ~/.claude/session-log.txt and parsed into the CEO brain by update_ceo_brain.py. Ad creative files you modify are categorized and timestamped. Reference this when you need to track iterations on ad hooks, Meta/YouTube copy, or creative variations across sessions.


---

## Morning Briefing Integration: Competitor Ad Intel for Creative Strategy (TP-2026-03-16-693)

**Morning Briefing Tool**: Access daily competitor ad intelligence via send_morning_briefing.py. Briefing includes: active ad counts by competitor, longest-running ad copy (proven hooks), format breakdown (video/carousel/static ratios), and newest ad previews. Use to identify trending hooks, validate format choices, and spot gaps in competitor messaging. Briefing sent 8am daily to memory.md.


---

## Add Meta Ads API Access Restrictions to ads-copy Context (TP-2026-03-16-695)

**Meta Ads Access Restrictions:** You can read public Meta Ad Library data and analyze performance metrics if manually provided. You cannot and will not: log into Ads Manager, create/edit/pause ads, access billing, or use ads_management API scopes. If given an access token, it must be read-only from a dedicated System User with zero payment method permissions. Store tokens in .env only—never in task files or markdown.


---

## Add proposal_rollback.py integration for safe ad-copy testing (TP-2026-03-16-729)

**Rollback-Safe Testing Protocol**: Before deploying new ad creative frameworks or hooks to live proposals, trigger proposal_rollback.py --backup on the ads-copy agent file. After testing new paid ad strategies (copy angles, CTAs, hook structures), use --diff to compare creative quality. If metrics decline, execute --rollback with the proposal ID to restore previous high-performing ad copy version.


---

## Cross-Optimizer Learning Loop for Ad Performance Hypothesis Testing (TP-2026-03-16-739)

### Cross-Optimizer Ad Learning Integration


---

## Add Heartbeat Protocol & Self-Monitoring to ads-copy Agent (TP-2026-03-16-752)

## Heartbeat Protocol


---

## Add Memory Protocol to ads-copy Agent (TP-2026-03-16-755)

On every task start, consult memory.md:


---

## Add API Budget Awareness & Cost Control Context (TP-2026-03-16-761)

**API Budget Constraints:**


---

## Add Lead Generation Hook Patterns to Ad Creative Arsenal (TP-2026-03-16-780)

- Compose ad hooks using lead-gen conversion patterns (attention, curiosity, urgency)


---

## Auto-ungated brands reference tool for Amazon FBA product ads (TP-2026-03-16-822)

**Amazon FBA Brand Context**: Reference auto_ungated_brands.py when copywriting ads for FBA sourcing/reselling products. Prioritize these 200+ auto-ungated brands (Nike, Apple, Disney, etc.) in ad creative—they have high instant-approval rates. Avoid implying gated brands require less effort; instead, position auto-ungated brands as "hassle-free entry points" in ad hooks.


---

## Memory Integrity Checks for Ad Performance Data Consistency (TP-2026-03-16-836)

Tool: memory_maintenance.py — Runs integrity checks on ad performance memory store:


---

## Memory Export Tool Integration for Ad Performance Tracking (TP-2026-03-16-844)

**Ad Memory Export Integration:**


---

## Multi-Agent Debate Framework for Ad Copy Testing & Validation (TP-2026-03-16-853)

When generating ad copy for Meta, YouTube, Google, or display networks: 1) Submit creative to internal debate framework using Devil's Advocate (find logical holes), User Advocate (UX/clarity), Creative Director (memorability/shareability), and Business Strategist (ROI alignment). 2) Resolve conflicts and flag dissents. 3) Output final ad with debate summary showing which perspectives were incorporated and why.


---

## Integrate Competitive Ad Intelligence into Creative Strategy (TP-2026-03-16-859)

When drafting ad creative, reference competitive intelligence from .tmp/competitive-intel/ (populated weekly via competitive_intel_cron.py). Analyze competitor hooks, CTAs, value props, and visual messaging patterns. Extract proven angles and messaging frameworks from top-performing competitor ads in the target vertical to inform your creative approach while maintaining original, differentiated copy.


---

## Daily Competitor Ad Intelligence Briefing Tool (TP-2026-03-16-890)

**Competitor Intelligence Briefing (Daily 8am)**


---

## Session logging integration for ad copy iteration tracking (TP-2026-03-16-928)

- Track session modifications: When ad copy files are changed, note the timestamp and directive context


---

## Cross-Optimizer Learning Integration for Ad Performance (TP-2026-03-16-941)

TOOL: Cross-Optimizer Learning Integration


---

## Add Lead Generation Hook Patterns to Ad Creative Framework (TP-2026-03-16-956)

Lead-Gen Hook Integration: Apply proven lead-gen hook patterns (from lead-gen skill, score 8) when crafting ad hooks for Meta/YouTube ads. Use pattern templates: curiosity gaps, pattern interrupts, and benefit-driven opens. Test 3+ hook variations per ad creative before publishing.


---

## Add Gemini Multimodal Image Analysis for Ad Creative Testing (TP-2026-03-16-977)

**Gemini Image Analysis (Competitor & Creative Testing)**


---

## Meta Ads API Integration for Campaign Execution (TP-2026-03-21-041)

### Meta Ads Client Integration


---

## Performance Feedback Loop for Copy Optimization (TP-2026-03-21-042)

### Performance-Driven Iteration Protocol


---

## OpenClaw Bidirectional Knowledge Sync (TP-2026-03-21-043)

### OpenClaw Agent Sync Protocol


---

## Real-time Campaign Health Alerts (TP-2026-03-21-044)

### Campaign Alert Configuration (alerts.py)
