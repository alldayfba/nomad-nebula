---
name: auto-outreach
description: End-to-end autonomous outreach — scrape leads, filter ICP, generate emails, send. Zero human input after initial prompt.
trigger: when user says "auto outreach", "autonomous outreach", "full pipeline outreach", "scrape and send"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Autonomous Outreach Pipeline


## Directive
Read `directives/outreach-sequencer-sop.md` for the full SOP before proceeding.


## Goal
Chain the full outreach pipeline in one autonomous run: scrape leads → ICP filter → generate personalized emails → (optionally) send. This orchestrates multiple existing skills into one end-to-end flow.

## Pipeline
```
Step 1: /lead-gen → scrape Google Maps for leads
Step 2: filter_icp.py → score and filter by ICP
Step 3: /cold-email → generate personalized emails
Step 4: Review → present results for approval
Step 5: (Optional) Send via SMTP or Instantly API
```

## Inputs
| Input | Required | Default |
|---|---|---|
| query | Yes | — (e.g., "dental clinics") |
| location | Yes | — (e.g., "Miami FL") |
| max_leads | No | 20 |
| icp_threshold | No | 6 |
| auto_send | No | false (always dry-run first) |

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate

# Step 1: Scrape leads
python execution/run_scraper.py --query "{query}" --location "{location}" --max {max_leads}

# Step 2: Filter by ICP
python execution/filter_icp.py --input b2b_leads.csv --threshold {icp_threshold}

# Step 3: Generate emails
python execution/generate_emails.py --input .tmp/filtered_leads_*.csv

# Step 4: Present for review (ALWAYS do this before sending)
# Show: lead count, sample emails, ICP scores

# Step 5: Send (only if auto_send=true AND user confirms)
# Via Instantly API or SMTP
```

## Guardrails
1. **ALWAYS dry-run first** — show results before any sending
2. **Never send without user confirmation** — even if auto_send is set
3. **ICP filter is mandatory** — never email unfiltered leads
4. **Spot-check 3-5 emails** before approving the batch
5. **Rate limit:** Max 50 emails per run

## Output
- Filtered leads CSV with ICP scores
- Email CSV with personalized subject + body
- Summary: {n} leads scraped → {n} passed ICP → {n} emails generated
- If sent: delivery report

## Self-Annealing
If any step fails:
1. Each step is independent — identify which step failed
2. Fix that step's script, re-run from that point
3. Don't restart the full pipeline if only one step broke
4. Update the relevant directive's Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
