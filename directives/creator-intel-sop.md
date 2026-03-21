# Creator Intelligence SOP
> directives/creator-intel-sop.md | Version 1.0

---

## Purpose

Reverse-engineer any content creator's entire intellectual framework from their public content (YouTube + Instagram). Output is a comprehensive "brain doc" — like the Jeremy Haynes VSL SOP — that captures their frameworks, mechanisms, strategies, terminology, philosophy, and specific examples.

Use this when Sabbo says:
- "Scrape [creator name]'s content"
- "Build a brain doc for [creator]"
- "Pull [creator]'s YouTube/Instagram"
- "I want to reference [creator]'s strategy for [project]"

---

## Pipeline Overview

```
Step 1: Scrape                    Step 2: Synthesize
scrape_creator_intel.py    →    build_creator_brain.py

YouTube: yt-dlp + transcript API    Pass 1: Sonnet extracts intel
Instagram: yt-dlp + ffmpeg + Whisper/Claude   Pass 2: Opus synthesizes brain doc

Output: .tmp/creators/{name}-raw.json    Output: bots/creators/{name}-brain.md
```

---

## Inputs

| Input | Required | Notes |
|---|---|---|
| Creator name (slug) | Yes | Lowercase, hyphenated (e.g. `nik-setting`) |
| YouTube channel URL | Yes (or IG) | Full URL: `https://youtube.com/@handle` |
| Instagram handle | Yes (or YT) | Without @ |
| Focus areas | Optional | Comma-separated: "offer positioning, funnel architecture" |
| Max videos | Optional | Default: all. Use for large channels to save time. |

---

## Step 1 — Scrape Content

```bash
source .venv/bin/activate
python execution/scrape_creator_intel.py \
  --name "creator-slug" \
  --youtube "https://youtube.com/@channel" \
  --instagram "handle" \
  --max-videos 50
```

**What it does:**
- YouTube: Lists all videos via yt-dlp → pulls transcripts via youtube-transcript-api (fallback: yt-dlp auto-subs)
- Instagram: Lists reels via yt-dlp → downloads video → extracts audio (ffmpeg) → transcribes (Whisper API → Claude API fallback)
- Also scrapes Instagram post captions via Playwright

**Output:** `.tmp/creators/{name}-raw.json`

**Flags:**
- `--max-videos N` — Limit YouTube videos (0 = all)
- `--max-reels N` — Limit Instagram reels (default 50)
- `--skip-ig-video` — Only get Instagram captions, skip video download/transcription

**Expected time:**
- YouTube: ~2s per video (transcript API is fast)
- Instagram: ~10-15s per reel (download + transcribe)
- 50 YouTube videos + 30 reels ≈ 8-10 minutes

---

## Step 2 — Build Brain Doc

```bash
python execution/build_creator_brain.py \
  --name "creator-slug" \
  --focus "offer positioning, content strategy"
```

**What it does:**
1. Loads raw transcripts from Step 1
2. Chunks transcripts into batches (~20K tokens each)
3. **Pass 1 (Sonnet):** Extracts frameworks, strategies, terminology, examples, anti-patterns from each chunk
4. **Pass 2 (Opus):** Synthesizes all extractions into a single comprehensive brain doc

**Output:** `bots/creators/{name}-brain.md`

**Flags:**
- `--focus "topics"` — Extra depth on specific areas
- `--extraction-only` — Only run Pass 1, cache results
- `--synthesis-only` — Only run Pass 2 (requires prior extraction)
- `--input path` — Custom input file path

**Expected time:** 2-5 minutes depending on content volume

**API cost estimate:**
- Pass 1: ~$0.05-0.15 per chunk (Sonnet)
- Pass 2: ~$0.50-1.00 (Opus, single call)
- 50 videos ≈ $1-2 total

---

## Brain Doc Structure

The output follows this structure:

1. **Core Philosophy & Beliefs** — Worldview, operating principles
2. **Named Frameworks & Mechanisms** — Every named system with full explanation
3. **Strategies & SOPs** — Step-by-step processes and playbooks
4. **Offer Architecture** — Pricing, packaging, positioning
5. **Buyer Psychology & Sales** — Why people buy, objections, decision-making
6. **Content & Marketing Strategy** — Content approach, distribution, audience building
7. **Case Studies & Examples** — Specific stories with names, numbers, timelines
8. **Anti-Patterns** — What NOT to do, with reasoning
9. **Key Terminology** — Glossary table of their unique terms
10. **Quick Reference** — Top 10-15 takeaways

---

## Quality Bar

A good brain doc lets you:
1. Reference a specific creator framework by name and know exactly how it works
2. Build an offer, VSL, or funnel using their methodology without watching their content
3. Compare two creators' approaches side-by-side
4. Apply their strategies to a different niche or offer

Test: "Can I build a [thing] using only this doc as reference?" If yes, it's good.

---

## File Locations

| File | Purpose |
|---|---|
| `execution/scrape_creator_intel.py` | Scraper (YouTube + Instagram) |
| `execution/build_creator_brain.py` | Synthesizer (raw → brain doc) |
| `.tmp/creators/{name}-raw.json` | Raw scraped data (intermediate) |
| `.tmp/creators/{name}-extractions.json` | Cached extraction passes (intermediate) |
| `bots/creators/{name}-brain.md` | Final brain doc (deliverable) |

---

## Known Limitations

- **Instagram login walls:** yt-dlp may require cookies for some profiles. Playwright fallback handles most public profiles.
- **Videos without captions:** ~10-20% of YouTube videos lack auto-captions. These are skipped with a note.
- **Instagram audio transcription:** Requires either OpenAI API key (for Whisper) or Anthropic API key (for Claude). Claude Haiku is used for cost efficiency.
- **Large channels (500+ videos):** Use `--max-videos` to limit. Full channel scrapes can take 15-20 minutes.
- **Private/age-restricted content:** Cannot be scraped.

---

## Examples

### Quick scrape (YouTube only, limited)
```bash
python execution/scrape_creator_intel.py --name "creator" --youtube "https://youtube.com/@channel" --max-videos 20
python execution/build_creator_brain.py --name "creator"
```

### Full scrape (YouTube + Instagram)
```bash
python execution/scrape_creator_intel.py --name "creator" --youtube "https://youtube.com/@channel" --instagram "handle"
python execution/build_creator_brain.py --name "creator" --focus "offer positioning, sales process"
```

### Re-synthesize with different focus
```bash
python execution/build_creator_brain.py --name "creator" --synthesis-only --focus "content strategy, audience building"
```

---

*Created: 2026-02-28*
