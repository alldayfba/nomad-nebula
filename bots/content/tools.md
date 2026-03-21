# Content Bot — Tools
> bots/content/tools.md | Version 2.0

---

## Active Tools

| Tool | Purpose | Status | Invocation |
|---|---|---|---|
| **Content Engine** | Generate platform-native content, calendars, repurpose long-form, generate ideas | **Active** | `python execution/content_engine.py` |
| File system | Read/write content calendar files | Active | Direct file I/O |

### Content Engine Commands

```bash
# Generate content for specific platforms
python execution/content_engine.py generate --topic "topic" --platforms instagram,linkedin --business agency

# Build a multi-week content calendar
python execution/content_engine.py calendar --weeks 4 --frequency 3 --business agency

# Repurpose long-form into short-form variants
python execution/content_engine.py repurpose --input .tmp/vsl_script.md --platforms short-form,instagram

# Generate topic ideas from ICP pain points
python execution/content_engine.py ideas --business agency --count 10
```

**Supported platforms:** instagram, linkedin, twitter, youtube, tiktok, short-form
**Output directory:** `.tmp/content/`
**LLM:** Claude Sonnet 4.6 (via Anthropic API)

---

## Planned Access

| Tool | Purpose | Status |
|---|---|---|
| Instagram (public scrape) | Monitor competitor content performance | Planned |
| TikTok (public scrape) | Trending content and hooks | Planned |
| YouTube Data API | Video performance, trending topics | Planned |

---

## Access Policy

- Read-only on all social platforms
- No login credentials stored
- No publishing access (Sabbo reviews and posts manually)
- Content engine generates drafts only — Sabbo reviews before publishing

---

*Content Bot Tools v2.0 — 2026-02-21*
