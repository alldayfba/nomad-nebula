# Catalog Scrape SOP

> Full retailer catalog dump → Amazon match → velocity analysis → leads list.
> Inspired by StartUpFBA's workflow. Zero-token-first, checkpoint/resume, multi-day capable.

## When to Use

| Use Catalog Mode When... | Use Other Modes When... |
|---|---|
| You want EVERY product from a retailer | You're searching for a specific brand/category |
| You want to find hidden gems across the full catalog | You need quick results (< 5 min) |
| You're willing to spend 1-3 days of Keepa tokens | You need results NOW |
| The retailer has 1K-50K products | The retailer has 500K+ products (too large) |

## Pipeline Stages

1. **SCRAPE** (0 tokens) — Dump entire retailer catalog. Auto-detects platform (Shopify API, sitemap + JSON-LD, or Playwright). Outputs UPC + price + title per variant.
2. **PRE-FILTER** (0 tokens) — Price range (no cap by default), valid UPC, in-stock, dedup, coupon math, price-drop detection.
3. **MATCH** (1 token per product) — Batch UPC lookup on Keepa (100/batch). Maps UPC → ASIN + Amazon price + BSR + weight.
4. **ANALYZE** (0 extra tokens) — Real FBA fee calc (weight-based when available) + velocity analysis + IP risk detection + gating check + Amazon-as-seller detection.
5. **SCORE** (0 tokens) — Confidence scoring (missing data = neutral 50, not 0) → output ALL products with positive margin (StartUpFBA style, tag don't drop).

## Smart Filters (added 2026-03-22)

Every product now includes: `amazon_on_listing`, `ip_risk`, `gating_risk`, `filter_status`, `weight_lbs`, `price_age_days`, `price_stale`, `on_sale`, `price_drop_pct`. Filter presets: `--preset beginner/intermediate/advanced/high_ticket/fast_flips`.

## Store Selection (CRITICAL)

**Multi-brand retailers work best** — stores that carry Nike, Adidas, health/beauty brands etc. that are also sold on Amazon. DTC brands (BBW, ColourPop, Fenty) don't work because their products aren't on Amazon. Target clearance pages specifically — `clearance_scanner.py` handles this.

| Store Type | Hit Rate | Example |
|---|---|---|
| Multi-brand clearance | HIGH | Walmart, Target, CVS, Kohl's clearance |
| Multi-brand full price | MEDIUM | ShopWSS, Dick's (arb from MSRP gap) |
| DTC / single-brand | LOW | BBW, Fenty, ColourPop (products not on Amazon) |

## CLI Usage

```bash
# Basic: scrape ShopWSS, spend up to 3000 tokens
python execution/source.py catalog https://www.shopwss.com

# Quick test: 100 products only, 50 tokens
python execution/source.py catalog https://www.shopwss.com --limit-scrape 100 --max-tokens 50

# With coupon: apply 20% discount to all prices
python execution/source.py catalog https://www.kohls.com --coupon "20% off"

# Adjust filters
python execution/source.py catalog https://www.shopwss.com --min-roi 20 --min-profit 2 --max-price 100

# Resume from checkpoint (multi-day run)
python execution/source.py catalog https://www.shopwss.com --resume --max-tokens 3000

# Direct pipeline (bypasses source.py)
python execution/catalog_pipeline.py https://www.shopwss.com --max-tokens 3000 --json
```

## Token Budget Planning

| Catalog Size | Tokens Needed | Days (Pro tier) |
|---|---|---|
| 1K products | ~1,000 | < 1 day |
| 5K products | ~5,000 | 1-2 days |
| 10K products | ~10,000 | 2-3 days |
| 30K products | ~30,000 | 5-7 days |

Pro tier refills at ~7,200 tokens/day. Use `--max-tokens` to cap daily spend.

## Platform Detection

The scraper auto-detects the e-commerce platform:

| Platform | Detection | Speed | UPC Source |
|---|---|---|---|
| **Shopify** | `/products.json` returns JSON | Fast (API, no browser) | `variants[].barcode` via per-product .json |
| **Sitemap + JSON-LD** | `/sitemap.xml` exists with product URLs | Medium (HTTP per page) | `schema.org/Product` gtin12/gtin13 |
| **Sitemap + Playwright** | Fallback for JS-rendered sites | Slow (headless browser) | CSS selectors from retailer_configs.py |

## Supported Retailers (Tested)

| Retailer | Platform | Products | UPC Coverage |
|---|---|---|---|
| ShopWSS | Shopify | ~6,600 | 100% |

*Add more as tested. Any Shopify store should work. Sitemap-based retailers need testing.*

## Outputs

- **Leads JSON:** `.tmp/sourcing/results/{domain}_{date}_leads.json`
- **Catalog cache:** `.tmp/sourcing/catalogs/{domain}_{date}.json` (TTL: 7 days)
- **Checkpoints:** `.tmp/sourcing/pipeline_checkpoints/` (auto-cleaned on success)

## Scripts

| Script | Purpose |
|---|---|
| `execution/catalog_scraper.py` | Universal retailer catalog dumper |
| `execution/velocity_analyzer.py` | Keepa inventory velocity engine |
| `execution/catalog_pipeline.py` | 5-stage orchestrator |
| `execution/source.py` (mode: catalog) | CLI entry point |

## API Endpoint

```
POST /api/sourcing
{
    "mode": "catalog",
    "retailer_url": "https://www.shopwss.com",
    "max_tokens": 3000,
    "min_roi": 30,
    "min_profit": 3,
    "coupon": "20% off",
    "limit_scrape": 100
}
```

## Confidence Scoring

```
score = ROI(25%) + Velocity(25%) + BSR(20%) + Competition(15%) + Price Stability(15%)

≥70 = BUY    — High confidence, take action
≥50 = MAYBE  — Promising, verify manually
≥30 = RESEARCH — Worth investigating
<30 = SKIP   — Not enough signal
```

## Edge Cases

- **No UPC:** Products without valid UPC (12-13 digits) are skipped. Log shows count.
- **Rate limited:** Exponential backoff on 429s. Shopify: 2 req/sec default.
- **Token exhaustion mid-run:** Auto-checkpoints. Resume next day with `--resume`.
- **Stale catalog:** Cache TTL is 7 days. Delete `.tmp/sourcing/catalogs/` to force re-scrape.
- **Pack size mismatch:** verify_sourcing_results.py catches these (ROI > 1000% = suspicious).
