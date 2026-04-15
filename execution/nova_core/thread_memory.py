"""Per-thread short-term memory for ASINs.

Students constantly follow up with "recalculate at $7" or "use that ASIN" —
without this, Nova would re-ask for the ASIN every turn. We persist the
last-seen ASIN per (platform, channel/thread, user) with a 24h TTL.

Not a replacement for real conversation context — the LLM still has chat
history. This is a fast-path lookup so the pre-processing pipeline knows
which ASIN to rehydrate before calling Keepa.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

_DB = Path(__file__).resolve().parents[2] / ".tmp" / "nova" / "nova.db"
_TTL_HOURS = 24


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB), timeout=5)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS thread_asin_memory (
            platform TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            asin TEXT NOT NULL,
            buy_cost REAL,
            moq INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (platform, thread_id, user_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_thread_memory_updated ON thread_asin_memory(updated_at)")
    return conn


def remember(
    platform: str,
    thread_id: str,
    user_id: str,
    asin: str,
    buy_cost: float | None = None,
    moq: int | None = None,
) -> None:
    """Persist the last ASIN (+ optional buy cost / MOQ) for this thread+user."""
    try:
        conn = _conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO thread_asin_memory "
                "(platform, thread_id, user_id, asin, buy_cost, moq, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    platform,
                    str(thread_id),
                    str(user_id),
                    asin,
                    buy_cost,
                    moq,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # best-effort — memory shouldn't break the bot


def recall(
    platform: str,
    thread_id: str,
    user_id: str,
) -> dict | None:
    """Return the last-seen ASIN for this thread+user if it's still fresh."""
    try:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT asin, buy_cost, moq, updated_at FROM thread_asin_memory "
                "WHERE platform = ? AND thread_id = ? AND user_id = ?",
                (platform, str(thread_id), str(user_id)),
            ).fetchone()
            if not row:
                return None
            asin, buy_cost, moq, updated_at = row
            stamp = datetime.fromisoformat(str(updated_at).replace("Z", "").split(".")[0])
            if datetime.utcnow() - stamp > timedelta(hours=_TTL_HOURS):
                return None
            return {"asin": asin, "buy_cost": buy_cost, "moq": moq}
        finally:
            conn.close()
    except Exception:
        return None


def purge_stale(ttl_hours: int = _TTL_HOURS) -> int:
    """Delete entries older than the TTL. Call from maintenance jobs."""
    try:
        conn = _conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(hours=ttl_hours)).isoformat()
            cur = conn.execute("DELETE FROM thread_asin_memory WHERE updated_at < ?", (cutoff,))
            conn.commit()
            return cur.rowcount or 0
        finally:
            conn.close()
    except Exception:
        return 0


# Trigger phrases that mean "use the remembered ASIN". Pre-processing should
# only fall back to recall() when the current message has no ASIN of its own
# AND includes one of these phrases — otherwise we risk answering about a
# product the student has moved on from.
_RECALL_TRIGGERS = (
    "that asin",
    "that product",
    "same asin",
    "same product",
    "recalculate",
    "recalc",
    "re-run",
    "rerun",
    "use that",
    "with that",
    "above asin",
    "previous asin",
    "last asin",
)


def should_recall(message_lower: str) -> bool:
    """True if the message looks like a follow-up referring to an earlier ASIN."""
    if not message_lower:
        return False
    m = message_lower.lower()
    return any(trigger in m for trigger in _RECALL_TRIGGERS)
