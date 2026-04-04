# Cowork Bridge — nomad-nebula

> This file is read by Claude Cowork when pointed at the nomad-nebula project folder.
> It gives Cowork the context to run setter skills and interact with the system.

## What This Project Is

AI-powered growth automation platform. The main system you'll interact with is the **AI Setter** — a 24/7 Instagram DM automation engine that discovers prospects, qualifies leads, and books calls.

## Environment

```bash
# Activate Python env before any script execution
source .venv/bin/activate

# Project root
/Users/Shared/antigravity/projects/nomad-nebula
```

## Setter System — Quick Reference

**Database:** `.tmp/setter/setter.db` (SQLite)
**Log:** `.tmp/setter/setter.log`
**Config:** `execution/setter/setter_config.py`
**SOP:** `directives/setter-sdr-sop.md`
**Bot config:** `bots/setter/` (identity, skills, tools, memory, heartbeat)

### Common Queries

```bash
# Pipeline by stage
sqlite3 .tmp/setter/setter.db "SELECT stage, COUNT(*) FROM conversations WHERE stage NOT IN ('dead','disqualified') GROUP BY stage;"

# Today's send counts
sqlite3 .tmp/setter/setter.db "SELECT channel, COUNT(*) FROM send_log WHERE date = date('now') GROUP BY channel;"

# A-grade leads
sqlite3 .tmp/setter/setter.db "SELECT p.ig_handle, c.stage, lg.grade FROM lead_grades lg JOIN conversations c ON lg.conversation_id = c.id JOIN prospects p ON c.prospect_id = p.id WHERE lg.grade = 'A';"

# Recent bookings
sqlite3 .tmp/setter/setter.db "SELECT p.ig_handle, c.updated_at FROM conversations c JOIN prospects p ON c.prospect_id = p.id WHERE c.stage = 'booked' ORDER BY c.updated_at DESC LIMIT 5;"
```

## Available Cowork Skills

| Skill | Trigger | What It Does |
|-------|---------|-------------|
| `/setter-morning` | "setter morning", "SDR status" | Daily briefing — overnight results, action items |
| `/setter-pipeline` | "setter pipeline", "show me the funnel" | Pipeline review — all leads by stage, stuck leads |
| `/setter-email` | "setter email", "email follow-ups" | Email qualified leads via Gmail connector |
| `/setter-call-prep` | "setter call prep", "who am I calling" | Generate call prep docs for booked calls |
| `/setter-profile-audit` | "audit my IG", "profile funnel" | Analyze IG profile against Nik Setting's framework |

## Cowork's Role vs nomad-nebula

| Task | Who Handles It |
|------|---------------|
| Sending IG DMs | **nomad-nebula** (Playwright daemon — never from Cowork) |
| Generating AI responses | **nomad-nebula** (setter_brain.py via Claude CLI) |
| Database reads/metrics | **Both** (Cowork can query SQLite for reporting) |
| Email follow-ups | **Cowork** (Gmail connector) |
| Calendar sync | **Cowork** (Google Calendar connector) |
| Morning briefings | **Cowork** (scheduled skill) |
| Pipeline reviews | **Cowork** (on-demand skill) |
| Call prep | **Cowork** (on-demand skill) |
| Profile audits | **Cowork** (Chrome + analysis) |

## Safety Rules

- **NEVER send Instagram DMs from Cowork** — the daemon handles all IG messaging
- **NEVER modify the setter database directly** — only read from it
- **NEVER expose financial data** unless Sabbo explicitly asks
- **Email default is dry_run=true** — Sabbo must say "send them" to go live
- **All student-facing output requires Sabbo's approval** before sending

## Scheduled Tasks

| Time | Task |
|------|------|
| 8:00 AM | `/setter-morning` — overnight results |
| 12:00 PM | `/setter-pipeline` — midday check |
| 5:00 PM | `/setter-pipeline` — end-of-day review |
| 6:00 PM | `/setter-email` — email follow-ups (dry run unless approved) |
