# AI Setter — Skills
> bots/setter/skills.md | Version 1.0

## Owned Skills

| Skill | Trigger | Script |
|---|---|---|
| Cold Outbound | "send cold DMs", "outbound" | `execution/setter/ig_conversation.py` |
| Warm Outreach | "engage followers", "warm outreach" | `execution/setter/ig_conversation.py` |
| Inbox Management | "check DMs", "handle replies" | `execution/setter/ig_conversation.py` |
| Follow-Up | "follow up", "bump" | `execution/setter/followup_engine.py` |
| Prospect Discovery | "find leads", "scan prospects" | `execution/setter/ig_prospector.py` |
| ICP Scoring | "score prospect", "qualify" | `execution/setter/setter_brain.py` |
| Show Rate Nurture | "pre-call", "remind" | `execution/setter/show_rate_nurture.py` |

## Execution Tools

| Tool | Path | Purpose |
|---|---|---|
| `setter_daemon.py` | `execution/setter/setter_daemon.py` | Main 24/7 orchestrator |
| `ig_browser.py` | `execution/setter/ig_browser.py` | Playwright Instagram automation |
| `setter_brain.py` | `execution/setter/setter_brain.py` | Claude API conversation engine |
| `setter_db.py` | `execution/setter/setter_db.py` | SQLite database layer |
| `ghl_client.py` | `execution/ghl_client.py` | GHL CRM integration |
| `launch_chrome.sh` | `execution/launch_chrome.sh` | Chrome instance management |
