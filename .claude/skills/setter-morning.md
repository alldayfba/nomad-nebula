---
name: setter-morning
description: Daily AI setter SDR morning briefing — overnight results, action items, pipeline status
trigger: when user says "setter morning", "SDR status", "how are the DMs doing", "setter brief"
tools: [Bash, Read, Grep]
---

# Setter Morning Brief

## Directive
Read `directives/setter-sdr-sop.md` for the full SOP before proceeding.

## Goal
Surface overnight setter results and the top 3 actions Sabbo needs to take right now.

## Inputs
| Input | Required | Default |
|---|---|---|
| None | — | — |

## Execution

1. Query the setter database for yesterday's metrics and overnight activity:

```bash
source .venv/bin/activate
python3 -c "
import sqlite3, json
from datetime import datetime, timedelta
from pathlib import Path

db = sqlite3.connect(str(Path('.tmp/setter/setter.db')))
db.row_factory = sqlite3.Row

yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
today = datetime.now().strftime('%Y-%m-%d')

# Yesterday's send counts
cold = db.execute('SELECT COUNT(*) FROM messages WHERE direction=\"out\" AND created_at >= ? AND created_at < ? AND message_type=\"cold\"', (yesterday, today)).fetchone()[0]
warm = db.execute('SELECT COUNT(*) FROM messages WHERE direction=\"out\" AND created_at >= ? AND created_at < ? AND message_type=\"warm\"', (yesterday, today)).fetchone()[0]
followups = db.execute('SELECT COUNT(*) FROM messages WHERE direction=\"out\" AND created_at >= ? AND created_at < ? AND message_type=\"followup\"', (yesterday, today)).fetchone()[0]
total_out = cold + warm + followups

# Replies received
replies = db.execute('SELECT COUNT(*) FROM messages WHERE direction=\"in\" AND created_at >= ? AND created_at < ?', (yesterday, today)).fetchone()[0]
reply_rate = round(replies / total_out * 100, 1) if total_out > 0 else 0

# Bookings
bookings = db.execute('SELECT COUNT(*) FROM conversations WHERE stage=\"booked\" AND updated_at >= ?', (yesterday,)).fetchone()[0]

# Pipeline by stage
pipeline = db.execute('SELECT stage, COUNT(*) as cnt FROM conversations WHERE stage NOT IN (\"dead\", \"disqualified\") GROUP BY stage ORDER BY cnt DESC').fetchall()

# A-grade leads needing action (replied but no response from us in 4+ hours)
stuck = db.execute('''
    SELECT c.id, p.ig_handle, c.stage, c.updated_at
    FROM conversations c
    JOIN prospects p ON c.prospect_id = p.id
    LEFT JOIN lead_grades lg ON lg.conversation_id = c.id
    WHERE c.stage IN (\"replied\", \"qualifying\", \"qualified\", \"booking\")
    AND c.requires_human = 0
    AND lg.grade IN (\"A\", \"B\")
    ORDER BY c.updated_at ASC
    LIMIT 10
''').fetchall()

print('=== SETTER MORNING BRIEF ===')
print(f'Yesterday: {total_out} DMs sent ({cold} warm outbound, {warm} story/engager, {followups} follow-ups)')
print(f'Replies: {replies} ({reply_rate}% rate)')
print(f'Bookings: {bookings}')
print()
print('--- Pipeline ---')
for row in pipeline:
    print(f'  {row[\"stage\"]}: {row[\"cnt\"]}')
print()
print('--- A/B Grade Leads Needing Action ---')
for row in stuck:
    print(f'  @{row[\"ig_handle\"]} | stage: {row[\"stage\"]} | last update: {row[\"updated_at\"]}')
if not stuck:
    print('  None -- all caught up')
db.close()
"
```

2. Read the setter log for any errors or action blocks overnight:

```bash
grep -i "ERROR\|action.block\|PAUSED\|ESCALAT" .tmp/setter/setter.log | tail -5
```

3. Check if the pause file exists (kill switch):

```bash
test -f .tmp/setter/PAUSED && echo "SETTER IS PAUSED" || echo "Setter running normally"
```

## Output

Formatted summary:
- Yesterday's DM volume + reply rate + bookings
- Pipeline snapshot (count by stage)
- Top action items: A/B grade stuck leads, escalations, errors
- System health: running/paused, any action blocks

## Self-Annealing
If the database query fails:
1. Check if `.tmp/setter/setter.db` exists
2. If not, the daemon hasn't been started yet — tell Sabbo
3. If schema error, check `execution/setter/setter_db.py` for current table names
