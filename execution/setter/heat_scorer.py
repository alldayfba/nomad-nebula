#!/usr/bin/env python3
"""
Heat Scorer — dynamic 0-100 buyer intent scoring for every lead.

Score = stage_base + signal_bonuses + signal_penalties

Updates on every conversation event (new message, stage change).
Used by the brain to prioritize responses and adjust tone.

Usage:
    python -m execution.setter.heat_scorer --score-all          # Recalculate all
    python -m execution.setter.heat_scorer --score-id 123       # Score one conversation
    python -m execution.setter.heat_scorer --leaderboard        # Show top leads
"""
from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from . import setter_db as db

logger = logging.getLogger("setter.heat_scorer")

# ── Stage Base Scores (0-60) ────────────────────────────────────────────────

STAGE_BASE: Dict[str, int] = {
    "new": 0,
    "opener_sent": 5,
    "replied": 20,
    "qualifying": 35,
    "qualified": 50,
    "booking": 55,
    "booked": 80,
    "show": 95,
    "no_show": 40,
    "nurture": 15,
    "disqualified": 0,
    "dead": 0,
    "escalated": 25,  # human flagged — still has some interest
}

# ── Signal Patterns ─────────────────────────────────────────────────────────

MONEY_KEYWORDS = re.compile(
    r"\b(money|capital|invest(ment|ing)?|budget|savings?|afford|funds?|"
    r"\$\d|k saved|thousand|cash)\b",
    re.IGNORECASE,
)
URGENCY_KEYWORDS = re.compile(
    r"\b(this month|asap|ready|soon|right now|immediately|today|tomorrow|"
    r"this week|urgent|quick(ly)?|start(ing)?)\b",
    re.IGNORECASE,
)
COMMITMENT_KEYWORDS = re.compile(
    r"\b(yes|let'?s do it|i'?m in|sign me up|count me in|absolutely|"
    r"for sure|definitely|100%|bet|ready to go|let'?s go)\b",
    re.IGNORECASE,
)
PERSONAL_INFO_PATTERN = re.compile(
    r"([\w.+-]+@[\w-]+\.[\w.-]+|[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}|"
    r"my name is|i'?m \w+\s\w+)",
    re.IGNORECASE,
)
QUESTION_PATTERN = re.compile(r"\?")
NEGATIVE_KEYWORDS = re.compile(
    r"\b(not interested|maybe later|no thanks|not right now|"
    r"can'?t afford|too expensive|not for me|pass)\b",
    re.IGNORECASE,
)
STOP_KEYWORDS = re.compile(
    r"\b(stop|unsubscribe|leave me alone|block(ed)?|report(ed)?|"
    r"spam|f\*?u\*?c\*?k off|don'?t (message|dm|contact) me)\b",
    re.IGNORECASE,
)
BIO_BUSINESS_KEYWORDS = re.compile(
    r"\b(ceo|founder|owner|entrepreneur|business|brand|agency|"
    r"coach|consultant|e-?commerce|amazon|fba|seller|shopify|"
    r"saas|startup|co-?founder|investor)\b",
    re.IGNORECASE,
)


# ── Core Scoring Engine ─────────────────────────────────────────────────────

def calculate_heat_score(conversation_id: int) -> int:
    """Calculate and persist the heat score for a conversation.

    Returns the computed score (0-100).
    """
    conv = db.get_conversation(conversation_id)
    if not conv:
        return 0

    prospect = db.get_prospect(conv["prospect_id"])
    if not prospect:
        return 0

    messages = db.get_messages(conversation_id, limit=100)

    score = 0

    # ── 1. Stage base score ─────────────────────────────────────────────
    stage = conv.get("stage", "new")
    score += STAGE_BASE.get(stage, 0)

    # ── 2. Signal bonuses from inbound messages ─────────────────────────
    inbound = [m for m in messages if m["direction"] == "in"]
    outbound = [m for m in messages if m["direction"] == "out"]

    if not inbound and stage in ("new", "opener_sent"):
        # No reply yet — just stage base
        db.update_heat_score(conversation_id, max(0, min(100, score)))
        return max(0, min(100, score))

    all_inbound_text = " ".join(m.get("content", "") for m in inbound)

    # +5: asked a question (shows engagement)
    if QUESTION_PATTERN.search(all_inbound_text):
        score += 5

    # +3: mentioned money/capital/investment/budget
    if MONEY_KEYWORDS.search(all_inbound_text):
        score += 3

    # +3: mentioned timeline/urgency
    if URGENCY_KEYWORDS.search(all_inbound_text):
        score += 3

    # +5: shared personal info (email, phone, name)
    if PERSONAL_INFO_PATTERN.search(all_inbound_text):
        score += 5

    # +3: expressed commitment
    if COMMITMENT_KEYWORDS.search(all_inbound_text):
        score += 3

    # +3: replied to multiple messages (multi-turn engagement)
    if len(inbound) >= 3:
        score += 3
    elif len(inbound) >= 2:
        score += 1

    # ── 3. Timing signals ───────────────────────────────────────────────
    # +5: replied within 1 hour of our opener
    if inbound and outbound:
        first_out = outbound[0]
        first_in = inbound[0]
        try:
            out_time = datetime.strptime(first_out["sent_at"], "%Y-%m-%d %H:%M:%S")
            in_time = datetime.strptime(first_in["sent_at"], "%Y-%m-%d %H:%M:%S")
            reply_delta = (in_time - out_time).total_seconds()
            if 0 < reply_delta <= 3600:  # replied within 1 hour
                score += 5
            elif 0 < reply_delta <= 14400:  # within 4 hours — still warm
                score += 2
        except (ValueError, TypeError):
            pass

    # ── 4. Profile signals ──────────────────────────────────────────────
    bio = prospect.get("bio", "") or ""

    # +2: has business-related bio keywords
    if BIO_BUSINESS_KEYWORDS.search(bio):
        score += 2

    # +2: story viewer (engaged with our content)
    try:
        d = db.get_db()
        viewer = d.execute(
            "SELECT view_count FROM story_viewers WHERE ig_handle = ?",
            (prospect.get("ig_handle", ""),),
        ).fetchone()
        if viewer and viewer["view_count"] >= 1:
            score += 2
    except Exception:
        pass

    # +3: comment trigger (conversation started from a comment)
    conv_type = conv.get("conversation_type", "")
    source = prospect.get("source", "")
    if conv_type == "inbound" or source in ("comment_trigger", "post_comment"):
        score += 3

    # ── 5. Penalties ────────────────────────────────────────────────────
    # -5: said "not interested" or "maybe later"
    if NEGATIVE_KEYWORDS.search(all_inbound_text):
        score -= 5

    # -10: said "stop" or negative keyword
    if STOP_KEYWORDS.search(all_inbound_text):
        score -= 10

    # -3: didn't reply to last 2+ messages
    if messages:
        consecutive_out = 0
        for msg in reversed(messages):
            if msg["direction"] == "out":
                consecutive_out += 1
            else:
                break
        if consecutive_out >= 2:
            score -= 3

    # ── 6. Clamp and persist ────────────────────────────────────────────
    final_score = max(0, min(100, score))
    db.update_heat_score(conversation_id, final_score)

    logger.debug(
        "Heat score for conv %d (@%s): %d (stage=%s, base=%d)",
        conversation_id,
        prospect.get("ig_handle", "?"),
        final_score,
        stage,
        STAGE_BASE.get(stage, 0),
    )

    return final_score


def score_all() -> Dict[str, int]:
    """Recalculate heat scores for all active conversations.

    Returns: {scored: int, skipped: int}
    """
    d = db.get_db()
    rows = d.execute(
        """SELECT id FROM conversations
           WHERE stage NOT IN ('dead', 'disqualified')
           ORDER BY last_message_at DESC"""
    ).fetchall()

    scored = 0
    skipped = 0
    for row in rows:
        try:
            calculate_heat_score(row["id"])
            scored += 1
        except Exception as e:
            logger.error("Failed to score conversation %d: %s", row["id"], e)
            skipped += 1

    logger.info("Heat scores recalculated: %d scored, %d skipped", scored, skipped)
    return {"scored": scored, "skipped": skipped}


def print_leaderboard(limit: int = 20):
    """Print the top leads by heat score."""
    leads = db.get_hottest_leads(limit=limit)
    if not leads:
        print("No active leads found.")
        return

    print(f"\n{'='*70}")
    print(f"  HEAT SCORE LEADERBOARD — Top {limit} Leads")
    print(f"{'='*70}")
    print(f"  {'#':<4} {'Handle':<22} {'Score':<8} {'Stage':<14} {'Name'}")
    print(f"  {'-'*4} {'-'*22} {'-'*8} {'-'*14} {'-'*20}")

    for i, lead in enumerate(leads, 1):
        handle = f"@{lead.get('ig_handle', '?')}"[:21]
        score = lead.get("heat_score", 0)
        stage = lead.get("stage", "?")
        name = (lead.get("full_name", "") or "")[:20]

        # Heat indicator
        if score >= 81:
            heat = "***"
        elif score >= 51:
            heat = "** "
        elif score >= 21:
            heat = "*  "
        else:
            heat = "   "

        print(f"  {i:<4} {handle:<22} {score:<5}{heat} {stage:<14} {name}")

    print(f"{'='*70}\n")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Heat Scorer — lead intent scoring")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--score-all", action="store_true", help="Recalculate all scores")
    group.add_argument("--score-id", type=int, help="Score a single conversation by ID")
    group.add_argument("--leaderboard", action="store_true", help="Show top leads")
    parser.add_argument("--limit", type=int, default=20, help="Leaderboard limit")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.score_all:
        result = score_all()
        print(f"Scored {result['scored']} conversations, skipped {result['skipped']}")
    elif args.score_id:
        score = calculate_heat_score(args.score_id)
        print(f"Conversation {args.score_id} heat score: {score}/100")
    elif args.leaderboard:
        score_all()  # Recalculate first
        print_leaderboard(limit=args.limit)


if __name__ == "__main__":
    main()
