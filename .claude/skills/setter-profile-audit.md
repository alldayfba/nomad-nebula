---
name: setter-profile-audit
description: Audit IG profile against Nik Setting's funnel framework — bio, highlights, CTA, content mix optimization
trigger: when user says "setter profile audit", "audit my IG", "optimize my profile", "profile funnel"
tools: [Bash, Read, Grep, WebSearch]
---

# Setter Profile Audit

## Directive
Read `directives/setter-sdr-sop.md` and `bots/creators/nik-setting-brain.md` for context.

## Goal
Analyze Sabbo's Instagram profile against proven high-converting profile funnel frameworks and generate specific, actionable recommendations.

## Inputs
| Input | Required | Default |
|---|---|---|
| handle | No | allday.fba |

## Execution

1. Read Nik Setting's profile funnel framework:

```bash
cat bots/creators/nik-setting-brain.md | head -200
```

2. Read the current setter identity for brand voice reference:

```bash
cat bots/setter/identity.md
```

3. Analyze the profile against these criteria:

**Profile Funnel Checklist (Nik Setting Framework):**

| Element | What to Check | Conversion Impact |
|---------|--------------|-------------------|
| **Profile Picture** | Clear face, professional, recognizable at small size | First impression — 2-3 seconds |
| **Name Field** | Keyword-rich (not just name — include what you do) | Searchability + context |
| **Bio Line 1** | Hook / authority statement | Stops the scroll |
| **Bio Line 2** | What you help people do (outcome-focused) | Qualifies the visitor |
| **Bio Line 3** | Social proof or credibility | Builds trust |
| **CTA Line** | Clear call to action (DM me "KEYWORD" or link) | Conversion trigger |
| **Link** | Single clear destination (not linktree with 10 options) | Reduces friction |
| **Highlights** | Story highlights as mini sales pages (Results, About, FAQ, Process) | Pre-sells before DM |
| **Content Mix** | 70% value / 20% social proof / 10% CTA posts | Feeds the funnel |
| **Pinned Posts** | Top 3 posts = best results, best hook, best CTA | First content seen |
| **Recent Reels** | Hooks in first 1-3 seconds, face visible, text overlay | Drives new followers |

4. For each element, rate 1-10 and provide specific improvement recommendations.

## Output

**Profile Audit Report:**
- Overall score (X/100)
- Element-by-element rating with specific fix
- Priority order (highest impact fixes first)
- Example rewrites for bio lines
- Highlight structure recommendation
- Content mix analysis with ratio

## Important Notes
- This is a one-time optimization (run once, implement, then re-audit monthly)
- The profile IS the funnel — every new follower sees it before responding to DMs
- A 10% improvement in profile conversion = 10% more replies from the same DM volume
- Reference Nik Setting's profile as a benchmark (he converts at scale)

## Self-Annealing
If Nik Setting brain file is outdated (>30 days), run a freshness check first per the Creator Intelligence Freshness Protocol.
