# Training Officer Bot — Memory
> bots/training-officer/memory.md | Version 1.0

---

## Purpose

This file is your persistent memory. You read it on every scan cycle and update it when proposals are approved, rejected, or when you discover patterns. This is how you improve over time without losing context.

---

## Approved Proposals Log

When Sabbo approves a proposal, log it here. This defines your quality bar for proposals.

Format:
```
### [DATE] — [PROPOSAL ID] — [TARGET AGENT]
What changed: [1-line description]
Why it worked: [Sabbo's feedback or inferred reason]
Pattern to repeat: [what made this proposal good]
```

---

## Rejected Proposals Log

When Sabbo rejects a proposal, log it here. This defines what to avoid.

Format:
```
### [DATE] — [PROPOSAL ID] — [TARGET AGENT]
What was proposed: [1-line description]
Why rejected: [Sabbo's feedback]
What to do differently: [specific correction]
```

---

## Agent Quality Trends

Running log of quality observations across agents. Updated after grading sessions.

Format:
```
### [DATE] — [AGENT NAME]
Quality score: [X/50]
Weak dimensions: [list]
Strong dimensions: [list]
Trend: [improving / stable / declining]
```

---

## Error Pattern Log

Recurring error patterns detected across the system. Each entry informs future proposals.

Format:
```
### [DATE] — [PATTERN NAME]
Agents affected: [list]
Frequency: [how often]
Root cause: [identified or suspected]
Proposal generated: [yes/no — proposal ID if yes]
```

---

## Learnings

Lessons from rejected proposals and system observations that inform future behavior.

Format:
```
### [DATE] — [LEARNING]
Context: [what happened]
Rule: [what to do differently going forward]
```

---

*Last updated: 2026-03-16*
