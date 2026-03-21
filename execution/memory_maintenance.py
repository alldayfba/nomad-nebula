#!/usr/bin/env python3
"""
memory_maintenance.py — Integrity checks, auto-archive, confidence decay.

Replaces brain_maintenance.py. Runs on Stop hook or manually.

Usage:
    python execution/memory_maintenance.py              # Full maintenance
    python execution/memory_maintenance.py --check      # Integrity check only
    python execution/memory_maintenance.py --archive     # Archive old memories
    python execution/memory_maintenance.py --decay       # Apply confidence decay
    python execution/memory_maintenance.py --dedup       # Find duplicates
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from execution.memory_store import MemoryStore, DB_PATH

# Memories older than this with 0 access get archived
ARCHIVE_DAYS = 90
# Types that are NEVER auto-archived
PERMANENT_TYPES = {"decision", "correction", "preference"}
# Confidence decay rate per 30 days for time-sensitive types
DECAY_RATE = 0.1
DECAY_TYPES = {"event"}  # Only events decay
# Min confidence before auto-archive
MIN_CONFIDENCE = 0.2


def check_integrity(store):
    """Run integrity checks on the memory DB."""
    issues = []

    # 1. FTS5 integrity
    try:
        store.conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('integrity-check')")
        print("  FTS5 index: OK")
    except Exception as e:
        issues.append("FTS5 integrity failed: {}".format(e))
        print("  FTS5 index: FAILED — {}".format(e))

    # 2. Orphaned links
    orphaned = store.conn.execute("""
        SELECT ml.id, ml.source_id, ml.target_id, ml.relation
        FROM memory_links ml
        LEFT JOIN memories m1 ON ml.source_id = m1.id
        LEFT JOIN memories m2 ON ml.target_id = m2.id
        WHERE m1.id IS NULL OR m2.id IS NULL
    """).fetchall()
    if orphaned:
        issues.append("{} orphaned links".format(len(orphaned)))
        print("  Orphaned links: {} found".format(len(orphaned)))
        for o in orphaned:
            store.conn.execute("DELETE FROM memory_links WHERE id = ?", (o[0],))
        store.conn.commit()
        print("    Cleaned up {} orphaned links".format(len(orphaned)))
    else:
        print("  Orphaned links: none")

    # 3. Superseded chain integrity
    broken_chains = store.conn.execute("""
        SELECT id, title, superseded_by FROM memories
        WHERE superseded_by IS NOT NULL
        AND superseded_by NOT IN (SELECT id FROM memories)
    """).fetchall()
    if broken_chains:
        issues.append("{} broken supersedence chains".format(len(broken_chains)))
        print("  Broken chains: {} found".format(len(broken_chains)))
        for bc in broken_chains:
            store.conn.execute(
                "UPDATE memories SET superseded_by = NULL WHERE id = ?", (bc[0],))
        store.conn.commit()
        print("    Fixed {} broken chains".format(len(broken_chains)))
    else:
        print("  Supersedence chains: OK")

    # 4. DB stats
    stats = store.stats()
    print("  Total: {} active, {} archived, {} KB".format(
        stats["total_active"], stats["total_archived"], stats["db_size_kb"]))

    return issues


def archive_old(store):
    """Archive memories older than ARCHIVE_DAYS with 0 access."""
    cutoff = (datetime.now() - timedelta(days=ARCHIVE_DAYS)).isoformat()
    type_placeholders = ",".join("?" * len(PERMANENT_TYPES))

    rows = store.conn.execute(
        """SELECT id, type, title FROM memories
           WHERE created_at < ? AND access_count = 0
           AND is_archived = 0
           AND type NOT IN ({})""".format(type_placeholders),
        [cutoff] + list(PERMANENT_TYPES),
    ).fetchall()

    if rows:
        now = datetime.now().isoformat()
        for row in rows:
            store.conn.execute(
                "UPDATE memories SET is_archived = 1, updated_at = ? WHERE id = ?",
                (now, row[0]),
            )
        store.conn.commit()
        print("  Archived {} old memories (>{} days, 0 access)".format(len(rows), ARCHIVE_DAYS))
    else:
        print("  No memories to archive")


def apply_decay(store):
    """Apply confidence decay to time-sensitive memories."""
    now = datetime.now()
    type_placeholders = ",".join("?" * len(DECAY_TYPES))

    rows = store.conn.execute(
        """SELECT id, confidence, created_at, type FROM memories
           WHERE type IN ({})
           AND is_archived = 0
           AND confidence > ?""".format(type_placeholders),
        list(DECAY_TYPES) + [MIN_CONFIDENCE],
    ).fetchall()

    decayed = 0
    archived = 0
    for row in rows:
        try:
            created = datetime.fromisoformat(row[2])
            age_days = (now - created).days
            periods = age_days // 30  # How many 30-day periods
            new_confidence = max(MIN_CONFIDENCE, row[1] - (DECAY_RATE * periods))

            if new_confidence != row[1]:
                if new_confidence <= MIN_CONFIDENCE:
                    # Auto-archive very low confidence
                    store.conn.execute(
                        "UPDATE memories SET confidence = ?, is_archived = 1, updated_at = ? WHERE id = ?",
                        (new_confidence, now.isoformat(), row[0]),
                    )
                    archived += 1
                else:
                    store.conn.execute(
                        "UPDATE memories SET confidence = ?, updated_at = ? WHERE id = ?",
                        (new_confidence, now.isoformat(), row[0]),
                    )
                    decayed += 1
        except (ValueError, TypeError):
            continue

    store.conn.commit()
    print("  Confidence decay: {} updated, {} archived (below {})".format(
        decayed, archived, MIN_CONFIDENCE))


def find_duplicates(store):
    """Find potential duplicate memories using word overlap."""
    rows = store.conn.execute(
        """SELECT id, title, content FROM memories
           WHERE is_archived = 0
           ORDER BY id"""
    ).fetchall()

    dupes_found = 0
    seen = {}  # normalized_title -> id

    for row in rows:
        norm = row[1].lower().strip()[:80]
        if norm in seen:
            dupes_found += 1
            print("  Potential dupe: #{} '{}' matches #{} '{}'".format(
                row[0], row[1][:60], seen[norm], norm[:60]))
        else:
            seen[norm] = row[0]

    if dupes_found == 0:
        print("  No duplicates found")
    else:
        print("  {} potential duplicates found (use memory_store.py merge to resolve)".format(dupes_found))


def main():
    parser = argparse.ArgumentParser(description="Memory maintenance — integrity, archive, decay")
    parser.add_argument("--check", action="store_true", help="Integrity check only")
    parser.add_argument("--archive", action="store_true", help="Archive old memories only")
    parser.add_argument("--decay", action="store_true", help="Apply confidence decay only")
    parser.add_argument("--dedup", action="store_true", help="Find duplicates only")
    args = parser.parse_args()

    store = MemoryStore(DB_PATH)
    run_all = not any([args.check, args.archive, args.decay, args.dedup])

    print("Memory Maintenance — {}".format(datetime.now().strftime("%Y-%m-%d %H:%M")))

    if run_all or args.check:
        print("\n[Integrity Check]")
        check_integrity(store)

    if run_all or args.archive:
        print("\n[Auto-Archive]")
        archive_old(store)

    if run_all or args.decay:
        print("\n[Confidence Decay]")
        apply_decay(store)

    if run_all or args.dedup:
        print("\n[Duplicate Detection]")
        find_duplicates(store)

    print("\nDone.")


if __name__ == "__main__":
    main()
