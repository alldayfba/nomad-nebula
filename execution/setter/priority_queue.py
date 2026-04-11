#!/usr/bin/env python3
"""
Priority Queue — generates an ordered DM queue for the setter.

Ranks prospects by a composite score:
  priority = (icp_score * 5) + (heat_score * 0.2) + recency_bonus + source_bonus + bio_bonus

Higher priority = DM first.

Usage:
    python -m execution.setter.priority_queue --limit 200    # Generate queue
    python -m execution.setter.priority_queue --show          # Show current queue
    python -m execution.setter.priority_queue --stats         # Show queue analytics
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from execution.setter import setter_db as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [queue] %(message)s")
logger = logging.getLogger("queue")

# ── Priority Scoring ────────────────────────────────────────────────────────

SOURCE_BONUS = {
    "comment_trigger": 15,
    "story_viewer": 10,
    "inbound_dm": 20,
    "new_follower": 5,
    "follower_scroll": 3,
    "hashtag": 8,
    "competitor_follower": 12,
    "ig_export": 2,
    "story_reply": 18,
    "post_comment": 15,
    "post_like": 4,
    "manychat_keyword": 16,
    "ad_lead": 14,
    "referral": 17,
    "manual": 1,
}


def calculate_priority(prospect: Dict, conversation: Optional[Dict] = None) -> int:
    """Calculate DM priority score (0-100)."""
    score = 0

    # ICP score (0-10 * 5 = 0-50 points)
    score += (prospect.get("icp_score", 0) or 0) * 5

    # Heat score (0-100 * 0.2 = 0-20 points)
    heat = conversation.get("heat_score", 0) if conversation else 0
    score += (heat or 0) * 0.2

    # Source bonus (higher intent sources score more)
    score += SOURCE_BONUS.get(prospect.get("source", ""), 0)

    # Recency bonus -- newer followers more likely to engage
    try:
        created = datetime.strptime(prospect.get("created_at", ""), "%Y-%m-%d %H:%M:%S")
        days_old = (datetime.now() - created).days
        if days_old <= 1:
            score += 10
        elif days_old <= 7:
            score += 7
        elif days_old <= 30:
            score += 3
    except (ValueError, TypeError):
        pass

    # Bio quality bonus -- has bio = can personalize
    bio = prospect.get("bio")
    if bio and bio not in ("", "No bio", None):
        score += 5

    return min(100, max(0, int(score)))


def _explain_priority(prospect: Dict, total_score: int) -> str:
    """Generate a short human-readable explanation of the priority score."""
    parts = []
    icp = prospect.get("icp_score", 0) or 0
    if icp > 0:
        parts.append(f"ICP:{icp}")
    source = prospect.get("source", "")
    sb = SOURCE_BONUS.get(source, 0)
    if sb > 0:
        parts.append(f"src:{source}(+{sb})")
    bio = prospect.get("bio")
    if bio and bio not in ("", "No bio", None):
        parts.append("has_bio")
    try:
        created = datetime.strptime(prospect.get("created_at", ""), "%Y-%m-%d %H:%M:%S")
        days = (datetime.now() - created).days
        if days <= 1:
            parts.append("new(<1d)")
        elif days <= 7:
            parts.append(f"recent({days}d)")
    except (ValueError, TypeError):
        pass
    return " | ".join(parts) if parts else "base"


# ── Queue Generation ────────────────────────────────────────────────────────

def generate_queue(limit: int = 200) -> List[Dict]:
    """Generate a prioritized DM queue from uncontacted prospects.

    Returns list of {prospect_id, ig_handle, priority_score, reason}.
    Also saves to dm_queue table.
    """
    d = db.get_db()

    # Get all new prospects that are NOT blocklisted and NOT in a conversation
    rows = d.execute(
        """SELECT p.* FROM prospects p
           LEFT JOIN conversations c ON c.prospect_id = p.id
           LEFT JOIN blocklist b ON b.ig_handle = p.ig_handle
           WHERE c.id IS NULL
           AND b.id IS NULL
           AND p.status IN ('new', 'qualified')
           ORDER BY p.created_at DESC""",
    ).fetchall()

    candidates = [dict(r) for r in rows]
    logger.info("Found %d uncontacted, non-blocklisted prospects", len(candidates))

    if not candidates:
        logger.info("No candidates for queue")
        return []

    # Score and sort
    scored = []
    for prospect in candidates:
        # Check if there's a heat-scored conversation (unlikely for uncontacted, but handle it)
        conv = db.get_conversation_by_prospect(prospect["id"], include_closed=True)
        priority = calculate_priority(prospect, conv)
        reason = _explain_priority(prospect, priority)
        scored.append({
            "prospect_id": prospect["id"],
            "ig_handle": prospect["ig_handle"],
            "priority_score": priority,
            "reason": reason,
            "icp_score": prospect.get("icp_score", 0) or 0,
            "source": prospect.get("source", ""),
            "bio": (prospect.get("bio") or "")[:50],
        })

    # Sort by priority descending
    scored.sort(key=lambda x: x["priority_score"], reverse=True)

    # Take top N
    top = scored[:limit]

    # Save to DB
    queue_entries = [
        {"prospect_id": s["prospect_id"], "priority_score": s["priority_score"]}
        for s in top
    ]
    db.save_dm_queue(queue_entries)

    logger.info("Saved %d entries to dm_queue", len(top))
    return top


def show_queue(limit: int = 50):
    """Display the current pending queue."""
    queue = db.get_pending_queue(limit=limit)
    if not queue:
        print("\nNo pending queue entries. Run --limit N to generate one.")
        return

    print(f"\n=== DM QUEUE ({len(queue)} pending) ===")
    print(f"{'#':<4} {'Handle':<25} {'Priority':<10} {'ICP':<5} {'Source':<20} {'Queued':<20}")
    print("-" * 84)

    for i, entry in enumerate(queue, 1):
        handle = entry.get("ig_handle", "?")
        priority = entry.get("priority_score", 0)
        icp = entry.get("icp_score", 0) or 0
        source = entry.get("source", "?")
        queued = entry.get("queued_at", "?")
        print(f"{i:<4} @{handle:<24} {priority:<10} {icp:<5} {source:<20} {queued:<20}")

    print()


def show_stats():
    """Show queue analytics."""
    d = db.get_db()
    db._ensure_dm_queue_table()

    total_pending = d.execute(
        "SELECT COUNT(*) FROM dm_queue WHERE status = 'pending'"
    ).fetchone()[0]
    total_sent = d.execute(
        "SELECT COUNT(*) FROM dm_queue WHERE status = 'sent'"
    ).fetchone()[0]

    print("\n=== QUEUE ANALYTICS ===")
    print(f"  Pending:  {total_pending}")
    print(f"  Sent:     {total_sent}")

    if total_pending > 0:
        # Score distribution in queue
        dist = d.execute(
            """SELECT
                SUM(CASE WHEN priority_score >= 70 THEN 1 ELSE 0 END) as tier1,
                SUM(CASE WHEN priority_score >= 40 AND priority_score < 70 THEN 1 ELSE 0 END) as tier2,
                SUM(CASE WHEN priority_score < 40 THEN 1 ELSE 0 END) as tier3,
                AVG(priority_score) as avg_score,
                MAX(priority_score) as max_score,
                MIN(priority_score) as min_score
               FROM dm_queue WHERE status = 'pending'"""
        ).fetchone()
        d_dict = dict(dist)
        print(f"\n  Priority Distribution (pending):")
        print(f"    Tier 1 (70+):   {d_dict['tier1'] or 0}")
        print(f"    Tier 2 (40-69): {d_dict['tier2'] or 0}")
        print(f"    Tier 3 (<40):   {d_dict['tier3'] or 0}")
        print(f"    Avg score:      {d_dict['avg_score']:.1f}")
        print(f"    Max score:      {d_dict['max_score']}")
        print(f"    Min score:      {d_dict['min_score']}")

    # Uncontacted prospects not in queue
    unqueued = d.execute(
        """SELECT COUNT(*) FROM prospects p
           LEFT JOIN conversations c ON c.prospect_id = p.id
           LEFT JOIN dm_queue q ON q.prospect_id = p.id
           LEFT JOIN blocklist b ON b.ig_handle = p.ig_handle
           WHERE c.id IS NULL AND q.id IS NULL AND b.id IS NULL
           AND p.status IN ('new', 'qualified')"""
    ).fetchone()[0]
    print(f"\n  Uncontacted not in queue: {unqueued}")
    print()


def get_queue_for_blitz(limit: int = 200) -> List[Dict]:
    """Get the pending queue as a list for follower_blitz integration.

    Returns list of dicts with ig_handle and prospect data needed for DMing.
    """
    return db.get_pending_queue(limit=limit)


def main():
    parser = argparse.ArgumentParser(description="Priority Queue — smart DM ordering")
    parser.add_argument("--limit", type=int, default=200,
                        help="Max entries in queue (default 200)")
    parser.add_argument("--show", action="store_true",
                        help="Show current pending queue")
    parser.add_argument("--stats", action="store_true",
                        help="Show queue analytics")
    args = parser.parse_args()

    if args.show:
        show_queue()
    elif args.stats:
        show_stats()
    else:
        queue = generate_queue(limit=args.limit)
        if queue:
            print(f"\n=== TOP {min(20, len(queue))} IN QUEUE ===")
            print(f"{'#':<4} {'Handle':<25} {'Score':<8} {'ICP':<5} {'Source':<20} {'Reason'}")
            print("-" * 100)
            for i, entry in enumerate(queue[:20], 1):
                print(f"{i:<4} @{entry['ig_handle']:<24} {entry['priority_score']:<8} "
                      f"{entry['icp_score']:<5} {entry['source']:<20} {entry['reason']}")
            if len(queue) > 20:
                print(f"  ... and {len(queue) - 20} more")
            print()


if __name__ == "__main__":
    main()
