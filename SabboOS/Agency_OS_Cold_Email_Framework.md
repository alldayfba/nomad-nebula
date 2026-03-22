# Agency OS — Cold Email Framework
> Built from Nick Saraev's 2026 Cold Email Copywriting & Outreach Course ($15M+ in outbound sales)
> Last Updated: 2026-03-21 | Version 2.0

---

## How This File Fits the System

This document covers **cold outbound email** — the top-of-funnel engine that feeds leads into the Agency OS pipeline. It sits *upstream* of everything in `Agency_OS_Email_Sequences.md`, which handles nurture, pre-call, no-show, post-call, and win-back flows.

```
COLD EMAIL (this file)
    | reply / interest
Setter qualifies in CRM (GHL)
    | booked
Agency_OS_Email_Sequences.md Flow 2 (pre-call)
    | showed
Strategy call -> close -> onboarding
```

**Existing tooling:** `execution/generate_emails.py` generates personalized cold emails from scraped lead CSVs. The templates below can be fed into that script's `SENDER_CONTEXT` or used as standalone copy in Instantly/Smartlead.

---

# SECTION 1: Nick Saraev's Four-Step Copywriting Framework (2026)

Nick's core framework has generated $15M+ in outbound sales. Every cold email, DM, SMS, or outbound message follows these four steps in order. No exceptions until you have mastered it.

> "Close your eyes. Can you recite those four steps back to me? Personalization. Who am I and why the hell does it matter? Offer. Call to action. If you just say that back to yourselves five, ten times, you do the same thing again tomorrow, you'll remember this formula for the rest of your life."

---

## Step 1: Personalization (1-2 sentences)

**Purpose:** Answer the prospect's first question: "Is this person a scammer/spammer?"

The personalization line cannot signal that you are selling something. It must read like a real human who has some connection to them. Two techniques:

### Cold Reading

Cold reading is a set of psychological techniques used to convince someone you know them intimately, even if you have never met them. The trick: make overly general statements that sound specific. 80% of the population would agree with them, but the reader thinks it applies uniquely to them.

> "Every human being on planet Earth is probably quiet initially and then grows more comfortable. But most people lack the ability to realize they are a representative sample of the whole population because we all think we're special."

**Cold reading for Agency OS prospects (7-8 figure founders):**

| Cold Read Statement | Why It Works (80%+ true) |
|---|---|
| "I can tell you've been heads-down building and probably haven't had time to really dial in the marketing side" | Every founder feels this way |
| "Feels like you've got a great product but the growth has been more word-of-mouth than anything systematic" | Most founders at this stage rely on referrals |
| "I noticed you're doing a lot yourself — which makes sense when you care about quality" | Founders do everything themselves |
| "Your business seems like it's at that stage where the next jump requires a fundamentally different approach" | Every plateaued founder believes this |
| "Looks like you've probably been burned by an agency or two that overpromised" | Most 7-figure founders have hired and fired agencies |

### Voluntary Disclosure

Share something personal about yourself. This is an FBI-validated rapport-building tactic. When you disclose something about yourself, the other person unconsciously feels obligated to reciprocate trust.

**Voluntary disclosure examples for Agency OS:**

- "Been following your space for a while — actually started my career in [adjacent industry] before moving into growth ops."
- "My first business was in [something relatable] so I get how hard it is to hand off the marketing to someone else."
- "I spent 3 months studying your industry before we started working with businesses like yours. Became kind of obsessed honestly."
- "Your recent post about [topic] hit home — went through the exact same thing last year with one of my clients."

### Putting It Together (Agency OS Personalization Examples)

**Example 1 (YouTuber/Content Creator ICP):**
> "Hey [Name], love your content, man. Very no BS and it actually helped me rethink how we approach growth systems for our clients. Think I can help you with something and maybe return a bit of the favor."

**Example 2 (SaaS Founder ICP):**
> "Hey [Name], been following [Company] for a while. I can tell you've been heads-down building and the product is genuinely great. I think you're leaving a ton of money on the table with your acquisition setup though."

**Example 3 (Service Business ICP):**
> "Hey [Name], found your company while looking into [industry] in [city]. My wife actually used your service last month and had great things to say. Think I spotted something that could help you grow though."

### Personalization Rules
- 1-2 sentences maximum
- Cannot signal that you are selling
- Cold reading preferred over generic compliments
- Include voluntary disclosure when natural
- Reference something real but general enough that it works for 80%+ of your list
- NEVER put quotes, bold, or special formatting around scraped variables — they must blend seamlessly

---

## Step 2: Who Am I & Why Do I Matter (1-2 sentences)

**Purpose:** Answer the prospect's second question: "Okay, not a scammer. So who the hell are they and why should I care?"

Social proof IS your introduction. You do not say "I'm a growth consultant" — that is who you ARE, not who you have WORKED WITH. You borrow credibility from your clients and results.

> "Who you ARE is not who you've WORKED WITH. 'I'm a thumbnail designer' is weak as hell."

### The Template

> "I currently work with [insert client or industry client in location] to help them [thing similar to what they do]. We've done [specific number] in [specific timeframe]."

What this accomplishes simultaneously:
- **Social proof** — shows you matter
- **In-group alignment** — you work with someone like them
- **Authority** — borrow their credibility
- **Specific numbers** — not vague claims

### Agency OS "Who Am I" Examples

**For SaaS founders:**
> "I run the growth engine for a few SaaS companies right now — one just crossed $2M ARR in 14 months after we built out their acquisition system."

**For service businesses:**
> "I currently work with a [industry] company in [city] doing about $3M/year. We've added $40K/month in new revenue in the last 90 days just by rebuilding their funnel."

**For e-commerce:**
> "I run acquisition for a couple DTC brands right now. One of them went from $180K to $450K/month after we installed the full growth system."

**For content creators/coaches:**
> "I work with a few 7-figure coaches right now on their acquisition infrastructure. We've booked 200+ qualified calls in the last 60 days for one of them."

### Who Am I Rules
- 1-2 sentences maximum
- Lead with who you WORK WITH, not who you ARE
- Use specific numbers (not "a lot of revenue" — "$40K/month")
- Match the reference group to the prospect (SaaS proof for SaaS, local biz proof for local biz)
- The closer the Venn diagram overlap between your case study and your prospect, the more powerful

---

## Step 3: The Offer (2-4 sentences)

**Purpose:** Answer: "Okay, you're somebody and I care. What can you do for me?"

Two parts: (a) point out something specific about their situation using cold reading, and (b) make an offer so good that saying no feels irrational.

### The Observation (Cold Reading Their Pain)

| Cold Read Observation | Why It Works |
|---|---|
| "I think you're leaking money with your current funnel setup" | Every business has funnel leaks |
| "Your ads are probably getting decent traffic but the back end isn't converting like it should" | True for 90% of businesses running ads |
| "You're probably spending more than you need to on customer acquisition" | Every founder thinks their CAC is too high |
| "I noticed your landing page is leaving a lot on the table" | Almost every landing page can be improved |
| "Your competitors are scaling faster and I think I know why" | Creates fear of loss + curiosity |

### The Offer Template

> "I will do [X thing] in [Y time] or [Z risk mitigation]."

Every offer MUST be:
- **Quantified** — exact numbers, no ambiguity (not "some leads" — "20 qualified calls")
- **Time-bound** — definition of done (not "eventually" — "in 60 days")
- **Hyper-specific** — no ranges (not "10 to 20K" — "$20K")
- **Guaranteed** — risk reversal that puts all risk on you

> "No, you're not working for free, but you do have to offer a guarantee. That is just how it works in any sort of cold outbound nowadays."

### Agency OS Offer Examples

**The Revenue Guarantee:**
> "I'll add $50K in monthly revenue to your business in the next 90 days or I'll keep working for free until I do."

**The Call Booking Guarantee:**
> "I'll book you 20 qualified sales calls in 60 days or you don't pay. No strings."

**The Free Build:**
> "Let me build your entire acquisition system — landing page, email flows, ad campaigns — at no cost. I'll do all the work up front. Only if you love the results will I ask you to work with me."

**The Audit Give-First:**
> "I'll run a full growth audit on your business and show you exactly where you're losing money. Completely free. Just say yes and I'll have it in your inbox within 48 hours."

**The CAC Reduction:**
> "I'll cut your customer acquisition cost by 30% in 60 days or I'll refund every dollar. I only need 15 minutes of your time to get started."

### Trust Through Contrast

When you overshoot the offer result, contrast it with what you have actually done:

> "I'll add $50K/month in new revenue in 90 days. By the way, we did $180K for our last client in 4 months."

The gap between the modest promise and the massive track record builds enormous trust.

### Offer Rules
- Observation first, then offer
- The offer must sound almost too good to be true
- Built-in guarantee/risk reversal is non-negotiable
- No ranges — pick one number
- Include a timeframe — always
- Frame the result relative to their revenue ("for a business doing $2M/year, we only need to improve things by 2.5% to hit that number")

---

## Step 4: Call to Action (1-2 sentences)

**Purpose:** Minimize steps between "yes" and "booked."

Every back-and-forth step leaks approximately 5% of leads. The average person doing vague CTAs loses 25% of their pipeline through unnecessary steps.

### Bad CTAs (and why)

| CTA | Problem |
|---|---|
| "Would you be interested?" | Vague, no action to take |
| "Let me know your thoughts" | Creates 3+ back-and-forth steps before booking |
| "Check out our website" | Link in cold email kills deliverability |
| "When would be a good time to chat?" | Puts burden on them to propose a time |
| "Reply if you want to learn more" | Still multiple steps from a call |

### Good CTAs

| CTA | Why It Works |
|---|---|
| "Would you be open to a 15-minute chat? I can give you a ring at 3:30 PM today or before noon tomorrow." | Specific time, specific method, low commitment |
| "Can I send you a quick audit? Just say yes and I'll have it in your inbox within 24 hours." | One-word reply ("yes") gets the ball rolling |
| "Mind if I shoot over a 2-minute Loom showing what I found? Just say the word." | Micro commitment, specific deliverable |
| "Are you opposed to a 15-minute call this week? I'm free Tuesday at 2 PM or Thursday at 10 AM." | "Opposed to" phrasing makes saying no feel unreasonable |

### CTA Rules
- Propose a specific time AND method (phone, Zoom, Google Meet)
- Keep the ask small (15 minutes, not "let's hop on a call")
- One CTA per email — never two asks
- The reply should be as close to one word as possible ("yes," "sure," "Thursday works")
- Include your phone number or a one-click invite option when appropriate

---

## The Text Message Test

Before sending any cold email, apply this test:

> "If a friend saw you typing this, would they think it's a personal message or a mass email?"

If it reads like a mass email, rewrite it. Optimize for personal.

---

## Frame Rules

The frame of cold outbound is one-to-one personal communication. NOT corporate, NOT marketing, NOT newsletter.

### Kill Corporate Signals
- No "Hope this finds you well"
- No illustrious signature blocks
- Use "I" not "we"
- Short, casual, slightly imperfect
- No HTML formatting, no images, no banners
- No links (kills deliverability)
- No pricing (never put prices in cold outbound)

### Add Human Signals
- Include "Sent from my iPhone" at the bottom
- Include one deliberate minor spelling mistake toward the end of the email (after trust is built, never at the beginning)
- Write like you are texting a professional acquaintance
- Use contractions ("I'll" not "I will," "don't" not "do not")
- Keep sentences short and punchy

### The Deliberate Typo

Nick teaches putting one minor typo near the end of proven emails. It signals "a real human typed this quickly." Rules:
- Never at the beginning (looks sloppy before trust is established)
- Near the end, after the offer is made
- Minor — a missing letter, a doubled word, a slight misspelling
- Not in the subject line
- Examples: "tomorow" instead of "tomorrow," "definately" instead of "definitely," "recieved" instead of "received"

---

# SECTION 2: The 7 Psychological Principles

Based on Robert Cialdini's "Influence" + Nick's behavioral neuroscience background. Every cold email should hit at least 5 of 7.

> "The best cold email copywriters are basically the best psychologists."

---

## Principle 1: Give First

Provide something valuable before asking for anything. Creates a sense of obligation that lowers resistance and disarms skepticism. Like restaurant mints before the bill, Costco samples before the buy.

**Agency OS application:**
- "I ran a quick audit on your funnel and found 3 things that are probably costing you $10K+/month. Happy to walk you through them."
- "I put together a custom growth roadmap for [Company] based on what I could see publicly. Want me to send it over?"
- "I noticed your landing page has a conversion bottleneck that's probably costing you leads. Here's exactly how to fix it."

**Scoring:** Does your email give something before asking? A free audit, free insight, free work, free diagnosis? If yes, check this box.

---

## Principle 2: Micro Commitments

Start small, escalate gradually. Every small agreement makes the next larger one feel natural. Never open with "Do you want to pay me $5,000/month?"

**The escalation ladder:**
```
Free audit (say "yes") -> 15-min call -> Strategy session -> Proposal -> Signed retainer
```

**Agency OS application:**
- "Just say yes and I'll send you the audit within 48 hours" (micro commitment: one word reply)
- "Would you be open to a 15-minute chat?" (micro commitment: small time investment)
- "Mind if I send you a 2-minute Loom?" (micro commitment: watching a short video)

**Scoring:** Does your email ask for something small first, not the big sale? If yes, check this box.

---

## Principle 3: Social Proof

Human beings are herd consensus animals. We look at what others do before deciding.

**Rules for social proof:**
- Use **specific numbers** (not "a lot of clients" — "we generated $112,482 last month")
- Use **names** of clients when possible and when you have permission
- **Match the reference group** — if pitching a SaaS founder, cite SaaS results, not a dentist's results
- The closer the Venn diagram overlap between your case study and your prospect, the more powerful

**Agency OS application:**
- "I currently run growth for a $3M/year [same industry] company in [same city]."
- "We've added $180K in new revenue for our clients in the last 90 days."
- "One of our clients — similar size to you — went from $80K to $280K/month in 4 months."

**Scoring:** Does your email cite specific numbers, names, or results from similar businesses? If yes, check this box.

---

## Principle 4: Authority

Demonstrate hyper-relevant expertise. Not generic credentials — expertise that matters to THIS prospect.

**Rules:**
- Match authority to the ICP (Google Partner works for blue-collar businesses, behavioral neuroscience does not)
- Signal confidence — do not hedge ("I believe maybe I could help" vs "I can absolutely help you")
- Borrow authority from clients ("I work with [impressive name]")

**Agency OS application:**
- "We've built growth systems for [recognized brand or competitor]"
- "I've personally managed over $2M in ad spend across [their industry]"
- "Our system has been installed in 15+ businesses doing $1M-$10M/year"

**Scoring:** Does your email demonstrate relevant expertise or credentials that this specific prospect would respect? If yes, check this box.

---

## Principle 5: Rapport

Find shared context. Be specific with the shared element — generic rapport is invisible.

**Types of rapport:**
- **Explicit rapport:** "I saw you went to [school]" or "Fellow [city] person here"
- **Implicit rapport:** Mirror their communication style, message length, punctuation, tonality

**Agency OS application:**
- "Fellow founder here — I get how hard it is to hand off the marketing when you've been doing it yourself"
- "I noticed you're in [city] — spent a few years there myself, great market"
- "Your post about [topic] resonated — went through the exact same thing with a client last quarter"

**Scoring:** Does your email establish a genuine shared element with the prospect? If yes, check this box.

---

## Principle 6: Scarcity

Limit availability or create time pressure. Use REAL constraints — fake ones get detected.

**Real scarcity for Agency OS:**
- "We only take on 3 new clients per quarter because of how deeply we embed" (true — operator model means limited capacity)
- "I've got one slot opening up next month" (capacity-based)
- "I'm putting together case studies in your industry right now, which is why I'm offering this for free — won't be doing this next month" (deadline-based)

**Bad scarcity (never use):**
- "This offer expires in 24 hours!" (in a cold email to a stranger — absurd)
- "Only 2 spots left!" (they have no context for why that matters)

**Scoring:** Does your email include a real, believable limitation on time or availability? If yes, check this box.

---

## Principle 7: Shared Identity

Establish common ground through in-group language, values, or challenges. Nick calls this the most important principle.

**In-group signals for Agency OS prospects:**
- Use industry-specific language (CAC, LTV, ROAS, funnel, CRO — not "customer getting cost")
- Mirror their tone (tech founders = casual/lowercase, professional services = slightly more formal)
- Acknowledge shared struggles ("I know how frustrating it is to fire another agency that overpromised")
- Reference their world ("I know running a [industry] business at your scale means...")

**Agency OS application:**
- "I know what it's like to scale past $1M and feel like the marketing never caught up with the product"
- "Other founders I work with had the same problem — great product, no system to acquire customers predictably"
- For tech/SaaS: use lowercase, casual tone, abbreviations
- For professional services: slightly more formal but still human

**Scoring:** Does your email signal that you are part of their world, not an outsider pitching? If yes, check this box.

---

## Scoring Your Emails

Before sending any cold email, score it against all 7 principles:

| # | Principle | Present? | How? |
|---|---|---|---|
| 1 | Give First | Y/N | What are you giving? |
| 2 | Micro Commitments | Y/N | What is the small ask? |
| 3 | Social Proof | Y/N | What specific numbers/names? |
| 4 | Authority | Y/N | What relevant expertise? |
| 5 | Rapport | Y/N | What shared element? |
| 6 | Scarcity | Y/N | What real constraint? |
| 7 | Shared Identity | Y/N | What in-group signal? |

**Minimum score: 5/7.** If you score below 5, rewrite before sending. Nick's best-performing emails (from the course roastings) scored 7/7.

---

# SECTION 3: The Offer Formula for Agency OS

## The Core Formula

```
Conversion Rate = (ROI x Trust) / Friction
```

- **ROI** = Perceived return on investment (the result you promise)
- **Trust** = Confidence they have that you can deliver
- **Friction** = Difficulty/cost of getting started

High ROI + High Trust + Low Friction = High Conversion Rate.

> "The only way to cut through the noise, the constant torrent of BS, is to have some amazing offer that sounds kind of almost too good to be true."

---

## ROI Framing for $5K-$25K/mo Retainers

Agency OS targets 7-8 figure founders. Frame your ROI relative to their existing revenue to make the promise feel easily achievable:

| Prospect Revenue | Your Promise | % Improvement Needed |
|---|---|---|
| $1M/year | $50K in new revenue in 90 days | 5% improvement |
| $3M/year | $100K in new revenue in 90 days | 3.3% improvement |
| $5M/year | $100K in new revenue in 90 days | 2% improvement |
| $10M/year | $200K in new revenue in 90 days | 2% improvement |

> "If pitching a $5M/year business and promising $100K: you only need to improve their business by 2%. That's it."

**Revenue vs profit:** Use revenue as the metric. Much easier to demonstrate and more impressive-sounding. $100K in new revenue sounds better than $30K in new profit, even though they might be the same thing.

### ROI Rules
- Quantified: exact numbers, no ambiguity
- Time-bound: definition of done
- Specific: no ranges
- Frame relative to their size ("we only need to improve your business by 2-3%")

---

## Trust Building

Trust is built through four channels:

### 1. Case Studies with Matched Reference Groups
- Cite results from businesses similar in size, industry, and stage
- Use specific numbers and timeframes
- Name clients when you have permission

### 2. In-Group Alignment
- Show you already work with businesses like theirs
- Use their industry language
- Reference shared challenges

### 3. The Contrast Technique
Promise modestly, then reveal your actual track record:
> "I'll add $50K/month in new revenue. By the way, we did $180K for our last client who was in a similar situation."

The gap between the conservative promise and the massive result builds enormous trust.

### 4. The Guarantee Itself
The guarantee IS a trust signal. If you are willing to work for free until you deliver, you must be confident. The willingness to guarantee signals competence.

---

## Friction Minimization for Agency OS

Every friction point you remove increases conversion:

| Friction Point | How to Minimize |
|---|---|
| Time investment | "Just 15 minutes of your time over one call at the beginning" |
| Money risk | "You don't pay unless I deliver" / "Money-back guarantee" |
| Effort required | "We do all the work. You just give us access." |
| Complexity | "Send me your ad account login and I'll handle the rest" |
| Decision fatigue | "Just say yes and I'll get started" |
| Follow-up burden | "We won't have to talk again until I deliver all the results" |

---

## 5 Complete Offer Examples for Agency OS

### Offer 1: The Revenue Guarantee
> "I'll add $50K in new monthly revenue to your business in 90 days. I'll build the entire acquisition system — landing pages, email flows, ad campaigns, conversion tracking — all of it. If I don't hit $50K, I keep working for free until I do. I just need 15 minutes of your time for one kick-off call. We handle everything else."

### Offer 2: The Free Growth System Build
> "Let me build your entire growth operating system at no cost. Landing page, email sequences, ad campaigns, conversion tracking. I'll do all the work up front. Only if you love the results will I ask you to work with me. Just say yes and I'll have the first draft ready within 2 weeks."

### Offer 3: The Qualified Calls Guarantee
> "I'll book you 15 qualified sales calls in 60 days or you don't pay a cent. No strings. These are decision-makers in your ICP who actually want to talk. I just need access to your calendar and 15 minutes for a kick-off call."

### Offer 4: The CAC Reduction
> "I'll cut your customer acquisition cost by 30% in the next 60 days or I refund every dollar. I've done this for 12 businesses in your space this year. Takes me about 2 weeks to diagnose and rebuild, then you'll see the results by day 45."

### Offer 5: The Free Audit
> "I'll run a complete growth audit on your business — your ads, your funnel, your email flows, your conversion rates — and show you exactly where you're losing money. Completely free. I'll have it in your inbox within 48 hours. Just say yes."

---

# SECTION 4: Cold Email Templates (10 Emails)

Every template follows the 4-step framework exactly:
1. Personalization (cold reading + voluntary disclosure)
2. Who Am I & Why Do I Matter (social proof introduction)
3. The Offer (too-good-to-be-true with guarantee)
4. CTA (specific time + method)

All templates: 80-150 words, one CTA, human tone, no links, no pricing, no corporate language, one minor typo near the end.

---

## Template 1: The "Growth System" Email
**Target:** Founder doing random marketing with no system
**Principles hit:** Give First, Micro Commitments, Social Proof, Authority, Rapport, Shared Identity (6/7)

**Subject:** growth setup thought

> Hey [Name], been checking out [Company] for a bit. I can tell you've built something great and my guess is the growth side has been more hustle than system. Totally get it — was the same way with my first business.
>
> I build growth operating systems for founders doing $1M-$10M. One of my clients went from $80K to $280K/month in 4 months after we installed the full engine.
>
> I think you're probably leaving a lot on the table with your current acquisition setup. I'll run a full growth audit on your business for free and show you exactly where the leaks are. Have it in your inbox within 48 hours.
>
> Would you be open to a 15-min call to walk through it? I can ring you at 3:30 PM tomorow or Thursday before noon.
>
> - [Your Name]
>
> Sent from my iPhone

---

## Template 2: The "Agency Carousel" Email
**Target:** Founder who has hired and fired multiple agencies
**Principles hit:** Give First, Social Proof, Authority, Rapport, Scarcity, Shared Identity (6/7)

**Subject:** [Name]'s marketing setup

> Hey [Name]. Got a feeling you've been through the agency carousel — hire one, get decent results for a month, then it fizzles and you're back to square one. Happens to pretty much every founder I talk to.
>
> I work with a few businesses your size right now. We don't run campaigns — we build the entire growth engine and operate it. One of my clients fired 3 agencies before working with us. We added $40K/month in new revenue in 90 days.
>
> Here's what I'll do: build you a custom growth roadmap based on your business for free. If it's not the best marketing plan you've ever seen, no hard feelings.
>
> Can I send it over? Just say the word and I'll have it to you within 48 hours. Or if you'd rather talk through it, I'm free Tuesday at 2 PM or Thursday at 10 AM.
>
> - [Your Name]
>
> Sent from my iPhone

---

## Template 3: The "Founder as CMO" Email
**Target:** Founder doing all the marketing themselves
**Principles hit:** Give First, Micro Commitments, Social Proof, Rapport, Scarcity, Shared Identity (6/7)

**Subject:** [Name] quick question

> Hey [Name]. I can tell you've been running most of the marketing yourself — which makes sense when you care about quality. But I'm guessing it's eating up 15-20 hours a week that should be going into product and team.
>
> I run growth ops for founders in your space. We embed into the business and take over the entire acquisition engine. Last client was spending 25 hours/week on marketing. We took that to zero and grew revenue by 35% in 3 months.
>
> I'll build a full acquisition plan for [Company] at no cost. You just send me your current setup and I handle the rest. If you don't love it, we part friends.
>
> Mind a 15-min call this week? I'm free Wednesday at 3 PM or Friday before noon. Can ring you or send a one-click Meet invite, whatever's easist.
>
> - [Your Name]
>
> Sent from my iPhone

---

## Template 4: The "LinkedIn Trigger" Email
**Target:** Founder who recently posted about growth, marketing, or scaling challenges
**Principles hit:** Micro Commitments, Social Proof, Authority, Rapport, Shared Identity (5/7)

**Subject:** your post about [topic]

> Hey [Name], saw your LinkedIn post about [topic]. Hit home for me — went through the exact same thing with a client last quarter. The answer ended up being simpler than we expected.
>
> I build growth systems for businesses like yours. We work with a few companies in [industry] doing $1M-$5M and the pattern is almost always the same: great product, no repeatable acquisition engine behind it.
>
> Based on what you posted, I'm pretty confident we could add $50K/month in new revenue within 90 days. If we don't hit that number, you don't pay. Just how we operate.
>
> Would you be open to a quick 15-min call? I can give you a ring Thursday at 2 PM or Friday morning. Just let me know.
>
> - [Your Name]
>
> Sent from my iPhone

---

## Template 5: The "Website Audit" Email
**Target:** Cold reading their website/funnel
**Principles hit:** Give First, Micro Commitments, Social Proof, Authority, Shared Identity (5/7)

**Subject:** [Company] landing page

> Hey [Name]. Spent some time on your site this morning and I think your landing page is leaving a lot of money on the table. Not in a bad way — the product is clearly great. But the conversion flow has a few leaks that are probably costing you $10-20K/month in lost revenue.
>
> I build growth systems for businesses in your space. One of my clients had a similar issue — we rebuilt their funnel and conversion went from 2.1% to 6.8% in 6 weeks. Added $35K/month in new revenue.
>
> I already put together some notes on what I'd fix. Want me to send them over? Completely free, no strings. Takes you 5 minutes to read.
>
> Just say yes and I'll shoot it over today. Or if you'd rather walk through it live I'm free tomorow at 3 PM.
>
> - [Your Name]
>
> Sent from my iPhone

---

## Template 6: The "Competitor" Email
**Target:** Someone in their space is scaling and they should know about it
**Principles hit:** Micro Commitments, Social Proof, Authority, Scarcity, Shared Identity (5/7)

**Subject:** [Name]'s blind spot

> Hey [Name]. Not sure if you've noticed but [competitor/peer in their space] has been scaling pretty aggressively over the last few months. I don't think it's because their product is better — they just have a better acquisition system behind it.
>
> I work with businesses in your industry and I've seen this pattern a lot. The companies that build a real growth engine early tend to pull away fast. The ones that don't eventually hit a ceiling.
>
> I'll tell you exactly what they're doing differently and build you a plan to close the gap. Free. I've done this for 12 businesses in your space this year. Takes about 48 hours to put together.
>
> Are you opposed to a 15-min chat this week? I can ring you Wednesday at 2 or Friday at 10. Either works for me.
>
> - [Your Name]
>
> Sent from my iPhone

---

## Template 7: The "Revenue Leak" Email
**Target:** They are losing money without knowing it
**Principles hit:** Give First, Micro Commitments, Social Proof, Authority, Shared Identity (5/7)

**Subject:** you're probably losing $15K/month

> Hey [Name]. Going to be direct — I think [Company] is losing somewhere between $10-20K/month in revenue from acquisition leaks. Not because you're doing anything wrong, but because there's no system connecting your ads to your sales process.
>
> I run growth ops for a few companies your size. Most common thing I see: good product, decent traffic, but the back end isn't converting because the funnel was never built properly. We fix that and revenue jumps 20-40% within 90 days. Happened with our last 3 clients.
>
> I'll diagnose exactly where you're losing money. Free, no strings. I'll put together a full audit and have it in your inbox within 48 hours.
>
> Just say yes and I'll get started. Or we can hop on a 15-min call — I'm free Tuesday at 3 PM or Thursday morning. Completley up to you.
>
> - [Your Name]
>
> Sent from my iPhone

---

## Template 8: The "Free Audit" Give-First Email
**Target:** Lead with pure value, no ask
**Principles hit:** Give First, Micro Commitments, Social Proof, Authority, Rapport, Shared Identity (6/7)

**Subject:** put something together for you

> Hey [Name]. I've been studying [industry] businesses for a while and [Company] caught my eye. Genuinely impressive what you've built.
>
> I work with businesses in your space — currently helping a few companies between $1M-$5M install growth operating systems. We've generated over $500K in new revenue for clients in the last 6 months.
>
> I put together a growth audit for [Company] based on what I could see publicly. It covers your funnel, your messaging, your conversion flow, and where I think the biggest opportunities are. Took me about 2 hours. It's yours, no strings attached.
>
> Want me to send it over? Just say yes and I'll have it in your inbox today. No call needed unless you want one.
>
> - [Your Name]
>
> Sent from my iPhone

---

## Template 9: The "Case Study" Email
**Target:** Share a relevant result that mirrors their situation
**Principles hit:** Give First, Social Proof, Authority, Rapport, Shared Identity (5/7)

**Subject:** thought of you

> Hey [Name]. Just wrapped up a project with a [industry] company that reminds me a lot of [Company]. Similar size, similar product, same growth challenges. Figured I'd reach out.
>
> They were stuck around $150K/month with no system to scale past it. We built the full acquisition engine — ads, funnel, email, conversion tracking — and they hit $280K/month within 4 months. They didn't have to do anything except give us access.
>
> I think you're in a similar position. I'd bet we could add $50K/month in new revenue in 90 days or I'll keep working until we do. No risk on your end.
>
> Would you be open to a 15-min call this week? Can ring you at 3 PM tomorow or send you a Google Meet link. Whatever's easier.
>
> - [Your Name]
>
> Sent from my iPhone

---

## Template 10: The "Industry Specific" Email
**Target:** Vertical customization (swap industry details)
**Principles hit:** Give First, Micro Commitments, Social Proof, Authority, Shared Identity (5/7)

**Subject:** [industry] growth engine

> Hey [Name]. I've been working with [industry] businesses for the last [X] months and there's a pattern I keep seeing: great [product/service], solid reputation, but no repeatable system to bring in new [customers/patients/clients] predictably.
>
> I currently run growth for [X] [industry] businesses. We've added a combined $[X] in new revenue this year. The system takes about 30 days to install and runs month over month with almost no involvement from you.
>
> Here's what I'll do: build you a custom growth plan based on your market, your competition, and your current setup. Completely free. If it's not actionable, no hard feelings. But if you want us to execute it, I'll guarantee $[X] in new revenue in 90 days or you don't pay.
>
> Can we do a 15-min call? I'm free [Day] at [Time] or [Day] before noon. Just let me know and I'll send over a calender link.
>
> - [Your Name]
>
> Sent from my iPhone

---

# SECTION 5: Subject Lines

## The Plausible Deniability Principle

> "Subject lines do not sell. If you find yourself selling at all in the subject line, you're doing something wrong."

The subject line has ONE job: buy the click. Create enough curiosity that they open the email, without revealing what the email is about. The reader should think: "Do I know this person? Is this a friend? A fan? An investor?"

Combined subject + teaser = approximately 148-150 characters. Unused space fills with metadata (date, time, etc.). The subject and teaser interact — a short subject gives more room for the teaser (first line of your email) to do work.

---

## 10 Bad Subject Lines (with reasons)

| # | Subject Line | Problem |
|---|---|---|
| 1 | "Interested in AI-driven performance optimization" | Corporate-speak, gives away the pitch immediately |
| 2 | "Growth agency services for [Company]" | Selling in the subject, screams template |
| 3 | "[Name], I can 10x your revenue" | Unbelievable claim, selling, corporate |
| 4 | "Quick question about your marketing" | "Quick" signals template/mass send |
| 5 | (No subject) | Correlated with spam/scams, always have a subject |
| 6 | "RE: Our conversation" | Fake reply thread — destroys trust when they realize |
| 7 | "Partnership opportunity with [Agency Name]" | Corporate, selling, "opportunity" is a spam trigger |
| 8 | "Can I help you scale to 8 figures?" | Selling, question format, unbelievable |
| 9 | "[Name], I noticed 3 problems with your funnel" | Too specific = clearly scraped, negative opener |
| 10 | "FREE growth audit for [Company]" | "FREE" in caps = spam filter trigger, selling |

---

## 10 Good Subject Lines for Agency OS

| # | Subject Line | Why It Works |
|---|---|---|
| 1 | "growth setup thought" | Lowercase, giving something (a thought), vague enough to click |
| 2 | "[Name]'s blind spot" | Fear of loss, curiosity, must click to find out |
| 3 | "[Name] quick question" | Short, could be from anyone, plausible deniability |
| 4 | "thought of you" | Sounds personal, like a friend forwarding something |
| 5 | "your [industry] and a growth idea" | Lowercase, tangential mention, giving something |
| 6 | "[Name]" | Just their name. Maximum plausible deniability |
| 7 | "[Name], are you taking on investors?" | Flips the script — sounds like THEY are being offered money |
| 8 | "put something together for you" | Give-first framing, curiosity, sounds personal |
| 9 | "you're probably losing $15K/month" | Fear of loss, specific number, lowercase signals real person |
| 10 | "[Company] landing page" | Sounds like a colleague flagging something, not a pitch |

---

## Subject Line Rules

1. Do NOT sell in the subject line — ever
2. Use lowercase when appropriate (signals real person, not marketing team)
3. Include personalization in subject or teaser (not both — pick one)
4. Create plausible deniability — could this be from a friend? An investor? A colleague?
5. **Fear > Opportunity** — "you're wasting $2,300/month" outperforms "I can make you $2,300/month." People respond to loss more than gain.
6. Keep it short — let the teaser (first line of your email) do the heavier lifting
7. Subject + teaser interact — a 3-word subject means the teaser has more room to hook

---

# SECTION 6: Follow-Up Framework

## Start with 2 Emails Only

This is Nick's 2026 rule: launch every campaign with exactly 2 emails.

- **Email 1:** Full four-step framework (initial outbound)
- **Email 2:** Simple human-style follow-up ping

### Why Only 2 Initially

You do not know if your campaign is good yet. If it sucks and you send 5 follow-ups, you are spamming people with bad copy. More follow-ups on bad copy = higher spam/block rate = burned mailboxes and profiles.

> "If it sucks and you send 5 follow-ups, you're spamming people with bad copy. Minimize the proportion of people who mark you as spam."

### When to Add More

Only add Email 3 when your campaign is proven. Proven means: 4.8%+ reply rate with 2 emails.

| Emails | Expected Reply Rate (winning campaign) |
|---|---|
| 2 emails | 4.8% baseline |
| + Email 3 | ~6.1% |
| + Email 4 | ~6.8% |

Each additional email lifts performance incrementally — but ONLY on winning campaigns.

---

## Follow-Up Style

**DO NOT** write newsletter-style follow-ups. Real humans do not say:
> "While analyzing [Company], I noticed you were spending XYZ on platforms you didn't have to be. Our recent case study, AAA Corp, saved over $10,000 by doing whatever."

**DO** write like a real human pinging a friend:
- "Hey [Name], quick ping on this. Let me know."
- "Hey [Name], just checking in — did this get lost in your inbox?"
- "Hey [Name], are you cool, man? Get back to me."
- "Hey [Name], bumping this up. No pressure either way."

> "Just having one follow-up is going to put you ahead of 99.9% of people."

---

## 4 Follow-Up Templates

### Follow-Up 1 (Day 3)
**Subject:** re: [original subject]

> Hey [Name], just bumping this up. Let me know if it got buried. No pressure either way.

### Follow-Up 2 (Day 7)
**Subject:** [Name]

> Hey [Name], quick ping. Still happy to put that audit together for you if you're interested. Just say the word.

### Follow-Up 3 (Day 10 — only after campaign proven at 4.8%+)
**Subject:** one more thing

> Hey [Name], last thing on this — I actually put together some notes on [Company] already. Want me to send them over? Takes you 2 minutes to read. No strings.

### Follow-Up 4 (Day 14 — only for top campaigns)
**Subject:** closing the loop

> Hey [Name], going to close the loop on this. If the timing isn't right, totally get it. But if you ever want a second opinion on your growth setup, my inbox is always open. Cheers.

---

## Follow-Up Rules

- Use a different subject line for each follow-up (allows testing multiple subjects)
- Keep follow-ups SHORT — the initial email did the heavy lifting
- Each follow-up should function as a self-contained message
- Never re-pitch in a follow-up — just ping
- Add Email 3 and 4 only AFTER the campaign hits 4.8%+ reply rate

---

# SECTION 7: Iteration Framework

## Core Principle

> "Your cold emails rarely rock right away. They usually suck. The game is gradual evolution through testing."

Cold email campaigns are a data science game. You evolve campaigns through testing, not through inspiration.

---

## Sunday Cadence

Nick iterates every Sunday for 20-30 minutes. Has done this for years. Gets 45-50 iteration cycles per year that competitors never get.

**Weekly iteration checklist:**
1. Pull reply rates for all active variants
2. Kill anything below 2.5% after 500+ sends
3. Identify the top performer
4. Create 1-2 new variants testing against the winner
5. Adjust subject lines, personalization, or offer based on data
6. Launch new variants

**Total time:** 20-30 minutes per week. That is the commitment.

---

## Volume Requirements

**500-1,000 sends per variant minimum.** With only 50-100 sends, you cannot make statistically significant decisions. One reply vs zero replies means nothing at that volume.

> "50-100 sends is laughable. You can't make any real decisions from that."

---

## Big Changes Early, Small Changes Late

**Early iterations (first 2-4 weeks):**
- Test fundamentally different emails: super short vs super long, formal vs informal, personalized vs generic
- This is like a 3x difference
- Quickly cut the losing half of the possibility space

**Mid iterations (weeks 4-8):**
- 2x differences: different offers, different CTAs, different social proof
- Narrowing in on what works

**Late iterations (weeks 8+):**
- Small changes: swap a few words, tweak the subject line, adjust personalization
- 0.5x differences
- Fine-tuning a high performer

> "The size of the difference between variants should significantly decrease over time. Eventually you narrow in on a high performer."

---

## TAM Selection Rules

Your Total Addressable Market must be large enough to iterate properly.

| TAM Size | Testable? | Example |
|---|---|---|
| < 500 | No | "Holistic nutritionists in Texas" |
| 500-2,000 | Barely | "SaaS founders in Austin" |
| 2,000-10,000 | Workable | "E-commerce brands doing $1M+" |
| 10,000-50,000 | Good | "Service businesses in the US doing $1M+" |
| 50,000-100,000+ | Excellent | "Digital agencies in the United States" |

> "You need thousands of leads minimum. 'Holistic nutritionists in Texas' = couple hundred leads = can't even do one good test."

---

## A/B Testing Hierarchy

What to test, in order of impact:

1. **Offer** (highest impact) — different promises, different guarantees
2. **Personalization approach** — cold reading vs specific mention vs none
3. **Social proof** — different case studies, different numbers
4. **Subject line** — different plausible deniability angles
5. **CTA** — call vs audit vs video vs reply
6. **Tone/length** — casual vs professional, short vs long
7. **Follow-up timing** — Day 3 vs Day 5, Day 7 vs Day 10

---

# SECTION 8: Platform-Specific Optimization

The four-step framework works across all platforms. What changes: tone, length, and platform-specific levers.

---

## Email (6 Levers)

| Lever | Details |
|---|---|
| **1. Sender Name** | Full first + last name. ~20 characters. First thing people see. |
| **2. Subject Line** | 30-50 characters. Plausible deniability. Does NOT sell. |
| **3. Teaser/Preview** | 50-100 characters. First ~150 chars total (subject + teaser). Unused space fills with metadata. |
| **4. Profile Picture** | Shows when email is opened. Professional but human. |
| **5. Email Address** | People judge you on this. firstname@yourdomain.com. Not info@ or sales@. |
| **6. Email Body** | The four-step framework. Minimum 150 characters (shorter = blank white space in teaser = looks bad). |

---

## LinkedIn (7 Levers)

| Lever | Details |
|---|---|
| **1. Profile Picture** | Professional, smiling, nice lighting, contrasting background. Blue ring + white backdrop stands out. |
| **2. Name** | Shorter first name = more teaser characters visible. |
| **3. Teaser** | ~53-55 characters. Do not waste this space. |
| **4. Job Title** | ~50-60 characters. Affects perception. "Growth Operator" > "CEO at Marketing Agency." |
| **5. Premium Badge** | Gold badge makes you stand out, decreases probability of landing in "Other" inbox. |
| **6. Credentials** | HubSpot Partner, Google Partner, etc. Extra authority signal. |
| **7. Message Body** | Same four-step framework. Tone similar to email. Can break corporate pattern with shorter, more informal DMs. |

**LinkedIn-specific rules:**
- Connect limits: 100-200/week (higher with Premium, higher with aged accounts)
- Must add connection before sending full DM
- Tone similar to email but slightly more professional
- If you must use a link, put it at the end — never beginning or middle

---

## X/Twitter (6 Levers)

| Lever | Details |
|---|---|
| **1. Profile Picture** | Relevant, on-brand. |
| **2. Full Name** | May not be actual name — many use handles. |
| **3. Teaser** | ~45-50 characters. |
| **4. Handle** | Silly or discordant handles hurt credibility. |
| **5. Join Date** | New accounts = obvious spam. Need aged accounts. |
| **6. Message Body** | Can be long, not truncated. |

**X-specific rules:**
- Tone: significantly more casual than email/LinkedIn
- Expected: lowercase, abbreviations, humor
- Most messages land in "Requests" tab (not main inbox) — the game is getting out of requests
- Write in the same tone of voice as X users

---

## Instagram (4 Levers)

| Lever | Details |
|---|---|
| **1. Profile Picture** | On-brand, recognizable. |
| **2. Handle** | Often not real name. Keep it clean and memorable. |
| **3. Teaser** | ~30 characters before truncation. Very short. |
| **4. Message Body** | Same framework, adapted for casual tone. |

**Instagram-specific rules:**
- Most messages land in "Message Requests" — same challenge as X
- Significantly shorter teaser than other platforms
- Write casually, match IG tone
- The entire game is making it out of message requests

---

## iMessage/SMS (6 Levers)

| Lever | Details |
|---|---|
| **1. Phone Number** | Or contact name if saved. |
| **2. Profile Picture** | If contact is saved. |
| **3. Message Teaser** | ~90 characters. |
| **4. Message Body** | Same framework, very casual tone. |
| **5. Blue vs Green Bubble** | Blue (iMessage) = trusted. Green (SMS) = less trusted. |
| **6. Special Features** | Photos, stickers, message effects. |

**iMessage-specific rules:**
- Fill out the entire teaser (~90 chars minimum)
- Insert something provocative near the end to ensure a click
- Anyone with money typically has an iPhone (blue bubble advantage)
- Cold SMS is highly regulated — use with caution

---

## Cross-Platform Character Limits

| Platform | Subject | Teaser | Total Pre-Click | Tone |
|---|---|---|---|---|
| Email | 30-50 chars | 50-100 chars | ~150 chars | Professional but human |
| LinkedIn | N/A | 53-55 chars | 53-55 chars | Professional, can break corporate mold |
| X/Twitter | N/A | 45-50 chars | 45-50 chars | Casual, lowercase, sarcastic |
| Instagram | N/A | ~30 chars | ~30 chars | Casual, visual |
| iMessage/SMS | N/A | ~90 chars | ~90 chars | Very casual |

---

# SECTION 9: AI in Copywriting (Nick's 2026 Anti-AI Stance)

## The Strong Stance

> "I rarely if at all use AI in my copywriting these days."
>
> "People that use AI really intensely in the process tend to suck."

Nick experimented with AI personalization approximately 1.5 years ago and found: "personalization does not replace a good quality campaign." Across 10,000+ people in Maker School, the pattern is clear: heavy AI use in copy = worse results.

---

## The Skill Curve Argument

Copywriting skill follows a logarithmic curve:
- **First 2 weeks:** You learn 75% of the skill
- **Next months/years:** Diminishing returns for the remaining 25%

AI writes at the 2-weeks-of-experience level. It can produce competent-sounding copy but struggles with the top 25% — which is exactly where the market currently sits. If your emails are not above the "AI floor," nobody opens them because everyone's inbox is already flooded with AI-generated outreach.

> "AI will happily write copy at the 2-weeks-of-experience level but really struggles with writing copy up at the expert level."
>
> "You need to get to this point on your own. Write all your emails on your own. And then and only then would I even consider spot-check use of AI worthwhile."

---

## 3 Narrow Approved Use Cases

### Use Case 1: Small Templated Variables
NOT rewriting whole emails. Just filling in small personalization snippets that fit into proven copy. Example: AI determines their most popular web property and inserts "love your channel" or "love your LinkedIn posts."

### Use Case 2: Casualization Layer
Convert formal/scraped company names to casual versions:

| Scraped Data | Casualized Version |
|---|---|
| LeftClick Incorporated | LeftClick |
| The Pacific Creative Group LLC | PCG |
| Vancouver, British Columbia | East Van |
| Nick Saraev Daily Updates | Nick |
| Harvard University | Harvard |

Nick has Claude Code skills specifically for this. AI has enough geographical and cultural knowledge to do casualization well.

### Use Case 3: Lead Scraping and Enrichment
Scrape leads, enrich info, build dossiers. This is data work, not copywriting.

---

## When to Use generate_emails.py vs Hand-Writing

| Situation | Approach |
|---|---|
| First draft of a new campaign | Hand-write. Always. |
| Iterating on a proven template | Hand-write the changes. |
| Filling in variables (name, company, industry) | Use generate_emails.py |
| Casualizing scraped data | Use generate_emails.py |
| Generating 500+ personalized versions of a proven template | Use generate_emails.py |
| Writing the actual copy/offer/CTA | Hand-write. No exceptions until proven. |

**Rule:** Write all your emails yourself FIRST. Get to 4.8%+ reply rate. THEN consider using AI for variable insertion and scaling.

---

# SECTION 10: Before/After Examples

These examples are adapted from Nick's course roastings. Each shows the scoring improvement against the 7 principles.

---

## Example 1: The AI Coach Pitch

### BEFORE (Score: 1/7)

> Subject: Quick question [Name]
>
> Hi [Name], I know you run a successful business. Very cool. I build custom AI tools for companies. If you want, I can make one for your business for free. No pressure at all. Just tell me what you need and I'll handle it. Thanks for your time.

**Principles hit:** Micro Commitments (barely — "tell me what you need")
**Principles missed:** No giving (empty offer), no social proof, no authority, no rapport, no scarcity, no shared identity

### AFTER (Score: 7/7)

> Hey [Name]. Huge respect for what you've built with [Company], man. I can tell you've been grinding on this for a while.
>
> I build growth systems for a few businesses in your space right now, collectively doing over $500K/month in revenue. Through this, we've managed to add about $40K/month in new revenue on average, which I'm sure you can imagine compounds pretty fast.
>
> I'm confident I could do the same for you. Your business is basically perfect for this — there's definitely heavy lifting you're doing right now on the marketing side that you don't have to be.
>
> Will you let me build you a custom growth plan in the next 7 days? If it doesn't identify at least $20K/month in growth opportunities, you wouldn't pay a cent. You wouldn't have to do anything to get started other than just send me a brief overview of your current setup.
>
> Let me know if this is worth your time. If so, can show you how it works over a casual 15-min call. Can ring you 10 AM tomorow or Thursday? Thanks, man.

**Principles hit:** Give First (free growth plan), Micro Commitments (send overview), Social Proof ($500K/month collectively), Authority (works with multiple businesses), Rapport (casual tone, "man"), Scarcity (implied time waste), Shared Identity (business language)

---

## Example 2: The Generic Pitch

### BEFORE (Score: 2/7)

> Subject: growth agency services
>
> Hi [Name], I'm [Your Name] from [Agency]. We help businesses grow through digital marketing. We offer SEO, PPC, social media management, and funnel optimization. Our clients typically see 2-3x ROI. Would you be interested in a call to discuss how we can help your business? Best regards, [Name], [Title], [Agency]

**Principles hit:** Social Proof (weak — "2-3x ROI"), Authority (barely — credentials in signature)
**Principles missed:** No giving, no micro commitments, no rapport, no scarcity, no shared identity. Corporate language throughout. Signature block. "We" instead of "I."

### AFTER (Score: 6/7)

> Hey [Name]. Been checking out [Company] and I think you're sitting on a growth goldmine that nobody has properly tapped yet. My guess is the marketing has been more reactive than strategic — which makes total sense when you're focused on actually running the business.
>
> I run growth for a [industry] company about your size right now. We added $35K/month in new revenue in 90 days by rebuilding their acquisition system from scratch.
>
> I'll run a full growth audit on [Company] for free — your ads, funnel, email, the whole thing — and show you exactly where the leaks are. If it's not the most useful marketing analysis you've ever received, no hard feelings.
>
> Mind a 15-min call this week? I can ring you Tuesday at 3 PM or Thursday morning. Whatever works.
>
> - [Your Name]
>
> Sent from my iPhone

**Principles hit:** Give First (free audit), Micro Commitments (15-min call), Social Proof ($35K/month), Authority (runs growth for similar business), Rapport (casual tone), Shared Identity (industry language)

---

## Example 3: The Overselling Pitch

### BEFORE (Score: 0/7)

> Subject: [Name], I can 10x your revenue in 90 days
>
> Hey [Name], I noticed your company [Company] and I'm confident I can 10x your revenue. We use AI-powered automation to drive leads and sales. Our proprietary system has generated millions for our clients. Check out our case studies at [link]. We're offering a limited-time 50% discount on our services. Book a call here: [link]. Looking forward to connecting! [Name], CEO & Founder, [Agency] | [Phone] | [Email] | [LinkedIn] | [Twitter]

**Every possible mistake:** Selling in subject, unbelievable claim (10x), links in cold email (deliverability), pricing mentioned (50% discount), fake scarcity (limited-time), massive signature block, corporate language, AI branding, no personalization, no giving, no real social proof, no rapport.

### AFTER (Score: 6/7)

> Hey [Name]. I can tell [Company] has been growing fast and I think the next level requires a fundamentally different approach to how you acquire customers. Been there myself with a previous business.
>
> I work with a company in your space right now doing about $3M/year. We installed their entire growth engine — ads, funnel, email, conversion tracking — and they added $180K in new revenue in 4 months. They didn't have to do anything except give us access.
>
> I think you're in a similar spot. I'll build you a custom growth roadmap at no cost. If it's not immediately actionable, we part friends. If you want us to execute it, I'll guarantee $50K in new monthly revenue in 90 days or you don't pay.
>
> Would you be open to a 15-min call? Can ring you at 3:30 PM tomorow or send a one-click Meet invite. Just let me know.
>
> - [Your Name]
>
> Sent from my iPhone

---

# SECTION 11: The 25 Rules

These are all 25 consolidated rules from Nick's 2026 course, adapted with Agency OS context.

1. **The Four-Step Framework:** Personalization, Who Am I, Offer, CTA. Every outbound message. No exceptions until you have mastered it.

2. **The Offer Formula:** CVR = (ROI x Trust) / Friction. Maximize ROI and trust, minimize friction. This is the system, not the template.

3. **The Offer Template:** "I will do [X thing] in [Y time] or [Z risk mitigation]." Must be quantified, time-bound, and hyper-specific. For Agency OS: "$50K in new revenue in 90 days or I keep working for free."

4. **The Text Message Test:** If a friend saw you typing this, would they think it's personal or a mass email? If it looks like mass email, rewrite it.

5. **Plausible Deniability:** Subject lines buy the click. They do NOT sell. The reader should wonder if you are a friend, fan, investor, or stranger.

6. **Cold Reading:** Make general statements that sound specific. 80% of the population agrees, but the reader thinks it is unique to them. "I can tell you've been heads-down building" works for every founder.

7. **Voluntary Disclosure:** Share something personal about yourself. FBI-validated rapport builder. Gets reciprocal trust.

8. **The 7 Psychological Principles:** Give First, Micro Commitments, Social Proof, Authority, Rapport, Scarcity, Shared Identity. Score every email. Hit 5/7 minimum.

9. **System > Template:** Learn the system (the formula). It produces unlimited templates. Templates decay over time; systems appreciate.

10. **Big Changes Early, Small Changes Late:** Start by testing fundamentally different approaches. As you learn, make increasingly smaller refinements.

11. **500-1,000 Per Variant:** Minimum sends before making statistical decisions about which copy works. 50-100 is not enough.

12. **Sunday Iteration:** Pick a consistent day. 20-30 minutes. Every week. 45-50 cycles per year. Most people iterate for a week then stop.

13. **Start with 2 Emails:** Only add follow-ups after the campaign is proven at 4.8%+ reply rate. Bad copy + more follow-ups = burned accounts.

14. **No Links in Cold Emails:** Kills deliverability. Not recommended in SMS or LinkedIn either.

15. **No Pricing in Cold Emails:** Never include prices for services in outbound. The price discussion happens on the call.

16. **No AI Branding:** Never present yourself as AI, a robot, or an automated system. Always human.

17. **Kill Corporate Signals:** No "hope this finds you well," no "we," no signature blocks, no HTML formatting. Use "I," be casual, be slightly imperfect. Add "Sent from my iPhone."

18. **Every Message Self-Contained:** Each email should function as a standalone campaign even if part of a sequence.

19. **Minimize Steps:** Every back-and-forth leaks approximately 5% of prospects. Provide specific times, phone numbers, one-click links.

20. **Match the Reference Group:** Social proof must be from businesses similar to the prospect. SaaS proof for SaaS founders, local biz proof for local biz owners.

21. **The Casualization Layer:** AI's best use in copy — converting formal scraped data into casual human language (company names, neighborhoods, job titles).

22. **Fear > Opportunity:** "You're wasting $15K/month" outperforms "I can make you $15K/month." People respond to loss more than gain.

23. **The Deliberate Typo:** Include one minor spelling mistake toward the end of proven emails. Signals "real human typed this." Never at the beginning.

24. **One Goal Per Message:** Reply, watch, book, or buy. Pick ONE. If you cannot describe your goal in one sentence, you are not ready to write the campaign.

25. **The Guarantee is Non-Negotiable:** Offers with guarantees 3x top of funnel at a cost of approximately 10% margin. Net 2.7x total profit increase. There is no reason NOT to guarantee.

---

# SECTION 12: Common Mistakes (25 from Course)

1. **Using AI to write entire emails.** "People that use AI really intensely tend to suck." Write your own copy. Use AI only for variables, casualization, and scraping.

2. **No personalization.** Immediately signals spam/scam. Even a cold read is better than nothing.

3. **Scraped names without cleaning.** "Hi, Nick Automates" or "Hi, Nicks arrive daily updates." Quick fix: just take the first word. "Nick Automates" becomes "Nick."

4. **Putting special formatting around variables.** Quotes, bold, or italics around scraped data is a dead giveaway that it was inserted by a script. Variables must blend seamlessly.

5. **Including links in cold emails.** Kills deliverability. Not recommended in SMS or LinkedIn either (on LinkedIn, if you must, put links at the end only).

6. **Including pricing in cold emails.** Never put prices for services in outbound. The price conversation happens on the call.

7. **Branding yourself as AI/robot.** "I'm an AI-powered growth engine" destroys trust instantly. Always present as human.

8. **Selling in the subject line.** The subject line buys the click, nothing more. "Growth agency services for [Company]" is immediate delete.

9. **Corporate language.** "Hope this finds you well," big signature blocks, using "we" instead of "I," HTML templates. Write like a human texting a professional acquaintance.

10. **No offer or vague offer.** "I can help you grow" is not an offer. "I'll add $50K/month in 90 days or I keep working for free" is an offer.

11. **No risk reversal/guarantee.** "That is just how it works in any sort of cold outbound nowadays." If you do not guarantee, your conversion rate drops dramatically.

12. **Ranges instead of specific numbers.** "10 to 20K" is a template tell. "$20K" is specific and believable. Pick one number.

13. **No time constraint on offers.** "I'll add revenue to your business" with no deadline. Every offer needs a timeframe: "in 90 days."

14. **Vague CTAs.** "Let me know your thoughts" instead of "Can I ring you at 3:30 PM today?" Every vague step leaks 5% of prospects.

15. **Too many follow-ups on unproven campaigns.** Sending 5 follow-ups on bad copy burns your mailboxes and profiles. Start with 2. Add more only after proving the campaign.

16. **Newsletter-style follow-ups.** "While analyzing [Company], I noticed..." Real humans say: "Hey [Name], quick ping. Let me know."

17. **Not iterating.** Most people iterate intensely for one week then never again. Nick iterates every Sunday for years. 45-50 cycles per year.

18. **Insufficient volume for testing.** 50-100 sends is not enough to know if a campaign works. Need 500-1,000 per variant minimum.

19. **Making small changes too early.** Test fundamentally different approaches first (3x differences). Narrow down to small changes (0.5x) once you know what works.

20. **Visible tracking pixels.** "Email tracked with Mailsweet" at the bottom of the email. Remove all visible tracking signatures.

21. **Redundant self-introduction.** "I'm [Name]" when your name is already in the sender field. Waste of valuable characters.

22. **Comma before name.** "Hi, [Name]" looks templated. "Hi [Name]" or "Hey [Name]" reads human.

23. **Too many people in one email.** "I'm sending on behalf of... our founder Harris... our co-founder..." One person per email. If you are sending it, you are the sender.

24. **"Launching or scaling" catch-all phrases.** Trying to account for all possibilities reveals it is a template. Pick one word. "Growing" covers both without the tell.

25. **Saying "quick" in subject or body.** "Quick question," "quick call," "quick collab." Signals mass send. Real humans pouring their hearts in do not say "quick."

---

# SECTION 13: Infrastructure Setup

## Instantly.ai Setup

Instantly is the recommended platform for cold email at scale. Setup checklist:

### Domain Setup
- Buy 2-3 domains that are similar to your primary domain
  - Example: primary = 247growth.org, secondaries = 247growth.co, growwith247.com
- Each domain should have a simple landing page (legitimacy)
- Never send cold email from your primary domain

### Mailbox Setup
- Create 3-5 mailboxes per domain (firstname@domain.com format)
- Name them after real team members or plausible names
- Each mailbox sends a maximum of 30-40 emails/day (stay under radar)
- Pre-warmed mailboxes eliminate the 21-day warm-up period

### DNS Configuration
- SPF record configured
- DKIM record configured
- DMARC record configured
- All three required for deliverability

### Lead Sourcing
Use existing `execution/run_scraper.py` to scrape Google Maps leads, then filter with `execution/filter_icp.py`. Export to CSV for Instantly import.

```bash
# Scrape leads
python execution/run_scraper.py --query "SaaS companies" --location "United States" --max 500

# Filter to ICP
python execution/filter_icp.py --input .tmp/leads.csv --output .tmp/icp_leads.csv
```

### Integration with Existing Scripts

**generate_emails.py** — Use for personalizing templates at scale:
```bash
python execution/generate_emails.py --leads .tmp/icp_leads.csv --template "growth_system" --output .tmp/emails.csv
```

**outreach_sequencer.py** — Use for multi-step sequence management:
```bash
python execution/outreach_sequencer.py --leads .tmp/icp_leads.csv --sequence "agency_cold_v1"
```

### Reply Handling Protocol

1. **Interested reply** → Qualify in GHL CRM → Book on calendar
2. **Question/objection** → Respond personally (never automated) within 2 hours
3. **Not interested** → Mark as closed-lost, do not follow up
4. **Angry/unsubscribe** → Remove immediately, add to suppression list
5. **Out of office** → Re-queue for when they return
6. **Referral** → Thank them, reach out to referral with "[Name] suggested I reach out"

---

# SECTION 14: Metrics & Benchmarks

## Reply Rate Benchmarks

| Stage | Reply Rate | Status |
|---|---|---|
| < 2.5% | Poor | Rewrite from scratch |
| 2.5% - 3.5% | Below average | Keep iterating, big changes |
| 3.5% - 4.8% | Average | Getting close, medium changes |
| 4.8% - 6.5% | Good | Campaign proven, add Email 3 |
| 6.5% - 8.0% | Very good | Fine-tune, small changes |
| 8.0% - 10%+ | Excellent | Scale volume, protect the template |

## Pipeline Conversion Math

| Metric | Target | Notes |
|---|---|---|
| Sends per day | 150-200 | Across all mailboxes |
| Open rate | 50-70% | Depends on subject line |
| Reply rate | 4.8%+ | After iteration |
| Interested rate | 30-50% of replies | Not all replies are positive |
| Call booked rate | 60-80% of interested | Qualify and book fast |
| Close rate | 20-35% of calls | Depends on call quality |

## Revenue Math for Agency OS

Assuming: $10K/month average retainer, 25% close rate on calls

| Monthly Sends | Replies (5%) | Interested (40%) | Calls (70%) | Closes (25%) | New MRR |
|---|---|---|---|---|---|
| 3,000 | 150 | 60 | 42 | 10-11 | $100K-$110K |
| 5,000 | 250 | 100 | 70 | 17-18 | $170K-$180K |
| 10,000 | 500 | 200 | 140 | 35 | $350K |

## Key Numbers from Nick's Course

- Nick's career: $15M+ in outbound sales, $4M/year profit, ~decade of outbound experience
- Maker School: $230-250K/month using offer "first paying client in 90 days or money back"
- 1SecondCopy: scaled to $92K/month with "send us a title, get free 500-word blog post"
- Offers 3x top of funnel at approximately 10% margin cost = 2.7x net profit increase
- Each back-and-forth step leaks approximately 5% of leads
- Follow-up lift: adding Email 3 to winning campaign (4.8%) pushes to approximately 6.1%
- Cold calling utilization: 20% without power dialer, approximately 50% with (2.5x improvement)

## Step Leakage Math

Every unnecessary back-and-forth step loses approximately 5% of prospects:

| Steps After "Yes" | Prospects Retained |
|---|---|
| 1 (direct book) | 95% |
| 2 (one clarification) | 90% |
| 3 | 86% |
| 4 | 81% |
| 5 | 77% |
| 6+ | < 75% |

Vague CTAs like "let me know your thoughts" create 4-6 steps minimum. Specific CTAs like "I can ring you at 3:30 PM" create 1-2 steps.

---

# SECTION 15: Tactical Cheat Sheet

## Writing a Cold Email from Scratch (Nick's Exact Steps)

1. **Define your goal in one sentence.** Example: "Book calls for Agency OS growth system."
2. **Pick your offer using the formula.** I will [quantified result] in [specific timeframe] or [risk reversal].
3. **Write Step 1 — Personalization (1-2 sentences).** Cold read something true about 80% of your audience. Include voluntary disclosure.
4. **Write Step 2 — Who Am I (1-2 sentences).** "I currently work with [in-group client] to help them [thing]. We've done [specific number] in [timeframe]."
5. **Write Step 3 — Offer.** Observation about their situation (cold readable) + your too-good-to-be-true offer with guarantee.
6. **Write Step 4 — CTA.** "Would you be open to a 15-min call? I can ring you at [specific time] or send a one-click Google Meet invite."
7. **Apply the frame.** Read it through: does it sound like a friend texting? Remove corporate signals. Add "Sent from my iPhone." Add one minor typo near the end.
8. **Score against 7 principles.** Give First? Micro Commitments? Social Proof? Authority? Rapport? Scarcity? Shared Identity? Hit at least 5/7.
9. **Write a subject line.** Short, lowercase-friendly, plausible deniability, does NOT sell.
10. **Set up the follow-up.** One short human ping 3-5 days later.
11. **Send 500-1,000.** Measure reply rate. Iterate every Sunday.

## Quick Reference Tables

### The 4 Steps

| Step | Purpose | Length | Key Technique |
|---|---|---|---|
| 1. Personalization | "Not a scammer" | 1-2 sentences | Cold reading + voluntary disclosure |
| 2. Who Am I | "Why should I care?" | 1-2 sentences | Social proof as introduction |
| 3. Offer | "What can you do?" | 2-4 sentences | Too-good-to-be-true + guarantee |
| 4. CTA | "What do I do next?" | 1-2 sentences | Specific time + method |

### The 7 Principles (Quick Score)

| # | Principle | Quick Check |
|---|---|---|
| 1 | Give First | Am I offering something before asking? |
| 2 | Micro Commitments | Is my first ask small? |
| 3 | Social Proof | Did I cite specific numbers from similar businesses? |
| 4 | Authority | Did I demonstrate relevant expertise? |
| 5 | Rapport | Did I establish a shared element? |
| 6 | Scarcity | Is there a real constraint? |
| 7 | Shared Identity | Am I speaking their language? |

### The Offer Formula

```
CVR = (ROI x Trust) / Friction

ROI: Quantified + Time-bound + Specific
Trust: Social Proof + Authority + In-group + Guarantee
Friction: Time + Money + Effort + Complexity + Decision

Agency OS Offer: "I'll add $50K/month in 90 days or I keep working for free.
                  I just need 15 minutes of your time to get started."
```

### Frame Checklist

| Signal | Status |
|---|---|
| Sounds like a friend texting | Y/N |
| No "hope this finds you well" | Y/N |
| Uses "I" not "we" | Y/N |
| No signature block | Y/N |
| No links | Y/N |
| No pricing | Y/N |
| No HTML/images | Y/N |
| "Sent from my iPhone" | Y/N |
| One deliberate typo near end | Y/N |
| 80-150 words | Y/N |

### Casualization Quick Reference

| Scraped Data | Casualized |
|---|---|
| LeftClick Incorporated | LeftClick |
| The Pacific Creative Group LLC | PCG |
| Vancouver, British Columbia | East Van |
| Nick Saraev Daily Updates | Nick |
| Harvard University | Harvard |
| firstname.lastname@company.com | [First Name] |

---

# Appendix: Quotable Lines from Nick Saraev (2026 Course)

## On Cold Outreach Philosophy
- "Successful outbound essentially boils down to: can you convince a stranger who has never talked to you before and has no pre-established sense of trust with you to buy something?"
- "The best cold email copywriters are basically the best psychologists."
- "The human brain is very leaky. It's like a video game — we need a patch severely."
- "You are constantly being manipulated every single day. Every company on planet Earth is employing this right now."

## On the Framework
- "Close your eyes. Can you recite those four steps back to me? Personalization. Who am I and why the hell does it matter? Offer. Call to action."
- "80 to 90% of all situations will fall within the formula."
- "Do not try bending or breaking the rules until you understand them."

## On Offers
- "You really have to put your money where your mouth is."
- "The only way to cut through the noise, the constant torrent of BS, is to have some amazing offer that sounds kind of almost too good to be true."
- "No, you're not working for free, but you do have to offer a guarantee. That is just how it works in any sort of cold outbound nowadays."
- "Why not have a guarantee? It's just free money on the table."
- "The most important thing: most people believe you have to use pre-existing super high quality winning email templates. You don't need the template. What you need is the system."
- "A template that you use once may work for a week, a month, a year — but eventually it'll stop working. A system has a much longer lifespan."
- "Strategy is the system. The tactic is the template. And templates don't work. Focus on higher level strategy."

## On the Frame
- "Write like a human. The frame of cold outbound is one-to-one comms."
- "The person on the other end of the line thinks that you wrote that email just for them."
- "Short, casual, slightly imperfect, like a real person having a conversation."
- "If a friend saw you typing this to them, would they think it was a personal message or a mass email?"

## On AI in Copy
- "I rarely if at all use AI in my copywriting these days."
- "People that use AI really intensely in the process tend to suck."
- "AI will happily write copy at the 2-weeks-of-experience level but really struggles with writing copy up at the expert level."
- "You need to get to this point on your own. Write all your emails on your own. And then and only then would I even consider spot-check use of AI worthwhile."

## On Subject Lines
- "Subject lines do not sell. If you find yourself selling at all in the subject line, you're doing something wrong."
- "The idea is plausible deniability. You want to give them enough information to pique their curiosity, but not enough that you can answer the question without them clicking."

## On Follow-Ups
- "Just having one follow-up is going to put you ahead of 99.9% of people."
- "Real humans don't send newsletter-style follow-ups. They say 'Hey Pete, quick ping.'"

## On Iteration
- "Your cold emails rarely rock right away. They usually suck."
- "No matter what, always iterate. Always have multiple variants going simultaneously."
- "More volume solves the issues of better strategy and statistics."

## On Cold Reading
- "Cold reading is a set of psychological techniques used to convince someone that you know them intimately, even if you've never met them before."
- "Every human being on planet Earth is probably quiet initially and then grows more comfortable. But most people lack the ability to realize they are a representative sample of the whole population because we all think we're special."

## On Social Proof
- "Who you ARE is not who you've WORKED WITH. 'I'm a thumbnail designer' is weak as hell."
- "Your results should always be in the context of the person you are considering talking to."

---

*Agency OS Cold Email Framework v2.0 | Built from Nick Saraev's 2026 Cold Email Copywriting & Outreach Course | SabboOS*
