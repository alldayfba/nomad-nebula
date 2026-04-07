"""
Pattern learner — analyzes conversations to find winning patterns.

Tracks which openers get replies, which qualifiers convert, and updates
the winning_patterns table so the brain can use proven messages.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from . import setter_db as db

logger = logging.getLogger("setter.patterns")


def update_winning_patterns():
    """Analyze recent conversations and update pattern success rates.

    Runs every 6 hours. Looks at conversations that progressed (or didn't)
    and credits the messages that worked.
    """
    d = db.get_db()

    # 1. Opener success = prospect replied
    # Find conversations where opener was sent AND prospect replied
    replied_convos = d.execute(
        """SELECT c.id, m.content as opener_content, c.offer
           FROM conversations c
           JOIN messages m ON m.conversation_id = c.id
           WHERE c.stage NOT IN ('new', 'opener_sent', 'dead')
             AND m.direction = 'out'
             AND m.id = (
                 SELECT MIN(id) FROM messages
                 WHERE conversation_id = c.id AND direction = 'out'
             )"""
    ).fetchall()

    for conv in replied_convos:
        if conv["opener_content"]:
            db.record_pattern_success("opener", conv["opener_content"])

    # 2. Qualifier success = conversation progressed to qualified or booked
    qualified_convos = d.execute(
        """SELECT c.id, c.offer
           FROM conversations c
           WHERE c.stage IN ('qualified', 'booking', 'booked', 'show')"""
    ).fetchall()

    for conv in qualified_convos:
        # Credit qualifying messages (messages 2-4 in the flow)
        msgs = d.execute(
            """SELECT content FROM messages
               WHERE conversation_id = ? AND direction = 'out'
               ORDER BY sent_at ASC
               LIMIT 5 OFFSET 1""",
            (conv["id"],),
        ).fetchall()
        for msg in msgs:
            if msg["content"]:
                db.record_pattern_success("qualifier", msg["content"])

    # 3. Booking bridge success = conversation reached booked
    booked_convos = d.execute(
        """SELECT c.id, c.offer
           FROM conversations c
           WHERE c.stage IN ('booked', 'show')"""
    ).fetchall()

    for conv in booked_convos:
        # Credit the message right before booking
        last_out = d.execute(
            """SELECT content FROM messages
               WHERE conversation_id = ? AND direction = 'out'
               ORDER BY sent_at DESC LIMIT 1""",
            (conv["id"],),
        ).fetchone()
        if last_out and last_out["content"]:
            db.record_pattern_success("booking_bridge", last_out["content"])

    # 4. Recalculate all success rates
    d.execute(
        """UPDATE winning_patterns
           SET success_rate = CASE
               WHEN times_used > 0 THEN CAST(times_succeeded AS REAL) / times_used
               ELSE 0.0
           END"""
    )
    d.commit()

    # Log top patterns
    for pt in ("opener", "qualifier", "booking_bridge"):
        top = db.get_top_patterns(pt, limit=3)
        if top:
            logger.info("Top %s patterns:", pt)
            for p in top:
                logger.info("  %.0f%% (%d/%d): %s",
                             p["success_rate"] * 100,
                             p["times_succeeded"],
                             p["times_used"],
                             p["content"][:60])

    logger.info("Winning patterns updated")
