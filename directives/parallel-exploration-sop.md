# Parallel Exploration SOP

> Directive: parallel-exploration-sop.md
> Owner: CEO Agent
> Last updated: 2026-03-19

## Purpose

When you need to build something new and aren't sure which approach is best, don't guess. Build 3–5 distinct implementations in isolated temp folders, test them with real data, rate them objectively, then promote the winner.

This is the "3 approaches in temp folders" pattern. It eliminates analysis paralysis and produces a decision backed by real test results — not speculation.

---

## When to Use This Pattern

**Use it when:**
- Integrating a new external API where multiple SDKs or approaches exist
- Choosing between fundamentally different workflow designs (e.g., polling vs. webhooks, sync vs. async)
- Building a new scraping strategy where selector approach, rate limiting, and anti-bot handling are unknown
- Selecting between data formats or storage backends for a new feature
- Any task where "it depends" is the honest answer and the tradeoffs aren't obvious upfront

**Do NOT use it when:**
- A directive already covers this exact task — follow the directive
- An existing script in `execution/` handles it — extend it, don't compete with it
- The task is simple and the approach is obvious (1–2 hour work or less)
- You're fixing a bug — debug the existing path, don't explore alternatives
- Sabbo has already specified the approach — execute the specified approach

---

## Folder Structure

Each exploration lives in `.tmp/explore/`:

```
.tmp/explore/
├── approach-1/
│   ├── README.md          ← What this approach is, hypothesis, tradeoffs
│   ├── run.py             ← Self-contained implementation
│   ├── test_data/         ← Real inputs (never model-generated)
│   └── results.md         ← Timing, output samples, error log, rating
├── approach-2/
│   └── ...
├── approach-3/
│   └── ...
└── decision.md            ← Final comparison table + winner declaration
```

Each `approach-N/` folder is fully self-contained. No shared code between approaches — isolation is the point.

---

## Building Each Approach

### README.md (write first, before any code)

```markdown
# Approach {N}: {Name}

## Hypothesis
{One sentence: why might this be the best approach?}

## Method
{2–3 sentences: what does this approach actually do?}

## Expected tradeoffs
- Speed: {fast/medium/slow — why?}
- Reliability: {high/medium/low — why?}
- Cost: {free/cheap/expensive — why?}
- Complexity: {low/medium/high — why?}
```

### run.py requirements

- Accepts `--input` and `--output` flags (or hardcodes paths relative to its own folder)
- Runs completely standalone: `python .tmp/explore/approach-1/run.py`
- Includes timing: prints elapsed time on completion
- Handles its own errors — don't let one approach crash the comparison session
- Uses real credentials from `.env` if needed (read via `python-dotenv` or `os.environ`)

### test_data/

Use real inputs, not invented ones. For example:
- A real ASIN for a sourcing approach
- A real business URL for a scraping approach
- A real CSV sample for a data processing approach

If real data isn't available yet, use the smallest realistic synthetic sample and document that it's synthetic in `results.md`.

---

## Running the Exploration

Run all approaches sequentially (or in parallel if they're independent and fast):

```bash
cd /Users/Shared/antigravity/projects/nomad-nebula

# Run each approach
python .tmp/explore/approach-1/run.py 2>&1 | tee .tmp/explore/approach-1/results.md
python .tmp/explore/approach-2/run.py 2>&1 | tee .tmp/explore/approach-2/results.md
python .tmp/explore/approach-3/run.py 2>&1 | tee .tmp/explore/approach-3/results.md
```

After each run, record in that approach's `results.md`:
- Actual elapsed time
- Output sample (first 10 results or equivalent)
- Any errors encountered
- Rating scores (see below)

---

## Rating Rubric

Rate each approach on four dimensions, each 1–5:

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| **Speed** | >60s for typical input | 10–60s | <10s |
| **Reliability** | Fails on edge cases, retries needed | Handles most cases, minor gaps | Handles all tested cases, robust error handling |
| **Cost** | Paid API calls per run, adds up quickly | Occasional paid calls, acceptable | Free or negligible cost per run |
| **Complexity** | Hard to read, hard to maintain, many moving parts | Moderate — understandable with context | Simple, obvious, easy to extend |

**Total score = sum of four dimensions (max 20)**

Also note any disqualifying factors that override the score:
- Requires an API key we don't have
- Violates a Learned Rule in `.claude/CLAUDE.md`
- Produces output format incompatible with downstream scripts

---

## decision.md Format

```markdown
# Exploration Decision — {Task Name}
Date: YYYY-MM-DD

## Approaches Tested

| Approach | Speed | Reliability | Cost | Complexity | Total | Notes |
|---|---|---|---|---|---|---|
| Approach 1: {name} | 4 | 3 | 5 | 4 | 16 | Fast but fragile on empty results |
| Approach 2: {name} | 2 | 5 | 3 | 3 | 13 | Most reliable, slowest |
| Approach 3: {name} | 3 | 4 | 5 | 5 | 17 | **WINNER** |

## Winner: Approach 3 — {Name}

### Why
{2–3 sentences explaining the winning choice in plain language}

### What the losers taught us
- Approach 1: {one concrete learning from why it lost}
- Approach 2: {one concrete learning from why it lost}

## Next steps
- Promote `approach-3/run.py` to `execution/{final_name}.py`
- Create or update directive `directives/{name}-sop.md`
- Delete `.tmp/explore/`
```

---

## Promoting the Winner

1. Copy `approach-N/run.py` to `execution/{final_script_name}.py`
2. Clean up the script: remove exploration scaffolding, add proper argparse, add docstring
3. Check if a directive already exists in `directives/` for this task:
   - If yes: update it to reflect what was learned from the exploration
   - If no: create `directives/{name}-sop.md` following the standard directive format
4. Add the new script to the appropriate capability row in `.claude/CLAUDE.md`
5. Delete the entire `.tmp/explore/` directory
6. Log in `SabboOS/CHANGELOG.md`: what was built, which approach won, why

---

## Documenting What the Losers Taught

The losing approaches aren't waste — they're data. Before deleting `.tmp/explore/`, extract learnings:

- If a loser revealed an API quirk → add to the winning directive's `## Known Issues` section
- If a loser exposed a rate limit → document exact limit and backoff strategy in directive
- If a loser showed a data format incompatibility → add a note to the relevant script's docstring
- If a loser's approach might be better for a different input scale → note it in directive's `## When to Use` section

---

## Known Issues

- Parallel approach execution can hit rate limits if all approaches call the same external API simultaneously. Stagger starts by 2–3 seconds if using the same API endpoint.
- `.tmp/explore/` is excluded from git by `.gitignore` — don't put anything there you want to keep. Promote winners before deleting.

## Learnings <!-- updated: 2026-03-19 -->

### 2026-03-19 — Initial directive creation
- Pattern sourced from Nick Saraev's "3 approaches in temp folders" technique
- Rating rubric calibrated to nomad-nebula's typical workloads (FBA sourcing, scraping, API integrations)
- Loser documentation section added because losing approaches consistently revealed API quirks not visible from docs alone
