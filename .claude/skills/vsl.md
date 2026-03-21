---
name: vsl
description: Generate full VSL (Video Sales Letter) scripts using Jeremy Haynes' 9-beat framework
trigger: when user says "write vsl", "vsl script", "video sales letter", "generate vsl"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# VSL Script Generator

## Directive
Read `directives/jeremy-haynes-vsl-sop.md` for the full 11-section framework before proceeding. This is the authoritative reference for VSL structure.

## Goal
Generate a full production-ready VSL script using the Jeremy Haynes 9-beat framework. Uses Opus model for high-stakes copy.

## 9-Beat Framework
```
0. Summary Section (first 60-90 seconds — compressed version of entire VSL)
1. Hook / Opener — "Here's what I can do for you"
2. Credibility — "Here's why I can help"
3. Buying Motives — "Here's why people like you buy this" (longest section)
4. Offer Reveal — state the price, no value stacks
5. Proof / Results — before → what we did → after (specific numbers)
6. Objection Handling — address top 3 objections
7. Qualification — who this is NOT for
8. CTA — one clear action
```

## Critical Rules (from Jeremy Haynes)
- **State the price.** Never use value stacks. "The investment is $X."
- **Summary first.** First 60-90 seconds = compressed version of entire VSL
- **Majority hook → minority hook cascade** in buying motives
- **No "As seen on Forbes"** — use real, specific, believable proof
- **Target runtime:** 12-20 minutes (~1,800-3,000 words)
- **Grade 6 reading level** throughout

## Inputs
| Input | Required | Default |
|---|---|---|
| business/offer | Yes | — (what we're selling) |
| input CSV | No | single business mode |
| target audience | No | inferred from offer |

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate

# Single business VSL
python execution/generate_vsl.py --input {csv} --single "{business_name}"

# Batch (token-heavy — use sparingly)
python execution/generate_vsl.py --input {csv}
```

## Output
- Full VSL script in `.tmp/vsl_{business}_{ts}.txt`
- CSV with `vsl_script` column (if batch mode)
- Cost: Opus pricing — monitor token usage

## Self-Annealing
If execution fails:
1. Check `ANTHROPIC_API_KEY` in `.env`
2. Use `--single` flag to reduce token cost
3. If copy is too generic, provide more specific business context
4. Reference `bots/creators/sabbo-growth-os-brain.md` for proven copy patterns
5. Fix the script, update directive Known Issues
6. Log fix in `SabboOS/CHANGELOG.md`
