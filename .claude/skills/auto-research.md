---
name: auto-research
description: Set up a self-improving experiment pipeline for any metric (cold email, ads, landing pages, listings)
trigger: when user says "auto research", "self-improving", "experiment pipeline", "optimize automatically", "A/B test loop"
tools: [Bash, Read, Write, Edit, Glob, Grep, WebFetch]
---

# Auto Research — Self-Improving Pipeline

## Directive
Read `directives/auto-research-sop.md` for the full pattern before proceeding.

## Goal
Set up an autonomous experimentation pipeline that continuously improves a metric. Based on Karpathy's auto-research pattern: hypothesis → experiment → measure → keep/discard → accumulate learnings → repeat.

## Inputs
| Input | Required | Default |
|---|---|---|
| goal_metric | Yes | — (e.g., "reply rate", "CTR", "conversion rate") |
| platform | Yes | — (e.g., "instantly", "meta", "vercel", "amazon") |
| changeable_input | Yes | — (e.g., "email copy", "ad hook", "headline") |
| loop_interval | No | "4h" (how often to run the loop) |
| api_credentials | Yes | — (API key for the platform) |

## Execution

### Step 1: Create pipeline directory
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula
mkdir -p execution/auto-research/{optimizer-name}/experiments
```

### Step 2: Build the orchestrator
Create `orchestrator.py` following the pattern in `directives/auto-research-sop.md`:
- Harvest previous results via platform API
- Pick winner (baseline vs challenger)
- Log learnings to `resources.md`
- Generate new challenger using accumulated learnings
- Deploy new experiment
- Send Slack notification

### Step 3: Build the platform client
Create `{platform}_client.py` with API wrapper methods:
- `create_campaign()` / `create_experiment()`
- `get_metrics()` — fetch objective metric
- `pause_campaign()` / `archive_experiment()`

### Step 4: Create baseline + config
- `baseline.md` — current best-performing version
- `config.yaml` — API keys, settings, loop interval
- `resources.md` — empty initially, grows with learnings

### Step 5: Add to scheduled-skills.yaml
```yaml
- skill: auto-research-{name}
  cron: "0 */4 * * *"  # every 4 hours
  script: execution/auto-research/{name}/orchestrator.py
  auto_run: true
```

### Step 6: Test with dry run
```bash
python execution/auto-research/{name}/orchestrator.py --dry-run
```

## Output
- Complete pipeline directory ready to run on autopilot
- Slack notifications on every harvest
- `resources.md` that grows smarter with every experiment

## Self-Annealing
If execution fails:
1. Check API credentials in `config.yaml`
2. Check if platform API has changed — update client
3. Never lose experiment data — all logged to `experiments/`
4. Fix the script, update `directives/auto-research-sop.md` Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
