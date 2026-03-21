# Outreach Bot — Tools
> bots/outreach/tools.md | Version 2.0

---

## Active Tools

| Tool | Purpose | Status | Invocation |
|---|---|---|---|
| **Outreach Sequencer** | Create multi-touch sequences, generate personalized copy, track pipeline | **Active** | `python execution/outreach_sequencer.py` |
| **Lead Scraper** | Google Maps → qualified leads CSV | Active | `python execution/run_scraper.py` |
| **ICP Filter** | Filter scraped leads by ICP criteria | Active | `python execution/filter_icp.py` |
| **Email Generator** | One-off personalized emails | Active | `python execution/generate_emails.py` |
| **Business Audit** | Generate personalized audit packages for prospects | Active | `python execution/generate_business_audit.py` |
| **Prospect Research** | Deep research on individual prospects | Active | `python execution/research_prospect.py` |
| **Dream 100 Pipeline** | Full hyper-personalized outreach | Active | `python execution/run_dream100.py` |

### Outreach Sequencer Commands

```bash
# Create a new outreach sequence from leads CSV
python execution/outreach_sequencer.py create-sequence --leads .tmp/filtered_leads.csv --template dream100

# View touches due today
python execution/outreach_sequencer.py next-touches --due today

# Mark touches as sent/replied/booked
python execution/outreach_sequencer.py mark-sent --touch-id 5
python execution/outreach_sequencer.py mark-replied --prospect-id 3 --notes "Interested"
python execution/outreach_sequencer.py mark-booked --prospect-id 3

# View pipeline stats
python execution/outreach_sequencer.py stats
```

**Templates:** dream100 (7 touches, 30d), cold_email (4 touches, 14d), warm_followup (3 touches, 10d)
**DB:** `.tmp/outreach/sequences.db`
**LLM:** Claude Sonnet 4.6 (via Anthropic API)

---

## Planned Access

| Tool | Purpose | Status |
|---|---|---|
| Instantly | Cold email sending and sequencing | Planned |
| LinkedIn (public) | Prospect research | Planned |
| Instagram DM | Direct outreach | Planned — high guardrail required |
| Eleven Labs | AI voice for cold calls | Phase 2 |
| Twilio | Call infrastructure | Phase 2 |

---

## Access Policy

- No access to Sabbo's personal social accounts without explicit per-campaign approval
- All sends logged with timestamp, recipient, message, and response
- Daily send caps must be set before activation
- No billing or payment access on any platform
- Sequencer generates drafts — Sabbo reviews before actual sending

---

*Outreach Bot Tools v2.0 — 2026-02-21*
