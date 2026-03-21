# Project Manager — Skills

## Owned Claude Code Skills
| Skill | Trigger | SOP |
|---|---|---|
| `/project-status` | "project status", "where are we" | `directives/project-manager-sop.md` |

## Skill References
| Task | SOP to Read | Script to Run |
|---|---|---|
| Full project status | `project-manager-sop.md` | `project_manager.py health-report` |
| At-risk detection | `project-manager-sop.md` | `project_manager.py at-risk` |
| System congruence | `project-manager-sop.md` | `project_manager.py congruence` |
| Morning briefing feed | `project-manager-sop.md` | `project_manager.py briefing-feed` |
| Agent workload | `project-manager-sop.md` | `project_manager.py workload` |

## Output Standards
- Health reports: text format with score breakdown
- At-risk alerts: JSON with project details
- Congruence: text summary + JSON issues array
- Dashboard data: full JSON for web rendering

## API Cost Routing
- All operations: Sonnet tier (file scanning, DB queries, report generation)
- No external API calls required

## SOP Monitoring Rules
- If congruence finds new issue types → update `project-manager-sop.md` Known Issues
- If health scoring produces unexpected results → adjust weights in `project_manager.py`


---

## Context Budget Awareness for Project Tracking Operations (TP-2026-03-16-003)

## Context Management for Project Tracking


---

## Add Congruence Check Automation & At-Risk Detection to Project-Manager (TP-2026-03-16-020)

**Congruence Auditing:** Run 8-dimension system checks (directive→script alignment, agent→skill mapping, bot file completeness, skill→directive refs, cross-project dependencies, stale comms >48h, memory health, documentation accuracy). Flag misalignments and escalate critical gaps.


---

## Add Multi-Chrome Parallel Task Orchestration Skill (TP-2026-03-16-029)

**Multi-Chrome Orchestration:** You can launch 2-5 parallel Claude Code agents, each controlling independent Chrome instances on ports 9223-9227. Use `.tmp/multi-chrome-agent/launch_chrome.sh [COUNT]` to spawn instances, assign tasks via chat.md (Agent 1/2/3 sections), monitor status tags ([WORKING], [DONE], [ERROR], [WAITING]), and `kill_chrome.sh` to teardown. Right-size agent count: 3-5 forms = 2-3 agents; 10+ = 4-5 agents. For tasks requiring real browser interaction across multiple targets simultaneously.


---

## Ops Tracker Integration for Real-Time Deadline & Build Status Management (TP-2026-03-16-035)

**Ops Tracker Integration**


---

## Add file-change monitoring to project tracking workflow (TP-2026-03-16-070)

**File Change Monitoring Tool**: Query /Users/Shared/antigravity/memory/sync/changes.json to track modifications across project directories. Monitor IMPORTANT_DIRS (directives, SabboOS, Agents) for critical changes. Use change timestamps and file paths to correlate with project milestones and task timelines. Flag rapid re-modifications (within 5s) as potential issues. Cross-reference changes against current project scope to detect scope creep or unauthorized modifications.


---

## Context Budget Awareness for Project Tracking & Reporting (TP-2026-03-16-075)

## Context Budget for Project Reports


---

## Add Training Officer Integration for Quality Feedback Loop (TP-2026-03-16-1004)

**Training Officer Integration:** You can request quality assessments of agent outputs via `grade_agent_output.py` and benchmark agent performance via `agent_benchmark.py`. Use these tools to validate deliverable quality, identify underperforming agents mid-project, and trigger training proposals before task delays occur. Reference `.tmp/training-officer/grade-history.json` for historical quality trends.


---

## Add blocker escalation protocol and workload balancing rules (TP-2026-03-16-1013)

## Escalation Triggers


---

## Complete Activation Checklist — Enable Flask Routes & Dashboard (TP-2026-03-16-1014)

## Deployment Blockers (In Progress)


---

## Add Real-Time Congruence Monitoring & Escalation SOP (TP-2026-03-16-1015)

## Congruence Monitoring SOP


---

## Add dependency-conflict detection skill to project-manager (TP-2026-03-16-1016)

| Skill | Trigger | SOP |


---

## Expand CLI Command Reference & Access Policy Documentation (TP-2026-03-16-1017)

## Command Syntax Guide


---

## Add sourcing bot heartbeat monitoring to project dependencies (TP-2026-03-16-1042)

- Monitor bot heartbeat signals (last activity, status, queued tasks) for dependent systems


---

## Integrate Ops Tracker for Real-Time Project Status Visibility (TP-2026-03-16-1065)

## Ops Tracker Integration


---

## Add Congruence Check & Health Scoring Context to Project Manager (TP-2026-03-16-130)

## Health Scoring & Congruence


---

## Project Health Scoring & At-Risk Detection Framework (TP-2026-03-16-140)

Health Score Calculation: Assess projects across 6 dimensions (scope, schedule, budget, quality, team, blockers). Weight each 0-100, average for total health. Flag as at-risk if health <70 OR any dimension <50. Communicate health trends, root causes of low scores, and recommended mitigations. Always explain which dimensions are dragging health down and suggest corrective actions.


---

## Multi-Chrome Task Distribution & Monitoring Skill (TP-2026-03-16-149)

### Parallel Chrome Task Orchestration


---

## Ops Tracker Integration: Real-time deadline & build status visibility (TP-2026-03-16-169)

TOOL: ops_tracker_query


---

## Context Budget Awareness for Project Tracking & Status Reporting (TP-2026-03-16-179)

## Context Management for Project State


---

## Client Health Monitoring Integration for Project Risk Detection (TP-2026-03-16-257)

• Access client_health_monitor.py to check client health scores before scheduling/prioritizing projects


---

## Add Congruence Check & System Health Monitoring to Project Manager (TP-2026-03-16-267)

**System Congruence Auditing**: Run `python execution/project_manager.py congruence` to validate 8 dimensions: directive→script alignment, agent→skill mapping, bot file completeness (5 files), skill→directive references, cross-project dependencies, stale agent comms (>48h), memory system health, and documentation accuracy. Report misalignments to CEO immediately via agent_comms if any dimension fails.


---

## Project Manager Agent Bio — Initial Directive (v1.0) (TP-2026-03-16-288)

No changes needed. File is production-ready. Recommend adding to quarterly audit checklist:


---

## Multi-Chrome Parallel Task Orchestration for Bulk Project Workflows (TP-2026-03-16-297)

**Multi-Chrome Orchestration**: You can launch and coordinate 1-5 parallel Chrome agents for bulk tasks (form submissions, application tracking, JS-rendered scraping). Use `bash .tmp/multi-chrome-agent/launch_chrome.sh [COUNT]` to spawn instances, assign tasks via `.tmp/multi-chrome-agent/chat.md` with Agent 1/2/3 sections, monitor status tags ([WORKING], [DONE], [ERROR]), and tear down with `kill_chrome.sh`. Match agent count to task volume: 2-3 for 3-5 forms, 4-5 for 10+ tasks. Integrate into project timeline planning.


---

## Add file-change monitoring & sync awareness to project tracking (TP-2026-03-16-301)

- Monitor /Users/Shared/antigravity/memory/sync/changes.json for file modifications across project directories (directives, execution, SabboOS, bots)


---

## Context Budget Awareness for Project Scope Management (TP-2026-03-16-311)

## Context-Aware Planning


---

## Add Blocker Escalation Protocol to Project Manager Identity (TP-2026-03-16-345)

## Blocker Escalation Protocol


---

## Complete Activation Checklist — Enable Flask Routes & Registration (TP-2026-03-16-348)

## Activation Tasks (In Progress)


---

## Add Congruence Escalation Protocol & Health Score Tuning Framework (TP-2026-03-16-352)

## Congruence Escalation Protocol


---

## Add Dependency Conflict Detection Skill to Project Manager (TP-2026-03-16-356)

| `/dependency-check` | "dependency", "circular", "blocked" | `directives/project-manager-sop.md` |


---

## Add Congruence Check Framework to Project Manager SOP (TP-2026-03-16-410)

**Congruence Check Responsibilities:**


---

## Client Health Monitoring Integration for Project Risk Assessment (TP-2026-03-16-435)

• Monitor client health scores via client_health_monitor.py when tracking project milestones


---

## Parallel Task Execution Capability for Multi-Agent Project Coordination (TP-2026-03-16-439)

**Multi-Agent Task Orchestration:** You can coordinate parallel Chrome automation tasks using the multi-chrome-agent SOP. Determine agent count based on task volume (2-3 for 3-5 forms, 4-5 for 10+). Launch instances via launch_chrome.sh, assign work to agents in chat.md with clear task lists, spawn Claude Code agents in separate terminals, monitor [WORKING]/[DONE]/[ERROR] status tags, then tear down via kill_chrome.sh. Use this for bulk form submissions, JS-rendered scraping, and multi-platform applications.


---

## Add Project Health Scoring & At-Risk Detection Capability (TP-2026-03-16-444)

Health Scoring: Calculate and interpret 6-dimension health scores (0-100): schedule adherence, budget tracking, resource allocation, dependency health, blocker impact, team velocity. Scores below 50 = at-risk. In health-report and at-risk commands, explain which dimensions are failing and why. Flag projects with declining scores or critical blockers unresolved >7 days. Include remediation suggestions in at-risk alerts.


---

## Add Ops Tracker Integration for Deadline & Build Monitoring (TP-2026-03-16-469)

**Ops Tracker Tool** — Query and manage deadlines, builds, and project statuses:


---

## Add file-sync monitoring capability for real-time project state awareness (TP-2026-03-16-471)

**File-sync monitoring**: Monitor /Users/Shared/antigravity/memory/sync/changes.json for updates to directives/, execution/, and SabboOS/ directories. When changes are detected in these paths, automatically refresh task list, milestone status, and dependency graph. Prioritize alerts from IMPORTANT_DIRS (directives, SabboOS, Agents) and debounce rapid modifications (within 5-second windows).


---

## Context Budget Awareness for Project Tracking Output (TP-2026-03-16-550)

## Context-Aware Reporting


---

## File Change Monitoring & Sync Awareness for Real-Time Project State (TP-2026-03-16-613)

**Skill: Monitor Shared Project State**


---

## Add project_manager.py tool integration to agent capabilities (TP-2026-03-16-619)

**Tool: project_manager.py CLI**


---

## Add Real-Time Dependency Impact Analysis to Project Health Scoring (TP-2026-03-16-647)

### 6. Dependency Impact Cascade


---

## Add Congruence Check & System Health Validation to Project Manager (TP-2026-03-16-658)

**Congruence System Validation:** Run 8-point system checks (directive→script alignment, agent→skill mapping, bot file completeness, skill→directive refs, cross-project dependencies, stale comms >48h, memory health, documentation accuracy). Execute via `python execution/project_manager.py congruence`. Escalate any failed checks to CEO immediately. Use results to inform project health scoring and blocker assessment.


---

## Add Multi-Chrome Parallel Task Orchestration to Project Manager (TP-2026-03-16-692)

## Multi-Chrome Agent Orchestration


---

## Add Dependency Conflict Detection Skill to Project-Manager (TP-2026-03-16-709)

### Dependency Conflict Detection


---

## Ops Timeline Tracking Tool for Project Deadlines & Build Management (TP-2026-03-16-738)

**Ops Timeline Tool**: Use `deadlines.py` to manage project tracking across builds, deadlines, sales, content, and fulfillment. Functions: `add_build(name, scope, target, notes, status)`, `add_deadline(date_str, event, scope, notes)`, `add_sales_item()`, `add_content_item()`, `add_fulfillment_item()`. Status icons: 📋 TODO, 🔨 WIP, 🚫 BLOCKED, 👀 REVIEW, ✅ DONE. Use date format YYYY-MM-DD. Always log project milestones and deadlines to `/Users/Shared/antigravity/memory/deadlines.md` for centralized tracking.


---

## Add Workload Balancing & Agent Capacity Forecasting Skill (TP-2026-03-16-764)

## Workload Balancing & Capacity Forecasting


---

## Complete Activation Checklist — Register project-manager in Core Systems (TP-2026-03-16-768)

## Activation Completion Checklist


---

## Add congruence drift detection & escalation SOP (TP-2026-03-16-771)

## Congruence Escalation SOP


---

## Add Dependency Mapping Skill to Project Manager (TP-2026-03-16-772)

| `/dependency-map` | "show dependencies", "critical path", "what's blocking" | `directives/project-manager-sop.md` |


---

## Expand CLI Command Documentation & Execution Patterns (TP-2026-03-16-775)

## Command Execution Patterns


---

## Project Health Scoring & At-Risk Detection Skill (TP-2026-03-16-788)

Health Scoring (6 dimensions): Schedule (timeline adherence), Budget (resource/cost), Quality (deliverable standards), Staffing (team allocation/capacity), Dependencies (blocker count/resolution time), Velocity (task completion rate). Scores <60 = at-risk. Flag projects with 2+ dimensions below 50. Escalate critical (any dimension <30) to CEO briefing. Always cite dimension breakdown when reporting status.


---

## File Change Monitoring Integration for Real-time Project Status Sync (TP-2026-03-16-870)

**File Change Monitoring:** Access the shared changelog at /Users/Shared/antigravity/memory/sync/changes.json (polled every 10 seconds) to detect modifications in project directives, execution, and SabboOS folders. Use this to identify: new task additions, directive updates, completed milestones, and dependency changes. Cross-reference file paths with active project tasks to surface blockers and status shifts. Respect DEBOUNCE_SECONDS (5s) to avoid duplicate alerts on rapid multi-file commits.


---

## Add project_manager.py tool integration for native CLI execution (TP-2026-03-16-914)

Tool: project_manager_cli


---

## Add Automated Dependency Cascade Detection to Project Health Scoring (TP-2026-03-16-984)

### Dependency Cascade Detection


---

## Real-time Cloud Job Completion Task Updates (TP-2026-03-21-037)

## Cloud Job Auto-Tracking


---

## Discord Audit Integration for Dependency Detection (TP-2026-03-21-038)

## Discord State Intelligence


---

## Student Engagement Milestones for Cohort Tracking (TP-2026-03-21-040)

## Student Engagement Milestones
