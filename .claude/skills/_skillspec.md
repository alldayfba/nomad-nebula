# Skill Spec — nomad-nebula

> Reference document for building and maintaining Claude Code skills. NOT a skill itself.

## File Format

```markdown
---
name: skill-name
description: One-line description
trigger: when user says "phrase1", "phrase2", "phrase3"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Skill Title

## Directive
Read `directives/<name>-sop.md` for the full SOP before proceeding.

## Goal
One sentence.

## Inputs
| Input | Required | Default |
|---|---|---|
| param1 | Yes | — |
| param2 | No | value |

## Execution
\```bash
source .venv/bin/activate
python execution/<script>.py --arg1 "{param1}"
\```

## Output
What gets produced and where it goes.

## Self-Annealing
If execution fails:
1. Read the error message and stack trace
2. Fix the script in `execution/`
3. Update the directive's Known Issues section
4. Re-run the command
5. Log the fix in `SabboOS/CHANGELOG.md`
```

## Architecture

Skills are **thin routing layers** in the DOE framework:
- **Skill** = router (tells agent what to read and run)
- **Directive** = SOP (the authoritative instructions in `directives/`)
- **Execution** = script (deterministic Python in `execution/`)

Skills reference directives at runtime — never duplicate content. When a directive updates, the skill automatically picks up changes.

## Location

- Project skills: `.claude/skills/` (this directory)
- Global skills: `~/.claude/skills/`

## Naming

- `kebab-case.md` matching directive name minus `-sop` suffix
- Example: `directives/lead-gen-sop.md` → `.claude/skills/lead-gen.md`

## Input Patterns

- **Pattern A (minimal):** 0-1 params, skill just runs the script
- **Pattern B (structured):** 2-5 params, ask user for missing required inputs
- **Pattern C (complex):** Conditional routing based on user intent (e.g., sourcing modes)

## Virtual Environment

Every skill activates `.venv/bin/activate` before running scripts:
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
```

## Invocation

Users invoke skills via `/skill-name` in Claude Code:
```
/lead-gen
/cold-email
/source-products
```

## Agent Ownership

Every skill is owned by exactly one agent. The mapping lives in `directives/agent-routing-table.md` → Skill → Agent Mapping.

When a new skill is created:
1. Training Officer auto-detects it during daily scan (Step 2.5)
2. Matches the skill's directive to the agent routing table
3. Assigns ownership to the corresponding agent
4. Adds a reference to `bots/<agent>/skills.md`
5. Generates a Training Proposal for Sabbo's approval

## Self-Improvement Loop

Skills get smarter every time they run:

1. **Self-Annealing:** When a skill fails, it fixes the script, updates the directive, and patches its own Self-Annealing section with the new failure pattern
2. **User Feedback:** When Sabbo gives feedback on a skill's output, the CEO queues a skill upgrade for the Training Officer
3. **Directive Sync:** When a directive updates, the skill automatically picks up changes (since it reads the directive at runtime)
4. **Agent Learning:** The owning agent's memory and skills files compound learnings from skill runs
5. **Training Officer Monitoring:** TO tracks skill health (run count, error rate, last run) and proposes upgrades when quality drops

## Creating New Skills

When a repeatable workflow is identified:
1. Check if a directive exists in `directives/` → create one if not
2. Check if an execution script exists in `execution/` → create one if not
3. Create the skill file following this spec
4. Test end-to-end at least once
5. The Training Officer will auto-assign it to the right agent on next scan
