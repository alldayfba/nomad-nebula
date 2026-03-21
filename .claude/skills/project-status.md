---
name: project-status
description: Track project health, milestones, blockers, congruence, and agent workload
trigger: when user says "project status", "where are we", "what's behind", "project health", "congruence check", "what should I work on"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

## Directive
Read `directives/project-manager-sop.md`

## Goal
Show current project health, at-risk projects, open blockers, and system congruence status.

## Inputs
- Optional: specific project name
- Optional: specific agent name (for `my-tasks`)

## Execution

### Quick Status (default)
```bash
source .venv/bin/activate && python execution/project_manager.py health-report
```

### At-Risk Projects
```bash
source .venv/bin/activate && python execution/project_manager.py at-risk
```

### Specific Project Detail
```bash
source .venv/bin/activate && python execution/project_manager.py status-report --project "project-name"
```

### System Congruence Check
```bash
source .venv/bin/activate && python execution/project_manager.py congruence
```

### My Tasks (for a specific agent)
```bash
source .venv/bin/activate && python execution/project_manager.py my-tasks --agent CEO
```

### Agent Workload
```bash
source .venv/bin/activate && python execution/project_manager.py workload
```

## Output
Present results in a clear summary. Highlight at-risk projects and critical blockers first.
If congruence issues found, list the top 3 highest-severity issues with recommended fixes.

## Self-Annealing
If the script fails:
1. Check if `.tmp/projects/` directory exists
2. If DB corrupted, delete `.tmp/projects/projects.db` and re-run
3. Update `directives/project-manager-sop.md` Known Issues
