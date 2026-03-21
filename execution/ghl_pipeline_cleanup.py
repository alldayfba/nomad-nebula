#!/usr/bin/env python3
"""GHL Pipeline Cleanup — moves stale 'Sales Call Booked' opportunities to 'No Answer Dial'.

Identifies opportunities in the Sales Call Booked stage that have no appointments
and haven't been updated recently, then moves them to keep the pipeline clean.

Usage:
    python execution/ghl_pipeline_cleanup.py                    # Dry run (default)
    python execution/ghl_pipeline_cleanup.py --execute          # Actually move them
    python execution/ghl_pipeline_cleanup.py --days 14          # Custom staleness threshold
    python execution/ghl_pipeline_cleanup.py --execute --days 3 # Move anything stale > 3 days
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

GHL_API_KEY = os.getenv("GHL_API_KEY", "")
GHL_BASE = "https://rest.gohighlevel.com/v1"
TIMEOUT = 15

# 24/7 Profits pipeline
PIPELINE_ID = "sFxWPIwC0fTGZBNRO0Lf"
SALES_CALL_BOOKED_STAGE = "694954ce-8782-4165-9e07-d8d3b57d5fc3"
NO_ANSWER_DIAL_STAGE = "2021b735-a8e2-4de7-9baa-a716de2dcf92"


def ghl_get(path: str, params: dict | None = None) -> dict | list | None:
    """GET from GHL v1 API."""
    resp = requests.get(f"{GHL_BASE}{path}",
                        headers={"Authorization": f"Bearer {GHL_API_KEY}"},
                        params=params, timeout=TIMEOUT)
    if resp.status_code == 200:
        return resp.json()
    print(f"  GHL {path}: {resp.status_code}", file=sys.stderr)
    return None


def ghl_put(path: str, data: dict) -> bool:
    """PUT to GHL v1 API."""
    resp = requests.put(f"{GHL_BASE}{path}",
                        headers={"Authorization": f"Bearer {GHL_API_KEY}",
                                 "Content-Type": "application/json"},
                        json=data, timeout=TIMEOUT)
    return resp.status_code in (200, 201)


def main():
    parser = argparse.ArgumentParser(description="Clean up stale GHL pipeline opportunities")
    parser.add_argument("--execute", action="store_true", help="Actually move stale opportunities (default: dry run)")
    parser.add_argument("--days", type=int, default=7, help="Staleness threshold in days (default: 7)")
    args = parser.parse_args()

    if not GHL_API_KEY:
        print("ERROR: GHL_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    cutoff = datetime.now() - timedelta(days=args.days)
    print(f"{'EXECUTE' if args.execute else 'DRY RUN'} — staleness threshold: {args.days} days (before {cutoff.strftime('%Y-%m-%d')})")
    print()

    # Get all opportunities in Sales Call Booked stage
    data = ghl_get(f"/pipelines/{PIPELINE_ID}/opportunities",
                   {"stageId": SALES_CALL_BOOKED_STAGE, "limit": 100})
    if not data:
        print("No data returned from GHL pipeline")
        return

    opps = data.get("opportunities", []) if isinstance(data, dict) else data
    print(f"Found {len(opps)} opportunities in 'Sales Call Booked' stage\n")

    stale = []
    active = []

    for opp in opps:
        name = opp.get("name", "Unknown")
        opp_id = opp.get("id", "")
        updated_at = opp.get("updatedAt", "")
        contact = opp.get("contact", {})
        contact_id = contact.get("id") or opp.get("contactId", "")

        # Parse updatedAt
        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00").replace("+00:00", ""))
        except (ValueError, AttributeError):
            updated = datetime.min

        is_old = updated < cutoff

        # Check if contact has appointments
        has_appointments = False
        if contact_id:
            apt_data = ghl_get(f"/contacts/{contact_id}/appointments")
            if apt_data:
                apts = apt_data.get("events", apt_data.get("appointments", []))
                if isinstance(apts, list) and len(apts) > 0:
                    has_appointments = True

        if is_old and not has_appointments:
            stale.append((name, opp_id, updated_at[:10]))
            marker = "STALE"
        else:
            active.append(name)
            marker = "ACTIVE" if has_appointments else f"RECENT ({updated_at[:10]})"

        print(f"  [{marker}] {name} — updated: {updated_at[:10]}" +
              (f" — has appointments" if has_appointments else ""))

    print(f"\n--- Summary ---")
    print(f"Active/Recent: {len(active)}")
    print(f"Stale (will move): {len(stale)}")

    if not stale:
        print("\nNothing to clean up!")
        return

    if not args.execute:
        print(f"\nDRY RUN — would move {len(stale)} opportunities to 'No Answer Dial':")
        for name, _, updated in stale:
            print(f"  • {name} (last updated: {updated})")
        print("\nRun with --execute to apply changes.")
        return

    # Move stale opportunities
    moved = 0
    for name, opp_id, updated in stale:
        success = ghl_put(
            f"/pipelines/{PIPELINE_ID}/opportunities/{opp_id}/status",
            {"stageId": NO_ANSWER_DIAL_STAGE}
        )
        if success:
            print(f"  MOVED {name} → No Answer Dial")
            moved += 1
        else:
            print(f"  FAILED to move {name}")

    print(f"\nDone: {moved}/{len(stale)} moved to 'No Answer Dial'")


if __name__ == "__main__":
    main()
