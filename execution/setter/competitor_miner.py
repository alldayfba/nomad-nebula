#!/usr/bin/env python3
"""
Competitor Miner -- scrapes followers from competitor FBA coaching accounts.

These leads are pre-qualified: they're already interested in Amazon FBA coaching.
They convert 2-3x higher than cold followers.

Usage:
    python -m execution.setter.competitor_miner --account @competitorhandle --limit 200
    python -m execution.setter.competitor_miner --all --limit 100  # All configured competitors
    python -m execution.setter.competitor_miner --list  # Show configured competitors
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
from execution.setter.setter_config import COMPETITOR_ACCOUNTS, RATE_LIMITS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [competitor_miner] %(message)s")
logger = logging.getLogger("competitor_miner")

# Hard cap: don't scrape more than 500 profiles per day across all competitors
DAILY_SCRAPE_CAP = 500


def mine_competitor(browser: IGBrowserSync, competitor: str, limit: int = 200) -> Dict:
    """Scrape followers from a single competitor account and add to prospect DB.

    Args:
        browser: Connected IGBrowserSync instance.
        competitor: IG handle of the competitor (without @).
        limit: Max followers to collect from this competitor.

    Returns:
        Dict with keys: total_found, already_in_db, blocklisted, newly_added
    """
    competitor = competitor.lstrip("@").strip()
    stats = {"total_found": 0, "already_in_db": 0, "blocklisted": 0, "newly_added": 0}

    logger.info("Mining followers from @%s (limit: %d)...", competitor, limit)

    # Use IGBrowserSync.scan_followers which handles the scroll + collect
    handles = browser.scan_followers(competitor, max_count=limit)
    stats["total_found"] = len(handles)

    if not handles:
        logger.warning("No followers found for @%s — account may be private or not exist", competitor)
        return stats

    logger.info("Found %d followers from @%s, processing...", len(handles), competitor)

    for i, handle in enumerate(handles):
        handle = handle.strip().lstrip("@")
        if not handle:
            continue

        # Check blocklist
        if db.is_blocklisted(handle):
            stats["blocklisted"] += 1
            continue

        # Check if already in prospects DB
        existing = db.get_prospect_by_handle(handle)
        if existing:
            stats["already_in_db"] += 1
            continue

        # Add to prospects with competitor_follower source
        db.upsert_prospect(
            ig_handle=handle,
            source="competitor_follower",
            source_detail=f"follows @{competitor}",
        )
        stats["newly_added"] += 1

        # Rate limit: sleep 1-3s every 50 handles to avoid detection
        if (i + 1) % 50 == 0:
            wait = random.uniform(1.0, 3.0)
            logger.info("  Processed %d/%d, sleeping %.1fs...", i + 1, len(handles), wait)
            time.sleep(wait)

    logger.info(
        "@%s results: %d found, %d new, %d already in DB, %d blocklisted",
        competitor, stats["total_found"], stats["newly_added"],
        stats["already_in_db"], stats["blocklisted"],
    )
    return stats


def mine_all_competitors(browser: IGBrowserSync, offer: str = "all", limit_per: int = 100) -> Dict:
    """Mine followers from all configured competitor accounts.

    Args:
        browser: Connected IGBrowserSync instance.
        offer: Which offer's competitors to mine ('amazon_os', 'agency_os', or 'all').
        limit_per: Max followers per competitor account.

    Returns:
        Aggregate stats dict.
    """
    totals = {"total_found": 0, "already_in_db": 0, "blocklisted": 0, "newly_added": 0, "competitors_mined": 0}

    accounts_to_mine = {}
    if offer == "all":
        accounts_to_mine = COMPETITOR_ACCOUNTS
    elif offer in COMPETITOR_ACCOUNTS:
        accounts_to_mine = {offer: COMPETITOR_ACCOUNTS[offer]}
    else:
        logger.error("Unknown offer: %s", offer)
        return totals

    for offer_key, competitors in accounts_to_mine.items():
        if not competitors:
            logger.info("No competitors configured for %s — skipping", offer_key)
            continue

        for competitor in competitors:
            if totals["total_found"] >= DAILY_SCRAPE_CAP:
                logger.warning("Daily scrape cap (%d) reached, stopping", DAILY_SCRAPE_CAP)
                break

            remaining_cap = DAILY_SCRAPE_CAP - totals["total_found"]
            effective_limit = min(limit_per, remaining_cap)

            result = mine_competitor(browser, competitor, limit=effective_limit)
            for key in ("total_found", "already_in_db", "blocklisted", "newly_added"):
                totals[key] += result[key]
            totals["competitors_mined"] += 1

            # Sleep between competitors to avoid suspicion
            wait = random.uniform(5.0, 15.0)
            logger.info("Sleeping %.0fs before next competitor...", wait)
            time.sleep(wait)

    return totals


def list_competitors():
    """Print configured competitor accounts."""
    print("=" * 50)
    print("CONFIGURED COMPETITOR ACCOUNTS")
    print("=" * 50)
    for offer_key, competitors in COMPETITOR_ACCOUNTS.items():
        print(f"\n{offer_key}:")
        if not competitors:
            print("  (none configured)")
        else:
            for c in competitors:
                print(f"  @{c}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Competitor Follower Miner")
    parser.add_argument("--account", type=str, help="Single competitor handle to mine (e.g. @competitor)")
    parser.add_argument("--all", action="store_true", help="Mine all configured competitors")
    parser.add_argument("--offer", type=str, default="all",
                        choices=["amazon_os", "agency_os", "all"],
                        help="Which offer's competitors to mine (default: all)")
    parser.add_argument("--limit", type=int, default=200, help="Max followers per competitor")
    parser.add_argument("--list", action="store_true", help="List configured competitors")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be mined without connecting")
    args = parser.parse_args()

    if args.list:
        list_competitors()
        return

    if args.dry_run:
        if args.account:
            print(f"Would mine up to {args.limit} followers from @{args.account.lstrip('@')}")
        elif args.all:
            for offer_key, competitors in COMPETITOR_ACCOUNTS.items():
                if args.offer != "all" and offer_key != args.offer:
                    continue
                for c in competitors:
                    print(f"Would mine up to {args.limit} followers from @{c} ({offer_key})")
            if not any(COMPETITOR_ACCOUNTS.values()):
                print("No competitors configured. Edit setter_config.py COMPETITOR_ACCOUNTS.")
        return

    if not args.account and not args.all:
        parser.print_help()
        print("\nError: specify --account @handle or --all")
        return

    browser = IGBrowserSync()
    if not browser.connect():
        logger.error("Cannot connect to Chrome — is it running with IG logged in?")
        return

    try:
        if args.account:
            result = mine_competitor(browser, args.account, limit=args.limit)
        else:
            result = mine_all_competitors(browser, offer=args.offer, limit_per=args.limit)

        print("\n" + "=" * 50)
        print("COMPETITOR MINER RESULTS")
        print("=" * 50)
        for key, val in result.items():
            print(f"  {key}: {val}")
        print()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error("Miner error: %s", e, exc_info=True)
    finally:
        browser.disconnect()


if __name__ == "__main__":
    main()
