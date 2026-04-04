---
name: setter-call-prep
description: Generate call prep document for upcoming setter-booked calls — pulls conversation history + prospect profile
trigger: when user says "setter call prep", "prep for setter call", "who am i calling"
tools: [Bash, Read, Grep]
---

# Setter Call Prep

## Directive
Read `directives/setter-sdr-sop.md` for the full SOP before proceeding.

## Goal
Generate a 1-page call prep document for an upcoming discovery call booked through the setter system.

## Inputs
| Input | Required | Default |
|---|---|---|
| handle | No | all booked calls in next 24h |

## Execution

1. Query booked calls:

```bash
source .venv/bin/activate
python3 -c "
import sqlite3, json
from datetime import datetime, timedelta
from pathlib import Path

db = sqlite3.connect(str(Path('.tmp/setter/setter.db')))
db.row_factory = sqlite3.Row

# All booked conversations
rows = db.execute('''
    SELECT c.id, c.stage, c.offer, c.messages_sent, c.messages_received,
           c.updated_at, c.booking_confirmed,
           p.ig_handle, p.full_name, p.bio, p.follower_count, p.following_count,
           p.email_from_bio, p.website, p.source,
           lg.grade, lg.temperature, lg.reasoning
    FROM conversations c
    JOIN prospects p ON c.prospect_id = p.id
    LEFT JOIN lead_grades lg ON lg.conversation_id = c.id
    WHERE c.stage = 'booked'
    ORDER BY c.updated_at DESC
''').fetchall()

for r in rows:
    print(f'=== @{r[\"ig_handle\"]} ({r[\"full_name\"] or \"?\"}) ===')
    print(f'Offer: {r[\"offer\"]}')
    print(f'Grade: {r[\"grade\"]}/{r[\"temperature\"]}')
    print(f'Bio: {r[\"bio\"] or \"N/A\"}')
    print(f'Followers: {r[\"follower_count\"]} | Following: {r[\"following_count\"]}')
    print(f'Website: {r[\"website\"] or \"N/A\"}')
    print(f'Email: {r[\"email_from_bio\"] or \"N/A\"}')
    print(f'Source: {r[\"source\"]}')
    print(f'Messages: {r[\"messages_sent\"]}out / {r[\"messages_received\"]}in')
    print(f'Grading reason: {r[\"reasoning\"] or \"N/A\"}')
    print()

    # Pull conversation history
    msgs = db.execute('''
        SELECT direction, content, created_at FROM messages
        WHERE conversation_id = ? ORDER BY created_at ASC
    ''', (r['id'],)).fetchall()

    print('--- Conversation ---')
    for m in msgs:
        arrow = 'US >>>' if m['direction'] == 'out' else 'THEM <<<'
        print(f'{arrow} {m[\"content\"]}')
    print()
    print('---')
    print()

db.close()
"
```

2. For each booked call, generate a prep document:

**Call Prep Format:**
```
CALL PREP — @{handle} ({name})
Offer: {offer}
Grade: {grade} | Source: {source}

BIO: {bio}
WEBSITE: {website}

QUALIFICATION SUMMARY:
- Commitment: {what they said about interest}
- Resources: {what they said about capital/credit}
- Urgency: {timeline signals}

KEY QUOTES (from DMs):
- "{most revealing thing they said}"
- "{their main pain point}"

OPENER SUGGESTION:
"Hey {name}, good to connect. I saw in our DMs you mentioned {specific thing} — tell me more about that."

WATCH FOR:
- {any objections raised in DMs}
- {any red flags from grading}
```

## Output
One call prep per booked lead. Can be added to Google Calendar event notes via Cowork Calendar connector.

## Self-Annealing
If no booked conversations found, check if the daemon is running and if any leads are in earlier stages that could be pushed to booking.
