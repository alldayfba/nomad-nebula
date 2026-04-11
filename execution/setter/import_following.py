#!/usr/bin/env python3
"""
Import IG following list into the setter blocklist.

Parses the Instagram data export (following.json) and adds every handle
to the blocklist with reason='following'. Also updates matching prospects
to following_status='we_follow'.

Usage:
    python -m execution.setter.import_following --file ~/Downloads/following.json
    python -m execution.setter.import_following --file ~/Downloads/following.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from execution.setter import setter_db as db


def _parse_following_json(data) -> List[str]:
    """Extract handles from IG following export (handles both known formats)."""
    handles = []

    # Format 1: top-level key "relationships_following" wrapping a list
    if isinstance(data, dict) and "relationships_following" in data:
        entries = data["relationships_following"]
    # Format 2: top-level array directly
    elif isinstance(data, list):
        entries = data
    else:
        # Try all top-level keys that look like lists
        entries = []
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    entries.extend(v)

    for entry in entries:
        # Each entry has string_list_data with value = handle
        sld = entry.get("string_list_data", [])
        for item in sld:
            handle = item.get("value", "").strip().lower().lstrip("@")
            if handle:
                handles.append(handle)
            elif item.get("href"):
                # Fallback: parse handle from URL
                href = item["href"].rstrip("/")
                h = href.split("/")[-1].strip().lower()
                if h:
                    handles.append(h)

    return handles


def import_following(file_path: str, dry_run: bool = False) -> dict:
    """Import following list from JSON or ZIP file.

    Returns: {total: int, added: int, already_blocked: int, prospects_updated: int}
    """
    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {path}")
        return {"total": 0, "added": 0, "already_blocked": 0, "prospects_updated": 0}

    # Handle ZIP files (IG exports come as ZIP)
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            # Look for following.json inside the zip
            candidates = [
                n for n in zf.namelist()
                if "following" in n.lower() and n.endswith(".json")
            ]
            if not candidates:
                print(f"No following.json found in {path}")
                return {"total": 0, "added": 0, "already_blocked": 0, "prospects_updated": 0}
            with zf.open(candidates[0]) as f:
                data = json.load(f)
    else:
        with open(path, "r") as f:
            data = json.load(f)

    handles = _parse_following_json(data)
    if not handles:
        print("No handles found in export file")
        return {"total": 0, "added": 0, "already_blocked": 0, "prospects_updated": 0}

    # Deduplicate
    handles = list(dict.fromkeys(handles))

    stats = {"total": len(handles), "added": 0, "already_blocked": 0, "prospects_updated": 0}

    print(f"Found {len(handles)} handles in following export")

    if dry_run:
        print("[DRY RUN] Would add to blocklist:")
        for h in handles[:20]:
            print(f"  @{h}")
        if len(handles) > 20:
            print(f"  ... and {len(handles) - 20} more")
        return stats

    for handle in handles:
        # Check if already blocklisted
        if db.is_blocklisted(handle):
            stats["already_blocked"] += 1
            continue

        # Add to blocklist
        db.add_to_blocklist(handle, reason="following", source="ig_export")
        stats["added"] += 1

        # Update matching prospect record
        prospect = db.get_prospect_by_handle(handle)
        if prospect:
            db.upsert_prospect(ig_handle=handle, status="following")
            stats["prospects_updated"] += 1

    print(f"\nImport complete:")
    print(f"  Total handles:      {stats['total']}")
    print(f"  Added to blocklist: {stats['added']}")
    print(f"  Already blocked:    {stats['already_blocked']}")
    print(f"  Prospects updated:  {stats['prospects_updated']}")

    # Show blocklist stats
    bl_stats = db.get_blocklist_stats()
    print(f"\nBlocklist totals: {bl_stats}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Import IG following into blocklist")
    parser.add_argument("--file", required=True, help="Path to following.json or IG export ZIP")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    args = parser.parse_args()

    import_following(args.file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
