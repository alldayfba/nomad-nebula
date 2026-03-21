# Sourcing Agent Routing Directive
> directives/sourcing-agent-routing.md | Version 1.0

---

## Purpose

This directive defines exactly how an AI agent (Claude Code, OpenClaw, or any future agent) must process sourcing requests. It exists because agents have a tendency to manually web-search instead of using the pipeline scripts, producing incomplete output (missing ASINs, no fee math, no risk flags).

**This directive is MANDATORY. Read it before processing ANY sourcing request.**

---

## The One Rule

**NEVER manually web-search for products, prices, or Amazon listings. ALWAYS use the pipeline scripts.**

The pipeline (`execution/source.py`) does everything:
- Scrapes 100+ retailers automatically
- Matches products to Amazon ASINs with confidence scoring
- Calculates FBA fees (referral, fulfillment, prep, tax, storage)
- Applies cashback + gift card + coupon stacking
- Scores deals (0-100) with risk flags (IP, hazmat, gating, Amazon-on-listing)
- Outputs standardized JSON + CSV

Manual web searching does NONE of this.

---

## Request Classification

### Step 1: Identify the request type

| Pattern | Type | Example |
|---|---|---|
| "Find profitable [brand] products" | `brand` | "Find profitable Dubble Bubble Easter products" |
| "Source [product name]" | `brand` or `search` | "Source reeses easter eggs" |
| "Find profitable [category]" | `category` | "Find profitable grocery clearance" |
| "What can I source from [retailer]?" | `retailer` | "What can I source from Target clearance?" |
| "Is ASIN [X] worth sourcing?" | `asin` | "Is B08XYZ1234 worth sourcing?" |
| "Check this URL: [url]" | `url` | "Check this URL: walmart.com/browse/clearance" |
| "Find me deals" | `scan` | "Find me deals right now" |
| "Check these ASINs" | `batch` | "Check these ASINs: B08X, B09Y, B10Z" |
| "What is [seller] selling?" | `stalker` | "What's seller A1B2C3 selling?" |
| "Find out-of-stock opportunities" | `oos` | "Find OOS opportunities in Grocery" |
| "Find Amazon flips" | `a2a` | "Find warehouse deals I can flip" |
| "Find price-dropped products" | `finder` | "Find products that dropped 30%+ in price" |

### Step 2: Activate virtual environment

```bash
source /Users/Shared/antigravity/projects/nomad-nebula/.venv-sabbojb/bin/activate
```

### Step 3: Run the command

| Type | Primary Command | Fallback |
|---|---|---|
| `brand` | `python execution/source.py brand "[brand]" --retailers target,walmart,walgreens,cvs,costco` | `python execution/multi_retailer_search.py search --query "[brand] [product]" --max-retailers 15` |
| `search` | `python execution/multi_retailer_search.py search --query "[query]" --max-retailers 10` | `python execution/source.py brand "[query]" --retailers target,walmart,walgreens` |
| `category` | `python execution/source.py category "[category]"` | `python execution/multi_retailer_search.py clearance --category "[category]"` |
| `retailer` | `python execution/source.py retailer [retailer] --section clearance` | — |
| `asin` | `python execution/source.py asin [ASIN]` | `python execution/reverse_sourcing.py --asin [ASIN]` |
| `url` | `python execution/run_sourcing_pipeline.py --url "[url]" --auto-cashback --auto-giftcard` | — |
| `scan` | `python execution/source.py scan --count 30` | `python execution/deal_scanner.py --count 30 --match-amazon` |
| `batch` | `python execution/batch_asin_checker.py --asins [list] --use-keepa` | — |
| `stalker` | `python execution/storefront_stalker.py --seller [ID] --reverse-source` | — |
| `oos` | `python execution/source.py oos --count 30 --max-bsr 100000` | `python execution/oos_opportunity_scanner.py --count 30` |
| `a2a` | `python execution/source.py a2a --type warehouse --count 30` | — |
| `finder` | `python execution/source.py finder --min-drop 30 --max-bsr 100000` | — |

### Step 4: If 0 results, escalate

1. Broaden search: increase `--max-retailers` to 15, try different retailers
2. Switch mode: try `search` instead of `brand`, or try `scan`
3. Relax thresholds: `--min-roi 20 --min-profit 2.0`
4. Only after ALL scripts return empty → tell the user what was tried and why

---

## Output Format

Every product in the response MUST include:

```
| ASIN | Amazon Link | Retailer | Source Link | Buy Cost | Amazon Price | Profit | ROI % | Verdict | Confidence |
```

- **Amazon Link**: Always `https://www.amazon.com/dp/{ASIN}`
- **Source Link**: The actual retail URL where the product can be purchased
- **Profit**: After ALL fees (referral + FBA + prep + tax + storage - cashback - gift card)
- **Confidence**: 0.0-1.0 match confidence score
- **Verdict**: BUY / MAYBE / SKIP with reason

If risk flags exist (IP risk, hazmat, gating, Amazon-on-listing, pack mismatch), list them.

---

## Never Do This

1. **NEVER** use WebSearch/WebFetch to find product prices or Amazon listings
2. **NEVER** guess at FBA fees — the calculator handles this
3. **NEVER** present products without ASINs and Amazon links
4. **NEVER** present products without source/retail links
5. **NEVER** skip the profitability calculation
6. **NEVER** present results without match confidence scores
7. **NEVER** say "check the link for current pricing" — the pipeline gets the price
8. **NEVER** present estimated prices from web search snippets as accurate
9. **NEVER** skip risk flags (IP, hazmat, gating, Amazon-on-listing)

---

## Parameter Defaults by Request Type

| Type | min_roi | min_profit | max_price | max_retailers | auto_cashback | auto_giftcard |
|---|---|---|---|---|---|---|
| brand | 30 | 3.00 | 50 | 10 | yes | yes |
| search | 30 | 3.00 | 50 | 10 | yes | yes |
| category | 30 | 3.00 | 50 | 10 | yes | yes |
| retailer | 25 | 2.50 | 75 | — | yes | yes |
| scan | 30 | 3.00 | 50 | — | yes | yes |
| oos | 30 | 3.00 | 50 | 10 | yes | yes |

---

*Created: 2026-03-13 | Version 1.0*
