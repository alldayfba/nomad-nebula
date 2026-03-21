# Agent Execution Loop SOP — PTMRO Pattern
> directives/agent-execution-loop-sop.md | Version 1.0

---

## Purpose

Standardize how ALL agents execute tasks using the 5-step PTMRO pattern: Plan → Tools → Memory → Reflect → Orchestrate. Making this explicit improves consistency across all agents and skills.

---

## The PTMRO Loop

Every agent follows this loop for every task, whether invoked via skill or direct prompt:

### 1. PLAN — Break down the objective
- Decompose the high-level goal into subtasks
- Identify dependencies between steps
- Sequence logically (what must happen first?)
- If planning is poor, everything downstream fails — this is where human input has highest ROI

### 2. TOOLS — Execute with the right instruments
- Check `execution/` for existing scripts before building new ones
- Check MCP servers for platform integrations
- If no tool exists → BUILD one (see Agent Self-Tool-Building Protocol)
- Call APIs, execute code, query databases
- Use the simplest tool that solves the problem

### 3. MEMORY — Store and recall
- **Short-term:** Current conversation context
- **Mid-term:** `.tmp/` files, session snapshots
- **Long-term:** `brain.md`, `resources.md`, bot memory files
- After completing a step, persist results so they survive context compaction
- Check prior work before starting: has this been done before?

### 4. REFLECT — Evaluate and correct
- Did the output match the goal?
- Are there errors or quality issues?
- If output quality < threshold → adjust approach and retry
- Check against prompt contracts if one exists
- Self-anneal: fix errors, update directive, re-run

### 5. ORCHESTRATE — Coordinate and delegate
- If task requires multiple agents → delegate subtasks
- Use scoped subagents (`.claude/agents/`) for parallel work
- Aggregate results from subtasks
- Report final outcome to user or calling agent

---

## When to Apply

- **Every skill invocation** — skills are thin routers, PTMRO is the execution engine
- **Every CEO delegation** — CEO plans, delegates tools/subtasks, reflects on results
- **Every Training Officer scan** — plan what to check, use scan tools, store findings, reflect on quality, orchestrate proposals

---

## Integration

Reference this SOP in:
- `SabboOS/Agents/CEO.md` — Boot Sequence
- `.claude/skills/_skillspec.md` — Skill execution pattern
- All `bots/*/identity.md` files — agent behavior

---

*Last updated: 2026-03-15*
