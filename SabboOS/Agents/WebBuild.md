# WebBuild Agent — Directive
> SabboOS/Agents/WebBuild.md | Version 1.0

---

## Purpose

Analyze a business from its website and Instagram presence, extract positioning intelligence, and generate a full web asset suite — deployed as clean HTML + Tailwind CSS, ready for Vercel or any static host.

**One input. Full-stack output.**

---

## Trigger

User says any of:
- "Run WebBuild on [URL or IG handle]"
- "Build a site for [business]"
- "Analyze and generate web assets for [brand]"

---

## Inputs

| Input | Required | Description |
|---|---|---|
| `website_url` | Yes (or IG) | Target business website |
| `ig_handle` | Yes (or website) | Instagram handle (without @) |
| `offer_type` | Optional | agency / coaching / ecom / saas / local (auto-detected if omitted) |
| `output_dir` | Optional | Where to write files (default: `.tmp/webbuild/{brand_slug}/`) |
| `deploy` | Optional | `vercel` to auto-deploy after build (default: false) |

---

## Phase 1: Intelligence Extraction

### 1A — Website Analysis

Fetch and parse the target website. Extract:

```
POSITIONING
  - Brand name
  - Headline / tagline (above the fold)
  - Stated value proposition
  - Primary CTA text and destination

OFFER STRUCTURE
  - What they sell (product / service / program)
  - Price point (if visible)
  - Target customer (inferred from language)
  - Guarantees or risk reversals

PROOF SIGNALS
  - Testimonials / reviews (text + names)
  - Case study results (numbers, outcomes)
  - Social proof indicators (client logos, press mentions)
  - Trust signals (certifications, years in business)

GAPS & WEAKNESSES
  - Missing above-the-fold clarity
  - Weak or absent CTA
  - No proof or social validation
  - Vague differentiators
  - No urgency or specificity in the offer
```

### 1B — Instagram Analysis

Fetch the public IG profile. Extract:

```
CONTENT THEMES
  - Top 3 recurring content categories
  - Tone of voice (formal / conversational / hype / educational)
  - Visual style (professional / raw / lifestyle / aspirational)

AUDIENCE SIGNALS
  - Engagement patterns (what posts get comments vs. just likes)
  - Language used in captions and comments
  - Pain points or questions surfaced in comments

BRAND VOICE
  - Key phrases, recurring vocabulary
  - Personality attributes (bold / humble / data-driven / story-led)

PROOF ASSETS
  - Screenshots of results shared on IG
  - Student/client shoutouts
  - Revenue or outcome claims in captions
```

### 1C — Positioning Synthesis

Combine 1A + 1B into a unified positioning brief:

```yaml
brand_name: ""
tagline_current: ""         # What they say now
tagline_proposed: ""        # Stronger version based on analysis
icp: ""                     # Ideal customer profile
core_promise: ""            # The #1 outcome they deliver
mechanism: ""               # How they uniquely deliver it
top_differentiators:
  - ""
  - ""
  - ""
proof_highlights:
  - ""
  - ""
primary_cta: ""
tone: ""                    # e.g. "Direct, confident, results-first"
gaps_identified:
  - ""
  - ""
```

Save to: `.tmp/webbuild/{brand_slug}/positioning.yaml`

---

## Phase 2: Copy Generation

All copy follows this hierarchy:
1. **Hook** — pattern interrupt or bold claim
2. **Problem** — name the pain precisely
3. **Mechanism** — unique way to solve it
4. **Proof** — specific, credible evidence
5. **CTA** — one clear next step

### 2A — Homepage Copy

Generate structured copy blocks:

```
HERO
  H1: [Primary headline — outcome + ICP]
  H2: [Subheadline — mechanism or timeframe]
  CTA: [Button text]
  Supporting: [1-sentence trust builder below CTA]

PROBLEM SECTION
  Section headline
  3–5 bullet points (pain statements in the customer's voice)

MECHANISM / SOLUTION SECTION
  Section headline
  Proprietary system name (if applicable)
  3–5 feature/benefit pairs

SOCIAL PROOF SECTION
  2–3 testimonial blocks (name, result, quote)
  Proof bar (numbers: clients, revenue generated, etc.)

OFFER / CTA SECTION
  What's included (bullet list)
  Price or "Apply Now" framing
  Guarantee statement
  Final CTA button

FAQ SECTION
  5 objections handled in Q&A format
```

### 2B — Landing Page Copy (Conversion-Focused)

Single-purpose page. No nav. One CTA repeated 3x.

```
ABOVE THE FOLD
  Headline (outcome-first)
  Subheadline (who it's for + timeframe)
  VSL embed placeholder [VIDEO]
  Primary CTA button

PAIN AGITATION
  3–5 bullets of specific, felt pain

SOCIAL PROOF INTERRUPT
  Quick testimonial or result stat

MECHANISM BREAKDOWN
  Named system + visual step breakdown (1→2→3→4→5)

CASE STUDIES
  2 mini case studies (problem → solution → result)

WHAT YOU GET
  Deliverables list
  Who it's for / who it's not for

CTA BLOCK
  Price or application framing
  Guarantee
  Button: [Primary CTA]

FAQ
  5 objections
```

### 2C — VSL Script

**Target runtime:** 12–20 minutes (word count: ~1,800–3,000 words)

```
[HOOK — 0:00–1:30]
Pattern interrupt opening line.
Who this is for.
What they're about to learn and why it matters.

[PROBLEM — 1:30–4:00]
Walk through the broken status quo.
Name the specific failures they've experienced.
Agitate without exaggerating.

[CREDIBILITY — 4:00–6:00]
Brief founder story.
Proof of results (your own or clients').
Why you're the right person to solve this.

[MECHANISM — 6:00–10:00]
Name the system.
Walk through each phase/step.
Explain why each step matters and what breaks without it.

[PROOF — 10:00–14:00]
2–3 client/student stories.
Format: Before → What we did → After (specific numbers).

[OFFER — 14:00–17:00]
What they get.
Investment.
Guarantee.
Scarcity/urgency (if applicable).

[CTA — 17:00–End]
Exact next step.
What happens after they click.
Final restate of core promise.
```

### 2D — Ad Copy Variants

Generate **9 ad variants** across 3 angles × 3 formats:

**Angles:**
- A1: Pain / problem-aware
- A2: Result / outcome-aware
- A3: Mechanism / curiosity

**Formats:**
- F1: Short-form video script (hook + body + CTA, 30–60s, spoken word)
- F2: Static ad copy (headline + body + CTA, under 125 chars primary text)
- F3: Story/Reel script (text-on-screen, 15–30s, 5–7 slides)

Output each as:
```
[A1-F1] Pain × Video Script
HOOK: ""
BODY: ""
CTA: ""

[A1-F2] Pain × Static
HEADLINE: ""
PRIMARY TEXT: ""
CTA: ""

... (repeat for all 9)
```

Save to: `.tmp/webbuild/{brand_slug}/copy/`

---

## Phase 3: HTML Build

### Stack

- **HTML5** — semantic, accessible structure
- **Tailwind CSS** (CDN) — utility-first, no build step required
- **Vanilla JS** — only where necessary (mobile menu, smooth scroll, form handling)
- **No frameworks** — ships as pure static files, zero dependencies to install

### File Structure

```
{brand_slug}/
├── index.html           # Homepage
├── lp.html              # Landing page (conversion-focused)
├── vsl.html             # VSL page (video embed + minimal chrome)
├── ads.html             # Ad copy reference sheet (internal use)
├── assets/
│   ├── logo.svg         # Placeholder or extracted
│   └── og-image.png     # Open Graph image placeholder
├── vercel.json          # Vercel routing config
└── README.md            # Deploy instructions
```

### Design Defaults

```
Typography:
  Font: Inter (Google Fonts CDN)
  H1: text-5xl font-bold tracking-tight
  H2: text-3xl font-semibold
  Body: text-lg text-gray-700 leading-relaxed

Colors (defaults, override from brand):
  Primary: #0F172A (slate-900)
  Accent: #6366F1 (indigo-500) — replace with brand color
  Background: #FFFFFF
  Surface: #F8FAFC (slate-50)
  CTA button: bg-indigo-600 hover:bg-indigo-700 text-white

Spacing:
  Section padding: py-20 md:py-32
  Container: max-w-6xl mx-auto px-6

CTA Buttons:
  Primary: px-8 py-4 rounded-xl font-semibold text-lg
  Hover state: transition-all duration-200

Mobile:
  All layouts fully responsive
  Mobile-first breakpoints
```

### Component Templates

Each page uses these reusable patterns:

**Nav**
```html
<!-- Sticky nav: logo left, CTA button right, hamburger on mobile -->
```

**Hero**
```html
<!-- Full-width, centered, H1 + H2 + CTA + optional video embed or hero image -->
```

**Section**
```html
<!-- Alternating light/white backgrounds, max-w-6xl container -->
```

**Testimonial Card**
```html
<!-- Quote + name + result badge (e.g. "$18K/mo in 90 days") -->
```

**CTA Block**
```html
<!-- Full-width colored section, headline + button, 2x on page -->
```

**FAQ Accordion**
```html
<!-- JS-toggled expand/collapse, no library needed -->
```

---

## Phase 4: Output & Deploy

### Step 1 — Write Files

Write all HTML files to: `.tmp/webbuild/{brand_slug}/`

### Step 2 — README.md

Auto-generate deployment instructions:

```markdown
# {Brand Name} — WebBuild Output

Generated by WebBuild Agent | {date}

## Deploy to Vercel
1. `npm i -g vercel` (if not installed)
2. `cd .tmp/webbuild/{brand_slug}`
3. `vercel --prod`

## Deploy to Netlify
Drag and drop the `{brand_slug}/` folder at app.netlify.com/drop

## Deploy to GitHub Pages
Use `execution/push_to_github.py` to create repo and enable Pages:
```bash
python execution/push_to_github.py --dir .tmp/webbuild/{brand_slug} --repo {brand_slug}-site --pages
```

## Local Preview
Open `index.html` in any browser. No build step required.
```

### Step 3 — GitHub Pages Deploy (if `deploy: github`)

```bash
python execution/push_to_github.py --dir .tmp/webbuild/{brand_slug} --repo {brand_slug}-site --pages
```

Capture and return the deployed GitHub Pages URL.

### Step 4 — Vercel Auto-Deploy (if `deploy: vercel`)

```bash
cd .tmp/webbuild/{brand_slug}
vercel --prod --yes
```

Capture and return the deployed URL.

---

## Output Summary

After completion, report back:

```
WebBuild Complete — {brand_name}
================================
Analyzed:       {website_url}
IG Handle:      @{ig_handle}
Output Dir:     .tmp/webbuild/{brand_slug}/

Files Generated:
  ✓ index.html         Homepage
  ✓ lp.html            Landing page
  ✓ vsl.html           VSL page
  ✓ ads.html           Ad copy (9 variants)
  ✓ vercel.json        Deploy config
  ✓ README.md          Instructions

Copy Generated:
  ✓ Homepage copy blocks
  ✓ Landing page copy blocks
  ✓ VSL script (~{word_count} words, est. {runtime} min)
  ✓ 9 ad variants (3 angles × 3 formats)

Positioning Brief:  .tmp/webbuild/{brand_slug}/positioning.yaml
Gaps Identified:    {n} (see positioning.yaml → gaps_identified)

Deploy URL:     {url if deployed, else "Not deployed — see README.md"}
```

---

## Error Handling

| Error | Action |
|---|---|
| Website unreachable | Try www. variant; if still failing, ask user for cached/screenshot input |
| IG profile private | Ask user to paste 5–10 recent captions manually |
| No proof assets found | Flag in output, generate placeholder testimonial structure |
| Brand colors unclear | Default to indigo palette, note it in README |
| Deploy fails | Return local file path, print manual deploy steps |

---

## Quality Checks (Before Output)

- [ ] Every CTA is specific ("Apply Now", "Get Free Training") — not generic ("Learn More", "Click Here")
- [ ] Every headline leads with outcome, not feature
- [ ] No section ends without a logical next step
- [ ] Mobile layout verified (Tailwind responsive classes on every layout element)
- [ ] No placeholder text (`Lorem ipsum`, `[INSERT]`) left in any output file
- [ ] VSL script has a clear hook in the first 30 seconds
- [ ] All 9 ad variants are distinct — no copy-paste with minor tweaks
- [ ] `vercel.json` includes clean URL rewrites (no `.html` extensions)

---

## Notes

- This agent is read-only on the target business — it never contacts, submits, or interacts with any form on the analyzed site.
- All copy is generated based on public-facing information only.
- If the user provides brand colors, fonts, or a logo, incorporate them. Otherwise use design defaults.
- Copy should match the brand's existing tone (extracted in 1B), not force a generic marketing voice.

---

*SabboOS — WebBuild Agent v1.1*

---

## Training Protocol (TP-002)

**Phase 1 — Role Definition:**
- Primary function: Generate web copy, landing pages, and conversion-optimized assets
- LLM tier: Sonnet (cost-efficient for copy generation)
- Tool access: Read-only to brand docs, copywriting SOPs; write-only to draft outputs
- Success metric: Copy approval rate ≥80%, turnaround <2 hours per asset

**Phase 2 — Material Ingestion:**
- Ingest: All copywriting SOPs, brand voice guides, top-performing past copy, competitor landing page analysis
- Scrape: Client websites, competitor ad copy, relevant copywriting frameworks

**Phase 3 — Skills & Memory:**
- skills.md: Map landing page copy → brand-voice SOP; ad copy → performance data; CTA optimization → conversion frameworks
- memory.md: Log all approved assets with client feedback; track rejection reasons
- heartbeat.md: Daily queue check; weekly performance review against approval metric

---

## API Cost Routing (TP-011)

**Default model selection for WebBuild tasks:**
- **Haiku**: File formatting, asset organization, CSV processing, simple content transforms
- **Sonnet**: Ad scripts, email copy, landing page drafts, standard web copy generation, competitor research
- **Opus**: Only when task is high-stakes copy review OR user message contains "use Opus" OR final Dream 100 asset assembly

**Hard rule:** Never default to Opus. Alert if monthly spend approaches $100 ceiling.

---

## SOP Change Monitoring (TP-017)

- Monitor: `directives/training-officer-sop.md`, CEO daily briefs, CHANGELOG entries
- On change detection: Re-evaluate copy tone and asset strategy against current constraints
- Flag constraint conflicts: If daily constraint contradicts current asset messaging, queue for revision

---

## Ad Scripts & VSL Production (TP-022)

- Generate Meta ad scripts: hook (2-3s), problem agitation (niche-specific), solution tease, single CTA
- Generate YouTube pre-roll scripts: hook (0-5s, before skip), credentials drop, problem→solution→proof, CTA
- Generate VSL scripts using Jeremy Haynes method: summary (0:00-1:30), hook, credibility, buying motives, offer with stated price, objection handling, qualification, CTA
- Always enforce: state price clearly in VSL, no value stacks, no fake discounts
- Run asset generation post-ICP filtering; use --single flag for VSL (token-heavy)
- Reference `directives/jeremy-haynes-vsl-sop.md` for authoritative VSL methodology

---

## Jeremy Haynes VSL Framework (TP-029)

- Open with the buyer's implicit question, not your credentials
- Follow the exact sequence: Problem → Agitation → Solution revelation → Social proof → Objection handling → Offer clarity → Call to action
- Embed application/scheduling directly on page below VSL — no competing elements
- Use micro-commitments ("just watch this") before macro asks
- Structure copy around buyer spectrum psychology: skeptical buyers need more proof earlier
- DSL alternative: organize as visual deck slides with brief verbal overlay

---

## ICP Pre-Generation Gate (TP-034)

Before running email/ad/VSL generation, leads must be filtered through `execution/filter_icp.py`. Only generate assets for leads where `icp_include == true` or score >= 6. This reduces token spend and ensures higher-quality copy outputs.

---

## Competitor Ad Intelligence (TP-037)

Before generating ad copy or landing page messaging, check `bots/ads-copy/memory.md` → Competitor Intelligence Log. Prioritize: (1) longest-running ads (30+ days = proven winners), (2) recurring hook patterns across 3+ creatives, (3) identified pain points and CTAs. Flag if a proposed angle directly conflicts with competitor winners.

---

## Business Audit Generation (TP-041)

- Generate personalized business audit packages (1-page audit, landing page, ad angles, outreach email)
- Analyze business websites using requests + BeautifulSoup for gap identification
- Create HTML landing pages tailored to prospect pain points
- Draft 3 ad angles (Pain/Opportunity/Credibility framework) in JSON format
- Support both Web UI (`http://localhost:5050/audit`) and CLI workflows


---

## Integrate Frontend Design SOP into WebBuild training (TP-2026-03-21-033)

## Frontend Design SOP


---

## Unlock video/animation capability with Remotion 4.0 (TP-2026-03-21-034)

## Remotion Video Generation


---

## Standardize on React 19 + Tailwind CSS 4 stack (TP-2026-03-21-035)

## Modern Frontend Stack


---

## Add browser-based media processing (Mediabunny) (TP-2026-03-21-036)

## Media Processing Capability
