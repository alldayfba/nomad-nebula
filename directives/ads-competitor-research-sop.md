# Ads Competitor Research SOP
> directives/ads-competitor-research-sop.md | Version 1.0

---

## Purpose

Systematically monitor competitor ad activity on Meta to surface what's working in the market before spending a dollar testing it ourselves.

Long-running ads = proven winners. New ads = market testing. Paused ads = failed tests. This is the signal.

---

## When to Run

- **Automatically:** Every morning at 08:00 (triggered by heartbeat or cron)
- **On-demand:** When Sabbo asks for competitive intel on a specific player

---

## Inputs

| Input | Source | Required |
|---|---|---|
| Competitor list — Agency | `bots/ads-copy/tools.md` → Competitor targets | Yes |
| Competitor list — Coaching | `bots/ads-copy/tools.md` → Competitor targets | Yes |
| Date range | Last 30 days (default) | Yes |

---

## Process

### Step 1 — Run the Scraper

```bash
source .venv/bin/activate
python execution/scrape_competitor_ads.py --business agency --output .tmp/ads/agency_competitors.json
python execution/scrape_competitor_ads.py --business coaching --output .tmp/ads/coaching_competitors.json
```

### Step 2 — Analyze Output

For each competitor, identify:

1. **Longest-running ad** — This is their current winner. Study the hook, angle, and format.
2. **Newest ads** — What are they currently testing? What angles are they exploring?
3. **Paused/missing ads** — What did they try that didn't work?
4. **Format breakdown** — What % is video vs. static vs. carousel?
5. **Hook patterns** — What type of opening line appears most across their ads?

### Step 3 — Extract Insights

For each finding, ask:
- What pain point is this ad targeting?
- What promise or mechanism is it leading with?
- What's the CTA and where does it go?
- Is this angle something we should be running or testing?

### Step 4 — Update Memory

Append findings to `bots/ads-copy/memory.md` → Competitor Intelligence Log.

### Step 5 — Write the Morning Briefing

Format: see `directives/morning-briefing-sop.md`.

---

## Output

- Raw data: `.tmp/ads/[business]_competitors.json`
- Processed intelligence: `bots/ads-copy/memory.md` → Competitor Intelligence Log
- Briefing: sent via delivery method in `bots/ads-copy/tools.md`

---

## Key Heuristics

| Signal | Interpretation |
|---|---|
| Ad running 30+ days | Winner — study and model it |
| Ad running 7–14 days | Still testing — watch next week |
| Ad running < 7 days | Too early to call |
| Same hook across 3+ creatives | Core angle for this competitor |
| High volume of new ads | Scaling phase — they found something |
| Very few active ads | Either coasting or pulling back |

---

## Known Issues

- Meta Ad Library does not expose impression data — use run duration as a proxy for performance
- Some advertisers run ads through agencies with different page names — manually verify attribution
- If a competitor's page has no active ads, note it but don't assume they've stopped — they may be using different pages

---

## Self-Annealing Notes

*Update this section when you discover new constraints, edge cases, or better approaches.*

---

*Last updated: 2026-02-20*
