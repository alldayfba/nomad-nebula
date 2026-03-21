# Frontend Design SOP

> Skill: `.claude/skills/frontend-design.md` | Owner: WebBuild Agent

---

## Purpose

Build production-grade frontend interfaces that are visually distinctive, aesthetically intentional, and avoid generic "AI slop" patterns. Every build commits to a clear creative direction and executes it with precision.

---

## When to Use

Invoked by `/frontend-design` or when the user asks to build any UI: component, page, form, dashboard, landing page, or application.

---

## Tools

- **shadcn MCP** — scaffold shadcn/ui components (use first, customize aggressively)
- **magic dry MCP** — DRY generation; reuse before creating
- **Claude Agent tool** — spawn reviewer for design QA on complex builds
- **WebFetch** — pull design reference or inspect live URLs the user provides

---

## Design Framework

### Phase 1 — Intake & Context Scan

Before designing anything:
1. Identify the **framework** (React/Next.js/Vue/HTML) from the codebase
2. Read **existing design tokens**: CSS vars, Tailwind config, globals.css
3. Scan **adjacent components** for visual consistency cues
4. Understand the **audience and purpose** — who sees this, what do they do with it

### Phase 2 — Aesthetic Commit (NON-NEGOTIABLE)

Pick a direction and commit. Hedging = mediocrity. Options include but aren't limited to:

| Aesthetic | Character |
|---|---|
| Editorial Dark | Serif headline, near-black bg, amber/gold accent, tight grid |
| Brutalist Raw | Heavy borders, stark typography, zero decoration, high contrast |
| Luxury Refined | Cream/bone palette, serif + light weight mono, generous space |
| Retro-Futuristic | Monospace, scan-lines, phosphor green/amber on near-black |
| Organic/Natural | Muted earth tones, rounded forms, natural texture overlays |
| Industrial | High density, data-forward, utility aesthetic, cool grays |
| Maximalist Editorial | Many layers, mixed type scales, diagonal flow, rich texture |
| Playful/Toy-like | Bold primaries, chunky rounded corners, spring animations |
| Soft Pastel | Dusty pastels, light mode, thin type, whisper shadows |
| Art Deco | Geometric symmetry, gold/black, decorative borders, caps |

**The commit includes:**
- Named aesthetic direction
- Display font + body font (specific Google Fonts or system alternatives)
- Dominant color + accent color + background treatment
- Spatial motif (how elements are arranged in space)
- The one unforgettable detail

### Phase 3 — Typography Rules

**Font Pairing Principles:**
- Display font: characterful, unexpected, memorable
- Body font: highly readable, complements display
- Avoid: Inter, Roboto, Arial, Space Grotesk, Poppins as primary display

**Pairing Ideas (not exhaustive — vary constantly):**
- Playfair Display + DM Serif Text
- Cabinet Grotesk + Fraunces
- Clash Display + Satoshi
- Instrument Serif + JetBrains Mono
- Anybody + Epilogue
- Bebas Neue + Source Serif 4
- Cormorant Garamond + Libre Baskerville

**Implementation:**
```css
/* Load from Google Fonts or Fontsource — never skip this */
@import url('https://fonts.googleapis.com/css2?family=...');
```

### Phase 4 — Color & Atmosphere

**Palette Construction:**
1. Pick a dominant (60%) — this sets the mood
2. Pick an accent (10%) — sharp, punchy, memorable
3. Background treatment (30%) — never just flat `#fff` or `#000`

**Background Techniques:**
```css
/* Noise texture overlay */
background-image: url("data:image/svg+xml,...");

/* Gradient mesh */
background: radial-gradient(at 40% 20%, hsl(28, 100%, 74%) 0px, transparent 50%),
            radial-gradient(at 80% 0%, hsl(189, 100%, 56%) 0px, transparent 50%);

/* Grain overlay (pseudo-element) */
.grain::after {
  content: '';
  background-image: url("data:image/svg+xml,...");
  opacity: 0.04;
  pointer-events: none;
}
```

### Phase 5 — Motion Principles

**High-impact, low-noise:**
- One orchestrated page load: staggered element reveals (`animation-delay`)
- Hover states that surprise (not just opacity changes)
- Scroll-triggered reveals (IntersectionObserver or CSS `@keyframes` with class toggle)
- Transitions: `cubic-bezier` easing, never `linear` for UI

**Avoid:**
- Animations on every element
- Simultaneous animations (visual noise)
- Long durations (>400ms for micro-interactions)
- Animations that delay interaction

**CSS-first for HTML, Motion library for React:**
```tsx
// React — Motion (Framer Motion)
import { motion, AnimatePresence } from 'motion/react'

// HTML/CSS — keyframes + animation-delay
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
```

### Phase 6 — Spatial Composition

**Memorable layouts break the grid:**
- Asymmetry: unequal column splits (e.g., 40/60, 30/70)
- Overlap: elements bleeding across section boundaries
- Diagonal flow: angled dividers, skewed containers
- Grid-breaking: pull-quote or hero element escaping its container
- Negative space as design element, not emptiness

**Avoid:**
- Centered everything
- Equal-weight card grids
- Predictable 3-column feature grids
- Hero → Features → CTA → Footer (without variation)

---

## Execution Checklist

Before returning any build, verify:

- [ ] Aesthetic direction named and executed with precision
- [ ] Fonts are distinctive — not on the banned list
- [ ] Background is treated — not a flat color
- [ ] At least one animation exists (page load or hover)
- [ ] Layout has spatial tension — not centered/symmetric by default
- [ ] Code is production-ready (no TODOs, no placeholder text)
- [ ] shadcn components used and customized (if available)
- [ ] Self-review passed: would this be remembered?

---

## Anti-Patterns (BANNED)

| Anti-pattern | Why |
|---|---|
| Inter as primary font | Ubiquitous, zero character |
| Purple gradient hero | Overused AI default |
| `#3B82F6` (Tailwind blue-500) as dominant accent | "AI blue" — immediate signal of lazy defaults |
| Equal visual weight everywhere | No hierarchy, nothing to look at |
| Generic card with box-shadow | Lazy component pattern |
| System font stack | No typographic character |
| Solid `#ffffff` or `#000000` backgrounds | Dead, flat, no atmosphere |
| Animations on every element | Visual chaos, not design |

---

## Known Issues

*(append as encountered)*

---

## Changelog

- 2026-03-16 — Initial SOP created from Sabbo's frontend-design skill definition
