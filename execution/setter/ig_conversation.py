"""
Conversation state machine — manages the lifecycle of every DM thread.

Core loop: read inbox → match to conversation → generate response → send.
Handles stage transitions, qualification tracking, GHL integration, and escalation.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .setter_config import (
    BOOKING,
    OFFERS,
    RATE_LIMITS,
    REPLY_DELAY,
    SAFETY,
)
from . import setter_db as db
from .setter_brain import generate_response, generate_opener
from .ig_browser import IGBrowserSync
from .followup_engine import schedule_follow_ups, cancel_follow_ups_for_conversation
from .heat_scorer import calculate_heat_score

logger = logging.getLogger("setter.conversation")


# ── GHL Integration ──────────────────────────────────────────────────────────

def _create_ghl_contact(prospect: Dict, offer_key: str) -> Optional[str]:
    """Create/update contact in GHL when prospect is qualified."""
    try:
        from execution.ghl_client import create_or_update_contact, add_tags

        offer = OFFERS.get(offer_key, OFFERS["amazon_os"])
        contact_data = {
            "firstName": prospect.get("full_name", "").split()[0] if prospect.get("full_name") else "",
            "lastName": " ".join(prospect.get("full_name", "").split()[1:]) if prospect.get("full_name") else "",
            "source": "ig-ai-setter",
            "tags": offer.get("tags", []),
        }
        if prospect.get("email_from_bio"):
            contact_data["email"] = prospect["email_from_bio"]
        if prospect.get("website"):
            contact_data["website"] = prospect["website"]

        result = create_or_update_contact(**contact_data)
        contact_id = result.get("contact_id") if result else None
        if contact_id:
            add_tags(contact_id, offer.get("tags", []))
            logger.info("GHL contact created: %s for @%s", contact_id, prospect.get("ig_handle"))
        return contact_id
    except Exception as e:
        logger.error("GHL contact creation failed: %s", e)
        return None


def _send_discord_alert(message: str, webhook_type: str = "setter"):
    """Send a Discord notification."""
    try:
        from execution.ghl_automations import discord_send
        webhook = os.getenv("DISCORD_SETTER_WEBHOOK") or os.getenv("DISCORD_WEBHOOK_URL")
        if webhook:
            discord_send(webhook, message)
    except Exception as e:
        logger.error("Discord alert failed: %s", e)


# ── Rate Limit Check ─────────────────────────────────────────────────────────

def _can_send(channel: str = "dm_total") -> bool:
    """Check if we can send another DM based on rate limits."""
    # Check pause file
    if Path(SAFETY["pause_file"]).exists():
        logger.warning("Setter is PAUSED (pause file exists)")
        return False

    # Check daily total
    total = db.get_send_count("dm_total")
    if total >= RATE_LIMITS["dm_daily_max"]:
        logger.info("Daily DM limit reached: %d/%d", total, RATE_LIMITS["dm_daily_max"])
        return False

    # Check specific channel
    count = db.get_send_count(channel)
    max_for_channel = RATE_LIMITS.get(f"{channel}_max", RATE_LIMITS["dm_daily_max"])
    if count >= max_for_channel:
        logger.info("Channel %s limit reached: %d/%d", channel, count, max_for_channel)
        return False

    # Check cooldown
    last_send = db.get_last_send_time("dm_total")
    if last_send:
        elapsed = (datetime.now() - datetime.strptime(last_send, "%Y-%m-%d %H:%M:%S")).total_seconds()
        if elapsed < RATE_LIMITS["dm_cooldown_min"]:
            return False

    # Check ramp-up (first 7 days)
    ramp_day = db.get_ramp_day()
    if ramp_day <= RATE_LIMITS.get("ramp_up_days", 7):
        ramp_limit = RATE_LIMITS["ramp_up"].get(ramp_day, RATE_LIMITS["dm_daily_max"])
        if total >= ramp_limit:
            logger.info("Ramp-up day %d limit reached: %d/%d", ramp_day, total, ramp_limit)
            return False

    return True


def _est_hour() -> int:
    """Get current hour in EST (Miami)."""
    from datetime import timezone, timedelta as _td
    return datetime.now(timezone(_td(hours=-5))).hour


def _is_night_mode() -> bool:
    """Check if we're in night mode (no outbound). Uses EST."""
    hour = _est_hour()
    return RATE_LIMITS["night_start_hour"] <= hour < RATE_LIMITS["night_end_hour"]


def _too_many_unanswered(conversation_id: int) -> bool:
    """Check if we've sent too many consecutive messages without a reply.

    Returns True if we should stop messaging and move to nurture.
    """
    messages = db.get_messages(conversation_id, limit=20)
    if not messages:
        return False
    # Count consecutive outbound from the end
    consecutive_out = 0
    for msg in reversed(messages):
        if msg["direction"] == "out":
            consecutive_out += 1
        else:
            break
    return consecutive_out >= SAFETY["max_unanswered_messages"]


def _needs_approval(conversation_id: int) -> bool:
    """Check if this conversation still needs human approval gate."""
    # Count total conversations with auto-approved messages
    d = db.get_db()
    row = d.execute(
        """SELECT COUNT(DISTINCT conversation_id) as cnt FROM messages
           WHERE approval_status = 'approved' AND direction = 'out'"""
    ).fetchone()
    approved_count = row["cnt"] if row else 0
    return approved_count < SAFETY["approval_gate_count"]


# ── Booking Info Detection ──────────────────────────────────────────────────

def _check_booking_info(conv: Dict, prospect: Dict, recent_messages: List[Dict]):
    """Detect when a prospect provides name + email + phone for booking.

    Fires a Discord alert and updates the conversation to 'booked' stage.
    """
    import re as _re

    # Scan ALL inbound messages for contact info (not just this batch —
    # prospect may send name in one message and email+phone in another)
    all_messages = db.get_messages(conv["id"], limit=50)
    inbound_msgs = [m for m in all_messages if m["direction"] == "in"]
    all_text = " ".join(m.get("content", "") for m in inbound_msgs)

    email_match = _re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', all_text)
    phone_match = _re.search(r'[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}', all_text)

    # If we have both email and phone, this is a booking
    if email_match and phone_match:
        email = email_match.group()
        phone = phone_match.group()

        # Try to extract name (usually first thing they say, or from profile)
        name = prospect.get("full_name", "") or prospect.get("ig_handle", "")

        # Update conversation
        db.update_conversation(
            conv["id"],
            stage="booked",
            booking_confirmed=1,
        )

        # Update lead grade to A
        from .lead_grader import grade_conversation
        grade_conversation(conv["id"])

        # Record as winning pattern (the conversation that led to booking)
        messages = db.get_messages(conv["id"])
        if messages:
            opener = next((m["content"] for m in messages if m["direction"] == "out"), "")
            if opener:
                db.record_pattern_success("opener", opener)

        handle = prospect.get("ig_handle", "unknown")
        logger.info("BOOKING DETECTED: @%s — %s / %s / %s", handle, name, email, phone)

        # Create/update GHL contact with booking info
        offer_key = conv.get("offer", "amazon_os")
        offer = OFFERS.get(offer_key, OFFERS["amazon_os"])
        contact_id = None
        try:
            from execution.ghl_client import create_or_update_contact
            result = create_or_update_contact(
                email=email,
                first_name=name.split()[0] if name else "",
                phone=phone,
                tags=["ig-ai-setter", "booked"],
                pipeline_id=offer.get("pipeline_id", ""),
                stage_id=offer.get("stage_id_booked", ""),
                source="ig-ai-setter",
            )
            contact_id = result.get("contact_id")
        except Exception as e:
            logger.error("GHL contact creation for booking failed: %s", e)

        # Auto-book on GHL calendar
        booked_time = None
        calendar_id = BOOKING["calendar_ids"].get(offer_key, "")
        if contact_id and calendar_id:
            try:
                from execution.ghl_client import get_next_available_slot, create_appointment
                slot = get_next_available_slot(
                    calendar_id,
                    buffer_hours=BOOKING["buffer_hours"],
                    timezone=BOOKING["timezone"],
                )
                if slot:
                    appt = create_appointment(
                        calendar_id=calendar_id,
                        contact_id=contact_id,
                        start_time=slot,
                        title=f"Discovery Call — @{handle}",
                        duration_minutes=BOOKING["default_duration"],
                    )
                    if not appt.get("error"):
                        booked_time = slot
                        logger.info("AUTO-BOOKED: @%s at %s", handle, slot)
                    else:
                        logger.warning("Auto-book failed for @%s: %s", handle, appt.get("message"))
                else:
                    logger.warning("No available slots for @%s in next 7 days", handle)
            except Exception as e:
                logger.error("Auto-booking failed for @%s: %s", handle, e)

        # Fire Discord alert
        if booked_time:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(booked_time)
                time_str = dt.strftime("%A %b %d at %I:%M %p %Z")
            except (ValueError, TypeError):
                time_str = booked_time
            alert_msg = (
                f"🔥 **QUALIFIED LEAD AUTO-BOOKED** 🔥\n\n"
                f"**Handle:** @{handle}\n"
                f"**Name:** {name}\n"
                f"**Email:** {email}\n"
                f"**Phone:** {phone}\n"
                f"**Booked:** {time_str}\n"
                f"**Messages exchanged:** {conv.get('messages_sent', 0) + conv.get('messages_received', 0)}\n"
                f"**Source:** {prospect.get('source', 'unknown')}\n\n"
                f"✅ Auto-booked — confirm in GHL."
            )
        else:
            alert_msg = (
                f"🔥 **QUALIFIED LEAD BOOKED** 🔥\n\n"
                f"**Handle:** @{handle}\n"
                f"**Name:** {name}\n"
                f"**Email:** {email}\n"
                f"**Phone:** {phone}\n"
                f"**Messages exchanged:** {conv.get('messages_sent', 0) + conv.get('messages_received', 0)}\n"
                f"**Source:** {prospect.get('source', 'unknown')}\n\n"
                f"⚠️ Could not auto-book — book manually in GHL."
            )
        _send_discord_alert(alert_msg)


# ── Core Processing Loop ────────────────────────────────────────────────────

def process_inbox(browser: IGBrowserSync) -> Dict:
    """Process all unread DM threads.

    1. Read inbox
    2. Match each thread to existing conversation
    3. Store inbound messages
    4. Generate and send responses

    Returns: {processed: int, sent: int, escalated: int, errors: int}
    """
    stats = {"processed": 0, "sent": 0, "escalated": 0, "errors": 0}

    if _is_night_mode():
        logger.info("Night mode — inbox monitoring only")

    threads = browser.read_inbox(max_threads=30)
    unread = [t for t in threads if t.get("unread")]

    # Sort unread: inbound-first (no existing conversation) get priority
    def _inbound_priority(thread):
        thread_id = thread.get("thread_id")
        conv = db.get_conversation_by_thread(thread_id) if thread_id else None
        # No existing conversation = they messaged us first = highest priority
        return 0 if conv is None else 1

    unread = sorted(unread, key=_inbound_priority)

    for thread in unread:
        try:
            thread_id = thread.get("thread_id")
            if not thread_id:
                continue

            stats["processed"] += 1

            # Read full thread history
            thread_messages = browser.read_thread(thread_id)
            if not thread_messages:
                continue

            # Find or create conversation
            conv = db.get_conversation_by_thread(thread_id)

            if not conv:
                # Try to match by handle from thread name
                handle = thread.get("name", "").lstrip("@")

                # Blocklist check for inbound too — don't auto-respond to blocklisted
                if handle and db.is_blocklisted(handle):
                    logger.debug("Skipping inbox thread from @%s — blocklisted", handle)
                    continue

                prospect = db.get_prospect_by_handle(handle) if handle else None

                if not prospect and handle:
                    # New prospect from inbound DM
                    profile = browser.scrape_profile(handle)
                    prospect_id = db.upsert_prospect(
                        ig_handle=handle,
                        source="inbound_dm",
                        **{k: v for k, v in profile.items() if k != "ig_handle"},
                    )
                    prospect = db.get_prospect(prospect_id)

                if prospect:
                    conv_id = db.create_conversation(
                        prospect_id=prospect["id"],
                        offer=prospect.get("offer_match", "amazon_os") or "amazon_os",
                        conversation_type="inbound",
                        ig_thread_id=thread_id,
                        stage="replied",
                    )
                    conv = db.get_conversation(conv_id)
                else:
                    continue
            else:
                # Existing conversation — check blocklist by prospect handle
                _prospect_check = db.get_prospect(conv["prospect_id"])
                if _prospect_check and db.is_blocklisted(_prospect_check.get("ig_handle", "")):
                    logger.debug("Skipping inbox thread from @%s — blocklisted",
                                 _prospect_check.get("ig_handle", ""))
                    continue

            prospect = db.get_prospect(conv["prospect_id"])
            if not prospect:
                continue

            # Store new inbound messages
            existing_msgs = db.get_messages(conv["id"])
            existing_count = len(existing_msgs)

            # Find messages we haven't stored yet
            # Use (content, direction) tuple for dedup — content-only misses direction flips
            existing_keys = {(m["content"], m["direction"]) for m in existing_msgs}
            new_inbound = []
            for msg in thread_messages:
                if msg["direction"] == "in" and (msg.get("content"), "in") not in existing_keys:
                    new_inbound.append(msg)

            for idx, msg in enumerate(new_inbound):
                import hashlib
                msg_hash = hashlib.md5(
                    f"{msg['content']}:{conv['id']}:{idx}".encode()
                ).hexdigest()[:16]
                db.add_message(
                    conversation_id=conv["id"],
                    direction="in",
                    content=msg["content"],
                    message_type=msg.get("message_type", "text"),
                    ig_message_id=f"in_{msg_hash}",
                )

            if not new_inbound:
                continue  # No new inbound messages

            # Cancel pending follow-ups (they replied)
            cancel_follow_ups_for_conversation(conv["id"])

            # Update stage if they just replied to opener
            if conv["stage"] == "opener_sent":
                db.update_conversation(conv["id"], stage="replied")
                conv["stage"] = "replied"
                db.increment_metric("replies_received")
                calculate_heat_score(conv["id"])

            # Check message cap
            if conv["messages_sent"] >= SAFETY["max_messages_before_flag"]:
                db.update_conversation(
                    conv["id"],
                    requires_human=1,
                    human_reason=f"Message cap reached ({conv['messages_sent']} messages, no booking)",
                )
                _send_discord_alert(
                    f"Message cap reached for @{prospect['ig_handle']} "
                    f"({conv['messages_sent']} msgs). Needs human review."
                )
                stats["escalated"] += 1
                continue

            # Night mode — don't respond, just store
            if _is_night_mode():
                continue

            # Check rate limits
            if not _can_send("dm_total"):
                continue

            # Check max unanswered — don't spam if they're not replying
            if _too_many_unanswered(conv["id"]):
                db.update_conversation(conv["id"], stage="nurture")
                calculate_heat_score(conv["id"])
                logger.info("@%s moved to nurture — %d unanswered messages",
                            prospect["ig_handle"], SAFETY["max_unanswered_messages"])
                continue

            # Generate response
            all_messages = db.get_messages(conv["id"])
            brain_result = generate_response(conv, prospect, all_messages, conv["offer"])

            if brain_result["requires_human"]:
                db.update_conversation(
                    conv["id"],
                    requires_human=1,
                    human_reason=brain_result["human_reason"],
                )
                _send_discord_alert(
                    f"Escalation for @{prospect['ig_handle']}: {brain_result['human_reason']}"
                )
                stats["escalated"] += 1
                continue

            if not brain_result["content"]:
                continue

            # Check approval gate
            if _needs_approval(conv["id"]):
                msg_id = db.add_message(
                    conversation_id=conv["id"],
                    direction="out",
                    content=brain_result["content"],
                    claude_model=brain_result["model"],
                    tokens_in=brain_result["tokens_in"],
                    tokens_out=brain_result["tokens_out"],
                    cost_usd=brain_result["cost"],
                    approval_status="pending",
                )
                _send_discord_alert(
                    f"Approval needed for @{prospect['ig_handle']}:\n"
                    f"**Prospect said:** {new_inbound[-1]['content']}\n"
                    f"**AI response:** {brain_result['content']}\n"
                    f"Approve at /setter/approvals"
                )
                continue

            # Human-like reply delay — faster for inbound (they DM'd us first, they're hot)
            import random as _rnd
            if conv.get("conversation_type") == "inbound":
                from .setter_config import REPLY_DELAY_INBOUND
                delay = _rnd.uniform(REPLY_DELAY_INBOUND["min_seconds"], REPLY_DELAY_INBOUND["max_seconds"])
            else:
                delay = _rnd.uniform(REPLY_DELAY["min_seconds"], REPLY_DELAY["max_seconds"])
            logger.info("Waiting %.0fs before replying to @%s...", delay, prospect["ig_handle"])
            time.sleep(delay)

            # Send the DM
            send_result = browser.send_dm(thread_id, brain_result["content"])

            if send_result["success"]:
                db.add_message(
                    conversation_id=conv["id"],
                    direction="out",
                    content=brain_result["content"],
                    claude_model=brain_result["model"],
                    tokens_in=brain_result["tokens_in"],
                    tokens_out=brain_result["tokens_out"],
                    cost_usd=brain_result["cost"],
                    approval_status="auto",
                )
                db.increment_send_count("dm_total")
                db.increment_send_count("dm_inbox")
                db.increment_metric("inbox_replies_sent")

                # Update conversation stage and qualifications
                if brain_result["stage_suggestion"] != conv["stage"]:
                    db.update_conversation(conv["id"], stage=brain_result["stage_suggestion"])

                if brain_result.get("qual_updates"):
                    db.update_conversation(conv["id"], **brain_result["qual_updates"])

                # Update API cost
                new_cost = (conv.get("total_api_cost") or 0) + brain_result["cost"]
                db.update_conversation(conv["id"], total_api_cost=new_cost)

                # Check if qualified → create GHL contact
                updated_conv = db.get_conversation(conv["id"])
                if (updated_conv and updated_conv["stage"] == "qualified"
                        and not updated_conv.get("ghl_contact_id")):
                    ghl_id = _create_ghl_contact(prospect, conv["offer"])
                    if ghl_id:
                        db.update_conversation(conv["id"], ghl_contact_id=ghl_id)

                # Detect booking info (name + email + phone in recent messages)
                # Only check once we're past initial qualifying — prevents false
                # triggers from random email/phone patterns in early openers
                updated_conv = db.get_conversation(conv["id"]) or conv
                if updated_conv["stage"] in ("qualifying", "qualified", "booking"):
                    _check_booking_info(updated_conv, prospect, new_inbound)

                # NOTE: We book manually — no calendar link auto-send.
                # When booking info is detected, Discord alert fires.

                # Recalculate heat score after all updates
                calculate_heat_score(conv["id"])

                stats["sent"] += 1

                # Record pattern for learning
                if conv["stage"] == "new" or conv["stage"] == "opener_sent":
                    db.record_pattern("opener", brain_result["content"], conv["offer"])
                elif conv["stage"] in ("replied", "qualifying"):
                    db.record_pattern("qualifier", brain_result["content"], conv["offer"])

            else:
                # Check for action block
                if browser.check_action_block():
                    _send_discord_alert(
                        "ACTION BLOCK DETECTED. Setter paused for 24h."
                    )
                    # Create pause file
                    Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                    Path(SAFETY["pause_file"]).touch()
                    db.increment_metric("action_blocks")
                    break

                stats["errors"] += 1
                logger.error("Failed to send DM to %s: %s",
                             prospect["ig_handle"], send_result.get("error"))

        except (TimeoutError, Exception) as e:
            stats["errors"] += 1
            logger.error("Error processing thread: %s", e, exc_info=True)
            # On timeout or crash, check if IG action-blocked us
            if isinstance(e, TimeoutError) or "timeout" in str(e).lower():
                try:
                    if browser.check_action_block():
                        _send_discord_alert("ACTION BLOCK DETECTED (timeout). Setter paused for 24h.")
                        Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                        Path(SAFETY["pause_file"]).touch()
                        db.increment_metric("action_blocks")
                        break
                except Exception:
                    pass

    return stats


# ── Send Approved Messages ────────────────────────────────────────────────

def send_approved_messages(browser: IGBrowserSync) -> Dict:
    """Send messages that were approved via the dashboard but not yet delivered.

    The approval gate stores messages as 'pending'. After Sabbo approves them,
    this function picks them up and actually sends the DM.

    Returns: {sent: int, errors: int}
    """
    stats = {"sent": 0, "errors": 0}

    d = db.get_db()
    rows = d.execute(
        """SELECT m.id, m.conversation_id, m.content,
                  c.ig_thread_id, c.stage, c.offer, c.prospect_id,
                  p.ig_handle
           FROM messages m
           JOIN conversations c ON m.conversation_id = c.id
           JOIN prospects p ON c.prospect_id = p.id
           WHERE m.approval_status = 'approved'
             AND m.direction = 'out'
             AND m.ig_message_id IS NULL
           ORDER BY m.sent_at ASC"""
    ).fetchall()

    if not rows:
        return stats

    logger.info("Sending %d approved messages...", len(rows))

    for row in rows:
        row = dict(row)
        thread_id = row.get("ig_thread_id") or row["ig_handle"]

        if not _can_send("dm_total"):
            logger.info("Rate limit reached, stopping approved sends")
            break

        try:
            # Human-like delay
            import random as _rnd
            delay = _rnd.uniform(REPLY_DELAY["min_seconds"], REPLY_DELAY["max_seconds"])
            time.sleep(delay)

            send_result = browser.send_dm(thread_id, row["content"])

            if send_result["success"]:
                # Mark as sent by storing the thread_id as ig_message_id
                d.execute(
                    "UPDATE messages SET ig_message_id = ? WHERE id = ?",
                    (send_result.get("thread_id", "sent"), row["id"]),
                )
                d.commit()
                db.increment_send_count("dm_total")
                db.increment_send_count("dm_inbox")
                stats["sent"] += 1
                logger.info("Approved message sent to @%s", row["ig_handle"])

                # Update thread_id on conversation if we didn't have one
                if not row.get("ig_thread_id") and send_result.get("thread_id"):
                    db.update_conversation(
                        row["conversation_id"],
                        ig_thread_id=send_result["thread_id"],
                    )
            else:
                stats["errors"] += 1
                logger.error("Failed to send approved message to @%s: %s",
                             row["ig_handle"], send_result.get("error"))

                # Check for action block
                if browser.check_action_block():
                    _send_discord_alert("ACTION BLOCK during approved send. Paused 24h.")
                    Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                    Path(SAFETY["pause_file"]).touch()
                    break

        except (TimeoutError, Exception) as e:
            stats["errors"] += 1
            logger.error("Error sending approved message: %s", e)
            if isinstance(e, TimeoutError) or "timeout" in str(e).lower():
                try:
                    if browser.check_action_block():
                        _send_discord_alert("ACTION BLOCK (timeout) during approved send. Paused 24h.")
                        Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                        Path(SAFETY["pause_file"]).touch()
                        break
                except Exception:
                    pass

    return stats


# ── Cold Outbound Batch ──────────────────────────────────────────────────────

def send_cold_outbound_batch(browser: IGBrowserSync, max_count: int = 50) -> Dict:
    """Send personalized openers to qualified prospects.

    Returns: {sent: int, skipped: int, errors: int}
    """
    stats = {"sent": 0, "skipped": 0, "errors": 0}

    if _is_night_mode():
        return stats

    prospects = db.get_qualified_prospects_for_outbound(limit=max_count)
    logger.info("Cold outbound batch: %d qualified prospects", len(prospects))

    for prospect in prospects:
        if not _can_send("dm_cold"):
            logger.info("Cold DM limit reached, stopping batch")
            break

        try:
            # Blocklist check
            if db.is_blocklisted(prospect.get("ig_handle", "")):
                logger.debug("Skipping @%s — blocklisted", prospect.get("ig_handle"))
                stats["skipped"] += 1
                continue

            # Skip if already has active conversation
            existing = db.get_conversation_by_prospect(prospect["id"])
            if existing:
                stats["skipped"] += 1
                continue

            # Generate opener
            offer_key = prospect.get("offer_match", "amazon_os")
            if offer_key in ("none", "both"):
                offer_key = "amazon_os"  # Default

            opener = generate_opener(prospect, offer_key)
            if not opener["content"]:
                stats["errors"] += 1
                continue

            # Create conversation record
            conv_id = db.create_conversation(
                prospect_id=prospect["id"],
                offer=offer_key,
                conversation_type="cold_outbound",
                stage="new",
                opener_type="cold",
            )

            # Check approval gate
            if _needs_approval(conv_id):
                db.add_message(
                    conversation_id=conv_id,
                    direction="out",
                    content=opener["content"],
                    claude_model=opener["model"],
                    tokens_in=opener["tokens_in"],
                    tokens_out=opener["tokens_out"],
                    cost_usd=opener["cost"],
                    approval_status="pending",
                )
                db.update_conversation(conv_id, stage="opener_sent")
                db.update_prospect_status(prospect["id"], "contacted")
                _send_discord_alert(
                    f"Approval needed — cold opener for @{prospect['ig_handle']}:\n"
                    f"**AI opener:** {opener['content']}"
                )
                continue

            # Send the DM
            import random
            cooldown = random.uniform(
                RATE_LIMITS["dm_cooldown_min"],
                RATE_LIMITS["dm_cooldown_max"],
            )
            time.sleep(cooldown)

            # SAFETY: Check for existing IG thread BEFORE sending.
            # If Sabbo DMd this person manually before the setter existed,
            # there's no DB record but there IS an IG thread. Never send
            # a cold opener to someone already spoken to.
            if browser.check_existing_thread(prospect["ig_handle"]):
                logger.info("@%s has existing IG thread — skipping cold opener",
                            prospect["ig_handle"])
                db.update_conversation(
                    conv_id,
                    stage="replied",  # Treat as existing conversation
                    requires_human=1,
                    human_reason="Existing IG thread found — needs context review before AI responds",
                )
                db.update_prospect_status(prospect["id"], "contacted")
                stats["skipped"] += 1
                continue

            send_result = browser.send_dm(prospect["ig_handle"], opener["content"])

            if send_result["success"]:
                thread_id = send_result.get("thread_id", "")
                db.update_conversation(
                    conv_id,
                    stage="opener_sent",
                    ig_thread_id=thread_id,
                    total_api_cost=opener["cost"],
                )
                db.add_message(
                    conversation_id=conv_id,
                    direction="out",
                    content=opener["content"],
                    claude_model=opener["model"],
                    tokens_in=opener["tokens_in"],
                    tokens_out=opener["tokens_out"],
                    cost_usd=opener["cost"],
                    approval_status="auto",
                )
                db.update_prospect_status(prospect["id"], "contacted")
                db.increment_send_count("dm_cold")
                db.increment_send_count("dm_total")
                db.increment_metric("cold_dms_sent")

                # Schedule follow-ups
                schedule_follow_ups(conv_id)

                # Record pattern
                db.record_pattern("opener", opener["content"], offer_key)

                # Calculate initial heat score
                calculate_heat_score(conv_id)

                stats["sent"] += 1
                logger.info("Cold opener sent to @%s", prospect["ig_handle"])
            else:
                stats["errors"] += 1
                if browser.check_action_block():
                    _send_discord_alert("ACTION BLOCK during cold outbound. Pausing.")
                    Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                    Path(SAFETY["pause_file"]).touch()
                    break

        except (TimeoutError, Exception) as e:
            stats["errors"] += 1
            logger.error("Error in cold outbound for @%s: %s",
                         prospect.get("ig_handle"), e, exc_info=True)
            if isinstance(e, TimeoutError) or "timeout" in str(e).lower():
                try:
                    if browser.check_action_block():
                        _send_discord_alert("ACTION BLOCK (timeout) during cold outbound. Paused 24h.")
                        Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                        Path(SAFETY["pause_file"]).touch()
                        break
                except Exception:
                    pass

    return stats


# ── Warm Outbound Batch ──────────────────────────────────────────────────────

def send_warm_outbound_batch(browser: IGBrowserSync, max_count: int = 50) -> Dict:
    """Send DMs to warm leads (story viewers, post likers, engagers).

    Returns: {sent: int, skipped: int, errors: int}
    """
    stats = {"sent": 0, "skipped": 0, "errors": 0}

    if _is_night_mode():
        return stats

    # Get recent engagers from Instagram
    engagers = browser.get_recent_engagers(max_count=max_count * 2)

    for engager in engagers:
        if not _can_send("dm_warm"):
            break

        handle = engager.get("handle")
        if not handle:
            continue

        try:
            # Blocklist check
            if db.is_blocklisted(handle):
                logger.debug("Skipping @%s — blocklisted", handle)
                stats["skipped"] += 1
                continue

            # Check if already a prospect
            prospect = db.get_prospect_by_handle(handle)
            if prospect:
                # Skip if already contacted or in conversation
                if prospect["status"] not in ("new", "qualified"):
                    stats["skipped"] += 1
                    continue
            else:
                # New prospect — scrape and score
                profile = browser.scrape_profile(handle)
                prospect_id = db.upsert_prospect(
                    ig_handle=handle,
                    source=engager.get("action_type", "post_like"),
                    **{k: v for k, v in profile.items() if k != "ig_handle"},
                )
                # Quick ICP check (we'll do full scoring later in prospector)
                prospect = db.get_prospect(prospect_id)

            if not prospect:
                continue

            # Skip low ICP scores if already scored
            if prospect.get("icp_score", 0) > 0 and prospect["icp_score"] < 4:
                stats["skipped"] += 1
                continue

            # Check if already has active conversation
            existing = db.get_conversation_by_prospect(prospect["id"])
            if existing:
                stats["skipped"] += 1
                continue

            # Generate warm opener
            offer_key = prospect.get("offer_match", "amazon_os")
            if offer_key in ("none", "", None):
                offer_key = "amazon_os"

            opener = generate_opener(prospect, offer_key)
            if not opener["content"]:
                continue

            # Create conversation + send
            conv_id = db.create_conversation(
                prospect_id=prospect["id"],
                offer=offer_key,
                conversation_type="warm",
                stage="new",
                opener_type="warm",
            )

            if _needs_approval(conv_id):
                db.add_message(
                    conversation_id=conv_id,
                    direction="out",
                    content=opener["content"],
                    approval_status="pending",
                    claude_model=opener["model"],
                    tokens_in=opener["tokens_in"],
                    tokens_out=opener["tokens_out"],
                    cost_usd=opener["cost"],
                )
                db.update_conversation(conv_id, stage="opener_sent")
                db.update_prospect_status(prospect["id"], "contacted")
                continue

            import random
            time.sleep(random.uniform(
                RATE_LIMITS["dm_cooldown_min"],
                RATE_LIMITS["dm_cooldown_max"],
            ))

            send_result = browser.send_dm(handle, opener["content"])
            if send_result["success"]:
                db.update_conversation(
                    conv_id,
                    stage="opener_sent",
                    ig_thread_id=send_result.get("thread_id", ""),
                    total_api_cost=opener["cost"],
                )
                db.add_message(
                    conversation_id=conv_id,
                    direction="out",
                    content=opener["content"],
                    approval_status="auto",
                    claude_model=opener["model"],
                    tokens_in=opener["tokens_in"],
                    tokens_out=opener["tokens_out"],
                    cost_usd=opener["cost"],
                )
                db.update_prospect_status(prospect["id"], "contacted")
                db.increment_send_count("dm_warm")
                db.increment_send_count("dm_total")
                db.increment_metric("warm_dms_sent")
                schedule_follow_ups(conv_id)
                calculate_heat_score(conv_id)
                stats["sent"] += 1
            else:
                stats["errors"] += 1
                if browser.check_action_block():
                    Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                    Path(SAFETY["pause_file"]).touch()
                    break

        except (TimeoutError, Exception) as e:
            stats["errors"] += 1
            logger.error("Warm outbound error for @%s: %s", handle, e)
            if isinstance(e, TimeoutError) or "timeout" in str(e).lower():
                try:
                    if browser.check_action_block():
                        _send_discord_alert("ACTION BLOCK (timeout) during warm outbound. Paused 24h.")
                        Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                        Path(SAFETY["pause_file"]).touch()
                        break
                except Exception:
                    pass

    return stats
