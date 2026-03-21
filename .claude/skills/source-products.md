---
name: source-products
description: Amazon FBA product sourcing — brand search, category browse, clearance scan, ASIN lookup
trigger: when user says "find products", "source", "find deals", "sourcing", "what can I source", "find profitable"
tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Amazon FBA Product Sourcing

## Directive
Read `directives/amazon-sourcing-sop.md` for the full SOP before proceeding. This is the most complex directive (930+ lines).

## Goal
Automate online arbitrage product sourcing using zero-token-first approach: scrape retailers free via Playwright, verify best candidates on Amazon via Keepa.

## CRITICAL RULES
1. **NEVER manually web-search for products** — no WebSearch, no WebFetch for product prices. The pipeline scripts handle everything.
2. **Classify the request** → run the right command (see routing table below)

## Request Routing Table

| User Says | Mode | Command |
|---|---|---|
| "Find profitable [brand] products" | brand | `source.py brand "[brand]" --retailers target,walmart,walgreens,cvs,costco` |
| "Find profitable [category]" | category | `source.py category "[category]"` |
| "Source [product name]" | brand | `source.py brand "[product]" --retailers target,walmart,walgreens` |
| "What can I source from [retailer]?" | retailer | `source.py retailer [retailer] --section clearance` |
| "Is ASIN [X] worth it?" | asin | `source.py asin [ASIN]` |
| "Find me deals right now" | scan | `source.py scan --count 30` |
| "Check this URL: [url]" | pipeline | `run_sourcing_pipeline.py --url "[url]" --auto-cashback --auto-giftcard` |
| "Check these ASINs: [list]" | batch | `batch_asin_checker.py --asins [list] --use-keepa` |
| "What's this seller selling?" | stalker | `storefront_stalker.py --seller [ID] --reverse-source` |
| "Find out-of-stock opportunities" | oos | `source.py oos --count 30` |
| "Find Amazon flip opportunities" | a2a | `source.py a2a --type warehouse --count 30` |
| "Find price-dropped products" | finder | `source.py finder --min-drop 30 --max-bsr 100000` |

## Execution
```bash
cd /Users/Shared/antigravity/projects/nomad-nebula && source .venv/bin/activate
python execution/source.py {mode} {args}
```

## Zero-Token-First Pipeline
1. **Phase A (FREE):** Scrape retailers via Playwright — 0 Keepa tokens
2. **Phase B (CHEAP):** Verify top candidates via Keepa search — 1 token each
3. **Phase C (EXPENSIVE, optional):** Deep-verify top hits with offers — 21 tokens each

Token budget: ~125 tokens per run (within Pro tier's ~400/day).

## Hard Filters (enforced automatically)
- Amazon is a seller on listing → SKIP
- Private label (brand is only seller) → SKIP
- < 2 FBA sellers → SKIP
- < $2.00/unit profit → SKIP
- BSR > 500,000 → SKIP
- Hazmat keywords → SKIP

## Fallback
If first command returns 0 results, read the directive's Rule 3 escalation chain and try alternative modes.

## Self-Annealing
If execution fails:
1. Check Keepa token balance before running expensive queries
2. If retailer scraping fails, check `execution/selector_health_check.py`
3. If Keepa API errors, verify `KEEPA_API_KEY` in `.env`
4. Fix the script, update directive Known Issues
5. Log fix in `SabboOS/CHANGELOG.md`
