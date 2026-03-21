# Email Generation SOP

## Purpose
Generate personalized cold outreach emails for each filtered lead using Claude.
Each email is 1:1 — tailored to the specific business name, category, and location.
Output is a CSV with `email_subject` and `email_body` columns appended.

## When to Use
After running `execution/filter_icp.py`. Input should be a filtered leads CSV (icp_include = true).
Do not run on unfiltered lists — personalization is wasted on bad-fit leads.

## Email Style Guide (Agency)
All emails follow a strict 3-layer prompt structure: Role → Context → Task.

**Role:** Direct response copywriter for a growth marketing agency

**Context provided to Claude per email:**
- Agency offer, promise, and differentiator (hardcoded in script)
- Lead-specific data: business name, owner name, category, location, website, rating

**Output rules (enforced in script):**
- Max 120 words
- One specific observation about their business
- One CTA: book a 20-minute strategy call
- No fluff phrases ("I hope this email finds you well", "circle back", etc.)
- Operator-to-operator tone — peer-level, direct, brief

To update the voice or offer, edit `SENDER_CONTEXT` in `execution/generate_emails.py`.

## Inputs
- `--input` — Filtered leads CSV (from `filter_icp.py`)
- `--output` — Optional. Defaults to `.tmp/emails_<timestamp>.csv`

## Outputs
- CSV in `.tmp/` with two new columns:
  - `email_subject` — personalized subject line
  - `email_body` — full email body (line breaks stored as `\n`)

## How to Run
```bash
source .venv/bin/activate

# Generate emails for filtered leads
python execution/generate_emails.py --input .tmp/filtered_leads_20250120.csv

# With custom output path
python execution/generate_emails.py --input .tmp/filtered.csv --output .tmp/campaign_emails.csv
```

## Prerequisites
- `.env` file with `ANTHROPIC_API_KEY` set
- Filtered leads CSV (output from `filter_icp.py`)

## Cost Estimate
- ~500 tokens per lead (input + output)
- At 100 leads: ~50K tokens ≈ $0.15 with claude-opus-4-6
- At 1,000 leads: ~$1.50

## Quality Review Checklist
Before loading into your outreach tool (Instantly, Apollo, etc.), spot-check 10-15 emails:
- [ ] Personalization references the actual business (not generic)
- [ ] Subject line reads like a human sent it
- [ ] Under 120 words
- [ ] CTA is a strategy call, not a demo or pitch
- [ ] No fluff or corporate language

## Next Steps After Generation
1. Export CSV to outreach tool (Instantly, Apollo, Smartlead)
2. Sequence: email_subject as subject line, email_body as email 1 body
3. Set follow-up sequences manually or in the tool

## Known Issues / Edge Cases
- Leads with no owner_name generate more generic openers — acceptable
- Businesses with very generic categories (e.g., "Store") produce less specific emails
- If Claude returns malformed JSON for a lead, that lead's email columns will contain the error message — filter before upload
