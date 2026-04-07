# Nick Saraev — Claude Computer Use Framework

<!-- Last Updated: 2026-03-26 -->
<!-- Source: https://www.youtube.com/watch?v=2u93VTYvG5U -->

## Overview

8 economically valuable use cases for Claude Computer Use (not toy demos). Core insight: Computer Use lets you automate anything you'd do with a mouse and keyboard — bypassing API restrictions, platform locks, and browser automation detection.

## Setup Requirements

1. **Claude Desktop App** → "Cowork" tab
2. **Settings** → Enable both **Browser Use** and **Computer Use**
3. **Min Browser** (`minbrowser.org`) — free, open source, NOT on Anthropic's blocklist
   - Anthropic blocks: Chrome, Safari, Edge, Firefox
   - Min gives Claude full read/write access to any website
4. **Prompt prefix**: Always prepend "with computer use" to force screen control (otherwise Claude defaults to API calls)

## How It Works

Claude takes screenshot → identifies UI elements → controls mouse/keyboard → takes another screenshot → loops. Same interface a human uses. You can jump in and make adjustments mid-task without breaking it.

## 8 Use Cases

### 1. Social Media Outreach (LinkedIn, IG, X, Facebook, TikTok)
- Log into platform in Min Browser
- Give Claude a list of leads or a search term
- Provide an icebreaker template with variables: `"Hey {first_name}, saw {casual_company_name} and I think we'd vibe quite a bit given our interests"`
- Claude clicks through profiles, sends personalized connection requests/DMs
- **Key**: Respect platform outreach limits. Don't send 5 quadrillion messages.
- **Why it works**: Browser fingerprint looks human, no API detection

### 2. Social Media Scraping → Content Calendar
- Prompt: "Scrape my LinkedIn feed for 10 posts about {topic}, save trending ones to a file"
- Claude scrolls feed, takes screenshots, saves text to local file
- Use the scraped content for: trending news, parasitic content, content calendar ideas
- Can also right-click save images

### 3. Contact Form Filling (Agency Outreach)
- Feed a list of URLs with contact forms (dentists, agencies, prospects)
- Claude opens each URL in Min, fills out every field, handles dynamic inputs (date pickers, dropdowns)
- Fills forms in a human-natural way — mitigates captcha appearance
- **Great for**: Businesses gated behind contact forms with no findable email

### 4. Ad Platform Management (No API Needed)
- Works on Google Ads, Meta Ads, TikTok Ads — all lock down their APIs
- Claude clicks through the dashboard UI like you would
- Prompt: "Click through all {campaign_name} ads, find cost per lead, turn off lowest performers"
- Can use strict SOPs: "Find top 3 performing ads, disable bottom 5"
- **Nick's quote**: "The more important thing is knowing WHAT to automate and having a pre-existing SOP for that"

### 5. YouTube Upload Management
- Upload videos via YouTube's actual UI (not API)
- Avoids API-based reach penalties — platforms restrict auto-uploaded content
- Gets full organic reach benefits since it looks like a real user clicking buttons

### 6. Invoice Compilation
- Navigate to billing pages across services
- Download invoices, organize into local folders
- Same human interface = works on any platform

### 7. Desktop App Automation
- Premiere Pro: identify low waveform points, cut at lowest point, generate/apply captions
- Any GUI app: combination of terminal + GUI commands
- Sky's the limit — any app you can click, Claude can click

### 8. QA Testing (Real User Simulation)
- Prompt: "QA test {url}. Go through entire sign-up flow, try to break it, screenshot every step"
- Unlike browser automation (which runs JavaScript click events), Computer Use actually clicks specific parts of the page
- Catches bugs that programmatic testing misses — buttons not immediately accessible, edge cases in real rendering
- **Nick's bet**: Anthropic's own team has been using this to stress-test their products

## The Anthropic Browser Bypass

Anthropic's blocklist prevents read/write on major browsers. Min Browser is not on the blocklist.
- If Min gets patched: search for other open-source browsers not on the blocklist
- Nick's method: asked Claude Code to find 20 different browsers, tried until one worked

## Key Insights

1. **SOPs > Use Cases** — The businesses that win are the ones with pre-existing SOPs for what to automate
2. **Token intensive** — Computer Use burns tokens (screenshots). Anthropic will optimize over time. For now, Pro Max subscription is cheapest path.
3. **Future vision**: "I foresee a future where we all have 100 Mac Minis where stuff like this is occurring on autopilot all the time"
4. **Browser fingerprinting advantage** — Computer Use looks like a real human to platforms, unlike API/Playwright automation
5. **Humanoid robot analogy** — Computer Use isn't best at any one thing but can do EVERYTHING, like humanoid robots in a human-designed environment

## Application to Our System

### Setter Bot (from IG reel)
Same approach — Claude Desktop Cowork + Min Browser + ManyChat/IG web interface. Setter bot brain provides the qualifying questions and stage progression, Claude drives the browser.

### Two Implementation Paths

| Path | How | Cost | Tradeoff |
|---|---|---|---|
| **Claude Desktop Cowork** | Min Browser, enable computer use, run in Cowork tab | ~$200/mo (Pro Max) | Cheap but needs Mac running, semi-supervised |
| **Claude API + VM** | Custom agent loop with screenshot API, run on VPS | ~$50-150/day API | Fully autonomous, expensive, 24/7 |

### What We Already Have That Maps
- `directives/` = SOPs (Nick says SOPs are the key differentiator)
- `bots/sales-manager/` = objection handling, NEPQ frameworks
- `execution/meta_ads_client.py` = ad management (API version — Computer Use could replace)
- `execution/extract_brand_voice.py` = voice guidelines for outreach
- Playwright stack = fallback for deterministic tasks (cheaper than Computer Use)
