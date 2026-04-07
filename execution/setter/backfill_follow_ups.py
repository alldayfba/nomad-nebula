#!/usr/bin/env python3
"""
Backfill follow-ups for orphaned conversations that never got them scheduled.

Finds conversations at 'opener_sent' or 'replied' with zero follow-up rows,
then schedules the appropriate follow-up steps based on how long ago the
opener was sent.

Usage:
    python -m execution.setter.backfill_follow_ups --dry-run
    python -m execution.setter.backfill_follow_ups
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from execution.setter import setter_db as db
from execution.setter.setter_config import FOLLOW_UP_SEQUENCE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [backfill] %(message)s")
logger = logging.getLogger("backfill")


def get_step_delay_hours(step: dict) -> float:
    """Convert a follow-up step's delay to hours."""
    if "delay_hours" in step:
        return step["delay_hours"]
    return step["delay_days"] * 24


def backfill(dry_run: bool = False):
    """Find orphaned conversations and schedule follow-ups."""
    d = db.get_db()

    # Find conversations with no follow-ups scheduled
    rows = d.execute(
        """SELECT c.id, c.stage, c.created_at, c.offer, p.ig_handle
           FROM conversations c
           JOIN prospects p ON c.prospect_id = p.id
           LEFT JOIN follow_ups f ON f.conversation_id = c.id
           WHERE c.stage IN ('opener_sent', 'replied')
             AND f.id IS NULL
           ORDER BY c.created_at DESC"""
    ).fetchall()

    if not rows:
        logger.info("No orphaned conversations found — all good!")
        return

    logger.info("Found %d orphaned conversations to backfill", len(rows))

    now = datetime.now()
    stats = {"total": len(rows), "scheduled": 0, "steps_created": 0, "skipped_old": 0}

    for row in rows:
        conv_id = row["id"]
        stage = row["stage"]
        handle = row["ig_handle"]

        try:
            created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            logger.warning("  @%s (conv %d): bad created_at, skipping", handle, conv_id)
            continue

        hours_elapsed = (now - created).total_seconds() / 3600
        steps_to_schedule = []

        for step in FOLLOW_UP_SEQUENCE:
            step_delay_h = get_step_delay_hours(step)

            # For 'replied' convos, skip FU#0 ("still with me?") — they already replied
            if stage == "replied" and step["number"] == 0:
                continue

            if hours_elapsed >= step_delay_h:
                # This step's delay already elapsed — schedule it soon (staggered)
                stagger_hours = random.uniform(1.0, 4.0)
                scheduled_at = now + timedelta(hours=stagger_hours)
            else:
                # This step hasn't elapsed yet — schedule at the original time
                scheduled_at = created + timedelta(hours=step_delay_h)

            steps_to_schedule.append((step, scheduled_at))

        # For very old conversations (>14 days), only keep the final touch
        if hours_elapsed > 14 * 24:
            steps_to_schedule = [
                (s, t) for s, t in steps_to_schedule
                if s["number"] == 4  # final_touch only
            ]
            if not steps_to_schedule:
                stats["skipped_old"] += 1
                continue

        if dry_run:
            logger.info("  [DRY RUN] @%s (conv %d, %s, %.0fh ago): would schedule %d steps",
                        handle, conv_id, stage, hours_elapsed, len(steps_to_schedule))
            for step, sched_at in steps_to_schedule:
                logger.info("    FU#%d (%s) → %s", step["number"], step["type"],
                            sched_at.strftime("%Y-%m-%d %H:%M"))
        else:
            for step, sched_at in steps_to_schedule:
                db.schedule_follow_up(
                    conversation_id=conv_id,
                    follow_up_number=step["number"],
                    content_type=step["type"],
                    scheduled_at=sched_at.strftime("%Y-%m-%d %H:%M:%S"),
                    content=step.get("template", "") if step["type"] == "still_with_me" else None,
                )
                stats["steps_created"] += 1

        stats["scheduled"] += 1

    logger.info("=== BACKFILL RESULTS ===")
    logger.info("  Conversations found: %d", stats["total"])
    logger.info("  Conversations scheduled: %d", stats["scheduled"])
    logger.info("  Follow-up steps created: %d", stats["steps_created"])
    logger.info("  Skipped (>14 days, no final touch): %d", stats["skipped_old"])
    if dry_run:
        logger.info("  (DRY RUN — nothing was written to DB)")


def main():
    parser = argparse.ArgumentParser(description="Backfill follow-ups for orphaned conversations")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be scheduled without writing to DB")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
