---
name: pipeline
description: Run wired end-to-end pipelines with auto-verification and contract validation
trigger: when user says "run pipeline", "full pipeline", "end to end", "run the whole thing"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Pipeline Runner

## Directive
Each pipeline chains existing tools with automatic quality checks.

## Goal
Run multi-step pipelines that auto-verify output quality at each stage.

## Available Pipelines

| Pipeline | Command | What It Does |
|---|---|---|
| `lead-gen` | Scrape → ICP Filter → Email Gen → Verify | Full lead gen with quality checks |
| `sourcing` | Source Products → Profitability → Contract Validate | FBA sourcing with contract validation |
| `creator-refresh` | Check Freshness → Scrape → Video-to-Action → Rebuild Brain | Update creator intelligence |
| `outreach` | Scrape → Filter → Parallel Browser Outreach | Full outreach with browser agents |

## Execution

```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate

# Lead gen pipeline
python execution/pipeline_runner.py lead-gen --query "dentists" --location "Miami FL" --max 30

# Sourcing pipeline
python execution/pipeline_runner.py sourcing --mode brand --brand "Jellycat" --max-results 20

# Creator refresh
python execution/pipeline_runner.py creator-refresh --creator "nick-saraev"

# Outreach (dry-run by default — add --live to submit forms)
python execution/pipeline_runner.py outreach --query "chiropractors" --location "Austin TX" --max 20
```

## Auto-Triggers Within Pipelines
- Lead gen auto-verifies sample emails via verification loop
- Sourcing auto-validates against sourcing_report contract
- Creator refresh auto-runs video-to-action on latest transcript
- Outreach defaults to dry-run for safety

## Self-Annealing
If a step fails, the pipeline logs the error and continues where possible. Check `.tmp/pipeline_*.json` for full logs.
