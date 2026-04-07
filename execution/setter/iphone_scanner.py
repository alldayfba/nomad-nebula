#!/usr/bin/env python3
"""
iPhone Mirroring scanner — uses the real IG mobile app to scan followers.

Automates the iPhone Mirroring window on Mac to:
1. Open IG notifications
2. Filter to "Follows" only
3. Scroll through weeks of follower history
4. Screenshot + Claude Vision to extract handles
5. Store new followers in setter DB for outbound

Usage:
    python -m execution.setter.iphone_scanner --scan           # Scan followers
    python -m execution.setter.iphone_scanner --scan --limit 500  # Scan up to 500
    python -m execution.setter.iphone_scanner --dm             # DM uncontacted followers
    python -m execution.setter.iphone_scanner --status         # Show scan stats

Requires: iPhone Mirroring window open, IG logged in on phone.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pyautogui

# Safe defaults — no accidental clicks off-screen
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.3

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from execution.setter import setter_db as db
from execution.setter.setter_config import OWN_IG_HANDLE, SAFETY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [iphone-scanner] %(message)s")
logger = logging.getLogger("iphone-scanner")

SCREENSHOT_DIR = _PROJECT_ROOT / ".tmp" / "setter" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ── iPhone Mirroring Window ─────────────────────────────────────────────────

def find_mirroring_window() -> Optional[Dict]:
    """Find the iPhone Mirroring window position and size."""
    try:
        import Quartz
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID
        )
        for w in windows:
            owner = w.get("kCGWindowOwnerName", "")
            if "iphone mirroring" in owner.lower():
                bounds = w.get("kCGWindowBounds", {})
                return {
                    "x": int(bounds.get("X", 0)),
                    "y": int(bounds.get("Y", 0)),
                    "width": int(bounds.get("Width", 0)),
                    "height": int(bounds.get("Height", 0)),
                    "owner": owner,
                }
    except Exception as e:
        logger.error("Cannot find iPhone Mirroring window: %s", e)
    return None


def focus_mirroring_window():
    """Bring iPhone Mirroring to front."""
    subprocess.run([
        "osascript", "-e",
        'tell application "iPhone Mirroring" to activate'
    ], capture_output=True, timeout=5)
    time.sleep(0.5)


def take_screenshot(window: Dict, name: str = "screen") -> Path:
    """Screenshot the iPhone Mirroring window region using native macOS screencapture."""
    path = SCREENSHOT_DIR / f"{name}_{int(time.time())}.png"
    x, y, w, h = window["x"], window["y"], window["width"], window["height"]
    # macOS screencapture -R takes x,y,w,h
    subprocess.run(
        ["screencapture", "-R", f"{x},{y},{w},{h}", "-x", str(path)],
        capture_output=True, timeout=5,
    )
    return path


# ── Claude Vision for OCR ───────────────────────────────────────────────────

def extract_handles_from_screenshot(screenshot_path: Path) -> List[str]:
    """Use Claude Vision (via CLI) to extract follower handles from a screenshot.

    Returns list of IG handles found in the screenshot.
    """
    prompt = """Look at this Instagram notifications screenshot (filtered to Follows).
Extract EVERY Instagram username/handle visible in the "started following you" notifications.

Rules:
- Return ONLY the handles, one per line
- No @ symbol, just the username
- No explanations or other text
- If you see "and X others" just skip those
- Only extract handles you can clearly read"""

    try:
        # Claude CLI can read images
        proc = subprocess.run(
            ["claude", "-p", "--model", "claude-haiku-4-5-20251001"],
            input=f"Read this image at {screenshot_path} and {prompt}",
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            logger.error("Claude Vision error: %s", proc.stderr[:200])
            return []

        # Parse handles from response
        handles = []
        for line in proc.stdout.strip().split("\n"):
            line = line.strip().lstrip("@").lstrip("- ").strip()
            # Valid handle: alphanumeric + dots + underscores, 1-30 chars
            if re.match(r'^[a-zA-Z0-9_.]{1,30}$', line):
                handles.append(line.lower())

        return handles

    except Exception as e:
        logger.error("Vision extraction error: %s", e)
        return []


# ── Tap Helpers ─────────────────────────────────────────────────────────────

def tap(window: Dict, rel_x: float, rel_y: float):
    """Tap at a relative position within the iPhone Mirroring window.

    rel_x, rel_y are 0.0–1.0 fractions of window size.
    """
    abs_x = window["x"] + int(window["width"] * rel_x)
    abs_y = window["y"] + int(window["height"] * rel_y)
    pyautogui.click(abs_x, abs_y)
    time.sleep(0.3)


def scroll_down(window: Dict, amount: int = 3):
    """Scroll down within the iPhone Mirroring window."""
    center_x = window["x"] + window["width"] // 2
    center_y = window["y"] + window["height"] // 2
    pyautogui.moveTo(center_x, center_y)
    pyautogui.scroll(-amount)
    time.sleep(0.8)


def swipe_down(window: Dict):
    """Swipe up gesture (to scroll content down) within the follows list.

    Swipes on the RIGHT side (where Follow buttons are) to avoid
    accidentally tapping usernames on the left side.
    """
    # Use right-center area (over the Follow buttons, safe zone)
    swipe_x = window["x"] + int(window["width"] * 0.85)
    start_y = window["y"] + int(window["height"] * 0.60)
    end_y = window["y"] + int(window["height"] * 0.25)
    pyautogui.moveTo(swipe_x, start_y)
    time.sleep(0.1)
    pyautogui.mouseDown()
    pyautogui.moveTo(swipe_x, end_y, duration=0.5)
    pyautogui.mouseUp()
    time.sleep(1.2)


def go_back(window: Dict):
    """Tap back arrow — top left of screen. Used to recover from accidental profile opens."""
    back_x = window["x"] + int(window["width"] * 0.08)
    back_y = window["y"] + int(window["height"] * 0.068)
    pyautogui.click(back_x, back_y)
    time.sleep(1.0)


# ── Navigation ──────────────────────────────────────────────────────────────

def navigate_to_notifications(window: Dict):
    """Navigate to the IG notifications tab.

    NOTE: On current IG, notifications is NOT in the bottom bar.
    User must navigate manually to notifications first (heart icon varies by IG version).
    This function assumes we're already on the notifications page.
    """
    # Notifications heart icon position varies by IG version.
    # If we're on the home feed, the heart is in the top-right area.
    # Tap it — but this is unreliable, so we verify with a screenshot after.
    tap(window, 0.72, 0.067)
    time.sleep(2.0)


def filter_to_follows(window: Dict):
    """Scroll the filter tabs right and tap 'Follows' on the notifications page.

    IG mobile filter tabs: Interactions | Follows | You (may need horizontal scroll)
    Calibrated from testing: Follows tab is at ~55% x, ~9.8% y when visible.
    """
    # The tabs may need a horizontal scroll to reveal "Follows"
    # Swipe left on the tabs area
    tab_y = window["y"] + int(window["height"] * 0.098)
    start_x = window["x"] + int(window["width"] * 0.8)
    end_x = window["x"] + int(window["width"] * 0.2)
    pyautogui.moveTo(start_x, tab_y)
    time.sleep(0.1)
    pyautogui.mouseDown()
    pyautogui.moveTo(end_x, tab_y, duration=0.3)
    pyautogui.mouseUp()
    time.sleep(0.5)

    # Now tap Follows — approximately center of the tab area
    tap(window, 0.55, 0.098)
    time.sleep(1.5)


# ── Main Scan Loop ──────────────────────────────────────────────────────────

def scan_followers(
    max_followers: int = 200,
    max_scrolls: int = 50,
) -> Dict:
    """Scan followers from iPhone Mirroring notifications.

    1. Focus window
    2. Navigate to notifications → filter to Follows
    3. Screenshot + extract handles
    4. Scroll + repeat
    5. Store new followers in DB

    Returns: {total_found, new_added, already_known, screenshots_taken}
    """
    stats = {
        "total_found": 0,
        "new_added": 0,
        "already_known": 0,
        "screenshots_taken": 0,
    }

    window = find_mirroring_window()
    if not window:
        logger.error("iPhone Mirroring window not found! Make sure it's open.")
        return stats

    logger.info("Found iPhone Mirroring: %dx%d at (%d,%d)",
                window["width"], window["height"], window["x"], window["y"])

    # Focus and navigate
    focus_mirroring_window()
    time.sleep(1)

    logger.info("Navigating to notifications...")
    navigate_to_notifications(window)
    time.sleep(1)

    logger.info("Filtering to Follows only...")
    filter_to_follows(window)
    time.sleep(1)

    all_handles = set()
    no_new_count = 0

    for scroll_num in range(max_scrolls):
        if len(all_handles) >= max_followers:
            logger.info("Reached max followers limit: %d", max_followers)
            break

        # Screenshot current view
        screenshot_path = take_screenshot(window, f"follows_{scroll_num:03d}")
        stats["screenshots_taken"] += 1

        # Extract handles from screenshot
        handles = extract_handles_from_screenshot(screenshot_path)

        # If we got very few handles, we may have accidentally opened a profile
        # Check and recover
        if len(handles) <= 1 and scroll_num > 0:
            logger.warning("Few handles found — may have opened a profile. Going back...")
            go_back(window)
            time.sleep(1)
            continue

        new_in_this_scroll = 0

        for handle in handles:
            if handle in all_handles or handle == OWN_IG_HANDLE:
                continue
            all_handles.add(handle)
            stats["total_found"] += 1

            # Check DB
            existing = db.get_prospect_by_handle(handle)
            if existing:
                stats["already_known"] += 1
            else:
                db.upsert_prospect(
                    ig_handle=handle,
                    source="new_follower",
                    source_detail="iphone_mirroring_scan",
                )
                stats["new_added"] += 1
                new_in_this_scroll += 1

        logger.info("Scroll %d: found %d handles (%d new) — total: %d",
                     scroll_num + 1, len(handles), new_in_this_scroll, len(all_handles))

        # If no new handles for 3 scrolls, we've reached the end
        if new_in_this_scroll == 0:
            no_new_count += 1
            if no_new_count >= 3:
                logger.info("No new followers for 3 scrolls — done")
                break
        else:
            no_new_count = 0

        # Scroll down for more
        swipe_down(window)
        time.sleep(1.0)

        # Clean up screenshot (keep last 5 only)
        if scroll_num > 5:
            old = SCREENSHOT_DIR / f"follows_{scroll_num - 5:03d}_{int(time.time()) - 10}.png"
            if old.exists():
                old.unlink()

    logger.info("Scan complete: %d found, %d new, %d already known",
                stats["total_found"], stats["new_added"], stats["already_known"])
    return stats


def show_status():
    """Show current scan stats."""
    d = db.get_db()
    total = d.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
    from_iphone = d.execute(
        "SELECT COUNT(*) FROM prospects WHERE source_detail = 'iphone_mirroring_scan'"
    ).fetchone()[0]
    uncontacted = d.execute(
        """SELECT COUNT(*) FROM prospects p
           LEFT JOIN conversations c ON c.prospect_id = p.id
           WHERE p.status IN ('new', 'qualified') AND c.id IS NULL"""
    ).fetchone()[0]

    print(f"\n=== iPhone Scanner Status ===")
    print(f"Total prospects in DB: {total}")
    print(f"From iPhone scans: {from_iphone}")
    print(f"Uncontacted (ready for DM): {uncontacted}")
    print()


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="iPhone Mirroring IG follower scanner")
    parser.add_argument("--scan", action="store_true", help="Scan followers from notifications")
    parser.add_argument("--limit", type=int, default=200, help="Max followers to scan")
    parser.add_argument("--scrolls", type=int, default=50, help="Max scroll attempts")
    parser.add_argument("--status", action="store_true", help="Show scan stats")
    parser.add_argument("--dm", action="store_true", help="DM uncontacted followers (uses main setter)")
    args = parser.parse_args()

    # Load .env
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

    if args.status:
        show_status()
    elif args.scan:
        stats = scan_followers(max_followers=args.limit, max_scrolls=args.scrolls)
        print(json.dumps(stats, indent=2))
    elif args.dm:
        print("DM mode uses the main setter daemon. Run:")
        print("  python -m execution.setter.setter_daemon --once")
        print("It will pick up all uncontacted followers from the DB.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
