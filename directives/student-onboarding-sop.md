# Student Onboarding SOP — AllDayFBA / 24/7 Profits Inner Circle
> directives/student-onboarding-sop.md | Version 1.0

---

## Purpose

When Sabbo pastes a student's Typeform application responses and says **"onboard this student"** (or similar), generate a **personalized 90-day onboarding document** covering their entire journey from enrollment to consistent $10K+ months on Amazon.

The output document gets:
1. Copied into a Google Doc
2. Shared with the student before the kickoff call
3. Walked through together on the call as their personal roadmap

---

## Trigger

- Sabbo pastes student data (name, selling status, age, problem, budget, etc.)
- Keywords: "onboard", "onboarding", "new student", "generate onboarding", "kickoff doc"

---

## Inputs (From Typeform Application)

| Field | Required | Example |
|---|---|---|
| First name | Yes | Marcus |
| Currently selling on Amazon? | Yes | No |
| Age | Yes | 28 |
| Biggest problem with Amazon / making money online | Yes | "I want to quit my 9-5" |
| Investment budget | Yes | $5k+ |
| Email | Optional | marcus@email.com |
| Phone | Optional | +15551234567 |
| Credit score | Optional | 720 |
| Enrollment date | If not provided, use today | 2026-03-15 |

---

## Step 1: Classify Student Tier

Use this deterministic logic:

```
IF currently_selling == "Yes":
    tier = "B"  # Existing seller, plateaued — needs systems, not basics

ELIF investment_budget in ("$5k+", "$3k-4k"):
    IF age >= 35 OR biggest_problem mentions ("invest", "asset", "portfolio", "passive", "business owner", "side business", "diversify", "wealth"):
        tier = "C"  # Investor/business owner adding Amazon as asset
    ELSE:
        tier = "A"  # Beginner with adequate capital

ELIF investment_budget == "$2k-3k":
    tier = "A"  # Beginner, tight budget — flag as budget_tight
    # Adjust: smaller first orders, free tool alternatives, emphasize learning over earning

ELIF investment_budget in ("$1k-2k", "$0"):
    tier = "DISQUALIFY"
    # Generate the "Getting Ready" doc instead (see Section at bottom)
```

### Secondary Signals (extract from "biggest problem" text)

**Motivation type** (shapes the Welcome section tone):
- `income_replacement` → keywords: quit, job, 9-5, replace, salary, freedom, escape, fired, laid off
- `scaling` → keywords: scale, grow, stuck, plateau, next level, more sales, expand
- `asset_building` → keywords: invest, asset, portfolio, passive, business owner, side, diversify

---

## Step 2: Generate the Onboarding Document

### Reference Files
Before generating, read these for current program details and Sabbo's frameworks:
- `bots/creators/sabbo-alldayfba-brain.md` — Sabbo's philosophy, Leverage Ladder, 24/7 Profit System, student case studies, 7 Reasons People Fail, quotable lines
- `SabboOS/Amazon_OS.md` — Program structure, coaching cadence, milestones

### Voice & Tone
- **Second person** ("you") throughout
- **Motivating but realistic** — like a coach who genuinely cares but won't sugarcoat
- **Sabbo's voice** — direct, young energy, no corporate speak, but professional
- Use Sabbo's actual quotable lines where they fit naturally
- **No fluff** — every sentence should either inform, instruct, or motivate
- **No emojis** unless Sabbo specifically requests them

### Document Structure (9 Sections + Quick Reference Card)

---

#### SECTION 1: Welcome — Why This Plan Is Built For You
**Length:** 300-400 words

- Address them by name
- Acknowledge their specific situation based on their "biggest problem" response
- Connect their pain point to the 24/7 Profit System
- Reference their tier without naming it:
  - **Tier A:** "You're starting fresh — and that's actually an advantage. No bad habits to unlearn."
  - **Tier B:** "You've already proven you can sell on Amazon. Now we're going to install the systems that turn inconsistent months into predictable ones."
  - **Tier C:** "You think like a business owner — so we're going to treat this like a business from day one. ROI, systems, delegation."
- State the 90-day target date explicitly
- End with Sabbo's philosophy: "The only way to fail in this business is if you quit."

---

#### SECTION 2: Your 90-Day Roadmap
**Format:** Week-by-week breakdown with actual calendar dates

Organize by the **Leverage Ladder progression**, NOT generic modules:

**Phase 1: Foundation & First Sales (Weeks 1-3)**
- Seller Central setup (Professional plan, $39.99/mo)
- Business entity (LLC recommended)
- Bank account separation
- SellerAmp walkthrough + Keepa basics
- Understanding BSR, ROI, profit per unit, seller count
- First product scan (storefront stalking method)
- First purchase decision
- First shipment to prep center or self-prep
- **Tier A:** Start with RA to learn the fundamentals hands-on, then transition to OA
- **Tier B:** Skip RA basics, go straight to systematizing OA with tools
- **Tier C:** Focus on OA + wholesale pipeline from day 1

**Phase 2: OA Scaling & Systems (Weeks 4-6)**
- Daily sourcing routine established (1-2 hours/day)
- Storefront stalking at scale
- Deal stacking mastered (3-Stack Protocol: cashback + credit card + coupons/gift cards)
- Ungating strategy for restricted brands
- First restock orders (proving consistency)
- Prep center integration (if not already using one)
- **Goal:** Consistent daily sourcing producing 3-5+ profitable products/day

**Phase 3: Wholesale & Diversification (Weeks 7-9)**
- Introduction to wholesale sourcing
- Finding distributors (trade shows, B2B directories, cold outreach)
- First wholesale order
- Building reorderable product catalog
- Inventory management basics (avoid stockouts, overstock)
- **Tier A:** Light introduction, keep OA as primary
- **Tier B:** Heavy focus — this is likely the unlock for their plateau
- **Tier C:** Primary focus + brand direct outreach begins

**Phase 4: Scale & Optimize (Weeks 10-12)**
- VA hiring (if ready) for sourcing assistance
- Automation tools (Tactical Arbitrage, BuyBotPro)
- Repricer setup for Buy Box optimization
- Revenue review and reinvestment strategy
- Second product category expansion
- Planning the path to $10K/month and beyond
- **Goal:** Repeatable system producing $5K-$10K+/month

For each week, include:
- **Week number and actual date range** (calculate from enrollment date)
- **Phase name**
- **Primary objective** (one clear sentence)
- **3-5 specific action items** (concrete, not vague)
- **Coaching touchpoint** (which calls happen this week)

---

#### SECTION 3: Tool Setup Checklist
**Format:** Table organized by WHEN each tool is needed

**Week 1 (Required immediately):**
| Tool | Cost | Why |
|---|---|---|
| Amazon Seller Central (Professional) | $39.99/mo | Your storefront — must be Professional to sell at scale |
| SellerAmp SAS | $15.99/mo (Chrome extension) | Profit calculator — this is your decision-making tool for every product |
| Keepa (free browser extension) | Free | Price/BSR history — tells you if a product actually sells |

**Week 2-3 (Research Phase):**
| Tool | Cost | Why |
|---|---|---|
| Keepa Premium (if budget allows) | ~$20/mo | Unlocks advanced data, product finder, API access |
| Rakuten | Free | Cashback on every retail purchase — 3-15% back |
| Capital One Shopping | Free | Auto-applies coupon codes at checkout |
| TopCashback | Free | Additional cashback source, stack with Rakuten on different purchases |

**Week 4+ (Scaling Phase):**
| Tool | Cost | Why |
|---|---|---|
| Tactical Arbitrage | $59-$129/mo | Automated OA sourcing — searches retail sites while you sleep |
| BuyBotPro | $29.99/mo | Automated deal analysis — instant buy/pass decisions |
| Repricer (BQool or RepricerExpress) | $25-$50/mo | Auto-adjusts pricing for Buy Box — essential at scale |

**Budget-adjust recommendations:**
- **$2k-3k budget:** Stick to free/cheap tools (SellerAmp + free Keepa + Rakuten). Delay Tactical Arbitrage and BuyBotPro until revenue supports it.
- **$3k-4k budget:** Standard stack above.
- **$5k+ budget:** Full stack from Week 2. Add prep center immediately.

---

#### SECTION 4: Capital Allocation Strategy
**Format:** Dollar amounts based on their stated investment budget

**OA/RA Capital Framework (NOT private label — no PPC, no listing, no photography):**

| Category | % | Purpose |
|---|---|---|
| Initial Inventory | 50-60% | First product purchases (start small, prove the process) |
| Tools & Subscriptions (3 months) | 10% | SellerAmp, Keepa, cashback setup |
| Prep Center Setup | 5-10% | If using a prep center ($1-2/unit for receiving, labeling, shipping) |
| Emergency Reserve | 20-25% | NEVER touch for inventory. Covers unexpected fees, returns, slow periods. |
| Funding Setup | 0% out of pocket | Business credit cards ($25K-$50K through Chase) — applied for during Week 1-2 |

**Generate actual dollar amounts.** Example for $10K budget:
- Inventory: $5,000-$6,000
- Tools: $1,000
- Prep center: $500-$1,000
- Reserve: $2,000-$2,500
- Plus: $25K-$50K in business credit available (applied Week 1-2)

**For tight budgets ($2k-3k):**
- Inventory: $1,200-$1,500 (start with fewer, cheaper products — prove the cycle first)
- Tools: $200-$300 (free tiers + SellerAmp only)
- Prep center: Skip initially — self-prep to save money
- Reserve: $500-$800
- **Key message:** "Your first products are about learning the process, not hitting a home run. Prioritize learning over earning."

**Credit Card Strategy (from 24/7 Profit System Pillar 4):**
- Apply for Chase Ink Business Preferred (80K points bonus)
- Apply for Chase Ink Business Cash (5% on office supplies, internet, phone)
- Apply for Capital One Spark (2% flat cashback)
- Apply for Amazon Business Amex (5% back at Amazon)
- Combined: $25K-$50K in available credit for inventory purchases
- **This is how students with limited cash start with serious buying power**

---

#### SECTION 5: Milestone Targets With Dates
**Format:** Table with actual calendar dates calculated from enrollment

| # | Milestone | Target Date | What "Done" Looks Like | Red Flag If Not Hit |
|---|---|---|---|---|
| 1 | Account Live | Week 1 | Seller Central Professional account active, business entity set up | If not done in 3 days, you're overthinking it |
| 2 | First Scan | Week 1 | Completed first storefront stalk, analyzed 20+ products in SellerAmp | Paralysis — just pick a storefront and start |
| 3 | First Purchase | Week 2 | Bought your first 3-10 units of a profitable product | Fear of spending — remember: calculated decisions, not shots in the dark |
| 4 | First Shipment | Week 2-3 | Products shipped to Amazon FBA (or prep center) | Procrastination on logistics — the process is simpler than you think |
| 5 | First Sale | Week 3-4 | Woke up to your first Amazon sale notification | If no sale by Week 4: check pricing, Buy Box eligibility, product selection |
| 6 | First $500 Week | Week 4-6 | Revenue of $500+ in a single week | Sourcing volume too low — need more products in pipeline |
| 7 | Consistent Daily Sales | Week 6-8 | Getting sales every day, not just sporadically | Need to increase SKU count and restock velocity |
| 8 | First $1K Week | Week 6-8 | Revenue of $1,000+ in a single week (not profit, revenue) | Review product selection, consider wholesale for higher volume |
| 9 | First $5K Month | Week 8-10 | Monthly revenue of $5,000+ | If stuck: likely a sourcing problem — not finding enough products |
| 10 | Consistent $10K/Month | Week 10-12+ | $10,000+ monthly revenue with 20-30% profit margins | You're on track — time to talk wholesale and scaling |

**Tier adjustments:**
- **Tier A:** Use the timeline above as-is. It's aggressive but achievable with daily effort.
- **Tier B:** Compress milestones 1-5 into Week 1-2 (you already know this stuff). Focus energy on milestones 6-10.
- **Tier C:** Same timeline but add: "First wholesale order placed" by Week 6, "First brand direct outreach" by Week 8.

---

#### SECTION 6: Common Pitfalls For Your Profile
**Format:** 5-7 specific pitfalls with explanations

**For Tier A (Beginner):**
1. **Never starting** — 99% of people don't even create the account. You paid for this program. Create the account today. Not tomorrow.
2. **Afraid to spend money on inventory** — "We are making calculated decisions, not taking shots in the dark." Your first $100 purchase is the hardest. After that, it gets easier.
3. **Analysis paralysis on product selection** — Spending 3 weeks "researching" instead of buying. If BSR is good, ROI is 30%+, profit is $3+, and there aren't 15 sellers — buy it. You'll learn more from one purchase than 100 hours of videos.
4. **Ordering too many units first time** — Start with 5-10 units per product. Prove it sells, then scale. Don't put $500 into a single untested product.
5. **Comparing yourself to YouTube sellers** — People showing $50K months have 2+ years of experience and $50K in inventory. You're in Week 2. Focus on YOUR progress.
6. **Doing too many things at once** — Amazon + crypto + dropshipping + day trading = failure at all of them. Lock in on this one thing.
7. **Not treating it like a real business** — Set a schedule. Source for 1-2 hours daily. Track your numbers. This isn't a lottery ticket — it's a business.

**For Tier B (Existing Seller):**
1. **Bringing old habits that got you stuck** — You're here because something isn't working. Be willing to unlearn and rebuild.
2. **Rushing through sourcing because "I already know how to do this"** — The Storefront Stalking method and 3-Stack Protocol might look simple but the system is what creates consistency. Don't skip steps.
3. **Ignoring data and going on gut feeling** — If you've been guessing on products, that's likely why you're plateaued. Every buy decision goes through SellerAmp.
4. **Not diversifying products** — If you're stuck, it's likely a SKU count problem. You need 30-50+ active SKUs for consistent $10K months.
5. **Emotional attachment to failing products** — Kill losers faster. If it's not selling in 30 days, lower the price and move on. Capital sitting in slow inventory is capital you can't reinvest.

**For Tier C (Investor/Business Owner):**
1. **Treating this like a passive investment from day one** — FBA requires active management, at least initially. You need to understand the full process before delegating.
2. **Hiring a VA before you understand the process yourself** — Learn the sourcing cycle first (Weeks 1-4), then hire. Otherwise you can't train or evaluate them.
3. **Over-optimizing spreadsheets instead of buying products** — Your business instinct is to model everything. That's good long-term, but for the first 4 weeks: buy, ship, sell, learn.
4. **Capital allocation too conservative** — FBA rewards velocity. The faster your inventory turns, the faster you compound. Don't sit on cash — deploy it into proven products.
5. **Expecting 30-day returns** — 90-day timeline is realistic. First month is mostly learning and setting up. Real revenue ramps in months 2-3.

---

#### SECTION 7: First Week Action Plan
**Format:** Day-by-day, 1-3 hours each

| Day | Date | Task | Time | Details |
|---|---|---|---|---|
| 1 | [Date] | **Account Setup** | 2 hrs | Create Amazon Seller Central account (Professional), set up business entity if not done, separate bank account |
| 2 | [Date] | **SellerAmp + Keepa Setup** | 1.5 hrs | Install SellerAmp SAS Chrome extension, install Keepa extension, watch Sabbo's SellerAmp tutorial, practice analyzing 5 products |
| 3 | [Date] | **First Storefront Stalk** | 2 hrs | Find 3 successful sellers on Amazon, browse their storefronts, analyze 20+ products in SellerAmp, identify 3-5 potential buys |
| 4 | [Date] | **Cashback & Funding Setup** | 1.5 hrs | Set up Rakuten + Capital One Shopping, apply for Chase Ink business credit card, set up CardBear alerts for gift card deals |
| 5 | [Date] | **First Purchase Decision** | 2 hrs | From yesterday's research, pick your best 1-3 products. Run full analysis: BSR, ROI, seller count, Keepa 90-day history. If it checks out — BUY. |
| 6 | [Date] | **Discord + Community** | 1 hr | Introduce yourself in the 24/7 Profits Discord, check the Lead Finder channel for today's sourced products, review call schedule, prep questions for first coaching call |
| 7 | [Date] | **Week 1 Review** | 1 hr | Review what you bought, what you learned, what confused you. Write down 3 questions for Sabbo. Prep for your first group call. |

**The goal of Week 1:** Overcome the inertia. By Day 7, you should have your account live, your tools set up, and your first products purchased or in-transit. Speed matters — not perfection.

---

#### SECTION 8: How Coaching Works (The 4 Pillars In Practice)

**Pillar 1: Masterclass Modules**
- Full step-by-step video training covering every aspect of OA/RA/Wholesale
- How to read Keepa charts, use SellerAmp, source products, ungate brands, ship to FBA
- Documents and checklists for every module
- Go at your own pace, but follow the weekly roadmap above

**Pillar 2: Product Sourcing Leads**
- The 24/7 Profits Lead Finder posts products daily in Discord
- Each lead includes: cost, sale price, margin, ROI, buy link, sell link
- Weekly live sourcing calls where Sabbo finds products in real-time
- "We find hundreds of products a day" — but also learn to find your own

**Pillar 3: One-on-One Access**
- Your own private Discord channel with Sabbo
- Ask questions anytime — 48-hour response SLA (usually faster)
- Send products for review, get feedback on your sourcing decisions
- Personalized game plan — not copy-paste

**Pillar 4: Systems to Scale**
- Business credit card guidance ($25K-$50K through Chase)
- Prep center setup and integration
- VA hiring and training when you're ready
- Automation tools and workflows

**Coaching Call Schedule:**
- **Weeks 1-4:** 2x/week group calls (1 hour each)
- **Weeks 5-8:** 1x/week group call + biweekly 1:1 with Sabbo (30 min)
- **Weeks 9-12:** 1x/week group call + async Loom feedback
- All calls recorded and uploaded within 24 hours

**Community Norms:**
- Be active in Discord — share wins AND struggles
- Come to calls prepared (bring questions, show your work)
- Help others when you can — teaching reinforces learning
- Celebrate every win, even small ones ($5 profit? That's proof the model works.)

**Emergency Protocol:**
- Account suspension, IP complaint, or listing removal = DM Sabbo immediately
- Don't panic — most issues are fixable within 24-48 hours
- This is what the 1:1 access is for

---

#### SECTION 9: Your Path Up the Leverage Ladder
**Format:** Where they are → where they're going → the long-term vision

**Where You Start:**
- [Tier A]: Retail Arbitrage + Online Arbitrage — learning the fundamentals, building your first inventory, getting your first sales
- [Tier B]: Systematized OA — installing the tools, methods, and routines that create consistency
- [Tier C]: OA + Wholesale foundation — building a diversified, reorderable product catalog

**Where You're Going (Months 3-6):**
- Online Arbitrage at scale (30-50+ active SKUs, daily sourcing routine, 3-Stack Protocol on every purchase)
- First wholesale accounts opened (distributors, B2B directories, trade show contacts)
- Prep center fully operational (you never touch a product)
- Revenue: $10K-$30K/month

**The Long Game (Months 6-12+):**
- Wholesale as primary channel (reorderable, higher margins, less competition)
- Brand Direct partnerships (best pricing, potential exclusivity)
- Freelance Brand Scaling (running ads for brands = recurring revenue on top of your own sales)
- VA team handling sourcing + customer service
- 80-85% passive with systems running

**This isn't just flipping products.** You're building a real, cash-flowing business asset that compounds over time. Every product you source, every brand you build a relationship with, every system you install — it all stacks. The students who understand this are the ones who hit $50K-$100K+ months.

---

#### QUICK REFERENCE CARD (End of Document)

```
╔══════════════════════════════════════════════════╗
║         24/7 PROFITS — QUICK REFERENCE           ║
╠══════════════════════════════════════════════════╣
║ Coach:          Sabbo (@allday.fba)              ║
║ Your Channel:   #[student-name] (Discord)        ║
║ Lead Finder:    #product-leads (Discord)          ║
║ Call Schedule:   [Insert schedule]                ║
║ Enrollment:     [Date]                           ║
║ 90-Day Target:  [Date]                           ║
║ Next Milestone:  [Name] by [Date]                ║
║                                                  ║
║ Emergency:      DM Sabbo on Discord              ║
║ Async Q&A:      Your private channel (48hr SLA)  ║
║                                                  ║
║ Key Tools:      SellerAmp | Keepa | Rakuten      ║
║ Key Method:     Storefront Stalking              ║
║ Key Rule:       BSR ✓ ROI 30%+ ✓ $3+ profit ✓   ║
║                     2-5 FBA sellers ✓ → BUY      ║
╚══════════════════════════════════════════════════╝
```

---

## Disqualification: "Getting Ready" Doc

If budget is $0 or $1k-2k, generate a shorter, honest document instead:

**Title:** "Your Pre-Launch Roadmap — Getting Ready for Amazon FBA"

**Contents:**
1. **Why we're not enrolling you yet** — Honest about $5K minimum capital for meaningful Amazon FBA. Below that, the math doesn't work (fees + inventory + tools + reserve = too thin).
2. **Your capital building plan** — Monthly savings targets to reach $5K within 3-6 months. Business credit card strategy (apply now, build credit).
3. **Free resources to learn while you save:**
   - Sabbo's FREE Amazon FBA Course: https://www.youtube.com/watch?v=0LCank9vlJ8
   - Sabbo's 2-hour complete training: https://www.youtube.com/watch?v=0SLOWSoGNoA
   - SellerAmp free tutorial: https://www.youtube.com/watch?v=ZHNC27h9PUI
   - Subscribe to @alldayfba for weekly sourcing videos
4. **When to reapply** — "Once you have $5K+ in capital (cash or credit), apply again. The program will still be here, and you'll be ready."

Do NOT register disqualified applicants in student tracker.

---

## Self-Annealing Notes

- If students consistently hit milestones faster/slower than projected → update timeline in this directive
- If a specific pitfall is never relevant → replace with one from coaching call feedback
- If new tools emerge or pricing changes → update Tool Setup Checklist
- If Sabbo adds new program assets (templates, checklists) → fold into relevant sections
- Track which sections students reference most on kickoff calls → expand those, trim the rest

---

## Integration Points

| System | Connection |
|---|---|
| `bots/creators/sabbo-alldayfba-brain.md` | Read for Sabbo's frameworks, philosophy, case studies, quotable lines |
| `SabboOS/Amazon_OS.md` | Program structure, coaching cadence, milestone definitions |
| `execution/student_tracker.py` | After onboarding doc is generated, manually register student: `python execution/student_tracker.py add-student --name "[name]" --tier [A/B/C] --start-date [date]` |
| CEO brain (`/Users/Shared/antigravity/memory/ceo/brain.md`) | Log new enrollment |
