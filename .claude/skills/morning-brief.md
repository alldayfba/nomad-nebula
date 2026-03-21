---
name: morning-brief
description: Generate and send daily CEO briefing with competitor intel, KPIs, and delegation report
trigger: when user says "morning brief", "daily brief", "send me the briefing", "what's happening today"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Morning Briefing

## Directive
Read `directives/morning-briefing-sop.md` for the full SOP before proceeding.

## Goal
Generate one briefing covering competitor intel, platform trends, top-performing ads, delegation report, and a recommended test — so Sabbo can make the highest-leverage decisions for the day in one read.

## Inputs
None required. Runs with pre-configured competitor lists from `bots/ads-copy/tools.md`.

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/send_morning_briefing.py
```

Delivery method configured in `.env`: `BRIEFING_DELIVERY` (telegram or email).

## Output
Briefing sent via Telegram or email containing:
- TOP INSIGHT TODAY (single most important finding)
- Agency competitor intel
- Coaching competitor intel
- Platform trends (Meta/YouTube/LinkedIn)
- Top 3 highest-impression ads across competitors
- Nightly delegation report
- Recommended test this week

## Quality Check
- TOP INSIGHT is specific and actionable, not vague
- Every competitor entry has real findings
- RECOMMENDED TEST tied to actual intel, not generic
- Under 500 words total

## Self-Annealing
If execution fails:
1. If competitor scrape fails, send briefing with available data (note the gap)
2. Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` for Telegram delivery
3. Check `SMTP_*` vars in `.env` for email delivery
4. Fix the script, update directive Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
