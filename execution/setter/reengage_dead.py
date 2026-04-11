#!/usr/bin/env python3
"""
Dead Lead Re-Engagement -- smart follow-up campaign for non-responders.

Instead of generic "still with me??" bumps, sends value-based touchpoints
that give the prospect a reason to re-engage.

3 rotation types (round-robin):
1. Value Share -- a relevant tip or insight
2. Social Proof -- a student win or case study
3. Curiosity Hook -- something time-sensitive or intriguing

Usage:
    python -m execution.setter.reengage_dead --limit 50 --dry-run
    python -m execution.setter.reengage_dead --limit 100
    python -m execution.setter.reengage_dead --preview  # Show what would be sent
"""
from __future__ import annotations

import argparse
import logging
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from execution.setter.ig_browser import IGBrowserSync
from execution.setter import setter_db as db
from execution.setter.setter_config import RATE_LIMITS, SAFETY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [reengage] %(message)s")
logger = logging.getLogger("reengage")

# Re-engagement message types — round-robin rotation
REENGAGE_TYPES = ["value_share", "social_proof", "curiosity_hook"]

# Prompts for each type (sent to Claude Haiku via CLI)
REENGAGE_PROMPTS = {
    "value_share": (
        "Generate a casual 1-sentence DM with a useful Amazon FBA tip. "
        "No pitch, no ask. Sound like a friend sharing something cool. "
        "Keep it under 120 chars. Lowercase, no emojis unless natural. "
        'Example vibe: "yo just saw someone flip [product category] for 3x ROI on amazon, crazy margins out there rn"\n'
        "Return ONLY the message text, nothing else."
    ),
    "social_proof": (
        "Generate a casual 1-sentence DM mentioning a student success story (generic, no real names). "
        "No pitch, no ask. Sound impressed, like sharing good news with a friend. "
        "Keep it under 120 chars. Lowercase, no emojis unless natural. "
        'Example vibe: "one of my guys just hit his first $10K month on amazon in 90 days, wild stuff"\n'
        "Return ONLY the message text, nothing else."
    ),
    "curiosity_hook": (
        "Generate a casual 1-sentence DM with a time-sensitive hook about Amazon FBA. "
        "Create genuine curiosity without being clickbaity. "
        "Keep it under 120 chars. Lowercase, no emojis unless natural. "
        'Example vibe: "amazon just opened a new category thats printing rn, most ppl dont know about it yet"\n'
        "Return ONLY the message text, nothing else."
    ),
}


def _get_dead_leads(min_days_since_last: int = 3, limit: int = 100) -> List[Dict]:
    """Query conversations at stage 'opener_sent' where last message was >N days ago.

    Returns list of dicts with conversation + prospect info.
    """
    d = db.get_db()
    cutoff = (datetime.now(timezone(timedelta(hours=-5))) - timedelta(days=min_days_since_last)).strftime("%Y-%m-%d %H:%M:%S")

    rows = d.execute(
        """SELECT c.id as conv_id, c.prospect_id, c.ig_thread_id, c.offer,
                  c.last_message_at, c.messages_sent,
                  p.ig_handle, p.full_name, p.bio
           FROM conversations c
           JOIN prospects p ON c.prospect_id = p.id
           WHERE c.stage = 'opener_sent'
             AND c.last_message_at < ?
             AND c.last_message_direction = 'out'
             AND c.requires_human = 0
           ORDER BY c.last_message_at ASC
           LIMIT ?""",
        (cutoff, limit * 2),  # Fetch extra to account for blocklist filtering
    ).fetchall()

    results = []
    for row in rows:
        row = dict(row)
        # Skip blocklisted
        if db.is_blocklisted(row["ig_handle"]):
            continue
        results.append(row)
        if len(results) >= limit:
            break

    return results


def _generate_message(reengage_type: str) -> Optional[str]:
    """Generate a re-engagement message using Claude Haiku via CLI.

    Args:
        reengage_type: One of 'value_share', 'social_proof', 'curiosity_hook'.

    Returns:
        Generated message string, or None on failure.
    """
    prompt = REENGAGE_PROMPTS.get(reengage_type)
    if not prompt:
        return None

    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "claude-haiku-4-5-20251001"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            msg = result.stdout.strip().strip('"').strip("'")
            # Validate: reasonable length, no empty
            if 10 < len(msg) < 200:
                return msg
            logger.warning("Generated message too short/long (%d chars): %s", len(msg), msg[:50])
    except subprocess.TimeoutExpired:
        logger.warning("Claude CLI timed out generating %s message", reengage_type)
    except FileNotFoundError:
        logger.error("claude CLI not found — install Anthropic CLI")
    except Exception as e:
        logger.error("Message generation error: %s", e)

    return None


def run_reengage(
    limit: int = 50,
    dry_run: bool = False,
    preview: bool = False,
    min_days: int = 3,
) -> Dict:
    """Run the dead lead re-engagement campaign.

    Args:
        limit: Max leads to re-engage this run.
        dry_run: Generate messages but don't send (print what would be sent).
        preview: Same as dry_run, shows a preview table.
        min_days: Minimum days since last message before re-engaging.

    Returns:
        Stats dict: {attempted, sent, errors, skipped, generated}
    """
    stats = {"attempted": 0, "sent": 0, "errors": 0, "skipped": 0, "generated": 0}

    dead_leads = _get_dead_leads(min_days_since_last=min_days, limit=limit)
    logger.info("Found %d dead leads eligible for re-engagement (>%d days since last msg)",
                len(dead_leads), min_days)

    if not dead_leads:
        logger.info("No dead leads to re-engage")
        return stats

    if preview or dry_run:
        print(f"\n{'='*70}")
        print(f"{'HANDLE':<25} {'TYPE':<15} {'LAST MSG':<20} {'MESSAGE'}")
        print(f"{'='*70}")

    browser = None
    if not dry_run and not preview:
        browser = IGBrowserSync()
        if not browser.connect():
            logger.error("Cannot connect to Chrome")
            return stats

    try:
        for i, lead in enumerate(dead_leads):
            if stats["sent"] + stats["generated"] >= limit:
                break

            stats["attempted"] += 1

            # Round-robin type selection
            reengage_type = REENGAGE_TYPES[i % len(REENGAGE_TYPES)]

            # Generate message
            message = _generate_message(reengage_type)
            if not message:
                logger.warning("Failed to generate %s message for @%s, skipping",
                               reengage_type, lead["ig_handle"])
                stats["errors"] += 1
                continue

            stats["generated"] += 1

            if preview or dry_run:
                last_msg = lead.get("last_message_at", "unknown")
                if last_msg and len(last_msg) > 16:
                    last_msg = last_msg[:16]
                print(f"@{lead['ig_handle']:<24} {reengage_type:<15} {last_msg:<20} {message}")
                continue

            # Check rate limits
            total_sent = db.get_send_count("dm_total")
            if total_sent >= RATE_LIMITS["dm_daily_max"]:
                logger.info("Daily DM limit reached, stopping")
                break

            # Check pause file
            if Path(SAFETY["pause_file"]).exists():
                logger.warning("Setter is PAUSED, stopping")
                break

            # Send the DM
            thread_id = lead.get("ig_thread_id") or lead["ig_handle"]
            try:
                # Cooldown between sends
                wait = random.uniform(
                    RATE_LIMITS["dm_cooldown_min"],
                    RATE_LIMITS["dm_cooldown_max"],
                )
                logger.info("Waiting %.0fs before sending to @%s...", wait, lead["ig_handle"])
                time.sleep(wait)

                send_result = browser.send_dm(thread_id, message)

                if send_result.get("success"):
                    # Record the message
                    db.add_message(
                        conversation_id=lead["conv_id"],
                        direction="out",
                        content=message,
                        message_type="text",
                    )

                    # Update conversation: move to nurture, schedule next follow-up in 7 days
                    next_followup = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
                    db.update_conversation(
                        lead["conv_id"],
                        stage="nurture",
                        next_action="reengage_followup",
                        next_action_at=next_followup,
                    )

                    db.increment_send_count("dm_total")
                    db.increment_send_count("dm_followup")
                    db.increment_metric("follow_ups_sent")

                    stats["sent"] += 1
                    logger.info("Sent %s to @%s (%d/%d)",
                                reengage_type, lead["ig_handle"], stats["sent"], limit)
                else:
                    stats["errors"] += 1
                    logger.error("Failed to send to @%s: %s",
                                 lead["ig_handle"], send_result.get("error"))

                    # Check for action block
                    if browser.check_action_block():
                        logger.error("ACTION BLOCK detected, stopping")
                        Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
                        Path(SAFETY["pause_file"]).touch()
                        break

            except Exception as e:
                stats["errors"] += 1
                logger.error("Error sending to @%s: %s", lead["ig_handle"], e)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        if browser:
            browser.disconnect()

    if preview or dry_run:
        print(f"\n{'='*70}")
        print(f"Total: {stats['generated']} messages generated for {stats['attempted']} leads")
    else:
        print(f"\n{'='*50}")
        print("RE-ENGAGEMENT RESULTS")
        print(f"{'='*50}")
        print(f"  Attempted: {stats['attempted']}")
        print(f"  Sent: {stats['sent']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  Skipped: {stats['skipped']}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Dead Lead Re-Engagement Campaign")
    parser.add_argument("--limit", type=int, default=50, help="Max leads to re-engage")
    parser.add_argument("--dry-run", action="store_true", help="Generate but don't send")
    parser.add_argument("--preview", action="store_true", help="Show what would be sent")
    parser.add_argument("--min-days", type=int, default=3,
                        help="Min days since last message (default: 3)")
    args = parser.parse_args()

    run_reengage(
        limit=args.limit,
        dry_run=args.dry_run,
        preview=args.preview,
        min_days=args.min_days,
    )


if __name__ == "__main__":
    main()
