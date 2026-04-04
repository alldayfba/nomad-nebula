---
name: setter-email
description: Send email follow-ups to qualified setter leads who shared their email — uses Cowork Gmail connector
trigger: when user says "setter email", "email follow-ups", "email qualified leads"
tools: [Bash, Read, Grep]
---

# Setter Email Follow-Ups

## Directive
Read `directives/setter-sdr-sop.md` for the full SOP before proceeding.

## Goal
Send personalized email follow-ups to leads in the setter pipeline who shared their email address. Adds a second touchpoint channel beyond IG DMs.

## Inputs
| Input | Required | Default |
|---|---|---|
| offer | No | all |
| dry_run | No | true (preview without sending) |

## Execution

1. Query the setter DB for qualified leads with email addresses:

```bash
source .venv/bin/activate
python3 -c "
import sqlite3
from pathlib import Path

db = sqlite3.connect(str(Path('.tmp/setter/setter.db')))
db.row_factory = sqlite3.Row

# Leads in booking/qualified/booked stage with email
rows = db.execute('''
    SELECT c.id, c.stage, c.offer, p.ig_handle, p.full_name, p.email_from_bio,
           lg.grade, lg.temperature
    FROM conversations c
    JOIN prospects p ON c.prospect_id = p.id
    LEFT JOIN lead_grades lg ON lg.conversation_id = c.id
    WHERE c.stage IN ('qualified', 'booking', 'booked', 'no_show')
    AND p.email_from_bio IS NOT NULL
    AND p.email_from_bio != ''
    ORDER BY lg.grade ASC
''').fetchall()

print(f'Found {len(rows)} leads with email addresses:')
for r in rows:
    print(f'  @{r[\"ig_handle\"]} | {r[\"full_name\"]} | {r[\"email_from_bio\"]} | {r[\"stage\"]} | grade {r[\"grade\"]}')
db.close()
"
```

2. For each lead, generate a personalized email based on their conversation stage:

**For `qualified`/`booking` leads (haven't booked yet):**
Subject: quick follow up
Body: Hey {first_name}, wanted to follow up from our IG conversation. Here's the link to book a time that works for you: {calendar_link}. Looking forward to connecting. — Sabbo

**For `booked` leads (pre-call):**
Subject: looking forward to our call
Body: Hey {first_name}, just confirming our call. Go through this before we chat: https://alldayfba.com/call-prep — it'll give you full clarity on how I can help. Talk soon. — Sabbo

**For `no_show` leads:**
Subject: missed you today
Body: Hey {first_name}, no worries about today — life happens. Here's a new link to reschedule whenever you're ready: {calendar_link}. — Sabbo

3. If NOT dry_run, use the Cowork Gmail connector to send each email. If dry_run, display the drafts for review.

## Output
- List of emails to send (or sent) with recipient, subject, stage
- Count by category (booking push, pre-call, no-show recovery)

## Important Notes
- Keep emails SHORT (3-4 sentences max). Match Sabbo's casual tone.
- NEVER include pricing, guarantees, or detailed offer info in email.
- Calendar link: https://api.leadconnectorhq.com/widget/booking/9fL4lUjdONSbW0oJ419Y
- Default to dry_run=true — Sabbo must explicitly say "send them" to go live.

## Self-Annealing
If Gmail connector is not set up in Cowork, tell Sabbo to connect Gmail in Cowork Settings > Connectors.