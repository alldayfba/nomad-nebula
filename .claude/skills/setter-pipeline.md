---
name: setter-pipeline
description: Review AI setter pipeline — all active conversations by stage, stuck leads, recommended actions
trigger: when user says "setter pipeline", "show me the funnel", "where are my leads", "DM pipeline"
tools: [Bash, Read, Grep]
---

# Setter Pipeline Review

## Directive
Read `directives/setter-sdr-sop.md` for the full SOP before proceeding.

## Goal
Show all active setter conversations grouped by stage, highlight stuck leads, and recommend specific actions.

## Inputs
| Input | Required | Default |
|---|---|---|
| offer | No | all (both amazon_os and agency_os) |

## Execution

1. Query the full active pipeline:

```bash
source .venv/bin/activate
python3 -c "
import sqlite3, json
from datetime import datetime, timedelta
from pathlib import Path

db = sqlite3.connect(str(Path('.tmp/setter/setter.db')))
db.row_factory = sqlite3.Row

now = datetime.now()

# All active conversations (not dead/disqualified)
rows = db.execute('''
    SELECT c.id, c.stage, c.offer, c.messages_sent, c.messages_received,
           c.requires_human, c.updated_at, c.booking_confirmed,
           p.ig_handle, p.full_name, p.source,
           lg.grade, lg.temperature
    FROM conversations c
    JOIN prospects p ON c.prospect_id = p.id
    LEFT JOIN lead_grades lg ON lg.conversation_id = c.id
    WHERE c.stage NOT IN ('dead', 'disqualified')
    ORDER BY
        CASE lg.grade WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3 WHEN 'D' THEN 4 ELSE 5 END,
        c.updated_at DESC
''').fetchall()

# Group by stage
from collections import defaultdict
by_stage = defaultdict(list)
for r in rows:
    by_stage[r['stage']].append(r)

stage_order = ['booked', 'booking', 'qualified', 'qualifying', 'replied', 'opener_sent', 'nurture', 'escalated', 'no_show', 'show', 'new']

print('=== SETTER PIPELINE ===')
print(f'Total active: {len(rows)}')
print()

for stage in stage_order:
    convs = by_stage.get(stage, [])
    if not convs:
        continue
    print(f'--- {stage.upper()} ({len(convs)}) ---')
    for c in convs[:10]:  # Show top 10 per stage
        handle = c['ig_handle'] or 'unknown'
        grade = c['grade'] or '?'
        temp = c['temperature'] or '?'
        msgs = f\"{c['messages_sent']}out/{c['messages_received']}in\"
        updated = c['updated_at'] or ''

        # Calculate hours since last update
        hours_ago = ''
        if updated:
            try:
                dt = datetime.strptime(updated[:19], '%Y-%m-%d %H:%M:%S')
                hours = (now - dt).total_seconds() / 3600
                if hours < 1:
                    hours_ago = f'{int(hours*60)}m ago'
                elif hours < 24:
                    hours_ago = f'{int(hours)}h ago'
                else:
                    hours_ago = f'{int(hours/24)}d ago'
            except ValueError:
                hours_ago = updated[:10]

        flags = []
        if c['requires_human']:
            flags.append('NEEDS HUMAN')
        if c['booking_confirmed']:
            flags.append('BOOKED')

        flag_str = f' [{\" | \".join(flags)}]' if flags else ''
        print(f'  @{handle} | {grade}/{temp} | {msgs} | {hours_ago}{flag_str}')

    if len(convs) > 10:
        print(f'  ... and {len(convs) - 10} more')
    print()

# Stuck leads (qualified/booking but no booking in 24h+)
stuck = [r for r in rows if r['stage'] in ('qualified', 'booking') and r['updated_at']]
stuck_old = []
for s in stuck:
    try:
        dt = datetime.strptime(s['updated_at'][:19], '%Y-%m-%d %H:%M:%S')
        if (now - dt).total_seconds() > 86400:
            stuck_old.append(s)
    except ValueError:
        pass

if stuck_old:
    print('--- STUCK (qualified/booking 24h+ without booking) ---')
    for s in stuck_old:
        print(f'  @{s[\"ig_handle\"]} | {s[\"stage\"]} | grade {s[\"grade\"]} | last: {s[\"updated_at\"][:10]}')
    print()

# Escalated
escalated = by_stage.get('escalated', [])
if escalated:
    print('--- ESCALATED (needs human) ---')
    for e in escalated:
        print(f'  @{e[\"ig_handle\"]} | reason: check conversation')
    print()

db.close()
"
```

2. For any A-grade stuck lead, pull last few messages:

```bash
# Replace CONV_ID with the actual conversation ID from above
source .venv/bin/activate
python3 -c "
import sqlite3
from pathlib import Path
db = sqlite3.connect(str(Path('.tmp/setter/setter.db')))
db.row_factory = sqlite3.Row
# Get last 5 messages for the most recent A-grade stuck conversation
rows = db.execute('''
    SELECT m.direction, m.content, m.created_at
    FROM messages m
    JOIN conversations c ON m.conversation_id = c.id
    JOIN lead_grades lg ON lg.conversation_id = c.id
    WHERE lg.grade = 'A' AND c.stage IN ('qualified', 'booking', 'qualifying')
    ORDER BY m.created_at DESC LIMIT 5
''').fetchall()
for r in rows:
    arrow = '>>>' if r['direction'] == 'out' else '<<<'
    print(f'{arrow} {r[\"content\"][:100]}  ({r[\"created_at\"][:16]})')
db.close()
"
```

## Output

Formatted pipeline view:
- Count by stage (booked → booking → qualified → qualifying → replied → opener_sent → nurture)
- Each lead: @handle, grade/temperature, message count, time since last update
- Stuck leads flagged (qualified/booking with no progress in 24h+)
- Escalated conversations highlighted
- Recommended actions for top stuck leads

## Self-Annealing
If the database query fails:
1. Check if `.tmp/setter/setter.db` exists
2. If schema mismatch, read `execution/setter/setter_db.py` for current table/column names
3. Adjust query accordingly and update this skill
