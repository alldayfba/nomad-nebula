# Agent Training SOP
> directives/agent-training-sop.md | Version 1.0

---

## Purpose

Setting up a new bot is like onboarding a new employee. If you rush it, the output is garbage. If you invest 1–2 weeks upfront, you get a fully functional operator that runs without you.

Kabrin's first bot took a full week. His second and third took less than 24 hours each. The investment compounds.

---

## Pre-Requisites Before Starting

- [ ] You understand agentic workflows (watch the 6-hour video in the Artisan Lab resources)
- [ ] You know exactly what role this bot will play (specific, not vague)
- [ ] You have the training files ready (SOPs, course material, brand docs)
- [ ] The hardware is set up (Mac Mini or always-on PC, separate user profile)

If any of these aren't done, stop here and complete them first.

---

## Phase 1 — Define the Role (Day 1)

Before touching any config file:

1. Write a one-paragraph description of what this bot does, what it doesn't do, and how you'll measure if it's working
2. Identify its primary LLM tier (Gemini Pro for most bots — see `directives/api-cost-management-sop.md`)
3. Identify its tools access — be as restrictive as possible (read-only is always safer)
4. Name it. The name helps you think of it as a specialized role, not a general chatbot.

Output: draft `bots/[bot-name]/identity.md`

---

## Phase 2 — Feed It Materials (Days 1–3)

This is the scraping and ingestion phase. The bot needs raw material to become an expert.

### What to feed it

For a copywriting/ads bot:
- Every copywriting course or SOP you have (Daniel Fazio, Jeremy Haynes, etc.)
- Your own best-performing copy (with notes on why it worked)
- Brand voice guides for all clients
- Competitor ad analysis

For a content bot:
- Content frameworks and SOPs
- Examples of top-performing posts in your niche
- Brand voice guides

For the COO:
- Full business OS (SabboOS files)
- KPI tracking sheets
- Historical performance data

### How to ingest

```bash
# Drop files in uploads folder
cp /path/to/doc.md /Users/Shared/antigravity/memory/uploads/

# Run ingestion
source .venv/bin/activate
python execution/ingest_docs.py
```

Or use the auto-watch mode:
```bash
python execution/ingest_docs.py --watch &
```

### Let it scrape

Where applicable, instruct the bot to scrape additional context:
- Client YouTube channels and Instagram profiles → brand voice files
- Competitor websites → positioning intel
- Relevant courses or communities (if you have access)

This is the phase where most of the value is built. Don't skip it.

---

## Phase 3 — Build Skills and Memory Files (Days 3–5)

Once the raw material is ingested, build the structured files:

1. **skills.md** — Map each task type to the SOPs and training files it should reference
2. **memory.md** — Set up the log structure (approved work, rejected work, learnings)
3. **heartbeat.md** — Define the check frequency and task queue format
4. **tools.md** — Lock down exactly what it can and can't access

At this point, run test tasks:
- Give it a simple task (write one ad variant)
- Review the output critically — does it reflect the SOPs you fed it?
- Give explicit feedback: "This is good because X" or "This is wrong because Y"
- Log the feedback in `memory.md`

---

## Phase 4 — First Supervised Week (Days 5–10)

Do not let the bot run fully autonomously yet.

- Review every output before it goes anywhere
- Give specific feedback on every piece (not just "looks good" — that teaches it the wrong standard)
- Update `memory.md` with each approved and rejected item
- Watch the output quality trend — it should improve noticeably by day 7

This is the quality-control phase. Kabrin's point: if you approve bad work, the bot learns that's the standard. Be rigorous.

---

## Phase 5 — Autonomous Operation (Day 10+)

Once output quality is consistent:
- Set the heartbeat to run on schedule
- Enable the morning briefing or other automated tasks
- Shift from reviewing every piece to spot-checking (sample 20% of output)
- Update `memory.md` when you catch something off

The bot is now running. Your job is pure quality control.

---

## Ongoing Maintenance

- When a new SOP is written, run `ingest_docs.py` to add it to memory
- When a client is added, create `bots/clients/[client-name].md`
- When output quality drifts, increase spot-check rate and add more feedback to `memory.md`
- When Sabbo's business evolves, update `identity.md` to reflect the new priorities

---

## Red Flags During Onboarding

| Symptom | Cause | Fix |
|---|---|---|
| Generic, bland output | Not enough training material ingested | Add more SOPs, run ingest again |
| Ignores brand voice | Client profile not created or not referenced | Build `bots/clients/[client].md` |
| Keeps asking questions | Skills file doesn't map tasks to SOPs | Improve `skills.md` |
| High API costs | Opus used for routine tasks | Fix LLM routing, see API cost SOP |
| Context "forgotten" | Not reading heartbeat or memory correctly | Check heartbeat.md format and reference |

---

*Last updated: 2026-02-20*
