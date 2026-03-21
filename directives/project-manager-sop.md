# Project Manager SOP
> directives/project-manager-sop.md | v1.0

## Purpose
Track all projects, milestones, tasks, dependencies, and blockers across Agency OS and Amazon OS. Calculate health scores, detect at-risk projects, run system congruence checks, and feed the CEO morning briefing.

## When to Use
- User says "project status", "where are we", "what's behind", "what should I work on"
- Daily morning briefing needs project data
- New project or initiative kicks off
- Checking system alignment (congruence)

## Inputs
- Project name, business unit (agency/amazon/internal/both), owner, priority, target date
- Milestones with due dates and expected durations
- Tasks assigned to agents with priorities
- Blockers with severity levels
- Cross-project dependencies

## Tools
- **Script:** `execution/project_manager.py` (all subcommands)
- **Database:** `.tmp/projects/projects.db` (SQLite)
- **Agent comms:** `execution/agent_comms.py` (for escalations)

## Execution

### Creating a Project
```bash
python execution/project_manager.py add-project \
    --name "Project Name" \
    --business agency \
    --owner CEO \
    --priority high \
    --target-date 2026-04-15 \
    --path /path/to/project
```

### Adding Milestones
```bash
python execution/project_manager.py add-milestone \
    --project "Project Name" \
    --name "MVP Launch" \
    --due-date 2026-04-01 \
    --expected-days 14 \
    --owner WebBuild
```

### Adding Tasks
```bash
python execution/project_manager.py add-task \
    --project "Project Name" \
    --milestone "MVP Launch" \
    --title "Build homepage" \
    --owner WebBuild \
    --priority high
```

### Health Check
```bash
python execution/project_manager.py health-report
python execution/project_manager.py at-risk
```

### Congruence Check
```bash
python execution/project_manager.py congruence
```
Checks 8 dimensions:
1. Directive→Script alignment (referenced scripts exist)
2. Agent→Skill alignment (skills map to agents)
3. Bot file completeness (5 required files per bot)
4. Skill→Directive alignment (referenced directives exist)
5. Cross-project dependency health
6. Stale agent comms (inbox >48h)
7. Memory system health
8. Documentation accuracy (script counts)

### Morning Briefing Feed
```bash
python execution/project_manager.py briefing-feed
```
Returns JSON with active count, at-risk list, blocked count, upcoming milestones.

## Health Scoring (0-100)
| Dimension | Weight | What It Measures |
|---|---|---|
| Schedule | 25% | Milestones on time vs overdue |
| Velocity | 20% | Task completion rate vs expected |
| Blockers | 20% | Open blocker count and severity |
| Scope | 15% | Task count drift from original |
| Engagement | 10% | Days since last activity |
| Dependencies | 10% | Blocked dependency count |

**Thresholds:** 70+ healthy, 40-69 at-risk, <40 critical

## Auto-Escalation Rules
- Health score drops below 40 → escalate to CEO via agent_comms
- Critical blocker open >48h → escalate to CEO
- Milestone overdue >7 days → escalate to CEO

## Self-Annealing
- If DB missing or corrupted → recreate from schema
- If congruence finds issues → log and report, don't auto-fix
- Update this directive when new check dimensions are discovered

## Output
- Health reports (text)
- At-risk project lists (JSON)
- Congruence check results (text + JSON)
- Dashboard data (JSON for web UI)
- Briefing feed (JSON for morning brief)
- Status reports per project (text)

## Known Issues
- None yet (v1.0)
