#!/usr/bin/env python3
"""
Extract course-relevant content from Discord scrape JSON into structured format
for SaaS academy import.

Reads: .tmp/discord-content-scrape.json (24MB)
Writes: .tmp/discord-course-content.json

Groups content into logical course modules, deduplicates by URL,
and captures metadata (title, url, type, channel, author, timestamp).
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# --- Configuration ---

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / ".tmp" / "discord-content-scrape.json"
OUTPUT_FILE = PROJECT_ROOT / ".tmp" / "discord-course-content.json"

# Video URL patterns
VIDEO_PATTERNS = [
    re.compile(r'https?://(?:www\.)?youtube\.com/(?:watch|embed|shorts)[^\s<>"]*', re.I),
    re.compile(r'https?://youtu\.be/[^\s<>"]+', re.I),
    re.compile(r'https?://(?:www\.)?loom\.com/share/[^\s<>"]+', re.I),
    re.compile(r'https?://(?:www\.)?vimeo\.com/[^\s<>"]+', re.I),
    re.compile(r'https?://urlgeni\.us/youtube/[^\s<>"]+', re.I),
]

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}

# Document URL patterns
DOC_PATTERNS = [
    re.compile(r'https?://docs\.google\.com/[^\s<>"]+', re.I),
    re.compile(r'https?://sheets\.google\.com/[^\s<>"]+', re.I),
    re.compile(r'https?://drive\.google\.com/[^\s<>"]+', re.I),
    re.compile(r'https?://docs\.google\.com/spreadsheets/[^\s<>"]+', re.I),
]

DOC_EXTENSIONS = {'.pdf', '.xlsx', '.xls', '.csv', '.docx', '.doc', '.pptx', '.ppt', '.txt'}

# Image extensions that could be course material (skip tiny icons)
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
MIN_IMAGE_SIZE = 50_000  # 50KB minimum to filter out small icons/emoji

# Module mapping rules (channel name substring -> module)
MODULE_RULES = [
    # Exact channel matches first
    ("alldayfba-uploads", "Core Course Videos"),
    ("call-recordings", "Coaching Call Library"),
    ("upload-call-recording", "Coaching Call Library"),
    ("server-call-recordings", "Coaching Call Library"),
    ("google-ads-course", "Google Ads Course"),
    ("sales-course", "Sales Course"),
    ("facebook-ads-course", "Facebook Ads Course"),
    ("tiktok-ads-course", "TikTok Ads Course"),
    ("leadgen-ads-course", "Lead Gen Ads Course"),
    ("b2b-outreach", "B2B Outreach Course"),
    ("online-arbitrage-course", "Online Arbitrage Course"),
    ("seller-central-course", "Seller Central Course"),
    ("keepa-course", "Keepa Course"),
    ("funding-course", "Funding Course"),
    ("mindset", "Mindset Course"),
    ("alex-hormozi-gems", "Alex Hormozi Gems"),
    ("amazon-resources", "Amazon Resources"),
    ("resources-2", "Amazon Resources"),
    ("new-product-lead", "Product Leads"),
    # Category-based fallbacks
    ("winners-circle", "Student Wins"),
    ("ic-wins", "Student Wins"),
    ("announcements", "Announcements"),
    ("client-success-manager", "Coaching Resources"),
    ("pat-va", "Coaching Resources"),
]

# Categories that map to modules
CATEGORY_MODULE_MAP = {
    "Amazon FBA/FBM Course": "Amazon FBA Course Materials",
    "Freelance Brand Scaling Course": "Brand Scaling Course Materials",
}


def classify_module(channel_name: str, category: str) -> str:
    """Determine which course module a channel belongs to."""
    clean = channel_name.lower()
    # Strip emoji prefixes for matching
    clean = re.sub(r'^[^\w]+', '', clean).strip()

    for pattern, module in MODULE_RULES:
        if pattern in clean:
            return module

    # Check category
    for cat_key, module in CATEGORY_MODULE_MAP.items():
        if cat_key.lower() in category.lower():
            return module

    # Inner Circle student channels -> Student Progress
    if "The Inner Circle" in category and re.match(r'^[^\w]*\w+$', channel_name):
        return "Inner Circle Student Channels"

    # Groupchat channels
    if "groupchat" in clean:
        return "Community Content"

    return "Supplementary Materials"


def extract_title_from_content(content: str) -> str | None:
    """Try to extract a meaningful title from message content."""
    if not content:
        return None

    # Look for bold text (**title**)
    bold = re.findall(r'\*\*([^*]+)\*\*', content)
    if bold:
        # Filter out generic markers
        for b in bold:
            b = b.strip()
            if len(b) > 3 and b.upper() not in ('NEW YT VIDEO', 'NEW VIDEO', '-'):
                return b[:200]

    # First non-empty line that isn't just a URL
    for line in content.split('\n'):
        line = line.strip()
        if line and not line.startswith('http') and len(line) > 5:
            return line[:200]

    return None


def classify_url(url: str) -> str:
    """Classify a URL as video, document, image, or link."""
    lower = url.lower()

    # Check video patterns
    for pat in VIDEO_PATTERNS:
        if pat.match(url):
            return "video"

    # Check extensions
    path_part = lower.split('?')[0]
    ext = '.' + path_part.rsplit('.', 1)[-1] if '.' in path_part else ''

    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in DOC_EXTENSIONS:
        return "document"
    if ext in IMAGE_EXTENSIONS:
        return "image"

    # Check doc patterns
    for pat in DOC_PATTERNS:
        if pat.match(url):
            return "document"

    return "link"


def extract_from_message(msg: dict, channel_name: str, module: str) -> list[dict]:
    """Extract all course-relevant resources from a single message."""
    resources = []
    seen_urls = set()

    author = msg.get("author", "unknown")
    timestamp = msg.get("timestamp", "")
    content = msg.get("content", "")
    msg_title = extract_title_from_content(content)

    # 1) Process embeds (richest metadata)
    for embed in msg.get("embeds", []):
        url = embed.get("url", "")
        if not url or url in seen_urls:
            continue

        embed_type = embed.get("type", "")
        resource_type = "video" if embed_type == "video" else classify_url(url)

        # For video embeds, also check video_url
        video_url = embed.get("video_url", "")
        if video_url and "youtube.com/embed" in video_url:
            resource_type = "video"

        title = embed.get("title") or msg_title or ""
        description = embed.get("description") or ""

        seen_urls.add(url)
        resources.append({
            "title": title,
            "description": description[:500] if description else "",
            "url": url,
            "type": resource_type,
            "channel_source": channel_name,
            "module": module,
            "author": author,
            "timestamp": timestamp,
            "thumbnail_url": embed.get("thumbnail_url", ""),
        })

    # 2) Process attachments
    for att in msg.get("attachments", []):
        url = att.get("url", "")
        if not url or url in seen_urls:
            continue

        filename = att.get("filename", "")
        content_type = att.get("content_type", "")
        size = att.get("size", 0)

        # Determine type from content_type or extension
        if content_type.startswith("video/") or any(filename.lower().endswith(e) for e in VIDEO_EXTENSIONS):
            resource_type = "video"
        elif content_type.startswith("image/") or any(filename.lower().endswith(e) for e in IMAGE_EXTENSIONS):
            # Filter small images
            if size < MIN_IMAGE_SIZE:
                continue
            resource_type = "image"
        elif any(filename.lower().endswith(e) for e in DOC_EXTENSIONS):
            resource_type = "document"
        elif content_type == "application/pdf":
            resource_type = "document"
        else:
            # Unknown attachment type — include if it's a reasonable size
            resource_type = "file"

        title = msg_title or filename
        seen_urls.add(url)
        resources.append({
            "title": title,
            "description": "",
            "url": url,
            "type": resource_type,
            "channel_source": channel_name,
            "module": module,
            "author": author,
            "timestamp": timestamp,
            "filename": filename,
            "size": size,
            "content_type": content_type,
        })

    # 3) Process links from all_links that weren't already captured
    for url in msg.get("all_links", []):
        if url in seen_urls:
            continue

        resource_type = classify_url(url)
        # Only include videos and documents from raw links (skip random web links)
        if resource_type in ("video", "document"):
            seen_urls.add(url)
            resources.append({
                "title": msg_title or "",
                "description": "",
                "url": url,
                "type": resource_type,
                "channel_source": channel_name,
                "module": module,
                "author": author,
                "timestamp": timestamp,
            })

    return resources


def main():
    print(f"Reading {INPUT_FILE}...")
    with open(INPUT_FILE, "r") as f:
        data = json.load(f)

    channels = data.get("channels", {})
    scrape_summary = data.get("summary", {})
    print(f"Scrape summary: {json.dumps(scrape_summary, indent=2)}")
    print(f"Total channels in file: {len(channels)}")
    print()

    all_resources = []
    module_stats = defaultdict(lambda: defaultdict(int))
    channels_processed = 0

    for channel_name, ch_data in channels.items():
        video_count = ch_data.get("video_count", 0)
        file_count = ch_data.get("file_count", 0)

        # Filter: only process channels with >0 videos or >5 files
        if video_count == 0 and file_count <= 5:
            continue

        channels_processed += 1
        category = ch_data.get("category", "")
        module = classify_module(channel_name, category)
        messages = ch_data.get("messages", [])

        for msg in messages:
            resources = extract_from_message(msg, channel_name, module)
            for r in resources:
                all_resources.append(r)
                module_stats[module][r["type"]] += 1

    # Deduplicate by URL
    seen = {}
    deduped = []
    dupes = 0
    # Domains where query params are essential to identity
    KEEP_PARAMS_DOMAINS = ('youtube.com', 'youtu.be', 'docs.google.com',
                           'sheets.google.com', 'drive.google.com',
                           'loom.com', 'vimeo.com')
    for r in all_resources:
        url = r["url"]
        # Only strip query params for CDN/attachment URLs where params are cache tokens
        if any(d in url for d in KEEP_PARAMS_DOMAINS):
            clean_url = url
        elif 'cdn.discordapp.com' in url:
            # Keep full URL for discord CDN (unique per file)
            clean_url = url.split('?')[0]
        else:
            clean_url = url.split('?')[0]
        if clean_url not in seen:
            seen[clean_url] = True
            deduped.append(r)
        else:
            dupes += 1

    # Sort by module, then by timestamp
    deduped.sort(key=lambda r: (r["module"], r.get("timestamp", "")))

    # Build output
    output = {
        "extracted_at": data.get("scraped_at", ""),
        "source_guild_id": data.get("guild_id", ""),
        "total_resources": len(deduped),
        "duplicates_removed": dupes,
        "channels_processed": channels_processed,
        "modules": {},
    }

    # Group by module
    for r in deduped:
        mod = r["module"]
        if mod not in output["modules"]:
            output["modules"][mod] = {
                "resources": [],
                "summary": defaultdict(int),
            }
        output["modules"][mod]["resources"].append(r)
        output["modules"][mod]["summary"][r["type"]] += 1

    # Convert summary defaultdicts to regular dicts
    for mod in output["modules"]:
        output["modules"][mod]["summary"] = dict(output["modules"][mod]["summary"])

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"Output written to {OUTPUT_FILE}")
    print(f"Channels processed: {channels_processed}")
    print(f"Total resources extracted: {len(deduped)} ({dupes} duplicates removed)")
    print()

    # Print summary per module
    print("=" * 70)
    print("MODULE SUMMARY")
    print("=" * 70)
    for mod_name in sorted(output["modules"].keys()):
        mod = output["modules"][mod_name]
        total = len(mod["resources"])
        summary = mod["summary"]
        parts = [f"{v} {k}s" for k, v in sorted(summary.items())]
        print(f"\n  {mod_name} ({total} resources)")
        print(f"    {', '.join(parts)}")

        # Show channel sources
        sources = set(r["channel_source"] for r in mod["resources"])
        print(f"    Channels: {', '.join(sorted(sources))}")

    # Extra: list all video resources for quick review
    videos = [r for r in deduped if r["type"] == "video"]
    print(f"\n{'=' * 70}")
    print(f"ALL VIDEOS ({len(videos)})")
    print("=" * 70)
    for v in videos:
        title = v.get("title", "") or v.get("filename", "") or "Untitled"
        print(f"  [{v['module']}] {title[:80]}")
        print(f"    {v['url'][:120]}")


if __name__ == "__main__":
    main()
