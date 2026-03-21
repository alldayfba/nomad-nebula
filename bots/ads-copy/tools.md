# Ads & Copy Bot — Tools
> bots/ads-copy/tools.md | Version 1.0

---

## Access Policy

- **Authentication:** API keys only. No stored passwords, no browser sessions with saved logins.
- **Principle:** Read-only access wherever possible. Write access only where explicitly required.
- **Never store:** Credit card info, billing credentials, ad account publishing access.

---

## Meta Ad Library

**Purpose:** Competitor research, trend monitoring.
**Access type:** Public (no auth required)
**Script:** `execution/scrape_competitor_ads.py`
**Usage:** Read-only. Scrape competitor ads for intelligence. Never log into any Meta account.

Competitor targets to monitor (update as needed):
```
# Agency competitors
- [Add competitor ad library URLs here]

# Coaching/Amazon competitors
- [Add competitor ad library URLs here]
```

---

## Morning Briefing Delivery

**Purpose:** Send daily 8am briefing to Sabbo.
**Script:** `execution/send_morning_briefing.py`
**Delivery method:** [Email / Telegram — configure in .env]

Required `.env` variables:
```
BRIEFING_DELIVERY=telegram  # or: email
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
BRIEFING_EMAIL_TO=
```

---

## File System

**Access type:** Read/write
**Scope:** Local project directory only — `bots/`, `directives/`, `execution/`, `.tmp/`
**Never access:** Files outside the project directory, system files, other user profiles

---

## API Budget

Monthly LLM spending limits:

```
Gemini Pro:   Primary — unlimited within reason (cheap per token)
Gemini Flash: Fallback — use when Gemini Pro is overkill
Claude Opus:  Max $X/month — requires Sabbo's explicit instruction before each use
              (Do not run Opus autonomously — confirm first)

Total monthly ceiling: $[SET THIS] — alert Sabbo at 80% of ceiling
```

Update this file when Sabbo sets a budget ceiling.

---

## What This Bot Cannot Access

- Meta Ads Manager publishing (no ability to create, edit, or pause ads)
- Stripe, payment processors
- Email platforms with send access
- Any client accounts directly
- Any credentials not listed in this file

---

*Ads & Copy Bot Tools v1.0 — 2026-02-20*
