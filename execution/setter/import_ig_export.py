#!/usr/bin/env python3
"""
Import Instagram's native JSON follower export into the setter database.

Instagram exports a ZIP containing followers_1.json (and followers_2.json, etc.
for large accounts). Each entry has string_list_data[0] with the handle, profile
URL, and follow timestamp.

Usage:
    python -m execution.setter.import_ig_export --file ~/Downloads/followers_1.json
    python -m execution.setter.import_ig_export --file ~/Downloads/instagram-export.zip
    python -m execution.setter.import_ig_export --file export.zip --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from execution.setter.setter_db import get_db, get_prospect_by_handle, upsert_prospect


def parse_ig_followers_json(data: list) -> List[Dict]:
    """Parse Instagram's follower JSON format into a list of dicts.

    Returns list of {handle, href, timestamp} for each valid entry.
    """
    followers = []
    for entry in data:
        sld = entry.get("string_list_data")
        if not sld or len(sld) == 0:
            continue
        item = sld[0]
        handle = item.get("value", "").strip()
        if not handle:
            continue
        followers.append({
            "handle": handle.lower().lstrip("@"),
            "href": item.get("href", ""),
            "timestamp": item.get("timestamp", 0),
        })
    return followers


def load_from_json(filepath: Path) -> List[Dict]:
    """Load followers from a single JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return parse_ig_followers_json(data)


def load_from_zip(filepath: Path) -> List[Dict]:
    """Extract and parse all followers_N.json files from a ZIP archive."""
    followers = []
    pattern = re.compile(r"(?:^|/)followers_?\d*\.json$", re.IGNORECASE)
    with zipfile.ZipFile(filepath, "r") as zf:
        matched = [n for n in zf.namelist() if pattern.search(n)]
        if not matched:
            # Fallback: any JSON file with "follower" in the name
            matched = [n for n in zf.namelist() if "follower" in n.lower() and n.endswith(".json")]
        if not matched:
            print(f"[!] No follower JSON files found in ZIP. Contents: {zf.namelist()[:20]}")
            return []
        for name in sorted(matched):
            print(f"  Reading {name} from ZIP...")
            with zf.open(name) as jf:
                data = json.load(jf)
            followers.extend(parse_ig_followers_json(data))
    return followers


def load_followers(filepath: Path) -> List[Dict]:
    """Auto-detect file type and load followers."""
    suffix = filepath.suffix.lower()
    if suffix == ".zip":
        return load_from_zip(filepath)
    elif suffix == ".json":
        return load_from_json(filepath)
    else:
        # Try JSON first, then ZIP
        try:
            return load_from_json(filepath)
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                return load_from_zip(filepath)
            except zipfile.BadZipFile:
                print(f"[!] Could not parse {filepath} as JSON or ZIP.")
                return []


def import_followers(followers: List[Dict], dry_run: bool = False) -> Tuple[int, int, int]:
    """Import parsed followers into the setter DB.

    Returns (total, skipped, added).
    """
    total = len(followers)
    skipped = 0
    added = 0

    for f in followers:
        handle = f["handle"]
        existing = get_prospect_by_handle(handle)
        if existing:
            skipped += 1
            continue
        if dry_run:
            added += 1
            continue

        ts = f.get("timestamp", 0)
        source_detail = ""
        if ts:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            source_detail = f"followed {dt.strftime('%Y-%m-%d')}"

        upsert_prospect(
            ig_handle=handle,
            source="ig_export",
            source_detail=source_detail,
            status="new",
        )
        added += 1

    return total, skipped, added


def main():
    parser = argparse.ArgumentParser(
        description="Import Instagram follower export into setter DB"
    )
    parser.add_argument(
        "--file", required=True, type=str,
        help="Path to followers JSON or ZIP file"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and check DB but don't insert anything"
    )
    args = parser.parse_args()

    filepath = Path(args.file).expanduser().resolve()
    if not filepath.exists():
        print(f"[!] File not found: {filepath}")
        sys.exit(1)

    # Ensure DB exists (get_db auto-creates schema)
    get_db()

    print(f"Loading followers from {filepath}...")
    followers = load_followers(filepath)
    if not followers:
        print("[!] No followers found in file.")
        sys.exit(1)

    # Deduplicate by handle (keep first occurrence)
    seen = set()
    unique = []
    for f in followers:
        if f["handle"] not in seen:
            seen.add(f["handle"])
            unique.append(f)
    dupes_in_file = len(followers) - len(unique)

    print(f"Parsed {len(followers)} entries ({len(unique)} unique handles, {dupes_in_file} duplicates in file)")

    if args.dry_run:
        print("[DRY RUN] Checking against DB without inserting...")

    total, skipped, added = import_followers(unique, dry_run=args.dry_run)

    print()
    print("=" * 50)
    print(f"  Total in export:    {total}")
    print(f"  Already in DB:      {skipped}")
    print(f"  Newly {'would add' if args.dry_run else 'added'}:      {added}")
    if dupes_in_file:
        print(f"  Dupes in file:      {dupes_in_file}")
    print("=" * 50)

    if args.dry_run:
        print("\n[DRY RUN] No changes were made to the database.")


if __name__ == "__main__":
    main()
