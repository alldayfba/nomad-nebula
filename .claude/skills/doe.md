---
name: doe
description: Apply the Directive-Orchestration-Execution framework to any task
trigger: when user says "run workflow", "doe", "check directives", "follow the SOP"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# DOE Workflow

## Goal
Route any task through the 3-layer architecture: read the directive, call the execution script, handle errors.

## Rules
1. Check `directives/` first — does an SOP already exist for this task?
2. SOPs go in `directives/<name>-sop.md` — markdown, human-readable
3. Scripts go in `execution/<verb>_<noun>.py` — deterministic, no LLM calls inside
4. Route decisions through `AGENTS.md`
5. On failure: fix the script AND update the SOP's "Known Issues" section

## DOE Map
- Lead gen → `directives/lead-gen-sop.md` → `execution/run_scraper.py`
- Cold email → `directives/email-generation-sop.md` → `execution/generate_emails.py`
- Business audit → `directives/business-audit-sop.md` → `execution/generate_business_audit.py`
- Dream 100 → `directives/dream100-sop.md` → `execution/run_dream100.py`
- Sourcing → `directives/amazon-sourcing-sop.md` → `execution/source.py`
- Morning brief → `directives/morning-briefing-sop.md` → `execution/send_morning_briefing.py`
- Client health → `directives/client-health-sop.md` → `execution/client_health_monitor.py`
- Pipeline analytics → `directives/pipeline-analytics-sop.md` → `execution/pipeline_analytics.py`
- Outreach sequences → `directives/outreach-sequencer-sop.md` → `execution/outreach_sequencer.py`
- Content engine → `directives/content-engine-sop.md` → `execution/content_engine.py`
- Student onboarding → `directives/student-onboarding-sop.md` → `execution/upload_onboarding_gdoc.py`
- Competitor intel → `directives/ads-competitor-research-sop.md` → `execution/scrape_competitor_ads.py`

## Self-Annealing
If any step fails:
1. Read the error
2. Fix the script in `execution/`
3. Update the directive's Known Issues section
4. Re-run
5. Log fix in `SabboOS/CHANGELOG.md`
