# AI Setter SDR SOP
> directives/setter-sdr-sop.md | Version 1.0

---

## Purpose

24/7 automated Instagram DM setter that discovers prospects, sends warm outbound to new followers/story viewers, qualifies leads through a 6-stage conversation flow, and auto-books calls on GHL. Owned by the setter bot.

---

## Trigger

- Daemon runs 24/7 as a launchd service
- `/blitz N` — manual one-off DM blast to N followers
- `/setter-morning` — daily SDR briefing (Cowork skill)
- `/setter-pipeline` — pipeline review (Cowork skill)

---

## Scripts

| Script | Purpose |
|--------|---------|
| `execution/setter/setter_daemon.py` | Main 24/7 orchestrator — runs all cycles |
| `execution/setter/setter_brain.py` | Claude API integration — generates responses |
| `execution/setter/ig_browser.py` | Playwright browser automation — reads/sends DMs |
| `execution/setter/ig_conversation.py` | Conversation state machine — stage transitions, GHL, booking |
| `execution/setter/ig_prospector.py` | Follower/hashtag/comment/story scanning |
| `execution/setter/setter_db.py` | SQLite schema + CRUD |
| `execution/setter/setter_config.py` | All tunable constants (rate limits, scripts, safety) |
| `execution/setter/lead_grader.py` | Auto-grading engine (A-F, hot/warm/cold/dead) |
| `execution/setter/followup_engine.py` | Day 1/3/7/14 follow-up scheduler + executor |
| `execution/setter/show_rate_nurture.py` | Pre-call touchpoints (5min/1hr/24hr pings) |
| `execution/setter/pattern_learner.py` | Winning pattern tracking + A/B test results |
| `execution/setter/sales_auditor.py` | Conversation quality scoring |
| `execution/setter/setter_metrics.py` | Daily aggregation |
| `execution/setter/setter_dashboard.py` | Web UI (read-only, `/setter/dashboard`) |
| `execution/setter/manychat_bridge.py` | ManyChat webhook handler (legacy) |
| `execution/setter/follower_blitz.py` | One-off manual DM blast |

**DB:** `.tmp/setter/setter.db`
**Log:** `.tmp/setter/setter.log`
**Config:** `bots/setter/` (identity, skills, tools, memory, heartbeat)

---

## Architecture

```
Prospect discovered (follower/story/hashtag/comment)
    ↓
ICP scored (Haiku, 1-10) → if ≥6, mark for outbound
    ↓
Opener sent (Sabbo's exact script, A/B rotated)
    ↓
Inbox monitored (every 2 min during business hours)
    ↓
Conversation state machine:
    new → opener_sent → replied → qualifying → qualified → booking → booked → show/no_show
    ↓
GHL contact created at qualification
GHL appointment auto-booked when prospect provides email + phone
    ↓
Discord alert fires on every booking
```

---

## Daily Operations

| Time | Action | Type |
|------|--------|------|
| 6:00 AM | Night mode ends, daemon resumes full operations | Auto |
| 8:00 AM | `/setter-morning` Cowork skill (overnight results + action items) | Scheduled |
| 9:00 AM | Warm outbound batch — 400 DMs to new followers | Auto |
| 12:00 PM | Midday pipeline check | Scheduled |
| 2:00 PM | Warm batch — 300 DMs to story viewers + engagers | Auto |
| 5:00 PM | End-of-day pipeline review | Scheduled |
| 10:00 PM | Daily summary via Discord | Auto |
| 12:00 AM | Night mode — inbox monitoring only, no outbound | Auto |

---

## Rate Limits

| Channel | Daily Max | Cooldown |
|---------|-----------|----------|
| Warm outbound (new followers) | 400 | 30-90s randomized |
| Story viewers + engagers | 300 | 30-90s randomized |
| Follow-ups (existing leads) | 200 | 30-90s randomized |
| **Total** | **1,000** | — |
| Profile views | 500/day, 100/hour | — |

**Batch spread:** Each batch spreads over 2 hours (not all at once).
**Night mode:** 12 AM–6 AM = inbox monitoring only, no outbound sends.

---

## Conversation Flow

### 6-Stage Script (Sabbo's exact words)

| Stage | Script | Purpose |
|-------|--------|---------|
| 1. Opener | A/B rotated from 5 variants (see `setter_config.py`) | Open conversation |
| 2. Qualify Interest | "gotcha, u ever tried online biz before?" | Confirm commitment |
| 3. Resources Check | "how much would you say you have to invest..." | Confirm resources + credit |
| 4. Trigger | "is that also the reason why you followed?" | Amplify need |
| 5. Close | "1on1 guidance or trial and error on your own?" | Binary close |
| 6. Booking | GHL calendar link OR auto-detect email + phone | Lock in call |

### Qualification Criteria (all 3 required before close)

1. **Commitment** — Interested in online business / Amazon
2. **Urgency** — Wants to start ASAP, this month, or soon
3. **Resources** — Has $5K-$20K capital + credit access

### Stage Transitions

- **replied → qualifying:** Prospect sends first reply
- **qualifying → qualified:** All 3 qualifiers confirmed
- **qualified → booking:** Close question asked
- **booking → booked:** Email + phone detected in messages OR prospect books via link
- **booked → show/no_show:** Post-call update

### Follow-Up Cadence

| Step | Delay | Type |
|------|-------|------|
| 0 | 5 hours | "still with me?" |
| 1 | 1 day | Text bump |
| 2 | 3 days | Voice memo style |
| 3 | 7 days | Value share (reel/resource) |
| 4 | 14 days | Final touch |

Follow-ups fire for conversations in stages: `opener_sent`, `replied`, `qualifying`, `nurture`.
Cancelled immediately when prospect replies.

---

## GHL Integration

| Event | GHL Action |
|-------|-----------|
| Prospect qualifies | Create/update contact with tags `[ig-ai-setter, amazon-os]` |
| Booking detected (email + phone) | Create opportunity in pipeline, auto-book calendar appointment |
| Auto-book succeeds | Appointment created, confirmation DM sent |
| Auto-book fails | Discord alert: "book manually in GHL" |

**Calendar IDs:** Set in `.env` as `GHL_CALENDAR_ID_AMAZON` and `GHL_CALENDAR_ID_AGENCY`.
**Buffer:** Minimum 2 hours from now before booking a slot.
**Duration:** 30 minutes per call.

---

## Warm vs Cold Outbound (IMPORTANT)

- **Warm outbound (safe):** DMing people who followed YOUR account. They opted in. This is our primary channel — 400/day.
- **Story viewers (safe):** They're watching your content. Warm signal.
- **Hashtag discovery (semi-warm):** They're posting about the topic but haven't interacted with you.
- **Competitor follower scanning (cold — higher risk):** DMing people who never interacted with your account. Start at 20/day max, monitor for action blocks. Tag as `source: competitor_scan` for separate tracking.

Priority: Follower outreach > Story viewers > Hashtag > Competitor scanning.

---

## Safety Guardrails

### Prompt Injection Detection
24+ patterns blocked (see `SAFETY["injection_patterns"]` in config). If detected: escalate to human, DO NOT execute.

### Escalation Keywords
Auto-flag for human takeover: lawsuit, sue, attorney, refund, scam, report, fraud, harassment, stop messaging, unsubscribe, block, spam.

### Hard Restrictions (NEVER)
- Post content, change profile, follow/unfollow, like/comment
- Send links other than booking calendar
- Send images/videos/voice notes autonomously
- Mention students/clients by name
- Share revenue, pricing, financial data, refund policies
- Make guarantees or agree to discounts

### Sensitive Data Filtering
Regex checks block: phone numbers (Sabbo's), internal emails, API keys, credentials, large dollar amounts.

### Message Limits
- Max DM length: 300 characters
- Max consecutive unanswered: 3 (then auto-pause)
- Max messages before flag: 15 (conversation review)
- Approval gate: First 20 conversations require human approval

### Action Block Detection
If Instagram action block detected: auto-pause for 24 hours, Discord alert fires.
Kill switch: create `.tmp/setter/PAUSED` file to stop all sending.

---

## Model Routing

| Task | Model | Why |
|------|-------|-----|
| ICP scoring | Haiku | Fast, cheap, classification task |
| Openers | Haiku | Template-based, minimal generation |
| Qualification | Sonnet | Needs nuance, multi-turn context |
| Objection handling | Sonnet | Needs persuasion + empathy |
| Escalation decisions | Sonnet | Safety-critical |
| Pattern analysis | Haiku | Batch processing |

All LLM calls use Claude CLI (Max plan — zero API cost).

---

## Monitoring

| Channel | Frequency | What |
|---------|-----------|------|
| Discord (setter webhook) | Real-time | Bookings, escalations, action blocks |
| Discord (daily summary) | 10 PM | DMs sent, reply rate, bookings, cost |
| Sales audit | Every 4 hours | Conversation quality scores (1-10 per stage) |
| Pattern learning | Every 6 hours | Update winning patterns table |
| Dashboard | Always-on | `/setter/dashboard` (read-only, password-protected) |

---

## Lead Grading

| Grade | Temperature | Criteria |
|-------|-------------|----------|
| A | Hot | All 3 qualifiers confirmed, high engagement, buying signals |
| B | Warm | 2/3 qualifiers, good engagement |
| C | Lukewarm | Some interest, missing signals |
| D | Cold | Low engagement, weak signals |
| F | Dead | No response after full follow-up sequence |

Grades auto-update after every message exchange via `lead_grader.py`.

---

## Self-Anneal Triggers

- **Action block:** Pause 24h → review rate limits → reduce batch if needed → update this directive
- **Low reply rate (<8%):** Review openers → update A/B variants → test → update this directive
- **Low booking rate:** Review qualification flow → check if close is too early/late → adjust stages
- **Prompt injection detected:** Review injection patterns list → add new patterns → update config
- **GHL integration failure:** Check API key → verify endpoint → fix → update this directive

---

## Learned Rules

1. Follow-ups must fire for `replied` and `qualifying` stages, not just `opener_sent` and `nurture` — mid-funnel stalls are the biggest drop-off.
2. New follower DMs are warm outbound (they opted in), not cold. Competitor scanning is cold. Different risk levels.
3. A/B test openers — single opener means zero learning. Rotate 5 variants, track via `pattern_learner.py`.
