# Context Management & Optimization SOP
> directives/context-management-sop.md | Version 1.0

---

## Purpose

The observe step in the agent loop grows every cycle. Without management, context bloat degrades output quality. This SOP defines rules for what goes in, what stays out, and when to compress.

---

## Core Principle

**Minimum effective context:** Include only what the agent needs for its next action. Not everything it might need. Not everything it has seen. Just what's relevant now.

---

## Context Budget by Model

| Model Tier | Task Type | Max Context (tokens) | ~Max Chars |
|---|---|---|---|
| Tier 1 (Haiku/Flash) | Routine | 4,000 | 16K |
| Tier 1 | Classification | 2,000 | 8K |
| Tier 2 (Sonnet/Pro) | Generation | 16,000 | 64K |
| Tier 2 | Code | 32,000 | 128K |
| Tier 2 | Research | 48,000 | 192K |
| Tier 3 (Opus) | High-stakes | 64,000 | 256K |

---

## What to Include

1. **System prompt** — Always (CLAUDE.md, directive for current task)
2. **Current task** — Always
3. **Relevant file contents** — Only files being modified
4. **Previous tool results** — Only the most recent, relevant ones
5. **Learned rules** — Always (they're compact)
6. **Contract** — If applicable to current output

## What to Exclude

1. **Completed sub-tasks** — Compress to 1-line summaries
2. **Irrelevant file contents** — Don't load files you're not editing
3. **Full tool output** — Summarize verbose outputs (e.g., git log, search results)
4. **Old conversation turns** — Compress anything older than 5 turns
5. **Duplicate information** — Same fact in multiple places = waste

---

## When to Compress

Trigger compression when:
- Context exceeds 80% of budget for current model/task
- Conversation exceeds 10 turns
- Multiple large file reads in sequence
- Agent output quality visibly degrades (repetition, hallucination)

---

## brain.md Management

### Active vs Archived
- **Active brain** (`brain.md`): Current session state, recent decisions, active projects. Max 500 lines.
- **Archived brain** (`brain_archive.md`): Compressed historical context. Referenced when needed, not loaded by default.

### Health Check
```bash
python execution/context_optimizer.py brain-health
```

### Auto-Archive
```bash
python execution/context_optimizer.py archive-brain --max-lines 500
```

---

## CLAUDE.md Structure (Optimized for Scanning)

Structure instruction files for optimal agent scanning:

```markdown
## [Section Name]                    ← Agent scans headers first
- **Key rule:** One-line rule here   ← Bold = important
- Supporting detail                  ← Normal = context
```

1. **Critical rules at top** — Most-referenced sections first
2. **Bullet points, not prose** — Agents parse bullets faster than paragraphs
3. **Bold key phrases** — Helps agent attention focus on what matters
4. **Group by topic** — Not chronologically
5. **Archive rarely-used rules** — Move to `CLAUDE_ARCHIVE.md` after 30 days unused

---

## Execution

```bash
# Compress a conversation
python execution/context_optimizer.py compress \
    --input .tmp/conversation.json \
    --output .tmp/compressed.json \
    --keep-last 5

# Check brain health
python execution/context_optimizer.py brain-health

# Archive old brain content
python execution/context_optimizer.py archive-brain --max-lines 500

# Check context budget for a task
python execution/context_optimizer.py budget --tier 2 --task code
```
