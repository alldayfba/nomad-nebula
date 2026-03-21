# CSM Bot — Skills
> bots/csm/skills.md | Version 1.0

---

## Health Monitoring

### Daily Scan
**Trigger:** "student health", "daily scan", "morning scan"
**Script:** `python execution/student_health_monitor.py daily-scan`
**Output:** Full cohort health scores, at-risk list, auto-DM queue, CEO digest

### Health Report
**Trigger:** "cohort report", "cohort health", "health report"
**Script:** `python execution/student_health_monitor.py health-report`
**Output:** Formatted table of all students with scores and risk levels

### Student Detail
**Trigger:** "student [name]", "how is [name] doing"
**Script:** `python execution/student_health_monitor.py student-detail --name "[name]"`
**Output:** Full health breakdown, recent signals, milestone timeline, check-in history

### At-Risk Students
**Trigger:** "at-risk", "churn risk", "who's struggling"
**Script:** `python execution/student_health_monitor.py at-risk`
**Output:** At-risk students sorted by severity with recommended interventions

---

## Engagement Tracking

### Log Signal
**Trigger:** When engagement data is reported
**Script:** `python execution/student_health_monitor.py log-signal --student "[name]" --type [signal_type] --channel [channel]`
**Valid types:** discord_message, discord_question, call_attended, call_missed, assignment_submitted, assignment_missing, mood_positive, mood_frustrated, payment_on_time, payment_late, screenshot_shared, etc.

### Engagement Digest
**Trigger:** "engagement report", "daily digest"
**Script:** `python execution/student_health_monitor.py engagement-digest`
**Output:** JSON summary for CEO brain

---

## Community & Celebration

### Leaderboard
**Trigger:** "leaderboard", "top students"
**Script:** `python execution/student_health_monitor.py leaderboard`
**Output:** Top students by milestone progress + engagement score (for Discord posting)

### Milestone Celebration
**Trigger:** "celebrate [name]", student hits milestone
**Action:** Generate celebration message using templates from CSM.md

---

## Graduation & Upsell

### Graduation Check
**Trigger:** "graduation check", "who's graduating"
**Script:** `python execution/student_health_monitor.py graduation-check`
**Output:** Students approaching Day 75-90 with recommended actions

### Continuation Offer
**Trigger:** "graduation prep [name]"
**Action:** Start Day 75-90 graduation flow per CSM.md Graduation Flow section

---

## Churn Prevention

### Win-Back Sequence
**Trigger:** "win-back [name]"
**Action:** Start 5-touch win-back sequence per CSM.md Win-Back Sequence section

### Exit Interview
**Trigger:** "exit interview [name]"
**Action:** Log churn event with reason category + detail

---

## Testimonial & Referral

### Request Testimonial
**Trigger:** "testimonial request [name]"
**Action:** Generate testimonial capture message based on student's milestone

### Generate Referral Code
**Trigger:** "referral code [name]"
**Action:** Generate unique REF-[FIRSTNAME]-[4DIGITS] code + register in DB
