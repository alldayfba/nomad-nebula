---
description: Monitor student health, detect churn risk, run engagement reports
command: student-health
triggers:
  - student health
  - at-risk students
  - churn risk
  - engagement report
  - leaderboard
  - cohort health
  - who's struggling
  - graduation check
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Student Health Skill

## What This Does

Runs the Student Health Monitor to check student engagement, detect churn risk, and generate reports.

## Directive

Read `directives/csm-sop.md` for the full operating procedure.

## Execution

Based on the user's request, run the appropriate command:

```bash
# Full daily scan (health scores + at-risk + auto-DM queue)
python execution/student_health_monitor.py daily-scan

# Formatted health report
python execution/student_health_monitor.py health-report

# Specific student detail
python execution/student_health_monitor.py student-detail --name "[name]"

# At-risk students sorted by severity
python execution/student_health_monitor.py at-risk

# Log engagement signal
python execution/student_health_monitor.py log-signal --student "[name]" --type [signal] --channel [channel]

# Weekly leaderboard
python execution/student_health_monitor.py leaderboard

# Daily digest for CEO brain
python execution/student_health_monitor.py engagement-digest

# Students approaching graduation
python execution/student_health_monitor.py graduation-check
```

## Output

Present results in a clear format. For at-risk students, include recommended interventions. For leaderboard, format for Discord posting.
