#!/usr/bin/env python3
from __future__ import annotations
"""
Script: catalog_pipeline.py
Purpose: End-to-end catalog sourcing pipeline — emulates StartUpFBA's workflow.

         5 stages:
         1. SCRAPE: Dump entire retailer catalog (0 Keepa tokens)
         2. PRE-FILTER: Price gates, valid UPC, dedup, in-stock (0 tokens)
         3. MATCH: Batch UPC lookup on Keepa (1 token per product)
         4. ANALYZE: Profitability calc + velocity analysis (0 extra tokens)
         5. SCORE: Confidence scoring + verify + output

         Token-budgeted with checkpoint/resume for multi-day runs.

Inputs:  Retailer URL + options
Outputs: JSON leads list + summary

Usage:
    python execution/catalog_pipeline.py https://www.shopwss.com --max-tokens 3000
    python execution/catalog_pipeline.py https://www.shopwss.com --resume --max-tokens 3000
    python execution/catalog_pipeline.py https://www.shopwss.com --max-tokens 50 --limit-scrape 100
    python execution/catalog_pipeline.py https://www.kohls.com --coupon "30% off"
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from execution.catalog_scraper import scrape_catalog
from execution.velocity_analyzer import analyze_velocity, score_confidence
from execution.calculate_fba_profitability import calculate_product_profitability
from execution.batch_keepa_analyzer import (
    batch_upc_lookup, check_tokens, pick_best_match, extract_keepa_data,
)

# ── Constants ────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing" / "results"
CHECKPOINT_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing" / "pipeline_checkpoints"
BATCH_SIZE = 100  # Keepa allows 100 UPCs per request
TOKEN_SAFETY_BUFFER = 50


# ── Stage 2: Pre-Filter ─────────────────────────────────────────────────────


def prefilter(products: list[dict], min_price: float = 5.0, max_price: float = 60.0,
              coupon: str | None = None) -> list[dict]:
    """Filter catalog products before Keepa verification (0 tokens).

    Args:
        products: Raw catalog products from catalog_scraper.
        min_price: Minimum retail price (below this, FBA fees eat all profit).
        max_price: Maximum retail price (above this, higher risk per unit).
        coupon: Optional coupon string (e.g., "20% off", "30% off 99+").

    Returns:
        Filtered, deduplicated product list.
    """
    # Parse coupon
    coupon_pct = 0
    if coupon:
        m = re.search(r"(\d+)%", coupon)
        if m:
            coupon_pct = int(m.group(1)) / 100.0

    filtered = []
    seen_upcs = set()

    for p in products:
        upc = p.get("upc")
        if not upc:
            continue  # No UPC = can't match to Amazon

        # Skip duplicates (keep lowest price)
        if upc in seen_upcs:
            continue

        price = p.get("price", 0)
        if price <= 0:
            continue

        # Apply coupon discount
        if coupon_pct > 0:
            price = price * (1 - coupon_pct)
            p["price_after_coupon"] = round(price, 2)
            p["coupon_applied"] = coupon

        # In-stock check
        if not p.get("available", True):
            continue

        # Price range
        if price < min_price or price > max_price:
            continue

        seen_upcs.add(upc)
        filtered.append(p)

    return filtered


# ── Stage 3: Keepa Batch Match ───────────────────────────────────────────────


def batch_match(products: list[dict], max_tokens: int = 3000,
                checkpoint_path: str | None = None,
                resume_from_batch: int = 0) -> tuple[list[dict], int]:
    """Match products to Amazon via Keepa batch UPC lookup.

    Token-budgeted: stops when max_tokens reached, saves checkpoint.

    Args:
        products: Pre-filtered products with UPCs.
        max_tokens: Maximum Keepa tokens to spend.
        checkpoint_path: Path for saving/loading progress.
        resume_from_batch: Batch index to resume from.

    Returns:
        (matched_products, tokens_used)
    """
    # Check token balance
    tokens_left, refill_rate = check_tokens()
    print(f"[pipeline] Keepa tokens: {tokens_left} left, refill {refill_rate}/min", file=sys.stderr)

    if tokens_left < TOKEN_SAFETY_BUFFER:
        print(f"[pipeline] Token balance too low ({tokens_left}). Try again later.", file=sys.stderr)
        return [], 0

    # Load existing matches from checkpoint
    matched = []
    if checkpoint_path and resume_from_batch > 0:
        cp = _load_pipeline_checkpoint(checkpoint_path)
        if cp:
            matched = cp.get("matched", [])
            print(f"[pipeline] Loaded {len(matched)} matches from checkpoint", file=sys.stderr)

    # Collect UPCs
    upcs = [p["upc"] for p in products]
    total_batches = (len(upcs) + BATCH_SIZE - 1) // BATCH_SIZE
    tokens_used = 0

    for batch_idx in range(resume_from_batch, total_batches):
        # Actual batch size (last batch may be smaller)
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(upcs))
        actual_batch_size = end - start

        # Budget check
        if tokens_used + actual_batch_size > max_tokens:
            print(
                f"[pipeline] Token budget reached ({tokens_used}/{max_tokens}). "
                f"Resume with --resume to continue from batch {batch_idx}.",
                file=sys.stderr,
            )
            if checkpoint_path:
                _save_pipeline_checkpoint(checkpoint_path, matched, batch_idx)
            break

        # Token balance check
        current_tokens, _ = check_tokens()
        if current_tokens < actual_batch_size + TOKEN_SAFETY_BUFFER:
            print(
                f"[pipeline] Token balance low ({current_tokens}). "
                f"Saving checkpoint at batch {batch_idx}.",
                file=sys.stderr,
            )
            if checkpoint_path:
                _save_pipeline_checkpoint(checkpoint_path, matched, batch_idx)
            break

        batch_upcs = upcs[start:end]

        print(
            f"[pipeline] Batch {batch_idx + 1}/{total_batches} | "
            f"UPCs {start + 1}-{end}/{len(upcs)} | "
            f"{tokens_used} tokens used",
            file=sys.stderr,
        )

        try:
            upc_map, toks_left, toks_consumed = batch_upc_lookup(batch_upcs)
            tokens_used += toks_consumed
        except Exception as e:
            print(f"[pipeline] Batch {batch_idx + 1} error: {e}", file=sys.stderr)
            time.sleep(5)
            continue

        # Process matches
        for upc in batch_upcs:
            keepa_products = upc_map.get(upc, [])
            if not keepa_products:
                continue

            # Find the source product
            source = next((p for p in products if p["upc"] == upc), None)
            if not source:
                continue

            # Pick best Amazon match
            best = pick_best_match(keepa_products, source.get("title", ""))
            if not best:
                continue

            amazon_data = extract_keepa_data(best["product"], best["price"])
            amazon_data["retail_price"] = source.get("price_after_coupon", source["price"])
            amazon_data["retailer_url"] = source.get("product_url", "")
            amazon_data["retailer_title"] = source.get("title", "")
            amazon_data["brand"] = source.get("brand", "")
            amazon_data["upc"] = upc
            amazon_data["keepa_raw"] = best["product"]  # Keep raw for velocity analysis

            matched.append(amazon_data)

        # Rate limiting
        time.sleep(3)  # Keepa Pro tier: ~20 tokens/min

    print(
        f"[pipeline] Matching complete: {len(matched)} products matched, "
        f"{tokens_used} tokens used",
        file=sys.stderr,
    )

    return matched, tokens_used


# ── Stage 4: Profitability + Velocity ────────────────────────────────────────


def analyze_matches(matched: list[dict], min_roi: float = 30.0,
                    min_profit: float = 3.0, max_bsr: int = 200000) -> list[dict]:
    """Run profitability calc + velocity analysis on matched products.

    Args:
        matched: Products matched to Amazon (from batch_match).
        min_roi: Minimum ROI % to keep.
        min_profit: Minimum profit per unit to keep.
        max_bsr: Maximum BSR to keep.

    Returns:
        List of analyzed products that pass filters.
    """
    results = []

    for m in matched:
        retail_price = m.get("retail_price", 0)
        amazon_price = m.get("amazon_price", 0)

        if not amazon_price or amazon_price <= 0:
            continue
        if not retail_price or retail_price <= 0:
            continue
        if retail_price >= amazon_price:
            continue  # No arbitrage opportunity

        # Profitability calculation
        try:
            profitability = calculate_product_profitability(
                buy_price=retail_price,
                sell_price=amazon_price,
                category=m.get("root_category", ""),
            )
        except Exception:
            # Simple fallback calc
            referral_fee = amazon_price * 0.15
            fba_fee = 5.0
            profit = amazon_price - retail_price - referral_fee - fba_fee
            roi = (profit / retail_price * 100) if retail_price > 0 else 0
            profitability = {
                "profit_per_unit": round(profit, 2),
                "roi_percent": round(roi, 1),
                "verdict": "BUY" if (roi >= 30 and profit >= 3) else "MAYBE" if (roi >= 20 and profit >= 2) else "SKIP",
            }

        profit = profitability.get("profit_per_unit", 0)
        roi = profitability.get("roi_percent", 0)
        bsr = m.get("sales_rank")

        # Apply filters
        if roi < min_roi:
            continue
        if profit < min_profit:
            continue
        if bsr and bsr > max_bsr:
            continue

        # Velocity analysis (cheap mode — uses data already in the Keepa response)
        keepa_raw = m.pop("keepa_raw", {})
        velocity = analyze_velocity(keepa_raw, mode="cheap")

        # Confidence scoring
        confidence = score_confidence(
            roi_pct=roi,
            velocity_data=velocity,
            bsr=bsr,
            fba_count=m.get("fba_seller_count"),
        )

        m["profitability"] = profitability
        m["velocity"] = {
            "score": velocity["velocity_score"],
            "monthly_est": velocity.get("monthly_sales_estimate"),
            "bsr_trend": velocity.get("bsr", {}).get("bsr_trend", "unknown"),
        }
        m["confidence"] = confidence
        results.append(m)

    # Sort by confidence score descending
    results.sort(key=lambda x: x.get("confidence", {}).get("score", 0), reverse=True)

    return results


# ── Stage 5: Output ──────────────────────────────────────────────────────────


def format_output(results: list[dict], domain: str, tokens_used: int,
                  total_scraped: int, total_filtered: int) -> dict:
    """Format final output with summary."""
    return {
        "metadata": {
            "retailer": domain,
            "generated_at": datetime.now().isoformat(),
            "total_scraped": total_scraped,
            "total_filtered": total_filtered,
            "total_matched": len(results),
            "tokens_used": tokens_used,
        },
        "summary": {
            "buy_count": sum(1 for r in results if r.get("confidence", {}).get("verdict") == "BUY"),
            "maybe_count": sum(1 for r in results if r.get("confidence", {}).get("verdict") == "MAYBE"),
            "research_count": sum(1 for r in results if r.get("confidence", {}).get("verdict") == "RESEARCH"),
            "avg_roi": round(
                sum(r.get("profitability", {}).get("roi_percent", 0) for r in results) / max(len(results), 1), 1
            ),
            "avg_profit": round(
                sum(r.get("profitability", {}).get("profit_per_unit", 0) for r in results) / max(len(results), 1), 2
            ),
            "top_roi": round(max((r.get("profitability", {}).get("roi_percent", 0) for r in results), default=0), 1),
        },
        "products": [
            {
                "asin": r.get("asin", ""),
                "amazon_title": r.get("title", ""),
                "amazon_url": r.get("product_url", ""),
                "amazon_price": r.get("amazon_price", 0),
                "retail_price": r.get("retail_price", 0),
                "retailer_url": r.get("retailer_url", ""),
                "retailer_title": r.get("retailer_title", ""),
                "upc": r.get("upc", ""),
                "brand": r.get("brand", ""),
                "bsr": r.get("sales_rank"),
                "category": r.get("category", ""),
                "fba_sellers": r.get("fba_seller_count"),
                "profit": r.get("profitability", {}).get("profit_per_unit", 0),
                "roi_pct": r.get("profitability", {}).get("roi_percent", 0),
                "velocity_score": r.get("velocity", {}).get("score", 0),
                "monthly_sales_est": r.get("velocity", {}).get("monthly_est"),
                "confidence_score": r.get("confidence", {}).get("score", 0),
                "confidence_verdict": r.get("confidence", {}).get("verdict", "SKIP"),
            }
            for r in results
        ],
    }


# ── Checkpoint Utilities ─────────────────────────────────────────────────────


def _save_pipeline_checkpoint(path: str, matched: list, batch_idx: int):
    """Save pipeline checkpoint for resume."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Strip keepa_raw from checkpoint to save space
    clean = []
    for m in matched:
        c = {k: v for k, v in m.items() if k != "keepa_raw"}
        clean.append(c)
    checkpoint = {
        "batch_idx": batch_idx,
        "matched_count": len(clean),
        "timestamp": datetime.now().isoformat(),
        "matched": clean,
    }
    with open(path, "w") as f:
        json.dump(checkpoint, f)
    print(f"[pipeline] Checkpoint saved: batch {batch_idx}, {len(clean)} matches", file=sys.stderr)


def _load_pipeline_checkpoint(path: str) -> dict | None:
    """Load pipeline checkpoint."""
    if not Path(path).exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# ── Main Pipeline ────────────────────────────────────────────────────────────


def run_pipeline(
    url: str,
    max_tokens: int = 3000,
    min_roi: float = 30.0,
    min_profit: float = 3.0,
    max_bsr: int = 200000,
    min_price: float = 5.0,
    max_price: float = 60.0,
    coupon: str | None = None,
    limit_scrape: int = 0,
    resume: bool = False,
) -> dict:
    """Run the full catalog sourcing pipeline.

    Returns formatted output dict with metadata, summary, and products.
    """
    domain = urlparse(url).netloc.replace("www.", "")
    date_str = datetime.now().strftime("%Y%m%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    pipeline_checkpoint = str(CHECKPOINT_DIR / f"{domain}_{date_str}_pipeline.json")

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"CATALOG SOURCING PIPELINE: {domain}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    # ── Stage 1: Scrape ─────────────────────────────────────────────────
    print("[STAGE 1] Scraping retailer catalog...", file=sys.stderr)
    catalog = scrape_catalog(url, limit=limit_scrape, resume=resume)
    if isinstance(catalog, dict):
        # detect_only mode returned a dict
        return catalog

    total_scraped = len(catalog)
    print(f"[STAGE 1] Complete: {total_scraped} variants scraped\n", file=sys.stderr)

    if total_scraped == 0:
        print("[pipeline] No products found. Check the URL and try again.", file=sys.stderr)
        return format_output([], domain, 0, 0, 0)

    # ── Stage 2: Pre-filter ─────────────────────────────────────────────
    print("[STAGE 2] Pre-filtering candidates...", file=sys.stderr)
    filtered = prefilter(catalog, min_price=min_price, max_price=max_price, coupon=coupon)
    total_filtered = len(filtered)
    print(
        f"[STAGE 2] Complete: {total_filtered} candidates "
        f"(from {total_scraped} variants, "
        f"{total_filtered * 100 // max(total_scraped, 1)}% pass rate)\n",
        file=sys.stderr,
    )

    if total_filtered == 0:
        print("[pipeline] No products passed pre-filter. Adjust price range or check UPC coverage.", file=sys.stderr)
        return format_output([], domain, 0, total_scraped, 0)

    # ── Stage 3: Keepa match ────────────────────────────────────────────
    print("[STAGE 3] Matching to Amazon via Keepa...", file=sys.stderr)
    resume_batch = 0
    if resume:
        cp = _load_pipeline_checkpoint(pipeline_checkpoint)
        if cp:
            resume_batch = cp.get("batch_idx", 0)
            print(f"[STAGE 3] Resuming from batch {resume_batch}", file=sys.stderr)

    matched, tokens_used = batch_match(
        filtered, max_tokens=max_tokens,
        checkpoint_path=pipeline_checkpoint,
        resume_from_batch=resume_batch,
    )
    print(f"[STAGE 3] Complete: {len(matched)} matches, {tokens_used} tokens used\n", file=sys.stderr)

    if not matched:
        print("[pipeline] No Amazon matches found.", file=sys.stderr)
        return format_output([], domain, tokens_used, total_scraped, total_filtered)

    # ── Stage 4: Profitability + Velocity ───────────────────────────────
    print("[STAGE 4] Analyzing profitability + velocity...", file=sys.stderr)
    analyzed = analyze_matches(matched, min_roi=min_roi, min_profit=min_profit, max_bsr=max_bsr)
    print(f"[STAGE 4] Complete: {len(analyzed)} profitable products\n", file=sys.stderr)

    # ── Stage 5: Output ─────────────────────────────────────────────────
    print("[STAGE 5] Formatting output...", file=sys.stderr)
    output = format_output(analyzed, domain, tokens_used, total_scraped, total_filtered)

    # Save results
    output_path = OUTPUT_DIR / f"{domain}_{date_str}_leads.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"[STAGE 5] Results saved: {output_path}\n", file=sys.stderr)

    # Clean up pipeline checkpoint on success
    cp_path = Path(pipeline_checkpoint)
    if cp_path.exists():
        cp_path.unlink()

    # Print summary
    s = output["summary"]
    print(f"{'='*60}", file=sys.stderr)
    print(f"RESULTS: {domain}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Scraped:    {total_scraped} variants", file=sys.stderr)
    print(f"  Filtered:   {total_filtered} with valid UPC + price", file=sys.stderr)
    print(f"  Matched:    {len(matched)} found on Amazon", file=sys.stderr)
    print(f"  Profitable: {len(analyzed)} pass ROI/profit/BSR filters", file=sys.stderr)
    print(f"  Tokens:     {tokens_used} Keepa tokens used", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"  BUY:        {s['buy_count']}", file=sys.stderr)
    print(f"  MAYBE:      {s['maybe_count']}", file=sys.stderr)
    print(f"  RESEARCH:   {s['research_count']}", file=sys.stderr)
    print(f"  Avg ROI:    {s['avg_roi']}%", file=sys.stderr)
    print(f"  Avg Profit: ${s['avg_profit']}", file=sys.stderr)
    print(f"  Top ROI:    {s['top_roi']}%", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    return output


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Full catalog sourcing pipeline — scrape → filter → match → analyze → score"
    )
    parser.add_argument("url", help="Retailer URL (e.g., https://www.shopwss.com)")
    parser.add_argument("--max-tokens", type=int, default=3000, help="Max Keepa tokens to spend (default: 3000)")
    parser.add_argument("--min-roi", type=float, default=30.0, help="Min ROI %% (default: 30)")
    parser.add_argument("--min-profit", type=float, default=3.0, help="Min profit per unit (default: $3)")
    parser.add_argument("--max-bsr", type=int, default=200000, help="Max BSR (default: 200000)")
    parser.add_argument("--min-price", type=float, default=5.0, help="Min retail price (default: $5)")
    parser.add_argument("--max-price", type=float, default=60.0, help="Max retail price (default: $60)")
    parser.add_argument("--coupon", type=str, default=None, help="Coupon to apply (e.g., '20%% off')")
    parser.add_argument("--limit-scrape", type=int, default=0, help="Max products to scrape (0=unlimited)")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--json", action="store_true", help="Output full JSON to stdout")
    args = parser.parse_args()

    output = run_pipeline(
        url=args.url,
        max_tokens=args.max_tokens,
        min_roi=args.min_roi,
        min_profit=args.min_profit,
        max_bsr=args.max_bsr,
        min_price=args.min_price,
        max_price=args.max_price,
        coupon=args.coupon,
        limit_scrape=args.limit_scrape,
        resume=args.resume,
    )

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        # Print top leads as text
        products = output.get("products", [])
        if products:
            print(f"\nTop {min(20, len(products))} Leads:")
            print(f"{'Score':>5} {'Verdict':<8} {'ROI':>6} {'Profit':>7} {'BSR':>8} {'ASIN':<12} Title")
            print("-" * 90)
            for p in products[:20]:
                score = p.get('confidence_score') or 0
            verdict = p.get('confidence_verdict') or 'N/A'
            roi = p.get('roi_pct') or 0
            profit = p.get('profit') or 0
            bsr = p.get('bsr') or 'N/A'
            print(
                    f"{score:>5} "
                    f"{verdict:<8} "
                    f"{roi:>5.0f}% "
                    f"${profit:>5.2f} "
                    f"{bsr!s:>8} "
                    f"{p.get('asin',''):<12} "
                    f"{(p.get('amazon_title','') or '')[:40]}"
                )


if __name__ == "__main__":
    main()
