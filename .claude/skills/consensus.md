---
name: consensus
description: Run stochastic multi-agent consensus to get high-confidence answers on important decisions
trigger: when user says "run consensus", "get consensus", "what do multiple models think", "compare models"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Stochastic Multi-Agent Consensus

## Directive
Read `directives/consensus-sop.md` for the full SOP before proceeding.

## Goal
Spawn multiple AI completions with the same prompt, analyze statistical agreement, and return the consensus answer with confidence level.

## Inputs
| Input | Required | Default |
|---|---|---|
| prompt | Yes | — (the question or task to get consensus on) |
| models | No | `claude` (options: claude, gemini, openai — comma-separated) |
| runs | No | 3 |
| temperature | No | 0.7 |

Extract the prompt from the user's message. If unclear, ask what they want consensus on.

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/consensus_engine.py --prompt "{prompt}" --models {models} --runs {runs} --temperature {temperature} --save .tmp/consensus/consensus_$(date +%Y%m%d_%H%M%S).json
```

## Output
- Console: consensus answer + confidence level (high/medium/low) + outlier if any
- File: full results JSON saved to `.tmp/consensus/`

## Mode Selection
- **Quick copy decision** → `--models claude --runs 3 --temperature 0.9`
- **Cross-model architecture decision** → `--models claude,gemini,openai --runs 1`
- **High-stakes ($10K+)** → `--models claude,gemini,openai --runs 3`

Note: gemini and openai require GOOGLE_API_KEY and OPENAI_API_KEY in `.env`.

## Self-Annealing
If execution fails:
1. If API key error → check `.env` for the relevant key
2. If all calls fail → fall back to single Claude call
3. Fix the script, update `directives/consensus-sop.md`
4. Log fix in `SabboOS/CHANGELOG.md`
