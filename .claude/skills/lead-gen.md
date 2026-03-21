---
name: lead-gen
description: Scrape Google Maps for B2B leads matching a query and location, export to CSV
trigger: when user says "find leads", "scrape leads", "lead gen", "prospect list", "find me businesses"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Lead Generation

## Directive
Read `directives/lead-gen-sop.md` for the full SOP before proceeding.

## Goal
Scrape Google Maps for B2B business leads, export results to CSV for outreach pipeline.

## Inputs
| Input | Required | Default |
|---|---|---|
| query | Yes | — (e.g., "roofing companies", "dental clinics") |
| location | Yes | — (e.g., "Austin TX", "Miami FL") |
| max_results | No | 20 |
| fetch_emails | No | true (slower but gets emails from websites) |

Extract these from the user's message. If query or location is missing, ask for them.

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/run_scraper.py --query "{query}" --location "{location}" --max {max_results}
```

Or use the web UI at `http://localhost:5050` if the Flask server is running.

## Output
- `b2b_leads.csv` with columns: business_name, owner_name, category, phone, email, website, address, rating, maps_url

## Next Steps (suggest to user)
1. Filter leads through ICP scorer: `python execution/filter_icp.py --input b2b_leads.csv --threshold 6`
2. Generate emails: `/cold-email` with the filtered CSV
3. Or run business audits: `/business-audit` for high-value prospects

## Self-Annealing
If execution fails:
1. Check if Playwright/Chromium is installed: `playwright install chromium`
2. Check if `.venv` is activated and dependencies installed
3. If rate-limited, reduce `max_results` to under 50
4. Fix the script, update `directives/lead-gen-sop.md` Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
