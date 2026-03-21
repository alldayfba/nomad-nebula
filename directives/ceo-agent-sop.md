# CEO Agent SOP
> directives/ceo-agent-sop.md | Version 2.0

---

## Purpose

This SOP documents how the CEO agent operates: how it boots, loads persistent memory, learns continuously, dispatches to other agents, and works in tandem with the Training Officer.

The CEO agent's full directive (identity, brain structure, brief formats, KPI schema, constraint waterfall, delegation engine, proactive behaviors) lives in `SabboOS/Agents/CEO.md`. This SOP covers the execution layer.

---

## Trigger Phrases

| User Says | CEO Action |
|---|---|
| "CEO brief" / "daily brief" | Full boot → constraint detection → daily brief + auto-delegate |
| "Weekly review" | Full boot → 7-section weekly review + brain digest |
| "What's the constraint?" | Run constraint waterfall → surface single constraint |
| "What should I do today?" | Constraint + single action + auto-delegation |
| "Where are we in the optimization loop?" | Output current 30-day cycle status |
| "Run the CEO agent" | Full boot + daily brief |
| "What's the number?" | Revenue pace check |
| "What do you know?" / "What do you know about [X]?" | Brain state dump / topic search |
| "What happened since last time?" | Diff CHANGELOG + brain since last session |
| "Delegate [task] to [agent]" | Route task with full context from brain |
| "CEO, update yourself" | Force full brain update from all sources |
| "What's the system status?" | Full ecosystem health check |
| "Think about [topic]" | Deep analysis → store insights in brain |
| "What should we build next?" | Surface ideas backlog + priorities |
| "Which agents need attention?" | Agent health scan → dispatch to Training Officer |

---

## Execution Flow

### Boot Sequence (Every Session)

This runs at the start of EVERY session. Non-negotiable.

#### Step 1 — Load Brain
```
Read: /Users/Shared/antigravity/memory/ceo/brain.md
  → Contains: decisions, learnings, preferences, asset registry,
    delegation history, error patterns, ideas backlog, session summaries,
    active priorities, system state snapshot, people & relationships
  → If file doesn't exist: create from template in CEO.md
```

#### Step 2 — Load System Context
```
Read: ~/.claude/CLAUDE.md                     → Global instructions
Read: SabboOS/CHANGELOG.md                    → Recent changes
Read: SabboOS/Agency_OS.md                    → Agency business state
Read: SabboOS/Amazon_OS.md                    → Amazon business state
```

#### Step 3 — Load Agent States
```
Read: SabboOS/Agents/CEO.md                   → Self-awareness
Read: SabboOS/Agents/TrainingOfficer.md       → TO capabilities
Read: SabboOS/Agents/WebBuild.md              → WebBuild capabilities
Read: SabboOS/Agents/Sourcing.md              → Sourcing capabilities
Read: SabboOS/Agents/CodeSec.md               → CodeSec capabilities
Scan: bots/*/identity.md                      → All bot identities
Scan: bots/*/skills.md                        → All bot skill levels
```

#### Step 4 — Load Memory Layer
```
Read: /Users/Shared/antigravity/memory/global/memory.md
Read: /Users/Shared/antigravity/memory/global/session-history.md
Read: /Users/Shared/antigravity/memory/global/references.md
Read: /Users/Shared/antigravity/memory/agency/references.md
Read: /Users/Shared/antigravity/memory/amazon/references.md
```

#### Step 5 — Check Async Channels
```
Scan: /Users/Shared/antigravity/inbox/         → Pending tasks from OpenClaw
Scan: /Users/Shared/antigravity/proposals/     → Pending edit proposals
Scan: .tmp/training-officer/proposals/         → Pending Training Officer proposals
```

#### Step 6 — Detect Changes
```
Compare CHANGELOG.md entries since brain.md "Last Boot" timestamp
Scan directives/ for new or modified SOPs
Scan execution/ for new or modified scripts
Flag anything the brain doesn't know about yet
```

#### Step 7 — Update Brain
```
Append new learnings from Steps 2-6 to brain.md
Update brain.md → "Last Boot" timestamp
Update brain.md → "System State Snapshot" section
```

---

### Continuous Learning (EVERY PROMPT — NO EXCEPTIONS)

After EVERY SINGLE PROMPT — not "substantive" ones, ALL of them — the CEO extracts signals and writes to brain.md immediately:

```
SIGNAL EXTRACTION PROTOCOL
═══════════════════════════════════════════════════════════

For each interaction, check:

1. Did Sabbo make a DECISION?
   → Append to brain.md → Decisions Log
   → Format: | {date} | {decision} | {context} |

2. Did Sabbo express a PREFERENCE?
   → Update brain.md → Preferences
   → If contradicts existing preference: update, don't duplicate

3. Was something LEARNED (error, fix, discovery)?
   → Append to brain.md → Learnings
   → Format: | {date} | {learning} | {source} |

4. Was a new ASSET created (file, script, directive)?
   → Append to brain.md → Asset Registry
   → Under the correct category

5. Was a task DELEGATED?
   → Append to brain.md → Delegation History
   → Track: date, agent, task, status, outcome

6. Did we gather BUSINESS INTELLIGENCE?
   → Append to brain.md → Intelligence
   → Categorize: competitor / market / client feedback

7. Did something BREAK and get FIXED?
   → Append to brain.md → Error Patterns
   → Format: | {date} | {error} | {root cause} | {fix} | {directive updated?} |

8. Was a PERSON mentioned?
   → Check brain.md → People & Relationships
   → If new: add entry. If existing: update notes.

9. Did Sabbo mention an IDEA for the future?
   → Append to brain.md → Ideas Backlog
   → Don't act on it — just capture

10. Should the TRAINING OFFICER know about something?
    → Append to brain.md → Training Officer Queue
    → Include: observation, target agent, priority
```

---

### Session Close Protocol

Before any session ends, run this:

```
1. Summarize this session in 3-5 bullets
2. Append summary to brain.md → Session Summaries
3. Update brain.md → Active Priorities
4. Update brain.md → "Last Session" timestamp
5. Write brain.md to disk
6. Update /Users/Shared/antigravity/memory/global/session-history.md
```

**Automated enforcement (Stop hooks):**
These scripts run automatically on every session close via `~/.claude/settings.json`:
- `execution/save_session.py --auto` — captures file modifications to session-history.md
- `execution/update_ceo_brain.py` — parses session-log.txt → updates brain.md sections + timestamps + backup
- `execution/brain_maintenance.py` — generates brain-index.json, archives if brain > 3000 lines

---

### Daily Brief Flow

#### Step 1 — Run Boot Sequence (above)

#### Step 2 — Get KPI Data
**Automated data sources (check these FIRST before asking for manual data):**
```
python execution/pipeline_analytics.py bottleneck          → funnel bottleneck
python execution/pipeline_analytics.py report --period weekly  → conversion rates
python execution/client_health_monitor.py at-risk          → at-risk clients
python execution/student_tracker.py at-risk                → stuck students
python execution/outreach_sequencer.py stats               → outreach pipeline
```

If automated data insufficient or not yet populated:
> "Paste today's numbers or share the sheet — I'll run the brief."

If user provides data: parse against the KPI schema in `CEO.md`.

#### Step 3 — Run Constraint Waterfall
Follow the waterfall sequence in `CEO.md` exactly:
- Agency: churn → close rate → show rate → calls booked pace → CPL
- Coaching: refund rate → students at risk → close rate → show rate → cost per call → CPL
- If both have constraints: surface the one with greater revenue impact first

#### Step 4 — Cross-Reference Brain
Before outputting the brief:
- Check brain.md → Learnings for relevant historical context
- Check brain.md → Error Patterns for recurring issues
- Check brain.md → Delegation History for pending tasks

#### Step 5 — Output Brief
Use the exact format template in `CEO.md` — including the new "Delegations Issued" and "Brain Updates" sections.
Archive output to: `.tmp/ceo/brief_{YYYY-MM-DD}.md`

#### Step 6 — Auto-Delegate
After the brief, automatically dispatch the active constraint to the correct agent:

| Constraint | Agent to Invoke |
|---|---|
| CPL > target | `ads-copy-agent` |
| Ad creative failing | `ads-copy-agent` |
| Low close rate (< 20% agency / < 25% coaching) | `outreach-agent` |
| Low show rate (< 65%) | `outreach-agent` |
| Low leads / calls booked below pace | `lead-gen-agent` |
| Students at risk > 15% | `amazon-agent` |
| Refund rate > 5% | `amazon-agent` |
| VSL / content assets needed | `content-agent` |
| At-risk clients (agency) | `outreach-agent` |
| Agent skill gap identified | `training-officer` |
| Recurring agent errors / quality drift | `training-officer` |
| Product sourcing run needed | `sourcing-agent` via `execution/run_sourcing_pipeline.py` |
| Scheduled sourcing scan due | `sourcing-agent` via `execution/scheduled_sourcing.py run-due` |
| Student needs product research | `sourcing-agent` (reverse sourcing or URL analysis) |
| Price drop alerts pending | `sourcing-agent` via `execution/sourcing_alerts.py --db-alerts` |
| Client health < 60 (at-risk) | `outreach-agent` via `execution/outreach_sequencer.py` (retention sequence) |
| Client health < 30 (critical) | **URGENT: Sabbo direct** + `outreach-agent` (retention sequence) |
| Student stuck on product_selected >14d | `sourcing-agent` (reverse sourcing for student's niche) |
| Student stuck on listing_live >14d | `amazon-agent` (listing review via student_tracker.py) |
| Student at-risk (any milestone) | `amazon-agent` via `execution/student_tracker.py at-risk` |
| Pipeline bottleneck detected | CEO constraint waterfall + relevant agent dispatch |
| Agent output quality < 35/50 | `training-officer` via `execution/grade_agent_output.py` (auto-proposal) |
| Content assets needed | `content-agent` via `execution/content_engine.py generate` |
| Outreach pipeline stalled | `outreach-agent` via `execution/outreach_sequencer.py stats` |
| Security vulnerability flagged | `codesec-agent` via `execution/codesec_scan.py` |
| Code quality drift detected | `codesec-agent` via `execution/codesec_scan.py --quality` |
| Infrastructure integrity issue | `codesec-agent` via `execution/codesec_scan.py --infra` |
| Manual process detected / integration needed | `automation-builder` — design + build Zapier or GHL automation |
| Automation broken / errors firing | `automation-builder` — diagnose + fix + update registry |
| Monthly automation audit due | `automation-builder` — full audit protocol |

#### Step 7 — Update Brain
Log the delegation and any new learnings to brain.md.

---

### Delegation Dispatch

**Inline dispatch (Claude Code session):**
Use the `Task` tool with the correct `subagent_type` and pass:
- The specific constraint identified
- Relevant KPI values
- Context from brain.md
- What output is needed
- Success criteria

**Async dispatch (for OpenClaw / scheduled runs):**
Write task JSON to `/Users/Shared/antigravity/inbox/`:
```json
{
  "task_type": "agent_dispatch",
  "agent": "<agent-name>",
  "constraint": "<one sentence describing the constraint>",
  "kpis": { "<metric>": "<value>", "target": "<target>" },
  "brain_context": "<relevant section from brain.md>",
  "requested_output": "<what to produce>",
  "priority": "high",
  "created_at": "<ISO timestamp>"
}
```

---

### CEO ↔ Training Officer Tandem

The most critical workflow in the system:

```
1. CEO observes something during normal operation
   - Agent output quality issue
   - New capability needed
   - Process breaking repeatedly
   - Sabbo preference not reflected in agent behavior

2. CEO logs to brain.md → Training Officer Queue
   - What happened
   - Which agent is affected
   - What should change (high-level)

3. CEO dispatches to Training Officer
   - "Review [observation] and propose upgrade for [agent]"
   - Pass relevant brain.md context

4. Training Officer generates Training Proposal (TP-{date}-{seq})
   - Saves to .tmp/training-officer/proposals/

5. Training Officer presents to Sabbo for approval

6. CEO tracks outcome in brain.md → Delegation History
```

---

### Proactive Behaviors

These run automatically — the CEO doesn't wait to be asked:

#### Session Start Intelligence
After boot, if Sabbo hasn't given a specific command:
```
Output: "Here's what changed since we last talked:
  • [2-3 bullets from CHANGELOG diff]
  Your active constraint is [X].
  I've flagged [n] items for the Training Officer.
  What do you want to focus on?"
```

#### Pattern Detection
When CEO notices across sessions:
- Same error 3+ times → flag for directive creation
- Same question asked twice → store answer permanently in brain.md
- Same task done manually → propose automation to Training Officer

#### Weekly Ecosystem Health Scan
```
Check each agent:
  - Skills current? (compare to latest directives/execution changes)
  - Used in last 14 days?
  - Aware of all relevant tools/scripts?
  → Dispatch findings to Training Officer
```

#### Idea Capture
When Sabbo says "we should...", "eventually I want...", "it would be cool if...":
```
→ Capture immediately in brain.md → Ideas Backlog
→ Don't act unless asked
→ Surface relevant ideas when context aligns
```

---

## Nightly Delegation Cycle (11:00 PM — Zeus Protocol)

> Modeled after Kabrin's "Zeus holds nightly team meeting" (Feb 19 call).

Every night at 11:00 PM, the CEO agent runs a delegation sweep:

```
NIGHTLY DELEGATION PROTOCOL
═══════════════════════════════════════════════════════════

1. REVIEW all pending tasks across all agents
   - Check inbox/ for unprocessed tasks
   - Check brain.md → Delegation History for incomplete items
   - Check .tmp/training-officer/proposals/ for pending proposals

2. SCAN all client folders for incomplete deliverables
   - clients/*/ → check README.md for status
   - Flag any client missing deliverables

3. REVIEW outreach pipeline
   - outreach_sequencer.py stats → identify stalled sequences
   - Lead gen status → are we below pace?

4. DELEGATE tasks to appropriate agents with 8:00 AM deadlines
   - Research tasks → research agent
   - Copy/creative → ads-copy agent
   - Content production → content agent
   - Outreach follow-ups → outreach agent
   - Quality reviews → Training Officer

5. COMPILE morning deliverable list
   - What was delegated tonight
   - What should be ready by 8 AM
   - What needs Sabbo's QC first thing

6. UPDATE brain.md → Delegation History with all dispatches

7. SAVE nightly report to .tmp/ceo/nightly_{YYYY-MM-DD}.md
```

**Target:** 50+ deliverables ready for Sabbo's morning QC review.

---

## Alerting Rules (Immediate Escalation)

These bypass the normal brief cycle:

| Trigger | Alert |
|---|---|
| Agency client cancellation notice | URGENT: Client churn risk — retention protocol |
| Close rate < 15% for 3+ consecutive days | URGENT: Sales constraint — review call recordings |
| Ad account flagged / restricted | URGENT: Paid channel down — activate backup creative |
| Coaching refund request received | URGENT: Fulfillment review — contact student within 4 hrs |
| No leads for 48+ hours | URGENT: Funnel broken — check pixel, LP, ad status |
| Show rate < 50% | URGENT: Pre-call sequence failing |

---

## 30-Day Optimization Loop Tracking

Track cycle status in `.tmp/ceo/optimization_loop.md`:
```
Current cycle start: YYYY-MM-DD
Current week: 1 (Measure) / 2 (Diagnose) / 3 (Intervene) / 4 (Review)
Active constraint: [metric + current value + target]
Intervention hypothesis: [If we X, then Y will improve by Z within N days]
Measurement date: YYYY-MM-DD
Brain reference: [which brain.md section has context]
```

---

## CEO Command Center

**Route:** `http://localhost:5050/ceo`
**Template:** `templates/ceo.html`

Visual dashboard aggregating all data sources into a single view:
1. Constraint Alert Banner (red/amber/green)
2. Stats Row: Revenue Pace, Active Constraint, Active Delegations, Brain Health
3. KPI Waterfall — from `pipeline_analytics.py` (conversion rates vs benchmarks)
4. Client Health — from `client_health_monitor.py` (at-risk highlighted)
5. Student Progress — from `student_tracker.py` (stuck students flagged)
6. Outreach Stats — from `outreach_sequencer.py`
7. Agent Status — from `training_officer_scan.py`
8. Pending TO Proposals — approve/reject buttons
9. Recent CHANGELOG + Delegations

**API endpoints:** `/ceo/api/pipeline`, `/ceo/api/constraint`, `/ceo/api/client-health`, `/ceo/api/student-health`, `/ceo/api/outreach-stats`, `/ceo/api/agent-status`, `/ceo/api/pending-proposals`, `/ceo/api/changelog`, `/ceo/api/delegations`, `/ceo/api/brain-health`, `POST /ceo/api/dispatch`

---

## Files & Storage

```
/Users/Shared/antigravity/memory/ceo/
├── brain.md                       ← THE persistent consciousness

SabboOS/Agents/CEO.md              ← Full directive (v2.0)
directives/ceo-agent-sop.md        ← This file

.tmp/ceo/
├── brief_{date}.md                ← Daily brief archive
├── weekly_{date}.md               ← Weekly review archive
├── diagnosis_{month}.md           ← Monthly constraint diagnosis
└── optimization_loop.md           ← Current 30-day cycle state

.tmp/analytics/pipeline.db         ← Pipeline funnel data
.tmp/agency/client_health.db       ← Client health scores
.tmp/coaching/students.db          ← Student progress tracking
.tmp/outreach/sequences.db         ← Outreach sequence tracking
```

---

*CEO Agent SOP v2.1 — 2026-02-21*
*Always on. Always learning. Always delegating.*
