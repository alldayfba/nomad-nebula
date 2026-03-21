# API Cost Management SOP
> directives/api-cost-management-sop.md | Version 1.0

---

## Purpose

Kabrin burned $300 in one day by not restricting which LLM the bot used for routine tasks. This SOP prevents that. Every bot follows these rules.

---

## LLM Routing Rules — Claude Models

> Pricing (per million tokens, as of 2026-02): Haiku ~$0.25 input/$1.25 output | Sonnet ~$3/$15 | Opus ~$15/$75
> Opus is 60× more expensive than Haiku. Route accordingly.

### Tier 1 — Claude Haiku 4.5 (default for routine/deterministic tasks)

Model ID: `claude-haiku-4-5-20251001`

Use for:
- Lead scraping and CSV processing
- ICP scoring and classification
- File reading, formatting, and data transforms
- Heartbeat checks
- Simple summarization of short content
- Any task that is deterministic or could be done by a script

Cost profile: Very low. Use freely.

### Tier 2 — Claude Sonnet 4.6 (default for most Claude Code sessions)

Model ID: `claude-sonnet-4-6`

Use for:
- Morning briefing compilation
- Email generation (standard outreach)
- Ad script drafts
- Competitor research analysis
- Code writing, debugging, and orchestration
- Standard day-to-day Claude Code work
- Dream 100 research and asset drafts

Cost profile: Moderate. Default for interactive sessions and most generation tasks.

### Tier 3 — Claude Opus 4.6 (high-stakes creative only, intentional use)

Model ID: `claude-opus-4-6`

Use for:
- Long-form VSL scripts requiring high creative quality
- Dream 100 GammaDoc final assembly
- Complex multi-document synthesis where quality matters
- High-stakes copy: hooks, headline variants, offer angles
- **Reviewing and editing copy** (ad copy, email copy, landing page copy)
- Tasks where Sabbo explicitly says "use Opus on this"

**Rule:** Never default to Opus. Use only when quality delta justifies 20× cost.
**Hard gate:** The word "use Opus" must appear in the user's message OR the task type must match this list exactly. Do not infer Opus is needed.
**Why:** Opus is $15/$75 per million tokens vs Haiku $0.25/$1.25. One unchecked Opus loop costs what 60 Haiku tasks cost.

Cost profile: High. Treat every Opus call as a deliberate decision.

---

## Heartbeat Frequency

Every bot checks its heartbeat file every 60 minutes.

**Why this matters for cost:** If your heartbeat check uses Opus, and it runs 24 times a day across 3 bots, that's 72 Opus calls/day → guaranteed $$$. 

Rule: Heartbeat checks always use Haiku 4.5. No exceptions. Never Opus, never Sonnet.

---

## Budget Caps

### Per-Model Monthly Caps (Anthropic API)
| Model | Monthly cap | Notes |
|---|---|---|
| Haiku 4.5 | $20 | High volume, very cheap — hard to hit |
| Sonnet 4.6 | $30 | Code, orchestration, emails |
| Opus 4.6 | $20 | Creative only — alert at $15 |

**Total API target: ~$50-80/month**
Claude Pro Max ($200/month) covers Claude Code IDE usage separately.

### Per-Bot Ceilings
| Bot | Monthly ceiling | Primary model |
|---|---|---|
| Ads-Copy | $50–$100 | Opus (creative is core job) |
| Content | $30–$50 | Sonnet |
| Outreach | $20–$30 | Haiku (templated, high volume) |
| Sourcing | $10–$20 | Haiku (data processing) |
| Amazon | $20–$30 | Sonnet |
| CEO | $20 | Haiku (mostly reads files) |

Alert threshold: Message Sabbo when spending hits 80% of monthly ceiling.
**Hard gate on Opus:** If monthly Opus spend exceeds $50, alert Sabbo and stop all Opus calls until approved.

---

## What to Do When You Hit the Ceiling

1. Stop all non-critical autonomous tasks immediately
2. Switch everything to Haiku 4.5
3. Send Sabbo an alert: "Monthly API budget at [X]%. Awaiting approval to continue or increase limit."
4. Log the event in the relevant `memory.md` file

Do not exceed the ceiling without explicit approval.

---

## Warning Signs You're Spending Too Much

- Heartbeat file is very long and detailed (more text = more tokens per check)
- Running Opus on tasks that don't need it
- Checking heartbeat more frequently than 60 minutes
- Processing very large files through LLM instead of using Python for pre-processing

---

## Self-Annealing Notes

*Kabrin's $300 mistake: he set the heartbeat to use Claude Opus and set it to check every few minutes. That's the scenario to avoid.*

Update this file if new LLMs become available or pricing changes significantly.

---

## Subagent Model Routing (Claude Code Task Tool)

When spawning subagent Tasks in Claude Code for scraping, data processing, classification, or file operations:
- **Always set `model: "haiku"` in the Task tool call**
- This prevents Opus from running on routine work that Haiku handles equally well
- Only use Sonnet/Opus subagents for code generation or creative writing tasks

Example:
```
Task(subagent_type="Bash", model="haiku", prompt="scrape and parse RSS feed...")
```

---

## Quick Reference — Task → Model

| Task | Model |
|---|---|
| Lead scraping, CSV parsing, ICP scoring | Haiku 4.5 |
| Heartbeat checks | Haiku 4.5 |
| File reads, classification, data transforms | Haiku 4.5 |
| Subagent Tasks for scraping/parsing/classification | Haiku 4.5 |
| Morning briefing, email generation, ad scripts | Sonnet 4.6 |
| Code writing, debugging, orchestration | Sonnet 4.6 |
| Dream 100 research + asset drafts | Sonnet 4.6 |
| VSL scripts, GammaDoc final assembly | Opus 4.6 |
| High-stakes hooks, offer angles | Opus 4.6 |
| Explicit "use Opus on this" from Sabbo | Opus 4.6 |

---

## OpenClaw Default Model

The OpenClaw gateway default is **Haiku 4.5** (`anthropic/claude-haiku-4-5-20251001`).
This means all webchat, Telegram, and heartbeat interactions default to Haiku unless a bot or task explicitly escalates.

---

*Last updated: 2026-02-23*
