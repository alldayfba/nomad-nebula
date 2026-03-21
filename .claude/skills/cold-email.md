---
name: cold-email
description: Generate personalized cold outreach emails for filtered lead CSVs
trigger: when user says "generate emails", "cold emails", "write outreach emails", "email campaign"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Cold Email Generator

## Directive
Read `directives/email-generation-sop.md` for the full SOP before proceeding.

## Goal
Generate personalized 1:1 cold outreach emails for each lead in a filtered CSV. Each email is tailored to the specific business.

## Prerequisites
- Input CSV must be ICP-filtered (output from `execution/filter_icp.py` with `icp_include = true`)
- Do NOT run on unfiltered lists — personalization is wasted on bad-fit leads
- `.env` must have `ANTHROPIC_API_KEY` set

## Inputs
| Input | Required | Default |
|---|---|---|
| input CSV | Yes | — (path to filtered leads CSV) |
| output path | No | `.tmp/emails_<timestamp>.csv` |

If user doesn't specify an input CSV, check `.tmp/` for the most recent `filtered_leads_*.csv` or `icp_*.csv` file.

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/generate_emails.py --input "{input_csv}"
```

With custom output:
```bash
python execution/generate_emails.py --input "{input_csv}" --output "{output_path}"
```

## Output
- CSV in `.tmp/` with two new columns: `email_subject`, `email_body`
- Cost: ~$0.15 per 100 leads, ~$1.50 per 1,000 leads

## Quality Check (do this before telling user it's done)
Spot-check 3-5 emails:
- Personalization references the actual business (not generic)
- Subject line reads like a human sent it
- Under 120 words
- CTA is a strategy call, not a demo or pitch
- No fluff or corporate language

## Next Steps
1. Export CSV to outreach tool (Instantly, Apollo, Smartlead)
2. Or create outreach sequence: `/outreach-sequence`

## Self-Annealing
If execution fails:
1. Check `.env` for `ANTHROPIC_API_KEY`
2. If Claude returns malformed JSON, those leads get error messages — filter before upload
3. To update voice/offer, edit `SENDER_CONTEXT` in `execution/generate_emails.py`
4. Fix the script, update directive Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
