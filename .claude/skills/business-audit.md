---
name: business-audit
description: Generate 4-asset audit packages (audit doc, landing page, ad angles, email) for B2B prospects
trigger: when user says "audit", "build audit", "audit this business", "generate audit", "prospect audit"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Business Audit Generator

## Directive
Read `directives/business-audit-sop.md` for the full SOP before proceeding.

## Goal
Generate a complete, personalized audit package for any B2B prospect in under 2 minutes. Used to warm cold leads before outreach.

## What Gets Generated
1. **1-Page Business Audit** — marketing gaps, quick wins, revenue opportunity
2. **Personalized Landing Page** — HTML with top 3 gaps + book-a-call CTA
3. **3 Ad Angles** — Pain / Opportunity / Credibility (Meta format)
4. **Personalized Outreach Email** — specific observations + audit link

All uploaded to Google Drive folder: `Audit — [Business Name]`

## Inputs
| Input | Required | Default |
|---|---|---|
| business_name | Yes | — |
| website | No | analysis uses available fields only |
| category | No | industry/niche |
| phone | No | — |
| address | No | city/region |
| rating | No | Google star rating |
| owner_name | No | fallback: "Hi there" |

Extract from user's message. Only `business_name` is required.

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/generate_business_audit.py \
  --name "{business_name}" \
  --website "{website}" \
  --category "{category}" \
  --phone "{phone}" \
  --address "{address}" \
  --rating "{rating}" \
  --owner "{owner_name}"
```

Or use the web UI at `http://localhost:5050/audit`.

## Output
- Local: `.tmp/audit_{name}_{ts}/` (audit.md, landing.html, ad_angles.json, outreach.md)
- Cloud: Google Drive folder with shareable link
- Cost: ~$0.08-0.15 per audit

## Self-Annealing
If execution fails:
1. If website blocks scraper — analysis degrades gracefully using business info only
2. If Drive upload fails — local files still saved in `.tmp/`
3. Check `service_account.json` exists for Google Drive access
4. Don't run >20 audits in rapid succession (API rate limits)
5. Fix the script, update directive Known Issues
6. Log fix in `SabboOS/CHANGELOG.md`
