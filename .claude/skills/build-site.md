---
name: build-site
description: Analyze a prospect's web presence and generate a full website deployed live
trigger: when user says "build site", "build website", "website for", "generate site", "deploy site"
tools: [Bash, Read, Write, Edit, Glob, Grep, WebFetch]
---

# Website Builder

## Directive
Read `SabboOS/Agents/WebBuild.md` for the full 4-phase pipeline before proceeding.

## Goal
Analyze a prospect's website/IG presence → extract positioning intelligence → generate a full web asset suite (HTML + Tailwind CSS) → deploy live to Vercel/Netlify/GitHub Pages. One input, full-stack output.

## 4-Phase Pipeline
```
Phase 1: Intelligence Extraction (website + IG analysis)
Phase 2: Copy Generation (homepage, landing page, VSL page, ad copy)
Phase 3: HTML Build (Tailwind CSS, vanilla JS, zero dependencies)
Phase 4: Deploy (Vercel/Netlify/GitHub Pages)
```

## Inputs
| Input | Required | Default |
|---|---|---|
| website_url | Yes (or IG) | — |
| ig_handle | Yes (or website) | — |
| offer_type | No | auto-detected (agency/coaching/ecom/saas/local) |
| deploy | No | false (set to "vercel", "netlify", or "github" to deploy) |

Extract from user's message. At minimum need website URL or IG handle.

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate

# Phase 1: Research prospect
python execution/research_prospect.py \
  --name "{business_name}" \
  --website "{website_url}" \
  --niche "{niche}" \
  --offer "{offer}"

# Phase 3-4: Build + Deploy (WebBuild agent handles HTML generation)
# Output goes to .tmp/webbuild/{brand_slug}/
# Deploy via:
python execution/push_to_github.py --dir .tmp/webbuild/{brand_slug}/ --repo {repo_name}
```

## Output
- `.tmp/webbuild/{brand_slug}/` containing:
  - `index.html` — Homepage
  - `lp.html` — Landing page
  - `vsl.html` — VSL page (if applicable)
  - `ads.html` — Ad copy reference
  - `assets/` — Logo + OG image
  - `positioning.yaml` — Extracted positioning brief
- Live deployment URL (if deploy flag set)

## Design Approach
Use the screenshot iteration loop for design refinement:
1. Generate initial HTML based on positioning intelligence
2. Screenshot the output
3. Compare to reference design or brand aesthetic
4. List differences and iterate
5. Repeat until quality threshold met

## Self-Annealing
If execution fails:
1. If website blocks scraping — use available business info only
2. If deploy fails — check credentials (Vercel CLI token, GitHub token)
3. For Vercel: `npm i -g vercel && vercel --prod`
4. For GitHub Pages: check `execution/push_to_github.py` config
5. Fix the script, update directive Known Issues
6. Log fix in `SabboOS/CHANGELOG.md`
