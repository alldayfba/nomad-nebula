---
name: content-engine
description: Generate platform-native organic content, calendars, and repurpose long-form into short-form
trigger: when user says "generate content", "content calendar", "repurpose", "content ideas", "write a post"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Content Engine

## Directive
Read `directives/content-engine-sop.md` for the full SOP before proceeding.

## Goal
Generate platform-native organic content for both businesses. Supports single-topic generation, multi-week calendars, long-form repurposing, and ICP-driven idea generation.

## Inputs
Depends on the action:

**Generate content:** topic (required), platforms (required), business (required)
**Calendar:** weeks, frequency, business
**Repurpose:** input file, target platforms
**Ideas:** business, count

## Commands

### Generate platform-native content
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/content_engine.py generate --topic "{topic}" --platforms {platforms} --business {business}
```

Supported platforms: `instagram` (carousel), `linkedin` (post), `twitter` (thread), `youtube` (script outline), `tiktok` (script), `short-form` (reel script)

### Build a content calendar
```bash
python execution/content_engine.py calendar --weeks {weeks} --frequency {per_week} --business {business}
```

### Repurpose long-form into short-form
```bash
python execution/content_engine.py repurpose --input {input_file} --platforms short-form,instagram
```

### Generate topic ideas
```bash
python execution/content_engine.py ideas --business {business} --count 10
```

## Output
- Content files in `.tmp/content/`
- Calendar as JSON with topics, platforms, formats, hook lines per day

## Self-Annealing
If execution fails:
1. Check `ANTHROPIC_API_KEY` in `.env`
2. For repurpose, verify input file exists and is readable
3. Fix the script, update directive Known Issues
4. Log fix in `SabboOS/CHANGELOG.md`
