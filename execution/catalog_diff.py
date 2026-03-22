#!/usr/bin/env python3
from __future__ import annotations
"""
Script: catalog_diff.py
Purpose: Compare two catalog snapshots to find new products, price drops,
         and products that went out of stock. Highlights fresh arbitrage
         opportunities that nobody else has found yet.

Usage:
    from catalog_diff import diff_catalogs
    diff = diff_catalogs("old_catalog.json", "new_catalog.json")
    # diff = {"new": [...], "removed": [...], "price_drops": [...], "price_increases": [...]}
"""

import json
import sys
from pathlib import Path


def diff_catalogs(old_path: str, new_path: str) -> dict:
    """Compare two catalog JSON files by UPC.

    Returns:
        dict with new_products, removed_products, price_drops, price_increases, unchanged
    """
    old_products = _load_catalog(old_path)
    new_products = _load_catalog(new_path)

    old_by_upc = {p["upc"]: p for p in old_products if p.get("upc")}
    new_by_upc = {p["upc"]: p for p in new_products if p.get("upc")}

    old_upcs = set(old_by_upc.keys())
    new_upcs = set(new_by_upc.keys())

    # New products (in new but not old)
    new_only = []
    for upc in (new_upcs - old_upcs):
        p = new_by_upc[upc]
        p["_diff_status"] = "new"
        new_only.append(p)

    # Removed products (in old but not new — went OOS or delisted)
    removed = []
    for upc in (old_upcs - new_upcs):
        p = old_by_upc[upc]
        p["_diff_status"] = "removed"
        removed.append(p)

    # Price changes (in both)
    price_drops = []
    price_increases = []
    unchanged = 0

    for upc in (old_upcs & new_upcs):
        old_price = old_by_upc[upc].get("price", 0)
        new_price = new_by_upc[upc].get("price", 0)

        if old_price <= 0 or new_price <= 0:
            unchanged += 1
            continue

        pct_change = ((new_price - old_price) / old_price) * 100

        if pct_change < -2:  # Price dropped by more than 2%
            p = new_by_upc[upc]
            p["_diff_status"] = "price_drop"
            p["_old_price"] = old_price
            p["_price_drop_pct"] = round(abs(pct_change), 1)
            price_drops.append(p)
        elif pct_change > 2:  # Price increased
            p = new_by_upc[upc]
            p["_diff_status"] = "price_increase"
            p["_old_price"] = old_price
            p["_price_increase_pct"] = round(pct_change, 1)
            price_increases.append(p)
        else:
            unchanged += 1

    # Sort price drops by magnitude (biggest drop first)
    price_drops.sort(key=lambda p: p.get("_price_drop_pct", 0), reverse=True)

    return {
        "new_products": new_only,
        "removed_products": removed,
        "price_drops": price_drops,
        "price_increases": price_increases,
        "unchanged_count": unchanged,
        "summary": {
            "old_count": len(old_by_upc),
            "new_count": len(new_by_upc),
            "added": len(new_only),
            "removed": len(removed),
            "price_drops": len(price_drops),
            "price_increases": len(price_increases),
            "unchanged": unchanged,
            "avg_drop_pct": round(
                sum(p.get("_price_drop_pct", 0) for p in price_drops) / max(len(price_drops), 1), 1
            ),
        },
    }


def _load_catalog(path: str) -> list[dict]:
    """Load a catalog JSON file."""
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, FileNotFoundError):
        return []


def find_previous_catalog(domain: str, current_path: str) -> str | None:
    """Find the most recent previous catalog for a domain (excluding current)."""
    catalog_dir = Path(current_path).parent
    current_name = Path(current_path).name

    candidates = []
    for f in catalog_dir.glob(f"{domain}_*.json"):
        if f.name != current_name and "_checkpoint" not in f.name:
            candidates.append(f)

    if not candidates:
        return None

    # Return most recent by modification time
    candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return str(candidates[0])


def print_diff_summary(diff: dict):
    """Print a human-readable diff summary."""
    s = diff["summary"]
    print(f"  Catalog Diff: {s['old_count']} → {s['new_count']} products", file=sys.stderr)
    if s["added"]:
        print(f"    + {s['added']} NEW products added", file=sys.stderr)
    if s["removed"]:
        print(f"    - {s['removed']} products removed/OOS", file=sys.stderr)
    if s["price_drops"]:
        print(f"    ↓ {s['price_drops']} price drops (avg -{s['avg_drop_pct']}%)", file=sys.stderr)
    if s["price_increases"]:
        print(f"    ↑ {s['price_increases']} price increases", file=sys.stderr)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("old", help="Path to old catalog JSON")
    parser.add_argument("new", help="Path to new catalog JSON")
    args = parser.parse_args()

    diff = diff_catalogs(args.old, args.new)
    print_diff_summary(diff)
    print(json.dumps(diff["summary"], indent=2))
