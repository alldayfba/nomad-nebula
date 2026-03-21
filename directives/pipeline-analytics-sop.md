# Pipeline Analytics SOP
> directives/pipeline-analytics-sop.md | Version 1.0

---

## Purpose

Track full sales funnel data for both businesses. Identify the single biggest bottleneck by comparing each step's conversion rate against benchmarks. Feed real data into the CEO constraint waterfall instead of manual paste.

---

## Trigger

- CEO daily brief (Step 2 — automated KPI check)
- User says "what's the bottleneck?" or "funnel report"
- Weekly review cycle
- Any time pipeline data needs analysis

---

## Script

`execution/pipeline_analytics.py`

**DB:** `.tmp/analytics/pipeline.db`

---

## Commands

### Import funnel data
```bash
python execution/pipeline_analytics.py import --step leads --count 50 --date 2026-02-21 --business agency
```
Valid steps: `leads`, `icp_qualified`, `emails_sent`, `replies`, `calls_booked`, `shows`, `closes`, `revenue`

### Weekly report (conversion rates per step)
```bash
python execution/pipeline_analytics.py report --period weekly
python execution/pipeline_analytics.py report --period monthly --business coaching
```

### Find the bottleneck
```bash
python execution/pipeline_analytics.py bottleneck
python execution/pipeline_analytics.py bottleneck --business agency
```
Returns the single funnel step with the largest negative gap vs benchmark.

### View raw funnel
```bash
python execution/pipeline_analytics.py funnel --business agency --period monthly
```

### Export
```bash
python execution/pipeline_analytics.py export --format json
python execution/pipeline_analytics.py export --format csv
```

---

## Benchmarks (Hardcoded Defaults)

### Agency
| Step | Benchmark |
|---|---|
| leads → icp_qualified | 40% |
| icp_qualified → emails_sent | 90% |
| emails_sent → replies | 5% |
| replies → calls_booked | 30% |
| calls_booked → shows | 65% |
| shows → closes | 20% |

### Coaching
| Step | Benchmark |
|---|---|
| leads → icp_qualified | 35% |
| icp_qualified → emails_sent | 90% |
| emails_sent → replies | 8% |
| replies → calls_booked | 35% |
| calls_booked → shows | 65% |
| shows → closes | 25% |

---

## CEO Integration

The CEO brief (Step 2) checks `bottleneck` output before asking for manual data. The constraint waterfall uses real conversion rates when available.

---

## Self-Annealing

- If benchmarks are consistently beaten: raise them (Sabbo approval)
- If a step has no data: flag it in the brief as "no data — populate before next cycle"
- If import fails: check step name spelling, ensure date format is YYYY-MM-DD

---

*Pipeline Analytics SOP v1.0 — 2026-02-21*
