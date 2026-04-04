"""
Follow-up engine — Day 1/3/7/14 automated follow-up scheduler and executor.

Schedules follow-ups when openers are sent, cancels them when prospects reply,
and executes due follow-ups through the browser.
"""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List

from .setter_config import DM_SCRIPT, FOLLOW_UP_SEQUENCE, RATE_LIMITS, SAFETY
from . import setter_db as db
from .setter_brain import _claude_cli, _clean_response
from .ig_browser import IGBrowserSync

logger = logging.getLogger("setter.followup")


def _get_timing_multiplier(conversation_id: int) -> float:
    """Get follow-up timing multiplier based on lead grade.

    A/B leads (hot): 0.5x (faster follow-ups)
    C leads (lukewarm): 1.0x (default)
    D/F leads (cold): 2.0x (slower follow-ups)
    """
    try:
        conv = db.get_conversation(conversation_id)
        if conv and conv.get("prospect_id"):
            grade_row = db.get_lead_grade(conv["prospect_id"])
            if grade_row:
                grade = grade_row.get("grade", "C")
                if grade in ("A", "B"):
                    return 0.5
                elif grade in ("D", "F"):
                    return 2.0
    except Exception:
        pass
    return 1.0


def schedule_follow_ups(conversation_id: int):
    """Schedule all follow-ups for a conversation based on the cadence.

    Timing adjusts by lead grade:
      A/B leads: 0.5x delays (faster — hot leads need faster follow-up)
      C leads: 1.0x (default cadence)
      D/F leads: 2.0x delays (slower — don't spam cold leads)
    """
    conv = db.get_conversation(conversation_id)
    if not conv:
        return

    multiplier = _get_timing_multiplier(conversation_id)
    now = datetime.now()
    for step in FOLLOW_UP_SEQUENCE:
        # Support both hour-based and day-based delays
        if "delay_hours" in step:
            adjusted_hours = step["delay_hours"] * multiplier
            scheduled = now + timedelta(hours=adjusted_hours)
        else:
            adjusted_days = step["delay_days"] * multiplier
            scheduled = now + timedelta(days=adjusted_days)
        db.schedule_follow_up(
            conversation_id=conversation_id,
            follow_up_number=step["number"],
            content_type=step["type"],
            scheduled_at=scheduled.strftime("%Y-%m-%d %H:%M:%S"),
            content=step.get("template", "") if step["type"] == "still_with_me" else None,
        )
    logger.info("Scheduled %d follow-ups for conversation %d (multiplier=%.1fx)",
                 len(FOLLOW_UP_SEQUENCE), conversation_id, multiplier)


def cancel_follow_ups_for_conversation(conversation_id: int):
    """Cancel all pending follow-ups (prospect replied)."""
    db.cancel_follow_ups(conversation_id)
    logger.info("Cancelled follow-ups for conversation %d", conversation_id)


def execute_due_follow_ups(browser: IGBrowserSync) -> Dict:
    """Execute all due follow-ups.

    Returns: {sent: int, skipped: int, errors: int}
    """
    stats = {"sent": 0, "skipped": 0, "errors": 0}

    due = db.get_due_follow_ups()
    logger.info("Processing %d due follow-ups", len(due))

    for fu in due:
        # Rate limit check
        count = db.get_send_count("dm_followup")
        if count >= RATE_LIMITS["dm_followup_max"]:
            logger.info("Follow-up limit reached: %d/%d", count, RATE_LIMITS["dm_followup_max"])
            break

        total = db.get_send_count("dm_total")
        if total >= RATE_LIMITS["dm_daily_max"]:
            break

        try:
            conv = db.get_conversation(fu["conversation_id"])
            if not conv:
                db.mark_follow_up_sent(fu["id"])
                continue

            # Skip if conversation has progressed past follow-up stage
            if conv["stage"] not in ("opener_sent", "replied", "qualifying", "nurture"):
                db.mark_follow_up_sent(fu["id"])
                stats["skipped"] += 1
                continue

            # Skip if requires human
            if conv.get("requires_human"):
                stats["skipped"] += 1
                continue

            # Skip if too many unanswered — don't spam
            messages = db.get_messages(conv["id"], limit=20)
            consecutive_out = 0
            for msg in reversed(messages):
                if msg["direction"] == "out":
                    consecutive_out += 1
                else:
                    break
            if consecutive_out >= SAFETY["max_unanswered_messages"]:
                db.mark_follow_up_sent(fu["id"])
                db.update_conversation(conv["id"], stage="nurture")
                stats["skipped"] += 1
                logger.info("Skipping follow-up for conv %d — %d unanswered",
                            conv["id"], consecutive_out)
                continue

            prospect = db.get_prospect(conv["prospect_id"])
            if not prospect:
                db.mark_follow_up_sent(fu["id"])
                continue

            # Get thread ID
            thread_id = conv.get("ig_thread_id")
            if not thread_id:
                # Try to send to handle directly
                thread_id = prospect["ig_handle"]

            # Generate follow-up content
            content = _generate_follow_up_content(fu, conv, prospect)
            if not content:
                stats["errors"] += 1
                continue

            # Send with cooldown
            time.sleep(random.uniform(
                RATE_LIMITS["dm_cooldown_min"],
                RATE_LIMITS["dm_cooldown_max"],
            ))

            send_result = browser.send_dm(thread_id, content)

            if send_result["success"]:
                db.add_message(
                    conversation_id=conv["id"],
                    direction="out",
                    content=content,
                    message_type="text",
                )
                db.mark_follow_up_sent(fu["id"])
                db.increment_send_count("dm_followup")
                db.increment_send_count("dm_total")
                db.increment_metric("follow_ups_sent")
                stats["sent"] += 1
                logger.info("Follow-up %d sent to @%s",
                            fu["follow_up_number"], prospect["ig_handle"])
            else:
                stats["errors"] += 1
                if browser.check_action_block():
                    from pathlib import Path
                    Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                    Path(SAFETY["pause_file"]).touch()
                    break

        except Exception as e:
            stats["errors"] += 1
            logger.error("Follow-up error: %s", e, exc_info=True)

    return stats


def _generate_follow_up_content(
    follow_up: Dict,
    conversation: Dict,
    prospect: Dict,
) -> str:
    """Generate contextual follow-up using Claude with full conversation history.

    Falls back to templates if Claude fails.
    """
    fu_num = follow_up["follow_up_number"]
    content_type = follow_up["content_type"]
    name = (prospect.get("full_name") or "").split()[0] if prospect.get("full_name") else ""
    handle = prospect.get("ig_handle", "")
    bio = prospect.get("bio", "") or ""

    # Get full conversation history for context
    messages = db.get_messages(conversation["id"], limit=20)
    convo_text = ""
    for msg in messages:
        who = "ME" if msg["direction"] == "out" else "THEM"
        convo_text += f"{who}: {msg['content']}\n"

    # "still with me" is a hardcoded script — no AI needed
    if content_type == "still_with_me":
        return "still with me?"

    type_instructions = {
        "text_bump": "Day 1 bump — short, casual, just making sure they saw the message. No pressure.",
        "voice_memo": "Day 3 — warm check-in, reference something specific from the prior convo if possible. No ask.",
        "value_share": "Day 7 — share something valuable (mention a student win, insight, or resource). Light touch.",
        "final_touch": "Day 14 — graceful close. Leave the door open. If this isn't a priority, no worries.",
    }

    system = f"""You are Sabbo — a 21-year-old entrepreneur who's done $3M+ in online sales.
You're following up with someone who hasn't replied to your DM about Amazon FBA.

Their profile: @{handle} — {name} — bio: {bio}

Prior conversation:
{convo_text}

This is follow-up #{fu_num} ({content_type}): {type_instructions.get(content_type, '')}

Rules:
- Sound like a REAL person, not a bot. Casual, lowercase, no corporate language.
- Max 1-2 sentences. Keep it short.
- Reference the prior conversation if possible — don't repeat the same thing.
- Do NOT pitch or sell. Just re-engage.
- Do NOT use "I noticed you" or "I help people who"

Return ONLY the DM text."""

    try:
        result = _clean_response(_claude_cli(system, "Generate the follow-up message."))
        if result and len(result) > 5:
            return result
    except Exception as e:
        logger.warning("Claude follow-up generation failed, using template: %s", e)

    # Fallback templates
    if content_type == "text_bump":
        return "hey — just making sure this didn't get buried"
    elif content_type == "voice_memo":
        return f"hey{' ' + name if name else ''} — just checking in, no pressure at all. lmk if you ever want to chat"
    elif content_type == "value_share":
        return "just had a student hit their first $10K month — wild seeing it happen in real time"
    elif content_type == "final_touch":
        return f"if amazon ever becomes a focus, hit me up. here if you need anything{' ' + name if name else ''}"
    return ""
