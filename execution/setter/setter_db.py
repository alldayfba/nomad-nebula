"""
Setter database — SQLite schema, connection management, and CRUD helpers.

Single source of truth for all setter data: prospects, conversations, messages,
follow-ups, daily metrics, and winning patterns.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .setter_config import DB_PATH

# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ig_handle TEXT NOT NULL UNIQUE,
    ig_user_id TEXT,
    full_name TEXT,
    bio TEXT,
    follower_count INTEGER DEFAULT 0,
    following_count INTEGER DEFAULT 0,
    is_business INTEGER DEFAULT 0,
    is_private INTEGER DEFAULT 0,
    category TEXT,
    website TEXT,
    email_from_bio TEXT,
    profile_pic_url TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    source_detail TEXT,
    icp_score INTEGER DEFAULT 0,
    icp_reasoning TEXT,
    offer_match TEXT DEFAULT 'none',
    status TEXT DEFAULT 'new',
    outbound_batch TEXT,
    last_scanned_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL,
    ig_thread_id TEXT,
    offer TEXT NOT NULL DEFAULT 'amazon_os',
    conversation_type TEXT DEFAULT 'cold_outbound',
    stage TEXT DEFAULT 'new',
    qual_commitment INTEGER DEFAULT 0,
    qual_urgency INTEGER DEFAULT 0,
    qual_resources INTEGER DEFAULT 0,
    messages_sent INTEGER DEFAULT 0,
    messages_received INTEGER DEFAULT 0,
    last_message_at TEXT,
    last_message_direction TEXT,
    next_action TEXT,
    next_action_at TEXT,
    requires_human INTEGER DEFAULT 0,
    human_reason TEXT,
    ghl_contact_id TEXT,
    ghl_opportunity_id TEXT,
    booking_datetime TEXT,
    booking_confirmed INTEGER DEFAULT 0,
    opener_type TEXT,
    total_api_cost REAL DEFAULT 0.0,
    heat_score INTEGER DEFAULT 0,
    heat_score_updated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (prospect_id) REFERENCES prospects(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    content TEXT NOT NULL,
    message_type TEXT DEFAULT 'text',
    approval_status TEXT DEFAULT 'auto',
    approved_by TEXT,
    claude_model TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    ig_message_id TEXT,
    sent_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    follow_up_number INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    content TEXT,
    scheduled_at TEXT NOT NULL,
    sent_at TEXT,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    cold_dms_sent INTEGER DEFAULT 0,
    warm_dms_sent INTEGER DEFAULT 0,
    follow_ups_sent INTEGER DEFAULT 0,
    inbox_replies_sent INTEGER DEFAULT 0,
    total_dms_sent INTEGER DEFAULT 0,
    prospects_scanned INTEGER DEFAULT 0,
    prospects_qualified INTEGER DEFAULT 0,
    replies_received INTEGER DEFAULT 0,
    response_rate REAL DEFAULT 0.0,
    conversations_active INTEGER DEFAULT 0,
    qualified INTEGER DEFAULT 0,
    booked INTEGER DEFAULT 0,
    showed INTEGER DEFAULT 0,
    closed INTEGER DEFAULT 0,
    revenue_attributed REAL DEFAULT 0.0,
    api_cost REAL DEFAULT 0.0,
    escalations INTEGER DEFAULT 0,
    action_blocks INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS winning_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,
    content TEXT NOT NULL,
    offer TEXT,
    context TEXT,
    times_used INTEGER DEFAULT 1,
    times_succeeded INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_tracker (
    date TEXT NOT NULL,
    channel TEXT NOT NULL,
    send_count INTEGER DEFAULT 0,
    last_send_at TEXT,
    PRIMARY KEY (date, channel)
);

CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status);
CREATE INDEX IF NOT EXISTS idx_prospects_ig_handle ON prospects(ig_handle);
CREATE INDEX IF NOT EXISTS idx_prospects_offer ON prospects(offer_match);
CREATE INDEX IF NOT EXISTS idx_conversations_stage ON conversations(stage);
CREATE INDEX IF NOT EXISTS idx_conversations_prospect ON conversations(prospect_id);
CREATE INDEX IF NOT EXISTS idx_conversations_next_action ON conversations(next_action_at);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_scheduled ON follow_ups(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_follow_ups_status ON follow_ups(status);

-- Lead grading: every prospect gets a live grade that evolves with the convo
CREATE TABLE IF NOT EXISTS lead_grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL UNIQUE,
    grade TEXT NOT NULL DEFAULT 'D',          -- A/B/C/D/F
    temperature TEXT NOT NULL DEFAULT 'cold',  -- hot/warm/cold/dead
    engagement_score INTEGER DEFAULT 0,        -- 0-100: replies, speed, emoji, questions
    buying_signals INTEGER DEFAULT 0,          -- count of positive buying signals detected
    objection_count INTEGER DEFAULT 0,         -- count of objections raised
    response_time_avg INTEGER DEFAULT 0,       -- avg seconds to reply
    messages_exchanged INTEGER DEFAULT 0,
    last_graded_at TEXT NOT NULL,
    grade_history TEXT DEFAULT '[]',            -- JSON array of {grade, reason, timestamp}
    notes TEXT DEFAULT '',                      -- Sales Manager audit notes
    FOREIGN KEY (prospect_id) REFERENCES prospects(id)
);

-- Story viewers: track who views stories for re-engagement
CREATE TABLE IF NOT EXISTS story_viewers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ig_handle TEXT NOT NULL,
    prospect_id INTEGER,
    view_count INTEGER DEFAULT 1,              -- how many stories they've viewed
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    dm_sent INTEGER DEFAULT 0,                 -- have we DM'd them about stories?
    is_customer INTEGER DEFAULT 0,             -- skip if already paid
    FOREIGN KEY (prospect_id) REFERENCES prospects(id)
);

-- Conversation audits: Sales Manager reviews every convo
CREATE TABLE IF NOT EXISTS conversation_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    audit_type TEXT NOT NULL DEFAULT 'auto',    -- auto/manual
    grade TEXT NOT NULL,                        -- A/B/C/D/F
    opener_quality INTEGER DEFAULT 0,          -- 1-10
    qualification_quality INTEGER DEFAULT 0,   -- 1-10
    objection_handling INTEGER DEFAULT 0,      -- 1-10
    close_attempt_quality INTEGER DEFAULT 0,   -- 1-10
    what_worked TEXT,
    what_failed TEXT,
    improvement_suggestions TEXT,
    outcome TEXT,                               -- booked/no_show/closed/lost/ongoing
    revenue REAL DEFAULT 0.0,
    audited_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE INDEX IF NOT EXISTS idx_lead_grades_grade ON lead_grades(grade);
CREATE INDEX IF NOT EXISTS idx_lead_grades_temp ON lead_grades(temperature);
CREATE INDEX IF NOT EXISTS idx_story_viewers_handle ON story_viewers(ig_handle);
CREATE INDEX IF NOT EXISTS idx_story_viewers_last ON story_viewers(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_conv_audits_conv ON conversation_audits(conversation_id);

-- Follower watermark: track where we left off scanning
CREATE TABLE IF NOT EXISTS follower_watermark (
    id INTEGER PRIMARY KEY,
    ig_handle TEXT NOT NULL,
    last_position INTEGER DEFAULT 0,
    last_scanned_at TEXT,
    last_follower_handle TEXT
);

-- System state: track ramp-up start, action block history, etc.
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Blocklist: handles that should never receive DMs
CREATE TABLE IF NOT EXISTS blocklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ig_handle TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    source TEXT NOT NULL,
    added_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blocklist_handle ON blocklist(ig_handle);
"""


# ── Connection ───────────────────────────────────────────────────────────────

_conn: Optional[sqlite3.Connection] = None
_schema_initialized = False


def get_db() -> sqlite3.Connection:
    """Get a reusable database connection with WAL mode and row factory.

    Uses a module-level singleton — created once and reused.
    SQLite WAL mode handles concurrent reads with a single writer.
    """
    global _conn, _schema_initialized
    if _conn is not None:
        try:
            _conn.execute("SELECT 1")  # Quick liveness check
            return _conn
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            _conn = None  # Connection dead, recreate

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(DB_PATH), timeout=10)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA foreign_keys=ON")
    if not _schema_initialized:
        _conn.executescript(SCHEMA_SQL)
        # Migration: add heat_score columns if not present (existing DBs)
        try:
            _conn.execute("ALTER TABLE conversations ADD COLUMN heat_score INTEGER DEFAULT 0")
            _conn.execute("ALTER TABLE conversations ADD COLUMN heat_score_updated_at TEXT")
            _conn.commit()
        except Exception:
            pass  # Columns already exist
        # Migration: create blocklist table (existing DBs)
        try:
            _conn.execute("""CREATE TABLE IF NOT EXISTS blocklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ig_handle TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL,
                source TEXT NOT NULL,
                added_at TEXT NOT NULL
            )""")
            _conn.execute("CREATE INDEX IF NOT EXISTS idx_blocklist_handle ON blocklist(ig_handle)")
            _conn.commit()
        except Exception:
            pass
        _schema_initialized = True
    return _conn


def close_db():
    """Close the singleton connection (call on shutdown)."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None


def _now() -> str:
    """Current time in EST (Miami) — all DB timestamps are EST."""
    from datetime import timezone, timedelta as _td
    est = timezone(_td(hours=-5))
    return datetime.now(est).strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    """Current date in EST (Miami)."""
    from datetime import timezone, timedelta as _td
    est = timezone(_td(hours=-5))
    return datetime.now(est).strftime("%Y-%m-%d")


# ── Prospect CRUD ────────────────────────────────────────────────────────────

def upsert_prospect(
    ig_handle: str,
    source: str = "manual",
    source_detail: str = "",
    **kwargs,
) -> int:
    """Insert or update a prospect. Returns prospect ID."""
    db = get_db()
    now = _now()
    existing = db.execute(
        "SELECT id FROM prospects WHERE ig_handle = ?", (ig_handle,)
    ).fetchone()

    if existing:
        updates = {k: v for k, v in kwargs.items() if v is not None}
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [now, ig_handle]
            db.execute(
                f"UPDATE prospects SET {set_clause}, updated_at = ? WHERE ig_handle = ?",
                values,
            )
            db.commit()
        return existing["id"]

    cols = ["ig_handle", "source", "source_detail", "created_at", "updated_at"]
    vals = [ig_handle, source, source_detail, now, now]
    for k, v in kwargs.items():
        if v is not None:
            cols.append(k)
            vals.append(v)

    placeholders = ", ".join("?" for _ in vals)
    col_str = ", ".join(cols)
    cursor = db.execute(
        f"INSERT INTO prospects ({col_str}) VALUES ({placeholders})", vals
    )
    db.commit()
    return cursor.lastrowid


def get_prospect(prospect_id: int) -> Optional[Dict]:
    db = get_db()
    row = db.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
    return dict(row) if row else None


def get_prospect_by_handle(ig_handle: str) -> Optional[Dict]:
    db = get_db()
    row = db.execute("SELECT * FROM prospects WHERE ig_handle = ?", (ig_handle,)).fetchone()
    return dict(row) if row else None


def get_prospects_by_status(status: str, limit: int = 100) -> List[Dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM prospects WHERE status = ? ORDER BY icp_score DESC LIMIT ?",
        (status, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def update_prospect_status(prospect_id: int, status: str):
    db = get_db()
    db.execute(
        "UPDATE prospects SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now(), prospect_id),
    )
    db.commit()


def get_qualified_prospects_for_outbound(limit: int = 50) -> List[Dict]:
    """Get all new/qualified prospects not yet contacted.

    Every new follower gets a DM — qualification happens in the conversation.
    """
    db = get_db()
    rows = db.execute(
        """SELECT p.* FROM prospects p
           LEFT JOIN conversations c ON c.prospect_id = p.id
           WHERE p.status IN ('new', 'qualified')
             AND c.id IS NULL
           ORDER BY p.created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Conversation CRUD ────────────────────────────────────────────────────────

def create_conversation(
    prospect_id: int,
    offer: str = "amazon_os",
    conversation_type: str = "cold_outbound",
    **kwargs,
) -> int:
    db = get_db()
    now = _now()
    cols = ["prospect_id", "offer", "conversation_type", "created_at", "updated_at"]
    vals = [prospect_id, offer, conversation_type, now, now]
    for k, v in kwargs.items():
        if v is not None:
            cols.append(k)
            vals.append(v)
    placeholders = ", ".join("?" for _ in vals)
    col_str = ", ".join(cols)
    cursor = db.execute(
        f"INSERT INTO conversations ({col_str}) VALUES ({placeholders})", vals
    )
    db.commit()
    return cursor.lastrowid


def get_conversation(conversation_id: int) -> Optional[Dict]:
    db = get_db()
    row = db.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    return dict(row) if row else None


def get_conversation_by_prospect(prospect_id: int, include_closed: bool = False) -> Optional[Dict]:
    """Get the most recent conversation for a prospect.

    Args:
        prospect_id: The prospect's DB id.
        include_closed: If True, return ANY conversation (even dead/disqualified).
                        Use True for dedup checks (never re-DM someone we talked to).
                        Use False (default) for active convo management.
    """
    db = get_db()
    if include_closed:
        row = db.execute(
            """SELECT * FROM conversations WHERE prospect_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (prospect_id,),
        ).fetchone()
    else:
        row = db.execute(
            """SELECT * FROM conversations WHERE prospect_id = ?
               AND stage NOT IN ('dead', 'disqualified')
               ORDER BY created_at DESC LIMIT 1""",
            (prospect_id,),
        ).fetchone()
    return dict(row) if row else None


def get_conversation_by_thread(ig_thread_id: str) -> Optional[Dict]:
    db = get_db()
    row = db.execute(
        "SELECT * FROM conversations WHERE ig_thread_id = ?", (ig_thread_id,)
    ).fetchone()
    return dict(row) if row else None


def get_active_conversations(limit: int = 200) -> List[Dict]:
    db = get_db()
    rows = db.execute(
        """SELECT c.*, p.ig_handle, p.full_name, p.bio, p.icp_score
           FROM conversations c
           JOIN prospects p ON c.prospect_id = p.id
           WHERE c.stage NOT IN ('dead', 'disqualified', 'show')
           ORDER BY c.last_message_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_conversation(conversation_id: int, **kwargs):
    db = get_db()
    kwargs["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [conversation_id]
    db.execute(
        f"UPDATE conversations SET {set_clause} WHERE id = ?", values
    )
    db.commit()


def get_conversations_needing_action(before: Optional[str] = None) -> List[Dict]:
    """Get conversations with due next_action_at."""
    db = get_db()
    if before is None:
        before = _now()
    rows = db.execute(
        """SELECT c.*, p.ig_handle, p.full_name, p.bio
           FROM conversations c
           JOIN prospects p ON c.prospect_id = p.id
           WHERE c.next_action_at IS NOT NULL
             AND c.next_action_at <= ?
             AND c.requires_human = 0
             AND c.stage NOT IN ('dead', 'disqualified', 'booked', 'show', 'no_show', 'escalated')
           ORDER BY c.next_action_at ASC""",
        (before,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_booked_conversations() -> List[Dict]:
    """Get all booked conversations for show rate nurture."""
    db = get_db()
    rows = db.execute(
        """SELECT c.*, p.ig_handle, p.full_name
           FROM conversations c
           JOIN prospects p ON c.prospect_id = p.id
           WHERE c.stage IN ('booked', 'no_show')
           AND c.booking_datetime IS NOT NULL
           ORDER BY c.booking_datetime ASC"""
    ).fetchall()
    return [dict(r) for r in rows]


# ── Message CRUD ─────────────────────────────────────────────────────────────

def add_message(
    conversation_id: int,
    direction: str,
    content: str,
    message_type: str = "text",
    **kwargs,
) -> int:
    db = get_db()
    now = _now()
    cols = ["conversation_id", "direction", "content", "message_type", "sent_at"]
    vals = [conversation_id, direction, content, message_type, now]
    for k, v in kwargs.items():
        if v is not None:
            cols.append(k)
            vals.append(v)
    placeholders = ", ".join("?" for _ in vals)
    col_str = ", ".join(cols)
    cursor = db.execute(
        f"INSERT INTO messages ({col_str}) VALUES ({placeholders})", vals
    )

    # Update conversation counters
    if direction == "out":
        db.execute(
            """UPDATE conversations SET messages_sent = messages_sent + 1,
               last_message_at = ?, last_message_direction = 'out', updated_at = ?
               WHERE id = ?""",
            (now, now, conversation_id),
        )
    else:
        db.execute(
            """UPDATE conversations SET messages_received = messages_received + 1,
               last_message_at = ?, last_message_direction = 'in', updated_at = ?
               WHERE id = ?""",
            (now, now, conversation_id),
        )

    db.commit()
    return cursor.lastrowid


def get_messages(conversation_id: int, limit: int = 50) -> List[Dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY sent_at ASC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_pending_approval_messages() -> List[Dict]:
    """Get messages waiting for human approval, with prospect's last inbound message."""
    db = get_db()
    rows = db.execute(
        """SELECT m.*, c.stage, p.ig_handle, p.full_name,
           (SELECT m2.content FROM messages m2
            WHERE m2.conversation_id = m.conversation_id AND m2.direction = 'in'
            ORDER BY m2.sent_at DESC LIMIT 1) AS prospect_last_message
           FROM messages m
           JOIN conversations c ON m.conversation_id = c.id
           JOIN prospects p ON c.prospect_id = p.id
           WHERE m.approval_status = 'pending'
           ORDER BY m.sent_at ASC"""
    ).fetchall()
    return [dict(r) for r in rows]


def approve_message(message_id: int, approved_by: str = "sabbo"):
    db = get_db()
    db.execute(
        "UPDATE messages SET approval_status = 'approved', approved_by = ? WHERE id = ?",
        (approved_by, message_id),
    )
    db.commit()


def reject_message(message_id: int):
    db = get_db()
    db.execute(
        "UPDATE messages SET approval_status = 'rejected' WHERE id = ?",
        (message_id,),
    )
    # Flag the conversation for human follow-up so it doesn't sit in limbo
    row = db.execute(
        "SELECT conversation_id FROM messages WHERE id = ?", (message_id,)
    ).fetchone()
    if row:
        db.execute(
            """UPDATE conversations SET requires_human = 1,
               human_reason = 'AI response rejected — needs manual follow-up',
               updated_at = ? WHERE id = ?""",
            (_now(), row["conversation_id"]),
        )
    db.commit()


# ── Follow-Up CRUD ───────────────────────────────────────────────────────────

def schedule_follow_up(
    conversation_id: int,
    follow_up_number: int,
    content_type: str,
    scheduled_at: str,
    content: Optional[str] = None,
) -> int:
    db = get_db()
    cursor = db.execute(
        """INSERT INTO follow_ups (conversation_id, follow_up_number, content_type,
           scheduled_at, content) VALUES (?, ?, ?, ?, ?)""",
        (conversation_id, follow_up_number, content_type, scheduled_at, content),
    )
    db.commit()
    return cursor.lastrowid


def get_due_follow_ups(before: Optional[str] = None) -> List[Dict]:
    db = get_db()
    if before is None:
        before = _now()
    rows = db.execute(
        """SELECT f.*, c.prospect_id, c.offer, c.stage, p.ig_handle, p.full_name, p.bio
           FROM follow_ups f
           JOIN conversations c ON f.conversation_id = c.id
           JOIN prospects p ON c.prospect_id = p.id
           WHERE f.status = 'pending' AND f.scheduled_at <= ?
             AND c.stage IN ('opener_sent', 'replied', 'nurture')
             AND c.requires_human = 0
           ORDER BY f.scheduled_at ASC""",
        (before,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_follow_up_sent(follow_up_id: int):
    db = get_db()
    db.execute(
        "UPDATE follow_ups SET status = 'sent', sent_at = ? WHERE id = ?",
        (_now(), follow_up_id),
    )
    db.commit()


def cancel_follow_ups(conversation_id: int):
    """Cancel all pending follow-ups for a conversation (e.g. when they reply)."""
    db = get_db()
    db.execute(
        "UPDATE follow_ups SET status = 'cancelled' WHERE conversation_id = ? AND status = 'pending'",
        (conversation_id,),
    )
    db.commit()


# ── Rate Tracking ────────────────────────────────────────────────────────────

def get_send_count(channel: str, date: Optional[str] = None) -> int:
    db = get_db()
    if date is None:
        date = _today()
    row = db.execute(
        "SELECT send_count FROM rate_tracker WHERE date = ? AND channel = ?",
        (date, channel),
    ).fetchone()
    return row["send_count"] if row else 0


def increment_send_count(channel: str):
    db = get_db()
    date = _today()
    now = _now()
    db.execute(
        """INSERT INTO rate_tracker (date, channel, send_count, last_send_at)
           VALUES (?, ?, 1, ?)
           ON CONFLICT(date, channel) DO UPDATE SET
           send_count = send_count + 1, last_send_at = ?""",
        (date, channel, now, now),
    )
    db.commit()


def get_last_send_time(channel: str) -> Optional[str]:
    db = get_db()
    date = _today()
    row = db.execute(
        "SELECT last_send_at FROM rate_tracker WHERE date = ? AND channel = ?",
        (date, channel),
    ).fetchone()
    return row["last_send_at"] if row else None


# ── Daily Metrics ────────────────────────────────────────────────────────────

def update_daily_metrics(**kwargs):
    """Update today's metrics. Uses UPSERT."""
    db = get_db()
    date = _today()
    existing = db.execute(
        "SELECT * FROM daily_metrics WHERE date = ?", (date,)
    ).fetchone()

    if existing:
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [date]
        db.execute(f"UPDATE daily_metrics SET {set_clause} WHERE date = ?", values)
    else:
        cols = ["date"] + list(kwargs.keys())
        vals = [date] + list(kwargs.values())
        placeholders = ", ".join("?" for _ in vals)
        col_str = ", ".join(cols)
        db.execute(f"INSERT INTO daily_metrics ({col_str}) VALUES ({placeholders})", vals)
    db.commit()


def increment_metric(field: str, amount: int = 1):
    """Increment a single daily metric field."""
    db = get_db()
    date = _today()
    db.execute(
        f"""INSERT INTO daily_metrics (date, {field}) VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET {field} = {field} + ?""",
        (date, amount, amount),
    )
    db.commit()


def get_daily_metrics(date: Optional[str] = None) -> Optional[Dict]:
    db = get_db()
    if date is None:
        date = _today()
    row = db.execute("SELECT * FROM daily_metrics WHERE date = ?", (date,)).fetchone()
    return dict(row) if row else None


def get_metrics_range(start: str, end: str) -> List[Dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM daily_metrics WHERE date BETWEEN ? AND ? ORDER BY date ASC",
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Winning Patterns ─────────────────────────────────────────────────────────

def record_pattern(pattern_type: str, content: str, offer: str = "", context: str = ""):
    db = get_db()
    now = _now()
    existing = db.execute(
        "SELECT id, times_used FROM winning_patterns WHERE pattern_type = ? AND content = ?",
        (pattern_type, content),
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE winning_patterns SET times_used = times_used + 1, updated_at = ? WHERE id = ?",
            (now, existing["id"]),
        )
    else:
        db.execute(
            """INSERT INTO winning_patterns (pattern_type, content, offer, context, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pattern_type, content, offer, context, now, now),
        )
    db.commit()


def record_pattern_success(pattern_type: str, content: str):
    db = get_db()
    db.execute(
        """UPDATE winning_patterns SET times_succeeded = times_succeeded + 1,
           success_rate = CAST(times_succeeded + 1 AS REAL) / times_used,
           updated_at = ?
           WHERE pattern_type = ? AND content = ?""",
        (_now(), pattern_type, content),
    )
    db.commit()


def get_top_patterns(pattern_type: str, offer: str = "", limit: int = 5) -> List[Dict]:
    db = get_db()
    if offer:
        rows = db.execute(
            """SELECT * FROM winning_patterns
               WHERE pattern_type = ? AND (offer = ? OR offer = '')
                 AND times_used >= 5 AND success_rate > 0.2
               ORDER BY success_rate DESC LIMIT ?""",
            (pattern_type, offer, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT * FROM winning_patterns
               WHERE pattern_type = ? AND times_used >= 5 AND success_rate > 0.2
               ORDER BY success_rate DESC LIMIT ?""",
            (pattern_type, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Stats ────────────────────────────────────────────────────────────────────

def get_pipeline_stats() -> Dict:
    """Get current pipeline snapshot."""
    db = get_db()
    stats = {}
    for stage in ["new", "opener_sent", "replied", "qualifying", "qualified",
                   "booking", "booked", "show", "no_show", "nurture",
                   "disqualified", "dead", "escalated"]:
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE stage = ?", (stage,)
        ).fetchone()
        stats[stage] = row["cnt"]

    row = db.execute("SELECT COUNT(*) as cnt FROM prospects").fetchone()
    stats["total_prospects"] = row["cnt"]

    row = db.execute(
        "SELECT COUNT(*) as cnt FROM prospects WHERE status = 'qualified'"
    ).fetchone()
    stats["prospects_qualified"] = row["cnt"]

    row = db.execute(
        "SELECT SUM(total_api_cost) as total FROM conversations"
    ).fetchone()
    stats["total_api_cost"] = round(row["total"] or 0, 2)

    return stats


def get_today_send_counts() -> Dict:
    """Get all send counts for today."""
    db = get_db()
    rows = db.execute(
        "SELECT channel, send_count FROM rate_tracker WHERE date = ?", (_today(),)
    ).fetchall()
    return {r["channel"]: r["send_count"] for r in rows}


# ── Lead Grading ────────────────────────────────────────────────────────────

def upsert_lead_grade(
    prospect_id: int,
    grade: str = "D",
    temperature: str = "cold",
    engagement_score: int = 0,
    buying_signals: int = 0,
    objection_count: int = 0,
    response_time_avg: int = 0,
    messages_exchanged: int = 0,
    notes: str = "",
    reason: str = "",
) -> int:
    """Create or update a lead grade. Keeps history of grade changes."""
    db = get_db()
    now = _now()
    existing = db.execute(
        "SELECT * FROM lead_grades WHERE prospect_id = ?", (prospect_id,)
    ).fetchone()

    if existing:
        # Append to grade history if grade changed
        history = json.loads(existing["grade_history"] or "[]")
        if grade != existing["grade"]:
            history.append({"grade": grade, "reason": reason, "ts": now})
        db.execute(
            """UPDATE lead_grades SET grade=?, temperature=?, engagement_score=?,
               buying_signals=?, objection_count=?, response_time_avg=?,
               messages_exchanged=?, notes=?, grade_history=?, last_graded_at=?
               WHERE prospect_id=?""",
            (grade, temperature, engagement_score, buying_signals, objection_count,
             response_time_avg, messages_exchanged, notes, json.dumps(history),
             now, prospect_id),
        )
        db.commit()
        return existing["id"]
    else:
        history = [{"grade": grade, "reason": reason, "ts": now}] if reason else []
        cursor = db.execute(
            """INSERT INTO lead_grades (prospect_id, grade, temperature, engagement_score,
               buying_signals, objection_count, response_time_avg, messages_exchanged,
               notes, grade_history, last_graded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (prospect_id, grade, temperature, engagement_score, buying_signals,
             objection_count, response_time_avg, messages_exchanged, notes,
             json.dumps(history), now),
        )
        db.commit()
        return cursor.lastrowid


def get_lead_grade(prospect_id: int) -> Optional[Dict]:
    db = get_db()
    row = db.execute(
        "SELECT * FROM lead_grades WHERE prospect_id = ?", (prospect_id,)
    ).fetchone()
    return dict(row) if row else None


def get_leads_by_grade(grade: str, limit: int = 50) -> List[Dict]:
    db = get_db()
    rows = db.execute(
        """SELECT lg.*, p.ig_handle, p.full_name, p.bio
           FROM lead_grades lg
           JOIN prospects p ON lg.prospect_id = p.id
           WHERE lg.grade = ?
           ORDER BY lg.engagement_score DESC LIMIT ?""",
        (grade, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_hot_leads(limit: int = 20) -> List[Dict]:
    """Get all hot/warm leads sorted by engagement."""
    db = get_db()
    rows = db.execute(
        """SELECT lg.*, p.ig_handle, p.full_name, p.bio, c.stage, c.id as conv_id
           FROM lead_grades lg
           JOIN prospects p ON lg.prospect_id = p.id
           LEFT JOIN conversations c ON c.prospect_id = p.id
           WHERE lg.temperature IN ('hot', 'warm')
           ORDER BY lg.engagement_score DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Story Viewers ───────────────────────────────────────────────────────────

def upsert_story_viewer(ig_handle: str, prospect_id: int = None) -> int:
    db = get_db()
    now = _now()
    existing = db.execute(
        "SELECT * FROM story_viewers WHERE ig_handle = ?", (ig_handle,)
    ).fetchone()

    if existing:
        db.execute(
            """UPDATE story_viewers SET view_count = view_count + 1,
               last_seen_at = ? WHERE ig_handle = ?""",
            (now, ig_handle),
        )
        db.commit()
        return existing["id"]
    else:
        cursor = db.execute(
            """INSERT INTO story_viewers (ig_handle, prospect_id, first_seen_at, last_seen_at)
               VALUES (?, ?, ?, ?)""",
            (ig_handle, prospect_id, now, now),
        )
        db.commit()
        return cursor.lastrowid


def get_story_viewers_for_outreach(limit: int = 50) -> List[Dict]:
    """Get story viewers who haven't been DM'd yet and aren't customers."""
    db = get_db()
    rows = db.execute(
        """SELECT sv.*, p.ig_handle as p_handle, p.full_name, p.bio, p.id as p_id
           FROM story_viewers sv
           LEFT JOIN prospects p ON sv.prospect_id = p.id
           WHERE sv.dm_sent = 0 AND sv.is_customer = 0
           ORDER BY sv.view_count DESC, sv.last_seen_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_repeat_story_viewers(min_views: int = 3, limit: int = 50) -> List[Dict]:
    """Get people who watch stories regularly — hottest warm leads."""
    db = get_db()
    rows = db.execute(
        """SELECT sv.*, p.full_name, p.bio
           FROM story_viewers sv
           LEFT JOIN prospects p ON sv.prospect_id = p.id
           WHERE sv.view_count >= ? AND sv.is_customer = 0
           ORDER BY sv.view_count DESC LIMIT ?""",
        (min_views, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_story_viewer_dmd(ig_handle: str):
    db = get_db()
    db.execute("UPDATE story_viewers SET dm_sent = 1 WHERE ig_handle = ?", (ig_handle,))
    db.commit()


# ── Conversation Audits ─────────────────────────────────────────────────────

def add_conversation_audit(
    conversation_id: int,
    grade: str,
    opener_quality: int = 0,
    qualification_quality: int = 0,
    objection_handling: int = 0,
    close_attempt_quality: int = 0,
    what_worked: str = "",
    what_failed: str = "",
    improvement_suggestions: str = "",
    outcome: str = "ongoing",
    revenue: float = 0.0,
    audit_type: str = "auto",
) -> int:
    db = get_db()
    cursor = db.execute(
        """INSERT INTO conversation_audits
           (conversation_id, audit_type, grade, opener_quality, qualification_quality,
            objection_handling, close_attempt_quality, what_worked, what_failed,
            improvement_suggestions, outcome, revenue, audited_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (conversation_id, audit_type, grade, opener_quality, qualification_quality,
         objection_handling, close_attempt_quality, what_worked, what_failed,
         improvement_suggestions, outcome, revenue, _now()),
    )
    db.commit()
    return cursor.lastrowid


def get_conversation_audits(conversation_id: int) -> List[Dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM conversation_audits WHERE conversation_id = ? ORDER BY audited_at DESC",
        (conversation_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── System State ────────────────────────────────────────────────────────────

def get_system_state(key: str, default: str = "") -> str:
    db = get_db()
    row = db.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_system_state(key: str, value: str):
    db = get_db()
    db.execute(
        """INSERT INTO system_state (key, value, updated_at)
           VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
        (key, value, _now(), value, _now()),
    )
    db.commit()


def get_account_start_date() -> str:
    """Get the date the setter started sending (for ramp-up calculation)."""
    stored = get_system_state("ramp_start_date")
    if stored:
        return stored
    # Fallback: earliest rate_tracker entry
    db = get_db()
    row = db.execute("SELECT MIN(date) as d FROM rate_tracker WHERE send_count > 0").fetchone()
    if row and row["d"]:
        set_system_state("ramp_start_date", row["d"])
        return row["d"]
    # No sends yet — start today
    today = _today()
    set_system_state("ramp_start_date", today)
    return today


def get_ramp_day() -> int:
    """Get current ramp-up day number (1-based). Day 8+ means ramp complete."""
    from datetime import datetime as _dt
    start = get_account_start_date()
    try:
        start_dt = _dt.strptime(start, "%Y-%m-%d")
        return (_dt.now() - start_dt).days + 1
    except (ValueError, TypeError):
        return 1


# ── Watermark ───────────────────────────────────────────────────────────────

def get_watermark(ig_handle: str) -> Optional[Dict]:
    db = get_db()
    row = db.execute(
        "SELECT * FROM follower_watermark WHERE ig_handle = ?", (ig_handle,)
    ).fetchone()
    return dict(row) if row else None


def update_watermark(ig_handle: str, position: int, last_follower: str):
    db = get_db()
    db.execute(
        """INSERT INTO follower_watermark (ig_handle, last_position, last_scanned_at, last_follower_handle)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(ig_handle) DO UPDATE SET
           last_position = ?, last_scanned_at = ?, last_follower_handle = ?""",
        (ig_handle, position, _now(), last_follower, position, _now(), last_follower),
    )
    db.commit()


# ── Heat Score ──────────────────────────────────────────────────────────────

def update_heat_score(conversation_id: int, score: int):
    """Update the heat score for a conversation."""
    db = get_db()
    db.execute(
        "UPDATE conversations SET heat_score = ?, heat_score_updated_at = ? WHERE id = ?",
        (max(0, min(100, score)), _now(), conversation_id),
    )
    db.commit()


def get_hottest_leads(limit: int = 20) -> List[Dict]:
    """Get conversations sorted by heat score (highest first)."""
    db = get_db()
    rows = db.execute(
        """SELECT c.*, p.ig_handle, p.full_name, p.bio
           FROM conversations c
           JOIN prospects p ON p.id = c.prospect_id
           WHERE c.stage NOT IN ('dead', 'disqualified', 'booked', 'show')
           ORDER BY c.heat_score DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── EST Timestamps ──────────────────────────────────────────────────────────

def _now_est() -> str:
    """Current time in EST (Miami)."""
    from datetime import timezone, timedelta
    est = timezone(timedelta(hours=-5))
    return datetime.now(est).strftime("%Y-%m-%d %H:%M:%S")


def get_audit_summary() -> Dict:
    """Get aggregate audit stats for Sales Manager review."""
    db = get_db()
    row = db.execute(
        """SELECT COUNT(*) as total_audits,
                  AVG(opener_quality) as avg_opener,
                  AVG(qualification_quality) as avg_qualification,
                  AVG(objection_handling) as avg_objection,
                  AVG(close_attempt_quality) as avg_close,
                  SUM(CASE WHEN outcome = 'booked' THEN 1 ELSE 0 END) as total_booked,
                  SUM(CASE WHEN outcome = 'closed' THEN 1 ELSE 0 END) as total_closed,
                  SUM(revenue) as total_revenue
           FROM conversation_audits"""
    ).fetchone()
    return dict(row) if row else {}


# ── Blocklist ──────────────────────────────────────────────────────────────────

def is_blocklisted(handle: str) -> bool:
    """Check if a handle is on the blocklist."""
    d = get_db()
    row = d.execute(
        "SELECT 1 FROM blocklist WHERE ig_handle = ?",
        (handle.lower().lstrip("@"),),
    ).fetchone()
    return row is not None


def add_to_blocklist(handle: str, reason: str, source: str):
    """Add a handle to the blocklist."""
    d = get_db()
    try:
        d.execute(
            "INSERT OR IGNORE INTO blocklist (ig_handle, reason, source, added_at) VALUES (?, ?, ?, ?)",
            (handle.lower().lstrip("@"), reason, source, _now()),
        )
        d.commit()
    except Exception:
        pass


def remove_from_blocklist(handle: str):
    """Remove a handle from the blocklist."""
    d = get_db()
    d.execute(
        "DELETE FROM blocklist WHERE ig_handle = ?",
        (handle.lower().lstrip("@"),),
    )
    d.commit()


def get_blocklist_stats() -> Dict:
    """Get blocklist counts by reason."""
    d = get_db()
    rows = d.execute(
        "SELECT reason, COUNT(*) as cnt FROM blocklist GROUP BY reason"
    ).fetchall()
    return {r["reason"]: r["cnt"] for r in rows}


def get_blocklist(reason: Optional[str] = None) -> List[Dict]:
    """Get all blocklist entries, optionally filtered by reason."""
    d = get_db()
    if reason:
        rows = d.execute(
            "SELECT ig_handle, reason, source, added_at FROM blocklist WHERE reason = ? ORDER BY added_at DESC",
            (reason,),
        ).fetchall()
    else:
        rows = d.execute(
            "SELECT ig_handle, reason, source, added_at FROM blocklist ORDER BY added_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── DM Queue ───────────────────────────────────────────────────────────────

DM_QUEUE_SQL = """
CREATE TABLE IF NOT EXISTS dm_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL UNIQUE,
    priority_score INTEGER NOT NULL,
    queued_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (prospect_id) REFERENCES prospects(id)
);
CREATE INDEX IF NOT EXISTS idx_dm_queue_priority ON dm_queue(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_dm_queue_status ON dm_queue(status);
"""


def _ensure_dm_queue_table():
    """Create dm_queue table if it doesn't exist."""
    d = get_db()
    d.executescript(DM_QUEUE_SQL)


def save_dm_queue(entries: List[Dict]):
    """Replace the pending queue with new entries.

    Each entry: {prospect_id: int, priority_score: int}
    """
    _ensure_dm_queue_table()
    d = get_db()
    # Clear old pending entries
    d.execute("DELETE FROM dm_queue WHERE status = 'pending'")
    now = _now()
    for entry in entries:
        try:
            d.execute(
                "INSERT OR REPLACE INTO dm_queue (prospect_id, priority_score, queued_at, status) VALUES (?, ?, ?, 'pending')",
                (entry["prospect_id"], entry["priority_score"], now),
            )
        except Exception:
            pass
    d.commit()


def get_pending_queue(limit: int = 200) -> List[Dict]:
    """Get pending queue entries joined with prospect data, ordered by priority."""
    _ensure_dm_queue_table()
    d = get_db()
    rows = d.execute(
        """SELECT q.id as queue_id, q.priority_score, q.queued_at,
                  p.id as prospect_id, p.ig_handle, p.bio, p.icp_score,
                  p.source, p.created_at as prospect_created_at
           FROM dm_queue q
           JOIN prospects p ON p.id = q.prospect_id
           WHERE q.status = 'pending'
           ORDER BY q.priority_score DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_queue_sent(prospect_id: int):
    """Mark a queue entry as sent."""
    _ensure_dm_queue_table()
    d = get_db()
    d.execute(
        "UPDATE dm_queue SET status = 'sent' WHERE prospect_id = ?",
        (prospect_id,),
    )
    d.commit()
