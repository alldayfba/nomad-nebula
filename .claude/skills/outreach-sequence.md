---
name: outreach-sequence
description: Create and manage multi-touch personalized outreach sequences for qualified leads
trigger: when user says "create outreach sequence", "outreach pipeline", "sequence", "follow-up sequence", "nurture sequence"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Outreach Sequencer

## Directive
Read `directives/outreach-sequencer-sop.md` for the full SOP before proceeding.

## Goal
Manage multi-touch personalized outreach sequences. Takes qualified leads, generates personalized copy per prospect, tracks pipeline from draft to booked.

## Inputs
| Input | Required | Default |
|---|---|---|
| leads CSV | Yes (for create) | — |
| template | No | "cold_email" |

Templates:
| Template | Touches | Duration | Use Case |
|---|---|---|---|
| `dream100` | 7 | 30 days | High-value prospects, full Dream 100 |
| `cold_email` | 4 | 14 days | Standard cold outreach |
| `warm_followup` | 3 | 10 days | Re-engaging warm leads |

## Commands

### Create sequence from leads CSV
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/outreach_sequencer.py create-sequence --leads {leads_csv} --template {template}
```

### View touches due today
```bash
python execution/outreach_sequencer.py next-touches --due today
```

### Mark pipeline progress
```bash
python execution/outreach_sequencer.py mark --prospect "{name}" --status replied
```

## Output
- Personalized email copy per prospect per touch
- Pipeline tracking in `.tmp/outreach/sequences.db`
- Due-today list for daily execution

## Self-Annealing
If execution fails:
1. Check if input CSV has required columns (email, business_name)
2. Check `ANTHROPIC_API_KEY` in `.env` for copy generation
3. Fix the script, update directive Known Issues
4. Log fix in `SabboOS/CHANGELOG.md`
