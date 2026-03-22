# Agency OS -- Client Onboarding SOP
## From Close to 90-Day Retention: Step-by-Step Operations Manual
> Version 1.0 | Last Updated: 2026-03-21
> Owner: Sabbo Jean-Baptiste | 247 Growth
> Related: `Agency_OS.md` (Sections 4-5, 11), `directives/client-onboarding-pipeline.md`, `directives/brand-voice-extraction-sop.md`

---

## Table of Contents

1. Day of Close (Within 2 Hours)
2. Onboarding Questionnaire
3. Week 1 -- Kickoff + Discovery
4. Weeks 2-4 -- Infrastructure Install
5. Month 2-3 -- Operation + Optimization
6. Escalation Procedures
7. Client Workspace Template
8. Handoff Checklist (Closer to Operations)
9. Appendix: Templates + Quick Reference

---

## 1. DAY OF CLOSE (Within 2 Hours)

Everything in this section happens within 2 hours of verbal commitment. Speed signals professionalism and locks in momentum before buyer's remorse sets in.

### 1.1 Payment Collection

**Action:** Send Stripe payment link within 15 minutes of verbal close.

| Step | Detail |
|---|---|
| Generate Stripe link | Dashboard > Products > Select tier > Create payment link |
| Include in link | Client name, tier, monthly amount, 90-day minimum term |
| Send via | Email (primary) + SMS (backup if no response in 30 min) |
| Confirm receipt | Stripe webhook fires > Slack notification > manual verify |

**Payment terms:**
- First month charged immediately upon link completion
- Subsequent months: auto-charge on the same calendar date
- Failed payment: Stripe retries 3x over 7 days, then ops notified
- No work begins until first payment clears

**Tier pricing reference (from Agency_OS.md):**

| Tier | Monthly | Channels | Commitment |
|---|---|---|---|
| Starter | $5,000 | Single channel | 90 days |
| Growth | $10,000 | Multi-channel | 90 days |
| Enterprise | $25,000 | Full-stack | 90 days |

### 1.2 Contract Signing

**Action:** Send contract within 30 minutes of payment confirmation.

| Step | Detail |
|---|---|
| Template | `SabboOS/templates/Agency_OS_Proposal_Template.md` (convert to PDF) |
| Signing tool | DocuSign (preferred) or signed PDF via email |
| Contract includes | Scope of work, tier, monthly retainer, 90-day minimum, performance guarantee, cancellation terms, NDA |
| Turnaround target | Signed within 24 hours of send |
| Follow-up | If not signed within 12 hours, send a reminder. If not signed within 48 hours, call the client directly. |

**Performance guarantee language (from Pitch Deck Slide 12):**
> "If we don't hit the agreed KPI targets within 90 days, we will continue operating your growth system at no additional cost until we do."

### 1.3 Welcome Email

**Action:** Send within 1 hour of payment confirmation.

**Subject:** Welcome to 247 Growth -- Here's What Happens Next

**Template:**

```
Hi [FIRST NAME],

Welcome to 247 Growth. We're excited to build your growth engine.

Here's exactly what happens from here:

1. ONBOARDING QUESTIONNAIRE (linked below)
   Please complete this before our kickoff call. It takes about 15 minutes
   and gives us everything we need to hit the ground running.

   [QUESTIONNAIRE LINK]

2. KICKOFF CALL
   Use the link below to book your 90-minute kickoff call. Aim for
   this week if possible -- the sooner we kick off, the sooner your
   infrastructure is live.

   [CALENDLY/CAL.COM LINK]

3. SLACK CHANNEL
   You've been added to #client-[name] on Slack. This is your direct
   line to your growth operator for day-to-day communication, questions,
   and approvals.

   [SLACK INVITE LINK]

4. WHAT TO EXPECT
   - Week 1: Kickoff call + discovery + access provisioning
   - Weeks 2-4: Full infrastructure build (landing pages, email flows,
     ad accounts, tracking, CRM)
   - Month 2+: Campaigns live, weekly optimization, weekly strategy calls

Your growth operator is [OPERATOR NAME]. They'll be your primary
point of contact throughout the engagement.

If you have any questions before the kickoff call, drop them in
Slack or reply to this email.

Let's build.

Sabbo Jean-Baptiste
247 Growth
sabbo@247growth.org
```

### 1.4 Slack Channel Creation

**Action:** Create within 30 minutes of close.

| Step | Detail |
|---|---|
| Channel name | `#client-[lastname]` or `#client-[businessname]` (lowercase, hyphens) |
| Add members | Client, growth operator, Sabbo, media buyer (if assigned) |
| Pin welcome message | "Welcome to your 247 Growth channel. This is for day-to-day comms, approvals, and questions. Weekly reports and strategy docs will be pinned here." |
| Pin onboarding checklist | Copy from Section 8 of this SOP |

### 1.5 CRM Status Update

**Action:** Update within 15 minutes of payment.

| Field | Value |
|---|---|
| CRM | GHL (GoHighLevel) |
| Pipeline stage | "Won -- Onboarding" |
| Deal value | Monthly retainer x 12 (annualized) |
| Tags | `active-client`, `tier-[starter/growth/enterprise]`, `onboarding` |
| Custom fields | Onboarding start date, assigned operator, kickoff call date (when booked) |

### 1.6 Internal Notification

**Action:** Post to `#sales-wins` Slack channel immediately after payment confirms.

**Format:**
```
NEW CLIENT CLOSED

Client: [Full Name / Business Name]
Tier: [Starter / Growth / Enterprise]
Monthly: $[X],000/mo
Annual value: $[X * 12]K
Industry: [Industry]
Closer: [Name]
Operator assigned: [Name]

Kickoff call: [Date if booked, "TBD" if not]
```

---

## 2. ONBOARDING QUESTIONNAIRE

### 2.1 Delivery

| Detail | Value |
|---|---|
| Tool | Typeform or Google Form |
| Sent | Within 1 hour of payment (included in welcome email) |
| Reminder | 24 hours before kickoff call if not completed |
| Hard requirement | Must be completed before kickoff call proceeds |

### 2.2 Questionnaire Fields

**Section A: Business Overview**

| # | Field | Type | Required |
|---|---|---|---|
| A1 | Business name | Text | Yes |
| A2 | Website URL | URL | Yes |
| A3 | What does your business do? (2-3 sentences) | Long text | Yes |
| A4 | How long have you been in business? | Dropdown (< 1yr, 1-3yr, 3-5yr, 5-10yr, 10+yr) | Yes |
| A5 | Current monthly revenue (approximate) | Dropdown ($50K-$100K, $100K-$250K, $250K-$500K, $500K-$1M, $1M+) | Yes |
| A6 | Team size | Number | Yes |
| A7 | Your role / title | Text | Yes |

**Section B: Target Audience**

| # | Field | Type | Required |
|---|---|---|---|
| B1 | Who is your ideal customer? | Long text | Yes |
| B2 | What problem do you solve for them? | Long text | Yes |
| B3 | What does your customer's life/business look like BEFORE working with you? | Long text | Yes |
| B4 | What does it look like AFTER? | Long text | Yes |
| B5 | Average deal size / customer lifetime value | Text | Yes |
| B6 | Current close rate on sales calls (if applicable) | Text | No |

**Section C: Current Marketing**

| # | Field | Type | Required |
|---|---|---|---|
| C1 | What marketing channels are you currently using? | Multi-select (Meta Ads, Google Ads, LinkedIn Ads, YouTube, SEO, Email, Organic Social, Referrals, Other) | Yes |
| C2 | Current monthly ad spend (if any) | Text | No |
| C3 | What has worked best for you so far? | Long text | Yes |
| C4 | What have you tried that did NOT work? | Long text | Yes |
| C5 | Have you worked with a marketing agency before? If so, what was the experience? | Long text | No |
| C6 | Biggest frustration with your marketing right now? | Long text | Yes |

**Section D: Access + Infrastructure**

| # | Field | Type | Required |
|---|---|---|---|
| D1 | Do you have a Meta (Facebook) Business Manager? | Yes/No/Unsure | Yes |
| D2 | Do you have Google Analytics / GA4 set up? | Yes/No/Unsure | Yes |
| D3 | What CRM do you use? | Text (GHL, HubSpot, Salesforce, None, Other) | Yes |
| D4 | What email platform do you use? | Text (Klaviyo, Mailchimp, ActiveCampaign, None, Other) | Yes |
| D5 | Do you have existing landing pages? If yes, link them. | Long text | No |
| D6 | Do you have brand guidelines (logos, fonts, colors, photos)? | Yes/No | Yes |

**Section E: Goals + Competitors**

| # | Field | Type | Required |
|---|---|---|---|
| E1 | What is your 90-day revenue goal? | Text | Yes |
| E2 | What does success look like for you in 6 months? | Long text | Yes |
| E3 | Top 3 competitors (names or URLs) | Long text | Yes |
| E4 | What makes you different from your competitors? | Long text | Yes |
| E5 | Is there anything else we should know? | Long text | No |

### 2.3 Processing the Questionnaire

Once submitted:
1. Growth operator reviews within 4 hours
2. Flag any gaps or unclear answers -- follow up in Slack before kickoff
3. Save responses to `clients/[client-name]/research/questionnaire_responses.md`
4. Use responses as input for Phase 1 research (see `directives/client-onboarding-pipeline.md`)
5. Prepare 3-5 follow-up questions for the kickoff call based on answers

---

## 3. WEEK 1 -- KICKOFF + DISCOVERY

### 3.1 Pre-Kickoff Preparation (Operator, 2-3 hours)

Before the kickoff call, the growth operator completes:

| Task | Time | Output |
|---|---|---|
| Review questionnaire responses | 30 min | Notes + follow-up questions |
| Audit current website | 30 min | `research/website_audit_notes.md` |
| Scan competitor ads (Meta Ad Library) | 30 min | `research/competitor_ads_scan.md` |
| Review social presence (IG, LinkedIn, YouTube) | 30 min | Brand voice initial notes |
| Prepare kickoff call deck / agenda | 15 min | Agenda doc pinned in Slack |
| Set up client workspace (Section 7) | 15 min | Directory structure created |

### 3.2 Kickoff Call Agenda (90 minutes)

**Format:** Zoom or Google Meet. Record with Fathom or similar. Share recording with client after.

**Block 1: Introductions + Communication Expectations (15 min)**

| Topic | Detail |
|---|---|
| Team introductions | Growth operator, any supporting team members |
| Communication norms | Slack for day-to-day, email for formal docs, weekly call for strategy |
| Response time expectations | Slack: same business day. Email: 24 hours. Urgent: call or text. |
| Approval workflow | All creative, copy, and campaign launches require client approval before going live |
| Reporting cadence | Weekly report every [Day], monthly deep-dive on the first [Day] of each month |

**Block 2: Questionnaire Review + Deep-Dive Discovery (30 min)**

| Topic | Questions to Explore |
|---|---|
| Business model | Walk me through how a customer goes from stranger to paying customer today. |
| Revenue breakdown | What percentage of revenue comes from each channel? What is your most profitable channel? |
| Sales process | Who takes sales calls? What does the pitch look like? What are the top 3 objections you hear? |
| Past marketing | What was the best ROI you ever got from marketing? What made it work? |
| Pain points | If you could fix ONE thing about your growth right now, what would it be? |
| Dream outcome | If everything we build works perfectly, what does your business look like in 12 months? |

**Block 3: Access Provisioning Walkthrough (15 min)**

Walk through each item on the access checklist (Section 3.3). For each one:
- Confirm they have it
- Get login / admin access granted live on the call (screen share)
- If they don't have it, note it as a setup task for Week 1

**Block 4: 30-Day Milestone Setting (15 min)**

| Milestone | Target | Owner |
|---|---|---|
| Infrastructure live | Day 28-30 | 247 Growth |
| All tracking verified | Day 14 | 247 Growth |
| Email flows built | Day 21 | 247 Growth |
| Landing page live | Day 25 | 247 Growth |
| First campaign launch | Day 28-30 | 247 Growth |
| 90-day KPI targets agreed | Day 7 | Both |

Set 90-day KPI targets together:
- Lead volume target
- Cost per lead target
- Close rate target
- Revenue target
- ROAS target (if applicable)

Document in `clients/[client-name]/strategy/okrs_90day.md`.

**Block 5: Next Steps + Q&A (15 min)**

| Item | Detail |
|---|---|
| Recap action items | List every deliverable and who owns it |
| Timeline confirmation | Restate the 30-day infrastructure timeline |
| Next call | Schedule Week 1 check-in (30 min, end of week) |
| Open questions | Address anything the client is unsure about |

### 3.3 Access Checklist

Complete within 5 business days of kickoff. Track in Slack with checkboxes.

**Advertising Platforms:**
- [ ] Meta Business Manager -- Admin access granted
- [ ] Meta Ad Account(s) -- Advertiser access granted
- [ ] Google Ads -- Manager access granted (if applicable)
- [ ] LinkedIn Campaign Manager -- Account access (if applicable)
- [ ] YouTube channel -- Manager access (if applicable)

**Analytics + Tracking:**
- [ ] Google Analytics / GA4 -- Editor access
- [ ] Google Tag Manager -- Publish access
- [ ] Meta Pixel -- installed and verified
- [ ] Google Ads conversion tracking -- installed
- [ ] UTM taxonomy documented

**CRM + Email:**
- [ ] CRM (GHL / HubSpot / Salesforce) -- Admin or custom role access
- [ ] Email platform (Klaviyo / Mailchimp / ActiveCampaign) -- Admin access
- [ ] Contact lists exported (for custom audiences)

**Social Accounts:**
- [ ] Instagram -- Collaborator or login credentials
- [ ] LinkedIn company page -- Admin access
- [ ] Facebook page -- Admin access
- [ ] YouTube channel -- Manager (if content support in scope)

**Website + Assets:**
- [ ] Website backend (WordPress / Shopify / Webflow / custom) -- Editor access
- [ ] Domain registrar (for DNS changes if needed)
- [ ] Hosting provider (for page speed / technical fixes)
- [ ] Brand asset folder (logos, fonts, color codes, photo library)
- [ ] Existing content library (blog posts, videos, case studies)

**Verification:** Each item above gets a date stamp and a "verified working" confirmation from the operator.

### 3.4 Brand Voice Extraction

**Action:** Run within first 5 days of engagement.

Follow `directives/brand-voice-extraction-sop.md`:
1. Scrape client's Instagram (last 30 posts), YouTube (last 10 videos), LinkedIn, website
2. Extract tonality, vocabulary, sentence structure, energy level, communication patterns
3. Generate `clients/[client-name]/strategy/brand_voice.md`
4. Review with client on Week 1 check-in call for accuracy

### 3.5 Competitor Audit

**Action:** Complete by end of Week 1.

| Analysis | Source | Output |
|---|---|---|
| Ad creative scan | Meta Ad Library, Google Ads Transparency | `research/competitor_ads_scan.md` |
| Landing page teardown | Direct URL analysis | `research/competitor_landing_pages.md` |
| Offer comparison | Website / sales pages | `research/competitor_offers.md` |
| Positioning map | All sources | `research/positioning_map.md` |
| Content strategy | Social profiles | `research/competitor_content.md` |

Minimum 3 competitors analyzed. Deliverable: `research/competitor_analysis.md` (synthesis).

### 3.6 Week 1 Check-In Call (30 min, end of week)

**Agenda:**
1. Access status update -- what's done, what's pending (5 min)
2. Brand voice review -- share extracted profile for accuracy check (10 min)
3. Competitor highlights -- initial findings (5 min)
4. 90-day OKR finalization -- confirm or adjust targets (5 min)
5. Week 2 preview -- what gets built next (5 min)

---

## 4. WEEKS 2-4 -- INFRASTRUCTURE INSTALL

This maps directly to Agency_OS.md Section 11, Phase 2. Everything below must be complete before any campaign goes live.

### 4.1 Week 2: Tracking + Attribution + Funnel Audit

| Task | Owner | Deliverable | Done By |
|---|---|---|---|
| Install/verify Meta Pixel | Media buyer | Pixel firing on all pages | Day 10 |
| Install/verify GA4 | Media buyer | Events configured, conversions set | Day 10 |
| Set up UTM taxonomy | Media buyer | UTM naming doc in strategy/ | Day 9 |
| Configure attribution dashboard | Media buyer | Dashboard link pinned in Slack | Day 12 |
| Audit existing funnel (if any) | Growth operator | `research/funnel_audit.md` | Day 10 |
| Funnel architecture finalized | Growth operator | `strategy/funnel_architecture.md` | Day 12 |
| CRM pipeline configured | Email/CRM operator | Pipeline stages matching funnel | Day 12 |

### 4.2 Week 3: Email Sequences + Ad Creative + Landing Page

| Task | Owner | Deliverable | Done By |
|---|---|---|---|
| Lead intake email sequence (5 emails) | Email/CRM operator | `emails/lead_intake_sequence.md` | Day 17 |
| Pre-call nurture sequence (2 emails) | Email/CRM operator | `emails/pre_call_nurture.md` | Day 17 |
| No-show re-engagement (3 emails) | Email/CRM operator | `emails/no_show_sequence.md` | Day 18 |
| Long-term nurture (weekly template) | Email/CRM operator | `emails/nurture_weekly.md` | Day 19 |
| Win-back sequence (30/60/90 day) | Email/CRM operator | `emails/winback_sequence.md` | Day 19 |
| Ad creative briefs (3 angles) | Creative strategist | `ads/creative_briefs.md` | Day 16 |
| Ad copy -- 5 cold traffic scripts | Creative strategist | `ads/cold_traffic_scripts.md` | Day 18 |
| Ad copy -- 3 retargeting scripts | Creative strategist | `ads/retargeting_scripts.md` | Day 19 |
| Landing page copy | Growth operator | `assets/landing_page_copy.md` | Day 17 |
| Landing page design/build | Growth operator | Live URL or staging link | Day 21 |

### 4.3 Week 4: Campaign Build + Launch Prep

| Task | Owner | Deliverable | Done By |
|---|---|---|---|
| Ad account structure (campaigns, ad sets) | Media buyer | Account structured per strategy | Day 23 |
| Creative uploaded and configured | Media buyer | Ads in review | Day 24 |
| Audience segments built (cold, warm, retarget) | Media buyer | Audience list documented | Day 23 |
| Landing page tested (mobile + desktop, all forms) | Growth operator | QA checklist signed off | Day 25 |
| Email sequences loaded in CRM and tested | Email/CRM operator | Test sends verified | Day 25 |
| Tracking end-to-end verified | Media buyer | Lead > CRM > email flow tested | Day 26 |
| Client review call (pre-launch) | Growth operator | All assets approved by client | Day 26-27 |
| Campaigns go live | Media buyer | Live confirmation posted in Slack | Day 28-30 |

### 4.4 Weekly Check-In Call Format (30 min)

Used during Weeks 2-4 and continuing through the engagement.

**Agenda template:**

```
WEEKLY CHECK-IN -- [CLIENT NAME] -- [DATE]
Duration: 30 minutes

1. WHAT WE DID THIS WEEK (10 min)
   - [Task 1 completed]
   - [Task 2 completed]
   - [Task 3 completed]
   Status: On track / Behind / Ahead

2. WHAT'S COMING NEXT WEEK (5 min)
   - [Task 1 planned]
   - [Task 2 planned]
   - [Task 3 planned]

3. APPROVALS NEEDED (5 min)
   - [Item needing client sign-off]
   - [Item needing client sign-off]

4. QUESTIONS / BLOCKERS (5 min)
   - [Open question]
   - [Blocker and proposed solution]

5. CLIENT QUESTIONS (5 min)
   - Open floor
```

### 4.5 Weekly Report Template

Sent every Friday by 5pm ET. Pinned in client Slack channel.

```
WEEKLY PERFORMANCE REPORT -- [CLIENT NAME]
Week of [DATE] to [DATE]

--- METRICS ---
| Metric          | This Week | Last Week | Change  | Target  |
|-----------------|-----------|-----------|---------|---------|
| Ad Spend        | $[X]      | $[X]      | [+/-]%  | $[X]    |
| Impressions     | [X]       | [X]       | [+/-]%  | --      |
| Clicks          | [X]       | [X]       | [+/-]%  | --      |
| CTR             | [X]%      | [X]%      | [+/-]pp | > 1.5%  |
| Leads           | [X]       | [X]       | [+/-]%  | [X]     |
| CPL             | $[X]      | $[X]      | [+/-]%  | < $[X]  |
| Calls Booked    | [X]       | [X]       | [+/-]%  | [X]     |
| Show Rate       | [X]%      | [X]%      | [+/-]pp | > 70%   |
| Closed Deals    | [X]       | [X]       | [+/-]   | [X]     |
| Revenue         | $[X]      | $[X]      | [+/-]%  | $[X]    |

--- WHAT WE DID ---
- [Action 1 and result]
- [Action 2 and result]
- [Action 3 and result]

--- WHAT WE LEARNED ---
- [Insight 1]
- [Insight 2]

--- WHAT'S NEXT ---
- [Planned action 1]
- [Planned action 2]
- [Planned action 3]

--- NOTES ---
[Any context, anomalies, or items needing discussion]
```

---

## 5. MONTH 2-3 -- OPERATION + OPTIMIZATION

### 5.1 Campaign Management Rhythm

**Daily (Internal -- No Client Involvement):**

| Task | Owner | Time |
|---|---|---|
| Check ad spend vs budget | Media buyer | 9am ET |
| Review conversion metrics (leads, CPL, ROAS) | Media buyer | 9am ET |
| Check for disapproved ads or account issues | Media buyer | 9am ET |
| Monitor email deliverability + open rates | Email/CRM operator | 10am ET |
| Flag anomalies in Slack (spend spike, conversion drop, etc.) | Media buyer | As needed |

**Weekly (Client-Facing):**

| Task | Owner | Day |
|---|---|---|
| Compile weekly performance report | Growth operator | Friday |
| Weekly strategy call | Growth operator | Scheduled day |
| Creative refresh review (new hooks every 10 days) | Creative strategist | Wednesday |
| A/B test review (LP, email subject lines, ad copy) | Growth operator | Thursday |
| Audience performance review | Media buyer | Thursday |

**Monthly (Strategic):**

| Task | Owner | When |
|---|---|---|
| Monthly strategy review call (60 min) | Growth operator | First week of month |
| Full performance report (month-over-month) | Growth operator | First week of month |
| Budget reallocation recommendation | Media buyer | First week of month |
| Creative audit (what's fatiguing, what's scaling) | Creative strategist | First week of month |
| Funnel CRO analysis | Growth operator | Mid-month |
| 90-day OKR progress check | Growth operator | Monthly |

### 5.2 Monthly Strategy Review Format (60 min)

**Agenda:**

```
MONTHLY STRATEGY REVIEW -- [CLIENT NAME] -- [MONTH YEAR]
Duration: 60 minutes

1. PERFORMANCE vs KPIs (15 min)
   | KPI               | Target    | Actual    | Status         |
   |--------------------|-----------|-----------|----------------|
   | Lead Volume        | [X]/mo    | [X]       | On Track / Off |
   | Cost Per Lead      | < $[X]    | $[X]      | On Track / Off |
   | Close Rate         | [X]%      | [X]%      | On Track / Off |
   | Revenue            | $[X]      | $[X]      | On Track / Off |
   | ROAS               | [X]x      | [X]x      | On Track / Off |

2. WHAT'S WORKING (10 min)
   - Top performing ad angle / creative
   - Best converting audience segment
   - Email sequence performance highlights

3. WHAT TO KILL (10 min)
   - Underperforming campaigns (criteria: 2x target CPL after $500+ spend)
   - Fatigued creative (frequency > 3.0, declining CTR)
   - Audiences with no conversions after 7 days

4. BUDGET REALLOCATION (10 min)
   - Shift $[X] from [losing channel] to [winning channel]
   - New test budget: $[X] for [new angle/audience/channel]

5. NEW TESTS FOR NEXT MONTH (10 min)
   - [Test 1: hypothesis, budget, success criteria]
   - [Test 2: hypothesis, budget, success criteria]

6. NEXT MONTH PRIORITIES (5 min)
   - Priority 1: [X]
   - Priority 2: [X]
   - Priority 3: [X]
```

### 5.3 90-Day OKR Template

Set during kickoff call (Section 3.2, Block 4). Reviewed monthly. Reset quarterly.

```
90-DAY OKRs -- [CLIENT NAME]
Period: [Start Date] to [End Date]

OBJECTIVE 1: [Revenue/Growth Objective]
  KR 1.1: [Specific measurable result]         Status: [RED/YELLOW/GREEN]
  KR 1.2: [Specific measurable result]         Status: [RED/YELLOW/GREEN]
  KR 1.3: [Specific measurable result]         Status: [RED/YELLOW/GREEN]

OBJECTIVE 2: [Efficiency/Cost Objective]
  KR 2.1: [Specific measurable result]         Status: [RED/YELLOW/GREEN]
  KR 2.2: [Specific measurable result]         Status: [RED/YELLOW/GREEN]
  KR 2.3: [Specific measurable result]         Status: [RED/YELLOW/GREEN]

OBJECTIVE 3: [Infrastructure/Systems Objective]
  KR 3.1: [Specific measurable result]         Status: [RED/YELLOW/GREEN]
  KR 3.2: [Specific measurable result]         Status: [RED/YELLOW/GREEN]
  KR 3.3: [Specific measurable result]         Status: [RED/YELLOW/GREEN]

STATUS KEY:
  GREEN  = On track or ahead
  YELLOW = At risk, action plan in place
  RED    = Behind, escalation needed
```

**Example OKRs for a Growth tier client:**

```
OBJECTIVE 1: Generate predictable lead flow
  KR 1.1: 80+ qualified leads per month by Month 3       GREEN
  KR 1.2: CPL below $150 by Month 2                      YELLOW
  KR 1.3: 70%+ show rate on booked calls                  GREEN

OBJECTIVE 2: Reduce acquisition cost
  KR 2.1: Blended CAC below $400 by Month 3              YELLOW
  KR 2.2: Email-attributed revenue > 20% of total         RED
  KR 2.3: Retargeting ROAS above 5x                       GREEN

OBJECTIVE 3: Build scalable infrastructure
  KR 3.1: Full attribution dashboard live by Day 14        GREEN
  KR 3.2: All 5 email flows automated and tested           GREEN
  KR 3.3: 3+ ad angles tested with clear winner            YELLOW
```

### 5.4 Creative Iteration Cycle

| Cadence | Action |
|---|---|
| Every 10 days | New hook variants for top-performing angle |
| Every 2 weeks | New static ad copy variants (headline + body) |
| Every 3 weeks | New video creative (fresh angle or new format) |
| Monthly | Full creative audit -- retire fatigued creative, identify new angles |

**Fatigue indicators:**
- Frequency > 3.0 on any ad set
- CTR declining 20%+ week-over-week
- CPL increasing 30%+ week-over-week
- Relevance score / quality ranking dropping

### 5.5 Funnel CRO Schedule

| Week | Test |
|---|---|
| Month 2, Week 1 | Headline A/B test on landing page |
| Month 2, Week 3 | CTA button copy / color test |
| Month 3, Week 1 | Application form length test (short vs long) |
| Month 3, Week 3 | Thank-you page content test (video vs text) |

Each test runs for minimum 500 visitors or 14 days, whichever comes first. Statistical significance required before declaring a winner.

---

## 6. ESCALATION PROCEDURES

### 6.1 Client Unhappy

**Trigger:** Client expresses dissatisfaction in Slack, email, or on a call. Any negative sentiment counts.

| Step | Timeline | Owner | Action |
|---|---|---|---|
| 1. Acknowledge | Within 1 hour | Growth operator | Respond in Slack/email: "I hear you. Let me look into this and get back to you with a plan." |
| 2. Diagnose | Within 4 hours | Growth operator | Identify root cause. Is it a performance issue, communication issue, expectation mismatch, or deliverable quality? |
| 3. Response plan | Within 4 hours | Growth operator | Draft a specific action plan with timeline |
| 4. Manager call | Within 24 hours | Sabbo + operator | Schedule a call with the client. Sabbo joins for executive presence. |
| 5. Execute fix | Within 48 hours | Growth operator | Begin executing the action plan. Post daily updates in Slack until resolved. |
| 6. Follow-up | 7 days later | Growth operator | Check in: "Are things moving in the right direction?" |

**Sabbo's role on escalation calls:**
- Listen first, talk second
- Acknowledge the gap without making excuses
- Present the action plan with specific dates
- Offer a goodwill gesture if appropriate (bonus deliverable, extended service, etc.)

### 6.2 Campaign Underperforming

**Trigger:** Any KPI 50%+ off target for 7+ consecutive days.

| Step | Timeline | Owner | Action |
|---|---|---|---|
| 1. Flag | Immediately | Media buyer | Post in Slack: "[KPI] is [X]% off target for [X] days. Investigating." |
| 2. Diagnosis | Within 24 hours | Media buyer + operator | Root cause analysis: creative fatigue? Audience exhaustion? Landing page issue? Tracking broken? Market shift? |
| 3. Action plan | Within 48 hours | Growth operator | Documented plan: what changes, what budget shifts, what tests |
| 4. Client communication | Within 48 hours | Growth operator | Share diagnosis + plan on weekly call or async in Slack if urgent |
| 5. Execute | Within 72 hours | Media buyer | Implement changes |
| 6. Monitor | Daily for 7 days | Media buyer | Track impact of changes. Report in next weekly check-in. |

**Common diagnoses and fixes:**

| Symptom | Likely Cause | Fix |
|---|---|---|
| CPL rising, CTR stable | Audience saturation | Expand audiences, add lookalikes |
| CPL rising, CTR dropping | Creative fatigue | New hooks, new format, new angle |
| Leads up, close rate down | Lead quality issue | Tighten qualification in form or ad copy |
| Show rate dropping | Poor nurture | Revise pre-call email sequence, add SMS reminder |
| No leads despite spend | Tracking broken | Verify pixel, check form, test end-to-end |

### 6.3 Churn Risk Detection

**Early warning signals (monitor weekly):**

| Signal | Risk Level | Response |
|---|---|---|
| Missed 2+ check-in calls | High | Operator reaches out directly. Sabbo texts client. |
| Reduced Slack activity (< 2 messages/week when previously active) | Medium | Operator sends proactive value update. |
| "When does the contract end?" or "What's our cancellation policy?" | Critical | Sabbo calls client within 24 hours. |
| "I need to think about whether to continue" | Critical | Executive check-in call within 48 hours. |
| Client stops approving creative / stops responding to reviews | High | Operator escalates to Sabbo. |
| Client hires internal marketing person | Medium | Reposition as complement, not replacement. |

### 6.4 Churn Prevention Playbook

**Proactive (run these regardless of churn signals):**

| Action | Frequency | Owner |
|---|---|---|
| Share a win or insight unprompted | Weekly | Growth operator |
| Celebrate milestones ("We hit 100 leads this month") | As they happen | Growth operator |
| Send competitive intel ("Your competitor just launched X") | Monthly | Growth operator |
| Executive check-in from Sabbo | Month 2 and Month 3 | Sabbo |
| Deliver something unexpected (bonus creative, extra report, new angle) | Monthly | Growth operator |

**Reactive (when churn signals detected):**

| Step | Action |
|---|---|
| 1 | Sabbo calls the client directly (not the operator). Personal touch. |
| 2 | Ask: "What would make this a no-brainer to continue?" Listen. |
| 3 | Present a concrete 30-day win plan tied to their answer. |
| 4 | Offer a value-add (free month extension, bonus service, strategy session). |
| 5 | If they still want to leave, conduct exit interview (Section 6.5). |

### 6.5 Client Exit Interview

If a client chooses not to renew:

| Question | Purpose |
|---|---|
| What was the #1 reason you decided not to continue? | Root cause |
| What did we do well? | Preserve for testimonials |
| What could we have done differently? | Process improvement |
| Would you recommend us to someone else? | Net promoter signal |
| Is there a scenario where you'd come back? | Win-back opportunity |

Log responses in `clients/[client-name]/reports/exit_interview.md`.
Feed learnings back into this SOP (self-annealing).

---

## 7. CLIENT WORKSPACE TEMPLATE

### 7.1 Directory Structure

Create this for every new client on Day 1:

```
clients/[client-name]/
|-- README.md              # Quick reference: funnel, metrics, tracking, contacts
|-- research/              # Phase 1 outputs
|   |-- questionnaire_responses.md
|   |-- market_dossier.md
|   |-- competitor_analysis.md
|   |-- competitor_ads_scan.md
|   |-- competitor_landing_pages.md
|   |-- competitor_offers.md
|   |-- voice_of_customer.md
|   |-- website_audit_notes.md
|   |-- funnel_audit.md
|   |-- positioning_map.md
|-- strategy/              # Phase 2 outputs
|   |-- brand_voice.md
|   |-- avatar.md
|   |-- campaign_angles.md
|   |-- ad_strategy.md
|   |-- funnel_architecture.md
|   |-- okrs_90day.md
|-- ads/                   # Ad copy and creative
|   |-- creative_briefs.md
|   |-- cold_traffic_scripts.md
|   |-- retargeting_scripts.md
|   |-- static_ad_copy.md
|-- emails/                # Email sequences
|   |-- lead_intake_sequence.md
|   |-- pre_call_nurture.md
|   |-- no_show_sequence.md
|   |-- nurture_weekly.md
|   |-- winback_sequence.md
|-- scripts/               # Sales and DM scripts
|   |-- dm_scripts.md
|   |-- call_scripts.md
|-- sms/                   # SMS workflows
|   |-- reminder_sequence.md
|-- reports/               # Weekly and monthly reports
|   |-- weekly/
|   |-- monthly/
|   |-- exit_interview.md
|-- assets/                # Brand assets received from client
|   |-- logos/
|   |-- photos/
|   |-- brand_guidelines.md
```

### 7.2 README.md Template

```markdown
# [CLIENT NAME] -- Client Workspace

> Status: **[Active/Paused/Churned]** | Started: [DATE] | Market: [MARKET]
> Scope: [Tier] ($[X]/mo) -- [Brief scope description]

---

## Quick Reference

| Field | Value |
|---|---|
| Client | [Full Name] |
| Business | [Business Name] |
| Instagram | @[handle] |
| Website | [URL] |
| Market | [City / Industry] |
| CRM | [GHL sub-account / HubSpot / etc] |
| Meta Ads | [Account ID: act_XXXXX] |
| Google Ads | [Account ID if applicable] |

---

## Funnel Architecture

[Diagram of traffic > landing page > form > call > close]

---

## Target Metrics

| Metric | Target |
|---|---|
| CPL | < $[X] |
| Cost Per Booked Call | < $[X] |
| Show Rate | [X]%+ |
| Close Rate | [X]% |
| ROAS | [X]x+ |

---

## 90-Day OKRs

[Link to strategy/okrs_90day.md]

---

## Tracking

- **247growth dashboard**: [Link or instructions]
- **Health monitor**: `python execution/client_health_monitor.py client-detail --client "[CLIENT NAME]"`
- **Meta Ads**: `python execution/meta_ads_client.py audit --account act_XXXXX`

---

## Changelog

- **[DATE]**: Client workspace created. Onboarding initiated.
```

### 7.3 Automation: Workspace Creation Script

Run after close to scaffold the workspace:

```bash
# Usage: python execution/create_client_workspace.py --name "client-name" --business "Business Name"
# Script location: execution/create_client_workspace.py
# Creates directory structure + populates README.md from template
```

If the script does not exist yet, create directories manually and copy the README template.

---

## 8. HANDOFF CHECKLIST (Closer to Operations)

This checklist is completed between the close and the kickoff call. The closer owns items 1-5. Operations owns items 6-9.

### 8.1 Closer Responsibilities

- [ ] **Contract signed** -- DocuSign completed, PDF stored in `clients/[client-name]/`
- [ ] **Payment collected** -- First month charged via Stripe, receipt confirmed
- [ ] **Welcome email sent** -- Using template from Section 1.3
- [ ] **Slack channel created** -- `#client-[name]`, client invited
- [ ] **Onboarding questionnaire sent** -- Link delivered in welcome email and Slack

### 8.2 Operations Responsibilities

- [ ] **Kickoff call scheduled** -- 90-minute slot within 5 business days of close
- [ ] **Client workspace created** -- Directory structure from Section 7.1
- [ ] **CRM updated** -- Status set to "Won -- Onboarding", all fields populated
- [ ] **Internal notification posted** -- Format from Section 1.6 in `#sales-wins`

### 8.3 Closer-to-Operator Introduction

The closer sends an email introducing the client to their growth operator:

**Subject:** Introducing Your Growth Operator -- [OPERATOR NAME]

```
Hi [CLIENT FIRST NAME],

I want to introduce you to [OPERATOR NAME], your growth operator at
247 Growth. [He/She/They] will be your primary point of contact from
here on out.

[OPERATOR NAME] is already reviewing your business and preparing for
your kickoff call. [He/She/They] will be reaching out shortly to
confirm the call time and share anything needed beforehand.

It's been great working with you through the process. You're in
excellent hands.

[CLOSER NAME]
247 Growth
```

### 8.4 Strategy Call Notes Handoff

The closer provides a summary of everything discussed during the sales process:

| Item | Detail |
|---|---|
| Why they signed up | What pain point or goal drove the decision |
| Hot buttons | What they care most about (revenue? leads? time savings? attribution?) |
| Concerns raised | Any objections or hesitations during the sales process |
| Expectations stated | Anything specific they said they expect ("I want X leads by month 2") |
| Personality notes | Communication style (data-driven? big-picture? detail-oriented? impatient?) |
| Competitor mentions | Any competitors they referenced during calls |
| Timeline pressure | Any deadlines or events driving urgency |

Saved to `clients/[client-name]/research/sales_handoff_notes.md`.

---

## 9. APPENDIX: TEMPLATES + QUICK REFERENCE

### 9.1 Key Timelines

| Milestone | Day |
|---|---|
| Payment collected | Day 0 |
| Welcome email + questionnaire sent | Day 0 (within 2 hours) |
| Contract signed | Day 0-1 |
| Slack channel live | Day 0 |
| Kickoff call | Day 1-5 |
| All access provisioned | Day 5-7 |
| Brand voice extracted | Day 5-7 |
| Competitor audit complete | Day 7 |
| Tracking + attribution live | Day 10-14 |
| Email sequences built | Day 17-21 |
| Landing page live | Day 21-25 |
| Ad creative produced | Day 18-24 |
| Campaigns launched | Day 28-30 |
| First optimization pass | Day 35-37 |
| 90-day review | Day 90 |

### 9.2 Communication Defaults

| Channel | Use For | Response Time |
|---|---|---|
| Slack | Day-to-day comms, quick questions, approvals | Same business day |
| Email | Formal documents, contracts, reports | 24 hours |
| Weekly call | Strategy, performance review, planning | Scheduled |
| Phone/text | Urgent issues only | 1 hour |

### 9.3 Tool Stack

| Function | Tool |
|---|---|
| Payment | Stripe |
| Contracts | DocuSign |
| CRM | GoHighLevel |
| Communication | Slack |
| Calls | Zoom / Google Meet |
| Call recording | Fathom |
| Scheduling | Cal.com |
| Questionnaire | Typeform / Google Forms |
| Reporting | Google Sheets + Looker Studio |
| Ad management | Meta Ads Manager, Google Ads |
| Email automation | Platform-dependent (Klaviyo, ActiveCampaign, GHL) |
| Attribution | GA4 + UTMs + custom dashboard |
| Brand voice | `execution/extract_brand_voice.py` |
| Client health | `execution/client_health_monitor.py` |

### 9.4 Performance Guarantee Terms

From Agency_OS_Pitch_Deck.md, Slide 12:

- KPI targets set mutually during kickoff call
- 90-day measurement window
- If targets not met: continued service at no additional cost until targets achieved
- Targets must be realistic and agreed upon by both parties
- External factors (market crash, product recall, etc.) are discussed and targets adjusted if needed

### 9.5 Renewal and Upsell

| Timing | Action |
|---|---|
| Day 60 | Operator mentions renewal naturally during monthly review |
| Day 75 | Sabbo sends personal note: "Here's what we've accomplished. Here's what Month 4-6 looks like." |
| Day 80 | If continuing: new 90-day OKRs drafted. If hesitant: run churn prevention playbook (Section 6.4). |
| Day 85 | Renewal confirmed or exit interview scheduled |

**Upsell opportunities:**
- Starter to Growth: "We've maxed out what one channel can do. Multi-channel unlocks [X]."
- Growth to Enterprise: "Your volume justifies dedicated resources and daily optimization."
- Add-on services: Content production, organic social management, sales enablement

### 9.6 Quality Standards

Every deliverable leaving 247 Growth meets these standards:

| Standard | Check |
|---|---|
| Written in client's brand voice | Cross-reference `strategy/brand_voice.md` |
| No placeholder text | Search for [X], [NAME], TBD, TODO |
| Mobile-optimized (all web assets) | Test on iPhone and Android viewports |
| Tracking verified | End-to-end: ad click > LP > form > CRM > email fires |
| Spell-checked and proofread | No typos in client-facing materials |
| Approved by client before launch | Written confirmation in Slack or email |

---

## Self-Annealing Log

When this SOP is used and gaps are found, log them here and update the relevant section.

| Date | Gap Found | Section Updated | Fix Applied |
|---|---|---|---|
| -- | -- | -- | -- |

---

*Agency OS -- Client Onboarding SOP v1.0 -- 2026-03-21*
*247 Growth | sabbo@247growth.org*
