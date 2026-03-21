---
name: competitor-intel
description: Scrape Meta Ad Library for competitor ad activity and surface winning angles
trigger: when user says "competitor ads", "ad intel", "what are competitors running", "competitor research", "ad library"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Competitor Ad Intelligence

## Directive
Read `directives/ads-competitor-research-sop.md` for the full SOP before proceeding.

## Goal
Scrape Meta Ad Library to surface what's working in the market. Long-running ads = proven winners. New ads = market testing. Paused ads = failed tests.

## Inputs
| Input | Required | Default |
|---|---|---|
| business | No | both (agency + coaching) |
| output path | No | `.tmp/ads/` |

Competitor lists are pre-configured in `bots/ads-copy/tools.md`.

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate

# Agency competitors
python execution/scrape_competitor_ads.py --business agency --output .tmp/ads/agency_competitors.json

# Coaching competitors
python execution/scrape_competitor_ads.py --business coaching --output .tmp/ads/coaching_competitors.json
```

## Analysis (per competitor)
After scraping, identify:
1. **Longest-running ad** — current winner (study hook, angle, format)
2. **Newest ads** — what they're testing now
3. **Paused/missing ads** — what didn't work
4. **Format breakdown** — video vs static vs carousel %
5. **Hook patterns** — most common opening lines

## Output
- JSON files in `.tmp/ads/` with competitor ad data
- Analysis feeds into morning briefing and ad copy generation

## Self-Annealing
If execution fails:
1. Meta Ad Library may rate-limit — add delays between requests
2. If a competitor page structure changes, update scraper selectors
3. If competitor not found, verify their Meta page ID in `bots/ads-copy/tools.md`
4. Fix the script, update directive Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
