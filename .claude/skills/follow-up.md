---
name: follow-up
description: Nurture existing CRM pipeline conversations with personalized follow-ups based on prior touchpoints
trigger: when user says "follow up", "nurture pipeline", "check in with leads", "follow-up nurture", "clear my pipeline"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Follow-Up Nurture

## Directive
Read `directives/outreach-sequencer-sop.md` and `directives/email-generation-sop.md` for context.

## Goal
Read existing pipeline/CRM conversations, identify where each lead is, and generate personalized follow-ups in the same conversation thread. Unlike `/outreach-sequence` (creates NEW sequences), this skill nurtures EXISTING conversations.

## How It Works
1. Check outreach sequencer DB for active sequences: `python execution/outreach_sequencer.py next-touches --due today`
2. For each due touch, read prior touchpoints to understand context
3. Generate contextual follow-up copy that continues the existing thread (not a new cold email)
4. Match tone and style of previous messages in the thread
5. Present all follow-ups for review before sending

## Inputs
| Input | Required | Default |
|---|---|---|
| prospect name | No | all due today |
| pipeline stage | No | all stages |
| max count | No | all due |

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate

# View what's due today
python execution/outreach_sequencer.py next-touches --due today

# View specific prospect's history
python execution/outreach_sequencer.py history --prospect "{name}"
```

## Follow-Up Rules
- **Tone:** Casual, peer-to-peer, operator-to-operator. NOT salesy.
- **Length:** Under 80 words for follow-ups (shorter than initial outreach)
- **Personalization:** Reference something specific from prior conversation or their business
- **Variety:** Each follow-up should use a different angle (new insight, case study, quick question, last touch)
- **Threading:** Follow-ups should feel like replies in an existing conversation, not new emails

## Follow-Up Cadence Reference
| Touch | Timing | Angle |
|---|---|---|
| 2 | Open trigger | "Just saw you opened it" |
| 3 | Day 3 | New insight from their niche |
| 4 | Day 7 | Result from a similar client |
| 5 | Day 14 | Quick question about their challenge |
| 6 | Day 21 | Relevant case study |
| 7 | Day 30 | "Last one from me — still happy to help" |

## Output
- List of follow-ups generated with prospect name, touch number, subject, body
- Status: drafted / sent / queued

## Self-Annealing
If execution fails:
1. Check if outreach sequencer DB exists at `.tmp/outreach/sequences.db`
2. If no sequences exist, suggest running `/outreach-sequence` first
3. Check `bots/outreach/memory.md` for winning follow-up patterns
4. Fix the script, update directive Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
