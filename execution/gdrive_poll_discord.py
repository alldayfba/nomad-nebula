#!/usr/bin/env python3
"""
Google Drive → Discord Poller — replaces Zapier ZAP-013 (Raw Footage to Discord).

Monitors a Google Drive folder for new files and sends notifications to Discord.
Tracks seen file IDs in .tmp/gdrive_poll_state.json to avoid duplicates.

Usage:
    python execution/gdrive_poll_discord.py --folder-id 1JwtXXiGJUOUJU8bQWvShe223HlvMeAid
    python execution/gdrive_poll_discord.py --folder-id <ID> --dry-run

Cron: every 10 minutes via launchd or scheduled-skills.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("gdrive-poll")

STATE_FILE = PROJECT_ROOT / ".tmp" / "gdrive_poll_state.json"

# Default: Content Hub folder from Zapier ZAP-013
DEFAULT_FOLDER_ID = "1JwtXXiGJUOUJU8bQWvShe223HlvMeAid"


def get_drive_service():
    """Build Google Drive API service using service account."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds_path = PROJECT_ROOT / "service_account.json"
    if not creds_path.exists():
        creds_path = PROJECT_ROOT / "credentials.json"

    creds = Credentials.from_service_account_file(
        str(creds_path),
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)


def load_state() -> dict:
    """Load polling state (set of seen file IDs per folder)."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    """Persist polling state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def list_files(folder_id: str, include_subfolders: bool = True) -> list:
    """List files in a Drive folder (optionally including subfolders)."""
    service = get_drive_service()

    query = f"'{folder_id}' in parents and trashed = false"
    fields = "files(id, name, mimeType, size, webContentLink, webViewLink, createdTime)"

    results = service.files().list(
        q=query,
        fields=fields,
        orderBy="createdTime desc",
        pageSize=50,
    ).execute()

    files = results.get("files", [])

    # Recursively check subfolders
    if include_subfolders:
        folders = [f for f in files if f.get("mimeType") == "application/vnd.google-apps.folder"]
        non_folders = [f for f in files if f.get("mimeType") != "application/vnd.google-apps.folder"]

        for folder in folders:
            sub_files = list_files(folder["id"], include_subfolders=True)
            non_folders.extend(sub_files)

        return non_folders

    return files


def format_file_embed(file_info: dict) -> dict:
    """Format a Drive file into a Discord embed matching the Zapier format."""
    name = file_info.get("name", "Unknown")
    link = file_info.get("webContentLink") or file_info.get("webViewLink", "")
    size_bytes = int(file_info.get("size", 0))
    created = file_info.get("createdTime", "")
    mime = file_info.get("mimeType", "")

    # Human-readable size
    if size_bytes > 1_000_000_000:
        size_str = f"{size_bytes / 1_000_000_000:.1f} GB"
    elif size_bytes > 1_000_000:
        size_str = f"{size_bytes / 1_000_000:.1f} MB"
    elif size_bytes > 1_000:
        size_str = f"{size_bytes / 1_000:.1f} KB"
    else:
        size_str = f"{size_bytes} bytes"

    # Icon based on type
    if "video" in mime:
        icon = "\U0001f3ac"
    elif "image" in mime:
        icon = "\U0001f5bc"
    elif "audio" in mime:
        icon = "\U0001f3b5"
    else:
        icon = "\U0001f4c4"

    return {
        "title": f"{icon} New Raw Footage Uploaded",
        "description": "\n".join([
            f"\U0001f4c1 **Title:** {name}",
            f"\U0001f4be **Size:** {size_str}",
            f"\U0001f4c5 **Uploaded:** {created[:10] if created else 'Unknown'}",
            f"\U0001f517 **Clip:** {link}" if link else "",
        ]),
        "color": 0x4285F4,
        "footer": {"text": "Google Drive \u2192 Direct (no Zapier)"},
    }


def main():
    parser = argparse.ArgumentParser(description="Poll Google Drive → Discord")
    parser.add_argument("--folder-id", default=DEFAULT_FOLDER_ID)
    parser.add_argument("--channel", default="raw-footage")
    parser.add_argument("--include-subfolders", action="store_true", default=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from execution.ghl_automations import discord_send

    state = load_state()
    seen_ids = set(state.get(args.folder_id, []))

    logger.info(f"Polling Drive folder {args.folder_id} (seen: {len(seen_ids)} files)")

    files = list_files(args.folder_id, include_subfolders=args.include_subfolders)

    if not files:
        logger.info("No files found")
        return

    new_files = [f for f in files if f["id"] not in seen_ids]

    if not new_files:
        logger.info(f"No new files (total: {len(files)})")
        return

    logger.info(f"Found {len(new_files)} new file(s)")

    for file_info in new_files:
        embed = format_file_embed(file_info)

        if args.dry_run:
            logger.info(f"[DRY RUN] {file_info['name']} ({file_info['id']})")
        else:
            try:
                discord_send(args.channel, embed=embed)
                logger.info(f"Sent notification for: {file_info['name']}")
            except Exception as e:
                logger.error(f"Failed to notify for {file_info['name']}: {e}")

        seen_ids.add(file_info["id"])

    # Save updated state
    state[args.folder_id] = list(seen_ids)
    save_state(state)
    logger.info(f"Updated state: {len(seen_ids)} files tracked")


if __name__ == "__main__":
    main()
