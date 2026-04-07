# Browser Automation SOP
> directives/browser-automation-sop.md | Version 1.0

---

## Purpose

Web automation has 3 tiers with distinct trade-offs. This SOP defines when to use each tier and the recommended workflow for scaling from prototype to production. Source: Nick Saraev Advanced Course (2026-04).

---

## The 3 Tiers

| Tier | Method | Speed | Cost | Setup Time | Reliability | Best For |
|------|--------|-------|------|------------|-------------|----------|
| 1 | HTTP Requests | Milliseconds | Cheapest | High (reverse-engineer API) | Fragile (format changes break it) | High-volume, known APIs, stable endpoints |
| 2 | Browser Automation | ~5s/action | Medium | Medium | Good (handles JS rendering) | Any website, prototyping, dynamic content |
| 3 | Computer Use | Very slow | Expensive | None | Low (screenshot-dependent) | One-off desktop tasks, native apps |

---

## Decision Flowchart

```
START: Need to automate a web task
  │
  ├─ Is there a documented API? ──YES──→ Tier 1: HTTP Requests
  │                                       (requests, httpx, aiohttp)
  │
  ├─ Is the website JavaScript-rendered? ──YES──→ Tier 2: Browser Automation
  │                                                (Playwright, Chrome DevTools MCP)
  │
  ├─ Is it a one-off desktop task? ──YES──→ Tier 3: Computer Use
  │                                          (Claude Desktop app)
  │
  ├─ Is anti-detection needed? ──YES──→ Tier 2: Browser Use Platform
  │   (social media, protected sites)        ($100 + credits, 99.9% evasion)
  │
  └─ Default ──→ Tier 2: Playwright (headless Chromium)
```

---

## Tier 1: HTTP Requests

**When to use:**
- API is documented or reverse-engineered
- High volume (100+ requests)
- Speed matters (milliseconds per request)
- Data extraction from static or API-served content

**Our existing tools:**
- `execution/scraper.py` — Google Maps scraping via HTTP
- `execution/run_scraper.py` — CLI wrapper
- `execution/keepa_client.py` — Keepa API (HTTP)
- `execution/meta_ads_client.py` — Meta Marketing API (HTTP)
- BeautifulSoup for HTML parsing
- `requests` / `httpx` for HTTP calls

**Advantages:** Fastest, cheapest, most scalable
**Disadvantages:** Fragile (format changes break it), requires API knowledge, can be blocked

---

## Tier 2: Browser Automation

**When to use:**
- No API available or API is undocumented
- JavaScript-rendered content (SPAs, dynamic pages)
- Prototyping before committing to HTTP
- Form filling, multi-step workflows
- Need to capture screenshots or visual content

**Our existing tools:**
- Playwright (headless Chromium) — primary browser automation
- `execution/multi_retailer_search.py` — multi-retailer scraping via Playwright
- `execution/catalog_scraper.py` — full catalog dumps via Playwright
- `execution/source.py` — FBA sourcing with Playwright fallback
- Chrome DevTools MCP — available in Claude Code for interactive browsing

**Anti-detection option: Browser Use Platform**
- Paid tool ($100 upfront + per-use credits)
- 99.9% bot detection evasion rate
- Best for: Facebook, Instagram, Twitter, LinkedIn scraping
- Undetectable fingerprinting, residential proxy support

**Advantages:** Works with any website, handles JS, no API reverse-engineering
**Disadvantages:** ~5 seconds per action, more tokens, can still be blocked

**Playwright best practices:**
- Always use headless mode for production
- Set realistic user agents and viewport sizes
- Implement rate limiting between requests
- Handle navigation timeouts gracefully
- Use `page.wait_for_selector()` not `time.sleep()`

---

## Tier 3: Computer Use

**When to use:**
- One-off tasks not worth automating properly
- Native desktop app interactions (Finder, System Settings)
- Tasks that span multiple applications
- Quick file organization, renaming

**Tools:** Claude Desktop app (computer use is native)

**Advantages:** Works with anything, zero setup
**Disadvantages:** Very slow (mouse → click → screenshot cycle), very expensive (many tokens), not scalable

---

## Recommended Scaling Workflow

Nick Saraev's production workflow:

```
1. PROTOTYPE with Tier 2 (Playwright or Chrome DevTools MCP)
   - Validate the flow works end-to-end
   - Capture the exact sequence of steps

2. VALIDATE the automation produces correct results
   - Test edge cases, error states, empty results

3. REVERSE-ENGINEER the API (if scaling needed)
   - Open Chrome DevTools Network tab
   - Replay the flow manually, capture API calls
   - Document request/response schemas
   - Build HTTP utility for Claude Code

4. SCALE with Tier 1 (HTTP requests)
   - Implement using documented API calls
   - Add rate limiting, retry logic, error handling
   - Run at volume (100s-1000s of requests)

5. FALLBACK to Browser Use Platform (if blocked)
   - When HTTP gets rate-limited or blocked
   - When anti-detection is required
   - Social media platforms (Facebook, Instagram, Twitter)
```

---

## Rate Limiting & Safety

- **Respect robots.txt** — check before scraping any new domain
- **Rate limit all automation** — minimum 1-2 seconds between requests
- **Rotate user agents** — maintain a list of realistic browser user agents
- **Session management** — don't reuse sessions across different tasks
- **Error handling** — implement exponential backoff on failures
- **Most platforms prohibit automation in ToS** — understand legal implications

---

## Integration with Existing SOPs

| SOP | Tier Used | Notes |
|-----|-----------|-------|
| `lead-gen-sop.md` | Tier 1 (HTTP) + Tier 2 (Playwright fallback) | Google Maps scraping |
| `amazon-sourcing-sop.md` | Tier 1 (Keepa API) + Tier 2 (retailer scraping) | Zero-token-first principle |
| `ads-competitor-research-sop.md` | Tier 1 (Meta Ad Library API) | Public API, no auth needed |
| `catalog-scrape-sop.md` | Tier 2 (Playwright) | Full retailer catalog dumps |
| `dream100-at-scale-sop.md` | Tier 2 (multi-Chrome) | Parallel browser instances |

---

*Last updated: 2026-04-03*
