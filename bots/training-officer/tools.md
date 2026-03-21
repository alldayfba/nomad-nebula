# Training Officer Bot — Tools
> bots/training-officer/tools.md | Version 1.0

---

## Access Policy

- **Authentication:** File system access only. No external API keys required for core functions.
- **Principle:** Read-only on agent files. Write access only to proposal storage (`.tmp/training-officer/`).
- **Never store:** Credentials, API keys, or sensitive client data in proposals.

---

## Core Tools

### training_officer_scan.py

**Purpose:** Full system scan — detect changes, generate proposals, produce Training Report.
**Script:** `execution/training_officer_scan.py`
**Usage:**
```bash
python execution/training_officer_scan.py
```
**Access type:** Read (directives, execution, bots, SabboOS, CHANGELOG). Write (`.tmp/training-officer/`).

---

### agent_quality_tracker.py

**Purpose:** Track and report agent output quality over time.
**Script:** `execution/agent_quality_tracker.py`
**Usage:**
```bash
python execution/agent_quality_tracker.py --agent ads-copy --days 30
python execution/agent_quality_tracker.py --report
```
**Access type:** Read (`.tmp/training-officer/grade-history.json`). Write (reports to stdout).

---

### grade_agent_output.py

**Purpose:** Grade a specific agent output on 5 dimensions (specificity, persuasion, relevance, clarity, format compliance).
**Script:** `execution/grade_agent_output.py`
**Usage:**
```bash
python execution/grade_agent_output.py grade --agent ads-copy --output-file .tmp/ad_copy.md --task-type ad_copy
python execution/grade_agent_output.py trends --agent ads-copy --days 30
python execution/grade_agent_output.py report
```
**Access type:** Read (output files). Write (`.tmp/training-officer/grade-history.json`, proposals if score < 35/50).

---

### apply_proposal.py

**Purpose:** Apply an approved Training Proposal to the target agent file.
**Script:** `execution/apply_proposal.py`
**Usage:**
```bash
python execution/apply_proposal.py --proposal TP-2026-03-16-001
python execution/apply_proposal.py --approve-all --agent ads-copy
```
**Access type:** Read (proposal YAML). Write (target agent file, CHANGELOG.md, proposal status update).

---

### proposal_rollback.py

**Purpose:** Roll back a previously applied proposal if it causes issues.
**Script:** `execution/proposal_rollback.py`
**Usage:**
```bash
python execution/proposal_rollback.py --proposal TP-2026-03-16-001
```
**Access type:** Read (proposal YAML, rollback plan). Write (target agent file, proposal status update).

---

### agent_benchmark.py

**Purpose:** Run benchmark comparisons across agents or before/after a proposal is applied.
**Script:** `execution/agent_benchmark.py`
**Usage:**
```bash
python execution/agent_benchmark.py --agent ads-copy --before TP-2026-03-16-001
python execution/agent_benchmark.py --compare ads-copy content --metric quality
```
**Access type:** Read (grade history, agent files). Write (benchmark reports to stdout).

---

## File System

**Access type:** Read/write
**Read scope:** `bots/`, `directives/`, `execution/`, `SabboOS/`, `.claude/skills/`, `clients/`, `/Users/Shared/antigravity/memory/`, `/Users/Shared/antigravity/proposals/`
**Write scope:** `.tmp/training-officer/` (proposals, scans, learnings, grade history)
**Post-approval write:** Target agent files (only after Sabbo approves)

---

## Storage Structure

```
.tmp/training-officer/
  proposals/          <- Individual proposal YAML files
  scans/              <- Daily scan results
  learnings.md        <- Lessons from rejected proposals
  last-scan.json      <- Timestamp + file hashes from last scan
  agent-health.json   <- Current health scorecard data
  grade-history.json  <- Output quality grades over time
```

---

## What This Bot Cannot Access

- External APIs (no web scraping, no LLM calls directly)
- Ad platforms (Meta, Google, Amazon)
- Client accounts or CRM systems
- Email or messaging platforms
- Any credentials not listed in this file

---

*Training Officer Bot Tools v1.0 — 2026-03-16*
