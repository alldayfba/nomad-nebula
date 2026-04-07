---
name: setter
description: AI Setter SDR — cold DM blitz, inbox analysis, follow-ups, full pipeline
user_invocable: true
tools: [Bash, Read, Write, Edit, Glob, Grep]
trigger: when user says "setter"
---

# /setter — AI Setter SDR Pipeline


## Directive
Read `directives/setter-sdr-sop.md` for the full SOP before proceeding.


Run the IG DM setter system. Requires Chrome on port 9222 with IG logged in.

## Commands

Parse the user's input to determine which mode to run:

| Input | Action |
|-------|--------|
| `/setter blitz N` | Cold DM N new followers (default 200) |
| `/setter analyze N` | AI-scan N DM threads, classify leads, suggest messages |
| `/setter auto N` | Analyze + auto-send to hot leads (priority >= 5) |
| `/setter follow-ups N` | Send N due follow-up messages |
| `/setter inbox` | Check inbox for replies, AI responds |
| `/setter full-cycle N` | Full pipeline: scroll → analyze → follow-ups → new DMs |
| `/setter review` | Show pipeline state + lead classifications |
| `/setter status` | DB stats: followers, contacted, uncontacted, follow-ups due |

## Execution

1. Ensure Chrome is running on port 9222:
```bash
curl -s "http://127.0.0.1:9222/json/version" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Chrome ready')" 2>/dev/null || { "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="/tmp/chrome-setter" --no-first-run --disable-gpu --disable-extensions --disable-sync --window-size=1280,900 "https://www.instagram.com/" &>/dev/null & sleep 5 && echo "Chrome launched"; }
```

2. Run the appropriate command:

| Mode | Command |
|------|---------|
| blitz | `source .venv/bin/activate && python -m execution.setter.follower_blitz --limit {N} --fast --no-night-mode` |
| analyze | `source .venv/bin/activate && python -m execution.setter.inbox_analyzer --mode analyze --limit {N}` |
| auto | `source .venv/bin/activate && python -m execution.setter.inbox_analyzer --mode auto --limit {N} --fast` |
| follow-ups | `source .venv/bin/activate && python -m execution.setter.follower_blitz --follow-ups --limit {N}` |
| inbox | `source .venv/bin/activate && python -m execution.setter.follower_blitz --inbox` |
| full-cycle | `source .venv/bin/activate && python -m execution.setter.follower_blitz --full-cycle --limit {N} --fast --no-night-mode` |
| review | `source .venv/bin/activate && python -m execution.setter.inbox_analyzer --mode review` |
| status | Run DB query (see below) |

3. For **status**, run:
```bash
source .venv/bin/activate && python3 -c "
import sys; sys.path.insert(0, '.')
from execution.setter import setter_db as db
d = db.get_db()
total = d.execute('SELECT COUNT(*) FROM prospects WHERE source IN (\"follower_scroll\", \"new_follower\")').fetchone()[0]
contacted = d.execute('SELECT COUNT(DISTINCT p.id) FROM prospects p JOIN conversations c ON c.prospect_id = p.id WHERE p.source IN (\"follower_scroll\", \"new_follower\")').fetchone()[0]
pending_fu = d.execute(\"SELECT COUNT(*) FROM follow_ups WHERE status='pending'\").fetchone()[0]
due_fu = d.execute(\"SELECT COUNT(*) FROM follow_ups WHERE status='pending' AND scheduled_at <= datetime('now')\").fetchone()[0]
stages = d.execute('SELECT stage, COUNT(*) as c FROM conversations GROUP BY stage ORDER BY c DESC').fetchall()
print(f'Followers: {total} total | {contacted} contacted | {total-contacted} uncontacted')
print(f'Follow-ups: {pending_fu} pending | {due_fu} due now')
print('Pipeline:')
for r in stages: print(f'  {r[\"stage\"]}: {r[\"c\"]}')
"
```

4. Run long commands in background. Report results when complete.

## Default behavior
- If user just says `/setter` with no args, run **status**
- Always add `--fast` and `--no-night-mode` unless user says otherwise
- Default limit is 200 for blitz, 30 for analyze, 50 for follow-ups
