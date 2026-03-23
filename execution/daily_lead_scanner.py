#!/usr/bin/env python3
from __future__ import annotations
"""
Script: daily_lead_scanner.py
Purpose: Automated daily lead generation — scans clearance stores + pushes
         BUY/MAYBE deals to Discord.

         Designed to run as a cron/launchd job. Produces a daily "Deal Drop"
         with the best OA leads found across all clearance stores.

Usage:
    python execution/daily_lead_scanner.py                    # Scan Tier 1 stores
    python execution/daily_lead_scanner.py --tier 2 --top 20  # Scan 20 Tier 2 stores
    python execution/daily_lead_scanner.py --dry-run           # Preview without Discord
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import requests as http_requests

from execution.clearance_scanner import scan_top_clearance, get_clearance_stores

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_SOURCING_WEBHOOK", "") or os.environ.get("DISCORD_WEBHOOK_URL", "")
OUTPUT_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing" / "daily"


def send_discord_deal_alert(products: list[dict], scan_date: str) -> bool:
    """Send top deals to Discord as an embed."""
    if not DISCORD_WEBHOOK_URL:
        print("[daily] No Discord webhook configured — skipping alert", file=sys.stderr)
        return False

    buy_products = [p for p in products if p.get("confidence_verdict") == "BUY"]
    maybe_products = [p for p in products if p.get("confidence_verdict") == "MAYBE"]
    top_deals = (buy_products + maybe_products)[:20]

    if not top_deals:
        print("[daily] No BUY/MAYBE deals to alert", file=sys.stderr)
        return False

    # Build embed
    lines = []
    for i, p in enumerate(top_deals[:15], 1):
        verdict = p.get("confidence_verdict", "?")
        emoji = {"BUY": "\u2705", "MAYBE": "\U0001f7e1"}.get(verdict, "\u26aa")
        title = (p.get("retailer_title") or p.get("amazon_title", "Unknown"))[:35]
        profit = p.get("profit", 0)
        roi = p.get("roi_pct", 0)
        asin = p.get("asin", "")
        buy_link = p.get("retailer_url", "")
        lines.append(
            f"{emoji} **{title}** | ${profit:.0f} profit | {roi:.0f}% ROI\n"
            f"   [Amazon](https://amazon.com/dp/{asin}) | [Buy]({buy_link})"
        )

    description = "\n".join(lines)
    if len(description) > 4000:
        description = description[:3990] + "\n..."

    embed = {
        "title": f"\U0001f4b0 Daily Deal Drop — {scan_date}",
        "description": description,
        "color": 0x00FF00 if buy_products else 0xFFFF00,
        "footer": {
            "text": f"{len(buy_products)} BUY | {len(maybe_products)} MAYBE | {len(products)} total leads"
        },
    }

    try:
        resp = http_requests.post(
            DISCORD_WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=10,
        )
        if resp.status_code in (200, 204):
            print(f"[daily] Discord alert sent ({len(top_deals)} deals)", file=sys.stderr)
            return True
        else:
            print(f"[daily] Discord error: {resp.status_code}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[daily] Discord send failed: {e}", file=sys.stderr)
        return False


def run_daily_scan(
    tier: int = 1,
    top_n: int = 10,
    total_tokens: int = 3000,
    min_roi: float = 20.0,
    min_profit: float = 3.0,
    dry_run: bool = False,
) -> dict:
    """Run the daily automated lead scan.

    1. Scan top clearance stores
    2. Compile results
    3. Push BUY/MAYBE to Discord
    4. Save daily report
    """
    scan_date = datetime.now().strftime("%Y-%m-%d")
    print(f"\n[daily] Daily Lead Scanner — {scan_date}", file=sys.stderr)
    print(f"[daily] Tier {tier}, top {top_n} stores, {total_tokens} tokens", file=sys.stderr)

    # Run clearance scan
    results = scan_top_clearance(
        n=top_n,
        total_tokens=total_tokens,
        min_roi=min_roi,
        min_profit=min_profit,
        tier=tier,
    )

    products = results.get("products", [])

    # Save daily report
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"daily_leads_{scan_date}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[daily] Report saved: {report_path}", file=sys.stderr)

    # Discord alert
    if not dry_run and products:
        send_discord_deal_alert(products, scan_date)
    elif dry_run:
        buy = sum(1 for p in products if p.get("confidence_verdict") == "BUY")
        maybe = sum(1 for p in products if p.get("confidence_verdict") == "MAYBE")
        print(f"[daily] DRY RUN — would send {buy} BUY + {maybe} MAYBE deals to Discord", file=sys.stderr)

    return results


def main():
    parser = argparse.ArgumentParser(description="Automated daily OA lead scanner")
    parser.add_argument("--tier", type=int, default=1, help="Store tier to scan (default: 1)")
    parser.add_argument("--top", type=int, default=10, help="Number of stores (default: 10)")
    parser.add_argument("--total-tokens", type=int, default=3000, help="Keepa token budget (default: 3000)")
    parser.add_argument("--min-roi", type=float, default=20.0, help="Min ROI %% (default: 20)")
    parser.add_argument("--min-profit", type=float, default=3.0, help="Min profit (default: $3)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending Discord")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    args = parser.parse_args()

    results = run_daily_scan(
        tier=args.tier,
        top_n=args.top,
        total_tokens=args.total_tokens,
        min_roi=args.min_roi,
        min_profit=args.min_profit,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
