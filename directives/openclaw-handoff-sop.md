# OpenClaw ↔ Claude Code Handoff SOP

## Purpose
Define how OpenClaw (running on `SabboOpenClawAI`) sends tasks to Claude Code and how results
are returned. Enables autonomous handoff without manual intervention.

## Mac User Setup

| User | Role |
|---|---|
| `SabboOpenClawAI` | OpenClaw host — drops tasks in inbox, receives results from outbox |
| `sabbojb` | Primary Claude Code account (migrated 2026-03-13) — runs inbox watcher, executes tasks |

Both users share access to `/Users/Shared/antigravity/` via `777` permissions.

## Shared Workspace Layout

```
/Users/Shared/antigravity/
├── inbox/      ← OpenClaw drops task JSON files here
├── outbox/     ← Claude Code writes results here
├── memory/     ← Shared agent context/memory files
└── proposals/  ← OpenClaw edit proposals (Sabbo reviews, Claude Code applies)
```

## Watcher — Always-On via launchd (runs on sabbojb)

The inbox watcher runs on the `sabbojb` user. It points directly to the canonical source —
no copy needed since the shared path `/Users/Shared/antigravity/` has no TCC restrictions.

| File | Purpose |
|---|---|
| `execution/watch_inbox.py` | Canonical source — always edit this one (no sync needed) |

**Plist:** `/Users/sabbojb/Library/LaunchAgents/com.sabbo.inbox-watcher.plist`
**Log:** `/Users/sabbojb/.claude/inbox-watcher.log`
**Error log:** `/Users/sabbojb/.claude/inbox-watcher-error.log`

The watcher auto-starts on login and restarts if it crashes (`KeepAlive: true`).

**After editing `execution/watch_inbox.py`, just restart:**
```bash
launchctl unload /Users/sabbojb/Library/LaunchAgents/com.sabbo.inbox-watcher.plist
launchctl load /Users/sabbojb/Library/LaunchAgents/com.sabbo.inbox-watcher.plist
```

To manually manage:
```bash
# Check status
launchctl list | grep sabbo

# Stop
launchctl unload ~/Library/LaunchAgents/com.sabbo.inbox-watcher.plist

# Start
launchctl load ~/Library/LaunchAgents/com.sabbo.inbox-watcher.plist

# Tail logs
tail -f ~/.claude/inbox-watcher.log
```

To start manually without launchd (debugging):
```bash
source /Users/SabboOpenClawAI/Documents/nomad-nebula/.venv/bin/activate
python /Users/SabboOpenClawAI/Documents/nomad-nebula/execution/watch_inbox.py
```

## Task File Format

OpenClaw creates a JSON file in `/Users/Shared/antigravity/inbox/` named:
`<timestamp>-<task-type>.json`

Example: `20260220220000-build_skill.json`

## Supported Task Types

**1. ping** — health check
```json
{
  "task": "ping",
  "agent": "zeus",
  "timestamp": "2026-02-20T22:00:00"
}
```

**2. build_skill** — create a new Claude Code agent skill file
```json
{
  "task": "build_skill",
  "agent": "zeus",
  "description": "Create a webinar funnel skill for building slide decks",
  "context": "The agent should take a client name and topic and produce a full webinar outline, slide deck, and follow-up email sequence.",
  "timestamp": "2026-02-20T22:00:00"
}
```
Output: writes to `~/.claude/agents/<skill-name>.md`

**3. run_scraper** — trigger the Google Maps lead gen scraper
```json
{
  "task": "run_scraper",
  "agent": "prospecting",
  "query": "roofing companies",
  "location": "Austin TX",
  "max_results": 30,
  "timestamp": "2026-02-20T22:00:00"
}
```

**4. filter_icp** — filter a leads CSV by ICP scoring
```json
{
  "task": "filter_icp",
  "agent": "prospecting",
  "input_csv": "/Users/Shared/antigravity/outbox/leads_20260220.csv",
  "threshold": 6
}
```

**5. generate_emails** — generate personalized outreach emails
```json
{
  "task": "generate_emails",
  "agent": "outreach",
  "input_csv": "/Users/Shared/antigravity/outbox/filtered_leads_20260220.csv"
}
```

**6. generate_ad_scripts** — generate Meta/YouTube ad scripts
```json
{
  "task": "generate_ad_scripts",
  "agent": "ads-copy",
  "input_csv": "/Users/Shared/antigravity/outbox/filtered_leads_20260220.csv",
  "platform": "meta"
}
```

**7. generate_vsl** — generate a VSL script
```json
{
  "task": "generate_vsl",
  "agent": "content",
  "input_csv": "/Users/Shared/antigravity/outbox/filtered_leads_20260220.csv",
  "single": "optional-business-name"
}
```

**8. reindex** — scan for recently changed directive/agent files and return a summary
```json
{
  "task": "reindex",
  "agent": "zeus",
  "hours": 48
}
```
Output: JSON summary of all `.md` files changed in the last N hours, written to outbox.
Use this so OpenClaw knows what changed without polling manually.

**9. heartbeat** — update a bot's heartbeat.md with current status
```json
{
  "task": "heartbeat",
  "agent": "system",
  "bot": "ads-copy",
  "status": "IDLE",
  "current_task": "none",
  "queue": []
}
```
Valid bot values: `ads-copy`, `content`, `outreach`

**10. propose_edit** — queue a file edit proposal for Sabbo's review
```json
{
  "task": "propose_edit",
  "agent": "zeus",
  "target_file": "directives/email-generation-sop.md",
  "proposed_change": "Add a section on follow-up sequences after no-reply after 3 days.",
  "reason": "Current SOP has no follow-up logic. Noticed open rate is fine but reply rate is low."
}
```
Output: proposal written to `/Users/Shared/antigravity/proposals/`. Sabbo reviews and
Claude Code applies. OpenClaw NEVER self-applies directive changes.

**11. run_ide_task** — trigger Claude Code CLI to work on a project
```json
{
  "task": "run_ide_task",
  "agent": "zeus",
  "project": "nomad-nebula",
  "prompt": "Add error handling to the scraper's retry logic in execution/run_scraper.py"
}
```
Available projects: `nomad-nebula`, `saas-dashboard`, `automation-engine`, `ultraviolet-curiosity`
Output: Claude Code runs the prompt against the project directory and returns results.
Use this when OpenClaw needs Claude Code to actually write/edit code in a project.

## Bidirectional Sync Protocol

The bridge is now **bidirectional**. Both systems stay aware of each other.

### File Change Watcher
A daemon (`execution/watch_changes.py`) monitors key directories and writes real-time changes to:
`/Users/Shared/antigravity/memory/sync/changes.json`

### Notifications
After every inbox task completes, a notification is appended to:
`/Users/Shared/antigravity/memory/sync/notifications.json`

OpenClaw reads this during heartbeat to know what Claude Code did.

### How to check sync state (from OpenClaw)
- **Recent file changes:** Read `/Users/Shared/antigravity/memory/sync/changes.json`
- **Task results:** Read `/Users/Shared/antigravity/memory/sync/notifications.json`
- **Pending proposals:** Check `/Users/Shared/antigravity/proposals/`

## Result Files

Claude Code writes results to `/Users/Shared/antigravity/outbox/<task-id>-result.json`:
```json
{
  "task_id": "20260220220000-build_skill",
  "task": "build_skill",
  "agent": "zeus",
  "received_at": "2026-02-20T22:00:05",
  "status": "success",
  "output": { "skill_file": "/Users/SabboOpenClawAI/.claude/agents/...", "skill_name": "..." },
  "error": null
}
```

Processed task files are renamed to `.done` in inbox.

## How to Add a New Task Type
1. Add a handler function `handle_<type>()` in `execution/watch_inbox.py`
2. Add a routing condition in `process_task()`
3. Update this SOP with the new task type and JSON format
4. Test by dropping a sample JSON into inbox manually
5. Append to `SabboOS/CHANGELOG.md`

## Known Issues & Warnings
- If `.venv` dependencies aren't installed, execution tasks will fail — run `pip install -r requirements.txt` in the venv first
- Task files must be valid JSON — malformed files are logged as errors and left in inbox
- `propose_edit` proposals in `/proposals/` must be reviewed manually — do not auto-apply

## Last Updated
2026-02-23
