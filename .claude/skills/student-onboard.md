---
name: student-onboard
description: Generate personalized 90-day onboarding documents for Amazon FBA coaching students
trigger: when user says "onboard", "onboarding", "new student", "generate onboarding", "kickoff doc"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Student Onboarding

## Directive
Read `directives/student-onboarding-sop.md` for the full SOP before proceeding.

## Goal
When Sabbo pastes a student's Typeform application responses, generate a personalized 90-day onboarding document. Output gets shared as a Google Doc before the kickoff call.

## Inputs (from Typeform application)
| Field | Required | Example |
|---|---|---|
| First name | Yes | Marcus |
| Currently selling on Amazon? | Yes | No |
| Age | Yes | 28 |
| Biggest problem | Yes | "I want to quit my 9-5" |
| Investment budget | Yes | $5k+ |
| Email | No | marcus@email.com |
| Phone | No | +15551234567 |
| Credit score | No | 720 |
| Enrollment date | No | defaults to today |

User will paste Typeform data as text. Parse the fields from their message.

## Tier Classification (deterministic)
- Currently selling = Yes → **Tier B** (existing seller, needs systems)
- Budget $3K+ AND (age >= 35 OR mentions invest/asset/portfolio) → **Tier C** (investor)
- Budget $3K+ → **Tier A** (beginner with capital)
- Budget $2K-3K → **Tier A** (budget-tight flag)
- Budget <$2K → **DISQUALIFY** (generate "Getting Ready" doc instead)

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/upload_onboarding_gdoc.py \
  --name "{name}" \
  --tier "{tier}" \
  --budget "{budget}" \
  --problem "{problem}" \
  --email "{email}"
```

## Output
- Personalized 90-day roadmap as Google Doc
- Shared with student via email
- 9 sections covering enrollment through consistent $10K+ months

## Self-Annealing
If execution fails:
1. Check Google OAuth credentials (`credentials.json`, `token.json`)
2. Check `service_account.json` for Drive access
3. If Typeform data is incomplete, generate with available fields
4. Fix the script, update directive Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
