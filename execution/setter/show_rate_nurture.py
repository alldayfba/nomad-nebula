"""
Show rate nurture — 11-touchpoint post-booking system.

After a call is booked, fires a sequence of DM touchpoints to maximize show rate.
GHL handles email touchpoints (1, 2, 4, 6, 7). The setter handles DM touchpoints (3, 5, 8, 9, 10, 11).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List

from . import setter_db as db
from .setter_config import OFFERS
from .ig_browser import IGBrowserSync

logger = logging.getLogger("setter.showrate")

# Touchpoints handled by the setter (DM-based)
# GHL handles: #1 (confirm email), #2 (training video email), #4 (24h email), #6 (12h email), #7 (2h email)
DM_TOUCHPOINTS = [
    {
        "number": 3,
        "trigger": "immediate",   # Right after booking
        "offset_hours": 0,
        "template": "Booked! {closer} will take great care of you. They're great at what they do — you're in good hands 🤝",
    },
    {
        "number": 5,
        "trigger": "24h_before",
        "offset_hours": -24,
        "template": "Hey — still good for tomorrow at {time}? Looking forward to connecting you with {closer}",
    },
    {
        "number": 8,
        "trigger": "morning_of",
        "offset_hours": -4,       # 4 hours before (morning)
        "template": "Hey — just confirming {time} today. {closer} is prepped and ready for you. See you there!",
    },
    {
        "number": 9,
        "trigger": "30min_before",
        "offset_hours": -0.5,
        "template": "Almost time! Here's the link: {zoom_link}\n\nSee you in 30 🔥",
    },
    {
        "number": 10,
        "trigger": "no_show_1h",
        "offset_hours": 1,        # 1 hour after scheduled time
        "template": "Hey — looks like we might have missed each other. Want to rebook? No worries if the timing was off",
    },
    {
        "number": 11,
        "trigger": "no_show_24h",
        "offset_hours": 24,       # 24 hours after scheduled time
        "template": "Hey — just following up from yesterday. Life gets busy, totally get it. If you still want to chat with {closer}, here's the link to rebook: {calendar_url}",
    },
]


def execute_show_rate_touchpoints(browser: IGBrowserSync) -> Dict:
    """Execute due show rate touchpoints for all booked conversations.

    Returns: {sent: int, errors: int}
    """
    stats = {"sent": 0, "errors": 0}

    booked = db.get_booked_conversations()
    now = datetime.now()

    for conv in booked:
        if not conv.get("booking_datetime"):
            continue

        try:
            booking_dt = datetime.strptime(conv["booking_datetime"], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            try:
                booking_dt = datetime.strptime(conv["booking_datetime"][:19], "%Y-%m-%dT%H:%M:%S")
            except (ValueError, TypeError):
                continue

        offer = OFFERS.get(conv.get("offer", "amazon_os"), OFFERS["amazon_os"])
        thread_id = conv.get("ig_thread_id")
        if not thread_id:
            continue

        # Get already-sent touchpoint numbers for this conversation
        messages = db.get_messages(conv["id"])
        sent_touchpoints = set()
        for msg in messages:
            if msg["direction"] == "out" and msg.get("message_type") == "show_rate":
                # We tag show rate messages in their content
                sent_touchpoints.add(msg.get("content", ""))

        for tp in DM_TOUCHPOINTS:
            # Calculate when this touchpoint should fire
            if tp["trigger"] == "immediate":
                fire_at = booking_dt  # Fire right when booked
                # But only if booked recently (within 1 hour)
                if (now - booking_dt).total_seconds() > 3600:
                    # Check if we already sent it
                    if any("Booked!" in m.get("content", "") for m in messages if m["direction"] == "out"):
                        continue
                    # If booking just happened (within 1h), send immediately
                    if (now - booking_dt).total_seconds() > 3600:
                        continue
            elif tp["offset_hours"] < 0:
                # Before the call
                fire_at = booking_dt + timedelta(hours=tp["offset_hours"])
            else:
                # After the call (no-show follow-ups)
                fire_at = booking_dt + timedelta(hours=tp["offset_hours"])
                # Only send no-show messages if they actually no-showed
                if tp["trigger"].startswith("no_show") and conv["stage"] != "no_show":
                    continue

            # Check if it's time to fire
            if now < fire_at:
                continue

            # Check if already sent (by touchpoint number tag)
            tag = f"[TP{tp['number']}]"
            if any(tag in m.get("content", "") for m in messages if m["direction"] == "out"):
                continue

            # Build the message
            closer = offer["closer_names"][0] if offer["closer_names"] else "our team"
            cal_url = offer.get("calendar_url", "")
            time_str = booking_dt.strftime("%I:%M %p")

            message = tp["template"].format(
                closer=closer,
                time=time_str,
                calendar_url=cal_url,
                zoom_link=os.getenv("ZOOM_LINK", cal_url),
            )

            # Send
            try:
                send_result = browser.send_dm(thread_id, message)
                if send_result["success"]:
                    # Store with tag for dedup
                    db.add_message(
                        conversation_id=conv["id"],
                        direction="out",
                        content=f"{tag} {message}",
                        message_type="show_rate",
                    )
                    db.increment_send_count("dm_total")
                    stats["sent"] += 1
                    logger.info("Show rate TP%d sent for conv %d (@%s)",
                                tp["number"], conv["id"], conv.get("ig_handle", "?"))
                else:
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error("Show rate TP%d error: %s", tp["number"], e)

    return stats
