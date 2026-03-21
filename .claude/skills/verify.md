---
name: verify
description: Run a producer-reviewer verification loop to quality-check agent output
trigger: when user says "verify this", "review this", "quality check", "double check this output"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Sub-Agent Verification Loop

## Directive
Read `directives/verification-loop-sop.md` for the full SOP before proceeding.

## Goal
Producer agent generates output, reviewer agent reviews it. If issues found, producer revises. Max 3 cycles. Returns verified, high-quality output.

## Inputs
| Input | Required | Default |
|---|---|---|
| task | Yes | — (what to produce) |
| producer-model | No | `claude` |
| reviewer-model | No | `claude` |
| contract | No | — (path to prompt contract YAML, auto-detected if possible) |

Extract the task from the user's message. Auto-detect contract:
- Email task → `execution/prompt_contracts/contracts/lead_gen_email.yaml`
- Ad copy → `execution/prompt_contracts/contracts/ad_script.yaml`
- VSL → `execution/prompt_contracts/contracts/vsl_section.yaml`
- Audit → `execution/prompt_contracts/contracts/business_audit.yaml`
- Sourcing → `execution/prompt_contracts/contracts/sourcing_report.yaml`

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/verification_loop.py --task "{task}" --producer-model {producer_model} --reviewer-model {reviewer_model} --contract {contract} --save .tmp/verified/verified_$(date +%Y%m%d_%H%M%S).json
```

Without contract:
```bash
python execution/verification_loop.py --task "{task}" --producer-model claude --reviewer-model claude
```

## Output
- Console: final verified output + score + cycle count
- File: full results with review trail saved to `.tmp/verified/`

## Self-Annealing
If execution fails:
1. Check API key in `.env`
2. If reviewer can't parse producer output → lower producer temperature
3. Fix the script, update `directives/verification-loop-sop.md`
4. Log fix in `SabboOS/CHANGELOG.md`
