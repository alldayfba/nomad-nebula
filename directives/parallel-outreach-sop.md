# Parallel Browser Agent Outreach SOP
> directives/parallel-outreach-sop.md | Version 1.0

---

## Purpose

Spawn N headless Chrome browsers in parallel, each navigating to a lead's website, finding their contact form, and filling it out with personalized outreach. Turns scraped leads into actual outreach without manual work.

---

## How It Works

1. Load leads from CSV (must have `website` column)
2. For each lead, a Playwright browser instance:
   a. Navigates to the website
   b. Screenshots the page
   c. Claude Haiku analyzes the screenshot to find contact form fields + selectors
   d. If no form found, clicks "Contact" link and re-analyzes
   e. Fills each form field with mapped data (name, email, company, personalized message)
   f. Submits the form (or screenshots for dry-run)
3. Results logged to `.tmp/outreach/`

---

## Prerequisites

- Playwright installed: `pip install playwright && playwright install chromium`
- ANTHROPIC_API_KEY in `.env` (uses Haiku for form analysis — very cheap)
- Lead CSV with `website` column (output of scraper or ICP filter)
- Optional: `OUTREACH_FROM_EMAIL` and `OUTREACH_FROM_PHONE` in `.env`

---

## Execution

```bash
# Dry run first (always dry-run first to verify)
python execution/parallel_outreach.py \
    --input .tmp/filtered_leads.csv \
    --max-browsers 3 \
    --dry-run

# Live run with default intro template
python execution/parallel_outreach.py \
    --input .tmp/filtered_leads.csv \
    --max-browsers 5 \
    --message-template outreach_intro

# With custom message
python execution/parallel_outreach.py \
    --input leads.csv \
    --max-browsers 3 \
    --message "Hi {first_name}, I put together a growth audit for {company}..."

# Show browsers (not headless)
python execution/parallel_outreach.py \
    --input leads.csv \
    --max-browsers 3 \
    --visible \
    --dry-run
```

---

## Templates

| Name | Use Case |
|---|---|
| `outreach_intro` | General intro — "I help businesses like yours install a growth engine" |
| `outreach_audit` | Audit lead-in — "I put together a quick growth audit for {company}" |
| `outreach_fba` | FBA coaching — "I coach sellers to hit $10K months" |

Custom templates use `{first_name}`, `{company}`, `{email}`, `{phone}`, `{website}`, `{category}` placeholders.

---

## Field Mapping

The AI analyzes form fields and the system maps them:

| Form Label | Maps To |
|---|---|
| First Name | lead's owner_name (first word) |
| Last Name | lead's owner_name (last word) |
| Email | `OUTREACH_FROM_EMAIL` env var |
| Phone | `OUTREACH_FROM_PHONE` env var |
| Company | "24/7 Growth" |
| Subject | "Quick question for {business_name}" |
| Message | Personalized template |

---

## Safety

1. **Always dry-run first** — verify forms are being filled correctly
2. **Start with 2-3 browsers** — scale up once confident
3. **Rate limiting** — batches process sequentially, not all at once
4. **Screenshots** — every step is screenshotted for review in `.tmp/outreach/screenshots/`
5. **No CAPTCHAs** — if a site has CAPTCHA, the form will fail gracefully (logged as error)

---

## Cost

- Haiku for form analysis: ~$0.001 per lead (2 screenshots × ~500 tokens each)
- 100 leads ≈ $0.10 in API costs + ~10 min runtime at 5 browsers

---

## Full Pipeline

```bash
# 1. Scrape leads
python execution/run_scraper.py --query "dentists" --location "Miami FL" --max 50

# 2. Filter ICP
python execution/filter_icp.py --input leads_output.csv --threshold 6

# 3. Generate personalized emails (optional — for email outreach)
python execution/generate_emails.py --input .tmp/filtered_leads.csv

# 4. Parallel contact form outreach (this script)
python execution/parallel_outreach.py --input .tmp/filtered_leads.csv --max-browsers 5 --dry-run
```
