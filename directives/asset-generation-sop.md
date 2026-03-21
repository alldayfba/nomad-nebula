# Asset Generation SOP — Ad Scripts & VSL

## Purpose
Generate paid ad scripts (Meta/YouTube) and full VSL scripts targeted to a lead's industry.
Used to build out the Dream 100 asset stack: email + ad + VSL per target niche/segment.

## Asset Types Built Here

| Asset | Script | Output |
|---|---|---|
| Meta ad script | `generate_ad_scripts.py --platform meta` | hook + body + CTA |
| YouTube ad script | `generate_ad_scripts.py --platform youtube` | hook + body + CTA |
| VSL script | `generate_vsl.py` | full 8-10 min script, sectioned |

## When to Use
- **Ad scripts:** When running paid traffic to a new niche segment. One ad per industry category.
- **VSL:** When building a landing page or VSL funnel for a specific niche. One VSL per segment.
- Run these after `filter_icp.py` so you're generating assets for real prospects.
- VSL is token-heavy — use `--single` flag to generate for one business/industry at a time.

---

## Ad Script Generation

### Structure (Meta)
1. Hook — 2-3 second scroll-stopper
2. Problem agitation — painfully specific to the viewer's world
3. Solution tease — the mechanism, not the product
4. CTA — one action

### Structure (YouTube pre-roll)
1. Hook — first 5 seconds, must earn attention before skip button
2. Credentials drop — fast, builds trust
3. Problem → Solution → Proof
4. CTA

### How to Run
```bash
source .venv/bin/activate

# Meta ad scripts
python execution/generate_ad_scripts.py \
  --input .tmp/filtered_leads.csv \
  --platform meta

# YouTube ad scripts
python execution/generate_ad_scripts.py \
  --input .tmp/filtered_leads.csv \
  --platform youtube \
  --output .tmp/yt_scripts.csv
```

### Output Columns
- `ad_hook` — opening hook line
- `ad_body` — full script body
- `ad_cta` — closing call to action
- `ad_platform` — meta or youtube

---

## VSL Generation

> **Read `directives/jeremy-haynes-vsl-sop.md` before generating any VSL.** That document is the authoritative methodology for all VSL production — synthesized from Jeremy Haynes' complete YouTube library. It overrides the summary below with full detail.

### Structure (Jeremy Haynes Method — 10–20 min for agency)
0. SUMMARY SECTION (0:00–1:30) — compress entire VSL into 60–90 seconds, state price immediately
1. HOOK / OPENER — "Here's what I can do for you" (not your bio, not credentials)
2. CREDIBILITY — specific, real, verifiable experience (no Forbes/press mentions)
3. BUYING MOTIVES — majority hook first, cascade to minority hooks
4. THE OFFER — state price clearly, no value stacks, no fake discounts
5. OBJECTION HANDLING — pull from real sales call data
6. QUALIFICATION — "this is for you / not for you" language
7. CTA — one clear action

**Key rules:** Always state price. Never use value stacks. Host on Wistia. Embed application (not a button). Only headline + VSL + form on the page — nothing else.

### How to Run
```bash
source .venv/bin/activate

# VSL for one specific business/niche
python execution/generate_vsl.py \
  --input .tmp/filtered_leads.csv \
  --single "Dental Clinic"

# VSL for all leads (expensive — use sparingly)
python execution/generate_vsl.py \
  --input .tmp/filtered_leads.csv
```

### Output
- CSV with `vsl_script` column (full script stored as text)
- Readable `.txt` file per lead in `.tmp/vsl_<business>_<ts>.txt` — open these for review

---

## Cost Estimates

| Asset | Tokens/lead | Cost at 100 leads |
|---|---|---|
| Meta ad script | ~800 | ~$0.25 |
| YouTube ad script | ~1,000 | ~$0.30 |
| VSL script | ~3,000 | ~$0.90 |

## Workflow: Full Dream 100 Asset Stack per Segment

### Phase Gates (STRICT ORDER — no skipping)

**Phase 1: Data Collection** — must complete before Phase 2
1. Scrape: `run_scraper.py --query "[niche]" --location "[market]" --max 50`
2. Filter: `filter_icp.py --input leads.csv`
- Quality gate: filtered CSV has 10+ qualified leads with valid data

**Phase 2: Copy Generation** — must complete before Phase 3. Uses Phase 1 output.
3. Email: `generate_emails.py --input filtered.csv`
4. Ad (Meta): `generate_ad_scripts.py --input filtered.csv --platform meta`
5. VSL: `generate_vsl.py --input filtered.csv --single "[top lead]"`
- Quality gate: all assets reference specific niche language, no generic "business owner" copy

**Phase 3: Review + Deploy**
6. Review all assets, QC against banned words list, upload to outreach tool + ad platform
- Quality gate: zero banned AI-tell words, hooks are niche-specific, CTA is singular

## Quality Review — Ad Scripts
- [ ] Hook is specific to the niche (not generic "are you a business owner?")
- [ ] Problem section uses language the ICP would use to describe their own pain
- [ ] CTA is one action — no multiple asks

## Quality Review — VSL
- [ ] Each section transitions naturally
- [ ] Proof/results section is specific (numbers > vague claims)
- [ ] Objection handling covers: price, time, "I've tried agencies before"
- [ ] CTA is urgent but not pushy

## Known Issues
- Very generic categories produce generic scripts — if category is "Store", manually specify the niche in `--single`
- VSL scripts require light editing before recording — they're 90% done, not 100%
- Ad scripts are for video — they need to be read aloud for timing review before shooting
