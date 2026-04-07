---
name: blitz
description: Launch the AI setter to DM followers from your IG account
triggers:
  - blitz
  - dm blitz
  - blast followers
  - run setter
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# /blitz — AI Setter Follower Blitz

DM your Instagram followers with the AI setter. Opens your followers list and sends openers down the list.

## Usage
- `/blitz` — send 20 DMs (default)
- `/blitz 50` — send 50 DMs
- `/blitz 100` — send 100 DMs

## Execution

1. Check Chrome is running on port 9222. If not, launch it:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.chrome-setter-profile" --no-first-run "https://www.instagram.com" &
```
Wait 3 seconds for Chrome to start.

2. Show current day stats before starting:
```bash
source .venv/bin/activate && python -c "
from execution.setter import setter_db as db
from execution.setter.setter_config import RATE_LIMITS
counts = db.get_today_send_counts()
total = counts.get('dm_total', 0)
limit = RATE_LIMITS['dm_daily_max']
print(f'Today: {total}/{limit} DMs sent')
print(f'Remaining: {limit - total}')
"
```

3. Parse the limit from args (default 20). Run the blitz:
```bash
source .venv/bin/activate && python -m execution.setter.follower_blitz --limit {LIMIT} --fast
```

4. Show the results summary when done.
