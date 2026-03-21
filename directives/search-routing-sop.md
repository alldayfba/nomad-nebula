# Search Routing SOP
> directives/search-routing-sop.md | Version 1.0

---

## Purpose

Prevent unnecessary web searches that burn tokens and slow down responses. Most knowledge is stable and doesn't need a search. This SOP defines exactly when to search, when to offer, and when to just answer.

---

## The 3-Tier Decision Tree

Before any web search, classify the query:

### Tier 1 — Never Search (Answer from training)

Search adds zero value here. The answer won't be different tomorrow.

- Definitions, concepts, terminology
- How things work (mechanisms, processes, math)
- Historical facts (pre-2024)
- Code syntax, API documentation structure, programming patterns
- Business frameworks (NEPQ, Hormozi pricing, VSL structure)
- Amazon FBA fundamentals (BSR, PPC mechanics, listing optimization)
- General copywriting rules

**Action:** Answer directly. Do not mention that you're answering from training.

---

### Tier 2 — Offer to Search (User decides)

The answer might be slightly stale but is stable enough to be useful without a search. Offer once, then answer.

Use this phrase: *"I can give you the current figures I have — want me to search for the latest?"*

- Pricing for tools, services, platforms (changes annually, not daily)
- Platform-specific rules that update occasionally (Amazon TOS, Meta ad policies)
- Statistics, market size numbers, benchmarks
- Software versions and compatibility
- Competitor information that isn't time-sensitive

**Action:** Answer with your best knowledge, append the offer in one short sentence.

---

### Tier 3 — Immediately Search (No hesitation)

Stale answers here cause real damage.

- Current Amazon product prices, BSR rankings, review counts
- Live inventory or availability status
- News, current events, announcements
- Today's ad performance, market conditions
- Current discount codes, promotions, sale events
- Anything the user prefixes with "right now", "today", "currently", "latest", "is [X] still..."

**Action:** Search first, answer second. Do not fabricate.

---

## Bot-Specific Rules

### Sourcing Bot
- Product price at a retailer → Tier 3 (search immediately via Playwright)
- General sourcing strategy → Tier 1 (never search)
- Platform rule/policy → Tier 2 (offer)

### Amazon Bot
- BSR, listing status, review count → Tier 3
- PPC strategy, indexing mechanics → Tier 1
- Current Amazon fee structure → Tier 2

### Outreach Bot
- Email copywriting principles → Tier 1
- Current deliverability best practices → Tier 2
- Whether a domain is blacklisted → Tier 3

### Content Bot
- Content strategy frameworks → Tier 1
- Platform algorithm preferences → Tier 2
- Trending topics / viral content right now → Tier 3

---

## Cost Impact

| Tier | Search frequency | Token cost |
|---|---|---|
| Tier 1 (never) | 0 | 0 |
| Tier 2 (offer) | ~20% of the time (user says yes) | Low |
| Tier 3 (immediately) | 100% | Moderate |

Wrongly Tier-3'ing a Tier-1 question adds a web search call (~2,000–5,000 tokens) to every answer. Across 50 student interactions/day on Discord, that's meaningful.

---

## LLM Routing

This directive requires no LLM routing — it's a decision rule, not an execution task. The bot implementing it uses whatever model it's already running.

---

## Self-Annealing Notes

If a bot consistently searches for things that are Tier 1, update its identity.md with an explicit "Never search for X" rule.
If a Tier 2 answer turns out to be stale and causes a problem, promote that category to Tier 3.

---

*Last updated: 2026-03-16*
