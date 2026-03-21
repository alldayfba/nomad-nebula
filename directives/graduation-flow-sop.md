# Graduation Flow — SOP
> directives/graduation-flow-sop.md | Version 1.0

---

## Purpose

Manage the Day 75-90 graduation sequence. Present the Continuation offer ($597/mo Inner Circle), handle conversions, and celebrate graduates. Also covers the full onboarding automation for new students.

## Tools

| Tool | Script | Purpose |
|---|---|---|
| Graduation Flow | `execution/graduation_flow.py` | Day 75-90 sequence, upsell, backend tracking |
| Student Onboarding | `execution/student_onboarding.py` | Auto-create channel, assign role, welcome message |
| Student Health Monitor | `execution/student_health_monitor.py` | Graduation check |

## Onboarding Flow (New Student Pays)

When a new student pays, run:
```bash
python execution/student_onboarding.py onboard --name "John Smith" --discord-id 123456789 --tier A --capital 10000
```

This automatically:
1. Creates a private `🎓┃john-smith` channel in the Inner Circle category
2. Assigns the `🎓24/7 Profits Student` role
3. Sends the welcome message with Week 1 checklist
4. Registers them in the student tracker DB
5. Creates enrolled (completed) + niche_selected (in_progress) milestones
6. Logs onboarding engagement signal

## Graduation Sequence (Day 75-90)

| Day | Touchpoint | Purpose |
|---|---|---|
| 75 | Review DM | "Let's review your progress — schedule a call" |
| 80 | Offer DM | Present Continuation ($597/mo) with full breakdown |
| 83 | FAQ DM | Answer common objections about continuing |
| 85 | Urgency DM | "5 days left — let's get you set up" |
| 87 | Final DM | "Continuing or graduating? Either way, proud of you" |
| 90 | Graduation | Public celebration in group chat OR seamless transition |

## Continuation Offer — Inner Circle ($597/mo)

What they get:
- Weekly group calls (permanent, not tapering)
- Monthly 1:1 with Sabbo (30 min)
- Private Discord channel stays open
- Lead Finder product sourcing access
- Monthly advanced masterclass
- Priority deal alerts
- Monthly P&L review

## Daily Execution

```bash
# Check graduation pipeline (run weekly, Mondays)
python execution/graduation_flow.py check

# Send next pending touchpoints
python execution/graduation_flow.py send-next

# Convert student to Continuation
python execution/graduation_flow.py convert --student "Mark" --offer retainer --revenue 597

# Graduate without upsell
python execution/graduation_flow.py graduate --student "Mark"

# Backend revenue report
python execution/graduation_flow.py backend-report
```

## Positioning Rules

1. Never hard-sell. Frame Continuation as the natural next step, not a desperate pitch.
2. Lead with their wins. "Look how far you've come — here's how to keep the momentum."
3. If student is frustrated or at-risk, skip the offer. Focus on saving the relationship first.
4. If student hasn't reached profitable_month, don't pitch. They need more results before paying more.
5. Always celebrate graduation publicly, even if they don't continue.

## Backend Revenue Tracking

All conversions logged in `backend_subscriptions` table:
- `retainer` — $597/mo Continuation
- `mastermind` — $2,500/mo Operators Circle
- `ppc` — $397-697/mo PPC management
- `va_placement` — $497 + $197/mo VA service

---

*Graduation Flow SOP v1.0 — 2026-03-16*
