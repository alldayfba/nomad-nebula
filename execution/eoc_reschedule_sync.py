#!/usr/bin/env python3
"""EOC Reschedule Sync — creates sales_calls_booked entries from showed_not_closed EOC reports.

Runs every 30 min via launchd. Idempotent — safe to run repeatedly.

Usage:
    python execution/eoc_reschedule_sync.py           # Normal run
    python execution/eoc_reschedule_sync.py --dry-run  # Preview only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
ORG_ID = os.getenv("DASHBOARD_ORG_ID", "")
GHL_API_KEY = os.getenv("GHL_API_KEY", "")
GHL_CALENDAR_ID = os.getenv("GHL_SALES_CALENDAR_ID", "9fL4lUjdONSbW0oJ419Y")
TIMEOUT = 15


def log(msg: str):
    print(f"[eoc-sync] {msg}", file=sys.stderr)


def supabase_get(table: str, params: dict) -> list:
    """Query Supabase REST API."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    query_params = {"select": "*"}
    if ORG_ID:
        query_params["organization_id"] = f"eq.{ORG_ID}"
    query_params.update(params)
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers,
                        params=query_params, timeout=TIMEOUT)
    if resp.status_code == 200:
        return resp.json()
    log(f"Supabase GET {table}: {resp.status_code} {resp.text[:200]}")
    return []


def supabase_insert(table: str, data: dict) -> bool:
    """Insert a row into Supabase."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    resp = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers,
                         json=data, timeout=TIMEOUT)
    if resp.status_code in (200, 201):
        return True
    log(f"Supabase INSERT {table}: {resp.status_code} {resp.text[:200]}")
    return False


def parse_time_from_notes(notes: str) -> str | None:
    """Extract a time from EOC notes field. Returns HH:MM or None."""
    if not notes:
        return None
    # Match patterns: "3pm", "3:00 PM", "3:00pm", "15:00", "at 3", "@ 3pm"
    patterns = [
        r'(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)',       # 3:00 PM
        r'(\d{1,2})\s*(am|pm|AM|PM)',                 # 3pm
        r'(\d{1,2}):(\d{2})',                          # 15:00 (24h)
        r'(?:at|@)\s*(\d{1,2})\b',                    # at 3, @ 3
    ]
    for pat in patterns:
        m = re.search(pat, notes)
        if m:
            groups = m.groups()
            if len(groups) == 3:  # HH:MM AM/PM
                h, mn, ampm = int(groups[0]), int(groups[1]), groups[2].lower()
                if ampm == "pm" and h < 12:
                    h += 12
                elif ampm == "am" and h == 12:
                    h = 0
                return f"{h:02d}:{mn:02d}"
            elif len(groups) == 2:
                if groups[1].lower() in ("am", "pm"):  # H AM/PM
                    h = int(groups[0])
                    if groups[1].lower() == "pm" and h < 12:
                        h += 12
                    elif groups[1].lower() == "am" and h == 12:
                        h = 0
                    return f"{h:02d}:00"
                else:  # HH:MM 24h
                    return f"{int(groups[0]):02d}:{int(groups[1]):02d}"
            elif len(groups) == 1:  # "at 3"
                h = int(groups[0])
                # Assume PM for business hours
                if 1 <= h <= 6:
                    h += 12
                return f"{h:02d}:00"
    return None


def ghl_create_appointment(contact_ghl_id: str, scheduled_for: str, title: str) -> bool:
    """Create an appointment in GHL for the rescheduled call."""
    if not GHL_API_KEY or not contact_ghl_id:
        return False
    try:
        # Parse the scheduled_for into start/end times
        start = datetime.fromisoformat(scheduled_for.replace("+00:00", ""))
        end = start + timedelta(hours=1)

        resp = requests.post(
            f"https://rest.gohighlevel.com/v1/appointments/",
            headers={"Authorization": f"Bearer {GHL_API_KEY}"},
            json={
                "calendarId": GHL_CALENDAR_ID,
                "contactId": contact_ghl_id,
                "startTime": start.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "endTime": end.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "title": title,
                "appointmentStatus": "confirmed",
            },
            timeout=TIMEOUT,
        )
        if resp.status_code in (200, 201):
            log(f"  GHL appointment created for {contact_ghl_id}")
            return True
        log(f"  GHL appointment failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        log(f"  GHL appointment error: {e}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Sync EOC reschedules to sales_calls_booked")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't create bookings")
    parser.add_argument("--hours", type=int, default=48, help="Look back N hours for EOC reports (default: 48)")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        log("ERROR: Missing SUPABASE_URL or SERVICE_ROLE_KEY")
        sys.exit(1)

    # 1. Get recent showed_not_closed EOC reports
    since = (datetime.now() - timedelta(hours=args.hours)).strftime("%Y-%m-%d")
    eoc_reports = supabase_get("eoc_reports", {
        "outcome": "eq.showed_not_closed",
        "report_date": f"gte.{since}",
        "select": "id,contact_id,team_member_id,offer,report_date,notes",
    })

    if not eoc_reports:
        log(f"No showed_not_closed EOC reports since {since}")
        return

    log(f"Found {len(eoc_reports)} showed_not_closed EOC reports since {since}")

    # 2. Get existing sales_calls_booked to check for duplicates
    existing_bookings = supabase_get("sales_calls_booked", {
        "scheduled_for": f"gte.{since}T00:00:00",
        "select": "contact_id,scheduled_for,status",
    })
    existing_contacts = set()
    for b in existing_bookings:
        cid = b.get("contact_id")
        if cid:
            existing_contacts.add(cid)

    # 3. Get contact details for name resolution + GHL IDs
    contact_ids = [e["contact_id"] for e in eoc_reports if e.get("contact_id")]
    contacts_map = {}
    if contact_ids:
        id_filter = "in.(" + ",".join(contact_ids) + ")"
        contacts = supabase_get("contacts", {
            "id": id_filter,
            "select": "id,full_name,ghl_contact_id",
            "organization_id": None,  # contacts may not have org filter
        })
        # If org filter caused empty, try without
        if not contacts:
            contacts = supabase_get("contacts", {
                "id": id_filter,
                "select": "id,full_name,ghl_contact_id",
            })
        contacts_map = {c["id"]: c for c in contacts}

    # 4. Get team member names
    member_ids = list({e["team_member_id"] for e in eoc_reports if e.get("team_member_id")})
    members_map = {}
    if member_ids:
        members = supabase_get("team_members", {
            "id": f"in.({','.join(member_ids)})",
            "select": "id,full_name",
        })
        members_map = {m["id"]: m.get("full_name", "Unknown") for m in members}

    # 5. Process each EOC report
    created = 0
    skipped = 0
    for eoc in eoc_reports:
        contact_id = eoc.get("contact_id")
        if not contact_id:
            continue

        # Skip if already has a booking
        if contact_id in existing_contacts:
            contact_name = contacts_map.get(contact_id, {}).get("full_name", "Unknown")
            log(f"  SKIP {contact_name} — already has booking after {eoc['report_date']}")
            skipped += 1
            continue

        # Parse time from notes, default to 12:00 PM
        parsed_time = parse_time_from_notes(eoc.get("notes", ""))
        time_str = parsed_time or "12:00"

        # Schedule for the day after the EOC report
        report_date = datetime.strptime(eoc["report_date"], "%Y-%m-%d")
        scheduled_date = report_date + timedelta(days=1)
        scheduled_for = f"{scheduled_date.strftime('%Y-%m-%d')}T{time_str}:00+00:00"

        contact_info = contacts_map.get(contact_id, {})
        contact_name = contact_info.get("full_name", "Unknown")
        closer_name = members_map.get(eoc.get("team_member_id", ""), "Unknown")

        log(f"  {'DRY RUN' if args.dry_run else 'CREATE'} booking: {contact_name} @ {scheduled_for} "
            f"(closer: {closer_name}, offer: {eoc.get('offer', 'N/A')})")

        if args.dry_run:
            created += 1
            continue

        # Create the booking
        booking = {
            "contact_id": contact_id,
            "scheduled_for": scheduled_for,
            "offer": eoc.get("offer", "coaching"),
            "closer_id": eoc.get("team_member_id"),
            "status": "scheduled",
            "source": "eoc_reschedule",
        }
        if ORG_ID:
            booking["organization_id"] = ORG_ID

        if supabase_insert("sales_calls_booked", booking):
            created += 1
            existing_contacts.add(contact_id)  # Prevent duplicates in same run

            # Try to sync to GHL
            ghl_id = contact_info.get("ghl_contact_id")
            if ghl_id:
                ghl_create_appointment(ghl_id, scheduled_for,
                                       f"Reschedule: {contact_name} & {closer_name}")
        else:
            log(f"  FAILED to create booking for {contact_name}")

    log(f"Done: {created} created, {skipped} skipped (already booked)")


if __name__ == "__main__":
    main()
