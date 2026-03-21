# Client Onboarding Pipeline — Single-Shot Directive
> directives/client-onboarding-pipeline.md | Version 1.0

---

## Purpose

One prompt, one client name + social handles → full deliverable stack ready for QC in 15-20 minutes. This is the highest-leverage directive in the system. Modeled after Kabrin's live demo (Feb 5 + Feb 19 calls).

---

## Goal

Produce every deliverable needed to launch a client's growth engine from a single initiation prompt. Sabbo's only job after this runs: quality control.

---

## Inputs (Minimum Required)

| Input | Required? | Description |
|---|---|---|
| Client name | Yes | Business or personal name |
| Instagram handle | Yes | Primary social presence |
| Website URL | Preferred | If available |
| YouTube channel | If exists | For brand voice extraction |
| Offer description | If known | What they sell, price point |
| Competitors | If known | 3-5 competitor names/URLs |

**Minimum viable input:** Client name + Instagram handle. Everything else can be researched.

---

## Phase Gates (STRICT — NO SKIPPING)

Each phase MUST complete before the next begins. No parallel execution across phases.

### PHASE 1: Deep Research
**Must complete before Phase 2 begins.**

1. **Social scraping** — Instagram posts, stories highlights, bio, link tree. YouTube videos (download transcripts of last 10-20 videos). X/Twitter if exists.
2. **Website analysis** — Current offer, funnel type, CTA, social proof, brand colors, logo
3. **Competitor analysis** — Identify 5 competitors if not provided. Scrape their: ads (Meta Ad Library), landing pages, offer structure, pricing, positioning
4. **Market research** — Reddit, Facebook groups, YouTube comments, Amazon reviews (if applicable). Extract: pain points, objections, dream outcomes, language patterns
5. **Voice of Customer** — Real quotes from forums/reviews that show how the ICP talks about their problems

**Output:** `clients/{client_name}/research/`
- `market_dossier.md` — full research synthesis
- `competitor_analysis.md` — competitor breakdown
- `voice_of_customer.md` — real quotes + language patterns

**Quality gate:** Research must contain at least 5 specific pain points, 3 competitor analyses, and 10+ real customer quotes before proceeding.

---

### PHASE 2: Brand Voice + Strategy
**Must complete before Phase 3 begins. Uses Phase 1 outputs.**

1. **Brand voice profile** — How the client speaks (tonality, vocabulary, sentence structure, energy level). Built from video transcripts + written content.
2. **Avatar research** — Detailed ICP profile based on the client's audience (demographics, psychographics, buying triggers, objections)
3. **Offer creation/refinement** — Based on research, define or refine: core offer, price point, unique mechanism, guarantee, bonuses
4. **Campaign angles** — 5-10 angles ranked by strength, each tied to a specific pain point or desire from research
5. **Ad strategy** — Audience segments (cold/warm/retargeting), budget allocation suggestion, platform recommendation

**Output:** `clients/{client_name}/strategy/`
- `brand_voice.md` — voice profile
- `avatar.md` — ICP profile
- `offer.md` — offer structure + unique mechanism
- `campaign_angles.md` — ranked angles with rationale
- `ad_strategy.md` — audience segments + approach

**Quality gate:** Brand voice must include 5+ example phrases in the client's voice. Offer must have a clear unique mechanism. At least 5 angles with supporting research.

---

### PHASE 3: Core Asset Production
**Must complete before Phase 4 begins. Uses Phase 1 + Phase 2 outputs.**

All assets written in the client's brand voice using the campaign angles from Phase 2.

1. **VSL script** — Full video sales letter following Jeremy Haynes method (see `directives/jeremy-haynes-vsl-sop.md`):
   - Summary section (0:00-1:30)
   - Hook/opener
   - Credibility
   - Buying motives
   - The offer (state price)
   - Objection handling
   - Qualification
   - CTA

2. **Email flows** — All sequences:
   - Pre-call nurture (3-5 emails)
   - Post-call follow-up (3 emails)
   - No-show recovery (2 emails)
   - Welcome/onboarding (3 emails)

3. **Ad scripts** — Per ad strategy:
   - 5x Meta ad scripts (cold traffic)
   - 3x Meta ad scripts (retargeting)
   - 2x YouTube pre-roll scripts
   - Static ad copy variants (5 headline + body combos)

4. **Landing page copy** — Full copy for:
   - Main VSL landing page (headline, subhead, VSL embed area, application form)
   - Confirmation/thank-you page (boosts show rates 30-50%)

5. **DM scripts** — For ManyChat or manual outreach:
   - New follower welcome flow
   - Comment responder flow
   - Story reply templates

**Output:** `clients/{client_name}/assets/`
- `vsl_script.md`
- `email_flows.md`
- `ad_scripts.md`
- `landing_page_copy.md`
- `confirmation_page_copy.md`
- `dm_scripts.md`

**Quality gate:** Run banned words check (see bot identity files). VSL must follow all 7 sections of Jeremy Haynes method. Emails must have subject lines. All copy must be in client's voice, not generic.

---

### PHASE 4: Build + Deploy
**Uses Phase 3 outputs.**

1. **Landing page HTML** — Build responsive HTML/CSS landing page from the copy
   - Mobile-optimized
   - Brand colors from research
   - VSL embed placeholder
   - Application form
2. **Confirmation page HTML** — Matching design
3. **Google Drive folder** — Create client folder, upload all deliverables
4. **GitHub deploy** — Push landing page to GitHub Pages (or flag for Vercel deploy)

**Output:** `clients/{client_name}/build/`
- `landing_page.html`
- `confirmation_page.html`
- Google Drive folder link logged in `clients/{client_name}/README.md`

---

## Self-Annealing

After each run:
1. Log what worked well and what needed manual correction
2. If a phase produced weak output, note the specific gap
3. Update this directive with the fix so it doesn't recur
4. Track: time per phase, quality score per deliverable, revision rounds needed

---

## Skills Referenced

This directive pulls from these skill sources:
- `bots/ads-copy/skills.md` — VSL, ad scripts, email copy, landing pages
- `bots/content/skills.md` — Brand voice, content strategy
- `bots/outreach/skills.md` — DM scripts, outreach sequences
- `directives/jeremy-haynes-vsl-sop.md` — VSL methodology
- `directives/client-brand-voice-sop.md` — Voice extraction
- `directives/ads-competitor-research-sop.md` — Competitor analysis
- `directives/asset-generation-sop.md` — Ad + VSL generation

---

## Usage

```
Initiate client onboarding for [CLIENT NAME].
Instagram: @[handle]
Website: [url]
YouTube: [channel url]
```

Or minimal:
```
Onboard [CLIENT NAME]. Instagram: @[handle]. Build everything.
```

---

*Client Onboarding Pipeline v1.0 — 2026-03-13*
