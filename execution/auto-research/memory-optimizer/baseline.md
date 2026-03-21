# Memory Optimizer — Current Baseline Configuration

## FTS5 Weights
- BM25 base: default SQLite FTS5 weights
- Recency boost: +0.30 (<=7 days), +0.15 (<=30 days), +0.05 (<=90 days)
- Access frequency boost: access_count * 0.02 (capped at 0.20)

## Category Taxonomy
agency, amazon, sourcing, sales, content, technical, agent, client, student, general

## Dedup Strategy
- Title similarity: first 80 chars, case-insensitive
- Content hash: SHA-256 of first 200 chars

## Auto-Categorization Keywords
- sourcing: keepa, asin, fba, amazon, retailer, sourcing, product, wholesale
- agency: agency, client, retainer, growth, ppc, ads, campaign
- sales: prospect, lead, close, pipeline, outreach, call, demo
- technical: script, api, python, bug, error, deploy, code, flask
- agent: bot, agent, directive, sop, training, skill
- content: content, video, youtube, post, reel, thumbnail
- amazon: amazon, fba, listing, bsr, ppc, acos
- client: client, kd-amazon, deliverable
- student: student, coaching, onboard

## Quality Thresholds
- Archive after: 90 days with 0 access and confidence < 0.5
- Confidence decay: 0.01/month for event type, 0.005/month for others

## Current Metrics (auto-updated)
- Baseline score: 43.29
- Last updated: 2026-03-16
