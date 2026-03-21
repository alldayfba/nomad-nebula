# Customer Success Manager — SOP
> directives/csm-sop.md | Version 1.0

---

## Purpose

Operate the student success system for Amazon OS coaching. Monitor all active students, detect and prevent churn, accelerate milestone progression, capture testimonials, manage referrals, and drive upsell conversion.

## Inputs

- Student health data from `execution/student_health_monitor.py`
- Discord activity from `execution/discord_bot/csm_cog.py`
- Milestone data from `execution/student_tracker.py`
- Check-in data (weekly calls, DM checks, assignment reviews)

## Tools

| Tool | Script | Purpose |
|---|---|---|
| Student Health Monitor | `execution/student_health_monitor.py` | Health scoring, at-risk detection, engagement tracking |
| Student Tracker | `execution/student_tracker.py` | Milestone management, student records |
| Discord CSM Cog | `execution/discord_bot/csm_cog.py` | Discord automation |
| Coaching Cadence | `execution/coaching_cadence.py` | Call scheduling, accountability |
| Testimonial Engine | `execution/testimonial_engine.py` | Testimonial + referral management |
| Graduation Flow | `execution/graduation_flow.py` | Day 75-90 upsell sequence |

## Daily Operating Procedure

### 1. Morning Scan (7:00 AM)

```bash
python execution/student_health_monitor.py daily-scan
```

Review output:
- CRITICAL students -> immediately flag for Sabbo
- RED students -> queue personal outreach from Sabbo
- ORANGE students -> queue CSM bot DM with specific help
- YELLOW students -> queue friendly check-in DM

### 2. Pre-Call Prep (8:00 AM, Tue + Thu)

On group call days:
- Pull recent Discord questions from student channels
- Generate call agenda with student-specific topics
- Post agenda in group chat 30 minutes before call

### 3. Continuous Monitoring (9:00 AM - 5:00 PM)

- Monitor Discord for student activity (csm_cog handles this automatically)
- Respond to /checkin, /win, /stuck commands
- Track assignment submissions
- Send celebration messages for milestone completions

### 4. Evening Wrap (5:00 PM)

```bash
python execution/student_health_monitor.py engagement-digest
```

- Update CEO brain with daily student health summary
- Queue next-day outreach list
- Log any interventions and outcomes in `bots/csm/memory.md`

### 5. Weekly Review (Friday)

```bash
python execution/student_health_monitor.py health-report
python execution/student_health_monitor.py leaderboard
```

- Post leaderboard to Discord
- Send weekly accountability DMs to all active students
- Review churn events -> update root cause analysis in memory.md
- Check graduation pipeline -> start Day 75 flows for approaching students

## Intervention Rules

### Escalation Thresholds
- YELLOW (60-79): CSM bot handles autonomously
- ORANGE (40-59): CSM bot handles + Sabbo gets daily digest
- RED (20-39): Sabbo must personally intervene within 48 hours
- CRITICAL (0-19): Sabbo must personally intervene within 24 hours

### What Triggers an Intervention
- Discord silence > 3 days
- Missed 2+ consecutive group calls
- Mood declining across 3 check-ins
- No assignment submissions for 2 weeks
- Payment failure
- Student explicitly says they want to quit

### What NOT to Do
- Don't send more than 2 automated DMs per week to any single student
- Don't mention other students' health scores or progress (unless celebrating publicly)
- Don't promise outcomes ("you WILL hit $10K") — promise support ("we'll work together until you do")
- Don't automate RED/CRITICAL interventions — those need a human voice

## Outputs

- Daily: Engagement digest (JSON) -> CEO brain
- Daily: At-risk student list -> Sabbo (if any RED/CRITICAL)
- Weekly: Cohort health report -> CEO Command Center
- Weekly: Leaderboard -> Discord
- On milestone: Celebration message -> Discord group
- Day 75: Graduation flow initiated
- On request: Testimonial capture messages
- On request: Referral code generation

## Self-Annealing

Track which interventions work:
1. Log every intervention in touchpoints table (student, type, message, outcome)
2. After 30 days, analyze: which messages got responses? Which saved students?
3. Update message templates based on data
4. Update this SOP with findings

## Edge Cases

- **Student re-enrolls after churning:** Reset health score to 70 (not 100), flag as "returning" in notes
- **Student in payment plan misses payment:** Log payment_failed signal, but don't remove access for 7 days (grace period)
- **Student hits 10K before Day 90:** Immediate celebration + early Mastermind flag + testimonial request
- **Multiple students CRITICAL simultaneously:** Prioritize by revenue at risk (enrollment_revenue), then by days since last contact

---

*CSM SOP v1.0 — 2026-03-16*
