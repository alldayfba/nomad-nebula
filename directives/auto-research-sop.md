# Auto Research SOP — Self-Improving Experiment Pipeline
> directives/auto-research-sop.md | Version 1.0
> Inspired by Karpathy's Auto Research pattern

---

## Purpose

Build autonomous experimentation pipelines that continuously improve a metric by testing hypotheses in a tight loop. The system runs 24/7 with zero human involvement — you wake up to a log of experiments and better results.

---

## Core Pattern

```
1. BASELINE    → Current best-performing version
2. HYPOTHESIS  → "If I change X, metric Y will improve because Z"
3. CHALLENGER  → AI-modified variant based on hypothesis
4. DEPLOY      → Run both baseline + challenger side by side
5. MEASURE     → Collect metric after N hours
6. HARVEST     → Winner becomes new baseline, loser discarded
7. LEARN       → Log what worked/didn't to resources.md
8. REPEAT      → Next challenger uses accumulated learnings
```

---

## Requirements

To build an auto-research pipeline, you need exactly 3 things:

| Requirement | Description | Example |
|---|---|---|
| **Objective metric** | A number you can track | Reply rate, CTR, conversion rate, BSR |
| **Changeable input** | Something the AI can modify | Email copy, headline, ad hook, price, description |
| **API access** | Way to deploy + measure programmatically | Instantly API, Meta API, Vercel Analytics, SP-API |

If you don't have all 3, this pattern won't work. Find proxies or build Chrome DevTools MCP flows.

---

## Pipeline Directory Structure

```
execution/auto-research/{optimizer-name}/
├── orchestrator.py       ← Main loop (harvest → generate → deploy → schedule)
├── {platform}_client.py  ← API wrapper for the platform
├── config.yaml           ← API keys, loop interval, settings
├── baseline.md           ← Current best-performing version
├── resources.md          ← Accumulated learnings (grows over time)
├── experiments/           ← Log of all experiments
│   ├── exp_001.json
│   ├── exp_002.json
│   └── ...
└── README.md             ← Setup instructions
```

---

## Orchestrator Loop (runs every N hours)

```python
# Pseudocode for orchestrator.py

def run_cycle():
    # 1. HARVEST previous experiment
    results = platform_client.get_metrics(active_experiment_id)
    winner = pick_winner(results)  # baseline or challenger
    update_baseline(winner)
    log_experiment(results)

    # 2. LEARN from results
    learnings = analyze_results(results)
    append_to_resources(learnings)

    # 3. GENERATE new challenger
    challenger = generate_challenger(
        baseline=load_baseline(),
        resources=load_resources(),
        hypothesis=generate_hypothesis()
    )

    # 4. DEPLOY new experiment
    experiment_id = platform_client.create_experiment(
        baseline=load_baseline(),
        challenger=challenger
    )

    # 5. NOTIFY
    send_slack_notification(experiment_id, results)
```

---

## Best Practices

### Fast Feedback Loops
- **Ideal:** 5 minutes (like Karpathy's ML training)
- **Good:** 1-4 hours (cold email, ads)
- **Okay:** 1 day (landing pages, pricing)
- **Slow:** 1 week (Amazon listings, SEO)
- Faster loops = faster improvement

### Clear Metrics
- Reply rate (cold email) — objective, tracked automatically
- CTR / CPA (ads) — objective, from Meta API
- Conversion rate (landing pages) — objective, from analytics
- Avoid fuzzy metrics like "warmth" or "brand perception"

### Knowledge Accumulation
- `resources.md` is the compound interest engine
- Every experiment adds learnings: "Short subject lines (+3.2% reply rate)"
- After 50+ experiments, the AI has a rich knowledge base for generating better challengers
- Consolidate resources.md every 100 experiments to prevent bloat

### Guardrails
- Never test more than ONE variable at a time
- Always have a minimum sample size before harvesting
- Set maximum deviation limits (challenger can't be 100% different from baseline)
- Slack notifications on every harvest so you can intervene if needed

---

## Available Implementations

### Internal (System Self-Improvement)

| Optimizer | Metric | What it optimizes | Status |
|---|---|---|---|
| Memory Quality | Composite health score (recall, categorization, freshness, dedup) | FTS5 weights, category taxonomy, dead-weight archiving | **ACTIVE** |
| Skill Quality | Execution success rate (completions without corrections) | Skill prompts, directive links, telemetry | **ACTIVE** |
| Growth Engine | System health (script health, pipeline data, sourcing, coverage) | Script fixes, pipeline tracking, sourcing strategy | **ACTIVE** |

### External (Business Metrics)

| Optimizer | Metric | Platform | Status |
|---|---|---|---|
| Cold Email | Reply rate | Instantly | Ready to build |
| Landing Page | Conversion rate | Vercel/Netlify | Planned |
| Ad Creative | CTR / CPA | Meta Ads | Planned |
| Amazon Listing | Conversion rate | Seller Central | Planned |

---

## Architecture

```
execution/auto-research/
├── experiment_runner.py          ← Shared base class (Karpathy loop)
├── meta_orchestrator.py          ← Runs all optimizers + cross-pollinates
├── correction_capture.py         ← Captures user corrections as negative signals
├── run_meta_cycle.sh             ← launchd trigger script
├── maintenance_daily.sh          ← Daily memory maintenance
├── memory-optimizer/
│   ├── orchestrator.py           ← Recategorize, merge dupes, archive dead weight
│   ├── baseline.md               ← Current config (FTS5 weights, taxonomy)
│   ├── resources.md              ← Accumulated learnings
│   ├── results.tsv               ← Experiment log
│   └── experiments/              ← JSON per experiment
├── skill-optimizer/
│   ├── orchestrator.py           ← Skill health, directive coverage, telemetry
│   ├── telemetry.json            ← Skill execution scores + corrections
│   ├── baseline.md
│   ├── resources.md
│   └── experiments/
└── growth-optimizer/
    ├── orchestrator.py           ← Pipeline data, sourcing health, script health
    ├── outcomes.json             ← Business outcome tracking
    ├── baseline.md
    ├── resources.md
    └── experiments/
```

---

## Scheduling

**launchd (active):**
- `com.sabbo.auto-research` — every 4 hours, runs meta_orchestrator.py
- `com.sabbo.memory-maintenance` — daily at 4 AM, runs maintenance + brain.md export

**scheduled-skills.yaml (active):**
- `auto-research-meta` — every 4 hours via scheduled skills runner
- `auto-research-memory` — 2 AM daily, 5 extra cycles overnight

---

## Correction Capture

When Sabbo corrects the system:
```bash
python execution/auto-research/correction_capture.py \
    --correction "Memory search returned wrong results" \
    --skill "lead-gen" --score 4
```
This propagates the correction to all 3 optimizers as a negative signal.

---

## Cross-Optimizer Learning

After each meta cycle, learnings are shared:
- Memory optimizer discovers something → skill + growth optimizers get it in resources.md
- Growth optimizer finds a broken script → memory stores it as an error
- All experiment results → memory.db as type=learning

---

## Self-Annealing

If the orchestrator fails:
1. Read the error → fix the API call or script
2. Never lose experiment data — all results logged to `experiments/`
3. If platform API changes, update `{platform}_client.py`
4. Update this SOP's Known Issues section
5. Log fix in `SabboOS/CHANGELOG.md`

---

*Last updated: 2026-03-16*
