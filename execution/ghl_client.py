#!/usr/bin/env python3
"""
GHL Contact API Client — create/update contacts and manage tags.

Used by webhook handlers (ghl_automations.py) to replace Zapier's
GHL integration steps.

Usage:
    from execution.ghl_client import create_or_update_contact, add_tags

    result = create_or_update_contact(
        email="test@example.com",
        first_name="John",
        phone="+15551234567",
        tags=["webinar-opt-in"],
        custom_fields={"capital": "$5K-10K"},
        pipeline_id="sFxWPIwC0fTGZBNRO0Lf",
        stage_id="a2018e4a-e6eb-4fc4-a6f0-e5f4167be189",
    )
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger("ghl-client")

GHL_BASE = "https://rest.gohighlevel.com/v1"
TIMEOUT = 15


def _get_api_key() -> str:
    key = os.environ.get("GHL_API_KEY", "")
    if not key:
        raise ValueError("GHL_API_KEY not set in .env")
    return key


def _request(method: str, path: str, data: Optional[dict] = None) -> dict:
    """Make an authenticated request to GHL v1 API.

    Uses curl under the hood — GHL rejects Python urllib's User-Agent with 403.
    """
    url = f"{GHL_BASE}{path}"
    cmd = [
        "curl", "-s", "-X", method, url,
        "-H", f"Authorization: Bearer {_get_api_key()}",
        "-H", "Content-Type: application/json",
    ]
    if data:
        cmd.extend(["-d", json.dumps(data)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        if not result.stdout.strip():
            logger.error("GHL %s %s: empty response", method, path)
            return {"error": True, "status": 0, "message": "empty response"}
        parsed = json.loads(result.stdout)
        # GHL returns error objects like {"error": "...", "statusCode": 403}
        if isinstance(parsed, dict) and parsed.get("statusCode", 0) >= 400:
            logger.error("GHL %s %s: %s — %s", method, path,
                         parsed.get("statusCode"), parsed.get("error", "")[:200])
            return {"error": True, "status": parsed.get("statusCode"),
                    "message": parsed.get("error", "")[:200]}
        return parsed
    except subprocess.TimeoutExpired:
        logger.error("GHL %s %s: timeout after %ds", method, path, TIMEOUT)
        return {"error": True, "status": 0, "message": "timeout"}
    except (json.JSONDecodeError, Exception) as e:
        logger.error("GHL %s %s: %s", method, path, str(e)[:200])
        return {"error": True, "status": 0, "message": str(e)[:200]}


def lookup_contact(email: str) -> Optional[dict]:
    """Find a contact by email. Returns contact dict or None."""
    from urllib.parse import quote
    result = _request("GET", f"/contacts/lookup?email={quote(email)}")
    contacts = result.get("contacts", [])
    return contacts[0] if contacts else None


def create_or_update_contact(
    email: str,
    first_name: str = "",
    last_name: str = "",
    phone: str = "",
    tags: Optional[list] = None,
    custom_fields: Optional[dict] = None,
    pipeline_id: str = "",
    stage_id: str = "",
    source: str = "",
) -> dict:
    """Create a new GHL contact or update existing (dedup by email).

    Returns: {"ok": True, "contact_id": "...", "created": True/False}
    """
    existing = lookup_contact(email)

    payload = {}
    if email:
        payload["email"] = email
    if first_name:
        payload["firstName"] = first_name
    if last_name:
        payload["lastName"] = last_name
    if phone:
        payload["phone"] = phone
    if source:
        payload["source"] = source
    if tags:
        payload["tags"] = tags

    # Map custom fields to GHL customField format
    if custom_fields:
        payload["customField"] = custom_fields

    if existing:
        contact_id = existing["id"]
        result = _request("PUT", f"/contacts/{contact_id}", payload)
        logger.info(f"[ghl] Updated contact {contact_id} ({email})")
        ok = not result.get("error")
    else:
        result = _request("POST", "/contacts/", payload)
        contact_id = result.get("contact", {}).get("id", "")
        logger.info(f"[ghl] Created contact {contact_id} ({email})")
        ok = bool(contact_id)

    # Create opportunity in pipeline if specified
    if ok and pipeline_id and stage_id and contact_id:
        opp_payload = {
            "pipelineId": pipeline_id,
            "pipelineStageId": stage_id,
            "contactId": contact_id,
            "name": f"{first_name} {last_name}".strip() or email,
            "status": "open",
        }
        _request("POST", "/pipelines/opportunities", opp_payload)
        logger.info(f"[ghl] Created opportunity for {contact_id} in pipeline {pipeline_id}")

    return {
        "ok": ok,
        "contact_id": contact_id,
        "created": not bool(existing),
    }


def add_tags(contact_id: str, tags: list) -> bool:
    """Add tags to an existing contact."""
    result = _request("PUT", f"/contacts/{contact_id}", {"tags": tags})
    return not result.get("error", False)


# ── Calendar / Appointments ────────────────────────────────────────────────


def get_calendar_slots(
    calendar_id: str,
    start_date: str,
    end_date: str,
    timezone: str = "America/New_York",
) -> list:
    """Get available time slots from a GHL calendar.

    Args:
        calendar_id: GHL calendar ID
        start_date: ISO date string (YYYY-MM-DD)
        end_date: ISO date string (YYYY-MM-DD)
        timezone: IANA timezone

    Returns: list of ISO datetime strings for available slots
    """
    from datetime import datetime as _dt

    # GHL v1 /appointments/slots requires epoch milliseconds, not date strings
    start_epoch = int(_dt.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_epoch = int(_dt.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

    from urllib.parse import quote
    params = (
        f"?calendarId={calendar_id}"
        f"&startDate={start_epoch}"
        f"&endDate={end_epoch}"
        f"&timezone={quote(timezone)}"
    )
    result = _request("GET", f"/appointments/slots{params}")
    if result.get("error"):
        logger.error("[ghl] Failed to fetch calendar slots: %s", result.get("message"))
        return []

    # GHL returns: {"YYYY-MM-DD": {"slots": ["2026-04-04T09:00:00-04:00", ...]}}
    slots = []
    for date_key, date_data in sorted(result.items()):
        if date_key in ("error", "status", "message"):
            continue
        if isinstance(date_data, dict) and "slots" in date_data:
            slots.extend(date_data["slots"])
        elif isinstance(date_data, list):
            for entry in date_data:
                if isinstance(entry, dict) and "slots" in entry:
                    slots.extend(entry["slots"])
                elif isinstance(entry, str):
                    slots.append(entry)
    return slots


def get_next_available_slot(
    calendar_id: str,
    buffer_hours: int = 2,
    timezone: str = "America/New_York",
) -> Optional[str]:
    """Find the next available slot at least buffer_hours from now.

    Returns: ISO datetime string of the next slot, or None if nothing available.
    """
    from datetime import datetime, timedelta
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    earliest = now + timedelta(hours=buffer_hours)

    # Search next 7 days
    start_date = now.strftime("%Y-%m-%d")
    end_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")

    slots = get_calendar_slots(calendar_id, start_date, end_date, timezone)
    if not slots:
        return None

    for slot in slots:
        try:
            # GHL returns ISO strings like "2026-04-04T09:00:00-04:00"
            slot_dt = datetime.fromisoformat(slot)
            if slot_dt.tzinfo is None:
                slot_dt = slot_dt.replace(tzinfo=tz)
            if slot_dt >= earliest:
                return slot
        except (ValueError, TypeError):
            continue

    return None


def create_appointment(
    calendar_id: str,
    contact_id: str,
    start_time: str,
    title: str = "Discovery Call",
    duration_minutes: int = 30,
) -> dict:
    """Book an appointment on a GHL calendar.

    If the selected slot is taken, automatically tries the next available slot
    (up to 5 attempts).

    Args:
        calendar_id: GHL calendar ID
        contact_id: GHL contact ID
        start_time: ISO datetime string for the slot start
        title: Appointment title
        duration_minutes: Duration in minutes

    Returns: appointment dict with 'id' on success, or error dict
    """
    from datetime import datetime, timedelta

    try:
        start_dt = datetime.fromisoformat(start_time)
    except (ValueError, TypeError) as e:
        logger.error("[ghl] Invalid start_time '%s': %s", start_time, e)
        return {"error": True, "message": str(e)}

    # Get all available slots so we can retry if first choice is taken
    today = start_dt.strftime("%Y-%m-%d")
    end_date = (start_dt + timedelta(days=7)).strftime("%Y-%m-%d")
    all_slots = get_calendar_slots(calendar_id, today, end_date)

    # Filter to slots at or after the requested time
    candidate_slots = []
    for s in all_slots:
        try:
            s_dt = datetime.fromisoformat(s)
            if s_dt >= start_dt:
                candidate_slots.append(s)
        except (ValueError, TypeError):
            continue

    if not candidate_slots:
        candidate_slots = [start_time]

    # Try up to 5 slots
    for slot in candidate_slots[:5]:
        try:
            s_dt = datetime.fromisoformat(slot)
            e_dt = s_dt + timedelta(minutes=duration_minutes)
        except (ValueError, TypeError):
            continue

        payload = {
            "calendarId": calendar_id,
            "contactId": contact_id,
            "startTime": s_dt.isoformat(),
            "endTime": e_dt.isoformat(),
            "selectedTimezone": "America/New_York",
            "selectedSlot": s_dt.isoformat(),
            "title": title,
            "appointmentStatus": "confirmed",
        }

        result = _request("POST", "/appointments/", payload)

        # Success — has an appointment ID
        if result.get("id"):
            logger.info("[ghl] Appointment created: %s at %s for contact %s (id=%s)",
                         title, slot, contact_id, result["id"])
            return result

        # Slot taken — try next one
        slot_err = result.get("selectedSlot", {})
        if isinstance(slot_err, dict) and "no longer available" in slot_err.get("message", ""):
            logger.info("[ghl] Slot %s taken, trying next...", slot)
            continue

        # Other error — stop retrying
        logger.error("[ghl] Failed to create appointment: %s", str(result)[:200])
        return {"error": True, "message": str(result)[:200]}

    logger.error("[ghl] All slots taken for %s", contact_id)
    return {"error": True, "message": "All attempted slots were taken"}
