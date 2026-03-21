#!/usr/bin/env python3
"""
Script: selector_health_check.py
Purpose: Verify that retailer CSS selectors still work by hitting each
         retailer's search page with a known product and checking if
         selectors find results. Run weekly via ABS to catch broken
         selectors before they cause silent scan failures.

Usage:
  python execution/selector_health_check.py
  python execution/selector_health_check.py --retailers target,walgreens
  python execution/selector_health_check.py --max 20 --timeout 15

Output: JSON report at .tmp/sourcing/selector_health_{date}.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "sourcing"

# Known products that should exist at most retailers
TEST_QUERIES = ["colgate toothpaste", "tide pods", "advil"]


def check_retailer(retailer, playwright_page, timeout=10):
    """Check if a retailer's selectors find results for a test query.

    Returns dict with status, selector results, and timing.
    """
    from retailer_registry import get_retailer, get_search_url

    config = get_retailer(retailer)
    if not config:
        return {"retailer": retailer, "status": "unknown", "error": "Not in registry"}

    search_url = get_search_url(config, TEST_QUERIES[0])
    if not search_url:
        return {"retailer": retailer, "status": "no_search_url",
                "error": "No search URL configured"}

    # Default selectors to check
    card_selectors = config.get("card_selectors", [
        'a[href*="/p"]', '.product-card', '.product-item',
        '[data-test="product-card"]', '.productCard',
    ])
    name_selectors = config.get("name_selectors", [
        'h3', '.product-title', '.product-name', '[data-test="product-title"]',
    ])
    price_selectors = config.get("price_selectors", [
        '[data-test="current-price"]', '.price', '.product-price',
        'span[class*="price"]', '.sale-price',
    ])

    result = {
        "retailer": retailer,
        "name": config.get("name", retailer),
        "search_url": search_url,
        "status": "unknown",
        "cards_found": 0,
        "names_found": 0,
        "prices_found": 0,
        "working_card_selector": None,
        "working_name_selector": None,
        "working_price_selector": None,
        "load_time_ms": 0,
        "error": None,
    }

    try:
        start = time.time()
        playwright_page.goto(search_url, timeout=timeout * 1000, wait_until="domcontentloaded")
        # Wait a bit for JS rendering
        playwright_page.wait_for_timeout(2000)
        result["load_time_ms"] = int((time.time() - start) * 1000)

        # Check for CAPTCHA/block
        content = playwright_page.content()
        from proxy_manager import detect_captcha
        if detect_captcha(content):
            result["status"] = "blocked"
            result["error"] = "CAPTCHA or bot block detected"
            return result

        # Test card selectors
        for sel in card_selectors:
            try:
                count = playwright_page.locator(sel).count()
                if count > 0:
                    result["cards_found"] = count
                    result["working_card_selector"] = sel
                    break
            except Exception:
                continue

        # Test name selectors
        for sel in name_selectors:
            try:
                count = playwright_page.locator(sel).count()
                if count > 0:
                    result["names_found"] = count
                    result["working_name_selector"] = sel
                    break
            except Exception:
                continue

        # Test price selectors
        for sel in price_selectors:
            try:
                count = playwright_page.locator(sel).count()
                if count > 0:
                    result["prices_found"] = count
                    result["working_price_selector"] = sel
                    break
            except Exception:
                continue

        # Determine status
        if result["cards_found"] > 0 and result["prices_found"] > 0:
            result["status"] = "healthy"
        elif result["cards_found"] > 0:
            result["status"] = "partial"
            result["error"] = "Cards found but no prices — price selector may be stale"
        else:
            result["status"] = "broken"
            result["error"] = "No product cards found — selectors likely outdated"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    return result


def run_health_check(retailers=None, max_retailers=20, timeout=15):
    """Run selector health check across retailers.

    Args:
        retailers: List of retailer keys, or None for top retailers.
        max_retailers: Max retailers to check if no list provided.
        timeout: Page load timeout in seconds.

    Returns:
        List of result dicts.
    """
    from retailer_registry import get_retailers_for_product

    if not retailers:
        all_retailers = get_retailers_for_product("General", max_retailers=max_retailers)
        retailers = [r["key"] for r in all_retailers]

    results = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"
            )

            for i, retailer_key in enumerate(retailers):
                print(f"  [{i+1}/{len(retailers)}] Checking {retailer_key}...",
                      file=sys.stderr, end=" ")
                result = check_retailer(retailer_key, page, timeout=timeout)
                results.append(result)

                status_icon = {
                    "healthy": "OK", "partial": "WARN",
                    "broken": "FAIL", "blocked": "BLOCK",
                    "error": "ERR", "unknown": "?",
                    "no_search_url": "SKIP",
                }.get(result["status"], "?")

                print(f"{status_icon} ({result['cards_found']} cards, "
                      f"{result['load_time_ms']}ms)", file=sys.stderr)

                time.sleep(2)  # Be polite

            browser.close()

    except ImportError:
        print("[health] Playwright not installed", file=sys.stderr)
    except Exception as e:
        print(f"[health] Browser error: {e}", file=sys.stderr)

    return results


def main():
    parser = argparse.ArgumentParser(description="CSS selector health check for retailers")
    parser.add_argument("--retailers", "-r", default=None,
                        help="Comma-separated retailer keys (default: top retailers)")
    parser.add_argument("--max", type=int, default=20,
                        help="Max retailers to check (default: 20)")
    parser.add_argument("--timeout", type=int, default=15,
                        help="Page load timeout in seconds (default: 15)")
    args = parser.parse_args()

    retailers = [r.strip() for r in args.retailers.split(",")] if args.retailers else None

    print(f"\n  Retailer Selector Health Check", file=sys.stderr)
    print(f"  {'=' * 40}", file=sys.stderr)

    results = run_health_check(retailers=retailers, max_retailers=args.max,
                               timeout=args.timeout)

    # Summary
    healthy = sum(1 for r in results if r["status"] == "healthy")
    partial = sum(1 for r in results if r["status"] == "partial")
    broken = sum(1 for r in results if r["status"] == "broken")
    blocked = sum(1 for r in results if r["status"] == "blocked")
    errors = sum(1 for r in results if r["status"] == "error")

    print(f"\n  Summary:", file=sys.stderr)
    print(f"    Healthy:  {healthy}/{len(results)}", file=sys.stderr)
    print(f"    Partial:  {partial}", file=sys.stderr)
    print(f"    Broken:   {broken}", file=sys.stderr)
    print(f"    Blocked:  {blocked}", file=sys.stderr)
    print(f"    Errors:   {errors}", file=sys.stderr)

    # Save report
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    report_path = TMP_DIR / f"selector_health_{datetime.now().strftime('%Y%m%d')}.json"
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total": len(results), "healthy": healthy, "partial": partial,
            "broken": broken, "blocked": blocked, "errors": errors,
        },
        "results": results,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report: {report_path}", file=sys.stderr)

    # Print broken/partial for quick visibility
    issues = [r for r in results if r["status"] in ("broken", "partial")]
    if issues:
        print(f"\n  Issues to fix:", file=sys.stderr)
        for r in issues:
            print(f"    {r['status'].upper()}: {r['retailer']} — {r.get('error', '')}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
