#!/usr/bin/env python3
from __future__ import annotations
"""
Script: catalog_price_monitor.py
Purpose: Re-check prices on profitable catalog leads daily.
         Alerts on price drops (ROI improvements) and OOS changes.
         Designed to run as a cron job.

Usage:
    python execution/catalog_price_monitor.py --results .tmp/sourcing/results/shopwss.com_20260322_leads.json
    python execution/catalog_price_monitor.py --all  # Check all saved leads
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS_DIR = Path(__file__).parent.parent / ".tmp" / "sourcing" / "results"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OOS_SIGNALS = [
    "out of stock", "sold out", "unavailable", "not available",
    "coming soon", "notify me", "currently unavailable",
]


def check_retailer_price(url: str) -> dict:
    """Check current price and availability at a retailer URL.

    Returns dict with: available (bool), current_price (float|None), error (str|None)
    """
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if r.status_code != 200:
            return {"available": False, "current_price": None, "error": f"HTTP {r.status_code}"}

        html_lower = r.text.lower()

        # Check for OOS signals
        for signal in OOS_SIGNALS:
            if signal in html_lower:
                return {"available": False, "current_price": None, "error": "out_of_stock"}

        # Try to extract price from JSON-LD
        price = _extract_price_jsonld(r.text)
        if not price:
            price = _extract_price_meta(r.text)
        if not price:
            price = _extract_price_shopify(r.text, url)

        return {"available": True, "current_price": price, "error": None}

    except requests.RequestException as e:
        return {"available": False, "current_price": None, "error": str(e)}


def _extract_price_jsonld(html: str) -> float | None:
    """Extract price from JSON-LD Product schema."""
    pattern = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "Product"), None)
            if not data or data.get("@type") != "Product":
                continue
            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price_str = offers.get("price", "")
            return float(price_str) if price_str else None
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return None


def _extract_price_meta(html: str) -> float | None:
    """Extract price from meta tags."""
    m = re.search(
        r'<meta[^>]*property=["\']product:price:amount["\'][^>]*content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _extract_price_shopify(html: str, url: str) -> float | None:
    """For Shopify stores, try the .json endpoint."""
    if "/products/" not in url:
        return None
    try:
        r = requests.get(url.rstrip("/") + ".json",
                         headers={"User-Agent": USER_AGENT}, timeout=10)
        if r.status_code == 200:
            product = r.json().get("product", {})
            variants = product.get("variants", [])
            if variants:
                return float(variants[0].get("price", 0))
    except Exception:
        pass
    return None


def monitor_leads(results_path: str) -> dict:
    """Re-check all leads in a results file. Returns updated results + alerts."""
    with open(results_path) as f:
        data = json.load(f)

    products = data.get("products", [])
    alerts = []
    updated = []
    checked = 0
    oos_count = 0
    price_drop_count = 0

    print(f"[monitor] Checking {len(products)} leads...", file=sys.stderr)

    for p in products:
        retailer_url = p.get("retailer_url", "")
        if not retailer_url:
            updated.append(p)
            continue

        check = check_retailer_price(retailer_url)
        checked += 1

        p["link_verified"] = check["available"]
        p["link_check_time"] = datetime.now().isoformat()

        if not check["available"]:
            oos_count += 1
            p["monitor_status"] = "oos"
            alerts.append({
                "type": "oos",
                "asin": p.get("asin", ""),
                "title": p.get("amazon_title", "")[:50],
                "url": retailer_url,
                "reason": check.get("error", "unavailable"),
            })
        elif check["current_price"] and p.get("retail_price"):
            old_price = p["retail_price"]
            new_price = check["current_price"]
            if new_price < old_price * 0.95:  # 5%+ drop
                pct_drop = round((1 - new_price / old_price) * 100, 1)
                p["monitor_status"] = "price_drop"
                p["_new_retail_price"] = new_price
                p["_price_drop_pct"] = pct_drop
                price_drop_count += 1

                # Recalc ROI with new price
                amazon_price = p.get("amazon_price", 0)
                if amazon_price > 0:
                    new_profit = amazon_price - new_price - (amazon_price * 0.15) - 5.0
                    new_roi = (new_profit / new_price * 100) if new_price > 0 else 0
                    p["_new_roi"] = round(new_roi, 1)
                    p["_new_profit"] = round(new_profit, 2)

                alerts.append({
                    "type": "price_drop",
                    "asin": p.get("asin", ""),
                    "title": p.get("amazon_title", "")[:50],
                    "old_price": old_price,
                    "new_price": new_price,
                    "drop_pct": pct_drop,
                    "new_roi": p.get("_new_roi"),
                })
            else:
                p["monitor_status"] = "stable"
        else:
            p["monitor_status"] = "checked"

        updated.append(p)
        time.sleep(1)  # Rate limit

        if checked % 10 == 0:
            print(f"[monitor] Checked {checked}/{len(products)}", file=sys.stderr)

    print(
        f"[monitor] Done: {checked} checked, {price_drop_count} price drops, "
        f"{oos_count} OOS",
        file=sys.stderr,
    )

    return {
        "products": updated,
        "alerts": alerts,
        "summary": {
            "checked": checked,
            "price_drops": price_drop_count,
            "oos": oos_count,
            "stable": checked - price_drop_count - oos_count,
        },
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=False, help="Path to leads JSON")
    parser.add_argument("--all", action="store_true", help="Check all saved leads")
    args = parser.parse_args()

    paths = []
    if args.all:
        paths = list(RESULTS_DIR.glob("*_leads.json"))
    elif args.results:
        paths = [Path(args.results)]
    else:
        parser.print_help()
        sys.exit(1)

    for path in paths:
        print(f"\n{'='*50}", file=sys.stderr)
        print(f"Monitoring: {path.name}", file=sys.stderr)
        result = monitor_leads(str(path))
        for alert in result["alerts"]:
            if alert["type"] == "price_drop":
                print(f"  ↓ PRICE DROP: {alert['title']} — ${alert['old_price']:.2f} → ${alert['new_price']:.2f} ({alert['drop_pct']}% off)")
            elif alert["type"] == "oos":
                print(f"  ✗ OOS: {alert['title']} — {alert['reason']}")
