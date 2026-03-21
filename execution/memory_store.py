#!/usr/bin/env python3
"""
memory_store.py — Core CRUD for the 10/10 memory system.

SQLite + FTS5 BM25 ranked full-text search. Zero external dependencies.
Every memory is typed, categorized, tagged, versioned, and dedup-checked.

Usage:
    # Add a memory (auto dedup check)
    python execution/memory_store.py add \
        --type decision --category agency \
        --title "Switched to retainer pricing" \
        --content "Moved from project to retainer model for agency clients" \
        --tags "pricing,agency"

    # Update existing (searches, creates version record)
    python execution/memory_store.py update \
        --search "retainer pricing" \
        --content "Updated range to $5K-$25K/mo" \
        --reason "Refined tier structure"

    # Merge duplicates
    python execution/memory_store.py merge --ids 5,12,18

    # Stats
    python execution/memory_store.py stats

    # Delete (soft)
    python execution/memory_store.py delete --id 42

    # Programmatic:
    from execution.memory_store import MemoryStore
    store = MemoryStore()
    store.add("decision", "agency", "Title", "Content", tags="pricing,agency")
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/Users/Shared/antigravity/memory/ceo/memory.db")

VALID_TYPES = {
    "decision", "learning", "preference", "event", "asset",
    "person", "error", "correction", "idea",
}

VALID_CATEGORIES = {
    "agency", "amazon", "sourcing", "sales", "content",
    "technical", "agent", "client", "student", "general",
}

# BM25 dedup threshold — scores closer to 0 are better matches in FTS5.
# FTS5 bm25() returns negative values; more negative = better match.
DEDUP_THRESHOLD = -5.0  # Matches scoring better (more negative) than this are dupes


class MemoryStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """Create tables and FTS5 index if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT DEFAULT 'session',
                source_session TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                superseded_by INTEGER REFERENCES memories(id),
                confidence REAL DEFAULT 1.0,
                access_count INTEGER DEFAULT 0,
                last_accessed TEXT,
                ttl_days INTEGER,
                tags TEXT DEFAULT '',
                is_archived INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
            CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(is_archived);
            CREATE INDEX IF NOT EXISTS idx_memories_superseded ON memories(superseded_by);

            CREATE TABLE IF NOT EXISTS memory_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL REFERENCES memories(id),
                target_id INTEGER NOT NULL REFERENCES memories(id),
                relation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(source_id, target_id, relation)
            );

            CREATE INDEX IF NOT EXISTS idx_links_source ON memory_links(source_id);
            CREATE INDEX IF NOT EXISTS idx_links_target ON memory_links(target_id);

            CREATE TABLE IF NOT EXISTS memory_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL REFERENCES memories(id),
                version INTEGER NOT NULL,
                content_before TEXT NOT NULL,
                content_after TEXT NOT NULL,
                change_reason TEXT,
                changed_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_versions_memory
                ON memory_versions(memory_id, version);

            CREATE TABLE IF NOT EXISTS session_context (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                topics TEXT,
                summary TEXT,
                files_modified TEXT,
                decisions_made TEXT,
                open_threads TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_session_started
                ON session_context(started_at);

            CREATE TABLE IF NOT EXISTS retrieval_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL REFERENCES memories(id),
                query TEXT NOT NULL,
                rank_position INTEGER,
                bm25_score REAL,
                retrieved_at TEXT NOT NULL
            );
        """)

        # FTS5 virtual table — created separately (can't use IF NOT EXISTS)
        try:
            self.conn.execute("""
                CREATE VIRTUAL TABLE memories_fts USING fts5(
                    title,
                    content,
                    tags,
                    content=memories,
                    content_rowid=id,
                    tokenize='porter unicode61'
                )
            """)
        except sqlite3.OperationalError:
            pass  # Already exists

        # FTS sync triggers
        for trigger_sql in [
            """CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, title, content, tags)
                VALUES (new.id, new.title, new.content, new.tags);
            END""",
            """CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, title, content, tags)
                VALUES ('delete', old.id, old.title, old.content, old.tags);
            END""",
            """CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, title, content, tags)
                VALUES ('delete', old.id, old.title, old.content, old.tags);
                INSERT INTO memories_fts(rowid, title, content, tags)
                VALUES (new.id, new.title, new.content, new.tags);
            END""",
        ]:
            try:
                self.conn.execute(trigger_sql)
            except sqlite3.OperationalError:
                pass  # Already exists

        self.conn.commit()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(
        self,
        type: str,
        category: str,
        title: str,
        content: str,
        tags: str = "",
        source: str = "session",
        source_session: str = "",
        ttl_days: int = None,
        confidence: float = 1.0,
        skip_dedup: bool = False,
    ) -> dict:
        """Add a memory. Returns the new memory or the existing dupe."""
        if type not in VALID_TYPES:
            return {"error": "Invalid type '{}'. Valid: {}".format(type, ", ".join(sorted(VALID_TYPES)))}
        if category not in VALID_CATEGORIES:
            return {"error": "Invalid category '{}'. Valid: {}".format(category, ", ".join(sorted(VALID_CATEGORIES)))}

        # Dedup check
        if not skip_dedup:
            dupe = self._check_dedup(title, content)
            if dupe:
                return {
                    "status": "duplicate",
                    "existing_id": dupe["id"],
                    "existing_title": dupe["title"],
                    "score": dupe["score"],
                    "message": "Similar memory already exists (id={}): {}".format(dupe["id"], dupe["title"]),
                }

        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            """INSERT INTO memories
               (type, category, title, content, source, source_session,
                created_at, updated_at, confidence, ttl_days, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (type, category, title, content, source, source_session,
             now, now, confidence, ttl_days, tags),
        )
        self.conn.commit()
        new_id = cursor.lastrowid

        return {
            "status": "created",
            "id": new_id,
            "type": type,
            "category": category,
            "title": title,
        }

    def update(
        self,
        search_query: str,
        new_content: str,
        reason: str = "",
    ) -> dict:
        """Find a memory by search, update it, and create a version record."""
        # Find best match
        matches = self._fts_search(search_query, limit=1)
        if not matches:
            return {"error": "No memory found matching '{}'".format(search_query)}

        memory = matches[0]
        memory_id = memory["id"]
        old_content = memory["content"]

        if old_content == new_content:
            return {"status": "unchanged", "id": memory_id, "title": memory["title"]}

        # Get current version number
        row = self.conn.execute(
            "SELECT MAX(version) FROM memory_versions WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        next_version = (row[0] or 0) + 1

        now = datetime.now().isoformat()

        # Create version record
        self.conn.execute(
            """INSERT INTO memory_versions
               (memory_id, version, content_before, content_after, change_reason, changed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (memory_id, next_version, old_content, new_content, reason, now),
        )

        # Update the memory
        self.conn.execute(
            "UPDATE memories SET content = ?, updated_at = ? WHERE id = ?",
            (new_content, now, memory_id),
        )
        self.conn.commit()

        return {
            "status": "updated",
            "id": memory_id,
            "title": memory["title"],
            "version": next_version,
            "reason": reason,
        }

    def merge(self, ids: list) -> dict:
        """Merge multiple memories into one. First ID becomes the target."""
        if len(ids) < 2:
            return {"error": "Need at least 2 IDs to merge"}

        rows = self.conn.execute(
            "SELECT * FROM memories WHERE id IN ({}) AND is_archived = 0".format(
                ",".join("?" * len(ids))
            ),
            ids,
        ).fetchall()

        if len(rows) < 2:
            return {"error": "Found fewer than 2 active memories for given IDs"}

        target = rows[0]
        now = datetime.now().isoformat()

        # Merge content from all sources
        merged_content = target["content"]
        merged_tags = set(t.strip() for t in (target["tags"] or "").split(",") if t.strip())

        for row in rows[1:]:
            merged_content += "\n\n---\n[Merged from memory #{}]: {}".format(row["id"], row["content"])
            for t in (row["tags"] or "").split(","):
                if t.strip():
                    merged_tags.add(t.strip())
            # Mark source as superseded
            self.conn.execute(
                "UPDATE memories SET superseded_by = ?, is_archived = 1, updated_at = ? WHERE id = ?",
                (target["id"], now, row["id"]),
            )
            # Create link
            self.conn.execute(
                """INSERT OR IGNORE INTO memory_links (source_id, target_id, relation, created_at)
                   VALUES (?, ?, 'supersedes', ?)""",
                (target["id"], row["id"], now),
            )

        # Update target with merged content
        self.conn.execute(
            "UPDATE memories SET content = ?, tags = ?, updated_at = ? WHERE id = ?",
            (merged_content, ",".join(sorted(merged_tags)), now, target["id"]),
        )
        self.conn.commit()

        return {
            "status": "merged",
            "target_id": target["id"],
            "merged_ids": [r["id"] for r in rows[1:]],
            "title": target["title"],
        }

    def delete(self, memory_id: int, hard: bool = False) -> dict:
        """Soft-delete (archive) or hard-delete a memory."""
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            return {"error": "Memory #{} not found".format(memory_id)}

        now = datetime.now().isoformat()
        if hard:
            self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self.conn.execute("DELETE FROM memory_links WHERE source_id = ? OR target_id = ?", (memory_id, memory_id))
            self.conn.execute("DELETE FROM memory_versions WHERE memory_id = ?", (memory_id,))
            self.conn.execute("DELETE FROM retrieval_log WHERE memory_id = ?", (memory_id,))
        else:
            self.conn.execute(
                "UPDATE memories SET is_archived = 1, updated_at = ? WHERE id = ?",
                (now, memory_id),
            )

        self.conn.commit()
        return {
            "status": "hard_deleted" if hard else "archived",
            "id": memory_id,
            "title": row["title"],
        }

    def link(self, source_id: int, target_id: int, relation: str) -> dict:
        """Create a link between two memories."""
        valid_relations = {"supersedes", "related_to", "contradicts", "supports", "caused_by"}
        if relation not in valid_relations:
            return {"error": "Invalid relation. Valid: {}".format(", ".join(sorted(valid_relations)))}

        now = datetime.now().isoformat()
        try:
            self.conn.execute(
                """INSERT INTO memory_links (source_id, target_id, relation, created_at)
                   VALUES (?, ?, ?, ?)""",
                (source_id, target_id, relation, now),
            )
            self.conn.commit()
            return {"status": "linked", "source": source_id, "target": target_id, "relation": relation}
        except sqlite3.IntegrityError:
            return {"status": "already_linked"}

    # ── Search ────────────────────────────────────────────────────────────────

    def _fts_search(self, query: str, limit: int = 10, type_filter: str = None,
                    category_filter: str = None, include_archived: bool = False) -> list:
        """BM25-ranked full-text search. Returns list of dicts."""
        # Escape FTS5 special characters and build query
        safe_query = self._sanitize_fts_query(query)
        if not safe_query:
            return []

        sql = """
            SELECT m.*, bm25(memories_fts, 3.0, 1.0, 1.5) as bm25_score
            FROM memories_fts
            JOIN memories m ON memories_fts.rowid = m.id
            WHERE memories_fts MATCH ?
        """
        params = [safe_query]

        if not include_archived:
            sql += " AND m.is_archived = 0"
        if type_filter:
            types = [t.strip() for t in type_filter.split(",")]
            sql += " AND m.type IN ({})".format(",".join("?" * len(types)))
            params.extend(types)
        if category_filter:
            cats = [c.strip() for c in category_filter.split(",")]
            sql += " AND m.category IN ({})".format(",".join("?" * len(cats)))
            params.extend(cats)

        sql += " ORDER BY bm25_score LIMIT ?"
        params.append(limit)

        try:
            rows = self.conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            # FTS5 query syntax error — fall back to LIKE search
            return self._like_search(query, limit, type_filter, category_filter, include_archived)

    def _like_search(self, query: str, limit: int = 10, type_filter: str = None,
                     category_filter: str = None, include_archived: bool = False) -> list:
        """Fallback LIKE search when FTS5 query fails."""
        sql = "SELECT *, 0.0 as bm25_score FROM memories WHERE (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
        pattern = "%{}%".format(query)
        params = [pattern, pattern, pattern]

        if not include_archived:
            sql += " AND is_archived = 0"
        if type_filter:
            types = [t.strip() for t in type_filter.split(",")]
            sql += " AND type IN ({})".format(",".join("?" * len(types)))
            params.extend(types)
        if category_filter:
            cats = [c.strip() for c in category_filter.split(",")]
            sql += " AND category IN ({})".format(",".join("?" * len(cats)))
            params.extend(cats)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def _sanitize_fts_query(self, query: str) -> str:
        """Make a raw query safe for FTS5 MATCH."""
        # Remove FTS5 operators that could cause syntax errors
        for char in ['"', "'", "(", ")", "{", "}", "[", "]", "^", "~", ":"]:
            query = query.replace(char, " ")
        # Split into words, filter empty, rejoin with implicit AND
        words = [w.strip() for w in query.split() if w.strip()]
        if not words:
            return ""
        # Quote each word to avoid issues with reserved words
        return " ".join('"{}"'.format(w) for w in words)

    def _check_dedup(self, title: str, content: str) -> dict:
        """Check if a similar memory already exists. Returns match or None."""
        # 1. Exact title match (strongest signal)
        exact = self.conn.execute(
            "SELECT id, title FROM memories WHERE title = ? AND is_archived = 0",
            (title,),
        ).fetchone()
        if exact:
            return {"id": exact[0], "title": exact[1], "score": -999.0}

        # 2. Normalized title match (case-insensitive, stripped)
        normalized = self.conn.execute(
            "SELECT id, title FROM memories WHERE LOWER(TRIM(title)) = ? AND is_archived = 0",
            (title.lower().strip(),),
        ).fetchone()
        if normalized:
            return {"id": normalized[0], "title": normalized[1], "score": -998.0}

        # 3. FTS5 BM25 search — catches semantic near-dupes
        matches = self._fts_search(title, limit=3)
        for m in matches:
            # With small corpora BM25 scores cluster near 0, so also check
            # word overlap as a percentage
            title_words = set(title.lower().split())
            match_words = set(m["title"].lower().split())
            if title_words and match_words:
                overlap = len(title_words & match_words) / max(len(title_words), len(match_words))
                if overlap >= 0.7:
                    return {"id": m["id"], "title": m["title"], "score": m["bm25_score"]}
        return None

    def search(self, query: str, limit: int = 10, type_filter: str = None,
               category_filter: str = None) -> list:
        """Public search method with access tracking."""
        results = self._fts_search(query, limit, type_filter, category_filter)
        now = datetime.now().isoformat()

        for i, r in enumerate(results):
            # Update access stats
            self.conn.execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (now, r["id"]),
            )
            # Log retrieval
            self.conn.execute(
                """INSERT INTO retrieval_log (memory_id, query, rank_position, bm25_score, retrieved_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (r["id"], query, i + 1, r.get("bm25_score", 0), now),
            )

        if results:
            self.conn.commit()

        return results

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Get memory system statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM memories WHERE is_archived = 0").fetchone()[0]
        archived = self.conn.execute("SELECT COUNT(*) FROM memories WHERE is_archived = 1").fetchone()[0]

        by_type = {}
        for row in self.conn.execute(
            "SELECT type, COUNT(*) FROM memories WHERE is_archived = 0 GROUP BY type ORDER BY COUNT(*) DESC"
        ).fetchall():
            by_type[row[0]] = row[1]

        by_category = {}
        for row in self.conn.execute(
            "SELECT category, COUNT(*) FROM memories WHERE is_archived = 0 GROUP BY category ORDER BY COUNT(*) DESC"
        ).fetchall():
            by_category[row[0]] = row[1]

        links = self.conn.execute("SELECT COUNT(*) FROM memory_links").fetchone()[0]
        versions = self.conn.execute("SELECT COUNT(*) FROM memory_versions").fetchone()[0]
        sessions = self.conn.execute("SELECT COUNT(*) FROM session_context").fetchone()[0]

        # Most accessed
        top_accessed = []
        for row in self.conn.execute(
            "SELECT id, title, access_count FROM memories WHERE access_count > 0 ORDER BY access_count DESC LIMIT 5"
        ).fetchall():
            top_accessed.append({"id": row[0], "title": row[1], "access_count": row[2]})

        # DB file size
        db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "total_active": total,
            "total_archived": archived,
            "by_type": by_type,
            "by_category": by_category,
            "total_links": links,
            "total_versions": versions,
            "total_sessions": sessions,
            "top_accessed": top_accessed,
            "db_size_kb": round(db_size_bytes / 1024, 1),
        }

    # ── Session Context ───────────────────────────────────────────────────────

    def create_session(self, session_id: str, topics: str = "", summary: str = "",
                       files_modified: list = None, open_threads: list = None) -> int:
        """Create a session context record."""
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            """INSERT INTO session_context
               (session_id, started_at, topics, summary, files_modified, open_threads)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, now, topics, summary,
             json.dumps(files_modified or []),
             json.dumps(open_threads or [])),
        )
        self.conn.commit()
        return cursor.lastrowid

    def close_session(self, session_id: str, summary: str = "",
                      decisions_made: list = None, open_threads: list = None):
        """Close a session context record."""
        now = datetime.now().isoformat()
        self.conn.execute(
            """UPDATE session_context SET
               ended_at = ?, summary = ?, decisions_made = ?, open_threads = ?
               WHERE session_id = ? AND ended_at IS NULL""",
            (now, summary, json.dumps(decisions_made or []),
             json.dumps(open_threads or []), session_id),
        )
        self.conn.commit()

    def get_last_session(self) -> dict:
        """Get the most recent session context."""
        row = self.conn.execute(
            "SELECT * FROM session_context ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row:
            result = dict(row)
            for key in ("files_modified", "decisions_made", "open_threads"):
                if result.get(key):
                    try:
                        result[key] = json.loads(result[key])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return result
        return None

    def get_recent(self, days: int = 7, type_filter: str = None, limit: int = 20,
                   track_access: bool = True) -> list:
        """Get recent memories (no search query needed). Tracks access by default."""
        from datetime import timedelta
        since = (datetime.now() - timedelta(days=days)).isoformat()

        sql = "SELECT *, 0.0 as bm25_score FROM memories WHERE created_at >= ? AND is_archived = 0"
        params = [since]

        if type_filter:
            types = [t.strip() for t in type_filter.split(",")]
            sql += " AND type IN ({})".format(",".join("?" * len(types)))
            params.extend(types)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        results = [dict(row) for row in rows]

        # Track access — these memories were retrieved and shown to the user
        if track_access and results:
            now = datetime.now().isoformat()
            for r in results:
                self.conn.execute(
                    "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (now, r["id"]),
                )
            self.conn.commit()

        return results

    def get_by_id(self, memory_id: int) -> dict:
        """Get a single memory by ID."""
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return dict(row) if row else None


# ── CLI ───────────────────────────────────────────────────────────────────────

def format_memory(m: dict, verbose: bool = False) -> str:
    """Format a memory for display."""
    line = "[#{id}] ({type}/{category}) {title}".format(**m)
    if m.get("bm25_score") and m["bm25_score"] != 0:
        line += "  [score: {:.2f}]".format(m["bm25_score"])
    if verbose:
        line += "\n    Content: {}".format(m["content"][:200])
        if m.get("tags"):
            line += "\n    Tags: {}".format(m["tags"])
        line += "\n    Created: {}  Updated: {}".format(m["created_at"][:10], m["updated_at"][:10])
        if m.get("access_count", 0) > 0:
            line += "  Accessed: {} times".format(m["access_count"])
    return line


def main():
    parser = argparse.ArgumentParser(description="Memory system — store, search, manage")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add
    add_p = subparsers.add_parser("add", help="Add a memory")
    add_p.add_argument("--type", required=True, choices=sorted(VALID_TYPES))
    add_p.add_argument("--category", required=True, choices=sorted(VALID_CATEGORIES))
    add_p.add_argument("--title", required=True)
    add_p.add_argument("--content", required=True)
    add_p.add_argument("--tags", default="")
    add_p.add_argument("--source", default="session")
    add_p.add_argument("--ttl-days", type=int, default=None)
    add_p.add_argument("--skip-dedup", action="store_true")

    # Update
    upd_p = subparsers.add_parser("update", help="Update a memory by search")
    upd_p.add_argument("--search", required=True)
    upd_p.add_argument("--content", required=True)
    upd_p.add_argument("--reason", default="")

    # Merge
    merge_p = subparsers.add_parser("merge", help="Merge memories")
    merge_p.add_argument("--ids", required=True, help="Comma-separated IDs")

    # Delete
    del_p = subparsers.add_parser("delete", help="Delete a memory")
    del_p.add_argument("--id", type=int, required=True)
    del_p.add_argument("--hard", action="store_true")

    # Search
    search_p = subparsers.add_parser("search", help="Search memories")
    search_p.add_argument("--query", required=True)
    search_p.add_argument("--type", default=None)
    search_p.add_argument("--category", default=None)
    search_p.add_argument("--limit", type=int, default=10)
    search_p.add_argument("--verbose", "-v", action="store_true")

    # Stats
    subparsers.add_parser("stats", help="Memory system statistics")

    # Link
    link_p = subparsers.add_parser("link", help="Link two memories")
    link_p.add_argument("--source", type=int, required=True)
    link_p.add_argument("--target", type=int, required=True)
    link_p.add_argument("--relation", required=True)

    args = parser.parse_args()
    store = MemoryStore()

    if args.command == "add":
        result = store.add(
            type=args.type, category=args.category,
            title=args.title, content=args.content,
            tags=args.tags, source=args.source,
            ttl_days=args.ttl_days, skip_dedup=args.skip_dedup,
        )
        if result.get("status") == "created":
            print("+ Memory #{} created: {}".format(result["id"], result["title"]))
        elif result.get("status") == "duplicate":
            print("= Duplicate detected (#{existing_id}): {existing_title}".format(**result))
        else:
            print("! Error: {}".format(result.get("error", "unknown")))
            sys.exit(1)

    elif args.command == "update":
        result = store.update(args.search, args.content, args.reason)
        if result.get("status") == "updated":
            print("~ Memory #{} updated (v{}): {}".format(result["id"], result["version"], result["title"]))
        elif result.get("status") == "unchanged":
            print("= Memory #{} unchanged: {}".format(result["id"], result["title"]))
        else:
            print("! Error: {}".format(result.get("error", "unknown")))
            sys.exit(1)

    elif args.command == "merge":
        ids = [int(x.strip()) for x in args.ids.split(",")]
        result = store.merge(ids)
        if result.get("status") == "merged":
            print("* Merged {} memories into #{}".format(len(result["merged_ids"]), result["target_id"]))
        else:
            print("! Error: {}".format(result.get("error", "unknown")))
            sys.exit(1)

    elif args.command == "delete":
        result = store.delete(args.id, hard=args.hard)
        print("{} Memory #{}: {}".format(
            "x" if args.hard else "-",
            result["id"], result.get("title", "deleted"),
        ))

    elif args.command == "search":
        results = store.search(args.query, limit=args.limit,
                               type_filter=args.type, category_filter=args.category)
        if results:
            print("Found {} memories:".format(len(results)))
            for m in results:
                print("  " + format_memory(m, verbose=args.verbose))
        else:
            print("No memories found for '{}'".format(args.query))

    elif args.command == "stats":
        s = store.stats()
        print("Memory System Stats")
        print("  Active: {}  Archived: {}  DB: {} KB".format(s["total_active"], s["total_archived"], s["db_size_kb"]))
        print("  Links: {}  Versions: {}  Sessions: {}".format(s["total_links"], s["total_versions"], s["total_sessions"]))
        if s["by_type"]:
            print("  By type: {}".format(", ".join("{}: {}".format(k, v) for k, v in s["by_type"].items())))
        if s["by_category"]:
            print("  By category: {}".format(", ".join("{}: {}".format(k, v) for k, v in s["by_category"].items())))
        if s["top_accessed"]:
            print("  Most accessed:")
            for t in s["top_accessed"]:
                print("    #{} ({} hits): {}".format(t["id"], t["access_count"], t["title"]))

    elif args.command == "link":
        result = store.link(args.source, args.target, args.relation)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
