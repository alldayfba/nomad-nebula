#!/usr/bin/env python3
"""
scrape_client_profile.py
Scrapes a client's public web presence (website + Instagram + YouTube) and
outputs a structured JSON file to .tmp/clients/[slug]-raw.json.

Usage:
  python execution/scrape_client_profile.py \
    --name "joe-smith" \
    --website "https://example.com" \
    --instagram "joesmith" \
    --youtube "https://youtube.com/@joesmith"
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
    import requests
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}", file=sys.stderr)
    print("Run: pip install playwright beautifulsoup4 requests", file=sys.stderr)
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape client public presence for brand voice file")
    parser.add_argument("--name", required=True,
                        help="Client slug for filenames (e.g. 'joe-smith', lowercase-hyphenated)")
    parser.add_argument("--website", default=None, help="Client website URL")
    parser.add_argument("--instagram", default=None, help="Instagram handle (without @)")
    parser.add_argument("--youtube", default=None, help="YouTube channel URL")
    return parser.parse_args()


def scrape_website(url: str) -> dict:
    """Scrape homepage text, headlines, CTA text, and overall positioning language."""
    print(f"  Scraping website: {url}", file=sys.stderr)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Remove script/style noise
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        headlines = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)]
        body_text = soup.get_text(separator=" ", strip=True)
        ctas = [btn.get_text(strip=True) for btn in soup.find_all(["button", "a"]) if btn.get_text(strip=True) and len(btn.get_text(strip=True)) < 60]

        return {
            "url": url,
            "headlines": headlines[:20],
            "ctas": list(set(ctas))[:15],
            "body_text_preview": body_text[:3000],
            "error": None,
        }
    except Exception as e:
        print(f"  ERROR scraping website: {e}", file=sys.stderr)
        return {"url": url, "headlines": [], "ctas": [], "body_text_preview": "", "error": str(e)}


def scrape_instagram(handle: str) -> dict:
    """Scrape public Instagram profile for bio and recent caption text."""
    url = f"https://www.instagram.com/{handle}/"
    print(f"  Scraping Instagram: @{handle}", file=sys.stderr)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15"
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)

        # Extract bio (appears near profile section)
        bio_match = re.search(r'("description"\s*:\s*"([^"]{10,300})")', text)
        bio = bio_match.group(2) if bio_match else ""

        # Extract caption snippets from meta tags
        captions = re.findall(r'"text"\s*:\s*"([^"]{20,500})"', text)

        return {
            "handle": handle,
            "url": url,
            "bio": bio,
            "captions": captions[:30],
            "raw_text_preview": text[:2000],
            "error": None,
        }
    except Exception as e:
        print(f"  ERROR scraping Instagram: {e}", file=sys.stderr)
        return {"handle": handle, "url": url, "bio": "", "captions": [], "raw_text_preview": "", "error": str(e)}


def scrape_youtube(channel_url: str) -> dict:
    """Scrape YouTube channel for video titles and descriptions."""
    print(f"  Scraping YouTube: {channel_url}", file=sys.stderr)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(channel_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)

            # Scroll to load more videos
            for _ in range(2):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)

            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Extract video titles
        titles = []
        for el in soup.find_all(id="video-title"):
            title = el.get_text(strip=True)
            if title:
                titles.append(title)

        # Fallback: look for title patterns in JSON-LD or meta
        if not titles:
            raw = soup.get_text(separator=" ", strip=True)
            titles = re.findall(r'"title"\s*:\s*\{\s*"runs"\s*:\s*\[\s*\{\s*"text"\s*:\s*"([^"]{5,150})"', raw)

        return {
            "channel_url": channel_url,
            "video_titles": titles[:30],
            "error": None,
        }
    except Exception as e:
        print(f"  ERROR scraping YouTube: {e}", file=sys.stderr)
        return {"channel_url": channel_url, "video_titles": [], "error": str(e)}


def main():
    args = parse_args()

    output_dir = Path(".tmp/clients")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{args.name}-raw.json"

    print(f"Building client profile for: {args.name}", file=sys.stderr)

    result = {
        "client_slug": args.name,
        "scraped_at": datetime.now().isoformat(),
        "website": None,
        "instagram": None,
        "youtube": None,
    }

    if args.website:
        result["website"] = scrape_website(args.website)

    if args.instagram:
        result["instagram"] = scrape_instagram(args.instagram)

    if args.youtube:
        result["youtube"] = scrape_youtube(args.youtube)

    if not any([args.website, args.instagram, args.youtube]):
        print("ERROR: Provide at least one of --website, --instagram, or --youtube.", file=sys.stderr)
        sys.exit(1)

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nRaw profile saved to: {output_path}", file=sys.stderr)
    print(f"Next step: use this data to fill in bots/clients/{args.name}.md", file=sys.stderr)
    print(f"  cp bots/clients/_template.md bots/clients/{args.name}.md", file=sys.stderr)
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
