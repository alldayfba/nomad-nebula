# AI Setter — Tools
> bots/setter/tools.md | Version 1.0

## Core Scripts
- `execution/setter/setter_daemon.py` — Main orchestrator (launchd service)
- `execution/setter/ig_browser.py` — Playwright Instagram automation
- `execution/setter/setter_brain.py` — Claude conversation engine
- `execution/setter/ig_conversation.py` — State machine + inbox processing
- `execution/setter/ig_prospector.py` — Prospect discovery + ICP scoring
- `execution/setter/followup_engine.py` — Day 1/3/7/14 follow-ups
- `execution/setter/show_rate_nurture.py` — 11-touchpoint post-booking
- `execution/setter/setter_metrics.py` — Daily metrics + Discord summary
- `execution/setter/pattern_learner.py` — Self-improvement engine
- `execution/setter/manychat_bridge.py` — ManyChat webhook integration

## External Integrations
- `execution/ghl_client.py` — GoHighLevel CRM (contacts, pipelines, tags)
- `execution/ghl_automations.py` — Webhook handlers + Discord notifications
- `execution/launch_chrome.sh` — Chrome instance management

## Databases
- `.tmp/setter/setter.db` — All setter data (prospects, conversations, messages, metrics)

## Dashboard
- `/setter` — Live oversight UI (Flask route)
- `/setter/api/stats` — JSON API for stats
- `/setter/api/conversations` — Active conversations
- `/setter/api/approve/<id>` — Approve pending message
