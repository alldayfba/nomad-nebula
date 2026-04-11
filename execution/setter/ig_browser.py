"""
Instagram browser automation — Playwright-based IG control layer.

Connects to a persistent Chrome instance (launched via launch_chrome.sh)
with an active Instagram session. Handles profile scraping, DM read/write,
follower scanning, and inbox management.

Requires Chrome running on SETTER_CHROME_PORT (default 9222) with IG logged in.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .setter_config import CHROME_PORT, RATE_LIMITS, SAFETY, PROJECT_ROOT

logger = logging.getLogger("setter.browser")

# Instagram URL patterns
IG_BASE = "https://www.instagram.com"
IG_DM_INBOX = f"{IG_BASE}/direct/inbox/"
IG_DM_THREAD = f"{IG_BASE}/direct/t/"
IG_EXPLORE_TAGS = f"{IG_BASE}/explore/tags/"


class IGBrowser:
    """Playwright-based Instagram automation.

    Connects to an existing Chrome instance with an active IG session.
    All operations are async for compatibility with the daemon loop.
    Includes visual self-healing: screenshots + Claude Vision to detect and recover from errors.
    """

    def __init__(self, port: int = CHROME_PORT):
        self.port = port
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to existing Chrome instance via CDP."""
        try:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().__aenter__()
            self.browser = await self.playwright.chromium.connect_over_cdp(
                f"http://localhost:{self.port}"
            )
            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
            else:
                self.context = await self.browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                )
            pages = self.context.pages
            self.page = pages[0] if pages else await self.context.new_page()
            self._connected = True
            logger.info("Connected to Chrome on port %d", self.port)
            return True
        except Exception as e:
            logger.error("Failed to connect to Chrome on port %d: %s", self.port, e)
            self._connected = False
            return False

    async def disconnect(self):
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
            self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def _ensure_connected(self):
        if not self._connected:
            if not await self.connect():
                raise ConnectionError(f"Cannot connect to Chrome on port {self.port}")

    async def _human_delay(self, min_s: float = 0.5, max_s: float = 2.0):
        """Random delay to mimic human behavior."""
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def _navigate(self, url: str, wait_for: str = "domcontentloaded"):
        """Navigate to URL with human-like timing."""
        await self._ensure_connected()
        current = self.page.url
        if current != url:
            await self.page.goto(url, wait_until=wait_for, timeout=30000)
            await self._human_delay(1.0, 3.0)

    async def _scroll_down(self, pixels: int = 300):
        await self.page.evaluate(f"window.scrollBy(0, {pixels})")
        await self._human_delay(0.5, 1.5)

    # ── Self-Healing (DOM-based, no screenshots) ──────────────────────────────

    async def _heal(self) -> bool:
        """Detect error states from page text and recover. No screenshots.

        Returns True if in a usable state (or recovered).
        """
        try:
            body = await self.page.inner_text("body")
            url = self.page.url

            if "Sorry, this page isn't available" in body or "Page Not Found" in body:
                logger.warning("Error page — navigating home")
                await self._navigate(IG_BASE)
                return True
            elif "Try Again Later" in body or "Action Blocked" in body:
                logger.error("Action block detected")
                return False
            elif 'input[name="username"]' and "/accounts/login" in url:
                logger.error("Login page — session expired")
                return False
            return True
        except Exception:
            return True  # Can't read page, assume OK

    async def _safe_navigate_profile(self, handle: str) -> bool:
        """Navigate to a profile with error detection.

        Returns False if the profile doesn't exist (error page).
        """
        await self._navigate(f"{IG_BASE}/{handle}/")
        await self._human_delay(1.0, 2.0)

        # Quick check: look for error indicators in page text
        try:
            body = await self.page.inner_text("body")
            if "Sorry, this page isn't available" in body or "Page Not Found" in body:
                logger.warning("Profile @%s does not exist — skipping", handle)
                return False
        except Exception:
            pass
        return True

    # ── Profile Scraping ─────────────────────────────────────────────────────

    async def scrape_profile(self, handle: str) -> Dict[str, Any]:
        """Scrape an Instagram profile for ICP scoring data.

        Returns: dict with full_name, bio, follower_count, following_count,
                 is_business, is_private, category, website, post_count, etc.
        Returns {"ig_handle": handle, "_error": True} if profile doesn't exist.
        """
        exists = await self._safe_navigate_profile(handle)
        if not exists:
            return {"ig_handle": handle, "_error": True}
        await self._human_delay(0.5, 1.0)

        profile = {
            "ig_handle": handle,
            "full_name": "",
            "bio": "",
            "follower_count": 0,
            "following_count": 0,
            "post_count": 0,
            "is_business": False,
            "is_private": False,
            "category": "",
            "website": "",
            "email_from_bio": "",
            "profile_pic_url": "",
        }

        try:
            # Try to extract from meta tags and page content first (more reliable)
            meta_desc = await self.page.query_selector('meta[property="og:description"]')
            if meta_desc:
                content = await meta_desc.get_attribute("content") or ""
                # Parse "X Followers, Y Following, Z Posts - ..." format
                nums = re.findall(r"([\d,.]+[KMkm]?)\s+(Followers?|Following|Posts?)", content)
                for val, label in nums:
                    parsed = self._parse_count(val)
                    if "Follower" in label:
                        profile["follower_count"] = parsed
                    elif "Following" in label:
                        profile["following_count"] = parsed
                    elif "Post" in label:
                        profile["post_count"] = parsed

            meta_title = await self.page.query_selector('meta[property="og:title"]')
            if meta_title:
                title = await meta_title.get_attribute("content") or ""
                # Format: "Full Name (@handle) • Instagram photos and videos"
                name_match = re.match(r"^(.+?)\s*\(@", title)
                if name_match:
                    profile["full_name"] = name_match.group(1).strip()

            # Extract bio from page
            bio_selectors = [
                'div[class*="biography"] span',
                'section main header section div:nth-child(3) span',
                'div.-vDIg span',
            ]
            for sel in bio_selectors:
                bio_el = await self.page.query_selector(sel)
                if bio_el:
                    profile["bio"] = (await bio_el.inner_text()).strip()
                    break

            # Fallback: extract bio from full page text
            if not profile["bio"]:
                try:
                    page_text = await self.page.inner_text("main")
                    profile["bio"] = self._extract_bio_from_text(page_text, handle)
                except Exception:
                    pass

            # Check for business category
            category_el = await self.page.query_selector(
                'div[class*="category"] a, div[class*="category"] span'
            )
            if category_el:
                profile["category"] = (await category_el.inner_text()).strip()
                profile["is_business"] = True

            # Check for external link
            link_el = await self.page.query_selector('a[class*="link"] span, a[rel="me nofollow"]')
            if link_el:
                profile["website"] = (await link_el.inner_text()).strip()

            # Check if private
            private_el = await self.page.query_selector('h2:has-text("This account is private")')
            if private_el:
                profile["is_private"] = True

            # Extract email from bio
            if profile["bio"]:
                email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', profile["bio"])
                if email_match:
                    profile["email_from_bio"] = email_match.group()

            # Profile pic
            pic_el = await self.page.query_selector('img[alt*="profile picture"]')
            if pic_el:
                profile["profile_pic_url"] = await pic_el.get_attribute("src") or ""

            # Check if WE follow them (mutual follow = known contact)
            # The Follow button text says "Following" if we already follow them
            follow_btn = await self.page.query_selector(
                'button:has-text("Following"), div[role="button"]:has-text("Following")'
            )
            if follow_btn:
                btn_text = (await follow_btn.inner_text()).strip().lower()
                if btn_text == "following":
                    profile["following_status"] = "following"  # We follow them
                else:
                    profile["following_status"] = "not_following"
            else:
                profile["following_status"] = "not_following"

        except Exception as e:
            logger.warning("Error scraping profile %s: %s", handle, e)

        return profile

    def _parse_count(self, text: str) -> int:
        """Parse follower/following counts like '12.5K', '1.2M', '340'."""
        text = text.strip().replace(",", "")
        multiplier = 1
        if text.endswith(("K", "k")):
            multiplier = 1000
            text = text[:-1]
        elif text.endswith(("M", "m")):
            multiplier = 1_000_000
            text = text[:-1]
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return 0

    def _extract_bio_from_text(self, page_text: str, handle: str) -> str:
        """Fallback bio extraction from raw page text."""
        lines = [l.strip() for l in page_text.split("\n") if l.strip()]
        # Bio usually comes after the name and before posts/followers counts
        bio_lines = []
        capture = False
        for line in lines:
            if line.lower() == handle.lower() or line.startswith(handle):
                capture = True
                continue
            if capture:
                if re.match(r'^[\d,.]+[KMkm]?\s*(posts?|followers?|following)', line, re.I):
                    break
                if len(line) > 5:
                    bio_lines.append(line)
                if len(bio_lines) >= 5:
                    break
        return " ".join(bio_lines)[:500]

    # ── Follower Scanning ────────────────────────────────────────────────────

    async def scan_followers(self, target_handle: str, max_count: int = 100) -> List[str]:
        """Get a list of follower handles from a target account.

        Opens the followers dialog and scrolls to collect handles.
        """
        await self._navigate(f"{IG_BASE}/{target_handle}/")
        await self._human_delay(2.0, 4.0)

        # Click followers link
        followers_link = await self.page.query_selector(
            'a[href*="/followers/"], a:has-text("followers")'
        )
        if not followers_link:
            logger.warning("Cannot find followers link for %s", target_handle)
            return []

        await followers_link.click()
        await self._human_delay(2.0, 3.0)

        handles = set()
        scroll_attempts = 0
        max_scrolls = max_count // 10 + 5

        while len(handles) < max_count and scroll_attempts < max_scrolls:
            # Extract handles from the dialog
            links = await self.page.query_selector_all(
                'div[role="dialog"] a[href^="/"][role="link"]'
            )
            for link in links:
                href = await link.get_attribute("href")
                if href and href.count("/") == 2:
                    handle = href.strip("/")
                    if handle and not handle.startswith(("explore", "p/", "reel")):
                        handles.add(handle)

            # Scroll the dialog
            dialog = await self.page.query_selector('div[role="dialog"] div[style*="overflow"]')
            if dialog:
                await dialog.evaluate("el => el.scrollTop += 500")
            else:
                await self.page.keyboard.press("End")

            await self._human_delay(1.0, 2.5)
            scroll_attempts += 1

        # Close dialog
        try:
            close_btn = await self.page.query_selector(
                'div[role="dialog"] button[aria-label="Close"], svg[aria-label="Close"]'
            )
            if close_btn:
                await close_btn.click()
        except Exception:
            await self.page.keyboard.press("Escape")

        result = list(handles)[:max_count]
        logger.info("Scanned %d followers from %s", len(result), target_handle)
        return result

    async def scan_hashtag(self, tag: str, max_posts: int = 20) -> List[str]:
        """Get poster handles from a hashtag page.

        Returns list of unique handles who posted with this hashtag.
        """
        await self._navigate(f"{IG_EXPLORE_TAGS}{tag}/")
        await self._human_delay(2.0, 4.0)

        handles = set()
        # Find post links on the hashtag page
        posts = await self.page.query_selector_all(
            'a[href^="/p/"], a[href^="/reel/"]'
        )

        for post in posts[:max_posts]:
            try:
                href = await post.get_attribute("href")
                if href:
                    await post.click()
                    await self._human_delay(1.5, 2.5)

                    # Try multiple selectors for username in post overlay
                    for selector in [
                        'div[role="dialog"] header a[href^="/"] span',
                        'div[role="dialog"] a[href^="/"][role="link"] span',
                        'div[role="dialog"] header a[href^="/"]',
                    ]:
                        user_el = await self.page.query_selector(selector)
                        if user_el:
                            handle = (await user_el.inner_text()).strip().rstrip(" •")
                            if handle and "/" not in handle and len(handle) < 40:
                                handles.add(handle)
                            break

                    await self.page.keyboard.press("Escape")
                    await self._human_delay(0.5, 1.0)
            except Exception as e:
                logger.debug("Error extracting post handle: %s", e)
                try:
                    await self.page.keyboard.press("Escape")
                except Exception:
                    pass

        result = list(handles)
        logger.info("Found %d handles from #%s", len(result), tag)
        return result

    # ── DM Inbox ─────────────────────────────────────────────────────────────

    async def read_inbox(self, max_threads: int = 20) -> List[Dict]:
        """Read DM inbox and return threads with unread messages.

        Returns list of dicts: {thread_id, handle, name, last_message, unread, timestamp}
        """
        await self._navigate(IG_DM_INBOX)
        await self._human_delay(2.0, 4.0)

        threads = []
        thread_elements = await self.page.query_selector_all(
            'div[role="listbox"] > div, a[href^="/direct/t/"]'
        )

        for el in thread_elements[:max_threads]:
            try:
                thread = {}

                # Extract thread link
                link = el if await el.get_attribute("href") else await el.query_selector('a[href^="/direct/t/"]')
                if link:
                    href = await link.get_attribute("href") or ""
                    tid_match = re.search(r"/direct/t/(\d+)", href)
                    if tid_match:
                        thread["thread_id"] = tid_match.group(1)

                # Extract name/handle
                name_el = await el.query_selector('span[dir="auto"]')
                if name_el:
                    thread["name"] = (await name_el.inner_text()).strip()

                # Extract last message preview
                msg_els = await el.query_selector_all('span[dir="auto"]')
                if len(msg_els) > 1:
                    thread["last_message"] = (await msg_els[-1].inner_text()).strip()

                # Check for unread indicator (blue dot)
                unread_el = await el.query_selector(
                    'div[style*="background-color: rgb(0, 149, 246)"], '
                    'div[class*="unread"]'
                )
                thread["unread"] = unread_el is not None

                if thread.get("thread_id"):
                    threads.append(thread)

            except Exception as e:
                logger.debug("Error reading inbox thread: %s", e)

        logger.info("Read %d threads from inbox (%d unread)",
                     len(threads), sum(1 for t in threads if t.get("unread")))
        return threads

    async def read_thread(self, thread_id: str, max_messages: int = 30) -> List[Dict]:
        """Read full message history from a DM thread.

        Returns list of dicts: {content, direction, timestamp, message_type}
        direction: 'in' (from prospect) or 'out' (from us)
        """
        await self._navigate(f"{IG_DM_THREAD}{thread_id}/")
        await self._human_delay(2.0, 3.0)

        messages = []

        # Scroll up to load more messages
        for _ in range(3):
            await self.page.keyboard.press("Home")
            await self._human_delay(0.5, 1.0)

        # Use multiple selectors for message containers — Instagram's DOM changes frequently
        msg_elements = await self.page.query_selector_all(
            'div[role="row"]'
        )
        # Fallback if role="row" yields nothing
        if not msg_elements:
            msg_elements = await self.page.query_selector_all(
                'div[class*="message"], div[data-testid*="message"]'
            )

        debug_count = 0
        for el in msg_elements[-max_messages:]:
            try:
                msg = {"message_type": "text"}
                text_el = await el.query_selector('span[dir="auto"], div[dir="auto"]')
                if text_el:
                    msg["content"] = (await text_el.inner_text()).strip()

                if not msg.get("content"):
                    continue

                # ── Direction Detection (multi-strategy) ──
                # Instagram renders sent messages with blue/purple bubbles
                # and received messages with grey bubbles. We check:
                # 1. Computed background color of the message bubble
                # 2. CSS alignment (flex-end = sent, flex-start = received)
                # 3. Presence of avatar img next to message (received msgs have avatar)
                direction = None

                # Strategy 1: Check bubble background color via JS
                try:
                    color_info = await el.evaluate("""el => {
                        // Walk down to find the actual message bubble div
                        const spans = el.querySelectorAll('span[dir="auto"], div[dir="auto"]');
                        for (const span of spans) {
                            let node = span.parentElement;
                            // Walk up max 5 levels looking for a colored container
                            for (let i = 0; i < 5 && node && node !== el; i++) {
                                const bg = window.getComputedStyle(node).backgroundColor;
                                if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
                                    return bg;
                                }
                                node = node.parentElement;
                            }
                        }
                        return '';
                    }""")
                    if color_info:
                        # Instagram blue/purple for sent: rgb(0, 149, 246), rgb(99, 102, 241),
                        # rgb(0, 132, 255), or similar bright blue
                        # Grey for received: rgb(239, 239, 239), rgb(38, 38, 38) dark mode, etc.
                        import re as _re
                        rgb = _re.findall(r'\d+', color_info)
                        if len(rgb) >= 3:
                            r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
                            # Blue-ish hues (sent) — high blue channel, low red
                            if b > 200 and r < 120:
                                direction = "out"
                            # Purple-ish (sent) — both r and b elevated
                            elif b > 200 and r > 80 and g < 120:
                                direction = "out"
                            # Grey/white (received) — all channels similar
                            elif abs(r - g) < 30 and abs(g - b) < 30:
                                direction = "in"
                except Exception:
                    pass

                # Strategy 2: Check alignment via computed styles up the tree
                if not direction:
                    try:
                        alignment = await el.evaluate("""el => {
                            let node = el;
                            for (let i = 0; i < 8 && node; i++) {
                                const s = window.getComputedStyle(node);
                                const justify = s.justifyContent || '';
                                const align = s.alignItems || '';
                                const flexDir = s.flexDirection || '';
                                const ml = s.marginLeft || '';
                                if (justify === 'flex-end' || align === 'flex-end') return 'out';
                                if (justify === 'flex-start' || align === 'flex-start') return 'in';
                                // Auto margin-left pushes element right (sent message)
                                if (ml === 'auto') return 'out';
                                node = node.parentElement;
                            }
                            return '';
                        }""")
                        if alignment in ("out", "in"):
                            direction = alignment
                    except Exception:
                        pass

                # Strategy 3: Avatar detection — received messages have the other person's avatar
                if not direction:
                    try:
                        has_avatar = await el.evaluate("""el => {
                            const imgs = el.querySelectorAll('img');
                            for (const img of imgs) {
                                const alt = (img.getAttribute('alt') || '').toLowerCase();
                                const src = img.getAttribute('src') || '';
                                // Profile pictures are small circular images
                                if (src.includes('profile') || src.includes('150x150')
                                    || img.width <= 40 || img.naturalWidth <= 40) {
                                    return true;
                                }
                            }
                            return false;
                        }""")
                        direction = "in" if has_avatar else "out"
                    except Exception:
                        pass

                # Final fallback — if we still can't determine, skip this message
                # rather than guessing wrong (prevents phantom inbound/outbound)
                if not direction:
                    logger.debug("Could not determine direction for message: %.40s...", msg.get("content", ""))
                    continue

                msg["direction"] = direction

                # Debug logging for first 3 messages per thread
                if debug_count < 3:
                    logger.info(
                        "Thread msg direction=%s: %.40s",
                        direction, msg.get("content", "")
                    )
                    debug_count += 1

                # Check for images/links
                img = await el.query_selector("img:not([alt*='profile'])")
                if img:
                    msg["message_type"] = "image"

                link = await el.query_selector("a[href]:not([href^='/'])")
                if link:
                    msg["message_type"] = "link"

                messages.append(msg)

            except Exception as e:
                logger.debug("Error reading message: %s", e)

        return messages

    async def _has_existing_thread(self) -> bool:
        """Check if the current DM thread has prior messages (we talked before)."""
        try:
            # Look for existing messages in the thread
            msgs = await self.page.query_selector_all(
                'div[role="row"], div[class*="message"], div[dir="auto"]'
            )
            # If there are messages visible, this is an existing conversation
            # Filter out just the input area — real messages have text content
            for msg in msgs:
                text = (await msg.inner_text()).strip()
                if text and len(text) > 2 and "Message" not in text:
                    return True
            return False
        except Exception:
            return False

    async def _open_dm_from_profile(self, handle: str):
        """Open DM thread from a user's profile page.

        Returns:
        - "sent" → new thread opened, ready to type
        - "existing" → prior conversation exists, should follow up instead
        - False → can't DM this person

        Tries in order:
        1. "Message" button on profile (most public accounts)
        2. 3-dots menu → "Send message" (private accounts, some public)
        3. Returns False if messaging is turned off → caller should skip
        """
        try:
            # Navigate to profile (with error page detection)
            exists = await self._safe_navigate_profile(handle)
            if not exists:
                return False

            # --- Path 1: Direct "Message" button on the profile ---
            msg_btn = await self.page.query_selector(
                'div[role="button"]:has-text("Message"), '
                'button:has-text("Message")'
            )
            if msg_btn:
                btn_text = (await msg_btn.inner_text()).strip()
                if btn_text.lower() == "message":
                    await msg_btn.click()
                    await self._human_delay(1.5, 2.5)
                    # Check if this opens an EXISTING thread (prior convo)
                    if await self._has_existing_thread():
                        return "existing"
                    return "sent"

            # --- Path 2: 3-dots → "Send message" ---
            more_btn = await self.page.query_selector(
                'svg[aria-label="Options"], '
                'button[aria-label="Options"]'
            )
            if not more_btn:
                more_btn = await self.page.query_selector(
                    'header button:has(svg)'
                )

            if more_btn:
                await more_btn.click()
                await self._human_delay(1.0, 2.0)

                send_msg_btn = await self.page.query_selector(
                    'button:has-text("Send message"), '
                    'button:has-text("Send Message")'
                )
                if send_msg_btn:
                    await send_msg_btn.click()
                    await self._human_delay(1.5, 2.5)
                    if await self._has_existing_thread():
                        return "existing"
                    return "sent"

                # Close the menu if "Send message" wasn't there
                try:
                    await self.page.keyboard.press("Escape")
                    await self._human_delay(0.3, 0.5)
                except Exception:
                    pass

            # --- Path 3: No message option → messaging turned off, skip ---
            logger.info("No message option for @%s — messaging disabled, skipping", handle)
            return False

        except Exception as e:
            logger.debug("Profile DM open failed for %s: %s", handle, e)
            return False

    async def _open_dm_from_inbox(self, handle: str) -> bool:
        """Fallback: open DM from inbox compose (search for handle)."""
        try:
            await self._navigate(IG_DM_INBOX)
            await self._human_delay(1.5, 2.5)

            new_msg_btn = await self.page.query_selector(
                'svg[aria-label="New message"], '
                'div[role="button"]:has-text("New message"), '
                'a[href="/direct/new/"]'
            )
            if not new_msg_btn:
                return False

            await new_msg_btn.click()
            await self._human_delay(1.0, 2.0)

            search_selector = (
                'input[placeholder*="Search"], '
                'input[name="queryBox"], '
                'input[name="searchInput"]'
            )
            search_input = await self.page.query_selector(search_selector)
            if not search_input:
                return False

            await search_input.click()
            await self._human_delay(0.5, 1.0)
            await self.page.type(search_selector, handle, delay=30)
            await self._human_delay(1.5, 3.0)

            first_result = await self.page.query_selector(
                'div[role="dialog"] button:not([type="submit"]), '
                'div[role="listbox"] > div:first-child'
            )
            if first_result:
                await first_result.click()
                await self._human_delay(0.5, 1.0)

            chat_btn = await self.page.query_selector(
                'div[role="dialog"] button:has-text("Chat"), '
                'div[role="dialog"] button:has-text("Next")'
            )
            if chat_btn:
                await chat_btn.click()
                await self._human_delay(1.0, 2.0)

            return True
        except Exception as e:
            logger.debug("Inbox DM open failed for %s: %s", handle, e)
            return False

    async def check_existing_thread(self, handle: str) -> bool:
        """Check if there's an existing DM thread with this handle.

        Opens their profile, clicks Message, checks for prior messages.
        Does NOT send anything. Returns True if existing thread found.
        """
        opened = await self._open_dm_from_profile(handle)
        if opened == "existing":
            # Close/navigate away — we just wanted to check
            try:
                await self.page.keyboard.press("Escape")
                await self._human_delay(0.5, 1.0)
            except Exception:
                pass
            return True
        elif opened == "sent":
            # Fresh thread opened — but we don't want to send. Navigate away.
            try:
                await self._navigate(IG_BASE)
            except Exception:
                pass
            return False
        return False  # Couldn't open DM at all

    async def send_dm(self, handle_or_thread_id: str, message: str) -> Dict:
        """Send a DM to a handle or existing thread.

        If handle_or_thread_id is numeric, sends to existing thread.
        Otherwise, opens a new DM with the handle.

        Returns: {success: bool, thread_id: str, error: str}
        """
        result = {"success": False, "thread_id": "", "error": "", "had_existing_thread": False}

        try:
            if handle_or_thread_id.isdigit():
                # Existing thread
                await self._navigate(f"{IG_DM_THREAD}{handle_or_thread_id}/")
                result["thread_id"] = handle_or_thread_id
                result["had_existing_thread"] = True
            else:
                # New DM — go to their profile, click Message
                opened = await self._open_dm_from_profile(handle_or_thread_id)
                if opened == "existing":
                    # Prior thread exists — caller MUST handle context-aware messaging
                    result["had_existing_thread"] = True
                elif opened == "sent":
                    pass  # Fresh thread opened
                elif not opened:
                    # Fallback: inbox compose method
                    opened = await self._open_dm_from_inbox(handle_or_thread_id)
                if not opened:
                    result["error"] = "Cannot open DM thread"
                    return result

                # Extract thread ID from URL
                url = self.page.url
                tid_match = re.search(r"/direct/t/(\d+)", url)
                if tid_match:
                    result["thread_id"] = tid_match.group(1)

            await self._human_delay(1.0, 2.0)

            # Type and send message
            msg_input = await self.page.query_selector(
                'textarea[placeholder*="Message"], '
                'div[role="textbox"][contenteditable="true"], '
                'textarea[aria-label*="Message"]'
            )
            if not msg_input:
                result["error"] = "Cannot find message input"
                return result

            # Use type() instead of fill() — IG React re-renders detach elements
            await msg_input.click()
            tag = await msg_input.evaluate("el => el.tagName")
            if tag.lower() in ("div", "p"):
                await msg_input.type(message, delay=20)
            else:
                await msg_input.fill(message)

            await self._human_delay(0.5, 1.5)

            # Send via Enter key — retry up to 3 times if "Something went wrong"
            max_retries = 3
            for attempt in range(max_retries):
                await self.page.keyboard.press("Enter")
                await self._human_delay(1.5, 2.5)

                # Check for "Something went wrong" error
                try:
                    body = await self.page.inner_text("body")
                    if "something went wrong" in body.lower() or "couldn't send" in body.lower():
                        if attempt < max_retries - 1:
                            logger.info("'Something went wrong' on attempt %d — retrying...", attempt + 1)
                            # Click the message area again and re-press Enter
                            retry_input = await self.page.query_selector(
                                'textarea[placeholder*="Message"], '
                                'div[role="textbox"][contenteditable="true"]'
                            )
                            if retry_input:
                                await retry_input.click()
                            await self._human_delay(1.0, 2.0)
                            continue
                        else:
                            result["error"] = "Something went wrong after 3 retries"
                            return result
                except Exception:
                    pass

                # No error — message sent
                result["success"] = True
                logger.info("DM sent to %s", handle_or_thread_id)
                break

        except Exception as e:
            result["error"] = str(e)
            logger.error("Error sending DM to %s: %s", handle_or_thread_id, e)

        return result

    # ── Engagement Scanning ──────────────────────────────────────────────────

    async def get_recent_engagers(
        self, max_count: int = 50, followers_only: bool = True
    ) -> List[Dict]:
        """Get handles from notifications — defaults to NEW FOLLOWERS ONLY.

        Args:
            max_count: Max handles to return.
            followers_only: If True, only return "started following you" entries.
                           Set False to also get likes/comments/mentions.

        Returns: list of {handle, action_type}
        """
        await self._navigate(f"{IG_BASE}/accounts/activity/")
        await self._human_delay(2.0, 3.0)

        engagers = []
        seen = set()

        # Get all notification items — look for container divs with links
        # Each notification row has text like "username started following you"
        items = await self.page.query_selector_all(
            'div[role="listbox"] > div, main div > div > div'
        )

        # Fallback: just scan all links with parent text
        if not items:
            items = await self.page.query_selector_all('a[href^="/"]')

        for item in items:
            if len(engagers) >= max_count:
                break
            try:
                # Get the full text of this notification row
                text = ""
                try:
                    text = (await item.inner_text()).strip().lower()
                except Exception:
                    continue

                if not text:
                    continue

                # Classify the action
                action = "unknown"
                if "started following you" in text or "follow" in text:
                    action = "new_follower"
                elif "liked" in text:
                    action = "post_like"
                elif "comment" in text:
                    action = "post_comment"
                elif "mentioned" in text or "story" in text:
                    action = "story_reply"

                # If followers_only mode, skip non-followers
                if followers_only and action != "new_follower":
                    continue

                # Extract handle from the link inside this item
                link = await item.query_selector('a[href^="/"]')
                if not link:
                    # If item IS a link, use it directly
                    href = await item.get_attribute("href") if hasattr(item, 'get_attribute') else None
                    if not href:
                        continue
                else:
                    href = await link.get_attribute("href") or ""

                handle = href.strip("/")
                skip = {"explore", "reels", "stories", "accounts", "p", "direct", ""}
                if "/" in handle or handle in skip or handle in seen:
                    continue
                seen.add(handle)

                engagers.append({
                    "handle": handle,
                    "action_type": action,
                })
            except Exception:
                continue

        logger.info("Found %d new followers from notifications", len(engagers))
        return engagers

    # ── Story Viewer Scanner ──────────────────────────────────────────────────

    async def get_story_viewers(self, max_count: int = 100) -> List[str]:
        """Get handles of people who viewed your most recent stories.

        Opens own profile → clicks story → swipes up to get viewer list.
        Returns list of handles.
        """
        handles = set()

        try:
            # Go to own profile
            await self._navigate(f"{IG_BASE}/allday.fba/")
            await self._human_delay(1.5, 2.5)

            # Click on the story ring (own profile pic with story ring)
            story_ring = await self.page.query_selector(
                'header canvas, '
                'header img[alt*="profile picture"], '
                'header div[role="button"] img'
            )
            if not story_ring:
                # Try clicking the story from the stories bar
                await self._navigate(f"{IG_BASE}/stories/allday.fba/")
                await self._human_delay(2.0, 3.0)
            else:
                await story_ring.click()
                await self._human_delay(2.0, 3.0)

            # Check if we're in a story view
            story_active = await self.page.query_selector(
                'div[role="presentation"] video, '
                'div[role="presentation"] img, '
                'section[class*="story"]'
            )
            if not story_active:
                logger.info("No active stories to scan viewers for")
                return []

            # Click the viewers count / swipe up area to see who viewed
            # On IG, it's the eye icon or viewer count at bottom of own story
            viewers_btn = await self.page.query_selector(
                'button[aria-label*="viewers"], '
                'div[role="button"]:has(svg[aria-label*="Seen by"]), '
                'button:has-text("Activity"), '
                'div:has-text("Seen by")'
            )
            if viewers_btn:
                await viewers_btn.click()
                await self._human_delay(1.5, 2.5)

            # Extract viewer handles from the viewer list
            # Scroll and collect
            scroll_attempts = 0
            while len(handles) < max_count and scroll_attempts < 10:
                links = await self.page.query_selector_all(
                    'div[role="dialog"] a[href^="/"], '
                    'div[aria-label*="Viewers"] a[href^="/"], '
                    'ul a[href^="/"]'
                )
                for link in links:
                    try:
                        href = await link.get_attribute("href") or ""
                        handle = href.strip("/")
                        skip = {"explore", "reels", "stories", "accounts", "p", "direct", ""}
                        if "/" not in handle and handle not in skip:
                            handles.add(handle)
                    except Exception:
                        continue

                # Scroll viewer list
                dialog = await self.page.query_selector(
                    'div[role="dialog"] div[style*="overflow"], '
                    'div[aria-label*="Viewers"]'
                )
                if dialog:
                    await dialog.evaluate("el => el.scrollTop += 400")
                    await self._human_delay(0.5, 1.5)
                scroll_attempts += 1

            # Close story view
            try:
                close_btn = await self.page.query_selector(
                    'button[aria-label="Close"], svg[aria-label="Close"]'
                )
                if close_btn:
                    await close_btn.click()
                else:
                    await self.page.keyboard.press("Escape")
            except Exception:
                await self.page.keyboard.press("Escape")

        except Exception as e:
            logger.error("Story viewer scan error: %s", e)
            try:
                await self.page.keyboard.press("Escape")
            except Exception:
                pass

        result = list(handles)
        logger.info("Found %d story viewers", len(result))
        return result

    # ── Action Block Detection ───────────────────────────────────────────────

    async def check_action_block(self) -> bool:
        """Check if Instagram is showing an action block dialog."""
        block_texts = [
            "Try Again Later",
            "Action Blocked",
            "We restrict certain activity",
            "temporarily blocked",
        ]
        try:
            body_text = await self.page.inner_text("body")
            for phrase in block_texts:
                if phrase.lower() in body_text.lower():
                    logger.error("ACTION BLOCK DETECTED: %s", phrase)
                    return True
        except Exception:
            pass
        return False

    # ── Health Check ─────────────────────────────────────────────────────────

    async def health_check(self) -> Dict:
        """Verify Chrome is connected and IG session is alive."""
        status = {
            "chrome_connected": self._connected,
            "ig_logged_in": False,
            "action_blocked": False,
        }

        if not self._connected:
            return status

        try:
            await self._navigate(IG_BASE, wait_for="domcontentloaded")
            # Check if we're on the login page (not logged in)
            login_form = await self.page.query_selector('input[name="username"]')
            status["ig_logged_in"] = login_form is None

            if status["ig_logged_in"]:
                status["action_blocked"] = await self.check_action_block()

        except Exception as e:
            logger.error("Health check failed: %s", e)

        return status


    # ── Comment Keyword Scanner ───────────────────────────────────────────────

    async def scan_comment_keywords(self, keywords: List[str], max_count: int = 30) -> List[Dict]:
        """Scan notifications for comments containing trigger keywords.

        Returns: [{handle, keyword_matched, comment_text}]
        """
        await self._navigate(f"{IG_BASE}/accounts/activity/")
        await self._human_delay(2.0, 3.0)

        results = []
        seen = set()
        keywords_lower = [k.lower() for k in keywords]

        # Get all notification items
        items = await self.page.query_selector_all(
            'div[role="listbox"] > div, main div > div > div'
        )
        if not items:
            items = await self.page.query_selector_all('a[href^="/"]')

        for item in items:
            if len(results) >= max_count:
                break
            try:
                text = ""
                try:
                    text = (await item.inner_text()).strip()
                except Exception:
                    continue

                text_lower = text.lower()
                if "comment" not in text_lower:
                    continue

                # Check if comment contains any keyword
                matched_keyword = None
                for kw in keywords_lower:
                    if kw in text_lower:
                        matched_keyword = kw.upper()
                        break

                if not matched_keyword:
                    continue

                # Extract handle
                link = await item.query_selector('a[href^="/"]')
                if not link:
                    continue
                href = await link.get_attribute("href") or ""
                handle = href.strip("/")
                skip = {"explore", "reels", "stories", "accounts", "p", "direct", ""}
                if "/" in handle or handle in skip or handle in seen:
                    continue
                seen.add(handle)

                results.append({
                    "handle": handle,
                    "keyword_matched": matched_keyword,
                    "comment_text": text[:200],
                })

            except Exception:
                continue

        logger.info("Found %d comment keyword matches", len(results))
        return results


# ── Sync Wrappers ────────────────────────────────────────────────────────────

def run_async(coro):
    """Run an async function synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


class IGBrowserSync:
    """Synchronous wrapper around IGBrowser for use in daemon loop."""

    def __init__(self, port: int = CHROME_PORT):
        self._async = IGBrowser(port)

    def connect(self) -> bool:
        return run_async(self._async.connect())

    def disconnect(self):
        return run_async(self._async.disconnect())

    @property
    def connected(self) -> bool:
        return self._async.connected

    def scrape_profile(self, handle: str) -> Dict:
        return run_async(self._async.scrape_profile(handle))

    def scan_followers(self, target: str, max_count: int = 100) -> List[str]:
        return run_async(self._async.scan_followers(target, max_count))

    def scan_hashtag(self, tag: str, max_posts: int = 20) -> List[str]:
        return run_async(self._async.scan_hashtag(tag, max_posts))

    def read_inbox(self, max_threads: int = 20) -> List[Dict]:
        return run_async(self._async.read_inbox(max_threads))

    def read_thread(self, thread_id: str, max_messages: int = 30) -> List[Dict]:
        return run_async(self._async.read_thread(thread_id, max_messages))

    def check_existing_thread(self, handle: str) -> bool:
        return run_async(self._async.check_existing_thread(handle))

    def send_dm(self, handle_or_thread_id: str, message: str) -> Dict:
        return run_async(self._async.send_dm(handle_or_thread_id, message))

    def get_recent_engagers(self, max_count: int = 50) -> List[Dict]:
        return run_async(self._async.get_recent_engagers(max_count))

    def health_check(self) -> Dict:
        return run_async(self._async.health_check())

    def check_action_block(self) -> bool:
        return run_async(self._async.check_action_block())

    def get_story_viewers(self, max_count: int = 100) -> List[str]:
        return run_async(self._async.get_story_viewers(max_count))

    def scan_comment_keywords(self, keywords: List[str], max_count: int = 30) -> List[Dict]:
        return run_async(self._async.scan_comment_keywords(keywords, max_count))
