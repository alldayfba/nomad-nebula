#!/usr/bin/env python3
"""
Follower Blitz — scroll-based follower collection + DM outbound.

Two phases:
  Phase 1 (Collect): Go to profile → click Followers → scroll down, saving
    every handle to the DB. Resumes from watermark so each run goes deeper.
    Over time, the DB has every single follower catalogued.
  Phase 2 (DM): Pick uncontacted followers from the DB → open DM thread →
    if thread is empty, send opener. If thread has messages, mark as contacted.

The DB is the single source of truth for who has/hasn't been reached out to.

Modes:
  cold  — Scroll followers list, DM only people we've NEVER messaged.
  warm  — DM story viewers who engaged but never got a DM.

Usage:
    python -m execution.setter.follower_blitz --mode cold --limit 50
    python -m execution.setter.follower_blitz --mode cold --limit 200 --fast
    python -m execution.setter.follower_blitz --collect-only  # just scroll + save, no DMs
    python -m execution.setter.follower_blitz --dm-only --limit 200  # skip scroll, DM from DB
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from execution.setter.ig_browser import IGBrowserSync
from execution.setter import setter_db as db
from execution.setter.setter_config import DM_SCRIPT, OWN_IG_HANDLE, RATE_LIMITS
from execution.setter.followup_engine import schedule_follow_ups, execute_due_follow_ups
from execution.setter.inbox_analyzer import run_analyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [blitz] %(message)s")
logger = logging.getLogger("blitz")


def run_blitz(limit: int = 20, dry_run: bool = False, cooldown: tuple = None,
              mode: str = "cold", collect_only: bool = False, dm_only: bool = False):
    """Scroll followers list, collect handles, DM uncontacted ones.

    Args:
        limit: Max DMs to send this run.
        dry_run: If True, generate openers but don't send.
        cooldown: (min_seconds, max_seconds) between DMs.
        mode: 'cold' (followers) or 'warm' (story viewers).
        collect_only: Just scroll and collect, no DMing.
        dm_only: Skip scrolling, DM from existing DB entries.
    """
    if cooldown is None:
        cooldown = (RATE_LIMITS["dm_cooldown_min"], RATE_LIMITS["dm_cooldown_max"])

    if not collect_only:
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
    if not getattr(run_blitz, '_no_night_mode', False) and not collect_only:
        est_hour = datetime.now(timezone(timedelta(hours=-5))).hour
        if 0 <= est_hour < 6:
            logger.info("Night mode (EST) — no outbound between 12AM-6AM")
            return

    browser = IGBrowserSync()
    if not browser.connect():
        logger.error("Cannot connect to Chrome")
        return

    stats = {"sent": 0, "skipped_contacted": 0, "skipped_no_msg": 0,
             "skipped_error": 0, "total_checked": 0, "collected": 0,
             "new_followers": 0, "skipped_blocklist": 0, "skipped_icp": 0}

    try:
        _run_blitz_loop(browser, limit, dry_run, cooldown, stats, mode,
                        collect_only, dm_only)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error("Blitz error: %s", e, exc_info=True)
    finally:
        browser.disconnect()

    logger.info("=== BLITZ RESULTS ===")
    logger.info("  Followers collected: %d (%d new)", stats["collected"], stats["new_followers"])
    logger.info("  DMs sent: %d", stats["sent"])
    logger.info("  Skipped (already contacted): %d", stats["skipped_contacted"])
    logger.info("  Skipped (blocklisted): %d", stats.get("skipped_blocklist", 0))
    logger.info("  Skipped (ICP mismatch): %d", stats.get("skipped_icp", 0))
    logger.info("  Skipped (not found/error): %d", stats["skipped_no_msg"])
    logger.info("  Total checked for DM: %d", stats["total_checked"])


def _run_blitz_loop(browser, limit, dry_run, cooldown, stats, mode="cold",
                    collect_only=False, dm_only=False):
    """Core loop — scroll followers, collect, DM."""

    loop = asyncio.get_event_loop()
    page = browser._async.page

    def _get_opener(handle: str = "", bio: str = ""):
        """Get a personalized opener based on the lead's profile."""
        if mode == "warm":
            return DM_SCRIPT["opener_story_new"]

        # If we have bio info, generate a personalized opener via AI
        if bio and len(bio) > 5:
            try:
                import subprocess
                prompt = f"""Write a cold DM opener for @{handle} who follows an Amazon FBA coaching account.

Their bio: "{bio}"

Rules:
- 1 sentence max, under 150 chars
- Casual, lowercase, like texting a friend (use "u" not "you", "ur" not "your")
- Reference something specific from their bio if relevant
- If bio mentions business/hustle/ecommerce → reference that
- If bio mentions a job/career → tie to side income or freedom
- If nothing useful in bio → use a generic Amazon opener
- Never be salesy. No emojis unless natural.
- Sabbo's voice: direct, chill, genuine curiosity

Examples of good openers:
- "yoo saw u do real estate too, ever look into amazon as another income stream?"
- "yooo u looking into amazon i see??"
- "noticed you're into fitness, ever thought about selling on amazon on the side?"

Return ONLY the message text, nothing else."""

                result = subprocess.run(
                    ["claude", "-p", "--model", "claude-haiku-4-5-20251001"],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    msg = result.stdout.strip().strip('"').strip("'")
                    if 5 < len(msg) < 200:
                        return msg
            except Exception:
                pass

        # Fallback: rotate through Sabbo's standard openers
        openers = DM_SCRIPT["opener_cold"]
        if isinstance(openers, list):
            import random as _rand
            return _rand.choice(openers)
        return openers

    # ── Phase 1: Scroll & Collect ──────────────────────────────────────────

    async def _scroll_and_collect() -> int:
        """Open profile → click Followers → scroll down, save every handle.

        Returns number of new followers added to DB.
        """
        logger.info("Phase 1: Scrolling followers list...")

        # Navigate to profile
        await page.goto(f"https://www.instagram.com/{OWN_IG_HANDLE}/")
        await asyncio.sleep(3)

        # Click the "followers" link/button
        followers_link = await page.query_selector(
            f'a[href="/{OWN_IG_HANDLE}/followers/"]'
        )
        if not followers_link:
            # Fallback: look for text containing follower count
            followers_link = await page.query_selector(
                'a[href*="followers"], '
                'div[role="button"]:has-text("followers")'
            )
        if not followers_link:
            logger.error("Cannot find Followers button on profile page")
            return 0

        await followers_link.click()
        await asyncio.sleep(3)

        # The followers modal/dialog should now be open
        # Find the scrollable container
        has_dialog = await page.evaluate("""() => {
            return !!document.querySelector('div[role="dialog"]');
        }""")
        if not has_dialog:
            logger.error("Cannot find followers dialog")
            return 0

        # Get watermark — where we left off last time
        watermark = db.get_watermark(OWN_IG_HANDLE)
        watermark_pos = watermark["last_position"] if watermark else 0
        logger.info("Watermark: position %d (last follower: %s)",
                    watermark_pos, watermark["last_follower_handle"] if watermark else "none")

        collected = 0
        new_count = 0
        seen_handles = set()
        no_new_rounds = 0
        max_no_new = 25  # Stop after 25 scroll rounds with no new handles
        while True:
            # Extract visible handles from the followers list
            handles = await page.evaluate("""() => {
                const dialog = document.querySelector('div[role="dialog"]');
                if (!dialog) return [];
                const links = dialog.querySelectorAll('a[href^="/"]');
                const handles = [];
                const seen = new Set();
                for (const a of links) {
                    const href = a.getAttribute('href');
                    if (href && href.match(/^\/[a-zA-Z0-9._]+\/?$/) && !href.includes('/p/')) {
                        const handle = href.replace(/\//g, '');
                        if (handle && !seen.has(handle) && handle !== '""" + OWN_IG_HANDLE + """') {
                            seen.add(handle);
                            handles.push(handle);
                        }
                    }
                }
                return handles;
            }""")

            new_in_round = 0
            for handle in handles:
                if handle in seen_handles:
                    continue
                seen_handles.add(handle)
                collected += 1

                # Save to DB
                existing = db.get_prospect_by_handle(handle)
                if not existing:
                    db.upsert_prospect(
                        ig_handle=handle,
                        source="follower_scroll",
                        source_detail="follower_blitz_collect",
                    )
                    new_count += 1
                    new_in_round += 1

            if new_in_round == 0:
                no_new_rounds += 1
            else:
                no_new_rounds = 0

            if no_new_rounds >= max_no_new:
                logger.info("No new followers in %d scroll rounds — reached end or stalled",
                            max_no_new)
                break

            # Log progress periodically
            if collected % 100 < 10:
                logger.info("Collected %d followers (%d new to DB)...",
                            collected, new_count)

            # Scroll using mouse wheel on the dialog
            dialog = await page.query_selector('div[role="dialog"]')
            if not dialog:
                # Dialog closed (user clicked off or IG glitch) — reopen
                logger.warning("Dialog closed — reopening followers list")
                followers_link = await page.query_selector(
                    f'a[href="/{OWN_IG_HANDLE}/followers/"]'
                )
                if followers_link:
                    await followers_link.click()
                    await asyncio.sleep(3)
                dialog = await page.query_selector('div[role="dialog"]')
                if not dialog:
                    logger.error("Cannot reopen followers dialog — stopping")
                    break
            if dialog:
                box = await dialog.bounding_box()
                if box:
                    # Hover over the dialog center and wheel-scroll down
                    await page.mouse.move(box["x"] + box["width"] / 2,
                                          box["y"] + box["height"] / 2)
                    await page.mouse.wheel(0, 600)

            # Wait for lazy load — IG fetches next batch when near bottom
            await asyncio.sleep(random.uniform(1.5, 2.5))

        # Update watermark
        if collected > 0:
            last_handle = list(seen_handles)[-1] if seen_handles else ""
            db.update_watermark(OWN_IG_HANDLE, watermark_pos + collected, last_handle)

        logger.info("Phase 1 complete: %d followers seen, %d new added to DB",
                    collected, new_count)
        stats["collected"] = collected
        stats["new_followers"] = new_count

        # Close the dialog
        try:
            close_btn = await page.query_selector(
                'div[role="dialog"] svg[aria-label="Close"], '
                'div[role="dialog"] button:has(svg)'
            )
            if close_btn:
                await close_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        return new_count

    # ── Phase 2: DM from DB ───────────────────────────────────────────────

    async def _dm_from_db():
        """Pick uncontacted followers from DB, open DM thread, send if fresh."""
        # Try priority queue first (smarter ordering by ICP + heat + recency)
        use_priority_queue = False
        try:
            from execution.setter.priority_queue import get_queue_for_blitz
            pq = get_queue_for_blitz(limit=limit * 3)
            if pq:
                candidates = [entry["ig_handle"] for entry in pq]
                use_priority_queue = True
                logger.info("Phase 2: Using priority queue (%d leads)", len(candidates))
        except Exception as pq_err:
            logger.debug("Priority queue unavailable: %s", pq_err)

        if not use_priority_queue:
            # Fallback to sequential order
            d = db.get_db()
            rows = d.execute(
                """SELECT p.ig_handle FROM prospects p
                   LEFT JOIN conversations c ON c.prospect_id = p.id
                   WHERE c.id IS NULL
                   AND p.source IN ('follower_scroll', 'new_follower')
                   ORDER BY p.created_at DESC
                   LIMIT ?""",
                (limit * 3,)  # Fetch extra in case many have existing threads
            ).fetchall()
            candidates = [r["ig_handle"] for r in rows]

        d = db.get_db()
        total_in_db = d.execute(
            "SELECT COUNT(*) FROM prospects WHERE source IN ('follower_scroll', 'new_follower')"
        ).fetchone()[0]
        contacted_count = d.execute(
            """SELECT COUNT(DISTINCT p.id) FROM prospects p
               JOIN conversations c ON c.prospect_id = p.id
               WHERE p.source IN ('follower_scroll', 'new_follower')"""
        ).fetchone()[0]

        logger.info("Phase 2: DB has %d followers total, %d contacted, %d uncontacted candidates%s",
                    total_in_db, contacted_count, len(candidates),
                    " (priority-ordered)" if use_priority_queue else "")

        if not candidates:
            logger.info("No uncontacted followers in DB — run with scroll first")
            return

        fails = 0
        for handle in candidates:
            if stats["sent"] >= limit:
                break

            # Blocklist check — never DM friends, students, creators
            if db.is_blocklisted(handle):
                logger.debug("Skipping @%s — blocklisted", handle)
                stats["skipped_blocklist"] = stats.get("skipped_blocklist", 0) + 1
                continue

            # ICP filter — skip prospects scored 0 with a real bio (not ICP)
            prospect_data = db.get_prospect_by_handle(handle)
            if prospect_data and prospect_data.get("icp_score", 0) == 0:
                # If they have a bio and scored 0, they're not ICP — skip
                if prospect_data.get("bio") and prospect_data["bio"] not in ("", "No bio", None):
                    logger.debug("Skipping @%s — ICP score 0 (not a match)", handle)
                    stats["skipped_icp"] = stats.get("skipped_icp", 0) + 1
                    continue
                # If no bio, we can't determine ICP yet — let them through

            stats["total_checked"] += 1
            logger.info("@%s — checking DM thread... (%d/%d sent)",
                        handle, stats["sent"], limit)

            if dry_run:
                logger.info("  [DRY RUN] \"%s\"", _get_opener()[:60])
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

            prospect = db.get_prospect_by_handle(handle)
            if not prospect:
                continue

            if msg_type == "skip":
                # Browser found existing thread — mark in DB
                if not db.get_conversation_by_prospect(prospect["id"], include_closed=True):
                    db.create_conversation(
                        prospect_id=prospect["id"],
                        offer="amazon_os",
                        conversation_type="manual_prior",
                        stage="replied",
                    )
                    db.update_prospect_status(prospect["id"], "contacted")
                    logger.info("  → existing thread, marked contacted in DB")
                stats["skipped_contacted"] += 1
                continue

            if msg_type == "followup":
                # Existing thread, no reply — sent "still with me??"
                conv = db.get_conversation_by_prospect(prospect["id"], include_closed=True)
                if not conv:
                    conv_id = db.create_conversation(
                        prospect_id=prospect["id"],
                        offer="amazon_os",
                        conversation_type="cold_follower_blitz",
                        stage="opener_sent",
                    )
                else:
                    conv_id = conv["id"]
                db.add_message(conv_id, "out", message_text)
                db.update_prospect_status(prospect["id"], "contacted")
                db.increment_send_count("dm_followup")
                db.increment_send_count("dm_total")
                if use_priority_queue:
                    db.mark_queue_sent(prospect["id"])
                stats["sent"] += 1
                logger.info("  FOLLOW-UP (%d/%d)", stats["sent"], limit)

            elif msg_type == "sent":
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
                if use_priority_queue:
                    db.mark_queue_sent(prospect["id"])
                stats["sent"] += 1
                logger.info("  SENT (%d/%d)", stats["sent"], limit)

                # Schedule follow-up cadence (5h, 1d, 3d, 7d, 14d)
                try:
                    schedule_follow_ups(conv_id)
                except Exception as fu_err:
                    logger.warning("  Follow-up scheduling failed: %s", fu_err)

            # Cooldown between DMs
            wait = random.uniform(cooldown[0], cooldown[1])
            await asyncio.sleep(wait)

    # ── DM Helper ──────────────────────────────────────────────────────────

    async def _dm_from_profile(handle: str):
        """Open a DM thread via /direct/new/, check for existing messages, send opener.

        Returns:
        - ("sent", message_text) if DM sent successfully
        - ("skip", None) if existing thread detected
        - False if can't DM (account gone, DMs closed, etc.)
        """
        # ── STEP 1: Open new-message flow and search for handle ────
        await page.goto("https://www.instagram.com/direct/new/")
        await asyncio.sleep(2)

        # Find the search input
        search_selector = (
            'input[placeholder*="earch"], '
            'input[name="queryBox"], '
            'input[name="searchInput"]'
        )
        search_input = await page.query_selector(search_selector)
        if not search_input:
            logger.warning("  @%s: search input not found", handle)
            return False

        await search_input.click()
        await asyncio.sleep(1)
        # Use type() not fill() — IG re-renders input on focus
        await page.type(search_selector, handle, delay=30)
        await asyncio.sleep(3)

        # Click the matching result + grab bio text from search result
        results = await page.query_selector_all('div[role="button"]')
        found_user = False
        result_bio = ""
        for result in results:
            try:
                txt = (await result.inner_text()).strip()
                if handle.lower() in txt.lower():
                    # Extract bio from the search result (format: "DisplayName\nhandle\nBio text")
                    lines = [l.strip() for l in txt.split("\n") if l.strip()]
                    # Bio is usually the last line (after name and handle)
                    if len(lines) >= 3:
                        result_bio = lines[-1]
                    await result.click()
                    found_user = True
                    await asyncio.sleep(2)
                    # Save bio to DB if we got one
                    if result_bio and len(result_bio) > 3:
                        prospect_rec = db.get_prospect_by_handle(handle)
                        if prospect_rec and not prospect_rec.get("bio"):
                            db.upsert_prospect(ig_handle=handle, bio=result_bio)
                    break
            except Exception:
                continue

        if not found_user:
            logger.info("  @%s: not found in search results", handle)
            return False

        # Click "Chat" / "Next" button
        for btn_text in ["Chat", "Next", "chat", "next"]:
            chat_btn = await page.query_selector(
                f'div[role="button"]:has-text("{btn_text}"), '
                f'button:has-text("{btn_text}")'
            )
            if chat_btn:
                try:
                    btn_label = (await chat_btn.inner_text()).strip().lower()
                    if btn_label in ("chat", "next"):
                        await chat_btn.click()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    continue

        # ── STEP 2: Verify we're in the thread ─────────────────────
        msg_input = await page.query_selector(
            'div[contenteditable="true"][role="textbox"], '
            'textarea[placeholder*="essage"], '
            'p[contenteditable="true"]'
        )
        if not msg_input:
            logger.info("  @%s: thread didn't open (no input found)", handle)
            return False

        # ── STEP 3: Check thread state — fresh vs has messages ──────
        # Instead of matching specific opener text, detect ANY messages in thread.
        # If thread has messages → "still with me??" follow-up.
        # If truly empty → cold opener.
        try:
            thread_state = await page.evaluate("""() => {
                const body = document.body.innerText.toLowerCase();
                // Check for "send a message" empty state → fresh thread
                const emptyIndicators = [
                    'send a message to start a chat',
                    'say something nice',
                    'send the first message',
                    'start a conversation',
                ];
                for (const ind of emptyIndicators) {
                    if (body.includes(ind)) return 'fresh';
                }
                // If we're still on /direct/new/ URL, it's fresh
                if (window.location.href.includes('/direct/new/')) return 'fresh';
                // Thread exists with messages — check for outbound (ours) vs inbound
                const main = document.querySelector('main') || document.querySelector('section');
                if (!main) return 'fresh';
                const allDivs = main.querySelectorAll('div[dir="auto"]');
                const skip = new Set(['', 'message...', 'active now', 'active today',
                    'send a message to start a chat.', 'message', 'audio', 'video']);
                let hasOurs = false, hasTheirs = false;
                for (const el of allDivs) {
                    const t = el.textContent.trim();
                    if (!t || t.length < 2 || skip.has(t.toLowerCase())) continue;
                    let node = el, isOurs = false;
                    for (let i = 0; i < 5; i++) {
                        if (!node.parentElement) break;
                        node = node.parentElement;
                        const s = window.getComputedStyle(node);
                        if (s.marginInlineStart === 'auto' || s.marginLeft === 'auto' ||
                            s.justifyContent === 'flex-end' || s.alignSelf === 'flex-end') {
                            isOurs = true; break;
                        }
                    }
                    if (isOurs) hasOurs = true;
                    else hasTheirs = true;
                }
                if (hasOurs && hasTheirs) return 'they_replied';
                if (hasOurs) return 'we_sent_no_reply';
                if (hasTheirs) return 'they_messaged_us';
                return 'has_thread';
            }""")
        except Exception as e:
            logger.warning("  @%s: thread check error: %s", handle, e)
            thread_state = "has_thread"

        if thread_state == "they_replied":
            # Active convo — they replied, skip
            logger.info("  @%s: they replied — skipping", handle)
            return ("skip", None)

        if thread_state in ("we_sent_no_reply", "has_thread", "they_messaged_us"):
            # Existing thread, no recent reply from them → "still with me??"
            logger.info("  @%s: existing thread (%s) — sending follow-up", handle, thread_state)
            message_to_send = "still with me??"
            await msg_input.click()
            await asyncio.sleep(0.3)
            tag = await msg_input.evaluate("el => el.tagName")
            if tag.lower() in ("div", "p"):
                await msg_input.type(message_to_send, delay=20)
            else:
                await msg_input.fill(message_to_send)
            await asyncio.sleep(0.3)
            for attempt in range(3):
                await page.keyboard.press("Enter")
                await asyncio.sleep(1.5)
                try:
                    body_check = await page.inner_text("body")
                    if "something went wrong" in body_check.lower():
                        if attempt < 2: await asyncio.sleep(3); continue
                        return False
                except Exception: pass
                return ("followup", message_to_send)
            return False

        # ── STEP 4: Fresh thread — send personalized cold opener ──
        # Use bio from search result or DB
        _prospect = db.get_prospect_by_handle(handle)
        _bio = result_bio or (_prospect.get("bio", "") if _prospect else "")
        message_to_send = _get_opener(handle=handle, bio=_bio)
        await msg_input.click()
        await asyncio.sleep(0.3)

        tag = await msg_input.evaluate("el => el.tagName")
        if tag.lower() == "div":
            await msg_input.type(message_to_send, delay=20)
        else:
            await msg_input.fill(message_to_send)
        await asyncio.sleep(0.3)

        # Send with retry
        for attempt in range(3):
            await page.keyboard.press("Enter")
            await asyncio.sleep(1.5)
            try:
                body_check = await page.inner_text("body")
                if "something went wrong" in body_check.lower():
                    if attempt < 2:
                        await asyncio.sleep(3)
                        continue
                    return False
            except Exception:
                pass
            return ("sent", message_to_send)

        return False

    # ── Main Orchestration ─────────────────────────────────────────────────

    async def _blitz():
        if mode == "warm":
            # Warm mode: pull story viewers from DB, DM them
            logger.info("Phase 1 (warm): Loading story viewers from DB...")
            d = db.get_db()
            rows = d.execute(
                """SELECT p.ig_handle FROM prospects p
                   LEFT JOIN conversations c ON c.prospect_id = p.id
                   WHERE c.id IS NULL AND p.source = 'story_viewer'
                   ORDER BY p.created_at DESC"""
            ).fetchall()
            # For warm mode, go straight to DM phase
            if rows:
                logger.info("%d story viewers ready to DM", len(rows))
            await _dm_from_db()
            return

        # Cold mode: Scroll + Collect → DM
        if not dm_only:
            await _scroll_and_collect()

        if not collect_only:
            await _dm_from_db()

    loop.run_until_complete(_blitz())


def run_follow_ups(limit: int = 50):
    """Execute due follow-ups from DB."""
    browser = IGBrowserSync()
    if not browser.connect():
        logger.error("Cannot connect to Chrome")
        return

    try:
        stats = execute_due_follow_ups(browser)
        logger.info("=== FOLLOW-UP RESULTS ===")
        logger.info("  Sent: %d | Skipped: %d | Errors: %d",
                    stats.get("sent", 0), stats.get("skipped", 0), stats.get("errors", 0))
    except Exception as e:
        logger.error("Follow-up error: %s", e, exc_info=True)
    finally:
        browser.disconnect()


def run_inbox():
    """Check inbox for replies, generate AI responses."""
    from execution.setter.ig_conversation import process_inbox

    browser = IGBrowserSync()
    if not browser.connect():
        logger.error("Cannot connect to Chrome")
        return

    try:
        stats = process_inbox(browser)
        logger.info("=== INBOX RESULTS ===")
        logger.info("  Processed: %d | Sent: %d | Escalated: %d | Errors: %d",
                    stats.get("processed", 0), stats.get("sent", 0),
                    stats.get("escalated", 0), stats.get("errors", 0))
    except Exception as e:
        logger.error("Inbox error: %s", e, exc_info=True)
    finally:
        browser.disconnect()


def run_full_cycle(limit: int = 200, fast: bool = False):
    """Full SDR cycle: scroll → inbox → follow-ups → new openers."""
    from execution.setter.ig_conversation import process_inbox

    cooldown = (15, 30) if fast else None

    browser = IGBrowserSync()
    if not browser.connect():
        logger.error("Cannot connect to Chrome")
        return

    try:
        # 1. Scroll & collect new followers
        logger.info("═══ PHASE 1: Scroll & Collect ═══")
        stats_collect = {"sent": 0, "skipped_contacted": 0, "skipped_no_msg": 0,
                         "skipped_error": 0, "total_checked": 0, "collected": 0,
                         "new_followers": 0, "skipped_blocklist": 0, "skipped_icp": 0}
        _run_blitz_loop(browser, limit, False, cooldown or (30, 90), stats_collect,
                        mode="cold", collect_only=True, dm_only=False)
        logger.info("  Collected %d followers (%d new)",
                    stats_collect["collected"], stats_collect["new_followers"])

        # 2. Analyze inbox — AI reads every DM, classifies, generates next messages
        logger.info("═══ PHASE 2: Analyze Inbox (AI) ═══")
        try:
            run_analyzer(mode="auto", limit=min(limit, 30), fast=fast)
            logger.info("  Inbox analysis + auto-send complete")
        except Exception as e:
            logger.warning("  Analyzer error (non-fatal): %s", e)

        # 3. Execute due follow-ups
        logger.info("═══ PHASE 3: Follow-Ups ═══")
        fu_stats = execute_due_follow_ups(browser)
        logger.info("  Sent: %d | Skipped: %d",
                    fu_stats.get("sent", 0), fu_stats.get("skipped", 0))

        # 4. Send new openers
        logger.info("═══ PHASE 4: New Openers ═══")
        stats_dm = {"sent": 0, "skipped_contacted": 0, "skipped_no_msg": 0,
                    "skipped_error": 0, "total_checked": 0, "collected": 0,
                    "new_followers": 0, "skipped_blocklist": 0, "skipped_icp": 0}
        _run_blitz_loop(browser, limit, False, cooldown or (30, 90), stats_dm,
                        mode="cold", collect_only=False, dm_only=True)
        logger.info("  Sent: %d new openers", stats_dm["sent"])

        # Summary
        logger.info("═══ FULL CYCLE COMPLETE ═══")
        logger.info("  New followers: %d | Follow-ups: %d | New DMs: %d",
                    stats_collect["new_followers"],
                    fu_stats.get("sent", 0), stats_dm["sent"])

    except Exception as e:
        logger.error("Full cycle error: %s", e, exc_info=True)
    finally:
        browser.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Follower Blitz — full SDR pipeline")
    parser.add_argument("--mode", choices=["cold", "warm"], default="cold",
                        help="cold = followers, warm = story viewers")
    parser.add_argument("--limit", type=int, default=20, help="Max DMs to send")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--fast", action="store_true", help="Shorter cooldowns (15-30s)")
    parser.add_argument("--collect-only", action="store_true",
                        help="Just scroll and collect followers to DB, no DMing")
    parser.add_argument("--dm-only", action="store_true",
                        help="Skip scroll phase, DM from existing DB entries")
    parser.add_argument("--follow-ups", action="store_true",
                        help="Execute due follow-ups from DB")
    parser.add_argument("--inbox", action="store_true",
                        help="Check inbox for replies, generate AI responses")
    parser.add_argument("--full-cycle", action="store_true",
                        help="Full SDR: scroll → inbox → follow-ups → new openers")
    parser.add_argument("--no-night-mode", action="store_true",
                        help="Disable night mode — allow sends 12AM-6AM EST")
    args = parser.parse_args()

    if args.no_night_mode:
        run_blitz._no_night_mode = True

    if args.full_cycle:
        logger.info("Full cycle | Limit: %d | Fast: %s", args.limit, args.fast)
        run_full_cycle(limit=args.limit, fast=args.fast)
    elif args.follow_ups:
        logger.info("Follow-ups mode | Limit: %d", args.limit)
        run_follow_ups(limit=args.limit)
    elif args.inbox:
        logger.info("Inbox mode")
        run_inbox()
    else:
        logger.info("Mode: %s | Limit: %d | Collect-only: %s | DM-only: %s | Fast: %s",
                    args.mode, args.limit, args.collect_only, args.dm_only, args.fast)
        cooldown = (15, 30) if args.fast else None
        run_blitz(
            limit=args.limit,
            dry_run=args.dry_run,
            cooldown=cooldown,
            mode=args.mode,
            collect_only=args.collect_only,
            dm_only=args.dm_only,
        )


if __name__ == "__main__":
    main()
