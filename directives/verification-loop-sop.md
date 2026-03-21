# Sub-Agent Verification Loops SOP
> directives/verification-loop-sop.md | Version 1.0

---

## Purpose

Quality control through peer review. Agent A produces work, Agent B reviews it. If issues are found, Agent A revises. Max 3 cycles. Catches errors that any single agent would miss.

---

## When to Use

**Required for:**
- Client deliverables (emails, ad copy, VSL scripts, audit reports)
- Code changes to production scripts
- Any output that will be sent externally

**Optional for:**
- Internal research or notes
- Brainstorming and ideation
- Quick one-off tasks

---

## How It Works

```
Task → Producer Agent → Output
                          ↓
                    Reviewer Agent → Review
                          ↓
                    PASS? → Done (return output)
                    REVISE? → Producer revises → Reviewer re-reviews
                          ↓
                    (max 3 cycles, then return best version)
```

---

## Model Pairing Recommendations

| Task Type | Producer | Reviewer | Why |
|---|---|---|---|
| Ad copy | Claude | Gemini | Different strengths catch different issues |
| Backend code | GPT | Claude | GPT codes, Claude catches logic gaps |
| Email sequence | Claude | Claude (low temp) | Same model, reviewer at temp 0.3 for stricter review |
| VSL script | Claude | Claude | High-stakes copy needs nuanced review |
| Frontend design | Gemini | Claude | Gemini designs, Claude reviews structure |

---

## Lightweight Mode

When using only Claude (no cross-model):
- Producer: temperature 0.7 (creative)
- Reviewer: temperature 0.3 (strict, analytical)
- Same model, different behavior via temperature

---

## Execution

```bash
# With contract validation
python execution/verification_loop.py \
    --task "Write a cold email for dental clinic owner in Miami" \
    --producer-model claude \
    --reviewer-model claude \
    --contract execution/prompt_contracts/contracts/lead_gen_email.yaml

# Cross-model verification
python execution/verification_loop.py \
    --task "Write an ad hook for Amazon FBA coaching" \
    --producer-model claude \
    --reviewer-model gemini \
    --save .tmp/verified/ad_hook.json
```

---

## Integration with Prompt Contracts

When a `--contract` is provided, the reviewer validates output against the contract's constraints and Definition of Done in addition to general quality review. This combines automated validation with AI judgment.

---

## Review Scoring

| Score | Meaning |
|---|---|
| 9-10 | Exceptional. Ship it. |
| 7-8 | Good. Minor polish only. |
| 5-6 | Acceptable but has gaps. Needs revision. |
| 3-4 | Significant issues. Major revision needed. |
| 1-2 | Fundamentally wrong. Start over. |
