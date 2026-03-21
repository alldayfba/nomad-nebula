# Code Review SOP — Subagent Verification Loops

> Version 1.0 | Based on Nick Saraev's Implement → Review → Resolve pattern

## Purpose

Quality improvement via fresh-context peer review. A separate agent with zero knowledge of the implementation reviews the code objectively, catching bugs, edge cases, security issues, and simplification opportunities that the implementer missed due to sunk-cost bias.

**Why this works:** The agent that wrote the code remembers every dead end, has sunk-cost bias ("I wrote this, so it must be right"), and is blind to its own mistakes. The reviewer agent has fresh empty context — it only sees the output, not the journey. No emotional attachment. No accumulated assumptions. Fresh eyes catch what tired eyes miss.

## When to Use

**Required (auto-trigger):**
- Security-sensitive code (auth, crypto, access control)
- Data-mutation code (migrations, bulk updates, deletes)
- Code that handles money or PII
- Complex implementations where you felt uncertain

**Optional (user-triggered via `/code-review`):**
- Any code the user asks to review
- Architecture/design decisions before implementing
- User-provided code they want a second opinion on

**Skip for:**
- Trivial changes (typos, config tweaks, adding a log line)
- Code the user explicitly said "just do it quick"
- Read-only operations

## The Pattern

```
Implement → Review → Resolve
```

Three agents, each with fresh context:
1. **Implementer** — You (the main agent). Already wrote the code.
2. **Reviewer** — Spawned with fresh context. Only sees the code + requirements. No implementation bias.
3. **Resolver** — Spawned with fresh context. Sees original code + review feedback. Produces corrected version.

## Execution Steps

### Step 1: Gather the Artifact

Determine what needs review:
- **Code just written** — most common case
- **Specific files** — user points to file(s)
- **Last change** — use `git diff` to identify what changed
- **Architecture/design** — verify a plan before implementing

Collect:
1. The code/output itself (full file contents)
2. The original requirements or prompt that produced it
3. Context: surrounding files, API contracts, types, tests
4. If reviewing a large codebase, split into logical chunks (< 500 lines per review)

### Step 2: Spawn the Reviewer

Spawn a **single reviewer subagent** with fresh context using the Agent tool. The reviewer has NO access to implementation reasoning — only the output and requirements.

**Agent tool config:**
- `subagent_type: "general-purpose"`
- `model: "sonnet"` (default — use `"opus"` for complex or security-critical code)

**Reviewer prompt template:**

```
You are a senior code reviewer with fresh eyes. You did NOT write this code. Your job is to find problems.

ORIGINAL REQUIREMENTS:
{what the code was supposed to do}

CODE TO REVIEW:
{the full code artifact — include file paths}

CONTEXT:
{surrounding code, API contracts, types, tests, or other relevant files}

Review for:
1. **Correctness** — Does it actually do what the requirements ask? Are there logic errors?
2. **Edge cases** — What inputs or states would break this? Empty arrays, null values, concurrent access, network failures?
3. **Simplification** — Is anything over-engineered? Can any code be removed or simplified without losing functionality?
4. **Security** — SQL injection, XSS, command injection, auth bypasses, secrets in code?
5. **Consistency** — Does it match the patterns and conventions of the surrounding codebase?

Respond in this exact format:

VERDICT: PASS | ISSUES_FOUND | CRITICAL

ISSUES (if any):
For each issue:
- SEVERITY: critical | major | minor | nit
- LOCATION: {file:line or section}
- PROBLEM: {what's wrong}
- FIX: {concrete fix — show the corrected code, not just "fix this"}

SIMPLIFICATIONS (if any):
- {what can be removed or simplified, with the simpler version}

SUMMARY: {one paragraph — overall assessment}

Be ruthless. Better to flag a false positive than miss a real bug. But don't invent problems that don't exist — if the code is clean, say PASS.

Write your response directly — do not write to any files.
```

### Step 3: Evaluate the Review

Read the reviewer's output. Three possible paths:

**Path A: PASS (no issues)**
The reviewer found nothing wrong. Report to the user:
- "Verified by independent reviewer — no issues found."
- Include the reviewer's summary as confirmation.
- Done.

**Path B: ISSUES_FOUND (non-critical)**
The reviewer found real issues but nothing catastrophic. Proceed to Step 4 (Resolve).

**Path C: CRITICAL**
The reviewer found a critical bug (security vulnerability, data loss, completely wrong logic). **Flag immediately to the user** before resolving — they may want to change approach entirely.

### Step 4: Spawn the Resolver (if issues found)

The resolver sees BOTH the original implementation AND the review. Its job: produce a corrected version that addresses the feedback while preserving the original intent.

**Agent tool config:**
- `subagent_type: "general-purpose"`
- `model: "sonnet"` (match the reviewer's model)

**Resolver prompt template:**

```
You are a senior engineer resolving code review feedback. You have two inputs:

1. ORIGINAL CODE:
{the original implementation — include file paths}

2. REVIEW FEEDBACK:
{the reviewer's full response}

Your job:
- Fix every issue marked "critical" or "major"
- Fix "minor" issues unless the fix would add complexity disproportionate to the benefit
- Apply simplifications where the reviewer's suggestion is genuinely simpler
- Ignore "nit" level feedback unless trivial to address
- Do NOT introduce new features or refactor beyond what the review requested

For each issue, either:
- FIXED: {show the fix}
- DECLINED: {explain why the reviewer's suggestion doesn't apply or would make things worse}

Then output the COMPLETE corrected code — not a diff, the full thing. The orchestrator will use this to replace the original.

Write your response directly — do not write to any files.
```

### Step 5: Apply the Resolution

You (the orchestrator) apply the corrected code to disk.

Before applying, sanity-check:
- Did the resolver address all critical/major issues?
- Did the resolver break anything the original got right?
- Are any "DECLINED" decisions reasonable?

If the resolver's output looks good, apply it using the Edit tool.

### Step 6: Optional Loop (for critical code)

For high-stakes code (auth, payments, data migrations), run a **second verification loop** on the resolver's output. This catches issues the resolver might have introduced while fixing the original.

**Max loops: 2.** If the code isn't clean after 2 review cycles, stop and flag to the user — there may be a deeper design problem that review can't fix.

```
Round 1: Implement → Review → Resolve
Round 2: Resolve output → Review → Resolve (if needed)
Done.
```

### Step 7: Write the Verification Report

Write to `.tmp/reviews/review_YYYYMMDD_HHMMSS.md`:

```markdown
# Code Review Report

**Artifact**: {what was reviewed — file paths}
**Date**: {date}
**Rounds**: {how many review cycles}
**Reviewer model**: {sonnet or opus}

## Verdict: {PASS | FIXED | CRITICAL}

## Issues Found
| # | Severity | Location | Problem | Status |
|---|----------|----------|---------|--------|
| 1 | major | file.py:42 | Off-by-one in loop | Fixed |
| 2 | minor | file.py:15 | Unused import | Fixed |
| 3 | nit | file.py:8 | Naming convention | Declined |

## Simplifications Applied
{What was simplified and why}

## Changes Made
{Summary of what changed between original and final version}

## Reviewer's Summary
{The reviewer's overall assessment}

## Resolver's Notes
{Any "DECLINED" decisions and reasoning}
```

### Step 8: Deliver Results

Present to the user:
- **Verdict** — PASS (clean) or FIXED (issues found and resolved) or CRITICAL (flagged)
- **Issue count** — X issues found, Y fixed, Z declined
- **Key fix** — the most important thing that was caught
- **Confidence** — higher after verification than before
- **Report path** — `.tmp/reviews/review_YYYYMMDD_HHMMSS.md`

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| model | sonnet | Model for reviewer and resolver subagents |
| max_loops | 1 | Review cycles (set to 2 for critical code) |
| severity_threshold | minor | Minimum severity to fix (minor, major, critical) |
| auto_apply | true | Apply fixes automatically or show diff first |

User overrides: "review this with opus", "do 2 rounds of verification", "show me the diff before applying"

## Edge Cases

- **Reviewer finds no issues**: PASS. Don't force a resolve step.
- **Reviewer hallucinates issues**: The resolver catches this — if the "fix" doesn't make sense, it DECLINES. You catch it in your sanity check.
- **Resolver introduces new bugs**: This is why Round 2 exists for critical code.
- **Reviewer and resolver disagree**: You (the orchestrator) break the tie. Read both arguments, pick the better one.
- **Code is too large**: Split into logical chunks (< 500 lines each) and review separately.
- **No requirements available**: Infer requirements from the code's structure, docstrings, tests, and surrounding context. Note that requirements were inferred in the report.

## Cost Considerations

- 1 round (reviewer + resolver) with sonnet: ~$0.10-0.20
- 1 round with opus: ~$0.50-1.00
- 2 rounds doubles the cost
- Very cheap relative to the quality improvement — default to always running for non-trivial code

## Known Issues

<!-- Append issues discovered during use below this line -->
