# AllDayFBA — EOD Sales Tracking System
## Setup Guide + Google Sheets Template

**Date:** February 24, 2026
**Purpose:** Get your sales team filling out daily reports so you can make data-driven decisions

---

## WHY THIS MATTERS

Ben said it directly: you can't optimize what you can't measure. Right now you're guessing. With tracking, you'll know:
- Exactly how many calls you're getting (and from where)
- Your true show rate, close rate, and cash collected rate
- Where the REAL bottleneck is (traffic? show rate? close rate? cash?)
- Whether changes you make are actually working

---

## GOOGLE SHEETS TEMPLATE

### Sheet 1: "Daily Sales Report"

Create these columns:

| Column | Description | Example |
|---|---|---|
| A: Date | Auto-fill | 2026-02-24 |
| B: Rep Name | Setter or Closer name | Marcus |
| C: Role | Setter / Closer | Closer |
| D: Calls Booked | Total calls on calendar that day | 5 |
| E: Calls Taken | Calls that actually happened (showed up) | 3 |
| F: No-Shows | Calls booked but didn't show | 2 |
| G: Deals Closed | Number of closes | 1 |
| H: Revenue Closed | Total $ closed | $5,000 |
| I: Cash Collected | Actual cash received (not financed) | $3,000 |
| J: Financed Amount | Amount through FanBase or payment plan | $2,000 |
| K: Lead Source | Where the lead came from | Instagram DM |
| L: Notes | Anything notable | "Lead was super qualified, watched all YT videos" |

### Sheet 2: "Weekly Dashboard" (Auto-Calculated)

| Metric | Formula | Target |
|---|---|---|
| Total Calls Booked | SUM of column D for week | 15-20+ |
| Total Calls Taken | SUM of column E | 10-15+ |
| Show Rate | Calls Taken / Calls Booked | 70%+ |
| Total Deals Closed | SUM of column G | 4-6+ |
| Close Rate | Deals Closed / Calls Taken | 30-40% |
| Total Revenue | SUM of column H | $20K+ |
| Total Cash Collected | SUM of column I | $15K+ |
| Cash Collection Rate | Cash Collected / Revenue | 60%+ |
| Average Deal Size | Revenue / Deals Closed | $4-5K |
| Top Lead Source | MODE of column K | Track this |

### Sheet 3: "Monthly Trends"
Same metrics as weekly, rolled up monthly. Add month-over-month comparison.

---

## EOD FORM (Google Form → Zapier → Sheet)

### Setup Steps:
1. Create a Google Form with these fields:
   - Date (auto)
   - Your Name (dropdown: list all reps)
   - Role (dropdown: Setter / Closer)
   - Calls Booked Today (number)
   - Calls Taken Today (number)
   - No-Shows (number)
   - Deals Closed (number)
   - Revenue Closed (dollar amount)
   - Cash Collected (dollar amount)
   - Financed Amount (dollar amount)
   - Lead Sources (checkboxes: Instagram DM, YouTube, TikTok, Referral, Paid Ad, Website, Other)
   - Notes (text)

2. Link form responses to the Google Sheet (Forms → Responses → Link to Sheets)

3. Set up Zapier automation:
   - Trigger: New Google Form response
   - Action: Send summary to your Slack/Discord/group chat
   - Optional: Send daily digest email to you at 8 PM

---

## ACCOUNTABILITY RULES

### Non-Negotiable:
- Every rep fills out the EOD form **every single day they work**
- No exceptions. If they took calls, they fill out the form.
- If the form isn't filled out by 8 PM, they get a message.
- If it happens 3 times in a week, there's a conversation.

### Weekly Review (Every Monday):
- Pull up the weekly dashboard
- Look at: show rate, close rate, cash collected, lead sources
- Ask: "What's the #1 bottleneck this week?"
  - If show rate is low → fix booking/confirmation process
  - If close rate is low → review call recordings, coach closers
  - If traffic is low → content isn't working, test new angles
  - If cash collection is low → review financing options, payment plan structure

### Monthly Review (First Monday of each month):
- Compare month-over-month trends
- Set targets for next month based on data
- Celebrate wins with the team

---

## QUICK WIN: SIMPLE VERSION

If the full setup feels like too much right now, start with THIS:

**Daily text message from each rep at end of day:**
```
EOD Report — [Date]
Calls booked: X
Calls taken: X
Closes: X
Revenue: $X
Cash: $X
```

Even this is 100x better than nothing. Upgrade to the form/sheet later.
