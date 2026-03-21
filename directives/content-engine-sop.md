# Content Engine SOP
> directives/content-engine-sop.md | Version 1.0

---

## Purpose

Generate platform-native organic content for both businesses. Supports single-topic generation, multi-week calendars, long-form repurposing, and ICP-driven idea generation. Owned by the content bot.

---

## Trigger

- User says "generate content" or "content calendar" or "repurpose"
- CEO dispatches content-agent for content assets
- Weekly content planning cycle

---

## Script

`execution/content_engine.py`

**Output directory:** `.tmp/content/`
**LLM:** Claude Sonnet 4.6 (via Anthropic API)

---

## Commands

### Generate platform-native content
```bash
python execution/content_engine.py generate --topic "why agencies need systems" --platforms instagram,linkedin --business agency
```

Supported platforms: `instagram` (carousel), `linkedin` (post), `twitter` (thread), `youtube` (script outline), `tiktok` (script), `short-form` (reel script)

### Build a content calendar
```bash
python execution/content_engine.py calendar --weeks 4 --frequency 3 --business agency
```
Outputs JSON calendar with topics, platforms, formats, and hook lines per day.

### Repurpose long-form into short-form
```bash
python execution/content_engine.py repurpose --input .tmp/vsl_script.md --platforms short-form,instagram
```

### Generate topic ideas
```bash
python execution/content_engine.py ideas --business agency --count 10
```
Pulls ICP pain points from OS file, generates angles per topic.

---

## Voice Context

The engine loads voice and ICP context from:
- `SabboOS/Agency_OS.md` — for agency content
- `SabboOS/Amazon_OS.md` — for coaching content

### Agency Voice
Operator, direct, no fluff. Platforms: LinkedIn + Instagram.
Angles: thought leadership, case studies, POV, systems thinking.

### Coaching Voice
Educational, proof-forward. Platforms: Instagram + TikTok + YouTube.
Angles: education, results, behind-the-scenes, transformation stories.

---

## Output Standards

- Every piece opens with a hook in the first line. No soft openers.
- CTA on every piece (follow, DM, link in bio, subscribe)
- Platform-native formatting (carousel slides, thread structure, script timing)
- Files saved to `.tmp/content/{date}_{platform}_{topic_slug}.md`

---

## Integration Points

| System | Connection |
|---|---|
| CEO Agent | Dispatches content-agent when "content assets needed" |
| Content Bot | `bots/content/skills.md` references this engine |
| OS Files | Loads voice context from Agency_OS.md / Amazon_OS.md |
| Training Officer | Grades content output via `grade_agent_output.py` |

---

## Phase Gates (for multi-step content production)

When generating a full content calendar or batch content:

**Phase 1: Research + Planning** — must complete before Phase 2
- Load ICP context from OS files
- Identify trending topics and angles
- Build content calendar structure (topics, platforms, formats)
- Quality gate: every topic tied to a specific ICP pain point or desire

**Phase 2: Content Generation** — must complete before Phase 3. Uses Phase 1 calendar.
- Generate each content piece per the calendar
- Apply platform-native formatting
- Quality gate: every piece has a hook in line 1, CTA present, zero banned AI-tell words

**Phase 3: Review + Schedule**
- QC all content against voice context
- Flag any pieces that sound generic for rewrite
- Output final batch to `.tmp/content/`

---

## Self-Annealing

- Track which content types get best engagement → prefer those formats
- If generation fails: check API key, ensure OS file exists
- Store top-performing content in `bots/content/memory.md` for future reference

---

*Content Engine SOP v1.0 — 2026-02-21*
