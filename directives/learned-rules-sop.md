# Self-Modifying Agent Instructions SOP
> directives/learned-rules-sop.md | Version 1.0

---

## Purpose

Agents accumulate learned rules over time, driving error rates toward zero. Instead of repeating the same mistakes, each correction becomes a permanent rule that persists across sessions.

---

## How It Works

Every CLAUDE.md / AGENTS.md / GEMINI.md has a `## Learned Rules` section at the bottom. When the agent makes an error or the user corrects it, a new numbered rule is appended immediately — not at the end of the session, not in a batch, but right then.

---

## When to Append a Rule

Append a learned rule when:
1. **User explicitly corrects output** — "No, don't do X" or "I prefer Y"
2. **User rejects a file, approach, or pattern** — "That's not how we do it"
3. **A bug is caused by a wrong assumption** — e.g., assumed an API returns JSON but it returns XML
4. **User states a preference** — "Always use light mode" or "Never use emojis"
5. **An error is resolved and the fix is generalizable** — rate limit hit → add backoff

Do NOT append a rule when:
- The correction is one-off and context-specific (e.g., typo fix)
- The information is already in a directive
- The rule would contradict an existing directive (update the directive instead)

---

## Rule Format

```
[rule_number]. [CATEGORY] Always/Never [do X] because [Y].
```

### Categories
- `FRONTEND` — UI, design, styling preferences
- `BACKEND` — Server, API, database patterns
- `COPY` — Writing style, tone, format
- `WORKFLOW` — Process, order of operations
- `TOOLING` — Which tools/scripts to use or avoid
- `DATA` — Data handling, formats, schemas
- `SECURITY` — Auth, secrets, permissions
- `GENERAL` — Anything else

### Examples
```
1. [FRONTEND] Never use dark mode for client-facing sites because Sabbo prefers light themes.
2. [WORKFLOW] Always run ICP filter before generating emails because unfiltered leads waste API tokens.
3. [BACKEND] Always use retry with exponential backoff on Google Sheets API because it rate-limits at 60 req/min.
4. [COPY] Never use "Dear" in cold emails because it reads as spam.
```

---

## Execution

### Manual (Agent inline)
When the agent detects a correction or error, it appends the rule directly to the `## Learned Rules` section of the relevant instruction file.

### Scripted
```bash
python execution/append_learned_rule.py \
  --file .claude/CLAUDE.md \
  --category FRONTEND \
  --rule "Never use dark mode" \
  --reason "User preference from 2026-03-15"
```

The script:
1. Reads the target file
2. Finds `## Learned Rules` section
3. Determines next rule number
4. Checks for duplicates (fuzzy match against existing rules)
5. Appends the new rule
6. Writes the file back

---

## Coexistence with Training Officer

| Change Type | Mechanism |
|---|---|
| Preference / pattern / small fix | Learned Rules (direct append) |
| New script / agent upgrade / architecture change | Training Officer (proposal → approval) |
| Directive rewrite | Training Officer (proposal → approval) |

Learned Rules are lightweight. Training Officer is heavyweight. Both compound knowledge.

---

## Meta-Prompt (Add to CLAUDE.md)

```markdown
## Self-Modifying Rules Protocol
When the user corrects you, rejects an approach, or you hit a bug from a wrong assumption:
1. Fix the immediate issue
2. Append a new rule to the ## Learned Rules section below
3. Format: `[number]. [CATEGORY] Always/Never do X because Y.`
4. Rules are numbered sequentially — check the last number before appending
5. Check for duplicates — don't add a rule that already exists
```

---

## Maintenance

- **Monthly review:** Scan rules for conflicts or obsolete entries. Remove or merge.
- **Cap:** If rules exceed 50, archive low-frequency rules to `CLAUDE_ARCHIVE.md`
- **Conflicts:** If a learned rule contradicts a directive, the directive wins. Update or remove the rule.
