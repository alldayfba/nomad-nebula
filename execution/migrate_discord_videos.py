#!/usr/bin/env python3
"""
Migrate Discord CDN video URLs to Supabase Storage.

Discord CDN signed URLs expire after ~24h. This script:
1. Reads all academy_lessons with cdn.discordapp.com video_url
2. Uses Discord Bot token to fetch fresh (non-expired) attachment URLs
3. Downloads each file
4. Uploads to Supabase Storage (course-videos bucket)
5. Updates academy_lessons.video_url with permanent Supabase URL

Usage:
    python execution/migrate_discord_videos.py
    python execution/migrate_discord_videos.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import requests
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("STUDENT_SAAS_SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("STUDENT_SAAS_SUPABASE_KEY", "")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
BUCKET_NAME = "course-videos"
TMP_DIR = Path(__file__).parent.parent / ".tmp" / "video_migration"

# Load from fba-saas .env.local if not in env
FBA_SAAS_ENV = Path("/Users/SabboOpenClawAI/Documents/fba-saas/.env.local")
if not FBA_SAAS_ENV.exists():
    FBA_SAAS_ENV = Path("/Users/sabbojb/Documents/fba-saas/.env.local")
if FBA_SAAS_ENV.exists() and not SUPABASE_URL:
    for line in FBA_SAAS_ENV.read_text().splitlines():
        if line.startswith("NEXT_PUBLIC_SUPABASE_URL="):
            SUPABASE_URL = line.split("=", 1)[1].strip()
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
            SUPABASE_SERVICE_KEY = line.split("=", 1)[1].strip()

# Load Discord bot token from nomad .env
NOMAD_ENV = Path(__file__).parent.parent / ".env"
if NOMAD_ENV.exists() and not DISCORD_BOT_TOKEN:
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
    url = f"{SUPABASE_URL}/rest/v1/academy_lessons"
    params = {
        "select": "id,title,video_url,module_id",
        "video_url": "like.*cdn.discordapp.com*",
        "order": "module_id,sort_order",
    }
    resp = requests.get(url, headers={**supabase_headers(), "Content-Type": "application/json"}, params=params)
    resp.raise_for_status()
    return resp.json()


def parse_discord_url(url):
    """Extract channel_id, attachment_id, filename from Discord CDN URL."""
    # https://cdn.discordapp.com/attachments/{channel_id}/{attachment_id}/{filename}?params
    match = re.search(r"/attachments/(\d+)/(\d+)/([^?]+)", url)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, None


def get_fresh_discord_url(channel_id, attachment_id, filename):
    """Use Discord API to get a fresh (non-expired) attachment URL.

    Fetches messages from the channel around the attachment message,
    finds the matching attachment, and returns the fresh URL.
    """
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

    # Search messages in channel around the attachment ID
    # Attachment IDs are snowflakes, so they're close to the message ID
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    params = {"around": attachment_id, "limit": 10}

    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        print(f"  Discord API error {resp.status_code} for channel {channel_id}")
        return None

    messages = resp.json()
    for msg in messages:
        for att in msg.get("attachments", []):
            if str(att["id"]) == str(attachment_id) or att["filename"] == filename:
                return att["url"]

    # Fallback: try fetching by message ID (attachment_id might be the message ID)
    msg_url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{attachment_id}"
    resp2 = requests.get(msg_url, headers=headers)
    if resp2.status_code == 200:
        msg = resp2.json()
        for att in msg.get("attachments", []):
            if att["filename"] == filename:
                return att["url"]

    return None


def download_file(url, dest_path):
    """Download a file with progress."""
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
    return downloaded


def ensure_bucket():
    """Create the Supabase Storage bucket if it doesn't exist."""
    url = f"{SUPABASE_URL}/storage/v1/bucket"
    resp = requests.get(url, headers=supabase_headers())
    buckets = resp.json()

    if any(b.get("name") == BUCKET_NAME for b in buckets):
        print(f"Bucket '{BUCKET_NAME}' exists")
        return

    create_url = f"{SUPABASE_URL}/storage/v1/bucket"
    resp = requests.post(create_url, headers={**supabase_headers(), "Content-Type": "application/json"}, json={
        "id": BUCKET_NAME,
        "name": BUCKET_NAME,
        "public": True,
        "file_size_limit": 524288000,  # 500MB
        "allowed_mime_types": ["video/mp4", "video/quicktime", "video/webm", "audio/mpeg", "audio/mp3"],
    })
    if resp.status_code in (200, 201):
        print(f"Created bucket '{BUCKET_NAME}'")
    else:
        print(f"Bucket creation response: {resp.status_code} {resp.text}")


def upload_to_supabase(file_path, storage_path):
    """Upload a file to Supabase Storage. Returns public URL."""
    mime_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mp3": "audio/mpeg",
    }
    ext = Path(file_path).suffix.lower()
    content_type = mime_types.get(ext, "application/octet-stream")

    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET_NAME}/{storage_path}"
    with open(file_path, "rb") as f:
        resp = requests.post(url, headers={
            **supabase_headers(),
            "Content-Type": content_type,
            "x-upsert": "true",
        }, data=f)

    if resp.status_code in (200, 201):
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{storage_path}"
        return public_url
    else:
        print(f"  Upload error {resp.status_code}: {resp.text[:200]}")
        return None


def update_lesson_url(lesson_id, new_url):
    """Update the video_url in academy_lessons."""
    url = f"{SUPABASE_URL}/rest/v1/academy_lessons"
    resp = requests.patch(
        url,
        headers={**supabase_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
        params={"id": f"eq.{lesson_id}"},
        json={"video_url": new_url},
    )
    return resp.status_code in (200, 204)


def sanitize_filename(name):
    """Clean filename for storage path."""
    name = re.sub(r'[^\w\-_. ]', '', name)
    name = re.sub(r'\s+', '_', name)
    return name[:100]


def main():
    parser = argparse.ArgumentParser(description="Migrate Discord CDN videos to Supabase Storage")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    args = parser.parse_args()

    # Validate config
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        print(f"  SUPABASE_URL: {'set' if SUPABASE_URL else 'MISSING'}")
        print(f"  SUPABASE_SERVICE_KEY: {'set' if SUPABASE_SERVICE_KEY else 'MISSING'}")
        sys.exit(1)
    if not DISCORD_BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN required (in .env)")
        sys.exit(1)

    TMP_DIR.mkdir(parents=True, exist_ok=True)

    # Get all Discord lessons
    lessons = get_discord_lessons()
    print(f"\nFound {len(lessons)} lessons with Discord CDN video URLs\n")

    if args.dry_run:
        for l in lessons:
            ch, att, fn = parse_discord_url(l["video_url"])
            print(f"  [{fn}] {l['title'][:60]}")
        print(f"\nDry run — would migrate {len(lessons)} files to Supabase Storage")
        return

    # Create bucket
    ensure_bucket()

    # Module name lookup for folder structure
    mod_resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/academy_modules?select=id,slug",
        headers={**supabase_headers(), "Content-Type": "application/json"},
    )
    mod_map = {m["id"]: m["slug"] for m in mod_resp.json()} if mod_resp.status_code == 200 else {}

    migrated = 0
    failed = 0
    skipped = 0

    for i, lesson in enumerate(lessons, 1):
        title = lesson["title"][:60]
        channel_id, attachment_id, filename = parse_discord_url(lesson["video_url"])

        if not channel_id:
            print(f"[{i}/{len(lessons)}] SKIP — can't parse URL: {title}")
            skipped += 1
            continue

        print(f"[{i}/{len(lessons)}] {title}")

        # Get fresh Discord URL
        print(f"  Fetching fresh URL from Discord...")
        fresh_url = get_fresh_discord_url(channel_id, attachment_id, filename)
        if not fresh_url:
            print(f"  FAILED — couldn't get fresh URL from Discord")
            failed += 1
            continue

        # Download
        local_path = TMP_DIR / filename
        print(f"  Downloading {filename}...")
        try:
            size = download_file(fresh_url, local_path)
            size_mb = size / (1024 * 1024)
            print(f"  Downloaded {size_mb:.1f} MB")
        except Exception as e:
            print(f"  FAILED download: {e}")
            failed += 1
            continue

        # Upload to Supabase Storage
        module_slug = mod_map.get(lesson["module_id"], "general")
        safe_name = sanitize_filename(Path(filename).stem) + Path(filename).suffix.lower()
        storage_path = f"{module_slug}/{safe_name}"

        print(f"  Uploading to {storage_path}...")
        public_url = upload_to_supabase(local_path, storage_path)
        if not public_url:
            print(f"  FAILED upload")
            failed += 1
            continue

        # Update lesson
        if update_lesson_url(lesson["id"], public_url):
            print(f"  OK — {public_url}")
            migrated += 1
        else:
            print(f"  FAILED — DB update failed")
            failed += 1

        # Cleanup temp file
        try:
            local_path.unlink()
        except Exception:
            pass

        # Rate limit Discord API
        time.sleep(1)

    print(f"\n{'='*60}")
    print(f"Migration complete:")
    print(f"  Migrated: {migrated}")
    print(f"  Failed:   {failed}")
    print(f"  Skipped:  {skipped}")
    print(f"  Total:    {len(lessons)}")


if __name__ == "__main__":
    main()
