# Project Manager — Tools

## Active Tools
| Tool | Script | Status | Invocation |
|---|---|---|---|
| Project Manager CLI | `execution/project_manager.py` | Active | `python execution/project_manager.py <cmd>` |
| Agent Comms | `execution/agent_comms.py` | Active | Used for escalations |

## CLI Commands
```
add-project, update-project, list-projects, project-detail, archive-project
add-milestone, update-milestone, list-milestones
add-task, update-task, my-tasks, list-tasks
add-dep, list-deps, resolve-dep
add-blocker, resolve-blocker, list-blockers
assign, unassign, workload
health-report, at-risk, status-report, congruence, dashboard-data, briefing-feed
```

## Planned Access
| Tool | Purpose | Status |
|---|---|---|
| Google Sheets integration | Sync project data to sheets | Future |
| GHL pipeline sync | Mirror projects to GHL pipelines | Future |

## Access Policy
- Read-only access to all directives, scripts, bots, skills
- Write access to `.tmp/projects/` database only
- Read access to agent comms inbox for stale message detection
- Read access to memory.db for health checking
