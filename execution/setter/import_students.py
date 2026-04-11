#!/usr/bin/env python3
"""
Import student IG handles into the setter blocklist.

Students who already paid should never receive cold DMs. This script
imports handles from a text file or adds them individually.

Optionally pulls from Supabase (247profits) if SUPABASE_URL is set.

Usage:
    python -m execution.setter.import_students                       # Import from file
    python -m execution.setter.import_students --add @handle1 @handle2
    python -m execution.setter.import_students --list
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from execution.setter import setter_db as db

STUDENT_FILE = _PROJECT_ROOT / ".tmp" / "setter" / "student_handles.txt"


def _load_from_file() -> List[str]:
    """Load student handles from the text file."""
    if not STUDENT_FILE.exists():
        return []
    handles = []
    with open(STUDENT_FILE, "r") as f:
        for line in f:
            h = line.strip().lower().lstrip("@")
            if h and not h.startswith("#"):
                handles.append(h)
    return list(dict.fromkeys(handles))  # dedupe


def _load_from_supabase() -> List[str]:
    """Try to pull student IG handles from Supabase (247profits)."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        return []

    try:
        from supabase import create_client
        client = create_client(supabase_url, supabase_key)

        # Try students table — look for ig_handle or instagram column
        for col in ("ig_handle", "instagram", "instagram_handle", "ig_username"):
            try:
                resp = client.table("students").select(col).not_.is_(col, "null").execute()
                if resp.data:
                    handles = []
                    for row in resp.data:
                        h = (row.get(col) or "").strip().lower().lstrip("@")
                        if h:
                            handles.append(h)
                    if handles:
                        print(f"  Pulled {len(handles)} handles from Supabase students.{col}")
                        return list(dict.fromkeys(handles))
            except Exception:
                continue

        # Try profiles table as fallback
        for col in ("ig_handle", "instagram", "instagram_handle"):
            try:
                resp = client.table("profiles").select(col).not_.is_(col, "null").execute()
                if resp.data:
                    handles = []
                    for row in resp.data:
                        h = (row.get(col) or "").strip().lower().lstrip("@")
                        if h:
                            handles.append(h)
                    if handles:
                        print(f"  Pulled {len(handles)} handles from Supabase profiles.{col}")
                        return list(dict.fromkeys(handles))
            except Exception:
                continue

    except ImportError:
        print("  supabase-py not installed — skipping Supabase import")
    except Exception as e:
        print(f"  Supabase error (non-fatal): {e}")

    return []


def import_students(add_handles: List[str] = None) -> dict:
    """Import student handles into blocklist.

    Returns: {total: int, added: int, already_blocked: int}
    """
    stats = {"total": 0, "added": 0, "already_blocked": 0, "from_file": 0, "from_supabase": 0}

    all_handles = []

    if add_handles:
        # Direct add mode
        all_handles = [h.lower().lstrip("@") for h in add_handles if h.strip()]
    else:
        # Import from file
        file_handles = _load_from_file()
        if file_handles:
            print(f"Loaded {len(file_handles)} handles from {STUDENT_FILE}")
            stats["from_file"] = len(file_handles)
            all_handles.extend(file_handles)
        else:
            print(f"No student file found at {STUDENT_FILE}")
            print(f"  Create one with one handle per line, or use --add @handle")

        # Also try Supabase
        print("Checking Supabase for student handles...")
        supa_handles = _load_from_supabase()
        if supa_handles:
            stats["from_supabase"] = len(supa_handles)
            all_handles.extend(supa_handles)

    # Deduplicate
    all_handles = list(dict.fromkeys(all_handles))
    stats["total"] = len(all_handles)

    if not all_handles:
        print("No student handles to import")
        return stats

    for handle in all_handles:
        if db.is_blocklisted(handle):
            stats["already_blocked"] += 1
            continue

        db.add_to_blocklist(handle, reason="student", source="student_list")
        stats["added"] += 1

        # Also save to the file for persistence
        if not add_handles:
            continue
        # When using --add, append to the file too
        STUDENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = set()
        if STUDENT_FILE.exists():
            existing = set(_load_from_file())
        with open(STUDENT_FILE, "a") as f:
            if handle not in existing:
                f.write(f"{handle}\n")

    print(f"\nStudent import complete:")
    print(f"  Total handles:      {stats['total']}")
    print(f"  Added to blocklist: {stats['added']}")
    print(f"  Already blocked:    {stats['already_blocked']}")
    if stats["from_file"]:
        print(f"  From file:          {stats['from_file']}")
    if stats["from_supabase"]:
        print(f"  From Supabase:      {stats['from_supabase']}")

    bl_stats = db.get_blocklist_stats()
    print(f"\nBlocklist totals: {bl_stats}")

    return stats


def list_students():
    """Show all student handles in the blocklist."""
    entries = db.get_blocklist(reason="student")
    if not entries:
        print("No students in blocklist")
        return

    print(f"Students in blocklist ({len(entries)}):")
    for e in entries:
        print(f"  @{e['ig_handle']}  (source: {e['source']}, added: {e['added_at']})")


def main():
    parser = argparse.ArgumentParser(description="Import student IG handles into blocklist")
    parser.add_argument("--add", nargs="+", help="Add specific handles: --add @h1 @h2")
    parser.add_argument("--list", action="store_true", help="Show all student handles in blocklist")
    args = parser.parse_args()

    if args.list:
        list_students()
    elif args.add:
        import_students(add_handles=args.add)
    else:
        import_students()


if __name__ == "__main__":
    main()
