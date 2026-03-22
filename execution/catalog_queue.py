#!/usr/bin/env python3
from __future__ import annotations
"""
Script: catalog_queue.py
Purpose: Queue multiple retailers for overnight batch catalog sourcing.
         Splits token budget proportionally across retailers.
         Supports resume (picks up from last completed retailer).

Usage:
    python execution/catalog_queue.py \
      https://www.shopwss.com \
      https://www.dickssportinggoods.com \
      https://www.bathandbodyworks.com \
      --total-tokens 5000

    python execution/catalog_queue.py --resume  # Continue from last run
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.catalog_scraper import detect_platform
from execution.catalog_pipeline import run_pipeline

QUEUE_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing" / "queue"
RESULTS_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing" / "results"


def run_queue(
    retailers: list[str],
    total_tokens: int = 5000,
    min_roi: float = 15.0,
    min_profit: float = 2.0,
    max_price: float = 0,
    resume: bool = False,
) -> dict:
    """Run catalog sourcing across multiple retailers sequentially.

    Splits token budget proportionally by estimated catalog size.
    """
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    queue_state_path = QUEUE_DIR / f"queue_{date_str}.json"

    # Load or create queue state
    if resume and queue_state_path.exists():
        with open(queue_state_path) as f:
            state = json.load(f)
        retailers = state.get("retailers", retailers)
        completed = set(state.get("completed", []))
        tokens_remaining = state.get("tokens_remaining", total_tokens)
        print(f"[queue] Resuming: {len(completed)} completed, {tokens_remaining} tokens remaining", file=sys.stderr)
    else:
        completed = set()
        tokens_remaining = total_tokens

    # Detect platforms and estimate sizes for pending retailers
    pending = [r for r in retailers if r not in completed]
    if not pending:
        print("[queue] All retailers already completed!", file=sys.stderr)
        return _load_combined_results(retailers, date_str)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"CATALOG QUEUE: {len(pending)} retailers, {tokens_remaining} tokens", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    # Detect platforms to estimate token allocation
    estimates = {}
    for url in pending:
        domain = urlparse(url).netloc.replace("www.", "")
        info = detect_platform(url)
        est = info.get("product_count_estimate", 1000)
        estimates[url] = est
        print(f"  {domain}: ~{est} products ({info['platform']})", file=sys.stderr)

    total_est = sum(estimates.values()) or 1

    # Run each retailer
    all_results = {}
    for url in pending:
        domain = urlparse(url).netloc.replace("www.", "")

        # Allocate tokens proportionally
        share = estimates.get(url, 1000) / total_est
        allocated = max(100, int(tokens_remaining * share))

        print(f"\n{'─'*50}", file=sys.stderr)
        print(f"[queue] Starting: {domain} ({allocated} tokens allocated)", file=sys.stderr)
        print(f"{'─'*50}", file=sys.stderr)

        try:
            output = run_pipeline(
                url=url,
                max_tokens=allocated,
                min_roi=min_roi,
                min_profit=min_profit,
                max_price=max_price,
            )
            all_results[domain] = output

            # Update tokens remaining
            tokens_used = output.get("metadata", {}).get("tokens_used", 0)
            tokens_remaining -= tokens_used

        except Exception as e:
            print(f"[queue] Error on {domain}: {e}", file=sys.stderr)
            all_results[domain] = {"error": str(e)}

        # Save queue state for resume
        completed.add(url)
        state = {
            "retailers": retailers,
            "completed": list(completed),
            "tokens_remaining": tokens_remaining,
            "timestamp": datetime.now().isoformat(),
        }
        with open(queue_state_path, "w") as f:
            json.dump(state, f)

        if tokens_remaining < 50:
            print(f"\n[queue] Token budget exhausted. Resume tomorrow with --resume.", file=sys.stderr)
            break

    # Print combined summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"QUEUE COMPLETE", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    total_products = 0
    total_profitable = 0
    for domain, output in all_results.items():
        if "error" in output:
            print(f"  {domain}: ERROR — {output['error']}", file=sys.stderr)
        else:
            products = output.get("products", [])
            buys = sum(1 for p in products if p.get("confidence_verdict") in ("BUY", "MAYBE"))
            total_products += len(products)
            total_profitable += buys
            print(
                f"  {domain}: {len(products)} leads, {buys} BUY/MAYBE",
                file=sys.stderr,
            )

    print(f"\n  Total: {total_products} leads, {total_profitable} BUY/MAYBE", file=sys.stderr)
    print(f"  Tokens remaining: {tokens_remaining}", file=sys.stderr)

    # Save combined results
    combined_path = RESULTS_DIR / f"queue_{date_str}_combined.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(combined_path, "w") as f:
        json.dump({
            "retailers": {d: r for d, r in all_results.items()},
            "summary": {
                "total_products": total_products,
                "total_profitable": total_profitable,
                "tokens_remaining": tokens_remaining,
                "retailers_completed": len(completed),
            },
            "generated_at": datetime.now().isoformat(),
        }, f, indent=2)
    print(f"\n  Combined results: {combined_path}", file=sys.stderr)

    return all_results


def _load_combined_results(retailers: list[str], date_str: str) -> dict:
    """Load previously saved results for all retailers."""
    results = {}
    for url in retailers:
        domain = urlparse(url).netloc.replace("www.", "")
        path = RESULTS_DIR / f"{domain}_{date_str}_leads.json"
        if path.exists():
            with open(path) as f:
                results[domain] = json.load(f)
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Queue multiple retailers for overnight catalog sourcing"
    )
    parser.add_argument("urls", nargs="*", help="Retailer URLs")
    parser.add_argument("--total-tokens", type=int, default=5000, help="Total Keepa token budget")
    parser.add_argument("--min-roi", type=float, default=30.0)
    parser.add_argument("--min-profit", type=float, default=3.0)
    parser.add_argument("--max-price", type=float, default=60.0)
    parser.add_argument("--resume", action="store_true", help="Resume from last run")
    args = parser.parse_args()

    if not args.urls and not args.resume:
        parser.print_help()
        sys.exit(1)

    run_queue(
        retailers=args.urls,
        total_tokens=args.total_tokens,
        min_roi=args.min_roi,
        min_profit=args.min_profit,
        max_price=args.max_price,
        resume=args.resume,
    )
