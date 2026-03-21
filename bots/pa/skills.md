# PA Bot — Skills
> bots/pa/skills.md | Version 1.0

---

## Web Research

### Topic Deep-Dive
**Trigger:** "research [X]", "look up [X]", "what is [X]", "tell me about [X]"
**Tool:** WebSearch → WebFetch for sources
**Output:** 2-3 sentence summary, key facts, sources, recommendation if applicable

### Product Research
**Trigger:** "find me a [product]", "best [X] under $[Y]", "compare [A] vs [B]"
**Tool:** WebSearch (Amazon, Google Shopping, review sites — Wirecutter, RTINGS, Reddit)
**Output:** Top 3 options with price, key specs, pros/cons, link, recommendation

### Person Research
**Trigger:** "who is [name]", "prep for call with [name]"
**Tool:** WebSearch → LinkedIn, company website, Twitter/X, news
**Output:** Background, company, role, recent activity, context for why they matter

### Competitor / Market Research
**Trigger:** "research [competitor/market]", "how does [X] compare to us"
**Tool:** WebSearch → structured analysis
**Output:** Overview, positioning, pricing, strengths, weaknesses, what matters for Sabbo

---

## Memory Retrieval

### Surface Known Context
**Trigger:** "surface [topic] from memory", "what do I know about [X]", "recall [X]"
**Script:** `PYTHONPATH=/Users/Shared/antigravity/projects/nomad-nebula python3 execution/memory_recall.py --query "[topic]" --limit 5`
**Output:** Relevant memories ranked by recency + relevance

### Preference Lookup (auto — runs before every research task)
**Trigger:** Automatic — runs before presenting any options
**Script:** `python3 execution/memory_recall.py --query "[category] preferences" --type preference --limit 3`
**Output:** Filters options against known preferences before presenting

---

## Purchasing Research

### Amazon Product Search
**Trigger:** "Amazon order [product]", "find [product] on Amazon"
**Tool:** WebSearch → Amazon.com product pages
**Output:** Top 2-3 listings with price, rating, review count, link — ready for Sabbo to confirm

### Price Comparison
**Trigger:** "best price for [product]"
**Tool:** WebSearch across Amazon, Google Shopping, manufacturer site, relevant retailers
**Output:** Price table — lowest to highest with notes on condition/warranty/shipping

---

## Travel Research

### Flight Search
**Trigger:** "find flights [origin] to [destination]", "flights to [city] [dates]"
**Tool:** WebSearch → Google Flights, Kayak, Skyscanner
**Output:** Top 3 options by price/convenience — airline, times, stops, price, link
**Preferences applied:** Check memory.md for known airline preferences, seat preferences, layover tolerance

### Hotel Search
**Trigger:** "find a hotel in [city]", "hotel in [city] [dates]"
**Tool:** WebSearch → Google Hotels, Booking.com, Hotels.com
**Output:** Top 3 options — name, nightly rate, key amenities, distance to context (meeting, city center), link
**Preferences applied:** Check memory.md for known hotel type preferences (boutique vs chain, amenities)

### Airbnb Search
**Trigger:** "find an Airbnb in [city]", "Airbnb [city] [dates]"
**Tool:** WebFetch → Airbnb.com search results
**Output:** Top 3 options — name, nightly rate, bedrooms, rating, review count, link

### Full Trip Planning
**Trigger:** "plan a trip to [destination] [dates]"
**Tool:** WebSearch (flights + hotels + activities in sequence)
**Output:** Complete trip overview — flights, accommodation, estimated total cost, key logistics

---

## Scheduling & Calendar

### Draft Calendar Block
**Trigger:** "schedule [X] with [person]", "block time for [X]"
**Output:** Calendar entry draft — title, date/time, duration, description, notes for Sabbo to add

### Meeting Prep
**Trigger:** "prep for [meeting] with [person/company]"
**Tool:** WebSearch (person/company research) + memory_recall.py
**Output:** Background brief — who they are, what they want, agenda draft, 3-5 key questions to ask

### Travel Logistics
**Trigger:** "prep trip to [destination]"
**Output:** Pre-trip checklist — flight confirmation, hotel check-in details, key addresses, local transport options

---

## Reminders & Tracking

### Add Reminder
**Trigger:** "remind me [X]", "add reminder", "track [bill/renewal/appointment]"
**Script:** `python /Users/Shared/antigravity/tools/deadlines.py add-deadline --title "[title]" --date "YYYY-MM-DD" --notes "[context]"`
**Output:** Confirmation with reminder details

### Check Upcoming
**Trigger:** "what are my reminders", "what's coming up", "any upcoming bills"
**Script:** `python /Users/Shared/antigravity/tools/deadlines.py quick`
**Output:** All items due in next 7 days, flagging anything overdue or < 48 hours

### Add Renewal Tracking
**Trigger:** "renewing [subscription/service] on [date]"
**Script:** deadlines.py add-deadline with category=renewal
**Output:** Confirmation + check for other renewals in same 30-day window

---

## Drafting

### Personal Email
**Trigger:** "draft email to [person/company] about [topic]"
**Output:** Subject line + body in Sabbo's voice — direct, no fluff, clear ask or context
**Format:** Ready to send with ACTION NEEDED line

### Message / DM
**Trigger:** "draft message to [person] about [topic]"
**Output:** Short message — max 5 sentences unless context requires more

### Response Draft
**Trigger:** "respond to [this message/email]"
**Input:** Paste the message
**Output:** Draft response appropriate to tone and context

### Legal-Adjacent Drafts (non-legal-advice)
**Trigger:** "draft a letter to [vendor/landlord/company] about [dispute/request]"
**Output:** Professional letter stating position clearly — flag to consult a lawyer if stakes are high

---

## Information Retrieval

### Quick Lookup
**Trigger:** "what is [X]", "how does [X] work", "define [X]"
**Tool:** WebSearch
**Output:** 2-4 sentence answer, source noted, no padding

### Fact Check
**Trigger:** "is it true that [X]", "verify [claim]"
**Tool:** WebSearch
**Output:** Confirmed / Unconfirmed / Nuanced — with source

---

*PA Bot Skills v1.0 — 2026-03-16*
