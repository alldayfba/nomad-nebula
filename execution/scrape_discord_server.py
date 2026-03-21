"""
Scrape ALL content from a Discord server using the REST API (httpx).
Extracts messages, attachments, embeds, and links from every text channel.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ENV_PATH = "/Users/Shared/antigravity/projects/nomad-nebula/.env"
OUTPUT_PATH = "/Users/Shared/antigravity/projects/nomad-nebula/.tmp/discord-content-scrape.json"
GUILD_ID = "1185214150222286849"
BASE_URL = "https://discord.com/api/v10"
RATE_DELAY = 0.5  # seconds between channel fetches
MESSAGE_LIMIT = 100  # max per request (Discord cap)

# Link patterns to extract from message content
LINK_PATTERNS = re.compile(
    r'https?://(?:'
    r'(?:www\.)?youtube\.com/\S+'
    r'|youtu\.be/\S+'
    r'|(?:www\.)?loom\.com/\S+'
    r'|drive\.google\.com/\S+'
    r'|docs\.google\.com/\S+'
    r'|(?:www\.)?dropbox\.com/\S+'
    r'|(?:www\.)?canva\.com/\S+'
    r'|(?:www\.)?notion\.so/\S+'
    r'|(?:www\.)?figma\.com/\S+'
    r'|(?:www\.)?vimeo\.com/\S+'
    r'|(?:www\.)?tiktok\.com/\S+'
    r'|(?:www\.)?instagram\.com/\S+'
    r'|(?:www\.)?twitter\.com/\S+'
    r'|(?:www\.)?x\.com/\S+'
    r'|(?:www\.)?facebook\.com/\S+'
    r'|(?:www\.)?linkedin\.com/\S+'
    r'|(?:www\.)?github\.com/\S+'
    r'|(?:www\.)?amazon\.com/\S+'
    r'|(?:www\.)?seller(?:amp|board)\.\S+'
    r'|(?:www\.)?keepa\.com/\S+'
    r')',
    re.IGNORECASE,
)

# Broader URL pattern for any link
ANY_URL = re.compile(r'https?://[^\s<>\)\]]+', re.IGNORECASE)


def load_token() -> str:
    load_dotenv(ENV_PATH)
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not found in .env")
        sys.exit(1)
    return token


def get_headers(token: str) -> dict:
    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }


def fetch_channels(client: httpx.Client, headers: dict) -> list[dict]:
    url = f"{BASE_URL}/guilds/{GUILD_ID}/channels"
    resp = client.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"ERROR fetching channels: {resp.status_code} {resp.text}")
        sys.exit(1)
    return resp.json()


def fetch_messages(client: httpx.Client, headers: dict, channel_id: str) -> list[dict]:
    """Fetch ALL messages from a channel with pagination."""
    all_messages = []
    url = f"{BASE_URL}/channels/{channel_id}/messages"
    params = {"limit": MESSAGE_LIMIT}

    while True:
        resp = client.get(url, headers=headers, params=params)

        if resp.status_code == 403:
            # Bot doesn't have access to this channel
            return []
        if resp.status_code == 429:
            # Rate limited
            retry_after = resp.json().get("retry_after", 2)
            print(f"    Rate limited, waiting {retry_after}s...")
            time.sleep(retry_after)
            continue
        if resp.status_code != 200:
            print(f"    Error {resp.status_code} for channel {channel_id}: {resp.text[:200]}")
            return all_messages

        messages = resp.json()
        if not messages:
            break

        all_messages.extend(messages)

        if len(messages) < MESSAGE_LIMIT:
            break  # No more messages

        # Paginate using before= oldest message ID
        params["before"] = messages[-1]["id"]
        time.sleep(RATE_DELAY)

    return all_messages


def extract_links(content: str) -> dict:
    """Extract categorized links from message content."""
    notable = LINK_PATTERNS.findall(content) if content else []
    all_urls = ANY_URL.findall(content) if content else []
    return {
        "notable_links": notable,
        "all_links": all_urls,
    }


def is_video_link(url: str) -> bool:
    video_domains = ["youtube.com", "youtu.be", "loom.com", "vimeo.com", "tiktok.com"]
    return any(d in url.lower() for d in video_domains)


def process_message(msg: dict) -> dict:
    content = msg.get("content", "")
    links = extract_links(content)

    attachments = []
    for att in msg.get("attachments", []):
        attachments.append({
            "filename": att.get("filename"),
            "url": att.get("url"),
            "content_type": att.get("content_type"),
            "size": att.get("size"),
        })

    embeds = []
    for emb in msg.get("embeds", []):
        embed_data = {
            "type": emb.get("type"),
            "title": emb.get("title"),
            "url": emb.get("url"),
            "description": emb.get("description", "")[:200] if emb.get("description") else None,
        }
        if emb.get("video"):
            embed_data["video_url"] = emb["video"].get("url")
        if emb.get("thumbnail"):
            embed_data["thumbnail_url"] = emb["thumbnail"].get("url")
        embeds.append(embed_data)

    author = msg.get("author", {})

    return {
        "id": msg.get("id"),
        "timestamp": msg.get("timestamp"),
        "author": f"{author.get('username', 'unknown')}#{author.get('discriminator', '0')}",
        "author_id": author.get("id"),
        "content": content,
        "attachments": attachments,
        "embeds": embeds,
        "notable_links": links["notable_links"],
        "all_links": links["all_links"],
    }


def main():
    token = load_token()
    headers = get_headers(token)

    print(f"Scraping Discord guild {GUILD_ID}...")

    with httpx.Client(timeout=30) as client:
        # 1. Get all channels
        channels = fetch_channels(client, headers)

        # Filter to text-based channels (type 0 = text, 5 = announcement, 11 = thread, 15 = forum)
        text_channels = [c for c in channels if c.get("type") in (0, 2, 5, 11, 15)]

        # Also get category info for organization
        categories = {c["id"]: c["name"] for c in channels if c.get("type") == 4}

        print(f"Found {len(channels)} total channels, {len(text_channels)} text-based channels")

        results = {}
        total_messages = 0
        total_videos = 0
        total_files = 0
        total_links = 0

        for ch in sorted(text_channels, key=lambda c: c.get("position", 999)):
            ch_id = ch["id"]
            ch_name = ch.get("name", "unknown")
            ch_type = ch.get("type")
            parent_id = ch.get("parent_id")
            category_name = categories.get(parent_id, "uncategorized") if parent_id else "uncategorized"

            type_labels = {0: "text", 2: "voice", 5: "announcement", 11: "thread", 15: "forum"}
            ch_type_label = type_labels.get(ch_type, f"type-{ch_type}")

            print(f"  Scraping #{ch_name} ({ch_type_label}, category: {category_name})...", end=" ", flush=True)

            messages = fetch_messages(client, headers, ch_id)
            print(f"{len(messages)} messages")

            if not messages:
                continue

            processed = []
            ch_videos = 0
            ch_files = 0
            ch_links = 0

            for msg in messages:
                p = process_message(msg)
                processed.append(p)

                # Count stats
                ch_files += len(p["attachments"])
                ch_links += len(p["all_links"])

                # Count videos
                for emb in p["embeds"]:
                    if emb.get("video_url") or (emb.get("url") and is_video_link(emb["url"])):
                        ch_videos += 1
                for link in p["all_links"]:
                    if is_video_link(link):
                        ch_videos += 1

            results[ch_name] = {
                "channel_id": ch_id,
                "channel_type": ch_type_label,
                "category": category_name,
                "message_count": len(processed),
                "video_count": ch_videos,
                "file_count": ch_files,
                "link_count": ch_links,
                "messages": processed,
            }

            total_messages += len(processed)
            total_videos += ch_videos
            total_files += ch_files
            total_links += ch_links

            time.sleep(RATE_DELAY)

    # Save output
    output = {
        "guild_id": GUILD_ID,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_channels_scraped": len(results),
            "total_messages": total_messages,
            "total_videos_found": total_videos,
            "total_files_found": total_files,
            "total_links_found": total_links,
        },
        "channels": results,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"SCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"  Channels scraped: {len(results)}")
    print(f"  Total messages:   {total_messages}")
    print(f"  Total videos:     {total_videos}")
    print(f"  Total files:      {total_files}")
    print(f"  Total links:      {total_links}")
    print(f"  Output:           {OUTPUT_PATH}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
