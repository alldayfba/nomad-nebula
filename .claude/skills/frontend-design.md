---
name: frontend-design
description: Create distinctive, production-grade frontend interfaces with high design quality. Avoids generic AI aesthetics. Uses shadcn MCP + magic dry MCP when available.
trigger: when user says "build ui", "build component", "build page", "design this", "create interface", "frontend for", "make a landing page", "build a dashboard", "build a form", "build a modal", "make it look good", "redesign this"
tools: [Bash, Read, Write, Edit, Glob, Grep, WebFetch, Agent]
---

# Frontend Design

## Directive
Read `directives/frontend-design-sop.md` for the full design SOP before proceeding.

## Goal
Build production-grade, visually distinctive frontend interfaces — components, pages, or full apps — that avoid generic AI aesthetics and commit to a clear, intentional design direction.

## MCPs (use when available)
- **shadcn MCP** — scaffold shadcn/ui components instead of writing from scratch
- **magic dry MCP** — DRY component generation; reuse before creating

## Inputs
| Input | Required | Default |
|---|---|---|
| what_to_build | Yes | — (component, page, app, or feature description) |
| framework | No | auto-detect from codebase (React/Next.js/HTML) |
| aesthetic_direction | No | auto-decide (commit boldly — see SOP) |
| existing_files | No | auto-scan codebase for context |
| output_path | No | inferred from project structure |

Extract from user's message. If `what_to_build` is vague and this is a client deliverable, ask 2-3 clarifying questions before proceeding.

## Execution

This skill is agent-driven — no Python script needed.

### Step 1 — Context Scan
Read the existing codebase to understand:
- Framework (React, Next.js, Vue, vanilla HTML)
- Existing design system (CSS vars, Tailwind config, component library)
- Adjacent components for visual consistency reference
- Color palette, font choices already in use

### Step 2 — Design Commit
Before writing a single line of code, internally commit to:
1. **Aesthetic direction** — pick one extreme and name it (e.g., "editorial dark with editorial serif + amber accent")
2. **Typography** — choose a distinctive display + body font pairing (NO Inter, Roboto, Arial, Space Grotesk as primary)
3. **Color** — dominant color + sharp accent + background treatment
4. **Layout** — identify the spatial motif (asymmetry, overlap, diagonal, grid-break, etc.)
5. **The one unforgettable thing** — the single detail that makes this design stick

### Step 3 — Build
Implement working code that is:
- Production-ready and functional
- Consistent with design commit from Step 2
- Animated where it matters (page load stagger, hover states, scroll triggers)
- Refined in micro-details (spacing, shadow, border-radius, transition timing)

Use shadcn MCP to scaffold base components → customize aggressively.
Use magic dry MCP to reuse existing patterns from the codebase.

### Step 4 — Self-Review
Before returning, read the output as a skeptical creative director:
- Does it avoid the generic AI slop checklist? (purple gradients, Inter font, predictable card layouts)
- Is the aesthetic direction executed with precision, not timidity?
- Are animations purposeful — not decorative noise?
- Would this be remembered?

If it fails review, revise until it passes.

## Output
- Modified or new file(s) at `output_path`
- Console: aesthetic direction chosen, fonts used, key design decision rationale (1-2 sentences)

## Design Anti-Patterns (NEVER)
- Inter / Roboto / Arial / System-UI / Space Grotesk as primary font
- Purple-on-white gradient hero
- Generic card grid with drop shadow
- "AI blue" (#3B82F6) as dominant accent
- Equal visual weight across all elements
- Animations on every element (scatter = noise)
- Solid color backgrounds on complex UIs

## Self-Annealing
If build fails:
1. If shadcn MCP unavailable — build components manually, same design quality
2. If framework unclear — default to vanilla HTML/CSS/JS (zero dependencies)
3. If conflicting design system — match existing tokens, elevate within constraints
4. Log unexpected constraints in `directives/frontend-design-sop.md` Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
