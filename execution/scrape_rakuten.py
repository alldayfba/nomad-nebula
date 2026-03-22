#!/usr/bin/env python3
from __future__ import annotations
"""
Script: scrape_rakuten.py
Purpose: Fetch live Rakuten cashback rates per retailer.
         Falls back to hardcoded rates if scrape fails.
         Caches rates for 24 hours.

Usage:
    from scrape_rakuten import get_cashback_rate
    rate = get_cashback_rate("shopwss.com")  # Returns 0.03 for 3%
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

CACHE_PATH = Path(__file__).parent.parent / ".tmp" / "rakuten_rates.json"
CACHE_TTL = 86400  # 24 hours
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Hardcoded fallback rates (from retailer_registry.py + known rates)
FALLBACK_RATES = {
    "walmart.com": 0.03,
    "target.com": 0.01,
    "kohls.com": 0.04,
    "cvs.com": 0.03,
    "walgreens.com": 0.02,
    "macys.com": 0.05,
    "nordstrom.com": 0.03,
    "bestbuy.com": 0.01,
    "homedepot.com": 0.02,
    "lowes.com": 0.02,
    "dickssportinggoods.com": 0.04,
    "ulta.com": 0.04,
    "sephora.com": 0.04,
    "bathandbodyworks.com": 0.04,
    "vitacost.com": 0.05,
    "shopwss.com": 0.0,  # Not on Rakuten
    "costco.com": 0.0,
    "samsclub.com": 0.0,
}


def _load_cache() -> dict:
    """Load cached Rakuten rates."""
    if not CACHE_PATH.exists():
        return {}
    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)
        # Check if cache is still fresh
        if time.time() - data.get("timestamp", 0) < CACHE_TTL:
            return data.get("rates", {})
    except (json.JSONDecodeError, IOError):
        pass
    return {}


def _save_cache(rates: dict):
    """Save rates to cache."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump({"timestamp": time.time(), "rates": rates}, f)


def _scrape_rakuten_rate(domain: str) -> float | None:
    """Try to scrape live cashback rate from Rakuten for a domain."""
    # Rakuten store pages: rakuten.com/{store-slug}
    # The slug is usually the domain without .com
    slug = domain.replace(".com", "").replace(".org", "").replace("www.", "")

    try:
        r = requests.get(
            f"https://www.rakuten.com/{slug}",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
            allow_redirects=True,
        )
        if r.status_code != 200:
            return None

        # Look for cashback rate in page — Rakuten shows "X% Cash Back"
        # Pattern: "Up to X% Cash Back" or "X% Cash Back"
        patterns = [
            r'(\d+(?:\.\d+)?)\s*%\s*Cash\s*Back',
            r'cashback.*?(\d+(?:\.\d+)?)\s*%',
            r'"cashbackPercent"\s*:\s*(\d+(?:\.\d+)?)',
            r'"rebate"\s*:\s*(\d+(?:\.\d+)?)',
        ]
        for pattern in patterns:
            m = re.search(pattern, r.text, re.IGNORECASE)
            if m:
                return float(m.group(1)) / 100.0

    except Exception:
        pass

    return None


def get_cashback_rate(domain: str) -> float:
    """Get Rakuten cashback rate for a retailer domain.

    Args:
        domain: Retailer domain (e.g., "shopwss.com", "kohls.com")

    Returns:
        Cashback rate as decimal (e.g., 0.04 for 4%). Returns 0.0 if unknown.
    """
    domain = domain.lower().replace("www.", "")

    # Check cache first
    cache = _load_cache()
    if domain in cache:
        return cache[domain]

    # Try live scrape
    rate = _scrape_rakuten_rate(domain)

    if rate is not None:
        # Save to cache
        cache[domain] = rate
        _save_cache(cache)
        return rate

    # Fallback to hardcoded
    rate = FALLBACK_RATES.get(domain, 0.0)
    cache[domain] = rate
    _save_cache(cache)
    return rate


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("domain", help="Retailer domain (e.g., kohls.com)")
    args = parser.parse_args()
    rate = get_cashback_rate(args.domain)
    print(f"{args.domain}: {rate*100:.1f}% cashback")
