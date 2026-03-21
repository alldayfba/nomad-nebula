#!/usr/bin/env python3
"""
Refresh Discord CDN video URLs in academy_lessons before they expire.

Discord signed URLs expire every ~24h. This script:
1. Reads all academy_lessons with cdn.discordapp.com video_url
2. Uses Discord Bot token to fetch fresh signed URLs from the same channels
3. Updates academy_lessons.video_url with the fresh URLs

Run daily at 11:50 PM via cron/launchd.

Usage:
    python execution/refresh_discord_video_urls.py
    python execution/refresh_discord_video_urls.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import requests
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
SUPABASE_URL = ""
SUPABASE_SERVICE_KEY = ""
DISCORD_BOT_TOKEN = ""

# Load from fba-saas .env.local (check both user paths)
FBA_SAAS_ENV = Path("/Users/SabboOpenClawAI/Documents/fba-saas/.env.local")
if not FBA_SAAS_ENV.exists():
    FBA_SAAS_ENV = Path("/Users/sabbojb/Documents/fba-saas/.env.local")
if FBA_SAAS_ENV.exists():
    for line in FBA_SAAS_ENV.read_text().splitlines():
        if line.startswith("NEXT_PUBLIC_SUPABASE_URL="):
            SUPABASE_URL = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
            SUPABASE_SERVICE_KEY = line.split("=", 1)[1].strip()

# Load Discord bot token from nomad .env
NOMAD_ENV = Path(__file__).parent.parent / ".env"
if NOMAD_ENV.exists():
    for line in NOMAD_ENV.read_text().splitlines():
        if line.startswith("DISCORD_BOT_TOKEN="):
            DISCORD_BOT_TOKEN = line.split("=", 1)[1].strip()


def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }


def get_discord_lessons():
    """Fetch all lessons with Discord CDN video URLs."""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/academy_lessons",
        headers={**supabase_headers(), "Content-Type": "application/json"},
        params={
            "select": "id,title,video_url",
            "video_url": "like.*cdn.discordapp.com*",
        },
    )
    resp.raise_for_status()
    return resp.json()


def parse_discord_url(url):
    """Extract channel_id, attachment_id, filename from Discord CDN URL."""
    match = re.search(r"/attachments/(\d+)/(\d+)/([^?]+)", url)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, None


def get_fresh_url(channel_id, attachment_id, filename):
    """Fetch fresh signed URL from Discord API."""
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

    # Try fetching messages around the attachment
    resp = requests.get(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers=headers,
        params={"around": attachment_id, "limit": 10},
    )
    if resp.status_code == 200:
        for msg in resp.json():
            for att in msg.get("attachments", []):
                if str(att["id"]) == str(attachment_id) or att["filename"] == filename:
                    return att["url"]

    # Fallback: try direct message fetch
    resp2 = requests.get(
        f"https://discord.com/api/v10/channels/{channel_id}/messages/{attachment_id}",
        headers=headers,
    )
    if resp2.status_code == 200:
        for att in resp2.json().get("attachments", []):
            if att["filename"] == filename:
                return att["url"]

    return None


def update_lesson_url(lesson_id, new_url):
    """Update video_url in academy_lessons."""
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/academy_lessons",
        headers={**supabase_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
        params={"id": f"eq.{lesson_id}"},
        json={"video_url": new_url},
    )
    return resp.status_code in (200, 204)


def main():
    parser = argparse.ArgumentParser(description="Refresh Discord CDN video URLs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: Supabase credentials not found")
        sys.exit(1)
    if not DISCORD_BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not found in .env")
        sys.exit(1)

    lessons = get_discord_lessons()
    print(f"Found {len(lessons)} lessons with Discord CDN URLs")

    if not lessons:
        print("Nothing to refresh")
        return

    refreshed = 0
    failed = 0

    for i, lesson in enumerate(lessons, 1):
        channel_id, attachment_id, filename = parse_discord_url(lesson["video_url"])
        if not channel_id:
            print(f"[{i}/{len(lessons)}] SKIP — can't parse: {lesson['title'][:50]}")
            failed += 1
            continue

        fresh_url = get_fresh_url(channel_id, attachment_id, filename)
        if not fresh_url:
            print(f"[{i}/{len(lessons)}] FAIL — no fresh URL: {lesson['title'][:50]}")
            failed += 1
            continue

        if args.dry_run:
            print(f"[{i}/{len(lessons)}] OK (dry) — {lesson['title'][:50]}")
            refreshed += 1
        else:
            if update_lesson_url(lesson["id"], fresh_url):
                print(f"[{i}/{len(lessons)}] OK — {lesson['title'][:50]}")
                refreshed += 1
            else:
                print(f"[{i}/{len(lessons)}] FAIL — DB update: {lesson['title'][:50]}")
                failed += 1

        # Rate limit: Discord allows 50 req/sec but be safe
        time.sleep(0.5)

    print(f"\nDone: {refreshed} refreshed, {failed} failed out of {len(lessons)}")

    # ── Alert on failure via Discord webhook ──
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        # Try loading from nomad .env
        if NOMAD_ENV.exists():
            for line in NOMAD_ENV.read_text().splitlines():
                if line.startswith("DISCORD_WEBHOOK_URL="):
                    webhook_url = line.split("=", 1)[1].strip()
                    break

    if failed > 0 and webhook_url:
        try:
            requests.post(webhook_url, json={
                "content": f"⚠️ **Video URL Refresh Alert**: {failed}/{len(lessons)} lessons failed to refresh. Students may see broken videos. Run `python execution/refresh_discord_video_urls.py` manually."
            }, timeout=10)
        except Exception:
            pass

    if refreshed == 0 and len(lessons) > 0 and webhook_url:
        try:
            requests.post(webhook_url, json={
                "content": f"🚨 **CRITICAL: Video URL Refresh FAILED**: 0/{len(lessons)} refreshed. ALL course videos may be broken. Investigate immediately."
            }, timeout=10)
        except Exception:
            pass


if __name__ == "__main__":
    main()
