# Dream 100 at Scale SOP — 4-Agent Concurrent Pipeline

> Version 1.0 | Based on Kabrin's 150/day Dream 100 pattern with concurrent agents

## Purpose

Scale Dream 100 outreach from 10/day to 50+/day using 4 concurrent agents, each specializing in one deliverable type. All 4 agents work in parallel on the same prospect, producing a complete personalized package in ~5 minutes.

## The 4-Agent Pipeline

```
Prospect data (name, website, socials)
    ↓ (parallel fan-out)
    ├── Agent 1: VSL Script Agent (personalized video sales letter)
    ├── Agent 2: Email Sequence Agent (3-touch email flow)
    ├── Agent 3: Ad Creative Agent (3 ad scripts + angles)
    └── Agent 4: Landing Page Agent (personalized landing page copy)
    ↓ (fan-in)
Package assembled → Approval gate → Send
```

## Prerequisites

1. Brand voice extracted for each prospect (run `extract_brand_voice.py` first or inline)
2. ICP filter applied (only qualified prospects enter pipeline)
3. Approval gate system active (all sends require review)

## Execution Steps

### Step 1: Prepare Prospect Batch

Load prospects from CSV or lead list. Each prospect needs:
- Name + company
- Website URL
- Social handles (IG, X, LinkedIn — any available)
- Industry/niche
- Estimated revenue or audience size

### Step 2: Extract Brand Voice (per prospect)

For each prospect, run brand voice extraction:
```bash
python execution/extract_brand_voice.py \
    --name "{prospect}" --website "{website}" --youtube "{yt_handle}"
```

### Step 3: Fan Out — 4 Concurrent Agents

Spawn 4 Agent tool subagents in parallel, each with:
- The prospect's brand voice markdown
- The prospect's basic info
- The relevant SOP/skill for their deliverable type

**VSL Agent prompt:**
"Write a personalized VSL script for {prospect} using their brand voice. Follow `directives/jeremy-haynes-vsl-sop.md`. Output: complete VSL script with stage directions."

**Email Agent prompt:**
"Write a 3-touch email sequence for {prospect}. Follow `directives/email-generation-sop.md`. Touch 1: value-first intro. Touch 2: case study + social proof. Touch 3: direct CTA. Use their brand voice."

**Ad Creative Agent prompt:**
"Write 3 ad scripts for {prospect} with different angles (pain, curiosity, authority). Follow the ad_script prompt contract. Each script: hook + problem + agitate + solution + proof + CTA."

**Landing Page Agent prompt:**
"Write personalized landing page copy for {prospect}. Include: headline, sub-headline, deliverables list, social proof section, CTA. Match their brand voice and color scheme."

### Step 4: Fan In — Assemble Package

Collect all 4 outputs. Assemble into a single Dream 100 package:
```
.tmp/dream100/{prospect-slug}/
├── vsl-script.md
├── email-sequence.md
├── ad-scripts.md
├── landing-page.md
└── package-summary.md
```

### Step 5: Approval Gate

Create approval proposal:
```bash
python execution/approval_gate.py propose \
    --agent outreach \
    --action "Send Dream 100 package to {prospect}" \
    --risk review_before_send
```

### Step 6: Send via Multi-Channel

On approval, send via `multichannel_outreach.py`:
- Email with GammaDoc/landing page link
- IG DM with short message + link
- X DM if available
- Follow up in 2 days on alternate channel

## Scaling

| Volume | Approach | Time per prospect |
|---|---|---|
| 10/day | Sequential, 1 agent at a time | ~15 min |
| 25/day | 2 agents parallel | ~7 min |
| 50/day | 4 agents parallel | ~5 min |
| 100+/day | 4 agents + batch brand voice extraction | ~3 min |

## Integration with Existing Skills

- `/dream100` — Existing skill, now upgraded to use this SOP
- `/cold-email` — Email agent uses this skill internally
- `/vsl` — VSL agent uses this skill internally
- `/business-audit` — Can replace the package with a full 4-asset audit

## Cost per Prospect

- Brand voice extraction: ~$0.02 (Sonnet, one-shot)
- 4 concurrent agents: ~$0.08 (4 × Sonnet calls)
- Total: ~$0.10/prospect
- 50/day = ~$5/day = ~$150/month

## Known Issues

<!-- Append issues discovered during use below this line -->
