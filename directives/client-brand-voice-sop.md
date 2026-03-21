# Client Brand Voice SOP
> directives/client-brand-voice-sop.md | Version 1.0

---

## Purpose

Before a bot can write for a client, it needs to know who that client is. This SOP defines how to build a brand voice file for any client — by scraping their public content, not by guessing.

Kabrin scraped all his clients' YouTube videos, Instagram content, and everything else he could find, then built markdown files from it. Two days of scraping = a bot that writes in their voice.

---

## Trigger

When Sabbo says:
- "Add [client name] to the system"
- "Build a profile for [client]"
- "I need the bot to write for [client]"

---

## Inputs

| Input | Required | Notes |
|---|---|---|
| Client name | Yes | As it will appear in filenames |
| Website URL | Yes (or IG) | Main site |
| Instagram handle | Yes (or website) | Public profile |
| YouTube channel | Optional | If they have one |
| Any existing brand docs | Optional | Style guides, existing copy, etc. |

---

## Process

### Step 1 — Scrape Public Content

```bash
source .venv/bin/activate
python execution/scrape_client_profile.py \
  --name "client-slug" \
  --website "https://example.com" \
  --instagram "handle" \
  --youtube "https://youtube.com/@channel"
```

This script outputs raw scraped content to `.tmp/clients/[client-slug]-raw.json`.

### Step 2 — Build the Brand Voice File

Using the scraped content, populate the client template:

```bash
cp bots/clients/_template.md bots/clients/[client-slug].md
```

Then fill in each section using the scraped data:
- **Brand voice:** Extract recurring phrases, tone, vocabulary from their posts and captions
- **Audience:** Infer from who engages and the language used in comments
- **Proof points:** Pull specific results from their content (numbers, outcomes, testimonials)
- **Funnel:** Map from their website and CTA patterns

### Step 3 — Review With Sabbo

Before using the file for any copy work:
- Share the draft with Sabbo
- Ask: "Does this match how [client] actually talks? Any corrections?"
- Update the file based on feedback

### Step 4 — Store and Reference

The finished file lives at: `bots/clients/[client-slug].md`

When writing for this client, every relevant bot references this file before generating any output.

---

## Quality Bar for Brand Voice Files

A good brand voice file lets the bot write something the client could have written themselves. Test this:

1. Generate a sample social post for the client
2. Send it to Sabbo: "Does this sound like [client]?"
3. If the answer is "not quite," go back to the file and add more examples, vocabulary corrections, or tone notes
4. Repeat until Sabbo says "yes, that sounds right"

---

## Output

- Raw scraped data: `.tmp/clients/[client-slug]-raw.json`
- Brand voice file: `bots/clients/[client-slug].md`
- Sample post (for quality check): generated on request

---

## Known Issues

- Instagram requires public profile — private accounts can't be scraped
- YouTube transcript extraction varies by channel settings
- If a client has very little public content, ask Sabbo to share internal docs instead

## Related: Creator Intelligence Pipeline

For deep reverse-engineering of a creator's frameworks, strategies, and philosophy (not just brand voice), use the **Creator Intelligence SOP**: `directives/creator-intel-sop.md`

That pipeline pulls ALL video transcripts (YouTube + Instagram Reels) and synthesizes them into a comprehensive brain doc — like the Jeremy Haynes VSL SOP. Use it when you need to reference a creator's full methodology, not just their voice.

---

*Last updated: 2026-02-20*
