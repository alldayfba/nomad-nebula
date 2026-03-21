# Amazon FBA Product Sourcing SOP
> directives/amazon-sourcing-sop.md | Version 7.0

---

## Purpose

Automate online arbitrage (OA) product sourcing using a zero-token-first approach: scrape retailers for free via Playwright, then verify only the best candidates on Amazon via Keepa. Supports brand-specific search, category browse, retailer clearance scan, and single-ASIN reverse sourcing.

---

## Primary CLI — `execution/source.py` (v6.0)

**This is the main entry point for all sourcing.** Use this instead of individual scripts.

```bash
# Brand search (zero-token-first)
python execution/source.py brand "Jellycat" --retailers target,walgreens
python execution/source.py brand "CeraVe" --retailers target --max 30

# Category browse
python execution/source.py category "toys" --subcategory "plush"
python execution/source.py category "beauty" --retailers target

# Retailer clearance scan
python execution/source.py retailer target --section clearance
python execution/source.py retailer target --brand "Crest"

# Multi-source scan (clearance + deal sites)
python execution/source.py scan --count 20

# Single ASIN reverse lookup
python execution/source.py asin B08XYZ1234
```

### Zero-Token-First Principle

1. **Phase A (FREE):** Scrape retailers via Playwright — 0 Keepa tokens
2. **Phase B (CHEAP):** Verify top candidates via Keepa search — 1 token each
3. **Phase C (EXPENSIVE, optional):** Deep-verify top hits with offers — 21 tokens each

Token budget per run: ~125 tokens (well within Pro tier's ~400/day).

---

## Hard Filter Rules (Enforced BEFORE output)

| Filter | Rule | Behavior |
|---|---|---|
| **Amazon on listing** | Amazon is a seller on the listing | SKIP — unless Amazon's price is >15% above Buy Box |
| **Private label** | Brand is only seller (3-tier detection) | SKIP — always |
| **FBA sellers** | < 2 FBA sellers | SKIP — always |
| **Min profit** | < $2.00/unit after ALL fees | SKIP — always |
| **BSR** | > 500,000 | SKIP — too slow to sell |
| **Hazmat** | Product name contains hazmat keywords | SKIP — always |
| **Pack size mismatch** | Retail and Amazon pack counts differ | FLAG with warning, show pack info |

---

## Trigger

Run when user:
- Says "find me products" / "find [brand]" / "source [category]" → use `source.py`
- **Product search**: Types a product name in the sourcing UI → searches 5-15 smart-routed retailers
- **URL source**: Pastes a retail URL into the sourcing UI at `http://localhost:5050/sourcing`
- **Clearance scan**: Clicks "Clearance Scan" in the sourcing UI → scans clearance pages across retailers
- Sends a `source_products` task via watch_inbox
- Runs any CLI command listed above
- Scheduled sourcing fires: `python execution/scheduled_sourcing.py run-due`

---

## Agent Routing Rules (MANDATORY)

**THIS SECTION IS NON-NEGOTIABLE. Every AI agent (Claude Code, OpenClaw, or any future agent) MUST follow these rules when processing ANY sourcing request. Violation = broken output.**

### Rule 1: NEVER manually web-search for products

Do NOT use WebSearch, WebFetch, or any manual browsing to find product prices, Amazon listings, or retail availability. The pipeline scripts handle all of this automatically with proper matching, fee calculation, and risk analysis. Manual web searches produce garbage output (missing ASINs, no fee math, no match confidence, no risk flags).

### Rule 2: Classify the request → Run the right command

| User says | Mode | Command |
|---|---|---|
| "Find profitable [brand] products" | brand | `python execution/source.py brand "[brand]" --retailers target,walmart,walgreens,cvs,costco` |
| "Find profitable [category]" | category | `python execution/source.py category "[category]"` |
| "Source [product name]" | brand or multi-retailer | `python execution/source.py brand "[product]" --retailers target,walmart,walgreens` OR `python execution/multi_retailer_search.py search --query "[product]" --max-retailers 10` |
| "What can I source from [retailer]?" | retailer | `python execution/source.py retailer [retailer] --section clearance` |
| "Is ASIN [X] worth it?" | asin | `python execution/source.py asin [ASIN]` |
| "Find me deals right now" | scan | `python execution/source.py scan --count 30` |
| "Check this URL: [url]" | pipeline | `python execution/run_sourcing_pipeline.py --url "[url]" --auto-cashback --auto-giftcard` |
| "Check these ASINs: [list]" | batch | `python execution/batch_asin_checker.py --asins [list] --use-keepa` |
| "What's this seller selling?" | stalker | `python execution/storefront_stalker.py --seller [ID] --reverse-source` |
| "Find out-of-stock opportunities" | oos | `python execution/source.py oos --count 30` |
| "Find Amazon flip opportunities" | a2a | `python execution/source.py a2a --type warehouse --count 30` |
| "Find price-dropped products" | finder | `python execution/source.py finder --min-drop 30 --max-bsr 100000` |

### Rule 3: Fallback escalation chain

If the first command returns 0 results:
1. Try broader search: increase `--max-retailers` to 15, try `multi_retailer_search.py` instead of `source.py`
2. Try different mode: switch from `brand` to `category`, or try `scan`
3. Try relaxed thresholds: lower `--min-roi` to 20, `--min-profit` to 2.0
4. **Only after ALL scripts return empty** → inform the user with what was tried and why it failed

### Rule 4: Standardized output format

Every sourcing response MUST include this data for each product:

| Field | Required | Source |
|---|---|---|
| ASIN | Yes | Pipeline output |
| Amazon link | Yes | `https://www.amazon.com/dp/{ASIN}` |
| Amazon price | Yes | Pipeline output |
| Source retailer | Yes | Pipeline output |
| Source link | Yes | Pipeline output (source_url) |
| Buy cost | Yes | Pipeline output |
| Profit per unit | Yes | Pipeline output (after ALL fees) |
| ROI % | Yes | Pipeline output |
| Verdict | Yes | BUY / MAYBE / RESEARCH / SKIP |
| Match confidence | Yes | Pipeline output (0.0-1.0) |
| BSR | If available | Pipeline output |
| FBA seller count | If available | Pipeline output |
| Risk flags | If any | Pipeline output |

**HARD GATE — ENFORCED BY `execution/verify_sourcing_results.py`:**
- If Source link is missing, empty, or "N/A" → verdict MUST be RESEARCH, not BUY/MAYBE
- If Source link domain is not in `retailer_registry.py` whitelist → REJECT
- If Source link domain doesn't match stated retailer → REJECT
- If buy price >= Amazon price → REJECT (not arbitrage)
- If ROI > 1000% → FLAG as suspicious (likely pack mismatch)
- If title similarity < 25% → REJECT (wrong product match)
- Products without verified buy links are RESEARCH leads only — never actionable buys
- This applies to ALL output: CLI, web UI, tables, summaries, deal drops — no exceptions

### Rule 5: Always activate the virtual environment

Before running any sourcing script:
```bash
source /Users/Shared/antigravity/projects/nomad-nebula/.venv-sabbojb/bin/activate
```

See also: `directives/sourcing-agent-routing.md` for the full standalone routing directive.

---

## Inputs

| Field | Required | Default | Description |
|---|---|---|---|
| url | Yes | — | Retail website URL (product page, category page, search results, or clearance page) |
| min_roi | No | 30 | Minimum ROI % to include in results |
| min_profit | No | 3.00 | Minimum profit $ per unit |
| max_price | No | 50.00 | Max retail buy price (limits capital risk per unit) |
| max_products | No | 50 | Max products to scrape from the page |
| cashback_percent | No | 0 | Manual cashback % override |
| coupon_discount | No | 0 | Dollar coupon discount |
| auto_cashback | No | false | Auto-apply estimated retailer cashback rates |
| auto_giftcard | No | false | Auto-apply CardBear gift card discount based on retailer |
| gift_card_discount | No | 0 | Manual gift card discount % override |
| prep_cost | No | auto | Prep cost per unit (auto-estimates by category if not set) |
| tax_state | No | none | State abbreviation for sales tax (e.g. TX, CA) |
| no_storage | No | false | Exclude estimated FBA storage fees from profit calc |

---

## Steps (Forward Sourcing)

1. **Detect retailer** — `execution/retailer_configs.py` maps the URL domain to a selector config
2. **Scrape products** — `execution/scrape_retail_products.py` extracts product data from the URL
3. **Match to Amazon** — `execution/match_amazon_products.py` searches Amazon for each product by UPC or title; extracts FBA seller count, Amazon-on-listing flag, BSR, category
4. **Calculate profitability** — `execution/calculate_fba_profitability.py` computes ROI, fees, profit per unit, competition score, gating/hazmat/IP warnings, multi-pack detection, cashback + gift card stacking, prep costs, sales tax, storage fees, BSR auto-filter (>500K = SKIP), deal score (0-100)
5. **Track in database** — `execution/price_tracker.py` stores results in SQLite, generates alerts for price drops and new BUY products
6. **Filter & rank** — Apply min_roi, min_profit filters; sort by ROI descending
7. **Output** — JSON results + CSV export
8. **Alert** — Send Telegram/email alerts for BUY products if configured

## Steps (Reverse Sourcing)

1. **Get Amazon product details** — Keepa API or Playwright product page
2. **Search retail websites** — Walmart, Target, Home Depot, CVS, Walgreens, Costco
3. **Match titles** — Title similarity scoring between Amazon and retail results
4. **Calculate profitability** — Full fee analysis for each retail source
5. **Rank** — Sort by ROI, present best source

---

## Scripts

| Step | Script | LLM | Time |
|---|---|---|---|
| **PRIMARY CLI** | **`execution/source.py`** | None | ~1-5 min |
| 1-2. Scrape retail | `execution/scrape_retail_products.py` | None | ~30-60s |
| 3. Match Amazon | `execution/match_amazon_products.py` | Haiku 4.5 (fuzzy matching only) | ~2-5 min |
| 4. Calculate profit | `execution/calculate_fba_profitability.py` | None | <1s |
| All (legacy) | `execution/run_sourcing_pipeline.py` | — | ~3-7 min total |
| Reverse source | `execution/reverse_sourcing.py` | None | ~2-4 min |
| Price tracking | `execution/price_tracker.py` | None | <1s |
| Scheduled runs | `execution/scheduled_sourcing.py` | None | varies |
| Keepa client | `execution/keepa_client.py` | None | — |
| Deal scanner | `execution/deal_scanner.py` | None | ~1-5 min |
| Fast grocery | `execution/fast_grocery_scan.py` | None | ~2-5 min |
| Deal hunter | `execution/keepa_deal_hunter.py` | None | ~1-3 min |
| Alerts | `execution/sourcing_alerts.py` | None | <5s |
| Google Sheets | `execution/export_to_sheets.py` | None | ~10s |
| CardBear scrape | `execution/scrape_cardbear.py` | None | ~5s |
| Batch ASIN check | `execution/batch_asin_checker.py` | None | ~1-5 min |
| Storefront stalker | `execution/storefront_stalker.py` | None | ~3-10 min |
| Inventory P&L | `execution/inventory_tracker.py` | None | <1s |

---

## Outputs

- `.tmp/sourcing/{timestamp}-results.json` — Full results with all product data
- `.tmp/sourcing/{timestamp}-results.csv` — Filtered profitable products (BUY + MAYBE)
- `.tmp/sourcing/price_tracker.db` — SQLite database with price history and alerts
- `.tmp/sourcing/bookmarks.json` — Scheduled sourcing bookmark URLs
- Google Sheets "FBA Sourcing Results" — Cloud-based results (via export_to_sheets.py)

### Verdicts

| Verdict | Criteria |
|---|---|
| **BUY** | ROI >= 30% AND profit >= $3.50/unit AND monthly sales >= 30 (if known) |
| **MAYBE** | ROI >= 20% AND profit >= $2/unit |
| **SKIP** | Below thresholds, no match, low confidence, saturated listing, hazmat, or Amazon-on-listing |

### Risk Flags (in profitability output)

| Flag | Meaning |
|---|---|
| `competition_score: SATURATED` | 15+ FBA sellers — avoid |
| `amazon_on_listing: true` | Amazon.com is selling — HARD SKIP unless Amazon price >15% above Buy Box |
| `is_gated: true` | Category requires approval (Grocery, Jewelry, Watches, etc.) |
| `hazmat_risk: true` | Product name contains hazmat keywords (battery, aerosol, etc.) |
| `ip_risk: true` | Product matches known litigious brand (Nike, Apple, LEGO, etc.) |
| `multipack_mismatch: true` | Quantity discrepancy between retail and Amazon listing |

---

## Data Sources (Tiered)

### Tier 0 — Free (always available)
- **Retail scraping** via Playwright — works for all retailers
- **Amazon search** via Playwright — search by product title/UPC, get ASIN + price + seller count
- **FBA fee estimation** via hardcoded fee tables (update quarterly)
- **Sales rank estimation** via category-specific lookup tables with multipliers
- **Cashback estimates** — per-retailer Rakuten cashback rates (approximate)
- **Gift card discounts** — CardBear.com daily scrape for 900+ retailers (auto-applied via `--auto-giftcard`)

### Tier 1 — Keepa API (€49/mo Pro recommended)
- If `KEEPA_API_KEY` is set in `.env`, auto-detected at runtime
- All scripts use centralized `execution/keepa_client.py` (v5.0)
- Correct CSV indices: FBA sellers (34), FBM sellers (35), Buy Box (18), Amazon price (0)
- `offers=20` parameter: returns actual seller list with names for private label detection
- Falls back to Tier 0 scraping if not configured

| Tier | Price | Tokens/min | Lookups/day | Scan speed (20 products) |
|---|---|---|---|---|
| Basic | $19/mo | 5 | ~100 | ~5 min |
| Pro | €49/mo | 20 | ~400 | ~1 min |

---

## Gift Card Discount Layer (CardBear)

**How it works:** CardBear.com aggregates gift card discount rates across 900+ retailers. By buying a discounted gift card before purchasing retail products, the effective buy cost drops further.

**Stacking order:** Raw cost → gift card discount → cashback → coupon = effective buy cost

**Example:** $100 item with 10% gift card + 3% cashback + $5 coupon = $82.30 effective cost (17.7% savings)

**Scripts:**
| Script | Purpose |
|---|---|
| `execution/scrape_cardbear.py scrape` | Daily scrape, stores in SQLite (`price_tracker.db`) |
| `execution/scrape_cardbear.py top --min-discount 10` | View highest current discounts |
| `execution/scrape_cardbear.py history --retailer "Walmart" --days 30` | Discount trend over time |
| `execution/scrape_cardbear.py trigger-sourcing --min-discount 10` | Auto-source from high-discount retailers |

**Pipeline CLI flags:**
- `--auto-giftcard` — Auto-apply CardBear discount based on retailer name
- `--gift-card-discount 8.5` — Manual gift card discount % override

**Cron (daily at 6 AM, before sourcing runs):**
```
0 6 * * * cd ~/Documents/nomad-nebula && .venv/bin/python execution/scrape_cardbear.py scrape 2>> .tmp/sourcing/cron.log
```

**Self-annealing:** If CardBear page structure changes, update `_extract_retailer_json()` in `execution/scrape_cardbear.py`, test with `scrape` subcommand, note fix date here.

---

## Profitability Calculator v3.0

The profitability calculator now includes 5 additional cost/scoring layers beyond basic ROI:

### Prep Costs
FBA prep costs per unit (FNSKU label $0.10, poly bag $0.15, bubble wrap $0.25). Auto-estimated by category — Beauty, Health, and fragile categories get higher prep costs. Override with `--prep-cost 0.50`.

### Sales Tax
State-level sales tax on the retail purchase price. Reduces real profit since tax is an additional cost of goods. Set your home state with `--tax-state TX`.

### Storage Fees
Estimated FBA monthly storage fees based on sales velocity. Fast-moving products (<30 days to sell) pay minimal storage. Slow movers (90+ days) get penalized. Q4 (Oct-Dec) rates are 2.5x higher. Disable with `--no-storage`.

### BSR Auto-Filter
Products with BSR > 500,000 are automatically marked SKIP — too slow to be worth the capital lock-up. Threshold defined as `MAX_BSR_THRESHOLD` in calculator.

### Deal Score (0-100)
Composite score weighted across 5 factors:
- **ROI quality** (25 pts) — higher ROI = higher score
- **Sales velocity** (25 pts) — faster sellers score higher
- **Competition** (20 pts) — fewer FBA sellers = better
- **Risk flags** (15 pts) — penalized for hazmat, gating, IP risk, Amazon-on-listing
- **BSR quality** (15 pts) — lower BSR relative to category = better

Use deal score to prioritize which BUY products to purchase first.

---

## Batch ASIN Checker

Bulk ASIN lookup tool for checking deal group lists. Paste 10-100+ ASINs and get profitability at various buy prices.

```bash
# Check ASINs with specific buy prices
python execution/batch_asin_checker.py --asins B08XYZ1234 B09ABC5678 --buy-prices 5,10,15,20

# Check from file (supports # comments)
python execution/batch_asin_checker.py --file asins.txt --output results.json

# Pipe from clipboard/stdin
pbpaste | python execution/batch_asin_checker.py --stdin

# Use Keepa for faster/more accurate data
python execution/batch_asin_checker.py --file asins.txt --use-keepa
```

Key feature: `find_max_buy_price()` — binary searches for the highest price you can pay and still get a BUY verdict.

---

## Storefront Stalker

Scrape a competitor seller's Amazon storefront to see what they're selling, then reverse-source the best products.

```bash
# Stalk by seller ID or URL
python execution/storefront_stalker.py --seller A1B2C3D4E5F6G7
python execution/storefront_stalker.py --url "https://www.amazon.com/sp?seller=A1B2C3D4E5F6G7"

# Limit products and auto-reverse-source top picks
python execution/storefront_stalker.py --seller A1B2C3D4E5F6G7 --max-products 50 --reverse-source

# Output to file
python execution/storefront_stalker.py --seller A1B2C3D4E5F6G7 --output .tmp/stalker/results.json
```

Scores each product with a demand-weighted deal score (BSR 40%, competition 25%, price 20%, reviews 15%).

---

## Inventory & P&L Tracker

Track actual purchases, shipments, sales, and P&L to measure real hit rate and compare estimated vs actual ROI.

```bash
# Record a purchase
python execution/inventory_tracker.py buy --asin B08XYZ1234 --name "Widget Pro" --qty 10 --cost 12.99 --retailer Walmart --estimated-roi 45

# Mark shipped to FBA
python execution/inventory_tracker.py ship --id 1

# Record sales
python execution/inventory_tracker.py sold --id 1 --units 3 --price 29.99 --fees 8.50

# Import BUY products from a sourcing run (preview first, then --confirm)
python execution/inventory_tracker.py import-buys --results .tmp/sourcing/results.json
python execution/inventory_tracker.py import-buys --results .tmp/sourcing/results.json --confirm

# Reports
python execution/inventory_tracker.py inventory           # Current inventory
python execution/inventory_tracker.py pnl --days 30       # Profit & Loss
python execution/inventory_tracker.py hit-rate --days 90   # % of purchases that sold
python execution/inventory_tracker.py dashboard            # Overall summary
```

Key insight: Compare `estimated_roi` vs actual ROI to calibrate your sourcing accuracy over time.

---

## Supported Retailers

| Retailer | Config Key | Best For | Cashback Est. |
|---|---|---|---|
| Walmart | `walmart.com` | Clearance, rollbacks | ~3% |
| Target | `target.com` | Circle deals, clearance | ~2% |
| Home Depot | `homedepot.com` | Tools, home improvement | ~2% |
| CVS | `cvs.com` | Health & beauty | ~3% |
| Walgreens | `walgreens.com` | Health & beauty | ~3% |
| Costco | `costco.com` | Bulk items | ~1% |
| Any other | `generic` | Common e-commerce selectors | 0% |

---

## Product Criteria (from Pro Sellers Research)

These thresholds are based on research from top FBA sellers (Clips for Miles, Fields of Profit, Jazz Hustles, Dan Buford):

| Metric | Threshold | Source |
|---|---|---|
| ROI | >= 30% (beginners), >= 20% (scaled) | Consensus across all creators |
| Profit per unit | >= $3.50 | Industry standard |
| BSR | Top 1% of category (< 50,000 typical) | Miles, Warner |
| Sales velocity | >= 30 units/month | Warner (Fields of Profit) |
| FBA seller count | 2-15 ideal | Consensus |
| Amazon as seller | AVOID | All creators agree |
| Price range | $15-$70 sweet spot | Industry consensus |

---

## OA Strategy Playbook (Confirmed from VA Sourcing Data — 2026-03)

Patterns confirmed from 295+ product scan entries (Feb Product Scan + IC Approved Products sheet):

### Strategy A: Multi-Pack Arbitrage
Buy single units retail → build multi-pack listing on Amazon (or buy bulk → flip singles).
- **Best categories**: Crayola (BTS), Fujifilm Instax, Convatec medical, food items
- **Key signal**: Amazon listing count ≠ retail unit count → `multipack_mismatch: true` in profitability output
- **How to use**: Run `source.py` normally — multipack mismatches are auto-detected and flagged. Check `cost_multiplier` in output to see true unit cost.

### Strategy B: Brand-Direct + Discount Code Stacking
Go to brand.com directly where coupon codes apply; not available at big-box.
- **Retailers**: Vitacost (20FOODIE, 25FOR814), yankeecandle.com ("4 for $60" bulk deal), Dr. Bronner's, Native
- **How to use**: Pass `--auto-coupon` to `calculate_fba_profitability.py` — auto-applies codes from `RETAILER_COUPON_CODES` dict. Update codes quarterly.

### Strategy C: Specialty Retailer Moat
Source from retailers competitors don't monitor: Lollicup (restaurant supply), Stylevana (K-beauty), PetEdge (pro pet supply), Webstaurantstore (foodservice).
- **Best brands**: 1883/Monin syrups (Lollicup), rom&nd (Stylevana), Andis pet (PetEdge)
- **How to use**: Run `source.py retailer lollicup --section all` or pass retailer URL directly to pipeline

### Strategy D: FBM for Fragrance/Hazmat/Restricted
Fragrances, aerosols, and some cosmetics can't ship FBA. FBM still profitable for fast movers.
- **Best brands**: Zara fragrances (zara.com direct), MAC Cosmetics, Fenty Beauty, Jones Road Beauty
- **How to use**: Pass `--fbm` flag to `calculate_fba_profitability.py` for FBM-specific fee math (no FBA fee, estimates self-ship cost instead)

### Strategy E: Seasonal Timing
- **Q4**: Source Halloween (Sept) and Christmas (Oct) 2-3 months before peak
- **BTS**: Source Crayola, school supplies in June when retail is stocking
- **Post-season clearance**: Source Q4 items on January clearance → hold → sell next Q4

---

## Brand Watchlist (Confirmed Profitable — Updated 2026-03)

| Tier | Brand | Primary Source | Strategy | Notes |
|------|-------|---------------|----------|-------|
| **S** | Zara Fragrances | zara.com direct | FBM | Zara doesn't sell on AMZ, no price wars |
| **S** | 1883 / Monin Syrups | Lollicup | FBA | Restaurant supply moat, consistent 30-50% ROI |
| **S** | Convatec Medical | Specialty retailers | FBA | Medical = fast mover, need ungating |
| **S** | rom&nd K-Beauty | Stylevana | FBA | K-beauty demand, specialty source moat |
| **A** | Dr. Bronner's | Vitacost + codes | FBA | Code stacking = 40-70% ROI |
| **A** | MAC Cosmetics | mac.com direct | FBM | Brand-direct only, FBM play |
| **A** | Jellycat | Brand-direct + specialty | FBA | Demand > supply consistently |
| **A** | Yankee Candle | yankeecandle.com | FBA | Q4 "4 for $60" bulk deal is recurring |
| **A** | Crayola | Target + BTS | FBA | Multi-pack arb, low buy/high bundle value |
| **B** | Native | Vitacost + codes | FBA | Code-dependent, watch price erosion |
| **B** | Andis Pet | PetEdge / Chewy | FBA | Pro pet supply moat |
| **B** | Fujifilm Instax | Walmart | FBA | Multi-pack play |
| **B** | Russell Stover | Fleet Farm / Menards | FBA | Seasonal Q4 only |

---

## FBM Mode (Added 2026-03)

For products that can't be sent FBA (fragrances, hazmat, restricted items):

```bash
python execution/calculate_fba_profitability.py \
  --input .tmp/sourcing/matched.json \
  --output .tmp/sourcing/profit.json \
  --fbm   # enables FBM mode: no FBA fee, estimates self-ship instead
```

FBM fee structure:
- Referral fee (same as FBA — 8-17% depending on category)
- Self-ship estimate (replaces FBA fulfillment fee — $4-13 depending on sell price)
- No prep cost (ship direct from retail)
- No storage fee (holds at home/warehouse)

---

## Coupon Code Auto-Apply (Added 2026-03)

```bash
python execution/calculate_fba_profitability.py \
  --input .tmp/sourcing/matched.json \
  --output .tmp/sourcing/profit.json \
  --auto-coupon   # auto-looks up best code from RETAILER_COUPON_CODES dict
```

Coupon database lives in `RETAILER_COUPON_CODES` at top of `execution/calculate_fba_profitability.py`. Update quarterly — check Honey, RetailMeNot, and direct brand sites. Current codes: Vitacost, Dr. Bronner's, Native, Yankee Candle, Bath & Body Works, Fenty Beauty, Jones Road Beauty, Stylevana, iHerb.

---

## Automation Tools (Added 2026-03)

### Brand Watchlist Cron
Runs daily against S/A-tier brand watchlist (8 brands), auto-alerting via Telegram + exporting to Sheets on BUY results.

```bash
# Run now (manual)
python execution/scheduled_sourcing.py brand-scan

# Run only due brands (respects 20h threshold)
python execution/scheduled_sourcing.py brand-scan

# Schedule at 8am daily (add to crontab)
0 8 * * * cd ~/Documents/nomad-nebula && .venv/bin/python execution/scheduled_sourcing.py brand-scan 2>> .tmp/sourcing/brand-scan.log
```

Brand watchlist: Zara (FBM), Jellycat, 1883 Monin (coupon), Dr. Bronner's (coupon), MAC Cosmetics (FBM), Crayola, rom&nd, Convatec.
State tracked per-brand in `.tmp/sourcing/brand_watchlist_state.json`.

---

### Google Sheets Auto-Export
After any scheduled scan with BUY results, auto-exports to "FBA Sourcing Results" Google Sheet.

```bash
# Manual export
python execution/export_to_sheets.py --input .tmp/sourcing/results.json

# Triggered automatically by scheduled_sourcing.py and run_sourcing_pipeline.py --auto-export
python execution/run_sourcing_pipeline.py --url "https://..." --auto-export
```

Requires `service_account.json` + `GOOGLE_SHARE_EMAIL` in `.env`.

---

### IC-Style Deal Drop Formatter
Converts scan results → IC Approved Products sheet format (Image, Product Name, ASIN, Source URL, Cost Price, Sale Price, Profit, ROI, Coupons, VA Comments).

```bash
python execution/format_deal_drop.py --input .tmp/sourcing/results.json
python execution/format_deal_drop.py --input .tmp/sourcing/results.json --min-verdict BUY
# Output CSV path printed to stdout. BUY listed first, sorted by ROI desc.
```

---

### Multi-Retailer Price Finder (Single ASIN)
Given an ASIN, searches all 239 enabled retailers in parallel and ranks by effective buy price (after cashback + gift card + coupon stack).

```bash
python execution/find_cheapest_source.py --asin B08N5WRWNW
python execution/find_cheapest_source.py --asin B08N5WRWNW --max-retailers 50 --top 5
```

Requires `KEEPA_API_KEY` for title/price lookup. Uses 20 parallel threads, 10s timeout per retailer.

---

### CardBear Auto-Trigger (Scheduled)
Scrapes CardBear for gift card discounts and auto-triggers sourcing for any retailer ≥10%.

```bash
python execution/scheduled_sourcing.py cardbear-scan          # dry-run (shows recommendations)
python execution/scheduled_sourcing.py cardbear-scan --execute # actually runs pipelines

# Schedule at 9am daily (add to crontab)
0 9 * * * cd ~/Documents/nomad-nebula && .venv/bin/python execution/scheduled_sourcing.py cardbear-scan --execute 2>> .tmp/sourcing/cardbear-scan.log
```

---

## Known Issues

- **Amazon anti-bot**: Aggressive blocking. Mitigated by 3-4 sec delay between requests. If blocked, products return without Amazon match.
- **Retailer DOM changes**: Selectors break without notice. Fix: update `execution/retailer_configs.py`, test, update this SOP.
- **Fee estimation**: Approximate (~$0.50 accuracy). For exact fees, integrate SP-API (requires seller account).
- **BSR estimation**: Category-specific multipliers improve accuracy, but still rough. Keepa API provides actual historical data.
- **UPC availability**: Many retailers don't expose UPC in their DOM. Title-based matching is the fallback.
- **Cashback rates**: Estimated from Rakuten averages. Actual rates fluctuate — verify on Rakuten before purchase.
- **Gating**: We flag gated categories but can't check YOUR specific account's gating status (would require SP-API).
- **Hazmat detection**: Keyword-based, not definitive. Always verify in Seller Central before listing.

---

## Self-Annealing

When scraping breaks:
1. Visit the URL in a browser, inspect updated DOM selectors
2. Update `execution/retailer_configs.py` with new selectors
3. Test: `python execution/scrape_retail_products.py --url "..." --max-products 5`
4. Update this SOP with the fix and date

When fees change:
1. Check Amazon Seller Central fee schedule
2. Update `REFERRAL_FEE_RATES`, `FBA_FEE_BY_PRICE`, and `BSR_CATEGORY_MULTIPLIERS` in `execution/calculate_fba_profitability.py`
3. Note the update date in this SOP

When cashback rates change:
1. Check Rakuten.com for current retailer rates
2. Update `RETAILER_CASHBACK_ESTIMATES` in `execution/calculate_fba_profitability.py`

---

## Multi-Retailer Product Search (v4.0)

**The key new capability.** Instead of sourcing from a single URL, search for a product by name across multiple retailers simultaneously. The system auto-detects the product category and picks the right 5-15 retailers using `retailer_registry.py`.

### How It Works

```
Product query → detect_category() → get_retailers_for_product() → search each retailer
                                                                        ↓
                                                              scrape results per retailer
                                                                        ↓
                                                              match to Amazon ASINs
                                                                        ↓
                                                              calculate profitability
                                                                        ↓
                                                    deduplicate by ASIN (keep cheapest source)
                                                                        ↓
                                                              rank by ROI → output
```

### Retailer Registry (100 Retailers)

- **Tier 1 (15 retailers)**: Custom CSS selectors in `retailer_configs.py` — best scraping accuracy
- **Tier 2 (85 retailers)**: Generic JSON-LD fallback — works for any e-commerce site
- Each retailer has: search URL template, clearance URL, cashback %, category tags, request delay

### Category Auto-Detection

Given a query like "reeses easter eggs", the system detects categories (Grocery, Seasonal) and routes to the right retailers (Walmart, Target, CVS, Walgreens, etc.).

18 categories supported: Grocery, Health, Beauty, Electronics, Home, Toys, Sports & Outdoors, Seasonal, Pets, Tools, Apparel, Footwear, Office, Crafts, Kids, Kitchen, Bulk, Farm.

### Modes

| Mode | Input | What it does |
|---|---|---|
| **search** | Product name | Auto-routes to 5-15 retailers, searches each, consolidates results |
| **clearance** | Category (optional) | Scans known clearance URLs across retailers |
| **list** | Product name | Dry-run: shows which retailers would be searched (no scraping) |

### Scripts

| Script | Purpose |
|---|---|
| `execution/retailer_registry.py` | 100-retailer database + smart category routing |
| `execution/multi_retailer_search.py` | Multi-retailer search orchestrator |
| `execution/retailer_configs.py` | CSS selectors for Tier 1 retailers |

### CLI

```bash
# Search for a product across smart-routed retailers
python execution/multi_retailer_search.py search --query "reeses easter eggs" --max-retailers 10

# Override auto-detected category
python execution/multi_retailer_search.py search --query "protein powder" --category "Health"

# Scan clearance pages across retailers
python execution/multi_retailer_search.py clearance --category "Grocery" --max-retailers 10

# Dry-run: see which retailers would be searched
python execution/multi_retailer_search.py list --query "dewalt drill"

# Test the registry directly
python execution/retailer_registry.py "reeses easter eggs"
```

### Flask UI

`http://localhost:5050/sourcing` — three tabs:
1. **Product Search** — type a product name, see retailer preview, search across 100 retailers
2. **URL Source** — paste a single retail URL (original mode)
3. **Clearance Scan** — scan clearance pages across retailers by category

API endpoint for retailer preview: `GET /sourcing/retailers?query=...&category=...&max=15`

---

## v5.0 — Centralized Keepa Client & Quality Filters

### KeepaClient (`execution/keepa_client.py`)

Single source of truth for all Keepa API interactions. Replaces duplicated parsing across 5 scripts.

**Key capabilities:**
- Correct CSV indices: 34 = FBA sellers, 35 = FBM sellers (NOT index 11)
- `offers` parameter support: returns actual seller list with names
- 3-tier private label detection (offers data → CSV counts → heuristic)
- Price trend extraction (30d/90d/180d averages, direction, volatility)
- Token budget management across pipeline stages
- Rate limiting with tier-aware delays (basic: 13s, pro: 4s)

### Private Label Detection

Products where the brand itself is the only seller are automatically SKIPPED — no arbitrage opportunity exists.

| Tier | Data Source | Confidence | Method |
|---|---|---|---|
| 1 | Offers data (seller names) | Definitive | Seller name matches brand name |
| 2 | CSV indices 34/35 | Strong | FBA count == 1 AND FBM count <= 1 |
| 3 | Total offer count | Possible | Total offers == 1 AND no Amazon |

### Multi-Seller Verification

Products must have 2+ FBA sellers (configurable via `--min-sellers N`). Single-seller listings are SKIPPED.

### Stock Availability

Target products are verified via the free Redsky fiats_v1 API (`--check-stock` flag). Out-of-stock products are flagged in output.

### Deal Scanner v3.0 CLI

```bash
# Standard scan with all quality filters
python execution/deal_scanner.py --count 20 --match-amazon --min-sellers 2 --no-private-label

# Full scan with stock checking
python execution/deal_scanner.py --count 20 --match-amazon --check-stock --min-sellers 2

# Pro tier (4x faster)
python execution/deal_scanner.py --count 50 --match-amazon --keepa-tier pro

# Allow private label (override default)
python execution/deal_scanner.py --count 20 --match-amazon --allow-private-label
```

### Profitability Calculator v3.0 Updates

| Filter | Action | Was |
|---|---|---|
| Private label detected | Hard SKIP | Not checked |
| FBA sellers < 2 | Hard SKIP | Not checked |
| Pack size mismatch | Hard SKIP | Warning only |
| Review count < 50 | Downgrade BUY → MAYBE | Not checked |
| Price trend rising | +5 deal score bonus | Not scored |
| Not at historical low | +5 deal score bonus | Not scored |

---

## CLI Quick Reference

```bash
# Deal scanner v3 with quality filters (NEW in v5.0)
python execution/deal_scanner.py --count 20 --match-amazon --check-stock --min-sellers 2
python execution/deal_scanner.py --count 50 --match-amazon --keepa-tier pro --category grocery

# Multi-retailer product search
python execution/multi_retailer_search.py search --query "protein powder" --max-retailers 10
python execution/multi_retailer_search.py clearance --category "Grocery"
python execution/multi_retailer_search.py list --query "dewalt drill"

# Full pipeline (with auto-cashback)
python execution/run_sourcing_pipeline.py --url "https://www.walmart.com/browse/clearance" --min-roi 30 --auto-cashback

# Full pipeline (with manual cashback)
python execution/run_sourcing_pipeline.py --url "https://www.target.com/c/clearance" --cashback-percent 5

# Reverse sourcing (ASIN → smart-routed to 15 retailers)
python execution/reverse_sourcing.py --asin B08XYZ1234

# Scheduled sourcing
python execution/scheduled_sourcing.py add --url "https://www.walmart.com/browse/clearance" --label "Walmart Clearance" --schedule daily
python execution/scheduled_sourcing.py run-due

# Price tracking
python execution/price_tracker.py stats
python execution/price_tracker.py history --asin B08XYZ1234
python execution/price_tracker.py drops --days 7

# Alerts
python execution/sourcing_alerts.py --db-alerts

# Google Sheets export
python execution/export_to_sheets.py --input .tmp/sourcing/results.json

# Just scrape retail (no Amazon matching)
python execution/scrape_retail_products.py --url "https://www.target.com/c/clearance" --max-products 20

# Just match Amazon (from existing scrape output)
python execution/match_amazon_products.py --input .tmp/sourcing/retail.json --output .tmp/sourcing/matched.json

# Just calculate profitability (from existing matches)
python execution/calculate_fba_profitability.py --input .tmp/sourcing/matched.json --output .tmp/sourcing/results.json --auto-cashback

# Full pipeline with all cost layers
python execution/run_sourcing_pipeline.py --url "https://www.walmart.com/browse/clearance" --auto-cashback --auto-giftcard --tax-state TX

# Batch ASIN check from deal group
python execution/batch_asin_checker.py --file asins.txt --buy-prices 5,10,15,20

# Stalk a competitor storefront
python execution/storefront_stalker.py --seller A1B2C3D4E5F6G7 --reverse-source

# Inventory tracking
python execution/inventory_tracker.py buy --asin B08XYZ1234 --name "Widget" --qty 10 --cost 12.99 --retailer Walmart
python execution/inventory_tracker.py pnl --days 30
python execution/inventory_tracker.py hit-rate
```

---

## watch_inbox Task Format

```json
{
    "task": "source_products",
    "agent": "sourcing",
    "url": "https://www.walmart.com/browse/clearance/0/0/?page=1",
    "min_roi": 30,
    "min_profit": 3.5,
    "max_price": 50.0,
    "max_products": 50,
    "auto_cashback": true
}
```

---

---

## Out-of-Stock Opportunity Scanning (v7.0)

Finds Amazon listings where all FBA sellers have dropped off but the product is still available at retail. You enter as the sole seller — 100%+ ROI common.

```bash
# Scan for OOS opportunities (uses Keepa Deals API)
python execution/source.py oos --count 30 --max-bsr 100000

# With category filter
python execution/source.py oos --count 30 --category "Grocery" --max-bsr 100000

# Standalone scanner with full pipeline
python execution/oos_opportunity_scanner.py --count 30 --min-reviews 50 --max-bsr 100000
```

**How it works:**
1. Keepa Deals API with `isOutOfStock=True`, `mustNotHaveAmazonOffer=True` → candidate ASINs
2. Filter: BSR < 100K, review count > 50, time OOS > 24 hours
3. For each candidate, search retailers via existing `multi_retailer_search.py` functions
4. Calculate profitability via `calculate_fba_profitability.py`
5. Output with `OOS_OPPORTUNITY` verdict + estimated monopoly window (days)

**Keepa cost:** 5 tokens per request (up to 150 deals). ~35 tokens per full scan.

**Scripts:**
| Script | Purpose |
|---|---|
| `execution/oos_opportunity_scanner.py` | Standalone OOS scanner |
| `execution/keepa_client.py` → `get_oos_deals()` | Keepa API wrapper for OOS deals |
| `execution/keepa_client.py` → `get_seller_count_history()` | Time-series seller count for OOS duration |

---

## Amazon-to-Amazon Flips (v7.0)

Find products on Amazon that can be resold at a higher price on Amazon itself. Zero sourcing friction.

```bash
# Warehouse deals (used/renewed at deep discount → resell as new)
python execution/source.py a2a --type warehouse --count 30

# Variation arbitrage (cheap child ASIN in a popular variation family)
python execution/source.py a2a --type variation --asin B08XYZ1234

# Multi-pack arbitrage (buy singles, bundle as multi-pack)
python execution/source.py a2a --type multipack --count 30
```

**Scripts:**
| Script | Purpose |
|---|---|
| `execution/source.py a2a` | A2A flip scanner (warehouse, variation, multipack) — integrated into main CLI |
| `execution/keepa_client.py` → `get_warehouse_deals()` | Keepa used/renewed price analysis |

---

## Always-Be-Scanning (ABS) — Proactive Deal Discovery (v7.0)

Runs scans 24/7 in the cloud (Modal), sends daily digest via Telegram.

```bash
# Run locally (one cycle)
python execution/always_be_scanning.py run

# View schedule
python execution/always_be_scanning.py schedule

# Add brand to watchlist
python execution/always_be_scanning.py watch --brand "CeraVe"
python execution/always_be_scanning.py watch --brand "Dubble Bubble"

# View daily digest
python execution/always_be_scanning.py digest --days 1
```

**Scan rotation:**
| Interval | Scan Type | Script |
|---|---|---|
| Every 4h | OOS opportunities | `oos_opportunity_scanner.py` |
| Every 6h | Keepa deal hunter | `keepa_deal_hunter.py` |
| Every 6h | Stock monitor | `stock_monitor.py` |
| Every 12h | Category clearance | `multi_retailer_search.py clearance` |
| Every 24h | Brand watchlist | `source.py brand` (for each saved brand) |
| Every 24h | A2A flips | `source.py a2a` |

**Modal deployment:** Deployed as a scheduled Modal function. Independent of Mac being on.

---

## Keepa Product Finder (v7.0)

Query Amazon's entire catalog with filters to find arbitrage windows at scale. Then reverse-source each candidate.

```bash
# Find products with price drops > 30% in 90 days
python execution/source.py finder --min-drop 30 --max-bsr 100000 --price-range 10,50

# With category filter
python execution/source.py finder --min-drop 30 --category "Health & Household" --count 50

# With reverse-sourcing (find retail source for each candidate)
python execution/source.py finder --min-drop 30 --reverse-source
```

**Keepa cost:** 5 tokens per 150 results via `/query` endpoint.

---

*Last updated: 2026-03-13 | Version 7.0 — Agent routing rules (MANDATORY), out-of-stock opportunity scanning (Keepa OOS deals), Amazon-to-Amazon flips (warehouse, variation, multipack), always-be-scanning (ABS) orchestrator with Modal deployment, Keepa Product Finder integration, Buy Box ownership tracking, image-based match verification, retailer expansion (100→300+)*
