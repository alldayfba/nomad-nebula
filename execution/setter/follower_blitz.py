#!/usr/bin/env python3
"""
Follower Blitz — opens followers list, goes down the list, DMs each one.

Modes:
  cold  — Scroll followers list, DM only people we've NEVER messaged.
  warm  — DM story viewers who engaged but never got a DM.

Flow (cold):
1. Open @allday.fba profile → click Followers
2. Scroll through list, save each handle to DB
3. For each uncontacted follower:
   a. Open profile → click Message
   b. If thread has ANY existing messages → skip (bulletproof check)
   c. If thread is empty → send Sabbo's opener
4. Next person

Usage:
    python -m execution.setter.follower_blitz --mode cold --limit 50
    python -m execution.setter.follower_blitz --mode warm --limit 30
    python -m execution.setter.follower_blitz --mode cold --limit 50 --fast
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from execution.setter.ig_browser import IGBrowserSync, IGBrowser
from execution.setter import setter_db as db
from execution.setter.setter_brain import generate_opener
from execution.setter.setter_config import DM_SCRIPT, OWN_IG_HANDLE, RATE_LIMITS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [blitz] %(message)s")
logger = logging.getLogger("blitz")


def run_blitz(limit: int = 20, dry_run: bool = False, cooldown: tuple = None, mode: str = "cold"):
    """Open followers list and DM down the list.

    Args:
        limit: Max DMs to send this run.
        dry_run: If True, generate openers but don't send.
        cooldown: (min_seconds, max_seconds) between DMs.
        mode: 'cold' (followers, never messaged) or 'warm' (story viewers).
    """
    if cooldown is None:
        cooldown = (RATE_LIMITS["dm_cooldown_min"], RATE_LIMITS["dm_cooldown_max"])

    # Show daily stats + ramp-up status
    ramp_day = db.get_ramp_day()
    today_sent = db.get_send_count("dm_total")
    if ramp_day <= RATE_LIMITS.get("ramp_up_days", 7):
        effective_max = RATE_LIMITS["ramp_up"].get(ramp_day, RATE_LIMITS["dm_daily_max"])
        logger.info("Day %d of ramp-up: %d/%d sent today", ramp_day, today_sent, effective_max)
    else:
        effective_max = RATE_LIMITS["dm_daily_max"]
        logger.info("Ramp complete. %d/%d sent today", today_sent, effective_max)

    remaining = effective_max - today_sent
    if remaining <= 0:
        logger.info("Daily limit reached — nothing to send")
        return
    if limit > remaining:
        logger.info("Clamping limit from %d to %d (daily allowance)", limit, remaining)
        limit = remaining

    # Night mode check (EST)
    from datetime import timezone, timedelta
    est_hour = datetime.now(timezone(timedelta(hours=-5))).hour
    if 0 <= est_hour < 6:
        logger.info("Night mode (EST) — no outbound between 12AM-6AM")
        return

    browser = IGBrowserSync()
    if not browser.connect():
        logger.error("Cannot connect to Chrome")
        return

    stats = {"sent": 0, "skipped_contacted": 0, "skipped_no_msg": 0,
             "skipped_error": 0, "total_checked": 0}

    try:
        _run_blitz_loop(browser, limit, dry_run, cooldown, stats, mode)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error("Blitz error: %s", e, exc_info=True)
    finally:
        browser.disconnect()

    logger.info("=== BLITZ RESULTS ===")
    logger.info("  Sent: %d", stats["sent"])
    logger.info("  Skipped (already contacted): %d", stats["skipped_contacted"])
    logger.info("  Skipped (no message btn): %d", stats["skipped_no_msg"])
    logger.info("  Skipped (error/gone): %d", stats["skipped_error"])
    logger.info("  Total checked: %d", stats["total_checked"])


def _run_blitz_loop(browser, limit, dry_run, cooldown, stats, mode="cold"):
    """Core loop — works inside the followers dialog."""

    loop = asyncio.get_event_loop()
    page = browser._async.page

    def _get_opener():
        """Get the opener based on mode."""
        if mode == "warm":
            return DM_SCRIPT["opener_story_new"]
        openers = DM_SCRIPT["opener_cold"]
        if isinstance(openers, list):
            return openers[0]  # Sabbo's exact opener
        return openers

    async def _open_followers_dialog():
        """Navigate to profile and open followers dialog. Returns True on success."""
        await page.goto(f"https://www.instagram.com/{OWN_IG_HANDLE}/")
        await asyncio.sleep(5)
        fl = await page.query_selector(
            f'a[href="/{OWN_IG_HANDLE}/followers/"]'
        )
        if not fl:
            fl = await page.query_selector('a[href*="/followers"]')
        if not fl:
            logger.error("Cannot find followers link")
            return False
        await fl.click()
        await asyncio.sleep(3)
        return True

    async def _get_follower_handles() -> List[str]:
        """Get all visible handles from the followers dialog."""
        handles = []
        links = await page.query_selector_all(
            'div[role="dialog"] a[href^="/"][role="link"]'
        )
        for link in links:
            try:
                href = await link.get_attribute("href")
                if not href or href.count("/") != 2:
                    continue
                handle = href.strip("/")
                skip = {"explore", "reels", "stories", "accounts", "p", "direct", ""}
                if handle and handle != OWN_IG_HANDLE and handle not in skip:
                    handles.append(handle)
            except Exception:
                continue
        return handles

    async def _scroll_followers_dialog():
        """Scroll down inside the followers dialog to load more.

        IG uses a scrollable div inside the dialog. We find it by looking
        for the element that actually has overflow scrolling, then scroll it.
        """
        # Find the actual scrollable container inside the dialog
        # It's the div that has a scrollHeight > clientHeight
        scrolled = await page.evaluate("""() => {
            const dialog = document.querySelector('div[role="dialog"]');
            if (!dialog) return false;
            // Find all divs in the dialog, pick the one that scrolls
            const divs = dialog.querySelectorAll('div');
            for (const div of divs) {
                if (div.scrollHeight > div.clientHeight + 10 && div.clientHeight > 100) {
                    div.scrollTop = div.scrollHeight;
                    return true;
                }
            }
            // Fallback: scroll the dialog itself
            dialog.scrollTop = dialog.scrollHeight;
            return true;
        }""")
        await asyncio.sleep(5)  # Wait for IG to lazy-load more followers
        return scrolled

    async def _dm_from_profile(handle: str):
        """Smart DM: reads existing thread, decides what to say, sends it.

        Returns:
        - ("sent", message_text) if DM sent successfully
        - ("followup", message_text) if follow-up sent to existing convo
        - False if can't DM
        """
        await page.goto(f"https://www.instagram.com/{handle}/")
        await asyncio.sleep(3)

        # Check error page
        try:
            body_text = await page.inner_text("body")
            if "Sorry, this page isn't available" in body_text:
                return False
        except Exception:
            pass

        # Find the Message button in the PROFILE HEADER (next to Follow)
        # NOT the DM inbox icon at the bottom of the page
        opened_dm = False

        # Path 1: Message button inside the header section
        header = await page.query_selector('header')
        if header:
            msg_btn = await header.query_selector(
                'div[role="button"]:has-text("Message"), '
                'button:has-text("Message")'
            )
            if msg_btn:
                try:
                    txt = (await msg_btn.inner_text()).strip().lower()
                    if txt == "message":
                        await msg_btn.click()
                        await asyncio.sleep(3)
                        opened_dm = True
                except Exception:
                    pass

        # Path 2: 3-dots menu → "Send message"
        if not opened_dm and header:
            more_btn = await header.query_selector(
                'svg[aria-label="Options"], button[aria-label="Options"]'
            )
            if more_btn:
                await more_btn.click()
                await asyncio.sleep(1.5)
                send_btn = await page.query_selector(
                    'button:has-text("Send message"), button:has-text("Send Message")'
                )
                if send_btn:
                    await send_btn.click()
                    await asyncio.sleep(3)
                    opened_dm = True
                else:
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)

        if not opened_dm:
            return False

        # ── CHECK FOR EXISTING THREAD (bulletproof) ─────────────────
        # Wait for thread to fully load
        await asyncio.sleep(2)
        current_url = page.url
        if "/direct/" not in current_url:
            return False  # Didn't navigate to DM thread

        # Strategy: look for empty-state indicators FIRST.
        # If we find one → definitely fresh thread → proceed.
        # If we DON'T find one → assume existing thread → skip.
        # This is the safe default: better to miss a prospect than double-message.
        is_fresh = False
        try:
            page_text = await page.inner_text("main")
            page_lower = page_text.lower()
            empty_indicators = [
                "no messages",
                "send a message",
                "start a conversation",
                "say something nice",
                "write a message",
            ]
            for indicator in empty_indicators:
                if indicator in page_lower:
                    is_fresh = True
                    break
        except Exception:
            pass

        if not is_fresh:
            logger.info("  @%s: existing thread detected — skipping", handle)
            return ("skip", None)

        # Fresh thread — send opener
        message_to_send = _get_opener()
        msg_type = "sent"

        msg_input = await page.query_selector('textarea[placeholder], div[contenteditable="true"][role="textbox"]')
        if not msg_input:
            return False

        await msg_input.click()
        await msg_input.fill(message_to_send)
        await asyncio.sleep(0.3)

        # Send with retry
        for attempt in range(3):
            await page.keyboard.press("Enter")
            await asyncio.sleep(3)
            try:
                body_check = await page.inner_text("body")
                if "something went wrong" in body_check.lower():
                    if attempt < 2:
                        await asyncio.sleep(3)
                        continue
                    return False
            except Exception:
                pass
            return (msg_type, message_to_send)

        return False

    async def _blitz():
        to_dm = []

        if mode == "warm":
            # ── WARM MODE: Pull story viewers from DB ────────────────
            logger.info("Phase 1 (warm): Loading story viewers from DB...")
            d = db.get_db()
            rows = d.execute(
                """SELECT p.ig_handle FROM prospects p
                   LEFT JOIN conversations c ON c.prospect_id = p.id
                   WHERE c.id IS NULL AND p.source = 'story_viewer'
                   ORDER BY p.created_at DESC"""
            ).fetchall()
            to_dm = [r["ig_handle"] for r in rows][:limit]
            stats["total_checked"] += len(to_dm)
            logger.info("Phase 1 complete: %d story viewers queued to DM", len(to_dm))

        else:
            # ── COLD MODE: Scroll followers list ─────────────────────
            logger.info("Phase 1 (cold): Opening followers list...")
            if not await _open_followers_dialog():
                logger.error("Failed to open followers dialog — aborting")
                return

            seen = set()
            scroll_rounds = 0
            max_scrolls = 50

            while len(to_dm) < limit and scroll_rounds < max_scrolls:
                handles = await _get_follower_handles()
                new_this_round = 0
                for handle in handles:
                    if handle in seen:
                        continue
                    seen.add(handle)
                    stats["total_checked"] += 1

                    # Check DB — already contacted?
                    prospect = db.get_prospect_by_handle(handle)
                    if prospect:
                        conv = db.get_conversation_by_prospect(prospect["id"])
                        if conv:
                            stats["skipped_contacted"] += 1
                            logger.info("  @%s — already contacted, skipping", handle)
                            continue

                    # Save to DB as new follower
                    if not prospect:
                        pid = db.upsert_prospect(
                            ig_handle=handle, source="new_follower",
                            source_detail="follower_blitz",
                        )
                        logger.info("  @%s — saved to DB (new follower)", handle)

                    to_dm.append(handle)
                    new_this_round += 1

                    if len(to_dm) >= limit:
                        break

                logger.info("Scroll %d: %d visible, %d new, %d queued to DM",
                            scroll_rounds + 1, len(handles), new_this_round, len(to_dm))

                if new_this_round == 0:
                    if scroll_rounds > 0:
                        logger.info("No new followers found — end of list")
                        break

                await _scroll_followers_dialog()
                scroll_rounds += 1

            # Close the dialog before DMing
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

            logger.info("Phase 1 complete: %d followers queued to DM", len(to_dm))

        # ── PHASE 2: DM each one from their profile ─────────────────
        fails = 0
        for handle in to_dm:
            if stats["sent"] >= limit:
                break

            # Store prospect if new
            prospect = db.get_prospect_by_handle(handle)
            if not prospect:
                pid = db.upsert_prospect(
                    ig_handle=handle, source="new_follower",
                    source_detail="follower_blitz",
                )
                prospect = db.get_prospect(pid)
            if not prospect:
                continue

            # Double-check not contacted (race condition guard)
            if db.get_conversation_by_prospect(prospect["id"]):
                stats["skipped_contacted"] += 1
                continue

            logger.info("@%s — DMing...", handle)

            if dry_run:
                logger.info("  [DRY RUN] \"%s\"", DM_SCRIPT["opener_cold"])
                stats["sent"] += 1
                continue

            dm_result = await _dm_from_profile(handle)

            if dm_result is False:
                stats["skipped_no_msg"] += 1
                fails += 1
                if fails >= 5:
                    logger.warning("5 consecutive failures — pausing 60s")
                    await asyncio.sleep(60)
                    fails = 0
                continue

            msg_type, message_text = dm_result
            fails = 0

            if msg_type == "skip":
                stats["skipped_contacted"] += 1
                continue
            
            if msg_type == "followup":
                # Existing convo — contextual follow-up was sent
                conv = db.get_conversation_by_prospect(prospect["id"])
                if not conv:
                    conv_id = db.create_conversation(
                        prospect_id=prospect["id"],
                        offer="amazon_os",
                        conversation_type="manual_prior",
                        stage="replied",
                    )
                else:
                    conv_id = conv["id"]
                db.add_message(conv_id, "out", message_text)
                db.update_prospect_status(prospect["id"], "contacted")
                db.increment_send_count("dm_followup")
                db.increment_send_count("dm_total")
                stats["sent"] += 1
                logger.info("  FOLLOW-UP (%d/%d): \"%s\"", stats["sent"], limit, message_text[:60])

            elif msg_type == "sent":
                # Fresh opener sent
                conv_type = "warm_story_blitz" if mode == "warm" else "cold_follower_blitz"
                conv_id = db.create_conversation(
                    prospect_id=prospect["id"],
                    offer="amazon_os",
                    conversation_type=conv_type,
                    stage="opener_sent",
                )
                db.add_message(conv_id, "out", message_text)
                db.update_prospect_status(prospect["id"], "contacted")
                db.increment_send_count("dm_cold")
                db.increment_send_count("dm_total")
                stats["sent"] += 1
                logger.info("  SENT (%d/%d)", stats["sent"], limit)

            db.update_watermark(OWN_IG_HANDLE, stats["total_checked"], handle)
            await asyncio.sleep(random.uniform(*cooldown))

    loop.run_until_complete(_blitz())


def main():
    parser = argparse.ArgumentParser(description="Follower Blitz — DM down the followers list")
    parser.add_argument("--mode", choices=["cold", "warm"], default="cold",
                        help="cold = followers never messaged, warm = story viewers")
    parser.add_argument("--limit", type=int, default=20, help="Max DMs to send")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--fast", action="store_true", help="Shorter cooldowns (15-30s)")
    args = parser.parse_args()

    logger.info("Mode: %s | Limit: %d | Fast: %s", args.mode, args.limit, args.fast)

    if args.fast:
        cooldown = (15, 30)
    else:
        cooldown = None
    run_blitz(limit=args.limit, dry_run=args.dry_run, cooldown=cooldown, mode=args.mode)


if __name__ == "__main__":
    main()
