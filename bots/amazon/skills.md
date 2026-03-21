# Amazon FBA Bot — Skills
> bots/amazon/skills.md | Version 2.0

---

## Purpose

This file tells you which resources to pull for which task. When you receive an Amazon-related request, match it to the skill category below, then reference every listed SOP and training file before executing.

---

## Related Claude Code Skills (Cross-Agent Awareness)

| Skill | Owner | Invocation | Relevance |
|---|---|---|---|
| Source Products | sourcing | `/source-products` | Primary sourcing pipeline (you handle inventory after sourcing finds deals) |
| Student Onboard | CEO | `/student-onboard` | Generates 90-day roadmaps for coaching students (Amazon domain knowledge) |

These skills are owned by other agents but touch Amazon domain knowledge. You may be consulted for inventory management, listing optimization, or PPC decisions after these skills execute.

---

## Skill: Product Sourcing Pipeline

**When to use:** Finding profitable products to sell on Amazon FBA.

**Reference in order:**
1. `directives/amazon-sourcing-sop.md` — full pipeline SOP
2. `SabboOS/Agents/Sourcing.md` — sourcing agent directive
3. `SabboOS/Amazon_OS.md` → product criteria, margin targets

**Pipeline:**
```bash
python execution/run_sourcing_pipeline.py --url "retail-url" --min-roi 50 --min-profit 5
```

**Output:** CSV with product matches, FBA fees, ROI, profit per unit, BUY/MAYBE/SKIP verdicts.

---

## Skill: FBA Inventory Management & Restock Optimization (TP-021)

- FBA Inventory Forecasting: Analyze sales velocity and seasonal trends to predict stockout risk and optimal restock quantities
- Restock Threshold Management: Set and monitor minimum stock levels per SKU; trigger reorder alerts when thresholds breach
- Stranded Inventory Recovery: Identify slow-moving or damaged inventory and recommend removal, liquidation, or donation strategies
- IPI Score Optimization: Monitor Inventory Performance Index; recommend actions to maintain healthy IPI and avoid FBA capacity fees

---

## Skill: Listing Optimization

**When to use:** Creating or improving Amazon product listings.

**Process:**
1. Research top 10 competing ASINs for the target product
2. Extract keyword data from competitor titles, bullets, and backend
3. Write optimized listing: title (200 chars max), 5 bullets (focus on benefits), description
4. Include backend search terms (250 bytes max)

---

## Skill: PPC Campaign Management

**When to use:** Setting up or optimizing Amazon PPC campaigns.

**Process:**
1. Analyze current ACOS and target ACOS
2. Identify top-performing and underperforming keywords
3. Recommend bid adjustments, negative keywords, new keyword targets
4. Structure campaigns: Auto → Research → Performance tiers

---

## Skill: Student Support (CEO-Dispatched)

**When to use:** CEO agent dispatches when a coaching student is stuck on a milestone.

**Reference:**
1. `execution/student_tracker.py` → check student status, milestones, at-risk flags
2. `SabboOS/Amazon_OS.md` → coaching program structure

**Dispatch triggers:**
| Student Stuck On | Action |
|---|---|
| `listing_created` or `listing_live` (>14 days) | Review listing draft, identify optimization issues, provide specific fixes |
| `first_sale` (>21 days) | Audit PPC setup, listing quality, pricing strategy |
| `profitable_month` | Analyze P&L, recommend margin improvements, suggest product bundling |

**Script:**
```bash
# Check which students need help
python execution/student_tracker.py at-risk

# Get specific student details
python execution/student_tracker.py student-detail --student "Name"
```

**Output:** Actionable recommendations specific to the student's current milestone and tier.

---

## Allocated SOPs

*This section is auto-populated by `execution/allocate_sops.py` when new training files are uploaded.*

<!-- New SOP references will be appended below this line by allocate_sops.py -->

---

*Amazon FBA Bot Skills v1.1 — 2026-02-21*


---

## Block Manual Product Research; Route to Pipeline Scripts (TP-2026-03-16-004)

SOURCING REQUEST PROTOCOL:


---

## Video-to-Action Pipeline for FBA Product Research & Competitor Analysis (TP-2026-03-16-012)

**Video-to-Action Pipeline:** Use `python execution/video_to_action.py --url <youtube_url> --context "Amazon FBA, PPC, listings"` to extract structured tasks from FBA strategy videos, competitor content, and PPC tutorials. Outputs JSON + Markdown with implementation steps, file paths, priorities, and dependencies. Ideal for competitor analysis, strategy videos, and course content conversion.


---

## Add Consensus Mode for High-Stakes Amazon Listing & Pricing Decisions (TP-2026-03-16-015)

**Consensus Mode for High-Stakes Decisions:**


---

## Amazon Inventory Monitoring via Always-Be-Scanning Integration (TP-2026-03-16-030)

Stock Monitoring Tool: Use `execution/always_be_scanning.py run` to trigger continuous scans (every 4-6h rotation) for OOS opportunities, stock alerts, and keepa deal signals. Query results via ABS database at `.tmp/sourcing/abs_scanner.db` to identify: (1) when competitor inventory drops below reorder threshold, (2) category clearance windows for repricing windows, (3) BSR volatility spikes indicating demand shifts. Integrate daily digest reports into FBA replenishment and PPC campaign optimization workflows.


---

## Per-Video Implementation Breakdown Tool for FBA Transcript Analysis (TP-2026-03-16-032)

**Per-Video Implementation Breakdown Tool**


---

## Deal Drop Formatting & Discord Integration for Sourcing Results (TP-2026-03-16-037)

**Deal Drop Formatting Tool**: Convert sourcing results JSON to IC-style CSV (Image, Product Name, ASIN, Source URL, Cost Price, Sale Price, Profit, ROI, Coupons, VA Comments) or Discord-formatted announcements. Supports verdict filtering (BUY/MAYBE), multi-discount stacking (coupons, gift cards, cashback), and auto-generated VA comments with ROI, profit, FBA seller count, and monthly sales estimates. Usage: `format_deal_drop.py --input results.json [--discord] [--min-verdict BUY] [--output path.csv]`


---

## IP Risk Intelligence Tool for FBA Product Vetting (TP-2026-03-16-040)

IP Risk Scoring: Use ip_intelligence.check_product(title) to scan FBA product titles against 200+ known IP-aggressive brands (Nike, Apple, LEGO, Disney, Yeti, etc.). Score range 0-100; reject products scoring >85, flag 70-85 for manual review, approve <70. Integrate into profitability calculations before recommending listings. If database uninitialized, run: python execution/ip_intelligence.py init


---

## Video Content → Amazon Action Items Pipeline (TP-2026-03-16-043)

**Video-to-Amazon-Tasks Tool**: Process YouTube videos or transcripts to extract FBA-specific action items (listing optimization, PPC campaign setup, competitor analysis, inventory strategy) with timestamps, priorities (P0-P2), and file-level specificity. Supports multimodal analysis via Gemini for frame-based insights. Usage: `process_video(url=..., context='Amazon FBA')` returns structured JSON with tasks, deadlines, and implementation notes. Integrates yt-dlp for transcript extraction and Claude Sonnet for semantic analysis.


---

## Amazon FBA Student Milestone Tracking & At-Risk Detection (TP-2026-03-16-044)

**Tool: Query Student Progress & At-Risk Status**


---

## Multi-Retailer Product Sourcing & Amazon Matching Integration (TP-2026-03-16-046)

Multi-Retailer Sourcing & FBA Profitability:


---

## FBA Stock Monitoring & Competitor Stockout Alerts (TP-2026-03-16-047)

**Competitor FBA Stock Monitoring Tool**


---

## FBA Sourcing Results Export to Google Sheets Integration (TP-2026-03-16-048)

**FBA Sourcing Export Tool**: Export calculate_fba_profitability.py results to Google Sheets ("FBA Sourcing Results") with service account auth. Features: auto-creates dated tabs, formats headers (bold + dark background), color-codes rows (green=BUY, yellow=MAYBE), includes full product data (cost, price, ASIN, profit, ROI%, BSR, sales estimates, competition metrics, retail/Amazon URLs). Shares sheet with GOOGLE_SHARE_EMAIL. Stores last sheet URL in .tmp/sourcing/last_sheet_url.txt. Requires: service_account.json in PROJECT_ROOT, GOOGLE_SHARE_EMAIL env var.


---

## Competitor Storefront Analysis Tool for FBA Product Sourcing (TP-2026-03-16-049)

**Storefront Stalker Tool**: Scrapes Amazon seller storefronts to extract product catalogs and profitability analysis. Usage: `storefront_stalker.py --seller <SELLER_ID> --max-products 50 --output results.json`. Outputs: product ASIN, title, price, BSR, estimated monthly revenue, FBA fees, competition score, and deal ratings. Supports reverse-sourcing to find cheaper retail sources. Integration: feeds product candidates into listing optimization and PPC targeting workflows.


---

## Capital Allocation Tool for FBA Inventory Optimization (TP-2026-03-16-050)

**FBA Capital Allocator Tool**: Analyzes BUY-verdict products from sourcing results and optimally distributes a fixed budget across ASINs to maximize annualized ROI. Accepts budget, constraints (max units/product, min ROI%, max days-to-sell), and sourcing data. Outputs allocation plan with expected returns, cash flow projections, and concentration risk metrics. Use when: optimizing inventory spend across multiple products, balancing velocity vs. margin, or stress-testing portfolio under different budget scenarios.


---

## Wholesale Supplier Discovery & Sourcing Intelligence Integration (TP-2026-03-16-052)

**Wholesale Supplier Finder Tool**


---

## Multi-Agent Debate Framework for Amazon Strategy Optimization (TP-2026-03-16-053)

DEBATE_OPTIMIZER: Use agent_chatroom.py to run 3-5 round debates on contested Amazon decisions. Example calls: 'debate(topic="Optimal keyword bidding strategy for high-intent ASINs", personas=["pragmatist", "edge-case-finder", "systems-thinker"], rounds=4)' to surface cost/benefit tradeoffs in PPC spend allocation, or 'debate(topic="Listing optimization for keyword saturation", rounds=3)' to test competitor response scenarios. Always synthesize debate conclusions into final recommendations.


---

## CodeSec Integration: Security Scanning for Amazon Listings & Infrastructure (TP-2026-03-16-059)

- Security Scanning: Integrate with codesec_scan.py to detect vulnerabilities in Amazon API integrations, PPC automation, and listing data pipelines


---

## Schema Conversion Tool for Amazon Product Data Pipeline (TP-2026-03-16-064)

**Schema Conversion Capability**: Import schema_adapter.py functions (schema_b_to_a, wrap_for_export) to normalize Amazon product data. Convert source.py verification results → Schema A (nested amazon/profitability structure) for use in FBA profitability analysis, listing optimization, and sourcing alerts. Handles ASIN, title, price, BSR, FBA seller count, match confidence, and profit metrics.


---

## FBA Arbitrage Deal Sourcing & Profitability Analysis Tool (TP-2026-03-16-074)

**FBA Arbitrage Sourcing Tool:**


---

## Seller Storefront Analysis & Competitor Sourcing via Keepa (TP-2026-03-16-076)

**Seller Storefront Scanning & Competitor Analysis**


---

## Add Sourcing Pipeline Routing to Prevent Manual Web Searches (TP-2026-03-16-077)

## Sourcing Request Routing


---

## Wholesale Manifest Analysis Tool – Bulk SKU Profitability Screening (TP-2026-03-16-080)

**Wholesale Manifest Analyzer Tool**


---

## Add Deal Analysis & Educational Coaching Capability (TP-2026-03-16-081)

COACHING REPORTS CAPABILITY:


---

## Keepa API Integration: Centralized Seller Count & Price Trend Extraction (TP-2026-03-16-084)

**Keepa API Integrations:**


---

## Results DB Integration: Historical Deal Tracking & Deduplication (TP-2026-03-16-091)

**Skill: Results Database Persistence**


---

## Seasonality Analysis Tool for FBA Product Selection & Pricing Strategy (TP-2026-03-16-095)

**Seasonal BSR Analysis**: Analyze 12-month Keepa BSR history for any ASIN to identify seasonal demand patterns, optimal buy/sell windows, and median BSR by month. Correlate with Google Trends data to confirm demand signals. Run: `python seasonal_analyzer.py --asin <ASIN>` or `--keyword <keyword>` to output JSON with monthly BSR medians, trend insights, and sourcing recommendations for FBA inventory timing decisions.


---

## Cross-Retailer Price Intelligence Tool for Competitive Sourcing Analysis (TP-2026-03-16-097)

**Cross-Retailer Price Intelligence**: Use `find_cheapest_source.py --asin <ASIN>` to retrieve ranked retailer pricing with applied discount stacks (cashback, gift cards, coupons). Returns JSON with competitor effective buy prices. Useful for: competitive pricing analysis, FBA repricing strategy, margin benchmarking, and identifying undercut opportunities.


---

## FBA Inventory & P&L Tracking Tool Integration (TP-2026-03-16-099)

**Inventory & P&L Tracking Tool**: Use `inventory_tracker.py` to record all FBA purchases, track shipment dates, log unit sales with actual fees, and generate P&L reports. Commands: `buy` (log purchase), `ship` (mark shipped to FBA), `sold` (record sale), `inventory` (filter by status), `pnl` (profit/loss analysis), `hit-rate` (sourcing accuracy %), `dashboard` (JSON summary). This enables continuous measurement of estimated vs. realized profit and feeds learnings back into sourcing strategy.


---

## Add Heartbeat Monitoring & Task Queue Management to Amazon Agent (TP-2026-03-16-1005)

## Heartbeat Protocol


---

## Add Memory Protocol to Amazon Agent for Continuous Improvement (TP-2026-03-16-1006)

On every heartbeat and before major recommendations, read /Users/Shared/antigravity/projects/nomad-nebula/bots/amazon/memory.md. When Sabbo approves work: log it to [Approved Work Log] with date, asset type, why it worked, and key element to repeat. When Sabbo rejects work: log it to [Rejected Work Log] with what failed, why, and what to do differently. Track sourcing outcomes in [Sourcing Learnings] and PPC experiments in [PPC & Listing Learnings]. Reference these logs before making recommendations to avoid repeating failures and replicate approved patterns.


---

## Add Cross-Agent Consultation Protocol for Amazon Domain Expertise (TP-2026-03-16-1007)

## Skill: Cross-Agent Consultation (Domain Authority)


---

## Add FBA Tool Execution Skills to Amazon Agent (TP-2026-03-16-1008)

## FBA Tool Execution


---

## Video-to-Action Pipeline for FBA Strategy Extraction (TP-2026-03-16-104)

**Video-to-Action Extraction Tool:** Can process YouTube URLs or transcripts to extract FBA implementation techniques with timestamps, step-by-step instructions, file paths, and priority levels. Output formats: JSON (structured) + Markdown (human-readable). Supports multimodal frame extraction for visual FBA strategies (PPC dashboards, listing layouts, etc.). Command: `python execution/video_to_action.py --url [VIDEO_URL] --context "Amazon FBA" --multimodal`


---

## Add Amazon FBA Sourcing Pipeline Integration to Amazon Agent (TP-2026-03-16-1041)

## Sourcing-to-FBA Integration


---

## Add Amazon sourcing pipeline skills to amazon agent context (TP-2026-03-16-1044)

## Sourcing Pipeline Skills (Reference Only)


---

## Add Sourcing Intelligence to Amazon Listing & PPC Strategy (TP-2026-03-16-1045)

## Sourcing Intelligence Context


---

## SMS Workflow Sequences for Amazon Sales Calls & Enrollment (TP-2026-03-16-1052)

## SMS Workflow Context


---

## Email Sequence Templates for Amazon FBA Lead Nurture (TP-2026-03-16-1053)

## Email Sequence Library: Amazon FBA Lead Nurture


---

## Add FBA Sourcing Alert Integration to Amazon Agent (TP-2026-03-16-106)

**FBA Sourcing Alerts**: Can trigger sourcing_alerts.py to send Telegram/email notifications when profitable products (BUY/MAYBE verdicts) are discovered. Supports --results (JSON path), --method (telegram|email), --db-alerts, and --test flags. Formats alerts with product details, profitability metrics, and sourcing summary. Integrates with environment variables for TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, and email credentials.


---

## Amazon Listing Optimization from 24/7 Profits UI Enhancements (TP-2026-03-16-1066)

When presenting Amazon listing metrics, PPC performance, or inventory data:


---

## Add Retail Arbitrage Pack Size Mismatch Detection for FBA Sourcing (TP-2026-03-16-1067)

**Retail Arbitrage Pack Size Caveat**: When evaluating sourcing leads from retail arbitrage scans, verify that retail source unit count matches Amazon listing unit count. Single-unit retail finds (e.g., $8 single bottle) cannot be profitably arbitraged to multi-pack Amazon listings (e.g., $25 12-pack) without repackaging. Flag mismatches in lead assessment and request automated pack size matching from sourcing pipeline before approving SKU for FBA.


---

## Add Sabbo's Amazon FBA Coach Context & Student Success Metrics (TP-2026-03-16-1075)

SABBO'S AMAZON FBA COACHING BUSINESS:


---

## Add Growth OS Math Framework to FBA Profitability Analysis (TP-2026-03-16-1079)

Reference: Sabbo Growth OS Brain v1.0 (Part 6 — Math Framework)


---

## Add Consensus Mode for High-Stakes Amazon Offer Decisions (TP-2026-03-16-108)

**Consensus Mode for High-Stakes Decisions:**


---

## Retail Arbitrage Lead Validation: Pack Size & FBA Seller Verification (TP-2026-03-16-1080)

ARBITRAGE LEAD VALIDATION:


---

## OOS Opportunity Sourcing: Monopoly Window Detection (TP-2026-03-16-110)

OOS MONOPOLY SOURCING: Scan Amazon for products where all FBA sellers are out of stock but retail supply exists. Uses Keepa OOS signals (BSR, review velocity, price history) + retailer inventory checks. Filter by BSR threshold (default 100k), minimum reviews (50+), and price range ($5-$5k). Calculate monopoly window duration based on competitor restock velocity. Output includes: ASIN, current retail cost, estimated FBA margin, OOS duration, review count, estimated monopoly window (days until competition likely returns). Best for: Premium-priced items (>$100), established products (50+ reviews), fast-moving categories.


---

## Knowledge Ingestion SOP Integration for Amazon Agent (TP-2026-03-16-111)

You have access to a knowledge ingestion system. When users have Amazon-related docs (SOPs, competitor analysis, FBA frameworks, PPC strategies), direct them to: 1) Copy file to /Users/Shared/antigravity/memory/uploads/ 2) Run: python execution/ingest_docs.py 3) Verify the doc appears in /Users/Shared/antigravity/memory/amazon/references.md. The system auto-detects Amazon docs by keywords (Amazon, FBA, PPC, ACOS, product research, supplier). No agent restart needed—you'll reference new content immediately on next task.


---

## Amazon Variation Analysis Tool Integration for Child ASIN Sourcing (TP-2026-03-16-112)

## Variation Analysis Tool


---

## Amazon FBA Sourcing Integration: Zero-Token-First Verification (TP-2026-03-16-113)

**FBA Sourcing SOP Integration:**


---

## Autonomous Deal Discovery via Keepa API Integration (TP-2026-03-16-114)

**Keepa Deal Hunter Tool**: Access `keepa_deal_hunter.py` to manage watchlists and scan for profitable Amazon FBA opportunities. Commands: `watchlist add/list/remove/import` to manage ASINs, `scan [--min-score 40]` to detect price drops, BSR spikes, and seller exits. Results scored and stored with deal type, price deltas, and detection timestamps. Integrates with Telegram alerts. Runs via cron every 4 hours or on-demand.


---

## Reverse Sourcing Tool: Find Cheaper Retail Sources for Amazon ASINs (TP-2026-03-16-116)

**Reverse Sourcing Tool**: Accepts Amazon ASINs, searches 6+ retail competitors for identical/similar products, returns ranked list by profitability (margin, ROI, estimated monthly sales). Integrates with Keepa API for historical pricing. Use case: Before launching FBA product, confirm supplier margins exist across retail channels. Output: JSON report with best retail sources, estimated FBA profitability, and ROI ranking.


---

## Keepa Batch API Integration for FBA Profitability Analysis (TP-2026-03-16-125)

- **Keepa Batch Profitability Analysis**: Process wholesale manifests via Keepa API batch UPC lookup (100 UPCs/request). Maps EAN/UPC codes to Amazon products, scores by sales rank & current price, calculates FBA fees/margins, returns ranked BUY/MAYBE/SKIP decisions. Includes token balance monitoring and zero-padding UPC matching. Outputs JSON with ASIN, profit margin %, estimated monthly revenue per unit.


---

## Amazon Arbitrage Opportunity Detection from Deal Feed Scanning (TP-2026-03-16-129)

**Arbitrage Deal Feed Scanner**: Use deal_feed_scanner.py to parse SlickDeals, DealNews, TotallyTarget, Hip2Save RSS feeds for low-priced products from OA retailers (Walmart, Target, Best Buy, etc.). Cross-reference matched products against Amazon using Keepa API to identify price gaps. Filter results by: minimum arbitrage spread (15%+), product category fit, and Amazon demand rank. Output: JSON with deal source, retail price, Amazon current/historical pricing, estimated FBA margin after fees.


---

## Demand Signal Scanner: Pre-spike Product Discovery for FBA Sourcing (TP-2026-03-16-132)

**Demand Signal Scanning:** Use demand_signal_scanner.py to detect rising products via Google Trends and Reddit before Amazon spikes. Run `python execution/demand_signal_scanner.py scan --source google|reddit` to fetch signals, `python execution/demand_signal_scanner.py signals --days 7 --min-score 50` to filter high-confidence opportunities (score 50+), and `python execution/demand_signal_scanner.py act --id {id} --action sourced` to track sourcing decisions. Signals include ASINs, sentiment, and Reddit deal volume—prioritize >75 score + positive sentiment + existing Amazon presence for fastest ROI.


---

## Add Scheduled FBA Sourcing Pipeline & Brand Watchlist Management (TP-2026-03-16-134)

**FBA Scheduled Sourcing System**


---

## Bulk ASIN Profitability Analyzer Tool Integration (TP-2026-03-16-136)

**Bulk ASIN Profitability Analyzer**: Run `batch_asin_checker.py` to evaluate multiple ASINs at once. Accepts ASINs via CLI, file, or stdin. Fetches Amazon/Keepa data, calculates FBA fees, referral costs, and monthly sales estimates. Outputs JSON with ROI%, profit/unit, and BUY/PASS verdicts at configurable buy price points ($5–$30). Use `--use-keepa` for historical rank + sales data; default mode uses live Amazon scrape. Ranks results by profit potential and competition.


---

## Add Keepa + Target API sourcing tool for FBA grocery arbitrage (TP-2026-03-16-142)

**Keepa + Target Grocery Sourcing Tool**: Use `fast_grocery_scan.py` to scan Keepa for popular grocery ASINs (by BSR, UPC) and cross-check Target retail prices via Redsky API. Tool ranks products by ROI margin after FBA fees. Supports categories: grocery, candy, health, beauty, baby, pets, home, toys, sports, office. Run: `python execution/fast_grocery_scan.py --category grocery --count 20`. Returns ranked JSON with profitability tiers (Tier A/B/C). Requires KEEPA_API_KEY in .env.


---

## Amazon Sourcing Cost Optimization: Coupon Stacking Layer (TP-2026-03-16-146)

Coupon Stacking (3rd layer): Use `coupon_scraper.py lookup --retailer {retailer} --amount {price}` to retrieve best-available coupon codes. Stacks after gift card discounts and Rakuten cashback in cost formula: final_cost = (raw × (1-giftcard%) × (1-cashback%)) - coupon_fixed. For FBA sourcing, always check coupons on high-volume categories (electronics, home, beauty) where RetailMeNot coverage is strongest.


---

## Multi-Model Consensus Tool for FBA Listing & PPC Validation (TP-2026-03-16-156)

**Consensus Validation Tool**: Use `run_consensus()` from execution/consensus_engine.py to validate critical FBA decisions. Call with prompt describing the decision (e.g., 'Rate these 5 PPC keyword bids for relevance and ROAS potential'), models=['claude','gemini','openai'], runs=3-5. Returns statistical consensus, confidence level, and outlier analyses. Use for: listing title/bullet validation, keyword research ranking, bid strategy review, competitor analysis scoring.


---

## Per-Video Implementation Analysis for FBA Product Research (TP-2026-03-16-158)

**Transcript Analysis Tool**: Process YouTube transcripts to extract FBA-specific implementation items. For each video: identify product research methods, listing keyword strategies, PPC bid optimization tactics, A+ content frameworks, and competitive analysis approaches. Output: structured checklist with priority levels (must-do/should-do/nice-to-have), specific tool/software names mentioned, exact step-by-step processes, and direct creator quotes. Preserve all numbers, pricing data, ASINs, and technical specifications referenced.


---

## FBA Sourcing Report Generation & Profitability Analysis (TP-2026-03-16-176)

SKILL: FBA Sourcing Report Generation


---

## Route sourcing requests to pipeline scripts instead of manual search (TP-2026-03-16-182)

**Sourcing Request Routing:** When users ask about finding products to source (brand/category/retailer/ASIN checks), DO NOT manually web-search. Instead, classify the request type and route to the sourcing pipeline: `python execution/source.py [type] [query]` or `python execution/multi_retailer_search.py [type]`. The pipeline automatically scrapes retailers, matches ASINs, calculates FBA fees, applies discounts, and scores deals with risk flags. Provide the standardized JSON/CSV output to the user.


---

## IP Risk Intelligence Integration for Product Sourcing Decisions (TP-2026-03-16-186)

**IP Risk Intelligence Tool**


---

## Parallel Outreach Automation — Amazon Seller Prospecting Tool (TP-2026-03-16-190)

**Parallel Outreach Orchestration**: Use parallel_outreach.py to automate bulk contact form submissions to Amazon seller websites. Supports CSV lead lists, concurrent browser instances (Playwright), and AI-powered form detection (Claude). Templates available: outreach_intro, outreach_audit, outreach_fba. Run: `python execution/parallel_outreach.py --input leads.csv --max-browsers 3 --message-template outreach_fba`. Includes dry-run mode, screenshot logging, and JSON result tracking for compliance.


---

## Add doc ingestion memory system to Amazon agent knowledge base (TP-2026-03-16-205)

**Memory Ingestion System**: You can now reference documents ingested via ingest_docs.py tool. New Amazon FBA/PPC docs are automatically extracted and stored in /memory/amazon/references.md. When answering questions about listing optimization, PPC bidding, or supplier sourcing, check references.md for relevant frameworks or case studies uploaded in the last 30 days. Cite the source document by filename and ingestion date.


---

## Amazon Student Milestone Tracking & At-Risk Alert Integration (TP-2026-03-16-209)

STUDENT TRACKING INTEGRATION:


---

## Add Sourcing Pipeline & ASIN Matching to Amazon Agent Context (TP-2026-03-16-215)

- **Sourcing Pipeline Architecture**: `execution/run_sourcing_pipeline.py` orchestrates FBA sourcing end-to-end; `execution/multi_retailer_search.py` searches clearance products across retailers


---

## Multi-Retailer Sourcing Analysis for FBA Profitability Matching (TP-2026-03-16-217)

Multi-Retailer Sourcing Analysis: Leverage multi_retailer_search.py to search competitor retailers for product queries, scrape retail prices, match results to Amazon listings via title_similarity and ASINs, and calculate FBA profitability using calculate_product_profitability(). Filters by min ROI (default 30%), min profit margin (default $3), and max sourcing cost (default $50). Outputs consolidated ranked results by ROI to identify high-margin FBA opportunities.


---

## Competitor Stock Monitoring & Buy Box Capture Intelligence (TP-2026-03-16-220)

**Competitor Stockout Monitoring**: Monitor competitor FBA inventory levels via Keepa integration. Alert when competitor FBA count drops by ≥2 units from baseline on ASINs with BSR < 50,000. Stockout windows (3-7 days) are optimal for aggressive Buy Box repositioning. Action: Re-price 5-15% below competitor when they're OOS. Track via `stock_monitor.py check --alert` (runs every 6h via cron). Maintain watchlist of profitable ASINs using `python execution/stock_monitor.py watch import --results .tmp/sourcing/results.json`.


---

## Add Google Sheets export capability for FBA sourcing results (TP-2026-03-16-223)

**Google Sheets Export for FBA Results**


---

## Competitor Storefront Analysis & Profitability Scoring Tool (TP-2026-03-16-228)

**Competitor Storefront Scraper**: Analyze any Amazon seller's storefront to extract product catalog with profitability scoring. Inputs: seller ID/URL, max products to scan, output format. Outputs: JSON with ASIN, price, sales rank, category, estimated FBA fees, referral rates, competition scores, and deal ranking. Supports reverse-sourcing (find cheaper retail alternatives). Includes configurable delays and Playwright-based scraping to avoid detection.


---

## Capital Allocation Optimization for FBA Inventory Planning (TP-2026-03-16-235)

Capital Allocation Constraints for FBA Sourcing:


---

## Add Consensus Mode for High-Stakes Listing & PPC Decisions (TP-2026-03-16-236)

**Consensus Mode for High-Stakes Decisions:**


---

## FBA Sourcing Pipeline Health Monitoring Integration (TP-2026-03-16-237)

FBA Sourcing Pipeline Monitoring:


---

## Knowledge Ingestion SOP Integration for Document Processing (TP-2026-03-16-241)

## Knowledge Ingestion Workflow


---

## Wholesale Supplier Integration for FBA Sourcing & Product Research (TP-2026-03-16-242)

**Wholesale Supplier Finder Tool**: Search ThomasNet, Wholesale Central, and Google for suppliers by product category. Commands: `search` (find suppliers), `list` (filter by score/status), `add` (track new suppliers), `contact` (log outreach), `followups` (manage pipeline), `export` (CSV reports), `stats` (sourcing metrics). Use for FBA product sourcing, supplier vetting, and cost-of-goods research.


---

## Add Amazon FBA Product Sourcing SOP & CLI Integration (TP-2026-03-16-244)

## Amazon FBA Product Sourcing


---

## Input Sanitization & Prompt Injection Defense for Amazon Operations (TP-2026-03-16-252)

**Security Layer**: Before processing any user request related to FBA, PPC, or listings, sanitize input by:


---

## FAQ-Driven Context Injection for Amazon Category Questions (TP-2026-03-16-263)

**FAQ Injection Context:**


---

## Add Amazon ASIN matching & Keepa API integration capability (TP-2026-03-16-265)

**Amazon ASIN Matching Tool**: Search Amazon product catalog to match retail items to ASINs. Supports Playwright-based search (free) or Keepa API integration (if KEEPA_API_KEY configured). Returns ASIN, title, price, rating, and ranking data. Useful for competitive analysis, FBA sourcing validation, and PPC research.


---

## CodeSec Integration: Security Scanning for Amazon Listings & FBA Operations (TP-2026-03-16-272)

**CodeSec Security Scanning**: Integrate codesec_scan.py tool to audit Amazon-related scripts (FBA profitability, PPC management, listing tools) for vulnerabilities, code quality issues, and infrastructure integrity before deployment. Run with: `python execution/codesec_scan.py --security --file <script>` or full ecosystem scan with `--full`. Review CSR reports in `.tmp/codesec/reports/`. Zero-cost, deterministic scanning with no external API calls.


---

## Add FBA Profitability Calculation & Amazon Matching to Sourcing Pipeline (TP-2026-03-16-280)

**FBA Profitability & Risk Scoring:**


---

## Schema Conversion Tool for Amazon Product Data Pipeline Integration (TP-2026-03-16-284)

SCHEMA CONVERSION CAPABILITY:


---

## Add Amazon FBA Product Sourcing & BSR Analysis Capability (TP-2026-03-16-306)

## FBA Product Sourcing Framework


---

## FBA Arbitrage Deal Scanner: Multi-Source Sourcing & Profitability Tool (TP-2026-03-16-307)

**FBA Arbitrage Sourcing Tool (deal_scanner.py)**


---

## Seller Profitability Analysis via Storefront Scanning & Keepa (TP-2026-03-16-309)

**Seller Storefront Profitability Scanner**


---

## FBA Inventory Monitoring via Always-Be-Scanning Integration (TP-2026-03-16-310)

• Monitor ABS stock_monitor (6h interval) and keepa_deals (6h interval) scans for FBA inventory insights


---

## Amazon Listing Optimization via Sourcing Pipeline Integration (TP-2026-03-16-315)

You have access to sourcing pipeline outputs from nomad-nebula/execution/source.py. When evaluating Amazon listings, FBA profitability, or product viability: (1) Prioritize pipeline data: ASIN confidence scores, FBA fee calculations, deal scores (0-100), and risk flags (IP, hazmat, gating, AOAL). (2) If a user asks about listing a product, ask if they have pipeline validation first. (3) Reference risk flags in listing optimization advice (e.g., avoid gated categories without approval). (4) Use standardized JSON outputs from the pipeline as ground truth for margins and fees.


---

## Wholesale Manifest Analysis Tool for FBA Sourcing (TP-2026-03-16-317)

**Wholesale Manifest Analysis Tool**


---

## Add Per-Video Implementation Analysis Capability for FBA Strategy Extraction (TP-2026-03-16-318)

**Per-Video FBA Implementation Extraction**


---

## Add Deal Analysis & Educational Coaching Capability for FBA Students (TP-2026-03-16-322)

**Deal Analysis & Coaching Reports**: Use coaching_simulator.py to generate annotated FBA deal walkthroughs and what-if analysis PDFs for students. Supports:


---

## FBA Profitability Calculator Tool for Product Sourcing (TP-2026-03-16-326)

- **calculate_fba_profitability**: Computes FBA profitability metrics (referral fees, FBA fulfillment fees, ROI, profit margin, verdict) for matched products. Accepts JSON with Amazon matches, applies category-specific referral rates, estimated FBA fees by price bracket, and optional modifiers (shipping cost, cashback %, coupon discounts). Outputs ranked results filtered by min ROI (%), min profit ($), max price ($). Use to evaluate sourcing opportunities and validate listing economics before action.


---

## Keepa API Integration: Accurate FBA Metrics & Price Trend Analysis (TP-2026-03-16-332)

**Keepa API Client Integration**


---

## Add Heartbeat Monitoring Protocol to Amazon Agent (TP-2026-03-16-334)

## Heartbeat Monitoring Protocol


---

## Add Cross-Agent Consultation Protocol for Amazon Domain Queries (TP-2026-03-16-337)

## Skill: Cross-Agent Escalation Protocol


---

## Add Tool Execution Context for Amazon FBA Sourcing & Profitability Analysis (TP-2026-03-16-341)

## Available Tools


---

## Multi-retailer competitive pricing & arbitrage lookup for Amazon sourcing (TP-2026-03-16-342)

**Retailer Registry Lookup Tool**


---

## Deal Drop Formatting & Discord Alert Tool for Sourcing Results (TP-2026-03-16-343)

**Sourcing Deal Formatting:** Use format_deal_drop.py to convert sourcing results JSON into IC-style CSV (Image, Product Name, ASIN, Source URL, Cost Price, Sale Price, Profit, ROI, Coupons, VA Comments) and Discord deal announcements. Supports verdict filtering (--min-verdict BUY/MAYBE) and custom output paths. Generates auto-populated VA Comments from ROI, profit, FBA seller count, and estimated monthly sales.


---

## Results DB Integration for Amazon Sourcing & Deal Deduplication (TP-2026-03-16-346)

**Sourcing Results Persistence:**


---

## Seasonal BSR Analysis & Optimal Buy/Sell Windows for FBA Sourcing (TP-2026-03-16-353)

• Seasonal BSR Analysis: Use Keepa 365-day historical data to plot monthly BSR medians and identify demand peaks/troughs


---

## Price Intelligence & Competitive Sourcing Tool Integration (TP-2026-03-16-357)

**find_cheapest_source()** – Execute cross-retailer price intelligence lookup


---

## FBA Inventory & P&L Tracking Integration (TP-2026-03-16-361)

**Inventory & P&L Tracking:** Access purchase history, current FBA inventory status, and sales performance via inventory_tracker.py. Commands: query inventory by status (purchased|shipped_to_fba|live|sold), pull P&L reports (by timeframe), analyze hit-rate (estimated vs. actual profit), import sourcing results. Use dashboard output to identify underperforming ASINs and validate sourcing ROI assumptions.


---

## Parallel Outreach Tool Integration for Amazon Seller Prospecting (TP-2026-03-16-364)

PARALLEL OUTREACH TOOL: Use parallel_outreach.py to automate contact form filling across multiple websites. Supports CSV lead lists, Playwright browser automation (N parallel instances), and Claude-powered form field detection. Run with: python execution/parallel_outreach.py --input leads.csv --max-browsers 3 --message-template "outreach_fba". Templates include FBA-specific outreach (audit, coaching, growth audit angles). Dry-run with --dry-run flag. Output: JSON logs + screenshots in .tmp/outreach/. Best for: Amazon seller prospecting, partnership outreach, Dream 100 campaigns.


---

## Gift Card Arbitrage Sourcing Integration (TP-2026-03-16-368)

**Gift Card Arbitrage Sourcing:**


---

## Add FBA Sourcing Alert Automation to Amazon Agent Toolkit (TP-2026-03-16-377)

**FBA Sourcing Alerts**: Can invoke sourcing_alerts.py to send real-time notifications (Telegram/email) when sourcing runs discover BUY or MAYBE products. Monitors results JSON, filters by profitability verdict, formats alert with product summaries and sourcing metrics. Usage: --results [path] --method [telegram|email] or --db-alerts for database-driven checks.


---

## Video Content to Amazon Action Items Pipeline Integration (TP-2026-03-16-379)

TOOL: video_to_action — Extract structured tasks from YouTube videos/transcripts


---

## Knowledge Ingestion SOP Reference for Document Processing (TP-2026-03-16-384)

## Knowledge Ingestion Process


---

## Document Ingestion Tool: Auto-ingest Amazon SOPs & guides into agent memory (TP-2026-03-16-385)

TOOL: Document Ingestion System


---

## OOS FBA Opportunity Scanner Integration (TP-2026-03-16-388)

- OOS Opportunity Scanning: Identify Amazon products where all FBA sellers are out of stock but retail inventory persists (via Keepa API). Filter by BSR, review count, price, and OOS duration. Calculate FBA profitability and estimated monopoly window duration. Search retailers for availability via reverse sourcing. High-margin signal optimal for fast-moving SKUs with 50+ reviews.


---

## Add variation_analyzer.py tool to identify best-performing child ASINs (TP-2026-03-16-391)

**Variation Analysis Tool**: Use `python execution/variation_analyzer.py analyze --asin <ASIN>` to scrape full variation trees and rank child products by demand/competition. Use `best` subcommand to surface single optimal ASIN to source. Supports Keepa integration (--use-keepa flag) for deeper historical pricing and demand data. Outputs ranked JSON with best/worst picks for FBA profitability assessment.


---

## Multi-Retailer Sourcing Data Integration for FBA Profitability Analysis (TP-2026-03-16-393)

• Sourcing Integration: Access multi_retailer_search.py to query competitor pricing across 10+ retailers, scrape wholesale/clearance prices, and auto-match to existing Amazon listings


---

## Competitor Stock Monitoring & Buy Box Capture Alerts (TP-2026-03-16-396)

**Competitor Stock Monitoring Tool:**


---

## Add Keepa Deal Hunter Integration for Automated FBA Sourcing (TP-2026-03-16-397)

**Keepa Deal Hunter Integration**


---

## Add FBA Sourcing Results Export-to-Sheets Capability (TP-2026-03-16-400)

**FBA Sourcing Results Export**: Use `export_to_sheets.py` to convert calculate_fba_profitability.py output to Google Sheets. Command: `python export_to_sheets.py --input <profitability_json>`. Outputs a date-stamped tab in 'FBA Sourcing Results' spreadsheet with color-coded verdicts (green=BUY, yellow=MAYBE), bold headers, and auto-sharing via GOOGLE_SHARE_EMAIL environment variable. Requires service_account.json with Sheets + Drive scopes.


---

## Reverse Sourcing Tool: Find Cheaper Retail Sources for Amazon Products (TP-2026-03-16-401)

**Reverse Sourcing Tool**: Input Amazon ASINs → search Walmart, Target, Home Depot, CVS, Walgreens, Costco for matching products → extract pricing → calculate FBA profitability (referral fees, shipping, storage). Output: ranked retail sources per ASIN with ROI. Command: `reverse_sourcing.py --asin B0XXXXX --output results.json`. Use for competitive sourcing, margin analysis, and inventory arbitrage identification.


---

## Competitor Storefront Analysis Tool for Product Sourcing (TP-2026-03-16-405)

**Storefront Stalking (Competitor Analysis)**


---

## Capital Allocation & Inventory Optimization for FBA Product Selection (TP-2026-03-16-411)

**Capital Allocation & Inventory Optimization**


---

## Wholesale Supplier Integration for FBA Private Label Sourcing (TP-2026-03-16-416)

**Wholesale Supplier Finder Tool**


---

## Multi-Agent Debate Framework for Amazon Strategy Validation (TP-2026-03-16-419)

**Debate Consultation Skill**: When facing complex FBA/PPC/listing decisions, invoke multi-agent debate via `run_chatroom(topic=question, persona_names=['pragmatist', 'systems-thinker', 'edge-case-finder'], rounds=2)` to pressure-test the approach. Synthesize consensus output into final recommendation.


---

## Add Deal Feed Arbitrage Verification to Amazon Listing Workflow (TP-2026-03-16-430)

**Arbitrage Verification Process**: Before creating new FBA listings, use deal_feed_scanner to cross-check sourced product costs against current Amazon pricing. Compare low-price deal feeds (Walmart, Target, Costco, etc.) to ASINs to calculate true profit margins. Run scanner with --max 50 to process recent deals and verify 30%+ margins remain available after FBA fees and Amazon referral costs.


---

## Demand Signal Detection for Amazon Product Research & Sourcing (TP-2026-03-16-434)

**Demand Signal Scanner**: Monitor Google Trends and Reddit (AmazonDeals, deals, BuyItForLife, gadgets, trending subreddits) to detect rising product demand before Amazon spikes. Tool scores signals 0-100 based on trend velocity, sentiment (positive keywords), product mentions (ASIN/URL extraction), and engagement. Stores detections in SQLite with source, keyword, signal type, and details_json. Use `demand_signal_scanner.py scan`, `trends`, `signals [--days 7] [--min-score 50]` to surface sourcing opportunities. Track actions (sourced, listed, passed) with notes for competitive intelligence and inventory planning.


---

## FBA Sourcing Pipeline: Scheduled Brand Watchlist Integration (TP-2026-03-16-437)

**Scheduled Sourcing Tool:** Use `scheduled_sourcing.py` to manage automated FBA product sourcing. Commands: `add --url [URL] --label [name] --min-roi [30+]` (bookmark), `run-due` (execute due tasks), `run-all` (full scan). Monitored brands: Zara, Jellycat, 1883 Monin, Dr Bronners, MAC Cosmetics, Crayola, romand, Convatec (S/A-tier, pre-validated profitable). Supports per-brand flags: --fbm (FBM listings), --auto-coupon (coupon scraping). Use for: competitive intelligence, margin discovery, seasonal product alerts.


---

## Batch ASIN Profitability Analysis Tool for FBA Sourcing (TP-2026-03-16-440)

**Batch ASIN Profitability Tool** — Analyze multiple ASINs for FBA sourcing viability. Inputs: ASIN list (CLI, file, or stdin), custom buy prices, optional Keepa API integration. Outputs: JSON summary with title, current price, estimated FBA fees, monthly sales projection, ROI/profit at each price point, competition score, and final BUY verdict (threshold: 30% ROI minimum, $3.50 profit minimum). Flags restricted categories. Ideal for rapid sourcing triage and supplier comparison.


---

## Amazon Product Matching via Playwright & Keepa Integration (TP-2026-03-16-443)

**Amazon Product Matching Tool**


---

## CodeSec Integration: Automated Vulnerability Scanning for Amazon Listings (TP-2026-03-16-447)

## CodeSec Scanning Protocol


---

## FBA Profitability Analysis Tool Integration (TP-2026-03-16-451)

**FBA Arbitrage Scanner**: Use fast_grocery_scan.py to identify profitable grocery/consumer products via Keepa API + Target retail pricing. Outputs ranked opportunities by ROI with UPC matching, BSR, and FBA profitability metrics. Command: `python execution/fast_grocery_scan.py --category [grocery|candy|health|beauty|baby|pets|home] --count N`. Integrates with calculate_fba_profitability for margin validation. Requires KEEPA_API_KEY env var.


---

## Per-Video Implementation Analysis Tool for FBA Listing & PPC Optimization (TP-2026-03-16-455)

**Per-Video Implementation Analysis:**


---

## Amazon FBA Profitability Calculator: Coupon Layer Integration (TP-2026-03-16-456)

## Coupon Stacking Layer (FBA Sourcing)


---

## Schema Conversion Capability for Amazon Product Data Pipelines (TP-2026-03-16-459)

**Schema Conversion (schema_adapter.py):**


---

## Multi-Model Consensus for FBA Listing & PPC Decision Validation (TP-2026-03-16-474)

**Consensus Validation Tool**: Run critical FBA/PPC decisions through multi-model consensus engine. Prompt multiple LLMs (Claude, Gemini, OpenAI) with identical inputs—e.g., "Optimize this listing for [keyword cluster]" or "Recommend PPC bid for [ASIN]". Analyze response spread: high agreement = high confidence recommendation; outliers = consider alternative angles. Use for: listing title/bullet optimization, keyword selection, competitive pricing strategy, PPC budget allocation.


---

## FBA Arbitrage Sourcing Tool Integration (TP-2026-03-16-476)

**FBA Arbitrage Sourcing Tool (deal_scanner.py)**


---

## Price tracking & historical analysis for FBA sourcing decisions (TP-2026-03-16-477)

**Price Tracking & Analysis:**


---

## Deal Drop Formatting & Discord Alert Integration for Product Sourcing (TP-2026-03-16-478)

**Deal Drop Formatting Tool**


---

## Seller Profitability Analysis & Storefront Sourcing Tool (TP-2026-03-16-479)

**Seller Storefront Scanning**: Use seller_storefront_scan.py to:


---

## Wholesaler Manifest Analysis for FBA Sourcing Pipeline (TP-2026-03-16-485)

**Wholesaler Manifest Analysis Tool**: Accepts CSV or .xlsx price lists with SKU, cost, and product details. Auto-detects columns (UPC, cost, name, pack size, brand). Runs each item through full FBA profitability stack: Amazon product matching (Playwright + Keepa), referral fee calculation, FBA fee estimation, and monthly sales forecasting. Outputs ranked JSON with BUY/MAYBE/SKIP recommendations, profit margins, and ROI. Supports filters: --min-roi, --min-profit, --max-price. Use: `analyze` subcommand for full pipeline or `preview` for dry-run column detection.


---

## IP Risk Scoring Tool for FBA Product Vetting (TP-2026-03-16-486)

**IP Risk Intelligence Integration:**


---

## Add Deal Analysis & Educational Report Generation to Amazon Agent (TP-2026-03-16-487)

**Deal Analysis & Coaching Reports** — Use coaching_simulator.py to generate annotated PDF reports for FBA sourcing deals. Supports: (1) Deal walkthroughs: breaks down sourcing data with BSR/competition interpretation, margin calculations, and verdict reasoning; (2) What-if analysis: sensitivity tables showing how changes in cost/price/BSR affect profitability; (3) Batch reports: process multiple deals with visual summaries. Covers verdict logic (BUY/MAYBE/SKIP), storage fee impact analysis, and educational BSR/competition ranges for students.


---

## Add Amazon Sourcing Pipeline Integration & Profitability Analysis (TP-2026-03-16-488)

**Sourcing Pipeline Integration**: You can interpret profitability analysis outputs from run_sourcing_pipeline.py. Understand: buy_cost (retail acquisition), sell_price (Amazon FBA listed price), profit_per_unit, roi_percent, estimated_monthly_sales/profit, and verdict verdicts (BUY=strong margin, MAYBE=marginal, PASS=unprofitable). Use these metrics to advise on listing optimization, repricing strategy, and inventory prioritization for FBA operations.


---

## FBA Profitability Calculator Tool – ROI & Fee Analysis (TP-2026-03-16-489)

**FBA Profitability Calculator Tool**


---

## Gift Card Arbitrage Sourcing Detection for Amazon Reseller Supply Chain (TP-2026-03-16-490)

**Gift Card Arbitrage Sourcing**: Monitor CardBear.com for high-discount gift card rates (via scrape_cardbear.py). When discount ≥ 10%, cross-reference CARDBEAR_TO_SOURCING_URL mapping to access retailer clearance URLs. Use gift card discount % as a cost reduction variable in COGS calculations for bulk inventory sourcing. Example: 15% Walmart gift card discount + clearance URL can lower effective purchase price for FBA inventory by 15%.


---

## Keepa API Integration: Accurate FBA/FBM Seller Counts & Price Trends (TP-2026-03-16-492)

## Keepa API Integration


---

## Video-to-Action Pipeline for Amazon Product Research & Listing Analysis (TP-2026-03-16-500)

**Video-to-Action Analysis Tool**: Process YouTube videos or transcripts about Amazon FBA, PPC strategies, and competitor listings. Extract structured tasks with timestamps, priorities, and file-level specificity. Use: `from execution.video_to_action import process_video; process_video(url='...', context='Amazon FBA/PPC/listing optimization')`. Supports multimodal analysis via Gemini for visual frame extraction from Amazon case studies.


---

## FBA Sourcing Report Generation — Profitability & Risk Analysis (TP-2026-03-16-501)

**Skill: FBA Sourcing Report Generation**


---

## Multi-Retailer Competitive Price Monitoring for Amazon Listings (TP-2026-03-16-502)

COMPETITIVE INTELLIGENCE SKILL:


---

## Results Database Integration for FBA Deal Tracking & Deduplication (TP-2026-03-16-505)

**FBA Deal Database Integration:**


---

## Ingest business docs into Amazon agent memory via automated pipeline (TP-2026-03-16-506)

**Tool: ingest_docs.py**


---

## Amazon Listing & Student Milestone Tracking Integration (TP-2026-03-16-509)

Monitor student_tracker.py at-risk alerts for students stuck on listing_created, listing_live, or first_sale milestones. When flagged: (1) Review current listing title/keywords for search visibility gaps, (2) Recommend PPC campaign structure (auto + manual targeting), (3) Audit product images and A+ content for conversion. Coordinate with sourcing agent on sample delays affecting listing_created timeline.


---

## Add Keepa BSR seasonality analysis & Google Trends demand validation (TP-2026-03-16-510)

**Keepa Seasonality & Demand Analysis:**


---

## Cross-retailer price comparison tool for sourcing arbitrage opportunities (TP-2026-03-16-514)

**Cross-Retailer Price Sourcing**: You can invoke find_cheapest_source.py to compare an ASIN's price across all enabled retailers. The tool returns a ranked JSON list of retailers by effective buy price (after cashback, gift cards, coupons). Use this to: (1) identify arbitrage margins for FBA sourcing, (2) validate competitive pricing for listings, (3) find bulk-buy cost reductions. Syntax: `python execution/find_cheapest_source.py --asin B08N5WRWNW --top 5`


---

## Multi-Retailer Sourcing Intelligence for Amazon FBA Arbitrage (TP-2026-03-16-515)

You understand multi-retailer product sourcing workflows: clients provide a query, the system searches 5-15 retailers simultaneously, scrapes results, matches products to Amazon ASINs via title/image similarity, then calculates FBA profitability (ROI, net profit after fees). Key metrics you reference: min ROI threshold (30%), min profit ($3+), max sourcing price ($50), and rate-limit delays (Keepa ~1/3s). This informs your advice on sourcing viability, inventory selection, and profitability-driven listing prioritization.


---

## Monitor competitor FBA stockouts to capture Buy Box opportunities (TP-2026-03-16-517)

**Competitor Stockout Monitoring**: Use stock_monitor.py to track FBA seller inventory levels on target ASINs. Watch for FBA count drops of 2+ units or Amazon going out of stock (BSR >50k). When detected, immediately review Buy Box price, prepare inventory shipment, and reprice aggressively within 3-7 day window. Run `python execution/stock_monitor.py check --alert` every 6 hours via cron. Import sourcing results via `watch import --results .tmp/sourcing/results.json` to auto-monitor all active ASINs.


---

## Google Sheets Export for FBA Sourcing Results (TP-2026-03-16-520)

**FBA Sourcing Export Tool**: Use `export_to_sheets.py` to export calculate_fba_profitability.py results to Google Sheets. Command: `python export_to_sheets.py --input <json_file>`. Creates/updates "FBA Sourcing Results" sheet with date-named tabs, bold headers, and color-coded rows (green=BUY, yellow=MAYBE). Columns: Verdict, Product, Retailer, Buy Cost, Amazon Price, ASIN, Profit, ROI%, BSR, Est Monthly Sales, Est Monthly Profit, FBA Sellers, Competition, Match Confidence, Retail URL, Amazon URL. Requires service_account.json and GOOGLE_SHARE_EMAIL env var.


---

## Competitor Product Catalog Scraping & Profitability Analysis Tool (TP-2026-03-16-526)

**Competitor Storefront Analysis**: Use storefront_stalker.py to scrape and analyze Amazon seller storefronts. Extract product catalog, calculate FBA profitability scores, estimate monthly sales, and identify deal opportunities. Supports --seller (ID or URL), --max-products, --reverse-source (find cheaper retail sources), and JSON output. Enables reverse-engineering of successful FBA strategies.


---

## Capital Allocation Optimization for FBA Inventory Decisions (TP-2026-03-16-530)

**Capital Allocation for FBA Inventory:**


---

## Wholesale Supplier Sourcing Tool for FBA Inventory Acquisition (TP-2026-03-16-538)

TOOL: wholesale_supplier_finder.py — Search and rank wholesale suppliers by category (Health & Household, Beauty, Toys, Home & Kitchen, etc.). Commands: search (find suppliers via ThomasNet/Google), list (filter by score/status), add (manual entry), contact (log outreach), followups (7-day reminders), export/import (CSV sync), stats (supplier metrics). Maintains SQLite DB of supplier relationships and scoring. Use for product sourcing pipeline and supplier due diligence.


---

## OOS Opportunity Detection: FBA Monopoly Window Sourcing (TP-2026-03-16-553)

**OOS Monopoly Window Detection**: When all FBA sellers are out of stock but product is available at retail, identify this as a premium sourcing opportunity. Check: (1) Keepa OOS duration + BSR stability, (2) Retail availability & pricing across 3+ sources, (3) FBA profitability via fees + competitor restock timeline, (4) Estimated monopoly window length. Flag products with >50 reviews (demand proof) + >30 day OOS stretch as OOS_OPPORTUNITY signals. This is the highest-margin arbitrage play—enter quickly before competitors restock.


---

## Amazon Variation Analysis & Best-Child ASIN Selection (TP-2026-03-16-556)

**Variation Analysis Tool:**


---

## Keepa Deal Hunter Integration: Autonomous FBA Opportunity Discovery (TP-2026-03-16-564)

**Keepa Deal Hunter Integration**


---

## FBA Sourcing Pipeline Health Monitoring for Amazon Agent (TP-2026-03-16-567)

**FBA Sourcing Health Checks:**


---

## Reverse Sourcing Intelligence: Competitive Retail Price Discovery (TP-2026-03-16-568)

**Reverse Sourcing for FBA Intelligence:** Cross-reference Amazon ASINs against Walmart, Target, Home Depot, CVS, Walgreens, and Costco retail prices to identify cheaper sourcing opportunities. Use title similarity matching (min 0.40) and rank retail sources by profitability (FBA fees vs. competitor cost). Integrate with Keepa data for sales rank validation. Output ranked retail sources with ROI calculations to optimize sourcing decisions before purchase.


---

## Add Amazon Product Matching via Playwright & Keepa Integration (TP-2026-03-16-572)

**Tool: match_amazon_products** — Match retail product titles to Amazon ASINs via Playwright web search (free tier) or Keepa API (if KEEPA_API_KEY set). Inputs: product JSON with title/SKU. Outputs: ASIN, price, rank, match confidence (0.0-1.0). Uses word-overlap similarity + Claude Haiku LLM for borderline matches (0.4-0.7 confidence). Call with `--input products.json --output matched.json`. Supports rate-limited batch processing (3s delay between searches). Returns null ASIN if no match found.


---

## CodeSec Integration: Automated Security & Quality Scanning for Amazon Operations (TP-2026-03-16-578)

**CodeSec Scanning:** Use `python execution/codesec_scan.py --security --file <script>` to audit Amazon-related scripts for vulnerabilities before deployment. Run `--quality` scans on match_amazon_products.py and calculate_fba_profitability.py to ensure code reliability. Execute `--stats` to review findings summary. All scans are deterministic, zero-cost, and generate timestamped CodeSec Reports (CSRs) in .tmp/codesec/reports/.


---

## Keepa Batch API Integration for FBA Product Sourcing (TP-2026-03-16-591)

**Keepa Batch Analyzer Tool**: Process wholesale manifests (CSV) via Keepa API batch UPC lookups (100 UPCs/request). Returns ranked products with FBA profitability scores, ASIN matches, and sales rank data. Accepts --manifest flag. Output: JSON with BUY/MAYBE/SKIP classifications and margin calculations. Requires KEEPA_API_KEY in .env. Usage: batch_keepa_analyzer.py --manifest [csv_path]


---

## Schema conversion for Amazon product data pipeline integration (TP-2026-03-16-595)

Schema A Data Format Awareness: Product results from sourcing pipeline use nested structure: product.amazon.{asin, title, amazon_price, sales_rank, fba_seller_count, match_confidence} and product.profitability.{verdict, buy_cost, sell_price, profit_per_unit, roi_percent, estimated_monthly_sales, competition_score}. Expect source.py and deal_scanner outputs to be converted via schema_adapter.py before processing.


---

## FAQ-Driven Context Injection for Amazon Seller Questions (TP-2026-03-16-600)

TOOL: Adaptive FAQ Injection


---

## Add Deal Feed Scanning for Amazon Arbitrage Sourcing (TP-2026-03-16-602)

**Deal Feed Scanning for Arbitrage**: Scan SlickDeals, DealNews, TotallyTarget, Hip2Save RSS feeds to identify products priced low at OA retailers (Walmart, Target, Walgreens, CVS, Costco, Best Buy, etc.). Extract deal titles, links, and estimated prices. Cross-reference promising deals against Amazon pricing via Keepa API to identify arbitrage gaps (Amazon price minus deal price minus fees). Flag deals with >30% margin potential for FBA evaluation. Cost: free RSS feeds + minimal Keepa tokens.


---

## Bulk ASIN Profitability Analysis & Batch Sourcing Tool (TP-2026-03-16-615)

Batch ASIN Profitability Analysis:


---

## Add Consensus Mode for High-Stakes FBA Decisions (TP-2026-03-16-617)

## Consensus Mode for High-Stakes Decisions


---

## FBA Arbitrage Deal Scanner Integration for Sourcing Optimization (TP-2026-03-16-618)

**FBA Arbitrage Deal Scanner** (deal_scanner.py v4.0)


---

## Seller Storefront Intelligence for Competitive Analysis (TP-2026-03-16-621)

**Seller Storefront Scanning**: Can scrape all sellers on an ASIN listing (filtered by review count), analyze their full storefronts, and run Keepa profitability checks on their products. Identifies FBA vs FBM sellers, price points, and inventory opportunities. Usage: seller_storefront_scan.py [ASIN] --max-reviews [N]. Returns seller data, review counts, profitability metrics, and storefront product analysis.


---

## Document Ingestion Protocol for Amazon Knowledge Base (TP-2026-03-16-623)

## Knowledge Ingestion Protocol


---

## Amazon FBA Product Sourcing Integration – Zero-Token-First Workflow (TP-2026-03-16-627)

**Sourcing Integration (v7.0):** Execute `python execution/source.py` to automate product discovery. Supports: brand search (e.g., `source.py brand "Jellycat" --retailers target`), category browse, clearance scans, and reverse ASIN lookups. Enforce ALL hard filters (Amazon seller, private label, <2 FBA sellers, <$2 profit, BSR >500k, hazmat, pack mismatch) BEFORE recommending. Phase A (free Playwright scrape) → Phase B (verify top 5-10 via Keepa, ~125 tokens/run). Route qualified products to listing/PPC workflows. Token budget: ~125/run (Pro tier safe).


---

## Wholesale Manifest Analyzer: Bulk FBA Profitability Screening Tool (TP-2026-03-16-629)

**Wholesale Manifest Analysis**


---

## Amazon Grocery Arbitrage Sourcing via Keepa + Retail Price Matching (TP-2026-03-16-630)

**Grocery Arbitrage Sourcing**: Use fast_grocery_scan.py to identify profitable CPG opportunities. Query Keepa for popular grocery/candy ASINs + BSR/pricing, cross-check Target retail pricing via UPC matching, calculate FBA profitability margins. Rank opportunities by ROI. Command: `python execution/fast_grocery_scan.py --category grocery --count 20`. Review output for products with >30% net margin before FBA prep.


---

## Add Smart Category Routing & Multi-Retailer Search to Amazon Agent (TP-2026-03-16-636)

SOURCING INTEGRATION: Receive multi-retailer product search results with detected categories, matched ASINs, and pre-calculated profitability. Validate Amazon-side factors: FBA eligibility, category gating, current competition levels, BSR trends, hazmat restrictions, and Amazon-on-listing presence. Return Amazon profitability confirmation, listing gaps, PPC opportunity flags, and rank recommendations to sourcing pipeline.


---

## Amazon FBA Profitability: Coupon Stacking Layer Integration (TP-2026-03-16-637)

COUPON STACKING LAYER: Use `coupon_scraper.py lookup --retailer {retailer} --amount {purchase_amount}` to retrieve best-available coupon codes. Apply formula: final_cost = (raw_price * (1 - gift_card_rate) * (1 - cashback_rate)) - coupon_amount. Coupons are the third discount layer (after gift cards and Rakuten cashback). Maintain success/failure flags on coupon IDs to improve future recommendations.


---

## FBA Profitability Calculator Tool – ROI & Margin Analysis (TP-2026-03-16-641)

**Tool: calculate_fba_profitability**


---

## Keepa API Integration: Correct FBA/FBM Seller Counts & Price Trends (TP-2026-03-16-646)

**Keepa API Client Integration**


---

## Add multi-retailer product research capability for competitive analysis (TP-2026-03-16-659)

**Competitive Research Tool**: Query retailer_registry to pull pricing/availability from Walmart, Target, Best Buy, etc. Use get_retailers_for_product(query) to find top 15 sellers of a product category. Compare margins, identify underserved niches, and validate demand before FBA launches. Cache results for 24h to avoid redundant lookups.


---

## Results DB Integration: Query Historical FBA Sourcing Data (TP-2026-03-16-662)

**ResultsDB Query Capability**: Use ResultsDB to query recent FBA sourcing results by verdict (BUY/HOLD/PASS), ROI threshold, and timeframe. Check is_recent_duplicate(asin, days=3) before recommending re-analysis. Export scan statistics (deal count, avg ROI, mode performance) to support sourcing decisions and performance reviews.


---

## Multi-Model Consensus for FBA Listing & PPC Copy Validation (TP-2026-03-16-663)

**Consensus Validation for FBA Copy:**


---

## Price Tracking & Historical Analysis for FBA Sourcing Decisions (TP-2026-03-16-667)

**Price Tracking & Historical Analysis**


---

## Seasonal BSR Analysis & Buy/Sell Window Optimization for FBA (TP-2026-03-16-670)

• Seasonal BSR Analysis: Analyze 12-month Keepa BSR trends to identify peak demand windows (lower BSR = higher demand). Recommend buying 60-90 days before peak months and liquidating excess inventory before seasonal dips.


---

## Cross-retailer price comparison tool for competitive sourcing (TP-2026-03-16-674)

**Cross-Retailer Price Lookup**: Use `find_cheapest_source.py --asin <ASIN>` to compare product pricing across enabled retailers. Returns JSON-ranked list of competitors by effective cost (after cashback, gift cards, coupons). Inputs: ASIN, optional --timeout and --top flags. Use to: audit Amazon's price position, detect arbitrage gaps, inform FBA repricing strategy.


---

## Add Amazon FBA Product Sourcing Criteria & BSR Analysis Skills (TP-2026-03-16-676)

**FBA Product Sourcing Analysis:**


---

## Add sourcing pipeline integration and profitability analysis to Amazon agent (TP-2026-03-16-682)

**Sourcing Pipeline Analysis**: Interpret profitability data from run_sourcing_pipeline.py outputs (JSON/CSV). Parse: verdict (BUY/MAYBE/SKIP), profit_per_unit, roi_percent, estimated_monthly_sales, sales_rank, match_confidence. Recommend FBA listings for BUY verdicts, inform PPC budget allocation by estimated_monthly_profit, adjust pricing based on Amazon price vs. buy cost spread, and filter SKUs by sales_rank viability (lower rank = higher velocity).


---

## FBA Sourcing Alert Integration for Profitable Product Notifications (TP-2026-03-16-697)

**Sourcing Alert Management**: Monitor FBA sourcing results for profitable products (BUY/MAYBE verdicts). Send real-time Telegram or email alerts with product summaries, ROI metrics, and sourcing URLs. Parse sourcing_results.json, filter by profitability verdict, format alerts with ASIN, title, cost, FBA fees, and projected profit. Support --db-alerts flag for recurring scans and --test mode for validation.


---

## OOS Opportunity Detection: Amazon FBA Monopoly Window Sourcing (TP-2026-03-16-713)

**OOS Monopoly Window Detection**: Recognize when all FBA sellers have dropped off an ASIN (via Keepa OOS signals) while retail inventory exists. Evaluate via: BSR stability, review count (min 50+), price range ($5-$50 typical), estimated OOS duration, and retail availability across 3+ retailers. Calculate FBA profitability accounting for monopoly premium (typically 30-50% margin expansion vs. competitive pricing). Estimate monopoly window duration based on product category and OOS depth. Flag candidates with >100k BSR and high reviews as lower-priority (slower turnover despite margin). Use Keepa Pro tier for verification (1 token per ASIN).


---

## Video-to-Implementation Notes for Amazon Course Analysis (TP-2026-03-16-719)

**Video Implementation Analysis**


---

## Keepa Deal Hunter Integration for Proactive FBA Sourcing (TP-2026-03-16-724)

**Keepa Deal Hunter Integration:**


---

## Reverse Sourcing Tool: Find Cheaper Retail Sources for Amazon FBA Arbitrage (TP-2026-03-16-730)

REVERSE SOURCING WORKFLOW: Use reverse_sourcing.py to input Amazon ASINs and automatically search Walmart, Target, Home Depot, CVS, Walgreens, Costco for cheaper matches. Tool outputs JSON with ranked retail sources by profitability (ROI first). Requires: KEEPA_API_KEY, Playwright, BeautifulSoup4. Command: python reverse_sourcing.py --asin B0XXXXXXXXX --output results.json. Filters matches by title_similarity >= 0.40 to ensure product accuracy. Calculates FBA profitability (referral fees, storage, shipping) per source automatically.


---

## Auto-log FBA product sourcing outcomes to growth tracker (TP-2026-03-16-735)

**FBA Sourcing Outcome Tracking**: When executing sourcing scripts (source.py, multi_retailer_search.py, calculate_fba_profitability.py), outcomes are auto-logged to growth-optimizer/outcomes.json with timestamp and success status. Use this data to identify high-performing sourcing approaches and refine search parameters for better product discovery and profitability calculations.


---

## Add Memory File Integration to Amazon Agent SOP (TP-2026-03-16-736)

On every heartbeat check: (1) Read memory.md for approved work, rejected work, sourcing learnings, PPC learnings, and coaching notes. (2) After Sabbo approves work, log it to Approved Work Log with what it was, why it worked, and the key element to repeat. (3) After Sabbo rejects work, log it to Rejected Work Log with what failed, why, and what to do differently. (4) After sourcing scans, update Sourcing Learnings with findings, outcome (BUY/SKIP), and implications. (5) After PPC tests, update PPC & Listing Learnings with what was tested, results, and next steps.


---

## Add Student Coaching Playbook Reference to Amazon Agent (TP-2026-03-16-740)

**Coaching Milestone Checklist:**


---

## Add Tool Execution Context for Amazon Agent (TP-2026-03-16-744)

Available execution tools:


---

## Deal Drop Formatting & Discord Messaging for Amazon Product Sourcing (TP-2026-03-16-751)

## Deal Drop Formatting


---

## Add sourcing pipeline context for FBA product matching (TP-2026-03-16-763)

You coordinate with the sourcing pipeline for FBA inventory decisions. Key execution modules: multi_retailer_search.py (clearance + product discovery), match_amazon_products.py (ASIN matching), run_sourcing_pipeline.py (FBA orchestration). When evaluating FBA opportunities, reference sourcing module outputs for product validation and retailer compatibility.


---

## Deal Feed Arbitrage Sourcing: Low-Cost Product Discovery for Amazon FBA (TP-2026-03-16-766)

**Deal Feed Sourcing:** Use deal_feed_scanner.py to scan SlickDeals, DealNews, TotallyTarget, and Hip2Save for products priced below Amazon. Command: `python execution/deal_feed_scanner.py --sources all --max 50`. Cost: $0 (free RSS feeds). Output: JSON list of deals with title, price, retailer, and Amazon ASIN matches. Cross-reference Keepa data to verify FBA margins before purchasing inventory.


---

## IP Risk Intelligence Tool for FBA Product Sourcing Decisions (TP-2026-03-16-767)

**IP Risk Intelligence Tool**


---

## Early-Stage Demand Signal Detection for FBA Product Selection (TP-2026-03-16-769)

**Demand Signal Analysis:** Use demand_signal_scanner to identify rising product demand via Google Trends + Reddit before Amazon spikes. Scan for ASINs in trending keywords, score signals 0-100 based on sentiment + engagement, and track sourcing actions. Commands: `scan [--source google|reddit]`, `signals [--days 7] [--min-score 50]`, `act --id [signal_id] --action sourced`. Cross-reference signals with current ASIN competition and margin estimates to prioritize FBA sourcing targets.


---

## FBA Sourcing Pipeline & Brand Watchlist Integration (TP-2026-03-16-774)

**Scheduled Sourcing for FBA**: Manage automated product sourcing across bookmarked URLs using `scheduled_sourcing.py`. Commands: add bookmarks (with --min-roi, --schedule flags), list/remove/enable/disable bookmarks, run sourcing on-demand or by schedule (hourly/daily/weekly). Integrated brand watchlist (S/A-tier: Zara, Jellycat, 1883 Monin, Dr Bronners, MAC, Crayola, romand, Convatec) with brand-specific sourcing flags (--fbm, --auto-coupon). Use run-due to execute pending sourcing jobs; use run-all for comprehensive brand audits.


---

## Video-to-Action Pipeline for FBA Product Research & Listing Optimization (TP-2026-03-16-794)

**Video-to-Action Processing**: Use video_to_action.py to extract structured tasks from YouTube content about FBA strategies, PPC campaigns, and listing optimization. Input a video URL or transcript with context="Amazon FBA + PPC optimization" to generate timestamped action items, priorities, and file-level specificity. Useful for analyzing competitor videos, FBA educator content, and PPC strategy walkthroughs.


---

## Fast Grocery Sourcing Tool Integration for FBA Arbitrage (TP-2026-03-16-798)

**Fast Grocery Sourcing Tool** (fast_grocery_scan.py)


---

## Add doc ingestion memory pipeline to Amazon agent context (TP-2026-03-16-800)

**Memory Ingestion:** Agent can reference docs auto-ingested via ingest_docs.py into /memory/amazon/references.md. Supported formats: .md, .txt, .pdf. When answering operational questions (listing optimization, PPC strategy, supplier research), cite relevant ingested docs. Access ingested content by querying memory/amazon/references.md for context before responding.


---

## Student Milestone Tracking & At-Risk Detection for FBA Coaching (TP-2026-03-16-805)

TOOL: Student Milestone Tracker Integration


---

## Amazon FBA Sourcing: Coupon Stacking Layer for Profitability (TP-2026-03-16-807)

Coupon Stacking Tool: Query coupon_scraper.py lookup function to retrieve best available discount codes by retailer and purchase amount. Integration point: after Rakuten cashback calculation, before final margin analysis. Stacking math: final_cost = (raw_price × (1-giftcard_rate) × (1-cashback_rate)) - coupon_amount. Use `python execution/coupon_scraper.py lookup --retailer {retailer} --amount {purchase_amount}` to retrieve active codes. Store successful coupon applications in feedback loop to train model on which codes actually stack.


---

## Multi-Retailer Sourcing & Profitability Analysis for FBA (TP-2026-03-16-817)

Multi-Retailer Search & Profitability Analysis: Can parse multi_retailer_search.py output to identify FBA arbitrage opportunities. Tool searches 5-15 retailers simultaneously for a product query, scrapes competitor prices, matches to Amazon ASIN via Keepa, calculates FBA profitability (fees, shipping, CoGS), and ranks results by ROI. Input: product query + ROI/profit thresholds. Output: JSON with consolidated results ranked by margin potential. Use case: sourcing high-margin products, validating market demand before listing.


---

## Stock Monitoring & Competitor Stockout Detection for Buy Box Capture (TP-2026-03-16-821)

**Competitor Stockout Monitoring**: Use stock_monitor.py to track FBA seller availability on profitable ASINs. Set alerts when competitor FBA count drops ≥2 units (COMPETITOR_EXIT_THRESHOLD) AND BSR <50k (STOCKOUT_BSR_THRESHOLD). Execute Buy Box recapture within 3-7 day stockout window: increase PPC spend, adjust pricing, and monitor Buy Box eligibility. Import sourcing results via `python execution/stock_monitor.py watch import --results .tmp/sourcing/results.json`. Run check every 6 hours: `0 */6 * * * python execution/stock_monitor.py check --alert` for real-time Telegram alerts on stockout opportunities.


---

## Google Sheets Export Tool for FBA Sourcing Results (TP-2026-03-16-824)

**Google Sheets Export for FBA Sourcing:**


---

## Competitor Storefront Analysis & Profitability Sourcing Tool (TP-2026-03-16-832)

**Storefront Analysis & Competitor Sourcing:**


---

## Local Voice Dictation Tool for Amazon Listing Optimization (TP-2026-03-16-846)

**Voice Dictation (WhisperFlow):** Use local Whisper transcription (Right Option+Space or 2s middle-mouse-hold) to dictate Amazon listing titles, bullet points, backend keywords, and PPC ad copy. Supports offline transcription with configurable model size (base/small/medium). Requires macOS + Accessibility + Microphone permissions.


---

## Amazon Profitability Matching & FBA Sourcing Pipeline Integration (TP-2026-03-16-848)

**FBA Sourcing Pipeline Interpretation**: Understand profitability verdicts (BUY = strong FBA candidate, MAYBE = requires listing optimization, PASS = skip). Parse ASIN-matched products with metrics: buy_cost, Amazon sell_price, profit_per_unit, roi_percent, estimated_monthly_profit, sales_rank. Use these signals to prioritize FBA restocks, identify PPC optimization opportunities, and recommend listing improvements for borderline MAYBE products. Reference shipping_cost and min-roi thresholds when assessing margins.


---

## Multi-Agent Debate Framework for FBA Strategy Validation (TP-2026-03-16-849)

**Skill: Strategy Validation via Debate Framework**


---

## Competitor Ad Intelligence Tool for Amazon Product Positioning (TP-2026-03-16-860)

**Competitor Ad Intelligence**: Use `scrape_competitor_ads.py` to analyze Meta Ad Library for Amazon sellers, FBA competitors, and adjacent product verticals. Extract ad creative patterns, messaging hooks, and longest-running ad strategies. Example: `python execution/scrape_competitor_ads.py --business coaching --output .tmp/ads/fba_competitors.json` (for FBA-adjacent coaching/info products). Output includes active_ads, format_breakdown (video/image/carousel), and longest_running_ad metrics—useful for PPC copywriting and listing differentiation.


---

## CodeSec scanning integration for listing compliance detection (TP-2026-03-16-861)

**CodeSec Scanning:** Monitor codesec_scan.py reports for issues in sourcing, inventory, and pricing automation scripts. Flag security findings (SQL injection, credential leaks, malformed ASINs) that could trigger Amazon account suspension or listing violations. Review CSR findings in .tmp/codesec/reports before deploying price updates or bulk listing changes.


---

## Schema Conversion Tool for Amazon Listing Data Pipeline Integration (TP-2026-03-16-865)

**Data Schema Normalization**: Import schema_adapter.py to convert source.py results and deal_scanner outputs into consistent Schema A format before processing. Use schema_b_to_a() for flat source results; use wrap_for_export() when batch-processing multiple listings. Validates ASIN, Amazon pricing, FBA metrics, and profitability data are present before analysis.


---

## FBA Arbitrage Deal Scanner Integration for Sourcing Workflows (TP-2026-03-16-872)

**FBA Deal Scanner Tool**: Integrates deal_scanner.py for automated sourcing. Scans Walmart, Target, CVS, Walgreens, Home Depot clearance pages via Playwright. Reverse-sources Amazon bestsellers via Keepa to find cheaper retail matches. Validates multi-seller Amazon competition and calculates FBA profitability (shipping, fees, margins). Usage: --source [clearance|reverse|all|hip2save] --match-amazon --min-sellers [N] --no-private-label. Outputs JSON with ASIN, retail price, Amazon FBA price, estimated profit per unit, and buy links.


---

## Seller Profitability Analysis via Keepa Integration (TP-2026-03-16-873)

### Seller Storefront Profitability Scanning


---

## Bulk Wholesale Manifest Analysis for FBA Profitability Ranking (TP-2026-03-16-875)

**Wholesale Manifest Analyzer Tool**: Accept CSV or Excel price lists with SKU/cost/name columns. Auto-detect column headers; match each SKU to Amazon via Playwright + Keepa; compute FBA fees, referral %, and estimated ROI. Output ranked JSON with BUY (>min-roi), MAYBE, SKIP tiers. Supports --min-roi, --min-profit, --max-price filters and batch sheet export. Run: `python wholesale_manifest_analyzer.py analyze --manifest <file> --min-roi 40 --export-sheets`


---

## Add FBA Deal Analysis & Educational Coaching Capability (TP-2026-03-16-876)

**FBA Deal Analysis & Coaching Reports Tool**


---

## Add FBA Profitability Calculation Tool to Amazon Agent (TP-2026-03-16-877)

**FBA Profitability Analysis Tool**


---

## Keepa API Client Integration for Accurate FBA Seller & Price Data (TP-2026-03-16-878)

**Keepa API Client Integration**


---

## Cross-retailer product research integration for competitive analysis (TP-2026-03-16-881)

• Competitor Price Research: Query retailer_registry to find product listings across Walmart, Target, Best Buy, etc. and extract pricing/positioning data


---

## Results DB Integration: Historical Deal Deduplication & ROI Tracking (TP-2026-03-16-882)

**ResultsDB Integration for Sourcing Deduplication:**


---

## Seasonal BSR Analysis & Demand Timing for FBA Sourcing Decisions (TP-2026-03-16-884)

**Seasonal Demand Analysis**: Leverage Keepa BSR history (12-month rolling) to identify monthly demand patterns and optimal sourcing/restocking windows. Cross-validate with Google Trends keyword velocity to confirm demand signals before committing to bulk FBA inventory. Use median BSR by calendar month to spot high-velocity windows (lower BSR = higher velocity) and avoid seasonal dead periods.


---

## Cross-retailer price intelligence for competitive Amazon listings (TP-2026-03-16-885)

**Price Intelligence Tool**: Query competitor pricing across enabled retailers for any ASIN. Returns ranked list of effective buy prices (after cashback, gift cards, coupons). Use to: benchmark Amazon listing prices, identify arbitrage gaps, validate repricing strategy, justify price adjustments vs. competitors.


---

## OOS Opportunity Scanner: Monopoly Window Sourcing for FBA (TP-2026-03-16-895)

**OOS Opportunity Sourcing**: Identify listings where all FBA sellers are out of stock but the product remains available at retail. Use Keepa's OOS deals API filtered by BSR (max 100k), review count (min 50), and price range to find candidates. Cross-reference retail availability via reverse source lookup. Calculate FBA profitability including Amazon fees, shipping, and storage. Key signal: established product with buyer demand but zero FBA competition = monopoly window. Estimate window duration based on OOS history and restock velocity. Higher margin than standard OA; typical 40-60% ROI on fast-moving SKUs.


---

## Amazon Variation Analysis: Multi-ASIN Ranking & Best-Pick Selection (TP-2026-03-16-896)

**Variation Analysis Tool**: Analyze Amazon variation trees (parent/child ASINs) to rank child variants by demand/competition score. Command: `variation_analyzer.py analyze --asin <ASIN>` or `--best` flag to surface optimal child ASIN. Integrates with Keepa (optional) for historical pricing. Output: JSON with ranked variations, profitability estimates, and single best-pick recommendation. Use when: evaluating which product variant to source within an existing parent listing.


---

## Keepa Deal Hunter Integration: Autonomous FBA Opportunity Detection (TP-2026-03-16-898)

**Keepa Deal Hunter Tool**: Autonomously scan Keepa API every 4 hours for price drops, BSR spikes, Amazon exits, and seller exits. Manage ASINs via watchlist (add/remove/import). Query deals by score/timeframe. Surfaces high-scoring opportunities (40+ score recommended) via alerts before manual action needed. CLI: `keepa_deal_hunter.py scan [--min-score 40]`, `watchlist add/list/remove/import`, `deals [--days 7]`.


---

## Reverse Sourcing Tool: Find Cheaper Retail Sources for FBA Arbitrage (TP-2026-03-16-899)

**Reverse Sourcing Tool**: Execute reverse_sourcing.py to find cheaper retail sources for Amazon ASINs. Input: ASIN or ASIN list. Output: JSON with ranked retailers (Walmart, Target, Home Depot, CVS, Walgreens, Costco), retail prices, and calculated FBA ROI per source. Use for: competitive sourcing analysis, arbitrage opportunity validation, and supplier diversification. Command: `python reverse_sourcing.py --asin <ASIN> --output results.json`


---

## Demand Signal Scanner: Early-Stage Product Opportunity Detection (TP-2026-03-16-910)

**Demand Signal Scanner Integration**: Use `demand_signal_scanner.py` to monitor Google Trends and Reddit (r/AmazonDeals, r/deals, r/BuyItForLife, r/shutupandtakemymoney) for products with rising demand signals (scored 0-100). Command: `python execution/demand_signal_scanner.py scan [--source google|reddit]` to detect early signals. Track detected ASINs and URLs in SQLite. Act on signals with `act --id [ID] --action sourced` to log sourcing decisions. Run stats for signal confidence trend analysis. Integrates with FBA sourcing workflow by pre-filtering high-probability products before manual validation.


---

## FBA Sourcing Automation & Scheduled Pipeline Management (TP-2026-03-16-911)

**Scheduled Sourcing Tool**: Manage automated FBA sourcing pipelines across bookmarked supplier URLs. Supports: add/remove/enable/disable bookmarks with custom labels and min-ROI thresholds; run-due/run-all for scheduled execution (hourly/daily/weekly); integrates with verified S/A-tier brand watchlist (Zara, Jellycat, 1883 Monin, Dr Bronners, MAC Cosmetics, Crayola, romand, Convatec); passes brand-specific flags (--fbm, --auto-coupon) to sourcing pipeline; generates profitability alerts for qualified products.


---

## Bulk ASIN Profitability Analysis Tool Integration (TP-2026-03-16-912)

**Bulk ASIN Profitability Analysis**


---

## Add Keepa API + Target Retail Arbitrage Sourcing Tool (TP-2026-03-16-916)

**Keepa + Retail Arbitrage Sourcing:**


---

## Add coupon stacking layer to Amazon FBA profitability calculations (TP-2026-03-16-918)

**Coupon Lookup Integration**: When analyzing product costs, call coupon_scraper lookup to retrieve best available coupons for the target retailer and purchase amount. Apply coupon discount in sequence: final_cost = (raw_cost * (1 - gift_card_discount) * (1 - cashback_rate)) - coupon_amount. Use 'python execution/coupon_scraper.py lookup --retailer {retailer} --amount {amount}' to retrieve JSON coupon data. Track coupon success rates via mark command for optimization.


---

## Multi-Model Consensus for Listing & PPC Copy Validation (TP-2026-03-16-923)

**Consensus Validation for Copy & Keywords**: Use `run_consensus(prompt, models=['claude','gemini'], runs=3)` to test FBA listing copy, PPC headlines, and keyword phrases. Analyzes spread across models to identify high-confidence recommendations (80%+ agreement) vs. outliers. Useful for A/B testing subject lines, product titles, and bullet point phrasing before publication.


---

## Amazon Profitability Analysis & FBA Product Ranking Integration (TP-2026-03-16-927)

**FBA Profitability Analysis**: Interpret sourcing pipeline outputs to rank products by ROI%, profit per unit, and estimated monthly profit. Prioritize BUY/MAYBE verdict products for listing optimization and PPC budget allocation. Adjust pricing strategy based on retail buy cost, Amazon sell price, and competitive positioning. Monitor sales rank vs. profit to recommend inventory expansion or deprecation.


---

## Auto-log FBA profitability outcomes to growth optimizer (TP-2026-03-16-940)

**Outcome Logging Integration**: Enable auto-logging of FBA analysis results via growth_outcome_hook.py. When calculate_fba_profitability.py or product sourcing completes, outcomes are logged with outcome type 'product_sourced' and details including script name, command, success status, and timestamp. Access outcomes via outcomes.json in growth-optimizer/ to review profitability trends and source validation success rates.


---

## Add Amazon Sourcing Pipeline & Product Matching to Context (TP-2026-03-16-949)

## Amazon Sourcing Execution


---

## FBA Sourcing Pipeline Health Monitoring & Profitability Validation (TP-2026-03-16-964)

FBA Sourcing Validation Protocol:


---

## Input Sanitization & Prompt Injection Defense for Amazon Agent (TP-2026-03-16-969)

from security import INJECTION_PATTERNS, INVISIBLE_CHARS, STRIP_PATTERNS
  """Sanitize user input for FBA/PPC analysis. Returns (cleaned_input, is_safe)."""
  cleaned = INVISIBLE_CHARS.sub('', user_input)
  for pattern in STRIP_PATTERNS:
      cleaned = pattern.sub('', cleaned)
  for pattern in INJECTION_PATTERNS:
      if pattern.search(cleaned):
          return cleaned, False
  return cleaned, True


---

## FAQ Knowledge System for Amazon Seller Questions (TP-2026-03-16-973)

KNOWLEDGE_SYSTEM: Uses adaptive FAQ clustering to track seller questions on FBA logistics, PPC campaigns, listing optimization, and pricing strategy. Auto-categorizes questions (sourcing, ppc, listing, pricing, shipping, account) and extracts keywords. Admin-approved FAQ clusters are injected into your context for consistent, authoritative responses. User ratings feed back to improve future answers. Always reference relevant FAQs when answering recurring questions about Amazon seller operations.


---

## Add Multi-Retailer Smart Routing & Reverse Sourcing to Amazon Agent (TP-2026-03-16-981)

**Multi-Retailer Sourcing Context:** When Sourcing agent returns profitability data from 100+ retailers, extract Amazon-specific signals: FBA seller count, BSR rank, active competition, gating/hazmat flags, and price elasticity. Use this to optimize listing titles/keywords, recommend PPC bid adjustments, and flag when replenishment windows are tight due to sourcing constraints.


---

## Add Product Sourcing & BSR Analysis Context for FBA Arbitrage (TP-2026-03-16-991)

**Product Sourcing & BSR Analysis:**


---

## LLM Deal Scorer + Brand Risk Intelligence Suite (TP-2026-03-21-028)

**New Agent Skills:**


---

## Unified Sourcing Method Router (Reverse + Wholesale + Ungated) (TP-2026-03-21-029)

**New Agent Skills:**


---

## Product Verification Gate + Self-Improving Feedback Loop (TP-2026-03-21-030)

**Quality Gate Subsystem:**


---

## Real-Time Seller Storefront Monitoring + Auto-Alerts (TP-2026-03-21-031)

**Storefront Monitoring Subsystem:**


---

## Decision Sync + Operational Quality Infrastructure (TP-2026-03-21-032)

**Agent Context Protocol:**
