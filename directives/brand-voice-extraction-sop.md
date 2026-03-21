# Brand Voice Extraction SOP

> Version 1.0 | Based on Kabrin Johal's auto-scrape brand voice pattern

## Purpose

Auto-extract a prospect or client's brand voice from their online presence (YouTube, Instagram, LinkedIn, website) into a structured markdown file. All future outputs (emails, ads, VSLs, audits) then match their voice automatically.

## When to Use

- **Before any Dream 100 outreach** — extract voice before writing personalized assets
- **On client onboarding** — first step of any new client engagement
- **When `/business-audit` is run** — auto-extract voice for personalized audit
- **Whenever outreach agent generates personalized content**

## Execution

```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/extract_brand_voice.py \
    --name "Prospect Name" \
    --website "example.com" \
    --youtube "@handle" \
    --instagram "handle" \
    --linkedin "company/example"
```

At minimum, provide `--name` + one source (website, youtube, instagram, or linkedin).

## Output

Markdown file at `.tmp/brand-voices/{slug}.md` containing:
- Personality & Tone (primary tone, energy, formality, humor)
- Language Patterns (sentence structure, vocabulary, signature phrases)
- Communication Style (opens, closes, storytelling, data usage)
- Content Themes (topics, positioning, audience, unique angle)
- Writing Rules (5 DOs and DON'Ts for matching their voice)
- Example Phrases (3+ sentences in their voice)

## Integration

When generating content for a prospect/client:
1. Check `.tmp/brand-voices/` for existing profile
2. If missing, run extraction first
3. Include brand voice markdown as context in the prompt
4. All outputs should match their voice patterns

## Known Issues

<!-- Append issues discovered during use below this line -->
