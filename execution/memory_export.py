#!/usr/bin/env python3
"""
memory_export.py — Generate brain.md from the SQLite DB.

brain.md becomes a read-only export, regenerated on demand or at session close.

Usage:
    python execution/memory_export.py                    # Export to stdout
    python execution/memory_export.py --output brain.md  # Write to file
    python execution/memory_export.py --format json      # JSON export
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from execution.memory_store import MemoryStore, DB_PATH

BRAIN_PATH = Path("/Users/Shared/antigravity/memory/ceo/brain.md")


def export_brain_md(store):
    """Generate brain.md format from the DB."""
    lines = []
    now = datetime.now()

    # Meta
    stats = store.stats()
    lines.extend([
        "# CEO Brain — Persistent Consciousness",
        "> Auto-generated from memory.db. Source of truth is the database.",
        "> Regenerated: {}".format(now.strftime("%Y-%m-%d %H:%M")),
        "",
        "---",
        "",
        "## Meta",
        "",
        "```",
        "Brain Version: 3.0 (SQLite-backed)",
        "Total Memories: {} active, {} archived".format(stats["total_active"], stats["total_archived"]),
        "DB Size: {} KB".format(stats["db_size_kb"]),
        "Last Export: {}".format(now.isoformat()),
        "```",
        "",
        "---",
        "",
    ])

    # Decisions Log
    decisions = store.conn.execute(
        """SELECT source_session, title, content FROM memories
           WHERE type = 'decision' AND is_archived = 0
           ORDER BY created_at DESC"""
    ).fetchall()
    if decisions:
        lines.extend([
            "## Decisions Log",
            "",
            "| Date | Decision | Context |",
            "|---|---|---|",
        ])
        for d in decisions:
            date = d[0] if d[0] else "?"
            title = d[1].replace("|", "/")[:150]
            # Extract context from content if it has "Context: " suffix
            content = d[2] or ""
            context = ""
            if "\nContext: " in content:
                context = content.split("\nContext: ", 1)[1][:200].replace("|", "/")
            lines.append("| {} | {} | {} |".format(date[:10], title, context))
        lines.extend(["", "---", ""])

    # Preferences
    preferences = store.conn.execute(
        """SELECT title FROM memories
           WHERE type = 'preference' AND is_archived = 0
           ORDER BY access_count DESC, created_at DESC"""
    ).fetchall()
    if preferences:
        lines.extend(["## Preferences", ""])
        seen = set()
        for p in preferences:
            text = p[0].strip()
            # Deduplicate on display
            norm = text.lower()[:80]
            if norm in seen:
                continue
            seen.add(norm)
            lines.append("- {}".format(text))
        lines.extend(["", "---", ""])

    # Learnings
    learnings = store.conn.execute(
        """SELECT source_session, title, content FROM memories
           WHERE type = 'learning' AND is_archived = 0
           ORDER BY created_at DESC"""
    ).fetchall()
    if learnings:
        lines.extend([
            "## Learnings",
            "",
            "| Date | Learning | Source |",
            "|---|---|---|",
        ])
        for l_row in learnings:
            date = l_row[0] if l_row[0] else "?"
            title = l_row[1].replace("|", "/")[:150]
            content = l_row[2] or ""
            source = ""
            if "\nSource: " in content:
                source = content.split("\nSource: ", 1)[1][:100].replace("|", "/")
            lines.append("| {} | {} | {} |".format(date[:10], title, source))
        lines.extend(["", "---", ""])

    # Asset Registry
    assets = store.conn.execute(
        """SELECT title, content FROM memories
           WHERE type = 'asset' AND is_archived = 0
           ORDER BY created_at DESC"""
    ).fetchall()
    if assets:
        lines.extend(["## Asset Registry", ""])
        for a in assets:
            content = a[1] or ""
            if content.startswith("Path: "):
                path_line = content.split("\n")[0].replace("Path: ", "")
                desc = "\n".join(content.split("\n")[1:]).strip()
                lines.append("- `{}` — {}".format(path_line, desc[:200]))
            else:
                lines.append("- {}".format(a[0]))
        lines.extend(["", "---", ""])

    # People
    people = store.conn.execute(
        """SELECT title, content FROM memories
           WHERE type = 'person' AND is_archived = 0
           ORDER BY access_count DESC, created_at DESC"""
    ).fetchall()
    if people:
        lines.extend(["## People & Relationships", ""])
        for p in people:
            lines.append("- **{}**: {}".format(p[0], (p[1] or "")[:200]))
        lines.extend(["", "---", ""])

    # Recent Events (last 30 days)
    events = store.get_recent(days=30, type_filter="event", limit=20)
    if events:
        lines.extend(["## Recent Events (30 days)", ""])
        for e in events:
            lines.append("- [{}] {}".format(e["created_at"][:10], e["title"][:120]))
        lines.extend([""])

    return "\n".join(lines)


def export_json(store):
    """Export all active memories as JSON."""
    rows = store.conn.execute(
        "SELECT * FROM memories WHERE is_archived = 0 ORDER BY created_at DESC"
    ).fetchall()
    memories = [dict(row) for row in rows]
    return json.dumps(memories, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(description="Export memory DB to brain.md or JSON")
    parser.add_argument("--format", choices=["brain", "json"], default="brain")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    store = MemoryStore(DB_PATH)

    if args.format == "brain":
        output = export_brain_md(store)
    else:
        output = export_json(store)

    if args.output:
        Path(args.output).write_text(output)
        print("Exported to {}".format(args.output))
    else:
        print(output)


if __name__ == "__main__":
    main()
