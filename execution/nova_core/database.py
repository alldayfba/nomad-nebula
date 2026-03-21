"""Shared Nova database — feedback, cross-platform question tracking, abuse log.

Stored at .tmp/nova/nova.db (SQLite, WAL mode).
Discord's chat_history/tickets stay in discord_bot.db — this DB is for shared state only.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / ".tmp" / "nova" / "nova.db"

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local connection with WAL mode and row factory."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
        # Restrict file permissions (owner read/write only)
        import os, stat
        try:
            os.chmod(str(DB_PATH), stat.S_IRUSR | stat.S_IWUSR)
            os.chmod(str(DB_PATH.parent), stat.S_IRWXU)
        except OSError:
            pass
    return _local.conn


def init_db():
    """Create all tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS question_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id INTEGER,
            user_id TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'discord',
            raw_question TEXT NOT NULL,
            keywords TEXT,
            asked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS question_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            representative_question TEXT NOT NULL,
            keywords TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            frequency INTEGER DEFAULT 1,
            first_asked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_asked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id INTEGER,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            source TEXT DEFAULT 'admin',
            approved INTEGER DEFAULT 0,
            approved_by TEXT,
            upvotes INTEGER DEFAULT 0,
            downvotes INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            user_id TEXT NOT NULL,
            conversation_id TEXT,
            message_id TEXT,
            rating INTEGER NOT NULL,
            comment TEXT,
            question_text TEXT,
            answer_text TEXT,
            cluster_id INTEGER,
            reviewed_by TEXT,
            review_action TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS abuse_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            severity TEXT DEFAULT 'low',
            pattern_matched TEXT,
            input_snippet TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_qt_cluster ON question_tracker(cluster_id);
        CREATE INDEX IF NOT EXISTS idx_qt_platform ON question_tracker(platform, asked_at);
        CREATE INDEX IF NOT EXISTS idx_kb_approved ON knowledge_base(approved);
        CREATE INDEX IF NOT EXISTS idx_feedback_platform ON feedback(platform, created_at);
        CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);
        CREATE INDEX IF NOT EXISTS idx_feedback_unreviewed ON feedback(reviewed_by)
            WHERE reviewed_by IS NULL;
        CREATE INDEX IF NOT EXISTS idx_abuse_user ON abuse_log(user_id, created_at);

        CREATE TABLE IF NOT EXISTS chat_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            channel_id TEXT DEFAULT '',
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_chatlog_user ON chat_log(user_id, platform, created_at);
        CREATE INDEX IF NOT EXISTS idx_chatlog_platform ON chat_log(platform, created_at);
    """)
    conn.commit()


def get_conn() -> sqlite3.Connection:
    """Public accessor for the shared connection."""
    return _get_conn()


# Auto-init on import
init_db()
