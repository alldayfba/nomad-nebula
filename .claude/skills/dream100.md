---
name: dream100
description: Build hyper-personalized GammaDoc outreach packages for high-value prospects
trigger: when user says "dream 100", "gammadoc", "build gammadoc", "dream100", "personalized outreach"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Dream 100 Outreach

## Directive
Read `directives/dream100-sop.md` for the full SOP before proceeding.

## Goal
Research a prospect, generate personalized deliverables FOR their business, assemble into a GammaDoc. Goal is NOT to close on first message — it's to provide enough real value that they reach out wanting more.

## Pipeline (STRICT ORDER — no parallel execution)
```
Phase 1: research_prospect.py    → gaps identified, offer extracted
Phase 2: generate_dream100_assets.py → assets reference specific research
Phase 3: assemble_gammadoc.py    → final GammaDoc ready for Gamma.app
```

## Inputs
| Input | Required | Default |
|---|---|---|
| name | Yes | prospect name or business name |
| website | Yes | their website URL |
| niche | Yes | their industry |
| offer | Yes | what they sell |
| platform | No | "meta" (where they primarily market) |

Extract from user's message. Ask for any missing required inputs.

## Execution (Full Pipeline — One Command)
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/run_dream100.py \
  --name "{name}" \
  --website "{website}" \
  --niche "{niche}" \
  --offer "{offer}" \
  --platform "{platform}"
```

## Output
- `.tmp/research_{name}_{ts}.json` — prospect intel
- `.tmp/assets_{name}_{ts}.json` — generated deliverables
- `.tmp/gammadoc_{name}_{ts}.md` — final GammaDoc (paste into Gamma.app → publish → send link)

## What Gets Built FOR the Prospect
- 3 Meta ad hooks they can run today
- 1 YouTube pre-roll script
- 3-email welcome/nurture sequence
- 5 landing page headline options
- VSL hook + problem-agitation section
- Confirmation page copy

## Follow-Up Cadence (remind user)
7 touches minimum. Most sales close on touches 4-7.
1. Day 0: Send GammaDoc link
2. Open trigger: "Just saw you opened it"
3. Day 3: New insight from their niche
4. Day 7: Result from a similar client
5. Day 14: Question about their current challenge
6. Day 21: Relevant case study
7. Day 30: "Last one from me"

## Self-Annealing
If execution fails:
1. If website blocks scraper — manually provide `--gaps` and `--offer` to asset generation
2. Keep `--platform` accurate (Meta hooks vs YouTube scripts are different formats)
3. GammaDoc markdown may need minor formatting cleanup for Gamma.app
4. Fix the script, update directive Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
