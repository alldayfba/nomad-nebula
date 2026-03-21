# Sourcing Agent — Directive
> SabboOS/Agents/Sourcing.md | Version 5.0

---

## Purpose

Full-stack Amazon FBA sourcing automation across **100 retailers** with smart category routing. Multi-retailer product search, forward sourcing, reverse sourcing (now smart-routed to 15 retailers), clearance scanning, wholesale manifest analysis, proactive deal hunting, competitor intelligence, seasonal timing, IP risk scoring, variation optimization, stock monitoring, capital allocation, coupon/cashback/gift card stacking, demand signal detection, coaching report generation, wholesale supplier discovery, and brand direct outreach. Covers the entire sourcing lifecycle from deal discovery to supplier relationship management.

---

## Trigger

User says any of:
- "Source products from [URL]"
- "Run sourcing on [URL]"
- "Find profitable products at [retailer]"
- "Analyze [URL] for FBA"
- "Check this for arbitrage: [URL]"
- "Reverse source [ASIN]"
- "Check these ASINs: [list]"
- "Stalk this seller: [seller ID/URL]"
- "Run scheduled sourcing"
- "Show sourcing alerts"
- "Check price history for [ASIN]"
- "Show my inventory / P&L / hit rate"
- "Analyze this manifest: [file]"
- "Hunt for Keepa deals"
- "Check IP risk for [brand]"
- "Analyze variations for [ASIN]"
- "When should I buy/sell [ASIN]?"
- "Monitor stock for [ASIN]"
- "Allocate $X budget across [results]"
- "Find coupons for [retailer]"
- "Scan for demand signals"
- "Generate coaching report from [results]"
- "Find wholesale suppliers for [category]"
- "Reach out to [brand] for wholesale"

- "Search for [product] across retailers"
- "Find cheapest source for [product]"
- "Scan clearance for [category]"

Or via watch_inbox task type: `source_products`

---

## Pipelines

### Multi-Retailer Product Search (NEW — primary mode)
```
Product query → detect_category → get_retailers_for_product (5-15 retailers)
                                        ↓
                              search each retailer in parallel
                                        ↓
                              scrape results per retailer
                                        ↓
                              match all to Amazon ASINs
                                        ↓
                              calculate profitability
                                        ↓
                    deduplicate by ASIN (keep cheapest source)
                                        ↓
                              rank by ROI → output
```

### Clearance Scan
```
Category (optional) → get_clearance_urls → scrape each → match Amazon → profitability → rank
```

### Forward Sourcing
```
URL → detect_retailer → scrape_products → match_amazon → calculate_profitability → rank → output
                                              ↓                    ↓
                                     (FBA sellers, BSR,    (cashback, gating,
                                      Amazon-on-listing)   competition, hazmat)
                                              ↓                    ↓
                                        track in DB ← ─ ─ ─ generate alerts
                                              ↓
                                     export to Sheets
```

### Reverse Sourcing
```
ASIN → get_amazon_details → search_retailers → match_titles → calculate_profitability → rank
```

### Wholesale Manifest
```
CSV/Excel → detect_columns → parse_manifest → UPC match Amazon → profitability → rank → export
```

### Proactive Deal Discovery
```
Keepa watchlist → scan BSR/price/seller changes → score deals → alert → auto-source winners
Google Trends + Reddit → detect spikes → extract ASINs → signal scoring → action tracking
```

### Supplier Pipeline
```
Category → search directories → score suppliers → CRM tracking → brand outreach → approved reseller
```

---

## Scripts

### Core Pipeline
| Step | Script | Model |
|---|---|---|
| **Multi-retailer search** | `execution/multi_retailer_search.py` | None (orchestrator) |
| **Retailer registry** | `execution/retailer_registry.py` | None (100-retailer database) |
| Scrape retail | `execution/scrape_retail_products.py` | None (deterministic) |
| Match Amazon | `execution/match_amazon_products.py` | Haiku 4.5 (fuzzy matching only) |
| Calculate profit | `execution/calculate_fba_profitability.py` | None (deterministic) |
| URL pipeline | `execution/run_sourcing_pipeline.py` | None (orchestrator) |
| Reverse sourcing | `execution/reverse_sourcing.py` | None (smart-routed, 15 retailers) |

### Data & Tracking
| Step | Script | Model |
|---|---|---|
| Price tracking | `execution/price_tracker.py` | None (SQLite) |
| Scheduled runs | `execution/scheduled_sourcing.py` | None (cron-compatible) |
| Alerts | `execution/sourcing_alerts.py` | None (Telegram/email) |
| Google Sheets | `execution/export_to_sheets.py` | None (Google API) |
| Inventory P&L | `execution/inventory_tracker.py` | None (SQLite) |
| Stock monitoring | `execution/stock_monitor.py` | None (Keepa + SQLite) |

### Deal Discovery & Intelligence
| Step | Script | Model |
|---|---|---|
| Gift card deals | `execution/scrape_cardbear.py` | None (HTTP + SQLite) |
| Coupon scraping | `execution/coupon_scraper.py` | None (HTTP + SQLite) |
| Batch ASIN check | `execution/batch_asin_checker.py` | None (Playwright/Keepa) |
| Storefront stalker | `execution/storefront_stalker.py` | None (Playwright) |
| Keepa deal hunter | `execution/keepa_deal_hunter.py` | None (Keepa API) |
| Demand signals | `execution/demand_signal_scanner.py` | None (pytrends + HTTP) |

### Product Analysis
| Step | Script | Model |
|---|---|---|
| IP intelligence | `execution/ip_intelligence.py` | None (SQLite, 160+ brands) |
| Variation analysis | `execution/variation_analyzer.py` | None (Playwright/Keepa) |
| Seasonal analysis | `execution/seasonal_analyzer.py` | None (Keepa + pytrends) |

### Wholesale & Supplier
| Step | Script | Model |
|---|---|---|
| Manifest analyzer | `execution/wholesale_manifest_analyzer.py` | None (openpyxl) |
| Supplier finder | `execution/wholesale_supplier_finder.py` | None (HTTP + SQLite) |
| Brand outreach | `execution/brand_outreach.py` | None (HTTP + SQLite) |

### Capital & Coaching
| Step | Script | Model |
|---|---|---|
| Capital allocator | `execution/capital_allocator.py` | None (deterministic) |
| Coaching simulator | `execution/coaching_simulator.py` | None (reportlab PDF) |

## Config

| File | Purpose |
|---|---|
| `execution/retailer_configs.py` | Per-retailer CSS selectors |
| `directives/amazon-sourcing-sop.md` | Full SOP |
| `execution/scrape_cardbear.py` | CardBear gift card discount tracking |
| `bots/sourcing/` | Bot identity, skills, heartbeat, tools |

---

## Profitability Analysis

Enhanced calculator includes:
- **4-layer cost stacking** — gift card → cashback → coupon → sales tax (multiplicative)
- **Seller competition scoring** — LOW / MODERATE / HIGH / SATURATED based on FBA seller count
- **Amazon-on-listing detection** — flags when Amazon.com is a seller (high Buy Box risk)
- **Gating warnings** — flags products in restricted categories (Grocery, Jewelry, Watches, etc.)
- **Hazmat detection** — flags products containing hazmat keywords (battery, aerosol, etc.)
- **IP risk intelligence** — 160+ brand database scored 0-100, replaces simple keyword check
- **Multi-pack mismatch detection** — catches quantity discrepancies between retail and Amazon listings
- **Category-specific BSR multipliers** — more accurate sales estimates per category
- **Prep cost estimation** — FNSKU labels, poly bags, bubble wrap by category
- **Storage fees** — velocity-based FBA monthly storage with Q4 surcharge
- **BSR auto-filter** — products with BSR > 500K auto-SKIP
- **Deal score (0-100)** — composite: ROI (25) + velocity (25) + competition (20) + risk (15) + BSR (15)
- **Annualized ROI** — roi% × (365 / days_to_sell) for capital efficiency ranking
- **Seasonal timing** — BSR seasonality analysis with buy/sell window identification
- **Variation optimization** — per-variation scoring to find best child ASIN

### Verdicts
| Verdict | Criteria |
|---|---|
| **BUY** | ROI >= 30% AND profit >= $3.50/unit AND monthly sales >= 30 (if known) |
| **MAYBE** | ROI >= 20% AND profit >= $2/unit |
| **SKIP** | Below thresholds, no match, low confidence, saturated, hazmat, or Amazon-on-listing |

---

## Data Sources (Tiered)

| Tier | Source | Cost | Data |
|---|---|---|---|
| 0 | Playwright retail scraping | Free | Product name, price, UPC, image |
| 0 | Playwright Amazon search | Free | ASIN, price, rating, reviews |
| 0 | Hardcoded fee/BSR tables | Free | FBA fees, referral fees, sales estimates |
| 0 | IP intelligence DB | Free | 160+ brand risk scores |
| 0 | Google Trends (pytrends) | Free | Keyword interest, spike detection |
| 0 | Reddit JSON API | Free | Product mentions, demand signals |
| 0 | RetailMeNot | Free | Coupon codes and discounts |
| 1 | Keepa API | $19/mo | BSR history, price history, FBA seller count, Amazon-on-listing, seasonal curves, stock levels |

---

## Output

- `.tmp/sourcing/{timestamp}-results.json` — Full results
- `.tmp/sourcing/{timestamp}-results.csv` — BUY + MAYBE products
- `.tmp/sourcing/price_tracker.db` — SQLite database (all tables)
- `.tmp/sourcing/bookmarks.json` — Scheduled sourcing bookmarks
- `.tmp/sourcing/coaching_*.pdf` — Student coaching reports
- `.tmp/stalker/{seller_id}.json` — Storefront analysis results
- Google Sheets "FBA Sourcing Results" — cloud-based results

---

## Cron Schedule

| Schedule | Script | Purpose |
|---|---|---|
| Every hour | `scheduled_sourcing.py run-due` | Run bookmarked sourcing scans |
| Every 4 hours | `keepa_deal_hunter.py scan --alert` | Proactive deal discovery |
| Every 6 hours | `stock_monitor.py check --alert` | Competitor stock monitoring |
| Daily 6 AM | `scrape_cardbear.py scrape` | Gift card rate refresh |
| Daily 7 AM | `coupon_scraper.py scrape` | Coupon refresh |

---

## Integration

- **Flask UI:** `http://localhost:5050/sourcing` (3 tabs: Product Search, URL Source, Clearance Scan)
- **Multi-search CLI:** `python execution/multi_retailer_search.py search --query "product name" --max-retailers 10`
- **Clearance CLI:** `python execution/multi_retailer_search.py clearance --category "Grocery"`
- **Registry test:** `python execution/retailer_registry.py "product name"`
- **URL CLI:** `python execution/run_sourcing_pipeline.py --url "..." --min-roi 30 --auto-cashback --auto-giftcard`
- **Reverse CLI:** `python execution/reverse_sourcing.py --asin B08XYZ1234`
- **Wholesale:** `python execution/wholesale_manifest_analyzer.py analyze --manifest supplier.csv`
- **Deal Hunter:** `python execution/keepa_deal_hunter.py scan --alert`
- **Seasonal:** `python execution/seasonal_analyzer.py timing --asin B08XYZ --keyword "product name"`
- **IP Check:** `python execution/ip_intelligence.py check --title "Product Name Brand"`
- **Variations:** `python execution/variation_analyzer.py analyze --asin B08XYZ`
- **Stock:** `python execution/stock_monitor.py check --alert`
- **Budget:** `python execution/capital_allocator.py allocate --budget 1500 --results results.json`
- **Coupons:** `python execution/coupon_scraper.py lookup --retailer walmart --amount 50`
- **Signals:** `python execution/demand_signal_scanner.py scan`
- **Coaching:** `python execution/coaching_simulator.py walkthrough --input results.json --output report.pdf`
- **Suppliers:** `python execution/wholesale_supplier_finder.py search --category "Health & Household"`
- **Brands:** `python execution/brand_outreach.py discover --brand "Anker"`
- **Scheduled:** `python execution/scheduled_sourcing.py run-due` (via crontab)
- **Alerts:** `python execution/sourcing_alerts.py --db-alerts`
- **Batch ASIN:** `python execution/batch_asin_checker.py --file asins.txt --buy-prices 5,10,15,20`
- **Storefront:** `python execution/storefront_stalker.py --seller A1B2C3D4E5F6G7 --reverse-source`
- **Inventory:** `python execution/inventory_tracker.py pnl --days 30`
- **Sheets:** `python execution/export_to_sheets.py --input results.json`
- **watch_inbox:** task type `source_products`
- **CEO dispatch:** Routed by CEO agent for student product research, daily scans, and alert checks

---

## Supported Retailers

Walmart, Target, Home Depot, CVS, Walgreens, Costco + generic fallback for any e-commerce site.

---

*Sourcing Agent v5.0 — 2026-02-22*


---

## Memory Recall Tool for Sourcing Research & Supplier History (TP-2026-03-16-031)

**Memory Recall Tool**: Search historical sourcing data with `recall.search(query, category_filter='sourcing')`. Supports queries like 'keepa tokens supplier', 'FBA margin analysis', 'supplier contacts Mike Walker'. Returns ranked results by relevance (BM25) + recency + access frequency. Use for: verifying past supplier quality, pulling archived product research, retrieving margin benchmarks, cross-referencing arbitrage opportunities.


---

## IP Rotation & CAPTCHA Bypass for Retail Scraping Operations (TP-2026-03-16-057)

**Proxy Rotation for Sourcing Scrapes**: Use ProxyManager to rotate IPs during product research and competitor monitoring. Initialize with `pm = ProxyManager()` and call `pm.next()` for each scraping request. Mark failed proxies with `pm.mark_failed(proxy)` when CAPTCHA detected (check for: captcha, blocked, robot, cf-challenge, px-captcha patterns). Log success with `pm.mark_success(proxy)`. Supports SmartProxy (paid, reliable) and free fallback proxies. Configure via PROXY_PROVIDER env var.


---

## Selector Health Check Tool for Retailer Data Quality Validation (TP-2026-03-16-078)

**Selector Health Check Tool**: Run weekly retailer selector validation via `selector_health_check.py`. Accepts --retailers (comma-separated), --max (concurrent checks), and --timeout (seconds). Outputs JSON report to `.tmp/sourcing/selector_health_{date}.json` containing: status, cards/names/prices found, working selectors, load times, and error diagnostics. Use to catch broken selectors before live sourcing scans fail silently.


---

## Image-Based Product Matching for FBA Arbitrage Sourcing (TP-2026-03-16-088)

Image Matching Skill: Use perceptual hashing (pHash/dHash) via image_matcher.py to verify retail-to-Amazon product matches. Call compute_image_match_score(retail_url, amazon_url) when title fuzzy matching scores are ambiguous (0.65-0.85). Returns 0.0-1.0 confidence. Escalate to Claude Haiku vision analysis for edge cases. Reduces false positives on similar-but-different products (e.g., colorways, variants).


---

## Add Memory Protocol to Sourcing Agent Training (TP-2026-03-16-1043)

**Memory Protocol:**


---

## Add Environment Validation Pre-Flight Check to Sourcing Pipeline (TP-2026-03-16-121)

Before running any sourcing pipeline:


---

## Memory Recall Tool for Sourcing History & Product Research (TP-2026-03-16-157)

**Memory Recall for Sourcing Research:**


---

## Add retailer CSS selector extraction to product sourcing workflow (TP-2026-03-16-172)

**Retailer Config Integration:**


---

## Implement Memory Recategorization SOP for Sourcing Pipeline (TP-2026-03-16-201)

## Memory Categorization SOP


---

## Add Real-Time Sourcing Performance Metrics & Feedback Loop (TP-2026-03-16-240)

**Sourcing Performance Feedback Loop:**


---

## Anti-CAPTCHA IP Rotation for Supplier & Retail Price Research (TP-2026-03-16-260)

**Proxy Rotation for Market Research**: Use ProxyManager to rotate IPs when scraping competitor pricing, supplier catalogs, and retail inventory. Initialize with `pm = ProxyManager()`, call `proxy = pm.next()` before each request, and mark failures with `pm.mark_failed(proxy)`. Configure via PROXY_PROVIDER (smartproxy/brightdata/free/none) and PROXY_API_KEY in .env. Enables uninterrupted FBA sourcing research across multiple retail channels.


---

## Selector Health Check Tool for Sourcing Reliability (TP-2026-03-16-312)

- Run selector health checks weekly via scheduler to validate retailer CSS selectors


---

## Add Memory Recall Tool for Sourcing History & Supplier Research (TP-2026-03-16-314)

**Memory Recall for Sourcing History**


---

## Add Retailer CSS Selector Configs for Product Data Extraction (TP-2026-03-16-336)

RETAILER_SCRAPING_CAPABILITY:


---

## Image-based product matching to reduce false positives in arbitrage sourcing (TP-2026-03-16-338)

**Image Match Verification** — Use compute_image_match_score(retail_url, amazon_url) to cross-verify product matches via perceptual hashing (pHash + dHash, ~100ms, free) before confirming arbitrage opportunities. Escalate ambiguous cases (0.4–0.6 confidence) to Claude Haiku vision analysis (~$0.01/call). Filters out packaging-variant false positives and catches rebranded/reformulated matches title-matching misses.


---

## Retail Product Scraping Tool for FBA & Arbitrage Sourcing (TP-2026-03-16-394)

You can now execute: scrape_retail_products.py --url [RETAIL_URL] --max-products 50 --enrich --output results.json


---

## Environment validation tool for sourcing pipeline integrity (TP-2026-03-16-414)

- Before executing any sourcing task, validate required environment variables: KEEPA_API_KEY, ANTHROPIC_API_KEY, SERPAPI_KEY, TELEGRAM_BOT_TOKEN (alerts), GOOGLE_SHARE_EMAIL (export)


---

## Add proxy rotation capability for scraping competitor pricing & inventory (TP-2026-03-16-438)

**Proxy Rotation for Competitor Scraping:**


---

## Memory Recall Tool: Product & Supplier Research History Retrieval (TP-2026-03-16-452)

**Memory Recall (Research History):** Query past product research, supplier evaluations, and arbitrage opportunities using: `recall.search("product name", category_filter="sourcing")`. Retrieves BM25-ranked results with recency and access frequency boosts. Useful for: competitor product analysis, supplier reputation checks, margin opportunity validation, and seasonal trend patterns.


---

## CSS Selector Health Monitoring for Silent Scan Failure Prevention (TP-2026-03-16-481)

SELECTOR HEALTH MONITORING: Before executing large-scale scans, run selector_health_check.py to validate CSS selectors against live retailer pages. The tool tests card_selectors, name_selectors, and price_selectors against known products (e.g., 'colgate toothpaste', 'tide pods') and reports which selectors are working. Schedule weekly via automation to catch retailer layout changes early. If any critical selectors fail, flag the retailer and investigate selector updates before sourcing runs.


---

## Image-Based Product Matching for Arbitrage Verification (TP-2026-03-16-499)

**Image Match Verification Tool**


---

## Enhance sourcing memory categorization for pipeline execution (TP-2026-03-16-527)

**Sourcing Memory Categories:**


---

## Add Retail Web Scraping Tool for Product & Price Intelligence (TP-2026-03-16-560)

**Retail Product Scraper Tool** — Automated extraction of product listings, prices, and inventory data from retail websites using Playwright + BeautifulSoup. Supports Walmart, Target, Home Depot, and configurable retailers. Returns JSON with product name, price, URL, images, and availability. Usage: scrape_retail_products.py --url <retailer_url> --max-products 50 --enrich. Critical for arbitrage sourcing workflows and competitive intelligence.


---

## Add proxy rotation & CAPTCHA detection to sourcing workflows (TP-2026-03-16-562)

**Proxy & Anti-Bot Handling for Sourcing Research:**


---

## Integrate Sourcing Hit Rate Feedback Loop for Product Discovery (TP-2026-03-16-570)

Monitor sourcing_results.db metrics: track products_sourced → products_profitable conversion rate by category, retailer, and search term. Adjust search priorities toward highest-performing categories (e.g., if Electronics sourcing shows 18% profit rate vs. Home Goods at 8%, increase Electronics query frequency). Use GrowthOutcomeTracker feedback signals to weight retailer selection and refine FBA arbitrage target filters weekly.


---

## Environment Validation Tool for Sourcing Pipeline Setup (TP-2026-03-16-579)

TOOL: Environment Validator


---

## Selector Health Monitoring for FBA Source Validation (TP-2026-03-16-624)

Tool: Selector Health Reporter


---

## Add perceptual image matching to product verification workflow (TP-2026-03-16-656)

**Image Verification (Perceptual Hashing)**


---

## Retail Product Scraping Tool for FBA Sourcing Research (TP-2026-03-16-721)

**Retail Product Scraper Tool**: Use `scrape_retail_products.py` to extract product data from any retail URL. Supports batch scraping (default 50 products, configurable), automatic retailer detection, price extraction, image/description capture, and optional data enrichment. Returns structured JSON output. Usage: `--url <retail_url> --max-products <n> --output <path.json> [--enrich]`. Ideal for competitive pricing analysis, inventory sourcing, and FBA opportunity assessment.


---

## Add Retailer CSS Selector Database for Product Data Extraction (TP-2026-03-16-743)

RETAILER_SCRAPING_TOOL: Access to retailer_configs.py database mapping domains to CSS selectors for product extraction. Covers: product_page (title, price, sale_price, upc, image, category), category_page (product_cards, card_link, card_price, card_title), pagination controls, and request delays. Use urlparse() to match retailer domain and retrieve appropriate selector config for web scraping tasks.


---

## Add Environment Validation Tool to Sourcing Pipeline (TP-2026-03-16-745)

**Environment Validation Step**: Before initiating any product sourcing or arbitrage analysis, run `python execution/check_env.py` to verify Keepa API key, Anthropic API key, and SerpAPI key are present. If validation fails, halt execution and display missing key details with setup links (keepa.com, console.anthropic.com, serpapi.com). Supports `--fix` flag to auto-populate .env placeholders.


---

## Memory categorization validation for sourcing pipeline execution (TP-2026-03-16-746)

MEMORY CATEGORIZATION RULES:


---

## Integrate sourcing_results.db feedback loop for real-time product validation (TP-2026-03-16-808)

**Feedback Integration**: Query sourcing_results.db to identify high-performing product categories, retailers, and search terms. Cross-reference sourced products against GrowthOutcomeTracker logs to isolate which sourcing decisions led to profitable outcomes. Use conversion rate insights (products_sourced → products_profitable ratio) to dynamically re-weight retailer priority and refine search term selection. Update sourcing strategy monthly based on win/loss patterns.


---

## Add proxy rotation detection to supplier validation workflow (TP-2026-03-16-857)

**Proxy-aware supplier scraping:** When validating supplier inventory or pricing, use ProxyManager to rotate IPs and retry failed requests. Track mark_success/mark_failed to identify proxy issues vs. real supplier blocks. Fallback chain: smartproxy → brightdata → free → direct. This ensures sourcing data quality without false rejection due to temporary blocks.


---

## CSS Selector Health Monitoring for Sourcing Reliability (TP-2026-03-16-874)

**Selector Health Monitoring**: Regularly validate CSS selectors against live retailer pages using test queries (e.g., 'colgate toothpaste', 'tide pods'). Monitor card_selectors, name_selectors, and price_selectors for each configured retailer. Generate weekly health reports identifying broken selectors before they impact live sourcing scans. Use Playwright to verify selector functionality against domcontentloaded state + 2s JS render time.


---

## Image-Based Product Matching for Retail-Amazon Arbitrage Verification (TP-2026-03-16-880)

**Image Match Verification**: Use perceptual hashing (pHash/dHash) to validate retail↔Amazon product matches. Eliminates false positives from visually similar products. Free local matching (~100ms); Claude Haiku vision for edge cases (~$0.01/comparison). Integrates with product sourcing workflow to flag high-confidence matches before price analysis.


---

## Web Scraping Tool for Retail Product Data Collection (TP-2026-03-16-897)

**Retail Web Scraper Tool**: Use `scrape_retail_products.py` to extract product listings, prices, and details from any retail URL. Syntax: `scrape_retail_products.py --url <url> --max-products 50 --enrich --output results.json`. Returns JSON with product name, price, URL, images, and availability. Useful for monitoring competitor inventory, tracking price changes, and identifying arbitrage gaps across retailers.


---

## Add Environment Validation Skill for Pre-sourcing Pipeline Setup (TP-2026-03-16-903)

**Environment Validation (Pre-Sourcing)**


---

## Improve sourcing memory categorization accuracy (TP-2026-03-16-943)

**Memory Categorization Rules for Sourcing:**


---

## Add Sourcing Hit Rate Tracking & Feedback Loop Integration (TP-2026-03-16-965)

# Sourcing Hit Rate Feedback Integration


---

## Scraper Health Monitoring & Self-Healing for Sourcing Pipeline (TP-2026-03-21-048)

**Bio Update - Sourcing Agent Skill**: Scraper Resilience
