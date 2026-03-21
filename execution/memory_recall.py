#!/usr/bin/env python3
"""
memory_recall.py — Search and retrieve memories with multi-signal ranking.

Combines BM25 relevance, recency boost, and access frequency for optimal results.

Usage:
    # Search by query
    python execution/memory_recall.py --query "keepa tokens sourcing" --limit 5

    # Filter by type
    python execution/memory_recall.py --query "Mike Walker" --type person,event

    # Browse recent (no search query)
    python execution/memory_recall.py --recent --days 7

    # Browse by category
    python execution/memory_recall.py --category sourcing --limit 10

    # Programmatic:
    from execution.memory_recall import MemoryRecall
    recall = MemoryRecall()
    results = recall.search("keepa tokens", limit=5)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from execution.memory_store import MemoryStore, DB_PATH


class MemoryRecall:
    def __init__(self):
        self.store = MemoryStore(DB_PATH)

    def search(self, query: str, limit: int = 10, type_filter: str = None,
               category_filter: str = None) -> list:
        """Search with multi-signal ranking: BM25 + recency + access frequency."""
        results = self.store.search(query, limit=limit * 2,  # oversample for re-ranking
                                    type_filter=type_filter,
                                    category_filter=category_filter)
        if not results:
            return []

        # Apply recency and access boosts
        now = datetime.now()
        scored = []
        for r in results:
            base_score = abs(r.get("bm25_score", 0))  # Normalize to positive

            # Recency boost
            try:
                created = datetime.fromisoformat(r["created_at"])
                age_days = (now - created).days
                if age_days <= 7:
                    recency_boost = 0.3
                elif age_days <= 30:
                    recency_boost = 0.15
                elif age_days <= 90:
                    recency_boost = 0.05
                else:
                    recency_boost = 0.0
            except (ValueError, KeyError):
                recency_boost = 0.0

            # Access frequency boost (capped at 0.2)
            access_count = r.get("access_count", 0)
            access_boost = min(access_count * 0.02, 0.2)

            # Combined score (higher = better)
            combined = base_score + recency_boost + access_boost
            r["combined_score"] = round(combined, 4)
            scored.append(r)

        # Sort by combined score descending, take top N
        scored.sort(key=lambda x: x["combined_score"], reverse=True)
        return scored[:limit]

    def recent(self, days: int = 7, type_filter: str = None, limit: int = 20) -> list:
        """Get recent memories without a search query."""
        return self.store.get_recent(days=days, type_filter=type_filter, limit=limit)

    def by_category(self, category: str, limit: int = 10) -> list:
        """Browse memories by category."""
        rows = self.store.conn.execute(
            """SELECT *, 0.0 as bm25_score FROM memories
               WHERE category = ? AND is_archived = 0
               ORDER BY updated_at DESC LIMIT ?""",
            (category, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def context_for_task(self, task_description: str, limit: int = 5) -> str:
        """Get a formatted context block relevant to a task. Used by auto-retrieval."""
        results = self.search(task_description, limit=limit)
        if not results:
            return "No relevant memories found."

        lines = ["## Relevant Memories ({} results)".format(len(results)), ""]
        for r in results:
            lines.append("**[{}|{}]** {} (#{})".format(r["type"], r["category"], r["title"], r["id"]))
            # Truncate content to keep context compact
            content = r["content"]
            if len(content) > 200:
                content = content[:200] + "..."
            lines.append(content)
            lines.append("")

        return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def format_result(m: dict, verbose: bool = False) -> str:
    """Format a single memory result."""
    score_str = ""
    if m.get("combined_score"):
        score_str = "  [score: {:.3f}]".format(m["combined_score"])
    elif m.get("bm25_score") and m["bm25_score"] != 0:
        score_str = "  [bm25: {:.2f}]".format(m["bm25_score"])

    line = "[#{id}] ({type}/{category}) {title}{score}".format(score=score_str, **m)

    if verbose:
        line += "\n    {}".format(m["content"][:300])
        if m.get("tags"):
            line += "\n    Tags: {}".format(m["tags"])
        line += "\n    Created: {} | Updated: {} | Accessed: {} times".format(
            m["created_at"][:10], m["updated_at"][:10], m.get("access_count", 0))
    return line


def main():
    parser = argparse.ArgumentParser(description="Search and retrieve memories")
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--type", "-t", help="Filter by type (comma-separated)")
    parser.add_argument("--category", "-c", help="Filter or browse by category")
    parser.add_argument("--limit", "-l", type=int, default=10)
    parser.add_argument("--recent", "-r", action="store_true", help="Browse recent memories")
    parser.add_argument("--days", "-d", type=int, default=7, help="Days for --recent")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--context", action="store_true", help="Output as context block for task")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()
    recall = MemoryRecall()

    if args.context and args.query:
        print(recall.context_for_task(args.query, limit=args.limit))
        return

    if args.recent:
        results = recall.recent(days=args.days, type_filter=args.type, limit=args.limit)
        label = "Recent memories (last {} days)".format(args.days)
    elif args.category and not args.query:
        results = recall.by_category(args.category, limit=args.limit)
        label = "Memories in category: {}".format(args.category)
    elif args.query:
        results = recall.search(args.query, limit=args.limit,
                                type_filter=args.type, category_filter=args.category)
        label = "Search results for '{}'".format(args.query)
    else:
        parser.print_help()
        return

    if args.json:
        # Clean up for JSON output
        for r in results:
            for k in list(r.keys()):
                if r[k] is None:
                    r[k] = ""
        print(json.dumps(results, indent=2, default=str))
        return

    if results:
        print("{} ({} results):".format(label, len(results)))
        for r in results:
            print("  " + format_result(r, verbose=args.verbose))
    else:
        print("{}: no results".format(label))


if __name__ == "__main__":
    main()
