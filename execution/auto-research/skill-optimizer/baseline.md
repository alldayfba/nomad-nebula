# Skill Optimizer — Current Baseline Configuration

## Skill System Stats
- Total skills: 27+ in .claude/skills/
- Skills with linked directives: ~70%
- Skills with complete fields (trigger, tools, steps): ~80%

## Quality Standards
- Every skill should reference its directive
- Every skill should have: name, description, trigger, tools, execution steps
- Output should be validated against prompt contracts when available

## Telemetry Scoring
- 10: Perfect output, no corrections needed
- 8-9: Minor formatting/style tweaks only
- 6-7: Needed moderate corrections to content
- 4-5: Significant rework needed
- 1-3: Completely wrong approach

## Known Issues to Monitor
- Skills missing directives need linking
- Orphan directives (SOPs with no skill) need skills created
- Learned rules should consolidate into directives when > 10

## Current Metrics (auto-updated)
- Baseline score: 83.79
- Last updated: 2026-03-16
