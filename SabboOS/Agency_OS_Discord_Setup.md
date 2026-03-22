# Agency OS -- Discord Server Setup

> **Server Name:** 247 Growth HQ
> **Purpose:** Central command for the sales floor. Every channel has a job. No bloat.
> **Scale:** 20-30 cold callers/setters + closers + leadership

---

## Roles (Top to Bottom Hierarchy)

| Priority | Role | Color | Who | Count |
|---|---|---|---|---|
| 1 | CEO | Purple | Sabbo | 1 |
| 2 | Sales Manager | Blue | Runs the floor | 1 |
| 3 | Team Lead | Green | Top performers leading pods of 5-7 | 3-4 |
| 4 | Closer | Yellow | Takes strategy calls, closes deals | 2-3 |
| 5 | Senior Setter | Orange | Proven setters (2+ weeks, hitting KPI) | 4-8 |
| 6 | Setter | White | Active setters in full production | 10-22 |
| 7 | Onboarding | Red | Brand new hires, pre-Milestone 1 | Variable |

---

## Channel Structure

```
START HERE
  #welcome-read-first
  #announcements
  #introduce-yourself

DAILY OPS
  #morning-standup
  #eod-reports
  #wins
  #pipeline-updates

DIAL FLOOR
  dial-block-1          (voice)
  dial-block-2          (voice)
  1-on-1-coaching       (voice)
  role-play-room        (voice)
  #call-notes

TRAINING
  #scripts-and-resources
  #objection-of-the-day
  #game-film
  #questions

TEAM
  #general
  #memes
  hangout               (voice)

LEADERSHIP              (locked)
  #leadership
  #rep-performance
  #closer-room
```

### Channel Descriptions

**START HERE**

| Channel | Purpose | Who Posts |
|---|---|---|
| #welcome-read-first | Rules, expectations, daily schedule, all onboarding links. Read-only for reps. | CEO, Manager |
| #announcements | Company updates, policy changes, big wins. Read-only for reps. | CEO, Manager |
| #introduce-yourself | New hires drop a short intro: name, location, background, why they're here. | Everyone |

**DAILY OPS**

| Channel | Purpose | Who Posts |
|---|---|---|
| #morning-standup | 11 AM meeting notes, daily focus, energy check. Manager recaps the plan. | Manager, Team Leads |
| #eod-reports | Everyone posts daily numbers using pinned template. No exceptions. | All reps |
| #wins | Closed deals, booked calls, breakthroughs. Celebrate here. | Everyone |
| #pipeline-updates | Bookings, show rates, follow-up status, calendar fill rate. | Manager, Closers, Leads |

**DIAL FLOOR**

| Channel | Type | Purpose | Schedule |
|---|---|---|---|
| dial-block-1 | Voice | Live dialing with manager present | 12:00 - 2:30 PM EST |
| dial-block-2 | Voice | Second dial block | 4:00 - 6:00 PM EST |
| 1-on-1-coaching | Voice | Private coaching between manager and individual rep | As needed |
| role-play-room | Voice | Script practice, objection drills, onboarding tryouts | Training blocks |
| #call-notes | Text | Notable call summaries, interesting objections, learnings | After calls |

**TRAINING**

| Channel | Purpose | Who Posts |
|---|---|---|
| #scripts-and-resources | Pinned: cold call script, objection cards, flowchart links, pitch deck | Manager (pins), Senior Setters |
| #objection-of-the-day | Manager posts one objection each morning, team practices responses | Manager |
| #game-film | Call recordings for team review (Fathom links) | Manager, anyone sharing calls |
| #questions | Ask anything about scripts, process, CRM, tools | Everyone |

**TEAM**

| Channel | Purpose |
|---|---|
| #general | Water cooler, casual chat, non-work banter |
| #memes | Keep morale high. Sales is energy. |
| hangout (voice) | Optional voice chat for breaks, hanging out between blocks |

**LEADERSHIP** (Locked -- CEO + Manager + Team Leads only)

| Channel | Purpose | Who Sees |
|---|---|---|
| #leadership | Strategy, hiring decisions, team performance, scaling plans | CEO, Manager, Team Leads |
| #rep-performance | Individual rep tracking, PIPs, promotions, terminations | CEO, Manager only |
| #closer-room | Closer-specific strategy, deal reviews, close rate optimization | CEO, Manager, Closers |

---

## Permissions Matrix

| Role | START HERE | DAILY OPS | DIAL FLOOR | TRAINING | TEAM | LEADERSHIP |
|---|---|---|---|---|---|---|
| Onboarding | Read | NO | Voice only | Read | #general, #memes | NO |
| Setter | Read | Full | Full | Read | Full | NO |
| Senior Setter | Read | Full | Full | Read + Pin | Full | NO |
| Closer | Read | Full | Full | Read | Full | #closer-room only |
| Team Lead | Read | Full | Full | Full | Full | #leadership only |
| Sales Manager | Full | Full | Full | Full | Full | Full |
| CEO | Full (Admin) | Full | Full | Full | Full | Full |

**Key permission rules:**
- @Onboarding CANNOT see DAILY OPS channels until promoted to @Setter (Milestone 1 passed)
- @Onboarding CAN join voice channels (role-play-room, dial blocks for observation)
- #announcements and #welcome-read-first are read-only for everyone except CEO and Manager
- @Senior Setter can pin messages in TRAINING channels
- @Closer gets #closer-room but NOT #leadership or #rep-performance
- @Team Lead gets #leadership but NOT #rep-performance (that stays CEO + Manager)

---

## Bots

### 1. EOD Reminder Bot
- **Trigger:** 6:15 PM EST daily (Mon-Fri)
- **Action:** Posts in #eod-reports: "EOD reports due. If you haven't posted yet, do it now. Template is pinned."
- **Logic:** Tag anyone with @Setter, @Senior Setter, @Team Lead, or @Closer who hasn't posted in #eod-reports today
- **Implementation:** Discord bot or scheduled webhook

### 2. Wins Bot
- **Trigger:** Any message posted in #wins
- **Action:** Auto-react with fire emoji. Track weekly totals per person.
- **Weekly:** Post leaderboard in #wins every Friday at 5 PM: "This week's top performers: 1. [Name] - X wins..."
- **Implementation:** Custom bot or MEE6

### 3. Fathom Integration
- **Channel:** #game-film
- **Action:** Auto-post call recordings with summary when shared via Fathom webhook
- **Implementation:** Fathom webhook -> Discord webhook URL for #game-film

### 4. Morning Standup Bot (Optional)
- **Trigger:** 10:45 AM EST daily
- **Action:** Posts in #morning-standup: "Standup in 15 minutes. Join dial-block-1 voice channel."

---

## Pinned Messages -- Day 1 Setup

### #welcome-read-first (9 Pins)

**Pin 1 -- Daily Schedule**
```
DAILY SCHEDULE (Mon-Fri, EST)

11:00 AM    Morning Standup (voice)
11:15 AM    Training Block 1 (objection drill)
12:00 PM    DIAL BLOCK 1 (voice, mandatory)
2:30 PM     Break
3:00 PM     Training Block 2 (role-play, pod practice)
4:00 PM     DIAL BLOCK 2 (voice, mandatory)
6:00 PM     Dials stop
6:15 PM     EOD Report due in #eod-reports
6:30 PM     EOD Review (voice, optional but encouraged)
7:00 PM     Day ends
```

**Pin 2 -- Flowcharts**
```
SALES FLOWCHARTS (bookmark these):
1. Closer Script Flowchart: [link]
2. Setter Script Flowchart: [link]
3. Meeting Flow: [link]
4. Onboarding Flow: [link]
5. Client Delivery Flow: [link]
```

**Pin 3 -- Cold Call Script**
```
COLD CALL SCRIPT: [Google Doc link]
Read it 5x. Black Marker Method. Memorize, don't read.
```

**Pin 4 -- Objection Battle Cards**
```
OBJECTION BATTLE CARDS: [Google Doc link]
Top 15 objections + exact rebuttals. Study daily.
```

**Pin 5 -- EOD Report Template**
```
EOD TEMPLATE -- Copy and fill:

Name:
Date:
Dials:
Connections:
Conversations (2min+):
Quality Convos (5min+):
Appointments Set:
Calls on Calendar:
Deals Closed:
Cash Collected:
What went well:
What I need help with:
```

**Pin 6 -- Voice Chat Rule**
```
VOICE CHAT IS NON-NEGOTIABLE DURING DIAL BLOCKS.

12:00-2:30 PM -- You are in dial-block-1 voice channel. Camera optional. Mic unmuted between calls.
4:00-6:00 PM -- You are in dial-block-2 voice channel. Same rules.

If you're not in voice, you're not working. Period.
```

**Pin 7 -- KPI Targets**
```
DAILY KPI TARGETS (50/50/50):

50 Cold Dials (new prospects)
50 Warm Follow-ups (existing pipeline)
50 Re-engagement (old leads, callbacks)

MINIMUM to stay on the team:
- 100+ total touches/day
- 3+ booked calls/week
- 70%+ show rate on your bookings
```

**Pin 8 -- Compensation Structure**
```
SETTER COMP:
- $2K-$3K/mo base (depending on experience)
- $25-$50 per qualified show
- $100-$200 per close from your booking
- Monthly bonuses for top performers

SENIOR SETTER: Base + $250/mo seniority bonus
TEAM LEAD: Base + $500/mo lead bonus + 1% pod override
CLOSER: $3K-$5K base + 8-12% commission + close rate bonus
```

**Pin 9 -- The Rules**
```
THE RULES:

1. Show up on time. Every day. No excuses.
2. Hit your numbers. 50/50/50 is the minimum.
3. Post EOD every day. Miss it twice, we talk. Miss it three times, you're out.
4. Be in voice chat during dial blocks. Non-negotiable.
5. No drama. No gossip. No excuses. Handle your business.
6. Ask questions in #questions, not in DMs to random people.
7. If you're struggling, say so. We coach, we don't punish effort.
8. If you're not putting in effort, we'll know. And we'll move on.
9. Celebrate wins. Your teammate's close is your booked call.
10. This is a performance-based team. The cream rises. So rise.
```

### #eod-reports (1 Pin)

```
EOD TEMPLATE -- Copy and fill every day before 6:30 PM:

Name:
Date:
Dials:
Connections:
Conversations (2min+):
Quality Convos (5min+):
Appointments Set:
Calls on Calendar:
Deals Closed:
Cash Collected:
What went well:
What I need help with:

No template = no report. No report = didn't work.
```

---

## Onboarding Flow in Discord

### Step 1: Join + Auto-Role
- New hire clicks invite link
- Auto-assigned @Onboarding role
- Only sees: START HERE + TRAINING + #general + #memes + voice channels
- Cannot see DAILY OPS or LEADERSHIP

### Step 2: Self-Study (Day 1-2)
- Read everything in #welcome-read-first (all 9 pins)
- Watch all training Loom videos linked in #scripts-and-resources
- Read cold call script 5x using Black Marker Method
- Post intro in #introduce-yourself

### Step 3: Role-Play Test (Day 3-4)
- Join role-play-room voice channel at scheduled time
- 10-min live role-play with Sales Manager or Team Lead
- Must deliver opener + hook naturally (not reading)
- Pass = promoted to @Setter
- Fail = one more attempt, then cut

### Step 4: Promotion to Setter
- @Onboarding role removed, @Setter role assigned
- DAILY OPS channels unlock
- First dial day: join dial-block-1 at 12 PM sharp
- Post first EOD report at 6:30 PM

### Step 5: First Week on Floor
- Full 50/50/50 cadence with live coaching
- Manager in voice channel providing real-time feedback
- Daily review of numbers and call quality
- End of Week 1: performance evaluation

---

## Server Settings Checklist

- [ ] Create server: "247 Growth HQ"
- [ ] Create all 7 roles with correct colors and hierarchy
- [ ] Create all 5 categories with channels
- [ ] Set permissions per the matrix above
- [ ] Pin all 9 messages in #welcome-read-first
- [ ] Pin EOD template in #eod-reports
- [ ] Set up EOD Reminder bot (6:15 PM webhook)
- [ ] Set up Wins Bot (auto-react in #wins)
- [ ] Configure Fathom webhook to #game-film
- [ ] Set server icon and banner
- [ ] Generate invite link (no expiry, limited uses for tracking)
- [ ] Test: create a test account with @Onboarding role, verify they only see correct channels
- [ ] Test: promote test account to @Setter, verify DAILY OPS unlocks
