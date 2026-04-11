#!/usr/bin/env python3
"""
Profile Enricher — scrapes IG profiles for prospects missing bio data.

Runs in batches to respect rate limits. Scrapes profile -> updates prospect
with bio, follower count, business status, etc -> runs ICP scoring -> updates
prospect with score.

Usage:
    python -m execution.setter.profile_enricher --limit 100
    python -m execution.setter.profile_enricher --limit 50 --score-only
    python -m execution.setter.profile_enricher --dry-run
    python -m execution.setter.profile_enricher --stats
    python -m execution.setter.profile_enricher --blocklist-check
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from pathlib import Path
from typing import Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from execution.setter.ig_browser import IGBrowserSync
from execution.setter import setter_db as db
from execution.setter.setter_brain import score_icp
from execution.setter.setter_config import RATE_LIMITS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [enricher] %(message)s")
logger = logging.getLogger("enricher")


def get_unenriched_prospects(limit: int = 100) -> List[Dict]:
    """Get prospects missing bio data, newest first."""
    d = db.get_db()
    rows = d.execute(
        """SELECT * FROM prospects
           WHERE (bio IS NULL OR bio = '' OR bio = 'No bio')
           ORDER BY created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_unscored_prospects(limit: int = 100) -> List[Dict]:
    """Get prospects that have bio data but icp_score = 0."""
    d = db.get_db()
    rows = d.execute(
        """SELECT * FROM prospects
           WHERE bio IS NOT NULL AND bio != '' AND bio != 'No bio'
           AND icp_score = 0
           ORDER BY created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_enrichment_stats() -> Dict:
    """Get coverage statistics for the prospect database."""
    d = db.get_db()
    total = d.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
    has_bio = d.execute(
        "SELECT COUNT(*) FROM prospects WHERE bio IS NOT NULL AND bio != '' AND bio != 'No bio'"
    ).fetchone()[0]
    no_bio = total - has_bio
    scored = d.execute(
        "SELECT COUNT(*) FROM prospects WHERE icp_score > 0"
    ).fetchone()[0]
    private = d.execute(
        "SELECT COUNT(*) FROM prospects WHERE is_private = 1"
    ).fetchone()[0]

    # Score distribution
    dist = d.execute(
        """SELECT
            SUM(CASE WHEN icp_score >= 8 THEN 1 ELSE 0 END) as hot,
            SUM(CASE WHEN icp_score >= 5 AND icp_score < 8 THEN 1 ELSE 0 END) as warm,
            SUM(CASE WHEN icp_score >= 1 AND icp_score < 5 THEN 1 ELSE 0 END) as cold,
            SUM(CASE WHEN icp_score = 0 THEN 1 ELSE 0 END) as unscored
           FROM prospects"""
    ).fetchone()

    # Source breakdown
    sources = d.execute(
        "SELECT source, COUNT(*) as cnt FROM prospects GROUP BY source ORDER BY cnt DESC"
    ).fetchall()

    # Offer match breakdown
    offers = d.execute(
        "SELECT offer_match, COUNT(*) as cnt FROM prospects WHERE icp_score > 0 GROUP BY offer_match ORDER BY cnt DESC"
    ).fetchall()

    return {
        "total": total,
        "has_bio": has_bio,
        "no_bio": no_bio,
        "bio_pct": round(has_bio / total * 100, 1) if total else 0,
        "scored": scored,
        "scored_pct": round(scored / total * 100, 1) if total else 0,
        "private": private,
        "score_distribution": {
            "hot_8_10": dict(dist)["hot"] or 0,
            "warm_5_7": dict(dist)["warm"] or 0,
            "cold_1_4": dict(dist)["cold"] or 0,
            "unscored_0": dict(dist)["unscored"] or 0,
        },
        "by_source": {r["source"]: r["cnt"] for r in sources},
        "by_offer": {r["offer_match"]: r["cnt"] for r in offers},
    }


def print_stats():
    """Print enrichment coverage stats."""
    stats = get_enrichment_stats()
    print("\n=== ENRICHMENT COVERAGE ===")
    print(f"  Total prospects:   {stats['total']}")
    print(f"  Has bio:           {stats['has_bio']} ({stats['bio_pct']}%)")
    print(f"  No bio:            {stats['no_bio']}")
    print(f"  Private accounts:  {stats['private']}")
    print(f"  ICP scored:        {stats['scored']} ({stats['scored_pct']}%)")
    print()
    print("  Score Distribution:")
    sd = stats["score_distribution"]
    print(f"    Hot (8-10):      {sd['hot_8_10']}")
    print(f"    Warm (5-7):      {sd['warm_5_7']}")
    print(f"    Cold (1-4):      {sd['cold_1_4']}")
    print(f"    Unscored (0):    {sd['unscored_0']}")
    print()
    print("  By Source:")
    for src, cnt in stats["by_source"].items():
        print(f"    {src}: {cnt}")
    if stats["by_offer"]:
        print()
        print("  By Offer Match:")
        for offer, cnt in stats["by_offer"].items():
            print(f"    {offer}: {cnt}")
    print()


def run_enrichment(limit: int = 100, dry_run: bool = False, blocklist_check: bool = False):
    """Scrape profiles for prospects missing bio data, then ICP score them."""
    prospects = get_unenriched_prospects(limit)
    if not prospects:
        logger.info("No unenriched prospects found")
        return

    logger.info("Found %d prospects to enrich (limit %d)", len(prospects), limit)

    if dry_run:
        for p in prospects[:10]:
            logger.info("  [DRY RUN] Would scrape @%s (source: %s, created: %s)",
                        p["ig_handle"], p["source"], p["created_at"])
        if len(prospects) > 10:
            logger.info("  ... and %d more", len(prospects) - 10)
        return

    browser = IGBrowserSync()
    if not browser.connect():
        logger.error("Cannot connect to Chrome")
        return

    stats = {"scraped": 0, "scored": 0, "private": 0, "errors": 0, "blocklisted": 0}
    hourly_count = 0
    hourly_limit = RATE_LIMITS.get("profile_views_hourly", 100)
    daily_limit = RATE_LIMITS.get("profile_views_daily", 500)

    try:
        for i, prospect in enumerate(prospects):
            if stats["scraped"] + stats["private"] + stats["errors"] >= daily_limit:
                logger.info("Daily profile view limit (%d) reached", daily_limit)
                break
            if hourly_count >= hourly_limit:
                logger.info("Hourly profile view limit (%d) reached — stopping", hourly_limit)
                break

            handle = prospect["ig_handle"]
            logger.info("[%d/%d] Scraping @%s...", i + 1, len(prospects), handle)

            try:
                profile = browser.scrape_profile(handle)
            except Exception as e:
                logger.warning("  @%s: scrape error: %s", handle, e)
                stats["errors"] += 1
                continue

            hourly_count += 1

            if profile.get("_error"):
                logger.info("  @%s: profile not found or error", handle)
                stats["errors"] += 1
                continue

            # Check private account
            if profile.get("is_private"):
                stats["private"] += 1
                logger.info("  @%s: private account", handle)
                # Update DB with what we got
                db.upsert_prospect(
                    ig_handle=handle,
                    is_private=1,
                    full_name=profile.get("full_name", ""),
                    bio=profile.get("bio", ""),
                    follower_count=profile.get("follower_count", 0),
                    following_count=profile.get("following_count", 0),
                )
                if blocklist_check:
                    db.add_to_blocklist(handle, "private_account", "profile_enricher")
                    stats["blocklisted"] += 1
                    logger.info("  @%s: added to blocklist (private)", handle)
                continue

            # Update prospect with scraped data
            db.upsert_prospect(
                ig_handle=handle,
                full_name=profile.get("full_name", ""),
                bio=profile.get("bio", ""),
                follower_count=profile.get("follower_count", 0),
                following_count=profile.get("following_count", 0),
                is_business=1 if profile.get("is_business") else 0,
                is_private=1 if profile.get("is_private") else 0,
                category=profile.get("category", ""),
                website=profile.get("website", ""),
                email_from_bio=profile.get("email_from_bio", ""),
                profile_pic_url=profile.get("profile_pic_url", ""),
                last_scanned_at=db._now(),
            )
            stats["scraped"] += 1

            # Run ICP scoring if we got a useful bio
            bio = profile.get("bio", "")
            if bio and bio not in ("", "No bio"):
                try:
                    result = score_icp(profile)
                    db.upsert_prospect(
                        ig_handle=handle,
                        icp_score=result.get("score", 0),
                        icp_reasoning=result.get("reasoning", ""),
                        offer_match=result.get("offer_match", "none"),
                    )
                    stats["scored"] += 1
                    logger.info("  @%s: bio=%s... | ICP=%d (%s)",
                                handle, bio[:40], result.get("score", 0),
                                result.get("offer_match", "none"))
                except Exception as e:
                    logger.warning("  @%s: ICP scoring error: %s", handle, e)
            else:
                logger.info("  @%s: no useful bio to score", handle)

            # Rate limit sleep
            wait = random.uniform(2, 5)
            time.sleep(wait)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        browser.disconnect()

    logger.info("=== ENRICHMENT RESULTS ===")
    logger.info("  Scraped:     %d", stats["scraped"])
    logger.info("  ICP scored:  %d", stats["scored"])
    logger.info("  Private:     %d", stats["private"])
    logger.info("  Errors:      %d", stats["errors"])
    if blocklist_check:
        logger.info("  Blocklisted: %d", stats["blocklisted"])


def run_score_only(limit: int = 100):
    """Re-score prospects that have bio data but icp_score = 0."""
    prospects = get_unscored_prospects(limit)
    if not prospects:
        logger.info("No unscored prospects with bio data found")
        return

    logger.info("Found %d prospects to score", len(prospects))
    scored = 0
    errors = 0

    for i, prospect in enumerate(prospects):
        handle = prospect["ig_handle"]
        logger.info("[%d/%d] Scoring @%s...", i + 1, len(prospects), handle)

        try:
            result = score_icp(prospect)
            db.upsert_prospect(
                ig_handle=handle,
                icp_score=result.get("score", 0),
                icp_reasoning=result.get("reasoning", ""),
                offer_match=result.get("offer_match", "none"),
            )
            scored += 1
            logger.info("  @%s: ICP=%d (%s) — %s",
                        handle, result.get("score", 0),
                        result.get("offer_match", "none"),
                        result.get("reasoning", "")[:60])
        except Exception as e:
            logger.warning("  @%s: scoring error: %s", handle, e)
            errors += 1

    logger.info("=== SCORING RESULTS ===")
    logger.info("  Scored:  %d", scored)
    logger.info("  Errors:  %d", errors)


def main():
    parser = argparse.ArgumentParser(description="Profile Enricher — scrape + ICP score")
    parser.add_argument("--limit", type=int, default=100, help="Max profiles to process")
    parser.add_argument("--score-only", action="store_true",
                        help="Just re-score prospects with bio but icp_score=0")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without scraping")
    parser.add_argument("--stats", action="store_true",
                        help="Show enrichment coverage stats")
    parser.add_argument("--blocklist-check", action="store_true",
                        help="Add private accounts to blocklist during enrichment")
    args = parser.parse_args()

    if args.stats:
        print_stats()
    elif args.score_only:
        run_score_only(limit=args.limit)
    else:
        run_enrichment(limit=args.limit, dry_run=args.dry_run,
                       blocklist_check=args.blocklist_check)


if __name__ == "__main__":
    main()
