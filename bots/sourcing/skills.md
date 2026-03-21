# Sourcing Bot — Skills
> bots/sourcing/skills.md | Version 7.0

---

## Owned Claude Code Skills (Slash Commands)

| Skill | Invocation | What It Does |
|---|---|---|
| Source Products | `/source-products` | Amazon FBA product sourcing — brand, category, clearance, ASIN, deals, OOS, A2A, finder |
| Deal Drop | `/deal-drop` | Format sourcing results as Inner Circle CSV + Discord @everyone messages |

**Skill files:** `.claude/skills/source-products.md`, `.claude/skills/deal-drop.md`

When `/source-products` runs, it reads `directives/amazon-sourcing-sop.md`, classifies the request via the routing table, and calls the correct `source.py` subcommand. Self-anneals on failure.

---

## Skill: Find Profitable Products (ROUTING — READ FIRST)

**When to use:** ANY sourcing request from the user. This skill routes to the correct pipeline command. See `directives/sourcing-agent-routing.md` for the full routing directive.

**MANDATORY RULES:**
1. NEVER manually web-search for products, prices, or Amazon listings
2. ALWAYS use pipeline scripts (`source.py`, `multi_retailer_search.py`, etc.)
3. ALWAYS present results with: ASIN, Amazon link, source link, buy cost, profit, ROI, match confidence
4. If 0 results: broaden search → switch mode → relax thresholds → then inform user

**Quick routing table:**

| User says | Command |
|---|---|
| "Find profitable [brand]" | `source.py brand "[brand]" --retailers target,walmart,walgreens,cvs,costco` |
| "Source [product]" | `multi_retailer_search.py search --query "[product]" --max-retailers 10` |
| "Find [category] deals" | `source.py category "[category]"` |
| "Is [ASIN] worth it?" | `source.py asin [ASIN]` |
| "Find deals" | `source.py scan --count 30` |
| "Find OOS opportunities" | `source.py oos --count 30` |
| "Find Amazon flips" | `source.py a2a --type warehouse --count 30` |
| "Find price drops" | `source.py finder --min-drop 30 --max-bsr 100000` |

**Always activate venv first:** `source /Users/Shared/antigravity/projects/nomad-nebula/.venv/bin/activate`

---

## Skill: Multi-Retailer Product Search (PRIMARY)

**When to use:** User types a product name and wants to find it across multiple retailers at the cheapest price.

**Reference:**
1. `directives/amazon-sourcing-sop.md` — full SOP (v4.0, Multi-Retailer section)
2. `execution/retailer_registry.py` — 231-retailer database with smart category routing
3. `execution/multi_retailer_search.py` — multi-retailer search orchestrator

**Steps:**
1. Auto-detect product category from query (Grocery, Health, Beauty, etc.)
2. Smart-route to 5-15 relevant retailers via `retailer_registry.py`
3. Run `execution/multi_retailer_search.py search --query "{query}" --max-retailers 10`
4. Results are deduped by ASIN (cheapest source kept, alternatives listed)
5. Present ranked by ROI with retailer comparison

**CLI:** `python execution/multi_retailer_search.py search --query "reeses easter eggs" --max-retailers 10`
**UI:** `http://localhost:5050/sourcing` → Product Search tab

**Output:** JSON + CSV in `.tmp/sourcing/`, deduped by ASIN

---

## Skill: Clearance Scan

**When to use:** User wants to scan clearance/deals pages across multiple retailers for a category.

**Steps:**
1. Run `execution/multi_retailer_search.py clearance --category "{category}" --max-retailers 10`
2. Scans known clearance URLs from the registry
3. Matches all to Amazon, calculates profitability
4. Present consolidated results

**CLI:** `python execution/multi_retailer_search.py clearance --category "Grocery"`
**UI:** `http://localhost:5050/sourcing` → Clearance Scan tab

---

## Skill: Product Sourcing (URL → Profit Analysis)

**When to use:** User provides a specific retail URL to analyze.

**Reference:**
1. `directives/amazon-sourcing-sop.md` — full SOP
2. `execution/retailer_configs.py` — supported retailers and selectors (15 Tier 1)

**Steps:**
1. Run `execution/run_sourcing_pipeline.py --url "{url}" --min-roi {threshold} --auto-cashback`
2. Present results ranked by ROI
3. Highlight BUY verdicts with key metrics (profit, ROI, est. monthly sales)
4. Flag products with: match_confidence < 0.7, competition warnings, gating/hazmat/IP risk
5. Call out multi-pack mismatches if detected

**Output:** JSON + CSV in `.tmp/sourcing/`, auto-tracked in SQLite DB

---

## Skill: Single Product Lookup

**When to use:** User provides a specific retail product URL to check against Amazon.

**Steps:**
1. Run `execution/scrape_retail_products.py --url "{url}" --max-products 1`
2. Run `execution/match_amazon_products.py --input {result} --output {matched}`
3. Run `execution/calculate_fba_profitability.py --input {matched} --output {final} --auto-cashback`
4. Present the single product analysis with full competition/risk breakdown

---

## Skill: Reverse Sourcing (ASIN → Find Retail Source)

**When to use:** User has an Amazon ASIN and wants to find cheaper retail sources.

**Steps:**
1. Run `execution/reverse_sourcing.py --asin {ASIN}`
2. Script searches Walmart, Target, Home Depot, CVS, Walgreens, Costco for the product
3. Present retail sources ranked by ROI
4. Highlight the best source with full profitability breakdown

**CLI:** `python execution/reverse_sourcing.py --asin B08XYZ1234`
**Batch:** `python execution/reverse_sourcing.py --asin-file asins.txt`

---

## Skill: Scheduled Sourcing

**When to use:** User wants automatic recurring scans of bookmarked URLs.

**Steps:**
1. Add bookmarks: `python execution/scheduled_sourcing.py add --url "{url}" --label "{label}" --schedule daily`
2. List bookmarks: `python execution/scheduled_sourcing.py list`
3. Run due scans: `python execution/scheduled_sourcing.py run-due`
4. View results and alerts from each run

**Cron setup:**
```
0 * * * * cd /Users/Shared/antigravity/projects/nomad-nebula && .venv/bin/python execution/scheduled_sourcing.py run-due 2>> .tmp/sourcing/cron.log
```

---

## Skill: Price Tracking & Alerts

**When to use:** User wants to track price history or check for alerts.

**Steps:**
1. View price history: `python execution/price_tracker.py history --asin {ASIN} --days 90`
2. Check for price drops: `python execution/price_tracker.py drops --days 7 --min-drop 10`
3. View trending buys: `python execution/price_tracker.py trending --days 30`
4. View DB stats: `python execution/price_tracker.py stats`
5. Send alerts: `python execution/sourcing_alerts.py --db-alerts`

**Alert types:** price_drop, new_buy, roi_increase, competition_change

---

## Skill: Export to Google Sheets

**When to use:** User wants sourcing results in Google Sheets for sharing/review.

**Steps:**
1. Run `python execution/export_to_sheets.py --input {results.json}`
2. Returns Google Sheets URL with formatted results tab
3. Sheet is shared with GOOGLE_SHARE_EMAIL from .env

**Requires:** `service_account.json` at project root (same as upload_to_gdrive.py)

---

## Skill: Retailer Selector Update

**When to use:** Scraping breaks on a retailer (selectors changed).

**Steps:**
1. Visit the URL with Playwright to inspect updated DOM
2. Identify the new CSS selectors for product title, price, UPC, etc.
3. Update `execution/retailer_configs.py` with corrected selectors
4. Test with: `python execution/scrape_retail_products.py --url "{test_url}" --max-products 3`
5. Update `directives/amazon-sourcing-sop.md` with the fix

---

## Skill: Fee Table Update

**When to use:** Quarterly, or when Amazon changes their fee structure.

**Steps:**
1. Check Amazon Seller Central fee schedule for updated rates
2. Update `REFERRAL_FEE_RATES` in `execution/calculate_fba_profitability.py`
3. Update `FBA_FEE_BY_PRICE` in `execution/calculate_fba_profitability.py`
4. Update `BSR_TO_MONTHLY_SALES` and `BSR_CATEGORY_MULTIPLIERS` if new research is available
5. Note the update date in `directives/amazon-sourcing-sop.md`

---

## Skill: Batch Sourcing

**When to use:** User wants to scan multiple URLs at once.

**Steps:**
1. For each URL, run the full pipeline
2. Aggregate all BUY products across runs
3. De-duplicate by ASIN (same product from multiple retailers → show lowest buy cost)
4. Present consolidated results sorted by ROI
5. Export combined results to Google Sheets

---

## Skill: Gift Card Presourcing (CardBear)

**When to use:** Before buying retail products, check if gift cards are available at a discount to maximize savings.

**Steps:**
1. Run `python execution/scrape_cardbear.py --retailer "{retailer_name}"`
2. Returns current gift card discount rates for that retailer
3. Factor discount into profitability calculation (stacks with cashback)
4. Track discount trends over time (SQLite DB)

**Output:** Discount rate that can be applied to reduce effective buy cost

---

## Skill: Batch ASIN Check (Deal Groups)

**When to use:** User pastes a list of ASINs from Discord, Facebook deal groups, or deal sheets.

**Steps:**
1. Run `python execution/batch_asin_checker.py --asins {ASIN1} {ASIN2} ...` (or `--file asins.txt` / `--stdin`)
2. Optionally specify buy prices: `--buy-prices 5,10,15,20`
3. Script fetches Amazon data, calculates profitability at each buy price
4. `find_max_buy_price()` tells you the highest you can pay and still get a BUY verdict
5. Present summary table with deal scores (0-100)

**CLI:** `python execution/batch_asin_checker.py --file asins.txt --buy-prices 5,10,15,20 --use-keepa`

---

## Skill: Storefront Stalking

**When to use:** User wants to spy on a competitor seller to find what they're selling.

**Steps:**
1. Run `python execution/storefront_stalker.py --seller {SELLER_ID}` (or `--url`)
2. Script scrapes all products from their storefront (paginated)
3. Enriches with BSR, category, seller count
4. Scores each product with demand-weighted deal score
5. Optionally auto-reverse-sources top products: `--reverse-source`

**CLI:** `python execution/storefront_stalker.py --seller A1B2C3D4E5F6G7 --max-products 50 --reverse-source`

---

## Skill: Inventory & P&L Tracking

**When to use:** User wants to track actual purchases, shipments, sales, and measure real profitability.

**Steps:**
1. Record purchases: `python execution/inventory_tracker.py buy --asin {ASIN} --name "{name}" --qty {qty} --cost {cost} --retailer {retailer}`
2. Update status: `ship --id {id}`, `sold --id {id} --units {n} --price {p} --fees {f}`
3. Import from sourcing run: `import-buys --results {file} --confirm`
4. View reports: `inventory`, `pnl --days 30`, `hit-rate`, `dashboard`

**Key insight:** Compare `estimated_roi` from sourcing pipeline vs actual ROI to calibrate accuracy over time.

---

## Skill: Keepa Deal Hunting (Proactive Opportunities)

**When to use:** User wants to proactively find deals via BSR drops, price drops, Amazon exits, or seller count changes.

**Steps:**
1. Manage watchlist: `python execution/keepa_deal_hunter.py watch add --asin {ASIN} --name "{name}"`
2. Import BUY products: `python execution/keepa_deal_hunter.py watch import --results {file}`
3. Scan for deals: `python execution/keepa_deal_hunter.py scan --alert`
4. View detected deals: `python execution/keepa_deal_hunter.py deals --days 7 --min-score 50`

**Cron:** Every 4 hours — `python execution/keepa_deal_hunter.py scan --alert`

---

## Skill: Wholesale Manifest Analysis

**When to use:** User has a CSV/Excel supplier manifest (500-5K SKUs) to analyze for FBA profitability.

**Steps:**
1. Preview columns: `python execution/wholesale_manifest_analyzer.py preview --manifest supplier.csv`
2. Full analysis: `python execution/wholesale_manifest_analyzer.py analyze --manifest supplier.csv`
3. With overrides: `--cost-col "Unit Cost" --upc-col "UPC" --pack-col "Case Qty"`
4. Export to Sheets: `--export-sheets`

---

## Skill: Seasonal Demand Analysis

**When to use:** User wants to know the best time to buy/sell a product based on BSR seasonality.

**Steps:**
1. Analyze ASIN: `python execution/seasonal_analyzer.py analyze --asin {ASIN}`
2. Check Google Trends: `python execution/seasonal_analyzer.py trends --keyword "{keyword}"`
3. Full timing verdict: `python execution/seasonal_analyzer.py timing --asin {ASIN} --keyword "{keyword}"`
4. Batch analysis: `python execution/seasonal_analyzer.py batch --file asins.txt`

**Verdicts:** BUY (1-2 months before peak), SELL_WINDOW (at peak), EARLY (3+ months out), LATE (post-peak), AVOID (BSR >2x average)

---

## Skill: IP Risk Intelligence

**When to use:** User wants to check brand IP risk before sourcing a product.

**Steps:**
1. Initialize DB: `python execution/ip_intelligence.py init` (seeds 160 brands)
2. Score a brand: `python execution/ip_intelligence.py score --brand "Nike"`
3. Check product title: `python execution/ip_intelligence.py check --title "Nike Air Max Running Shoes"`
4. Add custom brand: `python execution/ip_intelligence.py add --brand "NewBrand" --score 75 --category "Electronics"`

**Risk levels:** EXTREME (90-100), HIGH (70-89), MODERATE (40-69), LOW (10-39)

---

## Skill: Variation Tree Analysis

**When to use:** User wants to find the best variation (color, size, etc.) of a product to sell.

**Steps:**
1. Full analysis: `python execution/variation_analyzer.py analyze --asin {ASIN}`
2. Quick best pick: `python execution/variation_analyzer.py best --asin {ASIN}`
3. With Keepa enrichment: `--use-keepa`

**Scoring:** demand (40%) + competition (30%) + review gap (20%) + price sweet spot (10%)

---

## Skill: Stock Monitoring & Stockout Alerts

**When to use:** User wants to track competitor stock levels and get alerted when competitors exit or stock out.

**Steps:**
1. Add to watchlist: `python execution/stock_monitor.py watch add --asin {ASIN} --name "{name}"`
2. Import from results: `python execution/stock_monitor.py watch import --results {file}`
3. Run check: `python execution/stock_monitor.py check --alert`
4. View alerts: `python execution/stock_monitor.py alerts --days 7`

**Alert types:** competitor_exit, amazon_exit, stockout_opportunity, price_drop
**Cron:** Every 6 hours — `python execution/stock_monitor.py check --alert`

---

## Skill: Capital Allocation Optimization

**When to use:** User has a fixed budget and wants to optimize which products to buy for maximum returns.

**Steps:**
1. Allocate budget: `python execution/capital_allocator.py allocate --budget 1500 --results {file}`
2. Compare sourcing runs: `python execution/capital_allocator.py compare --budget 1500 --results run1.json run2.json`
3. Simulate reinvestment: `python execution/capital_allocator.py simulate --budget 1500 --results {file} --months 6`

**Key metric:** Annualized ROI = roi% × (365 / days_to_sell). 30% concentration cap per product.

---

## Skill: Coupon Stacking (Layer 3)

**When to use:** Before purchasing, check for retailer coupons to stack on top of gift card + cashback savings.

**Steps:**
1. Scrape all retailers: `python execution/coupon_scraper.py scrape`
2. Find best coupon: `python execution/coupon_scraper.py lookup --retailer walmart --amount 50`
3. List active coupons: `python execution/coupon_scraper.py list --retailer target`
4. Track usage: `python execution/coupon_scraper.py mark --id 123 --worked`

**Stacking order:** Gift card (CardBear) → Cashback (Rakuten) → Coupon (this) → Final cost

---

## Skill: Demand Signal Scanning

**When to use:** User wants to find products with rising demand before they spike on Amazon.

**Steps:**
1. Full scan: `python execution/demand_signal_scanner.py scan`
2. Check specific keyword: `python execution/demand_signal_scanner.py trends --keyword "stanley cup"`
3. View stored signals: `python execution/demand_signal_scanner.py signals --days 7 --min-score 50`
4. Mark action taken: `python execution/demand_signal_scanner.py act --id 123 --action sourced`

**Sources:** Google Trends (spike detection) + Reddit (r/AmazonDeals, r/deals, r/gadgets, etc.)

---

## Skill: Coaching Deal Walkthrough (Student Reports)

**When to use:** User wants to generate educational deal analysis reports for FBA coaching students.

**Steps:**
1. PDF walkthrough: `python execution/coaching_simulator.py walkthrough --input results.json --output report.pdf`
2. Text output: `python execution/coaching_simulator.py walkthrough --input results.json --text`
3. Single what-if: `python execution/coaching_simulator.py whatif --asin B08XYZ --buy-cost 15 --amazon-price 35`
4. Student report: `python execution/coaching_simulator.py batch --input results.json --student "John Doe" --output report.pdf`

**Output:** Color-coded PDF with fee breakdowns, competition explanations, sensitivity analysis, break-even calculations

---

## Skill: Wholesale Supplier Discovery

**When to use:** User wants to find wholesale suppliers for a product category.

**Steps:**
1. Search suppliers: `python execution/wholesale_supplier_finder.py search --category "Health & Household"`
2. List ranked: `python execution/wholesale_supplier_finder.py list --min-score 50 --status active`
3. Log contact: `python execution/wholesale_supplier_finder.py contact --id 5 --type email --notes "Sent intro" --followup 2026-03-01`
4. Check followups: `python execution/wholesale_supplier_finder.py followups --days 7`

**Sources:** Google Search, ThomasNet, Wholesale Central. Scoring (0-100) based on location, certifications, Amazon-friendliness.

---

## Skill: Brand Direct Outreach

**When to use:** User wants to reach out directly to brands for authorized reseller/wholesale accounts.

**Steps:**
1. Discover brand: `python execution/brand_outreach.py discover --brand "Anker"`
2. Batch from results: `python execution/brand_outreach.py discover --from-results results.json`
3. Generate email: `python execution/brand_outreach.py email --brand-id 5 --template cold_intro`
4. Log as sent: `python execution/brand_outreach.py send --brand-id 5 --template cold_intro`
5. Log reply: `python execution/brand_outreach.py reply --brand-id 5 --notes "Has wholesale form"`
6. Update status: `python execution/brand_outreach.py status --brand-id 5 --set approved --notes "40% off MSRP, MOQ 100"`
7. View pipeline: `python execution/brand_outreach.py pipeline`

**Templates:** cold_intro, followup_1, followup_2, application_reply. Set env vars: OUTREACH_SENDER_NAME, OUTREACH_COMPANY, OUTREACH_STORE_URL

---

## Skill: Out-of-Stock Opportunity Scanning

**When to use:** User wants to find Amazon listings where all FBA sellers dropped off but the product is still available at retail. Highest-margin arbitrage opportunity.

**Steps:**
1. Run `python execution/source.py oos --count 30 --max-bsr 100000`
2. Or standalone: `python execution/oos_opportunity_scanner.py --count 30 --min-reviews 50`
3. Results show `OOS_OPPORTUNITY` verdict + estimated monopoly window (days)
4. For each hit, source link and profitability are pre-calculated

**Keepa cost:** ~35 tokens per scan (5 tokens per Deals request + verification)

---

## Skill: Amazon-to-Amazon Flips

**When to use:** User wants to find products on Amazon that can be resold at a higher price on Amazon itself. Zero sourcing friction.

**Steps:**
1. Warehouse deals: `python execution/source.py a2a --type warehouse --count 30`
2. Variation arbitrage: `python execution/source.py a2a --type variation --asin {ASIN}`
3. Multi-pack arbitrage: `python execution/source.py a2a --type multipack --count 30`

**Sub-modes:**
- **warehouse** — Amazon Warehouse used/renewed at deep discount → resell as new
- **variation** — Find cheap child ASINs in popular variation families (wraps `variation_analyzer.py`)
- **multipack** — Buy singles cheaper than existing multi-pack listing

---

## Skill: Always-Be-Scanning (ABS)

**When to use:** User wants to set up proactive 24/7 deal finding that runs even when offline.

**Steps:**
1. Run locally: `python execution/always_be_scanning.py run`
2. View schedule: `python execution/always_be_scanning.py schedule`
3. Add brand to watchlist: `python execution/always_be_scanning.py watch --brand "CeraVe"`
4. View digest: `python execution/always_be_scanning.py digest --days 1`

**Scan rotation:** OOS (4h), Keepa deals (6h), stock monitor (6h), clearance (12h), brand watchlist (24h), A2A flips (24h)

**Deployment:** Modal scheduled function — runs in the cloud independent of Mac being on.

---

## Skill: Keepa Product Finder

**When to use:** User wants to find arbitrage windows by scanning Amazon's entire catalog for price drops, seller exits, etc.

**Steps:**
1. Run: `python execution/source.py finder --min-drop 30 --max-bsr 100000 --price-range 10,50`
2. With category filter: `--category "Health & Household"`
3. With reverse-sourcing: `--reverse-source` (finds retail source for each candidate)

**Keepa cost:** 5 tokens per 150 results via `/query` endpoint.

---

*Sourcing Bot Skills v6.0 — 2026-03-13*
