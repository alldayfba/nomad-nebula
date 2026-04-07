"""
Prospect discovery — scans Instagram notifications for new followers and engagers.

Primary flow:
  1. Go to notifications → find new followers
  2. Click each follower profile → scrape bio
  3. Check if we've spoken before (DB lookup)
  4. If NEW: send casual opener DM directly from their profile
  5. If EXISTING: analyze conversation history, decide next move
  6. Score ICP fit, store everything

NO hashtag clicking. NO random browsing. Only notifications + followers.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Dict, List

from .setter_config import (
    OWN_IG_HANDLE,
    RATE_LIMITS,
    SAFETY,
)
from . import setter_db as db
from .setter_brain import score_icp
from .ig_browser import IGBrowserSync

logger = logging.getLogger("setter.prospector")


def run_scan_cycle(browser: IGBrowserSync) -> Dict:
    """Run a full prospecting cycle.

    1. Scan notifications for new followers + engagers
    2. For each new follower: click profile, check if spoken, DM if not
    3. Score all new/unscored prospects

    Returns: {scanned: int, qualified: int, disqualified: int, errors: int}
    """
    stats = {"scanned": 0, "qualified": 0, "disqualified": 0, "errors": 0}

    # 1. PRIMARY: Scan own followers list (newest first — definitive source)
    #    Desktop notifications cap out fast, but followers list has everyone.
    #    We scan newest-first and stop when we hit handles already in DB.
    try:
        own_followers = browser.scan_followers(OWN_IG_HANDLE, max_count=200)
        already_seen_streak = 0
        for handle in own_followers:
            if handle == OWN_IG_HANDLE:
                continue
            existing = db.get_prospect_by_handle(handle)
            if existing:
                already_seen_streak += 1
                # If we've hit 10 known handles in a row, we've caught up
                if already_seen_streak >= 10:
                    logger.info("Hit 10 known followers in a row — caught up")
                    break
                continue
            already_seen_streak = 0  # Reset streak on new follower
            db.upsert_prospect(
                ig_handle=handle,
                source="new_follower",
                source_detail=f"@{OWN_IG_HANDLE} followers list",
            )
            stats["scanned"] += 1
    except Exception as e:
        logger.error("Follower scan error: %s", e)
        stats["errors"] += 1

    # 3. Quick-scrape new prospects to check if private (skip ICP scoring —
    #    every follower gets a DM, qualification happens in conversation)
    unscored = db.get_prospects_by_status("new", limit=50)
    profiles_viewed = 0

    for prospect in unscored:
        if profiles_viewed >= RATE_LIMITS["profile_views_hourly"]:
            logger.info("Hourly profile view limit reached")
            break

        try:
            # Scrape profile to get bio + check if private
            if not prospect.get("bio"):
                profile = browser.scrape_profile(prospect["ig_handle"])
                db.upsert_prospect(
                    ig_handle=prospect["ig_handle"],
                    **{k: v for k, v in profile.items() if k != "ig_handle"},
                )
                prospect.update(profile)
                profiles_viewed += 1
                time.sleep(random.uniform(1.0, 3.0))

            # Skip established Amazon sellers / coaches (competitors, not prospects)
            bio_lower = (prospect.get("bio") or "").lower()
            competitor_signals = [
                "6 figure", "7 figure", "8 figure", "six figure", "seven figure",
                "fba coach", "amazon coach", "amazon mentor", "fba mentor",
                "amazon expert", "ecom coach", "amazon consulting",
                "helping amazon sellers", "i teach amazon",
            ]
            is_competitor = any(s in bio_lower for s in competitor_signals)
            if is_competitor:
                db.update_prospect_status(prospect["id"], "disqualified")
                stats["disqualified"] += 1
                logger.info("Skipped @%s — competitor/established seller", prospect["ig_handle"])
                continue

            # Skip mutual follows (people Sabbo knows)
            # If we follow them back, they show up differently in the profile
            # The scrape_profile returns following_status or we check via browser
            if prospect.get("following_status") == "following":
                db.update_prospect_status(prospect["id"], "disqualified")
                stats["disqualified"] += 1
                logger.info("Skipped @%s — mutual follow (known contact)", prospect["ig_handle"])
                continue

            # Everyone else stays "new" — outbound batch will DM them
            stats["qualified"] += 1

        except Exception as e:
            stats["errors"] += 1
            logger.error("Profile check error for @%s: %s", prospect.get("ig_handle"), e)

    db.increment_metric("prospects_scanned", stats["scanned"])
    logger.info("Scan cycle: scanned=%d qualified=%d disqualified=%d errors=%d",
                 stats["scanned"], stats["qualified"], stats["disqualified"], stats["errors"])
    return stats
