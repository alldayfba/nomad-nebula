"""
Find Instagram profiles for leads via Google search.
Checks if lead has a real website (vs brokerage/third-party).
Outputs enriched CSV with instagram_url and has_real_website columns.
"""
from __future__ import annotations
import csv
import sys
import time
import re
import json
from pathlib import Path
from urllib.parse import urlparse, quote_plus

# Try playwright for Google search
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Brokerage / third-party domains that don't count as "their own website"
NOT_OWN_SITE = {
    'zillow.com', 'realtor.com', 'redfin.com', 'homes.com', 'trulia.com',
    'coldwellbanker.com', 'century21.com', 'kw.com', 'remax.com',
    'sothebysrealty.com', 'compass.com', 'berkshirehathaway.com', 'bhhs.com',
    'facebook.com', 'instagram.com', 'linkedin.com', 'yelp.com', 'twitter.com',
    'exprealty.com', 'elliman.com', 'weichert.com', 'era.com',
    'homelight.com', 'movoto.com', 'homesnap.com', 'har.com',
    'longandfoster.com', 'howardhanna.com', 'cbr.com', 'linktr.ee',
    'yellowpages.com', 'bbb.org', 'nextdoor.com', 'google.com',
}

def has_real_website(url: str) -> bool:
    """Check if URL is the agent's own website vs a third-party listing."""
    if not url or url.strip() in ('', 'N/A'):
        return False
    try:
        domain = urlparse(url).netloc.replace('www.', '').lower()
        return not any(nope in domain for nope in NOT_OWN_SITE)
    except Exception:
        return False

def find_ig_via_playwright(leads: list[dict], max_leads: int = 500) -> list[dict]:
    """Use Playwright to Google search for Instagram profiles."""
    print(f"[ig-finder] Searching Instagram for {min(len(leads), max_leads)} leads via Playwright...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        for i, lead in enumerate(leads[:max_leads]):
            if lead.get('instagram_url'):
                continue  # Already found

            name = lead.get('business_name', '').strip()
            city = lead.get('source_city', '').strip()

            query = f'{name} {city} instagram.com'
            search_url = f'https://www.google.com/search?q={quote_plus(query)}'

            try:
                page.goto(search_url, timeout=10000)
                time.sleep(1.5)  # Be respectful

                # Look for instagram.com links in results
                content = page.content()

                # Find instagram URLs in the page
                ig_patterns = re.findall(r'https?://(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)', content)

                # Filter out generic IG pages
                skip_handles = {'explore', 'accounts', 'p', 'reel', 'stories', 'about', 'legal', 'privacy', 'terms', 'help', 'developer'}
                ig_handles = [h for h in ig_patterns if h.lower() not in skip_handles and len(h) > 2]

                if ig_handles:
                    # Take the first unique handle (most likely match)
                    handle = ig_handles[0]
                    lead['instagram_url'] = f'https://instagram.com/{handle}'
                    lead['ig_handle'] = f'@{handle}'
                    print(f"  [{i+1}/{min(len(leads), max_leads)}] {name} → @{handle}")
                else:
                    lead['instagram_url'] = ''
                    lead['ig_handle'] = ''
                    print(f"  [{i+1}/{min(len(leads), max_leads)}] {name} → no IG found")

            except Exception as e:
                lead['instagram_url'] = ''
                lead['ig_handle'] = ''
                print(f"  [{i+1}/{min(len(leads), max_leads)}] {name} → error: {e}")

            # Rate limit
            if (i + 1) % 10 == 0:
                print(f"  ... {i+1} searched, pausing 3s")
                time.sleep(3)

        browser.close()

    return leads

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Find Instagram profiles for leads')
    parser.add_argument('--input', required=True, help='Input CSV file')
    parser.add_argument('--output', required=True, help='Output CSV file')
    parser.add_argument('--max', type=int, default=500, help='Max leads to search')
    parser.add_argument('--no-website-only', action='store_true', help='Only search leads without real websites')
    args = parser.parse_args()

    # Read leads
    leads = []
    with open(args.input, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            row['has_real_website'] = 'yes' if has_real_website(row.get('website', '')) else 'no'
            leads.append(row)

    total = len(leads)
    no_site = sum(1 for l in leads if l['has_real_website'] == 'no')
    print(f"[ig-finder] Loaded {total} leads. {no_site} have no real website.")

    # Filter if requested
    search_leads = leads
    if args.no_website_only:
        search_leads = [l for l in leads if l['has_real_website'] == 'no']
        print(f"[ig-finder] Searching only no-website leads: {len(search_leads)}")

    # Find Instagram
    if HAS_PLAYWRIGHT and search_leads:
        search_leads = find_ig_via_playwright(search_leads, max_leads=args.max)
    elif not HAS_PLAYWRIGHT:
        print("[ig-finder] WARNING: Playwright not available. Install with: pip install playwright && playwright install chromium")

    # Merge IG data back to full list if filtered
    if args.no_website_only:
        ig_map = {}
        for l in search_leads:
            key = l.get('phone', '') + l.get('business_name', '')
            ig_map[key] = (l.get('instagram_url', ''), l.get('ig_handle', ''))
        for l in leads:
            key = l.get('phone', '') + l.get('business_name', '')
            if key in ig_map:
                l['instagram_url'], l['ig_handle'] = ig_map[key]
            else:
                l.setdefault('instagram_url', '')
                l.setdefault('ig_handle', '')

    # Write output
    fieldnames = ['business_name', 'owner_name', 'phone', 'website', 'has_real_website',
                  'instagram_url', 'ig_handle', 'address', 'rating', 'maps_url', 'source_city']

    with open(args.output, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(leads)

    # Stats
    with_ig = sum(1 for l in leads if l.get('instagram_url'))
    no_site_with_ig = sum(1 for l in leads if l['has_real_website'] == 'no' and l.get('instagram_url'))

    print(f"\n[ig-finder] Results:")
    print(f"  Total leads: {total}")
    print(f"  No real website: {no_site}")
    print(f"  Has Instagram: {with_ig}")
    print(f"  No website + has IG (YOUR TARGET): {no_site_with_ig}")
    print(f"  Output: {args.output}")

if __name__ == '__main__':
    main()
