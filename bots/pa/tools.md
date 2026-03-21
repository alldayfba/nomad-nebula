# PA Bot — Tools
> bots/pa/tools.md | Version 1.0

---

## Access Policy

This bot operates under principle of least privilege. All access is scoped to personal admin and research operations. No access to revenue systems, student data, ad accounts, or payment processors. Authentication via environment variables in `.env` where required. Never expose credentials or personal data in outputs.

---

## WebSearch (PRIMARY RESEARCH TOOL)

**Purpose:** Live web research — products, prices, people, news, travel, market data
**Access type:** Read (external internet)
**Usage:** MCP tool — invoke directly in conversation
**Rate:** Unlimited (no per-call cost from Anthropic, subject to MCP provider limits)

**When to use:**
- Any price or availability query (must be live — stale data is wrong data)
- Person research (LinkedIn, company pages, news)
- Product comparison across retailers
- Travel research (flights, hotels, Airbnbs)
- Market/competitor overviews
- Any factual question where recency matters

---

## WebFetch

**Purpose:** Fetch specific URLs — product pages, booking pages, articles
**Access type:** Read (external internet)
**Usage:** MCP tool — invoke with specific URL
**When to use:** When WebSearch returns a promising URL that needs full content pulled

---

## Memory Recall

**Purpose:** Search memory DB for prior preferences, decisions, research, and context
**Access type:** Read
**Script:** `execution/memory_recall.py`
**Usage:**
```bash
# General preference lookup before a research task
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula \
python3 execution/memory_recall.py --query "travel preferences" --type preference --limit 5

# Research a person or topic
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula \
python3 execution/memory_recall.py --query "[person or topic]" --limit 5

# Find past purchase decisions
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula \
python3 execution/memory_recall.py --query "purchase [category]" --type decision --limit 3
```
**Database:** `/Users/Shared/antigravity/memory/ceo/memory.db`

---

## Memory Store

**Purpose:** Persist new preferences, purchases, vendor notes, and decisions
**Access type:** Read / Write
**Script:** `execution/memory_store.py`
**Usage:**
```bash
# Store a new preference
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula \
python3 execution/memory_store.py add \
  --type preference --category general \
  --title "[one-line summary]" \
  --content "[full detail]" \
  --tags "[comma,separated,tags]"

# Store a purchase decision
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula \
python3 execution/memory_store.py add \
  --type decision --category general \
  --title "Purchased: [product] — $[price]" \
  --content "[product details, where bought, why chosen, link]" \
  --tags "purchase,[category],[vendor]"

# Update existing knowledge
PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula \
python3 execution/memory_store.py update \
  --search "[what to find]" --content "[new info]" --reason "[why changed]"
```

---

## Deadlines / Reminders

**Purpose:** Add, update, and query personal reminders, bill payments, renewals, appointments
**Access type:** Read / Write
**Script:** `/Users/Shared/antigravity/tools/deadlines.py`
**Usage:**
```bash
# Add a reminder
python /Users/Shared/antigravity/tools/deadlines.py add-deadline \
  --title "[reminder title]" \
  --date "YYYY-MM-DD" \
  --notes "[context]"

# Quick view — next 7 days
python /Users/Shared/antigravity/tools/deadlines.py quick

# Full overview
python /Users/Shared/antigravity/tools/deadlines.py overview

# Update existing
python /Users/Shared/antigravity/tools/deadlines.py update \
  --title "[title]" --field notes --value "[updated notes]"
```
**Storage:** `/Users/Shared/antigravity/memory/deadlines.md`

---

## Timeclock

**Purpose:** Check current session timing and work context
**Access type:** Read
**Script:** `/Users/Shared/antigravity/tools/timeclock.py`
**Usage:**
```bash
python /Users/Shared/antigravity/tools/timeclock.py quick
```
**When to use:** When Sabbo asks "how long have we been working" or when prep requires knowing the time budget for a task

---

## Morning Briefing

**Purpose:** Pull Sabbo's full daily context — open tasks, schedule, priorities, deadlines
**Access type:** Read
**Script:** `execution/send_morning_briefing.py`
**Usage:**
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && \
source .venv/bin/activate && \
python execution/send_morning_briefing.py
```
**When to use:** "What's on today?", "Morning brief", or when doing meeting/call prep that needs full context

---

## File System

**Purpose:** Read/write working files within PA scope
**Access type:** Read/Write (scoped)
**Allowed paths:**
- `bots/pa/` — Bot config files (read/write)
- `.tmp/pa/` — Research outputs, drafts, snapshots (read/write)
- `SabboOS/` — Business OS docs (read-only), CHANGELOG (append)
- `directives/` — SOPs (read-only)
- `/Users/Shared/antigravity/memory/` — Memory and deadlines files (read/write via tools)

---

## What This Bot Cannot Access

- Payment processors (Stripe, PayPal) — no direct access, no transactions
- Student health data (`students.db`) — CSM's domain
- Ad accounts or campaign data — Media Buyer's domain
- GHL CRM — Sales Manager's domain
- Discord API — CSM and Nova's domain
- Credentials, API keys, or `.env` — environment only, never echoed in output
- Other bots' memory files — read-only at best, write only to `bots/pa/`

---

## API Budget

- Monthly token ceiling: Follow `directives/api-cost-management-sop.md`
- Sonnet for research summaries, drafts, structured outputs
- Haiku for quick lookups, reminder adds, short definitions
- Opus reserved for high-stakes drafts (legal-adjacent, sensitive negotiations) — approval required

---

*PA Bot Tools v1.0 — 2026-03-16*
