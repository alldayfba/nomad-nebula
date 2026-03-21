# Business Audit Generator — SOP

**Layer:** Directive
**Script:** `execution/generate_business_audit.py`
**UI Route:** `http://localhost:5050/audit`
**Last Updated:** 2026-02-20

---

## Purpose

Generate a complete, personalized audit package for any B2B business prospect — in under 2 minutes — ready to send via Google Drive. Used to warm cold leads before outreach and demonstrate the agency's operator-level thinking.

---

## What Gets Generated

For each business, the pipeline produces **4 assets**:

| Asset | Format | Destination |
|---|---|---|
| 1-Page Business Audit | Markdown → Google Doc | Google Drive folder |
| Personalized Landing Page | HTML file | Google Drive folder |
| 3 Ad Angles (Meta) | JSON / displayed in UI | Google Drive folder |
| Personalized Outreach Email | Markdown → Google Doc | Google Drive folder |

All 4 assets are uploaded to a named Google Drive folder: `Audit — [Business Name]`
The folder is shared with anyone who has the link (writer access).

---

## Two Ways to Use It

### Option A: Web UI (Recommended)
```
http://localhost:5050/audit
```
1. Choose input mode: **Search Market** or **Direct Input**
2. Search Market: enter niche + location → see results → click "Audit This"
3. Direct Input: paste business name + URL + category
4. Click **Generate Audit**
5. Watch the 7-step progress tracker
6. Get Drive folder link + full preview in the UI

### Option B: CLI
```bash
source .venv/bin/activate

python execution/generate_business_audit.py \
  --name "Blue Wave Dental" \
  --website "https://bluewavedc.com" \
  --category "Dental Practice" \
  --phone "(202) 555-1234" \
  --address "Washington DC" \
  --rating "4.3" \
  --owner "Dr. Marcus"
```

---

## Pipeline — 7 Steps

```
Step 1: Fetch + parse website (Playwright-free — uses requests + BeautifulSoup)
Step 2: Analyze marketing gaps (Claude Sonnet)
Step 3: Write 1-page audit document (Claude Sonnet → markdown)
Step 4: Build personalized landing page (Claude Sonnet → HTML)
Step 5: Draft 3 ad angles — Pain / Opportunity / Credibility (Claude Sonnet)
Step 6: Write personalized outreach email (Claude Sonnet)
Step 7: Upload all assets to Google Drive (service account auth)
```

**Total time:** ~60–90 seconds per audit
**Total cost:** ~$0.08–0.15 per audit (Claude Sonnet, ~4 API calls)

---

## Inputs

| Field | Required | Notes |
|---|---|---|
| `business_name` | Yes | Business name as it appears on Google |
| `website` | No | If missing, analysis uses available fields only |
| `category` | No | Industry/niche (e.g. "Dental Practice") |
| `phone` | No | Used in outreach context |
| `address` | No | City/region for geo-personalization |
| `rating` | No | Google star rating |
| `owner_name` | No | Used to personalize outreach (first name) |

---

## Outputs

### Local (`.tmp/audit_{name}_{ts}/`)
```
.tmp/audit_Blue_Wave_Dental_20260220_143020/
  ├── audit.md          ← 1-page audit document
  ├── landing.html      ← Personalized landing page
  ├── ad_angles.json    ← 3 ad angles
  └── outreach.md       ← Personalized email
```

### Google Drive (`Audit — [Business Name]`)
- `[Business Name] — Growth Audit` (Google Doc, converted from markdown)
- `Personalized Landing Page` (HTML file)
- `Ad Angles (3x Meta)` (text file)
- `Personalized Outreach Email` (Google Doc)

---

## Agency Config

Update in `execution/generate_business_audit.py` — `AGENCY` dict at the top:

```python
AGENCY = {
    "name": "Your Agency",
    "offer": "Done-For-You growth operating system",
    "promise": "Install a full-stack growth system in 30 days and run it month-over-month",
    "retainer": "$5K–$25K/mo",
    "differentiator": "Operators embedded in your business — not an account manager and a junior team",
    "cal_link": "https://cal.com/your-link",
    "from_name": "Nick",
}
```

---

## Requirements

### Dependencies (all in `.venv`)
```
anthropic
requests
beautifulsoup4
python-dotenv
google-auth
google-api-python-client
```

### `.env` vars needed
```
ANTHROPIC_API_KEY=sk-ant-...
```

### Google Drive
- `service_account.json` must exist in project root
- Service account needs Drive API enabled
- If missing, audit still runs — Drive upload is skipped gracefully

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Website blocks scraper | Analysis uses business info only (degrades gracefully) |
| Claude returns invalid JSON | Script retries-safe — catches exception, returns partial result |
| Drive upload fails | `drive_error` key returned; local files still saved to `.tmp/` |
| No website provided | Skips fetch step, uses name/category/location for analysis |
| Missing owner name | Outreach uses "Hi there" as fallback |

---

## What Goes Into Each Asset

### 1. Audit Document
- Executive Summary
- Current Marketing Assessment (funnel type, CTA, platforms, social proof)
- Growth Gaps (top 3, with impact + fix)
- Quick Wins (72-hour implementable)
- Revenue Opportunity
- What We'd Build For You
- CTA to book a strategy call

### 2. Landing Page
- Personalized headline: "We audited [Business]. Here's what we found."
- Top 3 gaps displayed as cards
- Prominent book-a-call CTA
- Agency credibility line
- Mobile-responsive, dark design, Inter font

### 3. Ad Angles
- **Pain angle**: agitates current frustration
- **Opportunity angle**: paints what's possible
- **Credibility angle**: earns trust via authority/proof
- Each has: hook (2-3s) + body (30-45s) + CTA

### 4. Outreach Email
- Subject line included
- Opens with specific observation about the business
- References 2 exact gaps found
- Teases the audit
- Includes `[DRIVE_LINK]` placeholder for the folder URL
- 150-200 words, sounds human

---

## Workflow: How to Use Audits in Outreach

```
1. Run audit for a lead
2. Copy Drive folder link
3. Open outreach message → replace [DRIVE_LINK] with Drive link
4. Send as first cold touch
5. Follow up referencing the audit 48 hrs later
6. Book strategy call → use audit findings as agenda
```

---

## Known Issues / Gotchas

- **JavaScript-heavy sites**: `requests` + BeautifulSoup may miss content rendered by JS. If analysis is too shallow, manually provide key business context via `--address` and `--category` flags.
- **Rate limits**: No rate limiting applied — don't run >20 audits in rapid succession against Claude API.
- **Drive folder permissions**: Set to "anyone with link can edit" — sender should review before sharing with sensitive prospects.
- **Landing page hosting**: HTML is uploaded to Drive as a file, not hosted. For a live URL, deploy via Modal or Netlify separately.

---

## Self-Anneal Log

| Date | Issue | Fix |
|---|---|---|
| 2026-02-20 | Initial build | — |
