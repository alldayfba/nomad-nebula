# Dream 100 Outreach SOP

## What This Is

Dream 100 = hyper-personalized outreach where you build a prospect a custom document (GammaDoc) packed with free, specific deliverables built for **their** business. The goal is NOT to close on the first message. The goal is to provide enough real value that they think "there's actual stuff I can implement here" — and they reach out wanting more.

This SOP drives the full pipeline: research a prospect → build their assets → assemble a GammaDoc → follow up until they book.

---

## Inputs

| Input | Description |
|---|---|
| `--name` | Prospect name or business name |
| `--website` | Their website URL |
| `--niche` | Their niche/industry (e.g., "online fitness coaching") |
| `--offer` | What they sell (e.g., "1:1 online fitness coaching at $500/mo") |
| `--platform` | Where they primarily market (meta, youtube, instagram, email) |

---

## Phase Gates (STRICT ORDER)

Each phase must complete and pass quality check before the next begins. No parallel execution.

```
PHASE 1: research_prospect.py        → Quality gate: gaps identified, offer extracted
      ↓
PHASE 2: generate_dream100_assets.py  → Quality gate: assets reference specific research findings
      ↓
PHASE 3: assemble_gammadoc.py         → Quality gate: GammaDoc rules pass, branding matches
      ↓
.tmp/gammadoc_<name>.md  ← paste into Gamma.app
```

Master runner: `execution/run_dream100.py` runs all three steps in sequence with phase validation.

**Phase 1 must complete before Phase 2.** Assets cannot be generated without research data — they'll be generic garbage.
**Phase 2 must complete before Phase 3.** GammaDoc assembly requires completed assets — partial assembly = unprofessional output.

---

## Step 1: Research the Prospect

**Script:** `execution/research_prospect.py`

What it does:
- Fetches their website homepage
- Extracts: current offer, existing CTA, funnel type, social proof signals, brand colors, logo URL
- Identifies marketing gaps (missing VSL, no email capture, weak ad hooks, etc.)
- Outputs JSON to `.tmp/research_<name>_<ts>.json`

**Usage:**
```bash
python execution/research_prospect.py \
  --name "Alex Hormozi" \
  --website "https://acquisition.com" \
  --niche "business education" \
  --offer "acquisition.com programs"
```

**What to look for in the output:**
- `funnel_type` — VSL, webinar, application, direct sales page, or none
- `gaps` — the 2-3 biggest marketing gaps you spotted
- `brand_colors` — hex codes to match in your GammaDoc
- `logo_url` — grab and put in the GammaDoc header

---

## Step 2: Generate the Deliverables

**Script:** `execution/generate_dream100_assets.py`

What it builds FOR THE PROSPECT (not for you — for their business):
- 3 Meta ad hooks they can run today
- 1 YouTube pre-roll script for their offer
- 3-email welcome/nurture sequence for their list
- 5 landing page headline options
- VSL hook + problem-agitation section
- Confirmation page copy (boosts show rates 30-50%)

Assets are personalized to their specific offer, niche, and the gaps identified in research.

**Usage:**
```bash
python execution/generate_dream100_assets.py \
  --research .tmp/research_Alex_Hormozi_20260220.json \
  --prospect-name "Alex Hormozi"
```

**Output:** `.tmp/assets_<name>_<ts>.json`

---

## Step 3: Assemble the GammaDoc

**Script:** `execution/assemble_gammadoc.py`

Builds the final GammaDoc in the **correct structure** (per Kabrin's feedback):

```
1. Branded header (their logo + colors)
2. One-line system overview (short — what you built and why)
3. FREE DELIVERABLES (main section — gets here fast, everything in one card)
   ├── Meta Ad Hooks (3x)
   ├── YouTube Ad Script
   ├── Email Sequence (3 emails)
   ├── Landing Page Headlines
   ├── VSL Hook + Problem Section
   └── Confirmation Page Copy
4. Results / Case Studies ("just so you know, not making this up")
5. Booking CTA (one action, no friction)
```

**Usage:**
```bash
python execution/assemble_gammadoc.py \
  --research .tmp/research_Alex_Hormozi_20260220.json \
  --assets .tmp/assets_Alex_Hormozi_20260220.json \
  --prospect-name "Alex Hormozi"
```

**Output:** `.tmp/gammadoc_<name>_<ts>.md`

Then paste this into Gamma.app → publish → send the link.

---

## Running the Full Pipeline (One Command)

```bash
python execution/run_dream100.py \
  --name "Alex Hormozi" \
  --website "https://acquisition.com" \
  --niche "business education" \
  --offer "high-ticket business coaching programs" \
  --platform "youtube"
```

This runs all 3 steps in sequence and outputs the final GammaDoc path.

---

## GammaDoc Rules (from Kabrin's feedback)

**Do:**
- Match their exact brand colors + logo in the header
- Get to the deliverables within the first scroll
- Put ALL deliverables in ONE section (not separate pages/cards)
- Use dropdown cards inside the deliverables section
- Use grade-6 reading level copy throughout
- Put results and case studies AFTER deliverables
- End with a single, clear booking link

**Don't:**
- Start with "about us" or your credentials
- Use jargon (SuperDoc, growth stack, etc.) — your prospect doesn't live in the bubble
- Claim revenue numbers without proof (e.g., "scale to $300K/mo" with no case study)
- Separate deliverables across multiple pages — one card, dropdowns
- Forget branding — generic white template = mass blast signal
- Add too many external links — prospect won't come back

---

## Follow-Up Cadence (7 Touches Minimum)

Most sales close on the **4th–7th follow-up**. One message = wasted effort.

| Touch | Timing | Type | Angle |
|---|---|---|---|
| 1 | Day 0 | Send GammaDoc | "Built this for you — [link]" |
| 2 | Open trigger | Email/DM | "Just saw you opened it — any questions?" |
| 3 | Day 3 | Email/DM | New insight from their niche |
| 4 | Day 7 | Email/DM | A result from a similar client |
| 5 | Day 14 | Email/DM | Quick question about their current challenge |
| 6 | Day 21 | Email/DM | Relevant case study or stat |
| 7 | Day 30 | Email/DM | "Last one from me — still happy to help" |

**Open-tracking:** If using Gamma.app, turn on open notifications. The moment they open, send Touch #2 immediately — this is the highest-conversion touchpoint.

**Platforms to follow up on:** Email + LinkedIn + IG DM (whichever they're active on). Don't spam all three at once.

---

## Volume Targets

| Phase | Volume | Method |
|---|---|---|
| Manual (now) | 5–10/day | Full quality control — build each one yourself |
| Semi-automated | 20–30/day | Research auto, assets Claude, assemble manual |
| Fully automated | 50+/day | Run `run_dream100.py` in batch via CSV of prospects |

**Rule:** Do 90 days before pivoting anything. 5 docs with no response is not a signal. 90 docs with tracked open rates is a signal.

---

## Offer Framing (the 72-hour close)

Don't pitch a $15K retainer on the first call. Pitch this:

> "I've built all of these for your business. My team can implement everything in your business within 72 hours for a one-time fee. After you see the work, we can talk about what an ongoing relationship looks like."

This removes retainer risk, gets them to experience your work, and creates a natural upsell path.

---

## Output Files

All outputs land in `.tmp/`:
```
.tmp/
├── research_<name>_<ts>.json       ← Step 1: prospect intel
├── assets_<name>_<ts>.json         ← Step 2: generated deliverables
└── gammadoc_<name>_<ts>.md         ← Step 3: final GammaDoc (paste into Gamma)
```

---

## Known Issues / Edge Cases

- Some websites block scrapers — if `research_prospect.py` fails, manually provide the `--gaps` and `--offer` args to `generate_dream100_assets.py` directly
- Keep `--platform` accurate — Meta hooks and YouTube scripts are different formats
- GammaDoc markdown may need minor formatting cleanup before pasting into Gamma.app (Gamma uses its own block format, not raw markdown)
- Open-tracking automation requires Gamma.app Pro or a custom pixel — see `directives/add_webhook.md` for webhook setup if building custom tracking

---

*Last updated: 2026-02-20*
