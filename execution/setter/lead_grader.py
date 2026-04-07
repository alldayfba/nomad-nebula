"""
Lead grading engine — auto-grades every prospect after each interaction.

Grades: A (hot buyer), B (warm engaged), C (lukewarm), D (cold/new), F (dead/hostile)
Temperature: hot, warm, cold, dead

Runs after every message exchange. Also provides batch grading for Sales Manager audits.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List

from . import setter_db as db

logger = logging.getLogger("setter.grader")


def grade_conversation(conversation_id: int) -> Dict:
    """Auto-grade a conversation based on all signals.

    Called after every inbound/outbound message.
    Returns the grade dict.
    """
    conv = db.get_conversation(conversation_id)
    if not conv:
        return {}

    prospect = db.get_prospect(conv["prospect_id"])
    if not prospect:
        return {}

    messages = db.get_messages(conversation_id)

    # Calculate signals
    total_msgs = len(messages)
    inbound = [m for m in messages if m["direction"] == "in"]
    outbound = [m for m in messages if m["direction"] == "out"]

    # Response rate
    response_rate = len(inbound) / max(len(outbound), 1)

    # Buying signals from inbound messages
    buying_keywords = [
        "interested", "how much", "what's the price", "tell me more",
        "when can we talk", "sounds good", "i'm in", "let's do it",
        "ready", "let's go", "sign me up", "yes", "book", "call",
        "invest", "capital", "budget", "afford", "pay",
    ]
    buying_signals = 0
    for msg in inbound:
        content_lower = msg["content"].lower()
        for kw in buying_keywords:
            if kw in content_lower:
                buying_signals += 1

    # Objection signals
    objection_keywords = [
        "too expensive", "can't afford", "not sure", "need to think",
        "talk to my", "let me check", "maybe later", "not ready",
        "no money", "broke", "skeptical", "scam",
    ]
    objection_count = 0
    for msg in inbound:
        content_lower = msg["content"].lower()
        for kw in objection_keywords:
            if kw in content_lower:
                objection_count += 1

    # Engagement score (0-100)
    engagement = 0
    if response_rate >= 1.0:
        engagement += 30  # They reply to every message
    elif response_rate >= 0.5:
        engagement += 15

    if buying_signals >= 3:
        engagement += 30
    elif buying_signals >= 1:
        engagement += 15

    if total_msgs >= 6:
        engagement += 20  # Extended conversation = engaged
    elif total_msgs >= 3:
        engagement += 10

    # Check if they asked questions (very positive signal)
    questions = sum(1 for m in inbound if "?" in m.get("content", ""))
    if questions >= 2:
        engagement += 20
    elif questions >= 1:
        engagement += 10

    engagement = min(100, engagement)

    # Determine grade
    stage = conv.get("stage", "new")
    if stage in ("booked", "show"):
        grade = "A"
        temperature = "hot"
    elif stage == "qualified" or (buying_signals >= 3 and engagement >= 60):
        grade = "A"
        temperature = "hot"
    elif stage in ("qualifying", "booking") or (buying_signals >= 1 and engagement >= 40):
        grade = "B"
        temperature = "warm"
    elif stage == "replied" or engagement >= 20:
        grade = "C"
        temperature = "warm"
    elif stage in ("dead", "disqualified") or objection_count >= 3:
        grade = "F"
        temperature = "dead"
    else:
        grade = "D"
        temperature = "cold"

    # Calculate avg response time
    response_time_avg = 0
    if len(inbound) >= 2:
        times = []
        for i, msg in enumerate(messages):
            if msg["direction"] == "in" and i > 0 and messages[i-1]["direction"] == "out":
                try:
                    t_out = datetime.strptime(messages[i-1]["sent_at"], "%Y-%m-%d %H:%M:%S")
                    t_in = datetime.strptime(msg["sent_at"], "%Y-%m-%d %H:%M:%S")
                    times.append((t_in - t_out).total_seconds())
                except (ValueError, TypeError):
                    pass
        if times:
            response_time_avg = int(sum(times) / len(times))

    # Determine reason for grade
    reason_parts = []
    if buying_signals > 0:
        reason_parts.append(f"{buying_signals} buying signals")
    if objection_count > 0:
        reason_parts.append(f"{objection_count} objections")
    reason_parts.append(f"engagement:{engagement}")
    reason_parts.append(f"stage:{stage}")
    reason = ", ".join(reason_parts)

    # Store grade
    db.upsert_lead_grade(
        prospect_id=conv["prospect_id"],
        grade=grade,
        temperature=temperature,
        engagement_score=engagement,
        buying_signals=buying_signals,
        objection_count=objection_count,
        response_time_avg=response_time_avg,
        messages_exchanged=total_msgs,
        reason=reason,
    )

    logger.info("Graded @%s: %s (%s) engagement:%d buying:%d objections:%d",
                prospect.get("ig_handle"), grade, temperature,
                engagement, buying_signals, objection_count)

    return {
        "grade": grade,
        "temperature": temperature,
        "engagement_score": engagement,
        "buying_signals": buying_signals,
        "objection_count": objection_count,
        "response_time_avg": response_time_avg,
    }


def batch_grade_all() -> Dict:
    """Re-grade all active conversations. Run by Sales Manager daily."""
    convos = db.get_active_conversations(limit=500)
    stats = {"graded": 0, "A": 0, "B": 0, "C": 0, "D": 0, "F": 0}

    for conv in convos:
        result = grade_conversation(conv["id"])
        if result:
            stats["graded"] += 1
            stats[result["grade"]] = stats.get(result["grade"], 0) + 1

    logger.info("Batch grade: %d convos — A:%d B:%d C:%d D:%d F:%d",
                stats["graded"], stats["A"], stats["B"], stats["C"], stats["D"], stats["F"])
    return stats
