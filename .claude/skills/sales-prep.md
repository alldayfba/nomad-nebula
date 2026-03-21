---
name: sales-prep
description: Generate a pre-call prospect brief pulling all existing data into one document
trigger: when user says "sales prep", "prep for call", "call prep", "pre-call brief", "prepare for meeting"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Sales Prep — Pre-Call Prospect Brief


## Directive
Read `directives/lead-gen-sop.md` for the full SOP before proceeding.


## Goal
Before a strategy call, pull EVERYTHING about a prospect into one brief: research data, audit results, pipeline stage, email history, prior touchpoints, and recommended talking points.

## Data Sources (check all)
1. **Research data:** `.tmp/research_{name}_*.json` (from `research_prospect.py`)
2. **Audit results:** `.tmp/audit_{name}_*/` (from `generate_business_audit.py`)
3. **GammaDoc:** `.tmp/gammadoc_{name}_*.md` (from Dream 100 pipeline)
4. **Pipeline stage:** `.tmp/outreach/sequences.db` (from outreach sequencer)
5. **Email history:** check outreach sequencer for sent touchpoints
6. **Client workspace:** `clients/` directory for any existing client files

## Inputs
| Input | Required | Default |
|---|---|---|
| prospect name | Yes | — |
| website | No | pulled from existing research if available |

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate

# Check for existing research
ls .tmp/research_{name}*
ls .tmp/audit_{name}*
ls .tmp/gammadoc_{name}*

# If no existing research, run prospect research first
python execution/research_prospect.py \
  --name "{name}" \
  --website "{website}" \
  --niche "{niche}" \
  --offer "{offer}"

# Check outreach pipeline
python execution/outreach_sequencer.py history --prospect "{name}"
```

## Output Brief Structure
Generate a single markdown file at `.tmp/sales-prep/{name}_{date}.md`:

```markdown
# Sales Prep — {Prospect Name}
## Date: {today}

## Prospect Overview
- Business: {name}
- Website: {url}
- Category: {industry}
- Rating: {stars}

## Marketing Gaps Found
- {gap 1}
- {gap 2}
- {gap 3}

## Prior Touchpoints
- {date}: {what was sent/discussed}
- {date}: {response or no response}

## Audit Highlights (if available)
- Quick wins identified
- Revenue opportunity

## Recommended Talking Points
1. Open with: {specific observation about their business}
2. Pain point to probe: {based on gaps}
3. Case study to reference: {similar client result}
4. Offer framing: {72-hour implementation, not retainer}

## Objection Prep
- "Too expensive" → {response}
- "Already have an agency" → {response}
- "Need to think about it" → {response}

## CTA
Book 72-hour implementation sprint at ${price}
```

## Self-Annealing
If execution fails:
1. If no prior data exists, run `research_prospect.py` first
2. If prospect name doesn't match files, try fuzzy matching
3. If outreach DB is empty, skip pipeline section
4. Fix the script, update directive Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
