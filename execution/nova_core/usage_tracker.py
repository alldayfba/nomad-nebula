"""Tier-aware Keepa usage quotas.

Counts live in nova.db (`keepa_usage` table). The Flask `/nova/usage`
endpoint reads this same table so the 247profits.org SaaS dashboard can
show students their remaining quota — single source of truth.

Tier resolution:
    1. If a caller passes `tier` directly, use it.
    2. Else read `students.db` (already synced from Supabase) for the
       matching discord_user_id.
    3. Default to `trial` if unknown (lowest cap — safe).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

_NOVA_DB = Path(__file__).resolve().parents[2] / ".tmp" / "nova" / "nova.db"
_STUDENTS_DB = Path(__file__).resolve().parents[2] / ".tmp" / "coaching" / "students.db"

# Defaults — overridable via env so we can tune without a deploy.
TIER_CAPS_DEFAULT = {
    "paid_in_full": int(os.getenv("KEEPA_CAP_PIF", "50")),
    "subscription": int(os.getenv("KEEPA_CAP_SUB", "30")),
    "trial": int(os.getenv("KEEPA_CAP_TRIAL", "5")),
    "unknown": int(os.getenv("KEEPA_CAP_UNKNOWN", "5")),
}

# Aliases: Supabase rows use several naming conventions.
_TIER_ALIASES = {
    "pif": "paid_in_full", "paid": "paid_in_full", "paid_in_full": "paid_in_full",
    "lifetime": "paid_in_full", "premium": "paid_in_full",
    "sub": "subscription", "subscription": "subscription", "monthly": "subscription",
    "trial": "trial", "free": "trial",
}


def _conn() -> sqlite3.Connection:
    _NOVA_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_NOVA_DB), timeout=5)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS keepa_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            asin TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            tier TEXT,
            cached INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_keepa_usage_user_day ON keepa_usage(user_id, created_at)")
    return conn


def _normalize_tier(raw: str | None) -> str:
    if not raw:
        return "unknown"
    return _TIER_ALIASES.get(raw.strip().lower(), "unknown")


def resolve_tier(discord_user_id: str) -> str:
    """Best-effort tier lookup from the synced students.db."""
    try:
        if not _STUDENTS_DB.exists():
            return "unknown"
        conn = sqlite3.connect(str(_STUDENTS_DB), timeout=3)
        try:
            row = conn.execute(
                "SELECT student_tier, plan, subscription_status FROM students "
                "WHERE discord_user_id = ? LIMIT 1",
                (str(discord_user_id),),
            ).fetchone()
        except sqlite3.OperationalError:
            # Schema variant — older installs may not have these columns.
            row = None
        conn.close()
        if not row:
            return "unknown"
        tier, plan, _status = row
        return _normalize_tier(tier or plan)
    except Exception:
        return "unknown"


def _today_bounds() -> tuple[str, str]:
    now = datetime.utcnow()
    start = datetime(now.year, now.month, now.day)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def count_today(user_id: str) -> int:
    """Number of non-cached Keepa calls this user has made today (UTC)."""
    try:
        start, end = _today_bounds()
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM keepa_usage "
                "WHERE user_id = ? AND cached = 0 AND created_at >= ? AND created_at < ?",
                (str(user_id), start, end),
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except Exception:
        return 0


def check_quota(user_id: str, tier: str | None = None) -> dict:
    """Return the caller's quota state without consuming any budget.

    Shape: {allowed, remaining, used, cap, tier}
    """
    resolved = _normalize_tier(tier) if tier else resolve_tier(user_id)
    cap = TIER_CAPS_DEFAULT.get(resolved, TIER_CAPS_DEFAULT["unknown"])
    used = count_today(user_id)
    remaining = max(0, cap - used)
    return {
        "allowed": remaining > 0,
        "remaining": remaining,
        "used": used,
        "cap": cap,
        "tier": resolved,
    }


def record(
    user_id: str,
    asin: str,
    tokens_used: int,
    tier: str | None = None,
    cached: bool = False,
) -> None:
    """Append a usage row. Cache hits are logged (tokens_used=0, cached=1)
    so the SaaS dashboard can show total lookups vs. paid lookups separately.
    """
    try:
        conn = _conn()
        try:
            # Explicit ISO timestamp — SQLite's CURRENT_TIMESTAMP uses a
            # space separator, which breaks string comparisons against our
            # datetime.isoformat() bounds.
            conn.execute(
                "INSERT INTO keepa_usage (user_id, asin, tokens_used, tier, cached, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(user_id),
                    asin,
                    int(tokens_used or 0),
                    _normalize_tier(tier) if tier else None,
                    1 if cached else 0,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def usage_summary(user_id: str) -> dict:
    """Today + month + all-time, for dashboard rendering."""
    try:
        conn = _conn()
        try:
            now = datetime.utcnow()
            today_start = datetime(now.year, now.month, now.day).isoformat()
            month_start = datetime(now.year, now.month, 1).isoformat()

            def _count(where: str, params: tuple) -> int:
                r = conn.execute(
                    f"SELECT COUNT(*) FROM keepa_usage WHERE user_id = ? {where}",
                    (str(user_id), *params),
                ).fetchone()
                return int(r[0]) if r else 0

            def _tokens(where: str, params: tuple) -> int:
                r = conn.execute(
                    f"SELECT COALESCE(SUM(tokens_used), 0) FROM keepa_usage "
                    f"WHERE user_id = ? {where}",
                    (str(user_id), *params),
                ).fetchone()
                return int(r[0]) if r else 0

            return {
                "today_lookups": _count("AND created_at >= ?", (today_start,)),
                "today_tokens": _tokens("AND created_at >= ?", (today_start,)),
                "month_lookups": _count("AND created_at >= ?", (month_start,)),
                "month_tokens": _tokens("AND created_at >= ?", (month_start,)),
                "all_time_lookups": _count("", ()),
            }
        finally:
            conn.close()
    except Exception:
        return {"today_lookups": 0, "today_tokens": 0, "month_lookups": 0, "month_tokens": 0, "all_time_lookups": 0}
