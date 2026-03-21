# CSM Bot — Tools
> bots/csm/tools.md | Version 1.0

---

## Access Policy

This bot operates under principle of least privilege. All access is scoped to student success operations. Authentication via environment variables in `.env`. Never expose credentials or student data in outputs.

---

## Student Health Monitor (PRIMARY)

**Purpose:** Core health scoring, engagement tracking, at-risk detection
**Access type:** Read / Write
**Script:** `execution/student_health_monitor.py`
**Usage:**
```bash
python execution/student_health_monitor.py daily-scan
python execution/student_health_monitor.py health-report
python execution/student_health_monitor.py student-detail --name "[name]"
python execution/student_health_monitor.py at-risk
python execution/student_health_monitor.py log-signal --student "[name]" --type [signal] --channel [channel]
python execution/student_health_monitor.py leaderboard
python execution/student_health_monitor.py engagement-digest
python execution/student_health_monitor.py graduation-check
```
**Database:** `.tmp/coaching/students.db`

---

## Student Tracker

**Purpose:** Milestone management, student records, check-in logging
**Access type:** Read / Write
**Script:** `execution/student_tracker.py`
**Usage:**
```bash
python execution/student_tracker.py add-student --name "[name]" --tier [A/B/C]
python execution/student_tracker.py update-milestone --student "[name]" --milestone [milestone]
python execution/student_tracker.py check-in --student "[name]" --type [type] --summary "[text]" --mood [mood]
python execution/student_tracker.py cohort-report
python execution/student_tracker.py at-risk
```

---

## Discord Bot (CSM Cog)

**Purpose:** Discord activity monitoring, slash commands, automated DMs
**Access type:** Read / Write (Discord API via bot token)
**Script:** `execution/discord_bot/csm_cog.py`
**Slash commands:** /checkin, /win, /stuck, /referral
**Env vars:** `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`

---

## Student Onboarding

**Purpose:** Generate 90-day onboarding Google Docs
**Access type:** Read / Write (Google Drive)
**Script:** `execution/upload_onboarding_gdoc.py`
**Directive:** `directives/student-onboarding-sop.md`

---

## File System

**Purpose:** Read/write working files
**Access type:** Read/Write (scoped)
**Allowed paths:**
- `bots/csm/` — Bot config files
- `.tmp/csm/` — Daily reports, leaderboards, intervention logs
- `.tmp/coaching/` — Student database
- `SabboOS/` — Business OS docs (read), CHANGELOG (append)
- `directives/` — SOPs (read)
- `bots/creators/` — Creator brain files (read)

---

## What This Bot Cannot Access

- Payment processors (Stripe) — no direct access
- Student financials beyond enrollment revenue
- Other bots' config files — read-only at best
- Credentials or API keys — only via env vars
- 247growth dashboard — that's the Sales Manager's domain
- Ad accounts — that's the ads-copy bot

---

## API Budget

- Monthly token ceiling: Follow `directives/api-cost-management-sop.md`
- Sonnet for analysis/reporting/intervention messages
- Haiku for signal aggregation/sentiment
- Opus reserved for case studies (approval required)

---

*CSM Bot Tools v1.0 — 2026-03-16*
