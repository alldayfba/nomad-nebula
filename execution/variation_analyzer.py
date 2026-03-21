#!/usr/bin/env python3
"""
Script: variation_analyzer.py
Purpose: Scrape the full variation tree for any Amazon parent or child ASIN,
         rank each child variation by demand/competition, and surface the
         single best child ASIN to source.
Inputs:  subcommand (analyze | best), --asin, optional flags
Outputs: JSON (stdout) with ranked variation list and best/worst picks

Usage:
  python execution/variation_analyzer.py analyze --asin B08XYZ1234
  python execution/variation_analyzer.py analyze --asin B08XYZ1234 --use-keepa --max-variations 20
  python execution/variation_analyzer.py best --asin B08XYZ1234
  python execution/variation_analyzer.py analyze --asin B08XYZ1234 --output .tmp/variations/result.json
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Re-use shared helpers from sibling scripts ────────────────────────────────
from execution.match_amazon_products import (
    get_amazon_product_details,
    get_keepa_product_details,
    USER_AGENT,
    parse_amazon_price,
)
from execution.calculate_fba_profitability import (
    estimate_monthly_sales,
    score_competition,
    check_restrictions,
)

KEEPA_API_KEY = os.getenv("KEEPA_API_KEY")
PAGE_DELAY = 3.5  # seconds between Playwright page loads


# ── Variation Discovery ───────────────────────────────────────────────────────

def _parse_twister_data(html: str) -> dict:
    """Extract variation ASIN map from Amazon's inline 'twister' JS data.

    Amazon embeds a JSON blob like:
      "dimensionValuesDisplayData" : { "B0CHILD001": ["Black", "M"], ... }
    and
      "asinVariationValues" : { "B0CHILD001": {"color": "black", "size": "m"}, ... }

    Returns dict: { asin -> {dimension: value, ...} }
    """
    asin_map: dict = {}

    # Primary pattern: twister-plus-buying-options or variation data
    patterns = [
        r'"asinVariationValues"\s*:\s*(\{[^}]+\})',
        r'"dimensionValuesDisplayData"\s*:\s*(\{.*?\})\s*,\s*"',
        r'twister_hero_asin_variation_values\s*=\s*(\{.*?\});',
    ]

    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if not m:
            continue
        try:
            raw = json.loads(m.group(1))
            for asin, dims in raw.items():
                if len(asin) == 10 and asin.startswith("B0") or re.match(r"^[A-Z0-9]{10}$", asin):
                    if isinstance(dims, dict):
                        asin_map[asin] = dims
                    elif isinstance(dims, list):
                        asin_map[asin] = {"label": " / ".join(str(v) for v in dims)}
            if asin_map:
                break
        except (json.JSONDecodeError, ValueError):
            continue

    # Fallback: scan for ASIN→label pairs in dimensionValuesDisplayData
    if not asin_map:
        m2 = re.search(r'"dimensionValuesDisplayData"\s*:\s*(\{.*?\})\s*[,}]', html, re.DOTALL)
        if m2:
            try:
                raw2 = json.loads(m2.group(1))
                for asin, vals in raw2.items():
                    if re.match(r"^[A-Z0-9]{10}$", asin):
                        if isinstance(vals, list):
                            asin_map[asin] = {"label": " / ".join(str(v) for v in vals)}
                        elif isinstance(vals, dict):
                            asin_map[asin] = vals
            except (json.JSONDecodeError, ValueError):
                pass

    return asin_map


def _extract_variation_dimensions(soup: BeautifulSoup) -> list:
    """Extract variation dimension names (e.g., ['Color', 'Size']) from the page."""
    dims = []
    # Amazon labels variation sections with labels like "Color:" or "Size:"
    for label_el in soup.select("label.a-form-label, span.a-color-secondary.a-size-small.a-text-bold"):
        text = label_el.get_text(strip=True).rstrip(":")
        if text and len(text) < 30 and text not in dims:
            dims.append(text)
    # Also look at twister section headers
    for el in soup.select("div#twister span.selection, div.twisterTextDiv"):
        text = el.get_text(strip=True)
        if text and len(text) < 30 and text not in dims:
            dims.append(text)
    return dims


def _extract_current_asin(page) -> str | None:
    """Extract current page ASIN from URL or page source."""
    url = page.url
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    if m:
        return m.group(1)
    # Fallback: look in page source
    html = page.content()
    m2 = re.search(r'"ASIN"\s*:\s*"([A-Z0-9]{10})"', html)
    if m2:
        return m2.group(1)
    return None


def _get_parent_asin(soup: BeautifulSoup, html: str) -> str | None:
    """Try to find the parent ASIN from a child variation page."""
    # Amazon sometimes embeds parentAsin in JS
    m = re.search(r'"parentAsin"\s*:\s*"([A-Z0-9]{10})"', html)
    if m:
        return m.group(1)
    # Look for "parent_asin" in hidden inputs or data attributes
    el = soup.select_one('input[name="ASIN"], input[id="ASIN"]')
    if el and el.get("value") and len(el["value"]) == 10:
        return el["value"]
    return None


def discover_variations(page, asin: str) -> tuple[str, str, list, list]:
    """Navigate to an ASIN page and discover all child variation ASINs.

    Returns:
        parent_asin (str),
        product_name (str),
        variation_dimensions (list of str),
        child_asins (list of dict: {asin, label, price})
    """
    url = f"https://www.amazon.com/dp/{asin}"
    print(f"[variation] Loading {url}", file=sys.stderr)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(int(PAGE_DELAY * 1000))
    except Exception as e:
        print(f"[variation] Page load error: {e}", file=sys.stderr)
        return asin, "", [], []

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    # CAPTCHA guard
    if soup.select_one("form[action*='captcha']") or "robot" in html[:1000].lower():
        print("[variation] CAPTCHA detected — aborting", file=sys.stderr)
        return asin, "", [], []

    # Product name
    name_el = soup.select_one("#productTitle, h1#title span")
    product_name = name_el.get_text(strip=True) if name_el else ""

    # Resolve parent ASIN (current page might already be a child)
    parent_asin = _get_parent_asin(soup, html) or asin

    # Variation dimensions
    variation_dimensions = _extract_variation_dimensions(soup)

    # Primary: parse twister JS blob for all variation ASINs
    asin_map = _parse_twister_data(html)
    print(f"[variation] Twister parse found {len(asin_map)} variations", file=sys.stderr)

    # Fallback: parse inline variation links / data-defaultasin attributes
    if not asin_map:
        for li in soup.select("li[data-asin], div[data-asin]"):
            child = li.get("data-asin", "")
            if child and len(child) == 10 and child != parent_asin:
                asin_map[child] = {}

    # Build child list with labels and prices from the map
    child_list = []
    price_el_map = {}  # asin → price string (best effort from swatches)

    for child_asin, dim_vals in asin_map.items():
        if not re.match(r"^[A-Z0-9]{10}$", child_asin):
            continue
        # Build human label from dimension values
        if isinstance(dim_vals, dict):
            label = " / ".join(str(v) for v in dim_vals.values() if v)
        else:
            label = str(dim_vals)

        # Try to extract price from swatch markup (not always available)
        price = None
        swatch_el = soup.select_one(f'[data-asin="{child_asin}"] .a-price span.a-offscreen')
        if swatch_el:
            price = parse_amazon_price(swatch_el.get_text(strip=True))

        child_list.append({"asin": child_asin, "label": label or child_asin, "price": price})

    # If still empty, treat the landing ASIN itself as the only "variation"
    if not child_list:
        current = _extract_current_asin(page) or asin
        child_list.append({"asin": current, "label": "default", "price": None})

    print(f"[variation] Found {len(child_list)} child ASINs for parent {parent_asin}", file=sys.stderr)
    return parent_asin, product_name, variation_dimensions, child_list


# ── Per-Child Enrichment ──────────────────────────────────────────────────────

def _enrich_via_keepa(child_asin: str) -> dict:
    """Fetch BSR, reviews, FBA count via Keepa API."""
    details = get_keepa_product_details(child_asin)
    if not details:
        return {}
    return {
        "bsr": details.get("sales_rank"),
        "category": details.get("category"),
        "price": details.get("fba_price") or details.get("amazon_price"),
        "fba_sellers": details.get("fba_seller_count"),
        "amazon_on_listing": details.get("amazon_on_listing"),
        "reviews": None,   # Keepa doesn't return review count directly here
        "rating": None,
    }


def _enrich_via_playwright(page, child_asin: str) -> dict:
    """Fetch BSR, reviews, FBA count by visiting the product detail page."""
    url = f"https://www.amazon.com/dp/{child_asin}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(int(PAGE_DELAY * 1000))
    except Exception as e:
        print(f"  [enrich] Page load error for {child_asin}: {e}", file=sys.stderr)
        return {}

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    if soup.select_one("form[action*='captcha']"):
        print(f"  [enrich] CAPTCHA on {child_asin}", file=sys.stderr)
        return {}

    details = get_amazon_product_details(page, child_asin)

    # Price
    price_el = soup.select_one("span.a-price span.a-offscreen, #priceblock_ourprice, #priceblock_dealprice")
    price = parse_amazon_price(price_el.get_text(strip=True) if price_el else None)

    # Reviews
    reviews = None
    review_el = soup.select_one("#acrCustomerReviewText, span[data-hook='total-review-count']")
    if review_el:
        m = re.search(r"([\d,]+)", review_el.get_text())
        if m:
            reviews = int(m.group(1).replace(",", ""))

    # Rating
    rating = None
    rating_el = soup.select_one("span[data-hook='rating-out-of-text'], i.a-icon-star span.a-icon-alt")
    if rating_el:
        m = re.search(r"([\d.]+)", rating_el.get_text())
        if m:
            rating = float(m.group(1))

    return {
        "bsr": details.get("sales_rank"),
        "category": details.get("category"),
        "price": price,
        "fba_sellers": details.get("fba_seller_count"),
        "amazon_on_listing": details.get("amazon_on_listing"),
        "reviews": reviews,
        "rating": rating,
    }


def enrich_children(page, children: list, use_keepa: bool, max_variations: int) -> list:
    """Enrich each child ASIN with BSR, reviews, FBA count, price."""
    enriched = []
    total = min(len(children), max_variations)
    for i, child in enumerate(children[:max_variations]):
        child_asin = child["asin"]
        print(f"  [{i + 1}/{total}] Enriching {child_asin} — {child.get('label', '')[:40]}",
              file=sys.stderr)
        if use_keepa and KEEPA_API_KEY:
            data = _enrich_via_keepa(child_asin)
        else:
            data = _enrich_via_playwright(page, child_asin)
            time.sleep(0.5)  # slight extra buffer on top of page delay

        # Merge into child record; prefer discovered price if enrichment has none
        merged = {**child, **data}
        if not merged.get("price") and child.get("price"):
            merged["price"] = child["price"]
        enriched.append(merged)

    return enriched


# ── Ranking Algorithm ─────────────────────────────────────────────────────────

def _demand_score(bsr: int | None, all_bsrs: list) -> float:
    """Score 0-40 based on BSR. Lower BSR = higher score."""
    if bsr is None or bsr <= 0:
        return 0.0
    # Normalize against the best (lowest) BSR in the set
    valid = [b for b in all_bsrs if b and b > 0]
    if not valid:
        return 0.0
    best_bsr = min(valid)
    worst_bsr = max(valid)
    if best_bsr == worst_bsr:
        return 40.0
    # Linear interpolation: best_bsr → 40 pts, worst_bsr → 0 pts
    spread = worst_bsr - best_bsr
    score = 40.0 * (1 - (bsr - best_bsr) / spread)
    return round(max(0.0, min(40.0, score)), 2)


def _competition_score_points(fba_sellers: int | None, amazon_on_listing: bool) -> float:
    """Score 0-30 based on FBA seller count and Amazon presence."""
    if amazon_on_listing:
        return 0.0
    if fba_sellers is None:
        return 15.0  # unknown → mid-credit
    if fba_sellers <= 2:
        return 30.0
    if fba_sellers <= 5:
        return 22.0
    if fba_sellers <= 10:
        return 14.0
    if fba_sellers <= 20:
        return 6.0
    return 0.0


def _review_gap_score(reviews: int | None, avg_reviews: float) -> float:
    """Score 0-20. Fewer reviews than parent average = more opportunity."""
    if reviews is None:
        return 10.0  # unknown → half credit
    if avg_reviews <= 0:
        return 10.0
    ratio = reviews / avg_reviews
    if ratio < 0.25:
        return 20.0  # far fewer reviews than average — big opportunity
    if ratio < 0.50:
        return 15.0
    if ratio < 1.0:
        return 10.0
    if ratio < 2.0:
        return 5.0
    return 0.0  # way more reviews than average — established, competitive


def _price_score(price: float | None) -> float:
    """Score 0-10. Sweet spot $15-$50 scores highest."""
    if price is None:
        return 5.0
    if 15 <= price <= 50:
        return 10.0
    if 10 <= price < 15 or 50 < price <= 65:
        return 6.0
    if price < 10:
        return 2.0
    return 3.0  # >$65


def score_variation(child: dict, all_bsrs: list, avg_reviews: float) -> int:
    """Compute composite variation_score 0-100."""
    demand = _demand_score(child.get("bsr"), all_bsrs)
    competition = _competition_score_points(child.get("fba_sellers"), child.get("amazon_on_listing", False))
    review_gap = _review_gap_score(child.get("reviews"), avg_reviews)
    price_pts = _price_score(child.get("price"))
    total = demand + competition + review_gap + price_pts
    return min(100, max(0, round(total)))


def rank_variations(enriched: list) -> list:
    """Score and rank all enriched child variations. Returns sorted list."""
    all_bsrs = [c.get("bsr") for c in enriched]
    all_reviews = [c["reviews"] for c in enriched if c.get("reviews") is not None]
    avg_reviews = sum(all_reviews) / len(all_reviews) if all_reviews else 0.0

    for child in enriched:
        bsr = child.get("bsr")
        category = child.get("category")
        monthly_sales = estimate_monthly_sales(bsr, category) if bsr else None
        child["monthly_sales_est"] = monthly_sales
        child["variation_score"] = score_variation(child, all_bsrs, avg_reviews)
        child["recommendation"] = ""  # assigned after sort

    enriched.sort(key=lambda c: c["variation_score"], reverse=True)

    # Tag the best
    if enriched:
        enriched[0]["recommendation"] = "BEST_PICK"
        if len(enriched) > 1:
            enriched[-1]["recommendation"] = "WORST_PICK"

    return enriched


# ── Output Formatting ─────────────────────────────────────────────────────────

def _clean_child(child: dict) -> dict:
    """Normalize a child dict to the canonical output schema."""
    return {
        "asin": child.get("asin", ""),
        "label": child.get("label", ""),
        "price": child.get("price"),
        "bsr": child.get("bsr"),
        "reviews": child.get("reviews"),
        "rating": child.get("rating"),
        "fba_sellers": child.get("fba_sellers"),
        "amazon_on_listing": child.get("amazon_on_listing"),
        "monthly_sales_est": child.get("monthly_sales_est"),
        "variation_score": child.get("variation_score", 0),
        "recommendation": child.get("recommendation", ""),
    }


def build_output(parent_asin: str, product_name: str, variation_dimensions: list,
                 ranked: list) -> dict:
    """Assemble the final output JSON structure."""
    cleaned = [_clean_child(c) for c in ranked]

    best = cleaned[0] if cleaned else None
    worst = cleaned[-1] if len(cleaned) > 1 else None

    # Demand spread: ratio of best to worst monthly_sales_est
    demand_spread = "unknown"
    if best and worst:
        best_sales = best.get("monthly_sales_est") or 0
        worst_sales = worst.get("monthly_sales_est") or 0
        if worst_sales and worst_sales > 0:
            ratio = round(best_sales / worst_sales, 1)
            demand_spread = f"{ratio}x between best and worst variation"
        elif best_sales:
            demand_spread = f"Best variation est. {best_sales} units/mo; worst has no sales data"

    return {
        "parent_asin": parent_asin,
        "product_name": product_name,
        "variation_dimensions": variation_dimensions,
        "total_variations": len(cleaned),
        "variations": cleaned,
        "best_child": best,
        "worst_child": worst,
        "summary": {
            "best_asin": best["asin"] if best else None,
            "demand_spread": demand_spread,
        },
        "analyzed_at": datetime.now().isoformat(),
        "data_source": "keepa" if (KEEPA_API_KEY) else "playwright",
    }


# ── Subcommand Handlers ───────────────────────────────────────────────────────

def cmd_analyze(args) -> dict:
    """Full analyze subcommand: discover all variations, enrich, rank, return JSON."""
    use_keepa = args.use_keepa and bool(KEEPA_API_KEY)
    max_variations = args.max_variations

    if args.use_keepa and not KEEPA_API_KEY:
        print("[variation] --use-keepa requested but KEEPA_API_KEY not set — falling back to Playwright",
              file=sys.stderr)

    print(f"[variation] Analyzing ASIN: {args.asin}", file=sys.stderr)
    print(f"[variation] Data source: {'Keepa' if use_keepa else 'Playwright'}", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        # Step 1: discover variations
        parent_asin, product_name, variation_dimensions, children = discover_variations(page, args.asin)

        if not children:
            print("[variation] No variations found — exiting", file=sys.stderr)
            browser.close()
            return {"error": "No variations discovered", "asin": args.asin}

        # Step 2: enrich each child
        enriched = enrich_children(page, children, use_keepa, max_variations)
        browser.close()

    # Step 3: score and rank
    ranked = rank_variations(enriched)

    # Step 4: build output
    result = build_output(parent_asin, product_name, variation_dimensions, ranked)

    print(f"[variation] Done. {len(ranked)} variations ranked. "
          f"Best: {result['summary']['best_asin']}", file=sys.stderr)
    return result


def cmd_best(args) -> dict:
    """Quick mode: return only the single best child ASIN."""
    # Reuse analyze but suppress full variation list in output
    full = cmd_analyze(args)
    if "error" in full:
        return full
    best = full.get("best_child")
    return {
        "parent_asin": full["parent_asin"],
        "product_name": full["product_name"],
        "best_child": best,
        "total_variations_analyzed": full["total_variations"],
        "analyzed_at": full["analyzed_at"],
        "data_source": full["data_source"],
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Analyze Amazon variation tree — rank child ASINs by demand/competition"
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Shared arguments for both subcommands
    def add_common_args(sp):
        sp.add_argument("--asin", required=True, help="Amazon parent or child ASIN")
        sp.add_argument("--use-keepa", action="store_true",
                        help="Use Keepa API for enrichment (requires KEEPA_API_KEY in .env)")
        sp.add_argument("--max-variations", type=int, default=50,
                        help="Max child ASINs to enrich (default: 50)")
        sp.add_argument("--output", type=str, default=None,
                        help="Write JSON output to file path (default: stdout)")

    sp_analyze = subparsers.add_parser("analyze", help="Full variation tree analysis")
    add_common_args(sp_analyze)

    sp_best = subparsers.add_parser("best", help="Quick mode — return only the single best child ASIN")
    add_common_args(sp_best)

    args = parser.parse_args()

    # Dispatch
    if args.subcommand == "analyze":
        result = cmd_analyze(args)
    elif args.subcommand == "best":
        result = cmd_best(args)
    else:
        parser.print_help()
        sys.exit(1)

    # Output
    output_json = json.dumps(result, indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json)
        print(f"[variation] Output written to {out_path}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
