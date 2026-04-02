# Group Call Framework: AI + Amazon FBA
> **Date:** April 2, 2026 | **Duration:** ~85 min | **Audience:** Amazon OS students (zero tech background)

---

## Pre-Call Checklist

- [ ] VS Code open with nomad-nebula project loaded
- [ ] Terminal visible at bottom of VS Code
- [ ] Browser tab: Stalker Dashboard (`localhost:5050/stalker`)
- [ ] Browser tab: Real Amazon seller storefront page
- [ ] Discord channel open showing alerts
- [ ] At least 1-2 tracked sellers with existing alerts in the DB
- [ ] Start Flask: `source .venv/bin/activate && python app.py`

---

# SEGMENT 1: Claude Code & AI Basics (32 min)

---

## [0:00] Opening Hook — "The AI Overhang" (3 min)

> "Most people are using AI like a fancy Google search. We're going to use it like hiring a full-time employee that works 24/7 for free."

**Talking points:**
- There's a massive gap between what AI can actually do and what people *think* it can do. That gap = the opportunity.
- Nick Saraev (built two AI agencies to $160K/month): "Most people are drinking the Pacific Ocean through a tiny straw."
- The window is closing as more people catch on. We're on the right side of it.

**Interactive:** "Type 1 in chat if you've used ChatGPT before." *(Most will.)* "Now type 2 if you've used AI to actually DO something in your business — not just ask a question." *(Most won't.)*

> "By the end of tonight, you'll understand how AI actually works under the hood and see a tool that will change how you source products forever."

---

## [3:00] What Is AI / Claude / Claude Code (5 min)

**The 3 things to understand:**

| Thing | What It Is | Analogy |
|-------|-----------|---------|
| **AI** | A pattern recognition engine trained on the entire internet. It reads, writes, and reasons. | A really smart brain that's read every book ever written |
| **Claude** | Anthropic's AI model. The "brain" we use. | The brain itself — it thinks and decides |
| **Claude Code** | That brain with HANDS. It can read files, write files, run code, search the web, scrape websites. | ChatGPT = texting a smart friend for advice. Claude Code = hiring that friend to sit at your desk, open your laptop, and do the work. |

**Key distinction:**
- ChatGPT / regular AI = you ask a question, you get an answer, you go do the work yourself
- Claude Code = you describe what you want done, the AI actually does it — writes the code, runs the scripts, creates the files, fixes its own errors

**Show on screen:** Open CLAUDE.md in VS Code. Scroll slowly.
> "Every time I start a session, the AI reads this file. It's like giving a new employee the company handbook on day one. Everything it needs to know is right here."

---

## [8:00] The IDE Setup — VS Code & Terminal (5 min)

> "You don't need to know how to code. You need to know how to give instructions."

**VS Code = Your workspace.** Think Microsoft Word but for code and AI instructions.

**Point out 3 areas on screen:**

| Area | What It Is | Analogy |
|------|-----------|---------|
| **File explorer** (left sidebar) | Shows all your folders and files | Your filing cabinet |
| **Editor** (center) | Where you read and write | Your notepad |
| **Terminal** (bottom panel) | Where you talk to the AI and run commands | Your command line — type an instruction, AI does it |

**Quick show:**
1. Open `execution/` folder → "These are all the tools. Over 200 automation scripts. You never touch these — the AI uses them."
2. Open `directives/` folder → "These are the instruction manuals. Plain English playbooks."

### File Types (60-second rapid fire)

| Extension | What It Is | You Need to Know |
|-----------|-----------|-----------------|
| `.md` | **Markdown** — formatted notes | This is how you write instructions for AI. Like Google Docs but simpler. |
| `.py` | **Python** — automation script | The AI writes these, not you. These are the tools that do the actual work. |
| `.env` | **Environment file** — secrets | API keys, passwords. Never share this file with anyone. Ever. |
| `.json` | **JSON** — structured data | Think of it like a spreadsheet in a different format. Data organized in a specific way. |
| `.yaml` | **YAML** — configuration | Settings files. Like a to-do list the computer reads. |
| `.html` | **HTML** — web page | The dashboards and interfaces you'll see. |

> "Don't memorize these. Just know: `.md` files = instructions. `.py` files = tools. Everything else = supporting stuff."

---

## [13:00] The DOE Framework — The Secret Sauce (7 min)

> This is the single most important concept. Everything else builds on this.

### The Restaurant Analogy

| Layer | Restaurant | Our System | What It Does |
|-------|-----------|------------|-------------|
| **D** — Directive | The **recipe book** | `directives/` folder (37 SOPs) | Tells the AI what to do. Written in plain English. Like instructions you'd give an employee. |
| **O** — Orchestration | The **head chef** | Claude (the AI brain) | Reads the recipe, decides what to do, calls the shots, handles problems. |
| **E** — Execution | The **line cooks** | `execution/` folder (200+ Python scripts) | Each one does ONE thing perfectly. Chop onions. Grill patty. Toast bun. Same output every time. |

### Why This Matters — The Math

> "Here's why you can't just let AI do everything on its own."

- AI is about **90% accurate** on any single step. Sounds pretty good, right?
- But what if the task has 5 steps?
- **0.9 x 0.9 x 0.9 x 0.9 x 0.9 = 0.59** — that's a 59% success rate. Basically a coin flip.
- **The fix:** Push every repeatable step into code. Code is **100% reliable** — same input, same output, every time.
- The AI only handles the THINKING (which step to do next, what to do when something goes wrong).

> "The AI decides WHAT to do. The code actually DOES it. That's how you get reliability."

**Nick Saraev demo:** "An AI took 30 seconds to sort a list of numbers. A Python script did it in 53 milliseconds. Hundreds of times faster AND essentially free."

**Show on screen:** Open CLAUDE.md, scroll to the "3-Layer Architecture" section. Point at it.
> "This is literally the instruction set the AI reads. It knows the rules."

---

## [20:00] Agents, Skills & Self-Annealing (4 min)

### Agents = Specialized AI Workers

> "You don't hire one person to do everything in a real business. You hire specialists."

- **Sourcing bot** — knows Amazon inside and out, finds products
- **Content bot** — writes posts, captions, ad copy
- **CSM bot** — monitors student progress, flags at-risk students
- **Ads bot** — analyzes ad performance, writes creative
- We have **10+ specialized agents**, each with their own identity, skills, and memory

> "Each agent only knows about their area. The sourcing bot doesn't write content. The content bot doesn't analyze ads. Specialists, not generalists."

### Skills = Speed Dial

- Instead of explaining a task to the AI every time, you save it as a **skill**
- Then you type `/source-products` and it runs the whole workflow
- We have **45+ skills** — like speed dial vs. dialing a 10-digit number every time

### Self-Annealing = The System Gets Smarter

> "This is my favorite part."

When something breaks:
1. The AI reads the error
2. Fixes the script
3. Tests it again
4. **Updates the playbook** so it never happens again

> "Most businesses make the same mistakes over and over. This system literally can't. Every error becomes a permanent fix. The system is stronger after every failure."

---

## [24:00] How You'll Use AI Day-to-Day for Amazon (4 min)

> "You won't need to build any of this. We already built it. You get access to the tools."

### 6 Ways AI Changes Your Amazon Business

| Use Case | Before AI | With AI |
|----------|----------|---------|
| **Product research** | 2-4 hours scrolling Amazon manually | AI analyzes BSR, competition, fees, margins in seconds |
| **Listing optimization** | Pay someone $200+ or guess | AI writes titles, bullets, descriptions, backend keywords |
| **Competitor analysis** | Manually check sellers one by one | AI scrapes entire storefronts, scores every product |
| **Content creation** | Stare at a blank screen | Social posts, email sequences, ad copy generated on demand |
| **Customer service** | Type every response manually | AI drafts responses, you review and send |
| **Sourcing** | Manual clearance hunting | AI scans 100+ retailers, finds cheaper sources automatically |

> "The goal is not to replace you. The goal is to give you superpowers. You make the decisions. AI does the grunt work."

---

## [28:00] Vision + Q&A Bridge (4 min)

**What's coming for students:**
- **Seller Spy** (tonight's demo) — first tool releasing
- **AI Deal Drops** — curated product opportunities pushed to Discord
- **Automated sourcing scans** — runs 24/7, notifies you when it finds something
- **Listing optimizer** — paste your listing, get instant improvements
- **Student dashboard** — track your progress, health score, milestones

> "What you're about to see in Segment 2 is the first tool. It's called Seller Spy. And it's going to change how you think about sourcing."

**Interactive:** "Drop your biggest question about AI in the chat. We'll hit the top 2-3 right now."

*(Take 2-3 minutes for quick Q&A before transitioning.)*

---

# SEGMENT 2: Seller Spy / AI Storefront Stalking (43 min)

---

## [32:00] The Problem — Why Manual Sourcing Is Broken (5 min)

> "Let me paint a picture of what sourcing looks like for most people."

**The manual grind:**
- You spend 2-4 hours a day scrolling Amazon, checking products one at a time
- Maybe you look at 20-30 products in a session
- You have no idea what successful sellers in your niche are actually selling
- By the time you find a good product, 50 other sellers already found it
- You check one retailer at a time — Walmart, then Target, then CVS — for each product
- It's slow, repetitive, and you miss 95% of the opportunities

**The analogy:**
> "Manual sourcing is like going to a library and reading every single book to find the one you want. What if you had a librarian who already read every book and just hands you the top 5?"

> "That librarian is Seller Spy."

---

## [37:00] How Seller Spy Works — The 5-Step Pipeline (5 min)

> "Here's how it works. Five steps. Dead simple."

### Step 1: Find Successful Sellers
- Go to Amazon, find a top product in your niche
- Click "Sold by [Seller Name]" → opens their storefront
- Copy their seller ID from the URL
- That's it. You just identified a target.

### Step 2: AI Scans Their Entire Storefront
- The system opens an invisible browser (called a "headless browser")
- Visits every page of that seller's storefront
- Extracts EVERY product: title, price, ASIN, rating, review count
- A seller with 500 products? Scanned in about 3 minutes.

### Step 3: AI Scores Each Product (Deal Score 0-100)
Every product gets scored on four factors:
- **Demand** (40%) — Is this product actually selling?
- **Competition** (25%) — How many other sellers are there?
- **Price** (20%) — Is it in the sweet spot for FBA?
- **Reviews** (15%) — Do real people actually want this?

### Step 4: Top Products Get Reverse-Sourced
- The system searches **15 major retailers** (Walmart, Target, CVS, Costco, etc.)
- Finds the same product cheaper
- Calculates ROI automatically — including Amazon fees, referral fees, FBA fees
- You get a list: "Buy this at Walmart for $12, sell on Amazon for $28, profit $8.50 per unit"

### Step 5: Real-Time Monitoring
- Add any seller to your watch list
- System checks every 15 minutes for new products
- When they add something new → you get a Discord alert within minutes
- **Convergence:** If 3+ tracked sellers all add the same product within 24 hours → **HOT DEAL** alert

> "Think of it like a spy network. Each seller you track is an informant. When multiple informants report the same thing, you know it's real."

**Simple flowchart to draw/show:**
```
Find Seller → Scan Storefront → Score Products → Reverse Source → Monitor + Alerts
     ↑                                                                    |
     └────────────────── Add more sellers ←────────────────────────────────┘
```

---

## [42:00] LIVE DEMO — Stalker Dashboard (10 min)

> **Screen share the Stalker Dashboard at `localhost:5050/stalker`**

### What to show (in order):

**1. Stats Bar (30 sec)**
Point out the top metrics:
- Tracked Sellers count
- Alerts Today
- Grade A Discoveries
- Average Precision
- Hot Deals (24h)

**2. Add a Seller (2 min)**
Walk through the "Deploy New Watcher" form:
- Show how to find a seller ID from Amazon URL (the `seller=` or `me=` parameter)
- Type in a real seller ID
- Give it a nickname (e.g., "Top Toy Seller")
- Click "Authorize Monitoring"
> "That's it. One click and you're now tracking everything this seller does, 24/7."

**3. Tracked Sellers Table (2 min)**
Point out:
- Accuracy scores (precision %)
- Status: Active / Quiet / Retired
- Last scan time
- Total products tracked
- Alert count
> "See this accuracy score? The system learns which sellers give you the best leads over time."

**4. Alerts Feed (3 min)**
Walk through a real alert:
- Product name, ASIN, price
- Deal Score with color coding (green = BUY, yellow = MAYBE, red = SKIP)
- Grade: A (strong buy signal), B (moderate), C (research only)
- The 3-stage pipeline: Stage 1 = instant notification, Stage 2 = deep analysis running, Stage 3 = final verdict with full profitability numbers

**5. Trigger a Live Scan (2 min)**
- Click "Scan All Nodes"
- Let it run, show real-time updates
- Show the results populating
> "This is what used to take me 3 hours of manual work. Now it runs automatically every 15 minutes, 24/7, while I sleep."

---

## [52:00] The Retailer Network — Where the Money Is (5 min)

> "The reverse sourcing engine doesn't just check one store. It checks over 100."

### Tier 1 — 15 Retailers with Custom Integration
*(These have precise price matching built in)*

| Retailer | Cashback | Notes |
|----------|----------|-------|
| Walmart | 3% | Largest selection |
| Target | 1% | Strong clearance |
| CVS | 3% | Health/beauty gold mine |
| Walgreens | 2% | Same — health/beauty |
| Costco | — | Bulk deals |
| Home Depot | 2% | Home/tools |
| Best Buy | 1% | Electronics |
| Kohl's | 4% | Apparel/home |
| Lowe's | 2% | Home/outdoor |
| Sam's Club | — | Wholesale |
| BJ's | — | Wholesale |
| Macy's | 3% | Apparel/beauty |
| Ulta | 2% | Beauty specialist |
| Dick's Sporting Goods | 2% | Sports/outdoor |
| Kroger | 1% | Grocery/home |

### Tier 2 — 85+ Additional Retailers
Nordstrom, TJ Maxx, Wayfair, Big Lots, Dollar General, Staples, GameStop, Petco, PetSmart, Vitamin Shoppe, GNC, Newegg, Bath & Body Works, and many more.

> "The system doesn't just find the product. It finds the CHEAPEST source — including cashback and gift card discounts factored into the ROI."

---

## [57:00] Deal Score Breakdown — What Makes a "Good" Product (5 min)

> "Let me break down exactly what the numbers mean so you can read these like a pro."

### Demand Signal (0-40 points) — 40% of score

| BSR Range | Points | What It Means |
|-----------|--------|--------------|
| Under 500 | 40 | Top seller — this thing FLIES off shelves |
| 500-2,000 | 35 | Strong seller — consistent daily sales |
| 2,000-5,000 | 30 | Solid — sells multiple units per day |
| 5,000-20,000 | 20 | Decent — sells regularly |
| 20,000-100,000 | 10 | Slow — might sell a few per week |
| Over 250,000 | 2 | Barely moving — avoid |

> "BSR = Best Sellers Rank. Think of it like a popularity contest. Lower number = more popular. #1 is the best-selling product in that category."

### Competition (0-25 points) — 25% of score

| Scenario | Points | What It Means |
|----------|--------|--------------|
| 1-2 FBA sellers | 25 | Low competition — great |
| 3-5 FBA sellers | 20 | Moderate — still good |
| 6-10 sellers | 10 | Getting crowded |
| Amazon on the listing | 5 | Tough — Amazon usually wins Buy Box |

> "If Amazon itself is selling the product, move on. They almost always win the Buy Box."

### Price Sweet Spot (0-20 points) — 20% of score

| Price Range | Points | Why |
|-------------|--------|-----|
| $15-$50 | 20 | Ideal FBA range — good margins, manageable risk |
| $50-$100 | 15 | Higher margin but slower sell-through |
| $8-$15 | 10 | Tight margins — fees eat into profit |
| Under $8 | 5 | Too cheap — Amazon fees destroy you |

> "Too cheap and Amazon fees kill you. Too expensive and the risk is too high when you're starting out. The sweet spot is $15-$50."

### Review Quality (0-15 points) — 15% of score

| Scenario | Points | Why |
|----------|--------|-----|
| 4+ stars AND 100+ reviews | 15 | Proven demand — people actually want this |
| 4+ stars, <100 reviews | 10 | Good product, less proven |
| 3-4 stars | 5 | Risky — quality concerns |
| Under 3 stars | 0 | Stay away |

### Reading the Total Score

| Score | Verdict | What to Do |
|-------|---------|-----------|
| **70-100** | **BUY** | Strong opportunity — verify and move fast |
| **50-69** | **MAYBE** | Worth investigating — check manually |
| **30-49** | **RESEARCH** | Needs more data before deciding |
| **0-29** | **SKIP** | Not worth your time |

---

## [62:00] Real-Time Monitoring + Convergence (5 min)

### How Monitoring Works

- You add sellers → system checks every **15 minutes** with randomized timing (so Amazon doesn't detect it)
- When a tracked seller adds a new product → **3-stage alert pipeline:**

| Stage | What Happens | When |
|-------|-------------|------|
| **Stage 1** | Instant Discord alert with basic info (ASIN, title, price) | Within minutes |
| **Stage 2** | Deep analysis runs — Keepa data, retailer scan, profitability calc | 5-10 min later |
| **Stage 3** | Original alert gets updated with final grade + full numbers | Automatic |

> "You get the heads-up immediately so you can start researching. Then the full analysis comes in automatically."

### Convergence Detection — The Secret Weapon

> "This is the most powerful feature."

- If **3 or more** tracked sellers all add the **same product** within **24 hours** → system flags it as a **HOT DEAL**
- Multiple successful sellers adding the same product is NOT a coincidence. It's a signal.
- These get a special Discord alert with higher priority

> "Your spy network has multiple informants. When they all report the same thing independently, you know it's real."

### Seller Retirement Detection
- If a seller goes quiet for 30+ days → flagged as "Retired"
- Replace them with a more active seller
- Your watch list stays lean and effective

---

## [67:00] Student Access — What's Coming (5 min)

### Phase 1 (First Release)
- Add seller storefronts to your personal watch list
- Get Discord alerts when tracked sellers add new products
- Basic deal scoring on all alerts

### Phase 2
- Full web dashboard — your own Seller Spy interface
- Deal scores, reverse sourcing results, accuracy tracking
- Filter by grade, seller, date
- See which sellers give you the best leads over time

### Phase 3
- **Community Deal Drops** — when the system finds exceptional deals (Grade A, convergence signals), they get pushed to a shared Discord channel
- Best deals surfaced automatically for the whole group
- Community feedback improves the system for everyone

> "You're not just getting a tool. You're getting a system that gets smarter the more all of us use it."

---

## [72:00] Homework — What to Do This Week (3 min)

### Assignment 1: Find 5 Successful Sellers (Required)
1. Go to Amazon
2. Search your category/niche
3. Find top products (look at Best Sellers, Movers & Shakers)
4. Click through to the seller page
5. Copy the seller URL or seller ID
6. **Drop all 5 in the coaching Discord channel**

> "We'll load these into Seller Spy before the next call."

### Assignment 2: Learn to Read a Listing (Required)
For each of those 5 sellers' top products, write down:
- **BSR** (found in the "Product Information" section, scroll down)
- **Number of FBA sellers** (check "Other Sellers on Amazon" box)
- **Price point**
- **Review count and average rating**

> "This is what the AI scores automatically — but understanding it yourself makes you dangerous."

### Assignment 3: Watch Nick Saraev's Video (Optional but Recommended)
- YouTube: "Agentic Workflows" by Nick Saraev (~6 hours)
- Even the first 30 minutes will change how you think about AI
- This is the course that inspired the architecture behind everything we built

### Assignment 4: Install VS Code (Optional for Now)
- Download from code.visualstudio.com
- Just install it — we'll walk through setup together next session

---

## [75:00] Open Q&A (7 min)

> "What questions do you have? Nothing is too basic."

### Common Questions (Pre-loaded Answers)

**"I'm not technical at all."**
> "You don't need to be. You need to know how to give instructions and read results. The AI handles the technical part."

**"Is this legal?"**
> "100% legal. This is publicly available information on Amazon. Anyone can visit a seller's storefront. We're just doing it faster and smarter."

**"How much does this cost?"**
> "The tools are included in your coaching. The AI runs for pennies per scan."

**"When can I start using Seller Spy?"**
> "Phase 1 is coming soon. In the meantime, do your homework — find those 5 sellers and drop them in Discord."

**"Does this work for [my category]?"**
> "Yes. If there are sellers on Amazon in your category, Seller Spy can track them."

---

## [82:00] Closing (3 min)

> "You now know more about AI and how it applies to Amazon than 99% of sellers out there."

> "The AI overhang is real. The window is open. And we're walking through it together."

**Reminders:**
- Drop your 5 seller IDs in Discord this week
- Write down BSR, sellers, price, reviews for each top product
- Next call: [date] — we'll review your seller picks and show early Seller Spy results

> "You're in the right room at the right time. Let's go build something."

---

# Quick-Reference Cheat Sheet

*Print this or keep it on a second screen during the call.*

| Time | Topic | Say This |
|------|-------|----------|
| 0:00 | Hook | "Pacific Ocean through a tiny straw" |
| 3:00 | AI/Claude | "ChatGPT = texting advice. Claude Code = employee at your desk" |
| 8:00 | VS Code | "Filing cabinet, notepad, command line" |
| 13:00 | DOE | "Recipe book → Head chef → Line cooks. 90% x5 = 59%" |
| 20:00 | Agents | "Specialists, not generalists. Speed dial, not full number" |
| 24:00 | Vision | "You get the tools. We built the infrastructure." |
| 28:00 | Bridge | Take 2-3 chat questions |
| 32:00 | Problem | "Reading every book in the library vs. librarian hands you top 5" |
| 37:00 | Pipeline | "Find → Scan → Score → Source → Monitor" |
| 42:00 | **DEMO** | Dashboard: add seller, show alerts, trigger scan |
| 52:00 | Retailers | "100+ retailers, 15 with custom integration" |
| 57:00 | Scores | "Demand 40 / Competition 25 / Price 20 / Reviews 15" |
| 62:00 | Monitor | "Spy network. Multiple informants = real signal" |
| 67:00 | Access | "Phase 1 → 2 → 3 rollout" |
| 72:00 | Homework | "5 sellers in Discord. Learn to read a listing." |
| 75:00 | Q&A | "Nothing is too basic" |
| 82:00 | Close | "Top 1%. Window is open. Walk through it together." |
