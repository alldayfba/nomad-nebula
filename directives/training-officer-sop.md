# Training Officer SOP
> directives/training-officer-sop.md | Version 1.0

---

## Purpose

This SOP documents how the Training Officer agent operates: how it detects changes, generates upgrade proposals, manages the approval workflow, and integrates with the rest of SabboOS.

The Training Officer's full directive (report formats, proposal schema, agent registry, scan routine, guardrails) lives in `SabboOS/Agents/TrainingOfficer.md`. This SOP covers the execution layer.

---

## Trigger Phrases

| User Says | Action |
|---|---|
| "Run the training officer" | Full scan → detect changes → generate proposals → output report |
| "Train the agents" | Alias for full scan |
| "What upgrades are pending?" | List pending proposals with summaries |
| "Review agent skills" | Agent health scorecard only |
| "Agent improvement scan" | Alias for full scan |
| "Show me pending proposals" | List all pending proposals |
| "Show me TP-{id}" | Display full proposal details |
| "Approve TP-{id}" | Apply proposal → update agent file → log to CHANGELOG |
| "Reject TP-{id}" | Mark rejected → ask for reason → store learning |
| "Approve all proposals for {agent}" | Batch approve all pending for that agent |
| "How can we make {agent} better?" | Targeted analysis → proposals for specific agent |
| "Analyze [competitor] and improve our agents" | Competitive intel → proposals |

---

## Execution Flow

### Full Scan

#### Step 1 — Load State
```
Read: .tmp/training-officer/last-scan.json
  → Contains: last_scan_timestamp, file_hashes (path → mtime)
  → If file doesn't exist: first run, treat everything as new
```

#### Step 2 — Detect Changes
```
Scan these directories for modified files (compare mtime to last-scan.json):
  directives/*.md
  execution/*.py
  SabboOS/Agents/*.md
  SabboOS/*.md
  bots/**/*
  clients/**/*
  /Users/Shared/antigravity/memory/
  /Users/Shared/antigravity/proposals/

For each changed/new file:
  → Read content
  → Determine which agents are affected
  → Queue for proposal generation
```

#### Step 3 — Read CEO Brief
```
Read: .tmp/ceo/brief_{today}.md (if exists)
  → Extract "CONSTRAINT OF THE DAY" section
  → Extract "TODAY'S ACTION" section
  → Determine if constraint maps to an agent skill gap
  → If yes: queue a skill upgrade proposal
```

#### Step 4 — Read CHANGELOG
```
Read: SabboOS/CHANGELOG.md
  → Find entries after last_scan_timestamp
  → Cross-reference with agent registry
  → Flag any changes that affect agents but don't have corresponding skill updates
```

#### Step 5 — Generate Proposals
```
For each queued change:
  → Classify upgrade type (skill | context | memory | tool | sop | bio)
  → Determine target agent and target file
  → Read current content of target file
  → Generate proposed content (append/replace/insert)
  → Write proposal YAML to .tmp/training-officer/proposals/TP-{date}-{seq}.yaml
  → Increment sequence counter
```

#### Step 6 — Update Scan State
```
Write: .tmp/training-officer/last-scan.json
  → Updated timestamp
  → Updated file hashes for all monitored paths
```

#### Step 7 — Output Report
```
Use the Training Report format from TrainingOfficer.md
Print to stdout (and optionally save to .tmp/training-officer/scans/)
```

---

## CLI Execution

```bash
# Full scan (generates proposals + report)
python execution/training_officer_scan.py

# Dry run (scan only, no proposals written)
python execution/training_officer_scan.py --dry-run

# List pending proposals
python execution/training_officer_scan.py --list-pending

# Show specific proposal
python execution/training_officer_scan.py --show TP-2026-02-21-001

# Agent health check only (no proposals)
python execution/training_officer_scan.py --health
```

---

## Proposal Lifecycle

```
1. DETECTED     → Change found during scan
2. GENERATED    → Proposal YAML written to .tmp/training-officer/proposals/
3. PRESENTED    → Shown to Sabbo in Training Report or on request
4. REVIEWED     → Sabbo reads full proposal details
5. APPROVED     → Sabbo says "Approve TP-{id}"
   └─→ 5a. APPLIED   → Change written to target agent file
   └─→ 5b. LOGGED    → Entry added to SabboOS/CHANGELOG.md
   OR
5. REJECTED     → Sabbo says "Reject TP-{id}"
   └─→ 5a. LEARNING  → Reason stored in .tmp/training-officer/learnings.md
```

---

## Applying an Approved Proposal

When Sabbo approves a proposal:

1. Read the proposal YAML file
2. Read the target file specified in `target_file`
3. Apply the change based on `change_type`:
   - **append**: Add `proposed_content` to the end of the target file
   - **replace**: Find `current_content` in the target file and replace with `proposed_content`
   - **insert**: Add `proposed_content` at the specified location (after a section header, etc.)
   - **restructure**: Replace a larger section — show diff to Sabbo before applying
4. Update the proposal YAML: set `status: applied`
5. Log to `SabboOS/CHANGELOG.md`:
   ```
   | {date} | `{target_file}` | Training Officer: {title} (TP-{id}) |
   ```
6. If `dependencies` is not empty: generate follow-up proposals for affected agents

---

## Integration with Existing Tools

### allocate_sops.py
The Training Officer can invoke `allocate_sops.py` when new training materials are detected:
```bash
python execution/allocate_sops.py --source-dir /path/to/new/materials --dry-run
```
Then generate proposals based on the allocation results.

### watch_inbox.py
The Training Officer can receive async tasks via the inbox:
```json
{
  "task_type": "training_scan",
  "scope": "full",
  "priority": "normal",
  "created_at": "2026-02-21T08:00:00Z"
}
```

### CEO Agent Dispatch
The CEO agent can dispatch to the Training Officer when a constraint reveals a skill gap:
```json
{
  "task_type": "agent_dispatch",
  "agent": "training-officer",
  "constraint": "Close rate dropped to 14% — outreach agent may need updated objection handling",
  "requested_output": "Skill upgrade proposal for outreach agent",
  "priority": "high"
}
```

---

## Competitive Intelligence Workflow

When Sabbo says "Analyze [competitor] and improve our agents":

1. **Research** the competitor's public presence:
   - Website (via WebBuild-style analysis or manual input)
   - Social media (IG, YouTube, LinkedIn)
   - Ad library (Meta Ad Library, if accessible)
   - Amazon listings (if applicable)

2. **Extract** actionable intelligence:
   - Ad copy patterns and hooks
   - Offer structure and pricing
   - Content themes and formats
   - Positioning and differentiation
   - Funnel structure

3. **Map** each finding to an agent:
   - Ad hooks → ads-copy-agent
   - Offer structure → CEO context, outreach messaging
   - Content patterns → content-agent
   - Funnel design → WebBuild templates
   - Amazon tactics → amazon-agent

4. **Generate** Training Proposals for each mapped finding

5. **Present** proposals to Sabbo for approval

---

## Error Pattern Detection

When checking for error patterns:

1. Scan `/Users/Shared/antigravity/outbox/` for task results with `status: "error"` or `status: "failed"`
2. Group errors by agent and error type
3. For recurring patterns (same error 2+ times):
   - Identify root cause
   - Generate a proposal to prevent future occurrences
   - Upgrade type: usually `skill` or `sop`

---

## Files & Storage

```
.tmp/training-officer/
├── proposals/
│   ├── TP-2026-02-21-001.yaml
│   └── ...
├── scans/
│   ├── scan-2026-02-21.md
│   └── ...
├── learnings.md               ← Lessons from rejected proposals
├── last-scan.json             ← Previous scan state
└── agent-health.json          ← Health scorecard cache

SabboOS/Agents/TrainingOfficer.md  ← Full directive (do not modify without proposal)
```

---

## Quality Standards for Proposals

A good proposal:
- Has clear evidence (not "I think this would help")
- Has a specific, measurable expected impact
- Changes the minimum necessary (surgical, not sweeping)
- Includes a rollback plan
- Respects the 3-layer architecture
- Doesn't contradict standing instructions in `~/.claude/CLAUDE.md`

A bad proposal (auto-reject):
- Vague description ("improve the agent")
- No evidence or trigger
- Overly broad changes
- Breaks existing functionality
- Duplicates an existing skill

---

*Training Officer SOP v1.0 — 2026-02-21*
*Continuous improvement, always with approval.*
