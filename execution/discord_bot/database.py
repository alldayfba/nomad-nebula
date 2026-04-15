"""SQLite database for Discord bot — tickets, chat history, knowledge base, audit log."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / ".tmp" / "discord" / "discord_bot.db"

SCHEMA = """
-- Chat history for conversation memory
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    model_used TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_user_channel ON chat_history(user_id, channel_id, created_at);

-- Support tickets
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_number INTEGER NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    subject TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    channel_id TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    closed_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id);

-- Ticket message transcript
CREATE TABLE IF NOT EXISTS ticket_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);
CREATE INDEX IF NOT EXISTS idx_ticket_msgs ON ticket_messages(ticket_id);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_date ON audit_log(created_at);

-- Rate limit tracking (persistence across restarts)
CREATE TABLE IF NOT EXISTS rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rate_user ON rate_limits(user_id, action_type, created_at);

-- Blacklisted users
CREATE TABLE IF NOT EXISTS blacklist (
    user_id TEXT PRIMARY KEY,
    reason TEXT,
    blacklisted_by TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Question tracking (adaptive knowledge)
CREATE TABLE IF NOT EXISTS question_tracker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER,
    user_id TEXT NOT NULL,
    raw_question TEXT NOT NULL,
    keywords TEXT NOT NULL,
    asked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cluster_id) REFERENCES question_clusters(id)
);
CREATE INDEX IF NOT EXISTS idx_qt_cluster ON question_tracker(cluster_id);

-- Question clusters (aggregated frequent questions)
CREATE TABLE IF NOT EXISTS question_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    representative_question TEXT NOT NULL,
    keywords TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    frequency INTEGER DEFAULT 1,
    first_asked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_asked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Curated knowledge base (FAQ)
CREATE TABLE IF NOT EXISTS knowledge_base (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'auto',
    approved INTEGER NOT NULL DEFAULT 0,
    approved_by TEXT,
    upvotes INTEGER DEFAULT 0,
    downvotes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cluster_id) REFERENCES question_clusters(id)
);
CREATE INDEX IF NOT EXISTS idx_kb_approved ON knowledge_base(approved);
"""


class BotDatabase:
    """Central database for all Discord bot data."""

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        # Restrict file permissions (owner read/write only)
        import os, stat
        try:
            os.chmod(str(self.db_path), stat.S_IRUSR | stat.S_IWUSR)
            os.chmod(str(self.db_path.parent), stat.S_IRWXU)
        except OSError:
            pass

    def _get_conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # ── Chat History ──────────────────────────────────────────────────────────

    def add_chat_message(self, user_id, channel_id, role, content,
                         model_used=None, tokens_in=0, tokens_out=0):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO chat_history (user_id, channel_id, role, content, model_used, tokens_in, tokens_out) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(user_id), str(channel_id), role, content, model_used, tokens_in, tokens_out)
            )
            conn.commit()
        finally:
            conn.close()

    def get_chat_history(self, user_id, channel_id, limit=10):
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT role, content FROM chat_history "
                "WHERE user_id = ? AND channel_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (str(user_id), str(channel_id), limit)
            ).fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
        finally:
            conn.close()

    # ── Tickets ───────────────────────────────────────────────────────────────

    def create_ticket(self, user_id, username, subject, category, channel_id):
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT COALESCE(MAX(ticket_number), 0) + 1 AS next_num FROM tickets").fetchone()
            ticket_num = row["next_num"]
            conn.execute(
                "INSERT INTO tickets (ticket_number, user_id, username, subject, category, channel_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ticket_num, str(user_id), username, subject, category, str(channel_id))
            )
            conn.commit()
            return ticket_num
        finally:
            conn.close()

    def close_ticket(self, ticket_id, closed_by):
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE tickets SET status = 'closed', closed_at = ?, closed_by = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), str(closed_by), ticket_id)
            )
            conn.commit()
        finally:
            conn.close()

    def get_ticket_by_channel(self, channel_id):
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM tickets WHERE channel_id = ? AND status = 'open'",
                (str(channel_id),)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_open_tickets(self):
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE status = 'open' ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def add_ticket_message(self, ticket_id, user_id, username, content):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO ticket_messages (ticket_id, user_id, username, content) VALUES (?, ?, ?, ?)",
                (ticket_id, str(user_id), username, content)
            )
            conn.commit()
        finally:
            conn.close()

    def get_ticket_transcript(self, ticket_id):
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT username, content, created_at FROM ticket_messages "
                "WHERE ticket_id = ? ORDER BY created_at ASC",
                (ticket_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Audit Log ─────────────────────────────────────────────────────────────

    def log_audit(self, user_id, action, details=None):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO audit_log (user_id, action, details) VALUES (?, ?, ?)",
                (str(user_id), action, details)
            )
            conn.commit()
        finally:
            conn.close()

    # ── Blacklist ─────────────────────────────────────────────────────────────

    def is_blacklisted(self, user_id):
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT 1 FROM blacklist WHERE user_id = ?", (str(user_id),)).fetchone()
            return row is not None
        finally:
            conn.close()

    def add_blacklist(self, user_id, reason, blacklisted_by):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO blacklist (user_id, reason, blacklisted_by) VALUES (?, ?, ?)",
                (str(user_id), reason, str(blacklisted_by))
            )
            conn.commit()
        finally:
            conn.close()

    def remove_blacklist(self, user_id):
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM blacklist WHERE user_id = ?", (str(user_id),))
            conn.commit()
        finally:
            conn.close()

    # ── Rate Limits ───────────────────────────────────────────────────────────

    def record_rate_limit(self, user_id, action_type):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO rate_limits (user_id, action_type) VALUES (?, ?)",
                (str(user_id), action_type)
            )
            conn.commit()
        finally:
            conn.close()

    def count_recent_actions(self, user_id, action_type, window_seconds):
        conn = self._get_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(seconds=window_seconds)).isoformat()
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM rate_limits "
                "WHERE user_id = ? AND action_type = ? AND created_at >= ?",
                (str(user_id), action_type, cutoff)
            ).fetchone()
            return row["cnt"]
        finally:
            conn.close()

    def count_recent_audit(self, user_id, action, window_seconds):
        conn = self._get_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(seconds=window_seconds)).isoformat()
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM audit_log "
                "WHERE user_id = ? AND action = ? AND created_at >= ?",
                (str(user_id), action, cutoff)
            ).fetchone()
            return row["cnt"]
        finally:
            conn.close()

    # ── Knowledge Base ────────────────────────────────────────────────────────

    def add_question(self, user_id, raw_question, keywords, cluster_id=None):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO question_tracker (cluster_id, user_id, raw_question, keywords) "
                "VALUES (?, ?, ?, ?)",
                (cluster_id, str(user_id), raw_question, keywords)
            )
            conn.commit()
        finally:
            conn.close()

    def find_or_create_cluster(self, keywords, raw_question, category="general"):
        conn = self._get_conn()
        try:
            kw_set = set(keywords.lower().split(","))
            rows = conn.execute("SELECT * FROM question_clusters").fetchall()
            best_match = None
            best_overlap = 0.0

            for row in rows:
                existing_kw = set(row["keywords"].lower().split(","))
                if not kw_set or not existing_kw:
                    continue
                overlap = len(kw_set & existing_kw) / max(len(kw_set), len(existing_kw))
                if overlap >= 0.6 and overlap > best_overlap:
                    best_overlap = overlap
                    best_match = row

            if best_match:
                conn.execute(
                    "UPDATE question_clusters SET frequency = frequency + 1, last_asked = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), best_match["id"])
                )
                conn.commit()
                return best_match["id"], best_match["frequency"] + 1
            else:
                cursor = conn.execute(
                    "INSERT INTO question_clusters (representative_question, keywords, category) "
                    "VALUES (?, ?, ?)",
                    (raw_question, keywords, category)
                )
                conn.commit()
                return cursor.lastrowid, 1
        finally:
            conn.close()

    def get_approved_knowledge(self, keywords, limit=3):
        conn = self._get_conn()
        try:
            kw_set = set(keywords.lower().split(","))
            rows = conn.execute(
                "SELECT * FROM knowledge_base WHERE approved = 1"
            ).fetchall()

            scored = []
            for row in rows:
                q_words = set(row["question"].lower().split())
                overlap = len(kw_set & q_words)
                if overlap > 0:
                    scored.append((overlap, dict(row)))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in scored[:limit]]
        finally:
            conn.close()

    def add_knowledge_entry(self, question, answer, source="admin", approved=True,
                            approved_by=None, cluster_id=None):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO knowledge_base (cluster_id, question, answer, source, approved, approved_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (cluster_id, question, answer, source, int(approved), approved_by)
            )
            conn.commit()
        finally:
            conn.close()

    def get_pending_knowledge(self):
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM knowledge_base WHERE approved = 0 ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_approved_knowledge_all(self):
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM knowledge_base WHERE approved = 1 ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def approve_knowledge(self, entry_id, approved_by):
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE knowledge_base SET approved = 1, approved_by = ?, updated_at = ? WHERE id = ?",
                (str(approved_by), datetime.utcnow().isoformat(), entry_id)
            )
            conn.commit()
        finally:
            conn.close()

    def delete_knowledge(self, entry_id):
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM knowledge_base WHERE id = ?", (entry_id,))
            conn.commit()
        finally:
            conn.close()

    def update_knowledge_votes(self, entry_id, upvote=True):
        conn = self._get_conn()
        try:
            if upvote:
                conn.execute("UPDATE knowledge_base SET upvotes = upvotes + 1 WHERE id = ?", (entry_id,))
            else:
                conn.execute("UPDATE knowledge_base SET downvotes = downvotes + 1 WHERE id = ?", (entry_id,))
            conn.commit()
        finally:
            conn.close()

    def get_top_clusters(self, days=30, limit=10):
        conn = self._get_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            rows = conn.execute(
                "SELECT * FROM question_clusters WHERE last_asked >= ? "
                "ORDER BY frequency DESC LIMIT ?",
                (cutoff, limit)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self):
        conn = self._get_conn()
        try:
            total_chats = conn.execute("SELECT COUNT(*) as c FROM chat_history WHERE role='user'").fetchone()["c"]
            total_tokens_in = conn.execute("SELECT COALESCE(SUM(tokens_in), 0) as s FROM chat_history").fetchone()["s"]
            total_tokens_out = conn.execute("SELECT COALESCE(SUM(tokens_out), 0) as s FROM chat_history").fetchone()["s"]
            open_tickets = conn.execute("SELECT COUNT(*) as c FROM tickets WHERE status='open'").fetchone()["c"]
            total_tickets = conn.execute("SELECT COUNT(*) as c FROM tickets").fetchone()["c"]
            blacklisted = conn.execute("SELECT COUNT(*) as c FROM blacklist").fetchone()["c"]
            faq_count = conn.execute("SELECT COUNT(*) as c FROM knowledge_base WHERE approved=1").fetchone()["c"]
            injection_attempts = conn.execute(
                "SELECT COUNT(*) as c FROM audit_log WHERE action='injection_attempt'"
            ).fetchone()["c"]

            return {
                "total_chats": total_chats,
                "total_tokens_in": total_tokens_in,
                "total_tokens_out": total_tokens_out,
                "open_tickets": open_tickets,
                "total_tickets": total_tickets,
                "blacklisted_users": blacklisted,
                "faq_entries": faq_count,
                "injection_attempts": injection_attempts,
            }
        finally:
            conn.close()
