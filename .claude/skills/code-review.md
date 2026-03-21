---
name: code-review
description: Spawn fresh-context reviewer and resolver subagents to review code. Implement → Review → Resolve pattern.
trigger: when user says "review this code", "code review", "verify this implementation", "review and resolve", "get a second opinion", "fresh eyes on this", "check this code"
tools: [Bash, Read, Write, Edit, Glob, Grep, Agent]
---

# Code Review (Subagent Verification)

## Directive
Read `directives/code-review-sop.md` for the full SOP before proceeding.

## Goal
Spawn independent reviewer and resolver subagents with fresh context to catch bugs, edge cases, security issues, and simplification opportunities. The reviewer didn't write the code, so it doesn't defend the code.

## Inputs
| Input | Required | Default |
|---|---|---|
| target | Yes | — (file path, directory, or "last change" for git diff) |
| requirements | No | inferred from code context |
| severity_threshold | No | minor |
| max_loops | No | 1 (set to 2 for critical code) |
| model | No | sonnet (use opus for security-critical) |

Extract target from user's message. If ambiguous, ask.

## Execution

This skill uses the Agent tool to spawn subagents — no Python script needed.

1. **Gather** — Read the target files, identify requirements, collect context (surrounding files, types, tests)
2. **Spawn reviewer** — Agent tool with `subagent_type: "general-purpose"`, fresh context. Use the reviewer prompt from the directive.
3. **Evaluate** — PASS → done. ISSUES_FOUND → spawn resolver. CRITICAL → flag user first.
4. **Spawn resolver** — Agent tool with fresh context. Sees original code + review feedback. Produces corrected code.
5. **Apply** — Sanity-check resolver output, apply fixes to disk via Edit tool
6. **Report** — Write to `.tmp/reviews/review_YYYYMMDD_HHMMSS.md`

## Output
- Console: verdict, issue count, key fix, confidence level
- Report: `.tmp/reviews/review_YYYYMMDD_HHMMSS.md`

## Self-Annealing
If subagent spawning fails:
1. Fall back to inline review (same context, less effective but functional)
2. Log the failure mode
3. Update `directives/code-review-sop.md` Known Issues section
4. Log fix in `SabboOS/CHANGELOG.md`
