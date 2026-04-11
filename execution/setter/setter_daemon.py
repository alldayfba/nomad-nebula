#!/usr/bin/env python3
"""
AI Setter Daemon — main orchestrator that runs 24/7 as a launchd service.

Manages the full setter lifecycle:
- Prospect discovery (every 30 min)
- Inbox processing (every 2 min during business hours)
- Cold outbound batches (9 AM)
- Warm outbound batches (2 PM)
- Follow-up execution (9 AM + 2 PM)
- Show rate nurture (every 5 min)
- Metrics aggregation (every hour)
- Pattern learning (every 6 hours)

Usage:
    # Normal operation (24/7 daemon)
    python -m execution.setter.setter_daemon

    # Dry run (read-only, no sending)
    python -m execution.setter.setter_daemon --dry-run

    # Single cycle (run once and exit)
    python -m execution.setter.setter_daemon --once

    # Status check
    python -m execution.setter.setter_daemon --status
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from execution.setter.setter_config import (
    CHROME_LAUNCH_SCRIPT,
    CHROME_PORT,
    COMMENT_KEYWORDS,
    LOG_PATH,
    RATE_LIMITS,
    SAFETY,
    PROJECT_ROOT as PROJ_ROOT,
)
from execution.setter import setter_db as db
from execution.setter.ig_browser import IGBrowserSync
from execution.setter.ig_conversation import (
    process_inbox,
    send_approved_messages,
    send_cold_outbound_batch,
    send_warm_outbound_batch,
)
from execution.setter.ig_prospector import run_scan_cycle
from execution.setter.followup_engine import execute_due_follow_ups
from execution.setter.show_rate_nurture import execute_show_rate_touchpoints
from execution.setter.setter_metrics import aggregate_daily_metrics, send_daily_summary
from execution.setter.pattern_learner import update_winning_patterns
from execution.setter.lead_grader import batch_grade_all
from execution.setter.sales_auditor import batch_audit

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_PATH)),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("setter.daemon")

# ── Globals ──────────────────────────────────────────────────────────────────

_running = True
_dry_run = False


def _signal_handler(signum, frame):
    global _running
    logger.info("Received signal %d, shutting down...", signum)
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


# ── Time Helpers ─────────────────────────────────────────────────────────────

def _est_now() -> datetime:
    """Get current datetime in EST (Miami)."""
    from datetime import timezone, timedelta as _td
    return datetime.now(timezone(_td(hours=-5)))


def _hour() -> int:
    return _est_now().hour


def _minute() -> int:
    return _est_now().minute


def _is_time_for(task: str, last_run: dict) -> bool:
    """Check if it's time to run a periodic task."""
    now = time.time()
    intervals = {
        "inbox": 45,           # Every 45 seconds — sub-2-min response time
        "inbox_night": 900,    # Every 15 minutes at night
        "prospect": 300,       # Every 5 minutes — catch new followers fast
        "followup": 300,       # Every 5 minutes
        "show_rate": 300,      # Every 5 minutes
        "story_viewers": 900,  # Every 15 minutes — catch story engagement fast
        "comment_scan": 300,   # Every 5 minutes — keyword comment triggers
        "grading": 3600,       # Every hour — batch re-grade all convos
        "audit": 14400,        # Every 4 hours — Sales Manager audit
        "metrics": 3600,       # Every hour
        "patterns": 21600,     # Every 6 hours
        "cold_batch": None,    # Triggered by hour
        "warm_batch": None,    # Triggered by hour
    }
    interval = intervals.get(task)
    if interval is None:
        return False
    elapsed = now - last_run.get(task, 0)
    return elapsed >= interval


def _can_send_dm() -> bool:
    """Quick check if we can send another DM (rate limit + pause check)."""
    from pathlib import Path as _P
    if _P(SAFETY["pause_file"]).exists():
        return False
    total = db.get_send_count("dm_total")
    return total < RATE_LIMITS["dm_daily_max"]


def _is_batch_time(batch_hour: int, last_run: dict, key: str) -> bool:
    """Check if it's time for a daily batch (run once at the specified hour)."""
    now = datetime.now()
    if now.hour != batch_hour:
        return False
    # Only run once per day
    last = last_run.get(key, 0)
    last_date = datetime.fromtimestamp(last).date() if last else None
    return last_date != now.date()


# ── Chrome Management ────────────────────────────────────────────────────────

def _ensure_chrome_running() -> bool:
    """Check if Chrome is running on the configured port, launch if not."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("localhost", CHROME_PORT))
        sock.close()
        if result == 0:
            return True
    except Exception:
        pass

    logger.info("Chrome not running on port %d, launching...", CHROME_PORT)
    try:
        subprocess.Popen(
            ["bash", CHROME_LAUNCH_SCRIPT, "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(10)  # Wait for Chrome to start
        # Verify
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("localhost", CHROME_PORT))
            sock.close()
            return result == 0
        except Exception:
            return False
    except Exception as e:
        logger.error("Failed to launch Chrome: %s", e)
        return False


# ── Pause Check ──────────────────────────────────────────────────────────────

def _is_paused() -> bool:
    """Check if setter is paused (action block recovery, manual pause, etc.)."""
    pause_file = Path(SAFETY["pause_file"])
    if pause_file.exists():
        # Check if pause has expired (auto-remove after 24h)
        age = time.time() - pause_file.stat().st_mtime
        if age > SAFETY["action_block_pause_hours"] * 3600:
            pause_file.unlink()
            logger.info("Pause expired after %d hours, resuming", SAFETY["action_block_pause_hours"])
            return False
        return True
    return False


# ── Main Loop ────────────────────────────────────────────────────────────────

def run_daemon(dry_run: bool = False, once: bool = False):
    """Main daemon loop."""
    global _dry_run
    _dry_run = dry_run

    logger.info("=" * 60)
    logger.info("AI Setter Daemon starting (dry_run=%s, once=%s)", dry_run, once)
    logger.info("=" * 60)

    # Ensure Chrome is running
    if not _ensure_chrome_running():
        logger.error("Cannot start Chrome. Login to IG manually on port %d first.", CHROME_PORT)
        return

    # Connect browser
    browser = IGBrowserSync(CHROME_PORT)
    if not browser.connect():
        logger.error("Cannot connect to Chrome on port %d", CHROME_PORT)
        return

    # Health check
    health = browser.health_check()
    logger.info("Health: %s", json.dumps(health))
    if not health.get("ig_logged_in"):
        logger.error("Instagram not logged in! Login manually first.")
        return
    if health.get("action_blocked"):
        logger.error("Action block detected at startup. Pausing.")
        return

    # Initialize DB
    db.get_db()
    logger.info("Database initialized at %s", db.DB_PATH)

    # Track last run times
    last_run = {}

    while _running:
        try:
            now_ts = time.time()
            hour = _hour()  # EST
            is_night = RATE_LIMITS["night_start_hour"] <= hour < RATE_LIMITS["night_end_hour"]  # EST
            paused = _is_paused()

            if paused:
                logger.debug("Setter paused, sleeping...")
                time.sleep(60)
                continue

            # ── 1. Inbox Processing (every 2 min, 15 min at night) ───────
            inbox_task = "inbox_night" if is_night else "inbox"
            if _is_time_for(inbox_task, last_run):
                logger.info("Processing inbox...")
                if dry_run:
                    logger.info("[DRY RUN] Would process inbox")
                else:
                    stats = process_inbox(browser)
                    logger.info("Inbox: processed=%d sent=%d escalated=%d errors=%d",
                                 stats["processed"], stats["sent"],
                                 stats["escalated"], stats["errors"])
                last_run[inbox_task] = now_ts

            # ── 1b. Send Approved Messages (every inbox cycle) ──────────
            if _is_time_for(inbox_task, last_run) and not dry_run:
                approved_stats = send_approved_messages(browser)
                if approved_stats["sent"]:
                    logger.info("Approved messages: sent=%d errors=%d",
                                approved_stats["sent"], approved_stats["errors"])

            # ── 2. Cold Outbound Batch (9 AM daily) ─────────────────────
            if _is_batch_time(RATE_LIMITS["cold_batch_hour"], last_run, "cold_batch"):
                logger.info("Running cold outbound batch...")
                if dry_run:
                    prospects = db.get_qualified_prospects_for_outbound(limit=5)
                    logger.info("[DRY RUN] Would send to %d qualified prospects", len(prospects))
                else:
                    stats = send_cold_outbound_batch(browser, max_count=RATE_LIMITS["dm_cold_max"])
                    logger.info("Cold outbound: sent=%d skipped=%d errors=%d",
                                 stats["sent"], stats["skipped"], stats["errors"])
                last_run["cold_batch"] = now_ts

            # ── 3. Follow-up Batch (9 AM + 2 PM) ────────────────────────
            if _is_time_for("followup", last_run) and not is_night:
                due = db.get_due_follow_ups()
                if due:
                    logger.info("Executing %d due follow-ups...", len(due))
                    if dry_run:
                        logger.info("[DRY RUN] Would send %d follow-ups", len(due))
                    else:
                        stats = execute_due_follow_ups(browser)
                        logger.info("Follow-ups: sent=%d skipped=%d errors=%d",
                                     stats["sent"], stats["skipped"], stats["errors"])
                last_run["followup"] = now_ts

            # ── 4. Warm Outbound Batch (2 PM daily) ─────────────────────
            if _is_batch_time(RATE_LIMITS["warm_batch_hour"], last_run, "warm_batch"):
                logger.info("Running warm outbound batch...")
                if dry_run:
                    logger.info("[DRY RUN] Would send warm outbound")
                else:
                    stats = send_warm_outbound_batch(browser, max_count=RATE_LIMITS["dm_warm_max"])
                    logger.info("Warm outbound: sent=%d skipped=%d errors=%d",
                                 stats["sent"], stats["skipped"], stats["errors"])
                last_run["warm_batch"] = now_ts

            # ── 5. Prospect Discovery (every 30 min) ────────────────────
            if _is_time_for("prospect", last_run):
                logger.info("Running prospect scan cycle...")
                stats = run_scan_cycle(browser)
                logger.info("Prospecting: scanned=%d qualified=%d disqualified=%d",
                             stats["scanned"], stats["qualified"], stats["disqualified"])
                last_run["prospect"] = now_ts

            # ── 6. Show Rate Nurture (every 5 min) ──────────────────────
            if _is_time_for("show_rate", last_run):
                booked = db.get_booked_conversations()
                if booked:
                    if dry_run:
                        logger.info("[DRY RUN] Would process %d booked conversations", len(booked))
                    else:
                        stats = execute_show_rate_touchpoints(browser)
                        if stats["sent"]:
                            logger.info("Show rate: sent=%d touchpoints", stats["sent"])
                last_run["show_rate"] = now_ts

            # ── 7. Metrics Aggregation (hourly) ─────────────────────────
            if _is_time_for("metrics", last_run):
                aggregate_daily_metrics()
                # Send daily summary at 10 PM
                if hour == 22:
                    send_daily_summary()
                last_run["metrics"] = now_ts

            # ── 8. Story Viewer Re-engagement (every 30 min) ───────────
            if _is_time_for("story_viewers", last_run) and not is_night:
                logger.info("Scanning story viewers...")
                try:
                    viewers = browser.get_story_viewers(max_count=100)
                    new_viewers = 0
                    for handle in viewers:
                        existing = db.get_prospect_by_handle(handle)
                        prospect_id = existing["id"] if existing else None
                        if not prospect_id:
                            prospect_id = db.upsert_prospect(
                                ig_handle=handle,
                                source="story_viewer",
                                source_detail="story viewer scan",
                            )
                            new_viewers += 1
                        db.upsert_story_viewer(handle, prospect_id)
                    logger.info("Story viewers: %d total, %d new prospects", len(viewers), new_viewers)

                    # Send re-engage DMs to repeat viewers who haven't been DM'd
                    if not dry_run:
                        warm_viewers = db.get_repeat_story_viewers(min_views=2, limit=20)
                        for sv in warm_viewers:
                            if sv.get("dm_sent"):
                                continue
                            if not _can_send_dm():
                                break
                            handle = sv["ig_handle"]
                            # Check if we already have an active conversation
                            prospect = db.get_prospect_by_handle(handle)
                            if prospect:
                                existing_conv = db.get_conversation_by_prospect(prospect["id"])
                                if existing_conv:
                                    continue  # Already in a conversation

                            # SAFETY: Check for existing thread before sending
                            if browser.check_existing_thread(handle):
                                logger.info("@%s has existing IG thread — skipping story opener",
                                            handle)
                                continue

                            from execution.setter.setter_brain import generate_opener
                            opener = generate_opener(
                                {"ig_handle": handle, "full_name": sv.get("full_name", ""),
                                 "bio": sv.get("bio", ""), "source": "story_viewer"},
                                "amazon_os"
                            )
                            if opener["content"]:
                                import random as _rnd
                                time.sleep(_rnd.uniform(
                                    RATE_LIMITS["dm_cooldown_min"],
                                    RATE_LIMITS["dm_cooldown_max"],
                                ))
                                result = browser.send_dm(handle, opener["content"])
                                if result["success"]:
                                    if prospect:
                                        conv_id = db.create_conversation(
                                            prospect_id=prospect["id"],
                                            offer="amazon_os",
                                            conversation_type="story_reengage",
                                            stage="opener_sent",
                                        )
                                        db.add_message(conv_id, "out", opener["content"],
                                                        claude_model=opener["model"])
                                    db.mark_story_viewer_dmd(handle)
                                    db.increment_send_count("dm_warm")
                                    db.increment_send_count("dm_total")
                except Exception as e:
                    logger.error("Story viewer scan error: %s", e)
                last_run["story_viewers"] = now_ts

            # ── 8b. Comment Keyword Detection (every 5 min) ───────────
            if _is_time_for("comment_scan", last_run) and not is_night:
                try:
                    # Flatten all keywords from all offers
                    all_keywords = []
                    for kws in COMMENT_KEYWORDS.values():
                        all_keywords.extend(kws)
                    all_keywords = list(set(all_keywords))

                    matches = browser.scan_comment_keywords(all_keywords, max_count=20)
                    if matches:
                        logger.info("Comment keywords: %d matches found", len(matches))
                        if not dry_run:
                            for match in matches:
                                if not _can_send_dm():
                                    break
                                handle = match["handle"]
                                prospect = db.get_prospect_by_handle(handle)
                                if prospect:
                                    existing_conv = db.get_conversation_by_prospect(prospect["id"])
                                    if existing_conv:
                                        continue
                                else:
                                    pid = db.upsert_prospect(
                                        ig_handle=handle,
                                        source="comment_trigger",
                                        source_detail=f"commented: {match['keyword_matched']}",
                                    )
                                    prospect = db.get_prospect(pid)

                                if not prospect:
                                    continue

                                from execution.setter.setter_brain import generate_opener
                                opener = generate_opener(
                                    {**prospect, "source": "comment_trigger",
                                     "source_detail": match["keyword_matched"]},
                                    "amazon_os"
                                )
                                if opener["content"]:
                                    import random as _rnd
                                    time.sleep(_rnd.uniform(
                                        RATE_LIMITS["dm_cooldown_min"],
                                        RATE_LIMITS["dm_cooldown_max"],
                                    ))
                                    result = browser.send_dm(handle, opener["content"])
                                    if result["success"]:
                                        conv_id = db.create_conversation(
                                            prospect_id=prospect["id"],
                                            offer="amazon_os",
                                            conversation_type="comment_trigger",
                                            stage="opener_sent",
                                        )
                                        db.add_message(conv_id, "out", opener["content"],
                                                        claude_model=opener.get("model", ""))
                                        db.update_prospect_status(prospect["id"], "contacted")
                                        db.increment_send_count("dm_warm")
                                        db.increment_send_count("dm_total")
                                        logger.info("Comment DM sent to @%s (keyword: %s)",
                                                     handle, match["keyword_matched"])
                except Exception as e:
                    logger.error("Comment scan error: %s", e)
                last_run["comment_scan"] = now_ts

            # ── 9. Lead Grading (hourly) ────────────────────────────────
            if _is_time_for("grading", last_run):
                logger.info("Batch grading all active conversations...")
                grade_stats = batch_grade_all()
                logger.info("Grading: %s", grade_stats)
                last_run["grading"] = now_ts

            # ── 10. Sales Manager Audit (every 4 hours) ─────────────────
            if _is_time_for("audit", last_run):
                logger.info("Sales Manager auditing conversations...")
                if dry_run:
                    logger.info("[DRY RUN] Would audit recent conversations")
                else:
                    audit_stats = batch_audit(limit=10)
                    logger.info("Audit: %s", audit_stats)
                last_run["audit"] = now_ts

            # ── 11. Pattern Learning (every 6 hours) ────────────────────
            if _is_time_for("patterns", last_run):
                update_winning_patterns()
                last_run["patterns"] = now_ts

            # ── Sleep ────────────────────────────────────────────────────
            if once:
                logger.info("Single cycle complete, exiting.")
                break

            time.sleep(30)  # Check every 30 seconds

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error("Daemon loop error: %s", e, exc_info=True)
            time.sleep(60)  # Back off on error

    # Cleanup
    logger.info("Daemon shutting down...")
    browser.disconnect()
    db.close_db()
    logger.info("Disconnected from Chrome. Goodbye.")


# ── Status Command ───────────────────────────────────────────────────────────

def show_status():
    """Show current setter status."""
    print("=" * 50)
    print("AI SETTER STATUS")
    print("=" * 50)

    # Pause status
    paused = _is_paused()
    print(f"Status: {'PAUSED' if paused else 'ACTIVE'}")

    # Pipeline stats
    stats = db.get_pipeline_stats()
    print(f"\nPipeline:")
    for stage, count in stats.items():
        if count > 0:
            print(f"  {stage}: {count}")

    # Today's metrics
    metrics = db.get_daily_metrics()
    if metrics:
        print(f"\nToday's Metrics:")
        print(f"  Cold DMs sent: {metrics.get('cold_dms_sent', 0)}")
        print(f"  Warm DMs sent: {metrics.get('warm_dms_sent', 0)}")
        print(f"  Follow-ups sent: {metrics.get('follow_ups_sent', 0)}")
        print(f"  Inbox replies: {metrics.get('inbox_replies_sent', 0)}")
        print(f"  Total DMs: {metrics.get('total_dms_sent', 0)}")
        print(f"  Replies received: {metrics.get('replies_received', 0)}")
        print(f"  Booked: {metrics.get('booked', 0)}")
        print(f"  API cost: ${metrics.get('api_cost', 0):.2f}")
    else:
        print("\nNo metrics for today yet.")

    # Rate limits
    sends = db.get_today_send_counts()
    if sends:
        print(f"\nRate Limits:")
        for channel, count in sends.items():
            print(f"  {channel}: {count}")

    # Pending approvals
    pending = db.get_pending_approval_messages()
    if pending:
        print(f"\nPending Approvals: {len(pending)}")
        for msg in pending[:5]:
            print(f"  @{msg.get('ig_handle', '?')}: {msg['content'][:60]}...")

    print()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Setter Daemon")
    parser.add_argument("--dry-run", action="store_true", help="Read-only mode, no sending")
    parser.add_argument("--once", action="store_true", help="Run single cycle and exit")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--pause", action="store_true", help="Pause the setter")
    parser.add_argument("--resume", action="store_true", help="Resume the setter")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.pause:
        Path(SAFETY["pause_file"]).parent.mkdir(parents=True, exist_ok=True)
        Path(SAFETY["pause_file"]).touch()
        print("Setter PAUSED.")
        return

    if args.resume:
        p = Path(SAFETY["pause_file"])
        if p.exists():
            p.unlink()
        print("Setter RESUMED.")
        return

    run_daemon(dry_run=args.dry_run, once=args.once)


if __name__ == "__main__":
    main()
