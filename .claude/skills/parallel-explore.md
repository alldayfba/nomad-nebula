---
name: parallel-explore
description: Explore 3 competing approaches simultaneously in temp folders, test all with real data, rate each on speed/reliability/cost/complexity, promote the winner to execution/ and directives/.
trigger: when user says "explore approaches", "which approach", "best way to build", "parallel explore", "try a few approaches", "not sure which approach", "compare approaches"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Parallel Explore

## Directive
Read `directives/parallel-exploration-sop.md` for the full SOP before proceeding.

## Goal
Build 3–5 competing implementations of the same task in isolated `.tmp/explore/approach-N/` folders, test each with real data, rate them on the standard rubric, and promote the winner to `execution/` and `directives/`.

## Inputs
| Input | Required | Default |
|---|---|---|
| task | Yes | — (what needs to be built) |
| n_approaches | No | 3 |
| test_data | No | inferred or synthetic |

Extract the task from the user's message. If it's vague, ask one clarifying question before proceeding: "What's the input and desired output?"

## Execution

### Phase 1 — Setup
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula
mkdir -p .tmp/explore/approach-1 .tmp/explore/approach-2 .tmp/explore/approach-3
```

### Phase 2 — Design approaches
Before writing code, write each `README.md` with the hypothesis and expected tradeoffs. Make the approaches genuinely distinct — not minor variations of the same method.

### Phase 3 — Build
Write `run.py` for each approach. Each must be self-contained and runnable standalone.

### Phase 4 — Test
```bash
source .venv/bin/activate
python .tmp/explore/approach-1/run.py
python .tmp/explore/approach-2/run.py
python .tmp/explore/approach-3/run.py
```
Record real timing, output samples, and any errors in each approach's `results.md`.

### Phase 5 — Rate and decide
Score each on Speed / Reliability / Cost / Complexity (1–5 each). Write `decision.md` with the comparison table, winner declaration, and loser learnings.

### Phase 6 — Promote
1. Copy winner to `execution/{final_name}.py` (clean up exploration scaffolding)
2. Create or update `directives/{name}-sop.md`
3. Delete `.tmp/explore/`
4. Log in `SabboOS/CHANGELOG.md`

## Output
- Winner script: `execution/{final_name}.py`
- Updated or new directive: `directives/{name}-sop.md`
- Decision record: printed to console before `.tmp/explore/` is deleted

## Self-Annealing
If an approach fails to run:
1. Read the error — is it a missing dep, wrong path, API key issue?
2. Fix the approach's `run.py` and re-run (one fix attempt per approach)
3. If it still fails, mark it DNF in `results.md` and continue with remaining approaches
4. If all approaches fail, stop and report what broke — don't promote a broken winner
5. Log any API quirks or environment issues discovered in the winning directive's `## Known Issues` section
