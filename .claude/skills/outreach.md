---
name: outreach
description: Run parallel browser agents to fill out contact forms on lead websites
trigger: when user says "contact form outreach", "browser outreach", "fill out contact forms", "parallel outreach"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Parallel Browser Outreach

## Directive
Read `directives/parallel-outreach-sop.md` for the full SOP before proceeding.

## Goal
Spawn multiple headless Chrome browsers to navigate to lead websites, find contact forms, and fill them out with personalized messages.

## Inputs
| Input | Required | Default |
|---|---|---|
| input CSV | Yes | — (CSV with `website` column) |
| max-browsers | No | 3 |
| message-template | No | `outreach_intro` |
| dry-run | No | true (always dry-run first) |

## Templates
- `outreach_intro` — General growth agency intro
- `outreach_audit` — Audit lead-in
- `outreach_fba` — FBA coaching outreach

## Execution

**ALWAYS dry-run first:**
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/parallel_outreach.py --input "{csv_path}" --max-browsers 3 --dry-run
```

After reviewing screenshots in `.tmp/outreach/screenshots/`:
```bash
python execution/parallel_outreach.py --input "{csv_path}" --max-browsers 5 --message-template outreach_intro
```

With visible browsers:
```bash
python execution/parallel_outreach.py --input "{csv_path}" --max-browsers 3 --visible --dry-run
```

## Safety
1. ALWAYS dry-run first — check screenshots before going live
2. Start with 2-3 browsers, scale after verification
3. Screenshots saved for every step in `.tmp/outreach/screenshots/`

## Self-Annealing
If execution fails:
1. Check Playwright: `playwright install chromium`
2. If forms aren't detected, the AI analysis may need a longer wait time
3. Fix the script, update `directives/parallel-outreach-sop.md`
4. Log fix in `SabboOS/CHANGELOG.md`
