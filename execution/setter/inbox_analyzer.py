#!/usr/bin/env python3
"""
Inbox Analyzer — AI-powered DM conversation scanner.

Scrolls through every DM thread, classifies each as lead vs friend/creator,
analyzes the conversation state, and generates the optimal next message for leads.

Filters:
  - SKIP if we follow them (friend/creator/mutual)
  - SKIP if they don't follow us (random DM)
  - ONLY process people who follow us and we don't follow back (leads)

Modes:
  analyze  — Scan inbox, classify, summarize, save analysis to DB (no sends)
  auto     — Analyze + auto-send the best next message for each lead
  review   — Show analysis results from last scan

Usage:
    python -m execution.setter.inbox_analyzer --mode analyze --limit 50
    python -m execution.setter.inbox_analyzer --mode auto --limit 20 --fast
    python -m execution.setter.inbox_analyzer --mode review
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from execution.setter.ig_browser import IGBrowserSync
from execution.setter import setter_db as db
from execution.setter.setter_config import DM_SCRIPT, OWN_IG_HANDLE, RATE_LIMITS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [analyzer] %(message)s")
logger = logging.getLogger("analyzer")

# ── DB Schema Extension ────────────────────────────────────────────────────────

ANALYSIS_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    ig_handle TEXT NOT NULL,
    thread_id TEXT,
    classification TEXT NOT NULL,
    stage TEXT,
    summary TEXT,
    their_last_message TEXT,
    our_last_message TEXT,
    last_message_direction TEXT,
    hours_since_last TEXT,
    suggested_message TEXT,
    send_priority INTEGER DEFAULT 0,
    sent INTEGER DEFAULT 0,
    analyzed_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
"""


def _ensure_analysis_table():
    """Create the analysis table if it doesn't exist."""
    d = db.get_db()
    d.executescript(ANALYSIS_SCHEMA)


def _classify_with_ai(handle: str, messages: List[Dict], bio: str = "") -> Dict:
    """Use Claude to classify and analyze a DM conversation.

    Returns: {
        classification: 'lead' | 'friend' | 'creator' | 'spam' | 'dead',
        stage: str,  # opener_sent, interested, qualifying, objection, cold, booked
        summary: str,  # 1-2 sentence summary
        suggested_message: str,  # exact message to send next
        send_priority: int,  # 1-10 (10 = send immediately)
        reasoning: str,
    }
    """
    # Build conversation transcript
    transcript = ""
    for msg in messages[-20:]:  # Last 20 messages max
        direction = "US" if msg.get("direction") == "out" else "THEM"
        transcript += f"{direction}: {msg.get('content', '[media]')}\n"

    if not transcript.strip():
        return {
            "classification": "dead",
            "stage": "no_messages",
            "summary": "Empty thread",
            "suggested_message": "",
            "send_priority": 0,
            "reasoning": "No messages in thread",
        }

    prompt = f"""Analyze this Instagram DM conversation between us (@{OWN_IG_HANDLE}, an Amazon FBA coaching business) and @{handle}.

Bio: {bio or 'unknown'}

Conversation:
{transcript}

Classify and respond with ONLY valid JSON:
{{
    "classification": "lead" or "friend" or "creator" or "spam" or "dead" or "stalled_booking",
    "stage": "opener_sent" or "interested" or "qualifying" or "objection" or "cold" or "warm" or "hot" or "booked" or "no_show" or "stalled" or "dead",
    "summary": "1-2 sentence summary of where this convo stands",
    "suggested_message": "the exact DM to send next (casual, lowercase, Sabbo's voice — short, direct, no emojis unless natural). Leave empty if no message needed.",
    "send_priority": 1-10 (10 = they're hot and waiting, 1 = dead lead),
    "reasoning": "why this classification and message"
}}

Rules:
- "lead" = someone interested in Amazon FBA, making money, or our coaching
- "friend" = someone we have a personal relationship with
- "creator" = another content creator, coach, or business we network with
- "dead" = no response after multiple follow-ups, or explicitly not interested
- "stalled_booking" = was interested/qualified but stalled: sent booking link but didn't book, booked but no-showed, or showed but didn't pay/sign up
- For stalled_booking: suggest a re-engagement message specific to their stall point:
  - Didn't book after getting link: "hey did you get a chance to pick a time?"
  - No-showed the call: "hey looks like we missed each other, want to rebook?"
  - Had the call but didn't start: "hey any questions about getting started?"
- If they asked a question and we haven't responded, priority should be 9-10
- If we sent last and they haven't replied, suggest a follow-up based on how long ago
- If the convo is clearly dead (months old, no engagement), classification = "dead"
- Keep messages SHORT (under 200 chars), casual, like texting a friend
- Never be salesy. Never use "I" capitalized. Use "i" lowercase like texting
- Reference their specific situation when possible
"""

    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "claude-haiku-4-5-20251001", "--output-format", "json"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Claude CLI error for @%s: %s", handle, result.stderr[:200])
            return _fallback_classification(messages)

        # Parse the JSON response from Claude
        output = result.stdout.strip()
        # Claude --output-format json wraps in {"result": "..."}
        try:
            wrapper = json.loads(output)
            if "result" in wrapper:
                output = wrapper["result"]
        except (json.JSONDecodeError, TypeError):
            pass

        # Extract JSON from the response
        json_match = None
        if isinstance(output, str):
            # Try to find JSON in the output
            import re
            json_pattern = re.search(r'\{[^{}]*"classification"[^{}]*\}', output, re.DOTALL)
            if json_pattern:
                json_match = json_pattern.group()
            else:
                json_match = output

        analysis = json.loads(json_match)
        return analysis

    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception) as e:
        logger.warning("Analysis failed for @%s: %s", handle, e)
        return _fallback_classification(messages)


def _fallback_classification(messages: List[Dict]) -> Dict:
    """Basic heuristic classification when AI fails."""
    if not messages:
        return {"classification": "dead", "stage": "no_messages", "summary": "Empty",
                "suggested_message": "", "send_priority": 0, "reasoning": "fallback"}

    last_msg = messages[-1]
    last_direction = last_msg.get("direction", "out")

    if last_direction == "in":
        # They sent last — we need to respond!
        return {
            "classification": "lead",
            "stage": "needs_response",
            "summary": f"They sent last: \"{last_msg.get('content', '')[:60]}\"",
            "suggested_message": "",
            "send_priority": 9,
            "reasoning": "fallback — they sent last, needs human review",
        }
    else:
        return {
            "classification": "lead",
            "stage": "waiting",
            "summary": f"We sent last: \"{last_msg.get('content', '')[:60]}\"",
            "suggested_message": "still with me?",
            "send_priority": 3,
            "reasoning": "fallback — we sent last",
        }


def run_analyzer(mode: str = "analyze", limit: int = 50, fast: bool = False):
    """Main analyzer entry point."""
    _ensure_analysis_table()

    if mode == "review":
        _show_review()
        return

    browser = IGBrowserSync()
    if not browser.connect():
        logger.error("Cannot connect to Chrome")
        return

    stats = {"scanned": 0, "leads": 0, "friends": 0, "creators": 0,
             "dead": 0, "sent": 0, "errors": 0}

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_analyze_inbox(browser, mode, limit, fast, stats))
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error("Analyzer error: %s", e, exc_info=True)
    finally:
        browser.disconnect()

    logger.info("=== ANALYZER RESULTS ===")
    logger.info("  Scanned: %d", stats["scanned"])
    logger.info("  Leads: %d | Friends: %d | Creators: %d | Dead: %d",
                stats["leads"], stats["friends"], stats["creators"], stats["dead"])
    if mode == "auto":
        logger.info("  Messages sent: %d", stats["sent"])
    logger.info("  Errors: %d", stats["errors"])


async def _analyze_inbox(browser, mode, limit, fast, stats):
    """Scroll through DM inbox, analyze each thread."""
    page = browser._async.page

    # Navigate to inbox
    await page.goto("https://www.instagram.com/direct/inbox/")
    await asyncio.sleep(3)

    analyzed_handles = set()
    d = db.get_db()

    # Parse inbox thread list — IG shows name + preview for each thread
    # Format: [Name] [Preview/last message] [time]
    # Much faster than clicking into each thread
    for scroll_round in range(10):
        if stats["scanned"] >= limit:
            break

        # Extract threads from the inbox list with their preview messages
        threads = await page.evaluate("""() => {
            const threads = [];
            const seen = new Set();
            // Get all profile pics to identify threads
            const imgs = document.querySelectorAll('img[alt*="profile picture"]');
            for (const img of imgs) {
                const alt = img.getAttribute('alt') || '';
                const match = alt.match(/^(.+?)(?:'s| 's) profile picture$/i);
                if (!match) continue;
                const handle = match[1].trim();
                if (seen.has(handle) || handle === '""" + OWN_IG_HANDLE + """') continue;

                // Skip Notes/Stories bubbles at the top — they're small circular imgs
                // in a horizontal scroll container. DM thread pics are larger.
                const imgRect = img.getBoundingClientRect();
                if (imgRect.width < 50 || imgRect.height < 50) continue;
                // Also skip if inside a horizontal scrolling container (Notes row)
                let parent = img.parentElement;
                let isNote = false;
                for (let i = 0; i < 5 && parent; i++) {
                    const ps = window.getComputedStyle(parent);
                    if (ps.overflowX === 'auto' || ps.overflowX === 'scroll' ||
                        ps.display === 'flex' && ps.flexDirection === 'row') {
                        // Check if this is a horizontal list (Notes)
                        const siblings = parent.children;
                        if (siblings.length > 3) { isNote = true; break; }
                    }
                    parent = parent.parentElement;
                }
                if (isNote) continue;

                seen.add(handle);

                // Walk up to the thread row container
                let row = img;
                for (let i = 0; i < 8; i++) {
                    if (!row.parentElement) break;
                    row = row.parentElement;
                    // Stop at the row level (has multiple spans = name + preview)
                    const spans = row.querySelectorAll('span[dir="auto"]');
                    if (spans.length >= 2) break;
                }

                // Extract all text spans from the row
                const spans = row.querySelectorAll('span[dir="auto"]');
                let name = '', preview = '', time = '';
                const texts = [];
                spans.forEach(s => {
                    const t = s.textContent.trim();
                    if (t && t.length > 0) texts.push(t);
                });

                // First meaningful text = display name, last = preview or time
                if (texts.length >= 1) name = texts[0];
                if (texts.length >= 2) preview = texts.slice(1).join(' | ');

                threads.push({handle, name, preview: preview.substring(0, 200)});
            }
            return threads;
        }""")

        for thread in threads:
            if stats["scanned"] >= limit:
                break

            handle = thread.get("handle", "")
            name = thread.get("name", handle)
            preview = thread.get("preview", "")

            if handle in analyzed_handles or not handle:
                continue
            analyzed_handles.add(handle)

            stats["scanned"] += 1

            # Quick filter: check DB if we follow them
            prospect = db.get_prospect_by_handle(handle)

            # Determine if it's a lead thread based on preview
            # "You: ..." means we sent last (follow-up candidate)
            # No "You:" means they sent last (hot — respond NOW)
            we_sent_last = preview.startswith("You:")
            their_msg = preview if not we_sent_last else ""
            our_msg = preview[4:].strip() if we_sent_last else ""

            logger.info("Scanning %d/%d: @%s | %s",
                        stats["scanned"], limit, handle,
                        preview[:60] if preview else "no preview")

            # Build a simple message list from the preview for AI analysis
            messages = []
            if our_msg:
                messages.append({"direction": "out", "content": our_msg})
            elif their_msg:
                messages.append({"direction": "in", "content": their_msg})

            # For high-value analysis, click into the thread to read full history
            # Click the thread to load full conversation
            clicked = await page.evaluate("""(targetHandle) => {
                const imgs = document.querySelectorAll('img[alt*="profile picture"]');
                for (const img of imgs) {
                    const alt = img.getAttribute('alt') || '';
                    if (!alt.toLowerCase().includes(targetHandle.toLowerCase())) continue;
                    // Skip small images (Notes bubbles)
                    const rect = img.getBoundingClientRect();
                    if (rect.width < 50 || rect.height < 50) continue;
                    const c = img.closest('div[role="button"]') ||
                              img.closest('[tabindex]') ||
                              img.parentElement?.parentElement?.parentElement;
                    if (c) { c.click(); return true; }
                }
                return false;
            }""", handle)

            if clicked:
                await asyncio.sleep(3)

                # Check if we follow them (friends/creators → skip)
                we_follow = await page.evaluate("""() => {
                    const btns = document.querySelectorAll('button, div[role="button"]');
                    for (const btn of btns) {
                        const text = btn.textContent.trim().toLowerCase();
                        if (text === 'following' || text === 'requested') return true;
                    }
                    return false;
                }""")

                if we_follow:
                    logger.info("  @%s: we follow them — skipping (friend/creator)", handle)
                    stats["friends"] += 1
                    continue

                # Read full thread messages from the right panel
                full_messages = await _read_thread_messages(page)
                if full_messages:
                    messages = full_messages

            if not messages:
                logger.info("  @%s: no messages — skipping", handle)
                stats["dead"] += 1
                continue

            # Get prospect bio if we have it
            prospect = db.get_prospect_by_handle(handle)
            bio = prospect.get("bio", "") if prospect else ""

            # AI analysis
            logger.info("  @%s: analyzing %d messages...", handle, len(messages))
            analysis = _classify_with_ai(handle, messages, bio)

            classification = analysis.get("classification", "unknown")
            logger.info("  @%s: %s | %s | priority: %d | %s",
                        handle, classification, analysis.get("stage", "?"),
                        analysis.get("send_priority", 0),
                        analysis.get("summary", "")[:80])

            # Track stats
            if classification == "lead":
                stats["leads"] += 1
            elif classification == "friend":
                stats["friends"] += 1
            elif classification == "creator":
                stats["creators"] += 1
            else:
                stats["dead"] += 1

            # Find last messages for storage
            their_last = ""
            our_last = ""
            last_direction = ""
            for msg in reversed(messages):
                if msg.get("direction") == "in" and not their_last:
                    their_last = msg.get("content", "")[:200]
                if msg.get("direction") == "out" and not our_last:
                    our_last = msg.get("content", "")[:200]
                if not last_direction:
                    last_direction = msg.get("direction", "")
                if their_last and our_last:
                    break

            # Get conversation_id if exists
            conv_id = None
            if prospect:
                conv = db.get_conversation_by_prospect(prospect["id"], include_closed=True)
                if conv:
                    conv_id = conv["id"]

            # Save analysis to DB
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            d.execute(
                """INSERT INTO conversation_analysis
                   (conversation_id, ig_handle, thread_id, classification, stage,
                    summary, their_last_message, our_last_message,
                    last_message_direction, suggested_message, send_priority,
                    analyzed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (conv_id, handle, None, classification,
                 analysis.get("stage", ""),
                 analysis.get("summary", ""),
                 their_last, our_last, last_direction,
                 analysis.get("suggested_message", ""),
                 analysis.get("send_priority", 0),
                 now)
            )
            d.commit()

            # Auto-send mode: send the suggested message for high-priority leads
            if mode == "auto" and classification == "lead":
                suggested = analysis.get("suggested_message", "")
                priority = analysis.get("send_priority", 0)

                if suggested and priority >= 5:
                    logger.info("  → Sending: \"%s\"", suggested[:60])

                    # Find message input and send
                    msg_input = await page.query_selector(
                        'div[contenteditable="true"][role="textbox"], '
                        'textarea[placeholder*="essage"], '
                        'p[contenteditable="true"]'
                    )
                    if msg_input:
                        await msg_input.click()
                        await asyncio.sleep(0.3)
                        tag = await msg_input.evaluate("el => el.tagName")
                        if tag.lower() in ("div", "p"):
                            await msg_input.type(suggested, delay=20)
                        else:
                            await msg_input.fill(suggested)
                        await asyncio.sleep(0.3)
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(1.5)

                        # Mark as sent in analysis
                        d.execute(
                            "UPDATE conversation_analysis SET sent = 1 WHERE ig_handle = ? AND analyzed_at = ?",
                            (handle, now)
                        )
                        d.commit()
                        stats["sent"] += 1

                        # Cooldown
                        wait = random.uniform(15, 30) if fast else random.uniform(30, 60)
                        await asyncio.sleep(wait)

            # Navigate back to inbox for next thread
            await page.goto("https://www.instagram.com/direct/inbox/")
            await asyncio.sleep(2)

        # Scroll inbox for more threads
        await page.mouse.wheel(0, 600)
        await asyncio.sleep(2)


async def _read_thread_messages(page) -> List[Dict]:
    """Read messages from the currently open thread (right panel in split view)."""

    msg_data = await page.evaluate("""() => {
        const messages = [];
        const skip = new Set([
            '', 'message...', 'active now', 'active today', 'send a message to start a chat.',
            'primary', 'general', 'requests', 'home', 'reels', 'messages', 'search',
            'explore', 'notifications', 'create', 'dashboard', 'profile', 'more',
            'also from meta', 'your note', 'new message'
        ]);

        // IG split-pane: messages are in the right section
        // Find all text elements and filter to actual message content
        const allText = document.querySelectorAll('div[dir="auto"], span[dir="auto"]');
        const seenTexts = new Set();

        for (const el of allText) {
            const text = el.textContent.trim();
            if (!text || text.length < 2 || text.length > 1000) continue;
            if (skip.has(text.toLowerCase())) continue;
            if (seenTexts.has(text)) continue;

            // Skip navigation, thread names, and timestamps
            // Timestamps are short numbers like "1m", "2h", "3d"
            if (text.match(/^\\d+[mhdsw]$/)) continue;
            // Skip thread preview items (they contain profile names)
            if (el.closest('img[alt*="profile picture"]')?.parentElement) continue;

            // Determine if this is in the message area (right panel)
            // Messages in the right panel are typically deeper in the DOM
            const depth = (function(node) {
                let d = 0;
                while (node.parentElement) { d++; node = node.parentElement; }
                return d;
            })(el);

            // Skip shallow elements (nav, sidebar) — messages are deep (15+ levels)
            if (depth < 12) continue;

            seenTexts.add(text);

            // Determine direction: check if any ancestor has flex-end alignment
            let direction = 'in';
            let node = el;
            for (let i = 0; i < 6; i++) {
                if (!node.parentElement) break;
                node = node.parentElement;
                const style = window.getComputedStyle(node);
                if (style.justifyContent === 'flex-end' ||
                    style.alignSelf === 'flex-end' ||
                    style.marginInlineStart === 'auto' ||
                    style.marginLeft === 'auto') {
                    direction = 'out';
                    break;
                }
            }

            messages.push({content: text.substring(0, 500), direction: direction});
        }
        return messages;
    }""")

    return msg_data if msg_data else []


def _show_review():
    """Show analysis results from last scan."""
    _ensure_analysis_table()
    d = db.get_db()

    # Summary
    total = d.execute("SELECT COUNT(*) FROM conversation_analysis").fetchone()[0]
    if total == 0:
        logger.info("No analysis results yet. Run with --mode analyze first.")
        return

    leads = d.execute(
        "SELECT COUNT(*) FROM conversation_analysis WHERE classification = 'lead'"
    ).fetchone()[0]
    print(f"\n=== INBOX ANALYSIS ({total} conversations) ===\n")

    # Classification breakdown
    classes = d.execute(
        "SELECT classification, COUNT(*) as c FROM conversation_analysis GROUP BY classification ORDER BY c DESC"
    ).fetchall()
    for r in classes:
        print(f"  {r['classification']}: {r['c']}")

    # Hot leads (priority >= 7)
    hot = d.execute(
        """SELECT ig_handle, stage, summary, suggested_message, send_priority, sent
           FROM conversation_analysis
           WHERE classification = 'lead' AND send_priority >= 7
           ORDER BY send_priority DESC
           LIMIT 20"""
    ).fetchall()

    if hot:
        print(f"\n=== HOT LEADS (priority >= 7) ===\n")
        for r in hot:
            sent_marker = " [SENT]" if r["sent"] else ""
            print(f"  @{r['ig_handle']} (priority {r['send_priority']}){sent_marker}")
            print(f"    Stage: {r['stage']}")
            print(f"    Summary: {r['summary']}")
            if r["suggested_message"]:
                print(f"    Next msg: \"{r['suggested_message']}\"")
            print()

    # Warm leads (priority 4-6)
    warm = d.execute(
        """SELECT ig_handle, stage, summary, suggested_message, send_priority
           FROM conversation_analysis
           WHERE classification = 'lead' AND send_priority BETWEEN 4 AND 6
           ORDER BY send_priority DESC
           LIMIT 10"""
    ).fetchall()

    if warm:
        print(f"=== WARM LEADS (priority 4-6) ===\n")
        for r in warm:
            print(f"  @{r['ig_handle']} (priority {r['send_priority']})")
            print(f"    {r['summary']}")
            if r["suggested_message"]:
                print(f"    Next msg: \"{r['suggested_message']}\"")
            print()


def main():
    parser = argparse.ArgumentParser(description="Inbox Analyzer — AI-powered DM scanner")
    parser.add_argument("--mode", choices=["analyze", "auto", "review"], default="analyze",
                        help="analyze = scan + classify, auto = scan + send, review = show results")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max threads to scan")
    parser.add_argument("--fast", action="store_true",
                        help="Shorter cooldowns between sends")
    args = parser.parse_args()

    logger.info("Mode: %s | Limit: %d | Fast: %s", args.mode, args.limit, args.fast)
    run_analyzer(mode=args.mode, limit=args.limit, fast=args.fast)


if __name__ == "__main__":
    main()
