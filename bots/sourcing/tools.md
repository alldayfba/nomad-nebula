# Sourcing Bot — Tools
> bots/sourcing/tools.md | Version 5.0

---

## Available Scripts

### Core Pipeline
| Script | Purpose | Cost |
|---|---|---|
| **`execution/multi_retailer_search.py`** | **Multi-retailer product search + clearance scan** | **Free (Playwright)** |
| **`execution/retailer_registry.py`** | **100-retailer database + smart category routing** | **Free (data)** |
| `execution/scrape_retail_products.py` | Scrape products from any retail URL | Free (Playwright) |
| `execution/match_amazon_products.py` | Match products to Amazon ASINs + seller data | Free (Playwright) or ~$0.01/product (Haiku) |
| `execution/calculate_fba_profitability.py` | Calculate ROI, fees, profit, competition, gating | Free (deterministic) |
| `execution/run_sourcing_pipeline.py` | Single-URL pipeline orchestrator | Sum of above |
| `execution/reverse_sourcing.py` | ASIN → find cheaper retail sources (smart-routed, 15 retailers) | Free (Playwright) |

### Data & Tracking
| Script | Purpose | Cost |
|---|---|---|
| `execution/price_tracker.py` | SQLite price history database | Free (local) |
| `execution/scheduled_sourcing.py` | Bookmark URLs + scheduled runs | Free (cron) |
| `execution/sourcing_alerts.py` | Telegram/email alerts for BUY products | Free (Telegram API) |
| `execution/export_to_sheets.py` | Export results to Google Sheets | Free (service account) |
| `execution/inventory_tracker.py` | Track purchases, shipments, sales, P&L | Free (SQLite) |
| `execution/stock_monitor.py` | Competitor FBA stock level tracking + stockout alerts | Free (Keepa) |

### Deal Discovery & Intelligence
| Script | Purpose | Cost |
|---|---|---|
| `execution/scrape_cardbear.py` | Track gift card discounts for presourcing savings | Free (HTTP + SQLite) |
| `execution/coupon_scraper.py` | RetailMeNot coupon scraper (Layer 3 stacking) | Free (HTTP + SQLite) |
| `execution/batch_asin_checker.py` | Bulk ASIN lookup from deal groups/Discord | Free (Playwright) or Keepa tokens |
| `execution/storefront_stalker.py` | Scrape competitor seller storefronts | Free (Playwright) |
| `execution/keepa_deal_hunter.py` | Proactive BSR drop / price low scanner | Free (Keepa tokens) |
| `execution/demand_signal_scanner.py` | Google Trends + Reddit spike detection | Free (pytrends + HTTP) |

### Product Analysis
| Script | Purpose | Cost |
|---|---|---|
| `execution/ip_intelligence.py` | Brand IP risk database (160+ brands, scored 0-100) | Free (SQLite) |
| `execution/variation_analyzer.py` | Child ASIN tree analysis, best variation finder | Free (Playwright/Keepa) |
| `execution/seasonal_analyzer.py` | 12-month BSR seasonality + Google Trends buy window | Free (Keepa + pytrends) |

### Wholesale & Supplier
| Script | Purpose | Cost |
|---|---|---|
| `execution/wholesale_manifest_analyzer.py` | Bulk CSV/Excel supplier manifest analysis | Free (openpyxl) |
| `execution/wholesale_supplier_finder.py` | Find/rank wholesale suppliers by category | Free (HTTP) |
| `execution/brand_outreach.py` | Direct brand sourcing outreach automation | Free (HTTP + SQLite) |

### Capital & Coaching
| Script | Purpose | Cost |
|---|---|---|
| `execution/capital_allocator.py` | ROI-weighted purchase optimization for fixed budget | Free (deterministic) |
| `execution/coaching_simulator.py` | Annotated deal walkthrough + what-if PDF for students | Free (reportlab) |

## API Budget

| API | Budget | Notes |
|---|---|---|
| Claude Haiku 4.5 | ~$0.01 per ambiguous match | Only used when match_confidence 0.4-0.7 |
| Keepa (optional) | $19/mo for 10K tokens | BSR, seller count, Amazon-on-listing, deal hunting, stock monitoring, seasonal analysis |
| Playwright (Amazon) | Free | 3+ sec delay between requests required |
| Telegram Bot API | Free | For sourcing alerts (needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) |
| Google Sheets API | Free | Service account auth (needs service_account.json) |
| pytrends (Google Trends) | Free | Rate limited to 5 req/min |
| Reddit JSON API | Free | 1 req/2 sec with proper User-Agent |
| reportlab | Free | Local PDF generation for coaching reports |
| openpyxl | Free | Excel file parsing for wholesale manifests |

## Data Storage

| Store | Path | Purpose |
|---|---|---|
| SQLite DB | `.tmp/sourcing/price_tracker.db` | Price history, alerts, deals, IP risk, coupons, signals, suppliers, outreach, coaching reports, stock, inventory |
| Bookmarks | `.tmp/sourcing/bookmarks.json` | Scheduled sourcing URLs |
| Results | `.tmp/sourcing/{ts}-results.json` | Per-run results |
| CSV exports | `.tmp/sourcing/{ts}-results.csv` | Per-run BUY/MAYBE products |
| Stalker output | `.tmp/stalker/{seller_id}.json` | Storefront analysis results |
| Coaching PDFs | `.tmp/sourcing/coaching_*.pdf` | Student deal walkthrough reports |

## Hard Limits

- Max 50 products per sourcing run
- Max 5 pages of pagination per category scrape
- 3 second minimum delay between Amazon requests
- No Opus usage for any sourcing task
- Cashback estimates are approximate — verify on Rakuten before purchase
- Google Trends: max 5 requests per minute
- Reddit: 1 request per 2 seconds
- Keepa deal hunter: batch 20 ASINs per API call
