# Bidirectional Sync SOP — Claude Code ↔ OpenClaw

## Purpose

Keep both agents in sync at all times so neither is flying blind:
- OpenClaw knows everything Claude Code has built
- Claude Code knows every decision and conversation Sabbo has had with OpenClaw

This is the infrastructure layer that makes the two-agent ecosystem coherent.

---

## Architecture

```
Claude Code (sabbojb)                    OpenClaw (SabboOpenClawAI)
        |                                          |
   [builds file]                        [Sabbo asks something]
        |                                          |
        v                                          v
memory_file_change.py                    drop sync_memory task
  + openclaw_bridge.py                     to inbox/ OR
        |                                write to event-bus/oc/
        |                                          |
        v                                          v
OC workspace/MEMORY.md          <──    watch_openclaw_events.py
event-bus/cc/*.json              (daemon, 30s poll, sabbojb)
        |                                          |
        v                                          v
OpenClaw reads on bootstrap           memory.db (shared SQLite)
```

### Shared Event Bus

```
/Users/Shared/antigravity/memory/sync/event-bus/
├── cc/   ← Claude Code writes JSON here (file changes, builds, decisions)
└── oc/   ← OpenClaw writes JSON here (conversations, decisions, user asks)
```

---

## Channel A: Claude Code → OpenClaw

**Automatic (PostToolUse hook):**

Every time Claude Code edits or creates a tracked file (`directives/`, `execution/`,
`SabboOS/`, `bots/`, `clients/`):

1. `memory_file_change.py` stores event in `memory.db`
2. Calls `openclaw_bridge.notify_build()` which:
   - Appends entry to `OC_WORKSPACE/MEMORY.md` (rolling 30-entry window)
   - Writes `event-bus/cc/TIMESTAMP-build.json`

OpenClaw loads `MEMORY.md` on every agent bootstrap — it automatically knows what
Claude Code built since last session.

**Manual (from Claude Code):**

To push a specific decision/learning to OpenClaw:
```bash
PYTHONPATH=/path/to/nomad-nebula python3 execution/openclaw_bridge.py event \
    --type decision \
    --title "Switched sourcing to zero-token-first" \
    --content "Full rationale here" \
    --tags "sourcing,fba,decision"
```

---

## Channel B: OpenClaw → Claude Code

### Method 1 — sync_memory task (recommended for explicit pushes)

OpenClaw drops a JSON file in `/Users/Shared/antigravity/inbox/`:

**Filename:** `YYYYMMDDHHMMSS-sync_memory.json`

```json
{
  "task": "sync_memory",
  "entries": [
    {
      "type": "decision",
      "category": "amazon",
      "title": "Sabbo decided to launch Mike's first shipment by April 1",
      "content": "Full context of the conversation...",
      "tags": "amazon,student,milestone"
    }
  ],
  "source": "openclaw",
  "timestamp": "2026-03-16T15:00:00"
}
```

`watch_inbox.py` picks this up within 5 seconds and stores all entries in `memory.db`.

### Method 2 — Event bus JSON (for lightweight real-time events)

Write a JSON file to `/Users/Shared/antigravity/memory/sync/event-bus/oc/`:

```json
{
  "source": "openclaw",
  "timestamp": "2026-03-16T15:00:00Z",
  "type": "decision",
  "category": "general",
  "title": "Sabbo wants to test $47/mo Starter tier this week",
  "content": "Came up during strategy discussion. Decision: soft-launch Whop Starter tier by 2026-03-20.",
  "tags": "pricing,amazon,decision"
}
```

`watch_openclaw_events.py` (daemon, 30s poll) picks this up and stores in `memory.db`.

### Method 3 — Session memory (automatic on /new or /reset)

OpenClaw's built-in `session-memory` hook saves session transcripts to
`OC_WORKSPACE/memory/YYYY-MM-DD-slug.md` whenever Sabbo types `/new` or `/reset`.

`watch_openclaw_events.py` scans this directory every 30s and syncs new files.

---

## Daemons (always-on, launchd on sabbojb)

| Label | Script | Purpose |
|---|---|---|
| `com.sabbo.inbox-watcher` | `watch_inbox.py` | Task queue (all task types incl. sync_memory) |
| `com.sabbo.openclaw-sync` | `watch_openclaw_events.py` | OC session memory + event bus → memory.db |

**Check status:**
```bash
launchctl list | grep sabbo
```

**Restart after script changes:**
```bash
launchctl unload /Users/sabbojb/Library/LaunchAgents/com.sabbo.openclaw-sync.plist
launchctl load   /Users/sabbojb/Library/LaunchAgents/com.sabbo.openclaw-sync.plist
```

**Logs:**
```bash
tail -f /Users/sabbojb/.claude/openclaw-sync.log
tail -f /Users/sabbojb/.claude/inbox-watcher.log
```

---

## OpenClaw Workspace Files

| File | Purpose | Updated by |
|---|---|---|
| `BOOT.md` | Loaded on gateway startup — explains full ecosystem and how to sync | Manual |
| `MEMORY.md` | Loaded on every agent bootstrap — contains latest CC build log | `openclaw_bridge.py` (automatic) |
| `memory/*.md` | Session transcripts from /new or /reset | OpenClaw session-memory hook |

All files are at `/Users/SabboOpenClawAI/.openclaw/workspace/main/`.

---

## Key Files

| File | Purpose |
|---|---|
| `execution/openclaw_bridge.py` | CC→OC notify + event bus utilities |
| `execution/memory_file_change.py` | PostToolUse hook (calls openclaw_bridge) |
| `execution/watch_openclaw_events.py` | OC→CC daemon |
| `execution/watch_inbox.py` | Task queue daemon (handles sync_memory) |
| `/Users/Shared/antigravity/memory/sync/event-bus/` | Shared event bus |

---

## What OpenClaw Knows Automatically

- Every file Claude Code edits in tracked dirs (via MEMORY.md rolling log)
- Explicit decisions Claude Code writes via `openclaw_bridge.py event`
- Results of any task it drops in the inbox (via outbox/ result files)

## What Claude Code Knows Automatically

- Every OpenClaw session transcript (via session-memory hook → watch_openclaw_events)
- Explicit syncs OpenClaw pushes via `sync_memory` task or event bus
- Everything in `memory.db` (thousands of entries, BM25 searchable)
