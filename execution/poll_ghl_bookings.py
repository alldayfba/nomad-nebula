#!/usr/bin/env python3
"""
Poll GHL calendar for new sales call bookings → fire Discord notification instantly.

Runs every 60s via launchd. Queries the round-robin calendar directly,
fetches full contact details for each new appointment, and sends a rich
embed to #call-booked via Discord webhook.

Usage:
  python execution/poll_ghl_bookings.py          # Normal poll
  python execution/poll_ghl_bookings.py --dry-run # Preview without sending
  python execution/poll_ghl_bookings.py --reset   # Clear state, re-poll
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("poll-ghl-bookings")

STATE_FILE = os.path.join(_PROJECT_ROOT, ".tmp", "poll_ghl_bookings_state.json")
GHL_BASE = "https://rest.gohighlevel.com/v1"
CALENDAR_ID = "9fL4lUjdONSbW0oJ419Y"


def _load_env():
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"seen": [], "last_poll": None}


def _save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["last_poll"] = datetime.now(timezone.utc).isoformat()
    state["seen"] = state["seen"][-500:]  # Cap to prevent unbounded growth
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _ghl_get(path: str) -> dict:
    api_key = os.environ.get("GHL_API_KEY", "")
    if not api_key:
        raise ValueError("GHL_API_KEY not set")
    req = urllib.request.Request(f"{GHL_BASE}{path}", method="GET")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())


def _discord_send(embed: dict):
    webhook_url = os.environ.get("DISCORD_CALL_BOOKED_WEBHOOK", "")
    if not webhook_url:
        raise ValueError("DISCORD_CALL_BOOKED_WEBHOOK not set")
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "DiscordBot (nomad-nebula, 1.0)")
    urllib.request.urlopen(req, timeout=10)


def _format_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%B %d, %Y @ %I:%M %p %Z").strip()
    except (ValueError, TypeError):
        return iso_str or "TBD"


def _build_embed(appt: dict) -> dict:
    contact = appt.get("contact", {})
    name = f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip() or "Unknown"
    email = contact.get("email", "")
    phone = contact.get("phone", "")
    source = contact.get("source", "")
    title = appt.get("title", name)  # "Prospect & Closer"
    call_time = _format_time(appt.get("startTime", ""))

    lines = [
        f"\U0001f464 **Prospect & Closer:**  {title}",
        "",
        f"\U0001f4e7 **Email:**  {email}" if email else "",
        f"\U0001f4de **Phone:**  {phone}" if phone else "",
        f"\U0001f4c5 **Call Date:**  {call_time}",
    ]
    if source:
        lines += ["", f"\U0001f4cd **Source:**  {source}"]

    return {
        "title": "\U0001f4de\U0001f3e0 24/7 Profits Sales Call Booked!",
        "description": "\n".join(line for line in lines if line is not None),
        "color": 0x00FF88,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "GHL Calendar \u2192 Discord (auto)"},
    }


def poll(dry_run: bool = False) -> int:
    state = _load_state()
    seen = set(state.get("seen", []))
    sent = 0

    # Query calendar: 24h ago → 30 days ahead
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (24 * 60 * 60 * 1000)
    end_ms = now_ms + (30 * 24 * 60 * 60 * 1000)

    try:
        data = _ghl_get(f"/appointments/?calendarId={CALENDAR_ID}&startDate={start_ms}&endDate={end_ms}")
    except Exception as e:
        logger.error(f"Calendar query failed: {e}")
        return 0

    appts = data.get("appointments", [])
    logger.info(f"Found {len(appts)} appointments on calendar")

    for appt in appts:
        aid = appt.get("id", "")
        if aid in seen:
            continue
        if appt.get("status") not in ("booked", "confirmed"):
            seen.add(aid)
            continue

        # Fetch full details (contact info)
        try:
            full = _ghl_get(f"/appointments/{aid}")
        except Exception as e:
            logger.warning(f"Detail fetch failed for {aid}: {e}")
            continue

        embed = _build_embed(full)
        title = full.get("title", aid)

        if dry_run:
            logger.info(f"[DRY RUN] Would send: {title}")
        else:
            try:
                _discord_send(embed)
                logger.info(f"Sent: {title}")
                sent += 1
            except Exception as e:
                logger.error(f"Discord send failed for {title}: {e}")
                continue

        seen.add(aid)

    state["seen"] = list(seen)
    _save_state(state)
    logger.info(f"Done — {sent} new notification(s)")
    return sent


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Poll GHL calendar → Discord")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    _load_env()

    if args.reset:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        logger.info("State reset")

    poll(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
