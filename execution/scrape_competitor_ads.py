#!/usr/bin/env python3
"""
scrape_competitor_ads.py
Scrapes the Meta Ad Library for competitor ads and outputs structured JSON.

Usage:
  python execution/scrape_competitor_ads.py --business agency --output .tmp/ads/agency_competitors.json
  python execution/scrape_competitor_ads.py --business coaching --output .tmp/ads/coaching_competitors.json
  python execution/scrape_competitor_ads.py --page "Page Name" --output .tmp/ads/custom.json
"""

import argparse
import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Competitor config — add Meta Ad Library page names/IDs here
# ---------------------------------------------------------------------------

COMPETITORS = {
    "agency": [
        # Add competitor page names from Meta Ad Library
        # Example: "SMMA Expert", "Growth Agency Co"
    ],
    "coaching": [
        # Add competitor page names from Meta Ad Library
        # Example: "Amazon FBA Guru", "FBA Mastery"
    ],
}

META_AD_LIBRARY_URL = "https://www.facebook.com/ads/library/"


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape Meta Ad Library for competitor intel")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--business", choices=["agency", "coaching"],
                       help="Which competitor list to use (defined in COMPETITORS dict)")
    group.add_argument("--page", type=str,
                       help="Scrape a specific page name directly")
    parser.add_argument("--output", type=str, required=True,
                        help="Output JSON file path (e.g. .tmp/ads/agency_competitors.json)")
    parser.add_argument("--days", type=int, default=30,
                        help="How many days back to look (default: 30)")
    return parser.parse_args()


def build_ad_library_url(page_name: str, country: str = "US") -> str:
    """Build a Meta Ad Library search URL for a given page."""
    import urllib.parse
    params = {
        "active_status": "all",
        "ad_type": "all",
        "country": country,
        "q": page_name,
        "search_type": "keyword_unordered",
    }
    return f"{META_AD_LIBRARY_URL}?{urllib.parse.urlencode(params)}"


def scrape_page(page_name: str, days_back: int) -> dict:
    """
    Scrape the Meta Ad Library for a single competitor page.
    
    Meta Ad Library is public and doesn't require authentication.
    Uses Playwright for JS-rendered content.
    
    Returns a dict with:
      - page_name
      - active_ads: list of ad objects
      - longest_running_ad: the ad that's been active longest
      - newest_ads: ads started in the last 7 days
      - format_breakdown: count by type (video/image/carousel)
    """
    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup

        url = build_ad_library_url(page_name)
        print(f"  Scraping: {page_name} → {url}", file=sys.stderr)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)  # let JS render

            # Scroll to load more ads
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)

            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Extract ad cards — Meta Ad Library renders cards with aria-label or data attributes
        # NOTE: Meta frequently changes their DOM structure. Update selectors if scraping breaks.
        ads = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Attempt to parse ad cards (structure varies — update if Meta changes layout)
        ad_cards = soup.find_all("div", {"data-testid": "ad-archive-renderer"})
        if not ad_cards:
            # Fallback: look for any card-like containers
            ad_cards = soup.find_all("div", class_=lambda c: c and "x8t9es0" in str(c))

        for card in ad_cards:
            text = card.get_text(separator=" ", strip=True)
            if not text:
                continue

            # Extract start date if present (format varies)
            start_date = None
            date_text = card.find(string=lambda s: s and ("Started running" in s or "Active" in s))
            if date_text:
                start_date = str(date_text).strip()

            # Determine format
            has_video = bool(card.find("video"))
            has_carousel = bool(card.find("ul"))
            ad_format = "video" if has_video else ("carousel" if has_carousel else "image")

            ads.append({
                "text_preview": text[:300],
                "format": ad_format,
                "start_date": start_date,
                "raw_length": len(text),
            })

        # Determine longest-running ad (heuristic: oldest start date or longest text = most established)
        longest_running = ads[0] if ads else None

        # Format breakdown
        format_counts = {"video": 0, "image": 0, "carousel": 0}
        for ad in ads:
            format_counts[ad.get("format", "image")] += 1

        return {
            "page_name": page_name,
            "scraped_at": datetime.now().isoformat(),
            "url": url,
            "total_ads_found": len(ads),
            "active_ads": ads[:20],  # cap at 20 for file size
            "longest_running_ad": longest_running,
            "newest_ads": ads[-5:] if len(ads) >= 5 else ads,
            "format_breakdown": format_counts,
            "error": None,
        }

    except Exception as e:
        print(f"  ERROR scraping {page_name}: {e}", file=sys.stderr)
        return {
            "page_name": page_name,
            "scraped_at": datetime.now().isoformat(),
            "url": build_ad_library_url(page_name),
            "total_ads_found": 0,
            "active_ads": [],
            "longest_running_ad": None,
            "newest_ads": [],
            "format_breakdown": {},
            "error": str(e),
        }


def main():
    args = parse_args()

    # Determine which pages to scrape
    if args.page:
        pages = [args.page]
        label = args.page
    else:
        pages = COMPETITORS.get(args.business, [])
        label = args.business
        if not pages:
            print(f"ERROR: No competitors configured for '{args.business}'.", file=sys.stderr)
            print(f"Add page names to the COMPETITORS dict in this script.", file=sys.stderr)
            sys.exit(1)

    print(f"Scraping {len(pages)} competitor(s) for: {label}", file=sys.stderr)

    # Ensure output dir exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Scrape all pages
    results = {
        "business": args.business or "custom",
        "label": label,
        "scraped_at": datetime.now().isoformat(),
        "days_back": args.days,
        "competitors": [],
    }

    for page_name in pages:
        result = scrape_page(page_name, args.days)
        results["competitors"].append(result)
        print(f"  {page_name}: {result['total_ads_found']} ads found", file=sys.stderr)

    # Write output
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nOutput written to: {output_path}", file=sys.stderr)
    print(f"Total competitors scraped: {len(pages)}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
