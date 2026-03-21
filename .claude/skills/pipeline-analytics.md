---
name: pipeline-analytics
description: Track sales funnel conversions and identify the biggest bottleneck
trigger: when user says "funnel report", "bottleneck", "pipeline analytics", "conversion rates", "what's the bottleneck"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Pipeline Analytics

## Directive
Read `directives/pipeline-analytics-sop.md` for the full SOP before proceeding.

## Goal
Track full sales funnel data for both businesses. Identify the single biggest bottleneck by comparing each step's conversion rate against benchmarks.

## Inputs
Depends on the action:

**Bottleneck analysis (most common):** business (optional, defaults to both)
**Import data:** step, count, date, business
**Report:** period (weekly/monthly), business (optional)

## Commands

### Find the bottleneck (default)
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/pipeline_analytics.py bottleneck
python execution/pipeline_analytics.py bottleneck --business agency
```

### Weekly/monthly report
```bash
python execution/pipeline_analytics.py report --period weekly
python execution/pipeline_analytics.py report --period monthly --business coaching
```

### Import funnel data
```bash
python execution/pipeline_analytics.py import --step leads --count 50 --date 2026-03-15 --business agency
```

Valid steps: `leads`, `icp_qualified`, `emails_sent`, `replies`, `calls_booked`, `shows`, `closes`, `revenue`

## Output
- Conversion rates per funnel step vs benchmarks
- Single biggest bottleneck identified with gap analysis
- DB stored at `.tmp/analytics/pipeline.db`

## Self-Annealing
If execution fails:
1. Check if `.tmp/analytics/` directory exists
2. If no data imported yet, prompt user to import baseline numbers first
3. Fix the script, update directive Known Issues
4. Log fix in `SabboOS/CHANGELOG.md`
