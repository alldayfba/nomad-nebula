#!/usr/bin/env python3
"""
Script: student_health_monitor.py
Purpose: Multi-dimensional student health scoring for Amazon FBA coaching.
         Scores each student 0-100 across 5 dimensions (Milestone Progress,
         Engagement, Momentum, Mood, Recency). Detects at-risk students,
         queues intervention touchpoints, tracks churn/graduation/referrals.
         Extends the existing student_tracker.py database.
Inputs:  CLI subcommands
Outputs: Health reports, at-risk alerts, leaderboard, engagement digests,
         graduation checks, JSON export for CEO Command Center

CLI:
    python execution/student_health_monitor.py daily-scan
    python execution/student_health_monitor.py health-report
    python execution/student_health_monitor.py student-detail --name "John"
    python execution/student_health_monitor.py at-risk
    python execution/student_health_monitor.py log-signal --student "John" --type discord_message --channel discord [--notes "Asked about sourcing"]
    python execution/student_health_monitor.py leaderboard
    python execution/student_health_monitor.py engagement-digest
    python execution/student_health_monitor.py graduation-check
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Import milestone definitions from student_tracker
from student_tracker import MILESTONE_ORDER, EXPECTED_DAYS, STUCK_MULTIPLIER

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"

# ── Valid Signal Types ──────────────────────────────────────────────────────

VALID_SIGNAL_TYPES = [
    # Discord
    "discord_message", "discord_question", "discord_help_given", "discord_silent",
    # Calls
    "call_attended", "call_missed", "call_question_asked",
    # Assignments
    "assignment_submitted", "assignment_late", "assignment_missing",
    # Milestones
    "milestone_completed", "milestone_stuck",
    # Mood
    "mood_positive", "mood_neutral", "mood_frustrated", "mood_disengaged",
    # Financial
    "payment_on_time", "payment_late", "payment_failed",
    # Platform
    "platform_login", "platform_inactive",
    # Wins
    "first_sale", "profitable_product", "revenue_milestone", "screenshot_shared",
]

POSITIVE_ENGAGEMENT_TYPES = {
    "discord_message", "call_attended", "assignment_submitted",
    "discord_question", "discord_help_given", "platform_login",
    "screenshot_shared", "call_question_asked",
}

NEGATIVE_ENGAGEMENT_TYPES = {
    "discord_silent", "call_missed", "assignment_missing",
    "assignment_late", "platform_inactive",
}

ACTIVITY_TYPES = POSITIVE_ENGAGEMENT_TYPES | {
    "assignment_late", "mood_positive", "mood_neutral",
    "mood_frustrated", "milestone_completed", "first_sale",
    "profitable_product", "revenue_milestone",
}

MOOD_MAP = {
    "positive": 15,
    "neutral": 10,
    "frustrated": 5,
    "disengaged": 0,
}

RISK_LEVELS = [
    (80, "green"),
    (60, "yellow"),
    (40, "orange"),
    (20, "red"),
    (0, "critical"),
]

WEIGHTS = {
    "milestone_progress": 25,
    "engagement": 30,
    "momentum": 20,
    "mood": 15,
    "recency": 10,
}

# ── Extended Schema ─────────────────────────────────────────────────────────

EXTENDED_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS engagement_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    signal_type TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'unknown',
    value TEXT DEFAULT 'true',
    date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS health_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    breakdown TEXT,
    risk_level TEXT,
    date TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS touchpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    channel TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'queued',
    sent_at TEXT,
    response_at TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS churn_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    reason_category TEXT NOT NULL,
    reason_detail TEXT,
    exit_interview_done INTEGER DEFAULT 0,
    win_back_attempted INTEGER DEFAULT 0,
    win_back_result TEXT,
    date TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS testimonials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    milestone TEXT,
    content TEXT,
    media_url TEXT,
    status TEXT DEFAULT 'requested',
    requested_at TEXT NOT NULL,
    received_at TEXT,
    approved_at TEXT,
    published_channels TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_student_id INTEGER NOT NULL,
    referred_name TEXT NOT NULL,
    referred_email TEXT,
    referral_code TEXT UNIQUE,
    status TEXT DEFAULT 'referred',
    commission_rate REAL DEFAULT 0.10,
    commission_amount REAL DEFAULT 0,
    commission_paid INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    enrolled_at TEXT,
    FOREIGN KEY (referrer_student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS graduation_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    offer_presented TEXT,
    offer_accepted TEXT,
    new_revenue REAL DEFAULT 0,
    completed_at TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS backend_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    offer_type TEXT NOT NULL,
    monthly_revenue REAL NOT NULL,
    start_date TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    cancelled_at TEXT,
    cancel_reason TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE INDEX IF NOT EXISTS idx_eng_signals_student ON engagement_signals(student_id);
CREATE INDEX IF NOT EXISTS idx_eng_signals_date ON engagement_signals(date);
CREATE INDEX IF NOT EXISTS idx_eng_signals_type ON engagement_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_health_snap_student ON health_snapshots(student_id);
CREATE INDEX IF NOT EXISTS idx_touchpoints_student ON touchpoints(student_id);
CREATE INDEX IF NOT EXISTS idx_churn_student ON churn_events(student_id);
CREATE INDEX IF NOT EXISTS idx_testimonials_student ON testimonials(student_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_student_id);
CREATE INDEX IF NOT EXISTS idx_graduation_student ON graduation_flows(student_id);
CREATE INDEX IF NOT EXISTS idx_backend_sub_student ON backend_subscriptions(student_id);
"""

# Columns to add to the existing students table
ALTER_COLUMNS = [
    ("discord_user_id", "TEXT"),
    ("discord_channel_id", "TEXT"),
    ("phone", "TEXT"),
    ("risk_level", "TEXT DEFAULT 'green'"),
    ("last_discord_activity", "TEXT"),
    ("last_call_attended", "TEXT"),
    ("last_assignment_submitted", "TEXT"),
    ("enrollment_revenue", "REAL"),
    ("payment_plan", "TEXT"),
    ("next_payment_date", "TEXT"),
    ("referral_source", "TEXT"),
    ("subscription_tier", "TEXT DEFAULT 'core'"),
]


# ── Database Connection ──────────────────────────────────────────────────────

def get_db():
    """Connect to the shared coaching DB and ensure extended schema exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(EXTENDED_SCHEMA_SQL)

    # Add new columns to existing students table
    for col_name, col_type in ALTER_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE students ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    return conn


# ── Helper Functions ─────────────────────────────────────────────────────────

def _get_risk_level(score):
    """Map a 0-100 score to a risk level string."""
    for threshold, level in RISK_LEVELS:
        if score >= threshold:
            return level
    return "critical"


def _find_student(conn, name):
    """Look up a student by name (case-insensitive LIKE match)."""
    row = conn.execute("SELECT * FROM students WHERE name = ?", (name,)).fetchone()
    if row:
        return row
    # Fallback: partial match
    row = conn.execute(
        "SELECT * FROM students WHERE name LIKE ? LIMIT 1", (f"%{name}%",)
    ).fetchone()
    return row


# ── Core Functions ───────────────────────────────────────────────────────────

def log_signal(student_name, signal_type, channel="unknown", value="true",
               date=None, notes=None):
    """Record an engagement signal for a student."""
    if signal_type not in VALID_SIGNAL_TYPES:
        raise ValueError(
            f"Invalid signal type '{signal_type}'. Valid: {VALID_SIGNAL_TYPES}"
        )

    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")

    conn = get_db()
    try:
        student = _find_student(conn, student_name)
        if not student:
            raise ValueError(f"Student '{student_name}' not found.")

        conn.execute("""
            INSERT INTO engagement_signals
                (student_id, signal_type, channel, value, date, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (student["id"], signal_type, channel, value, date, notes,
              datetime.utcnow().isoformat()))

        # Update activity timestamps on the student record
        update_fields = {}
        if signal_type in ("discord_message", "discord_question",
                           "discord_help_given"):
            update_fields["last_discord_activity"] = date
        if signal_type in ("call_attended", "call_question_asked"):
            update_fields["last_call_attended"] = date
        if signal_type == "assignment_submitted":
            update_fields["last_assignment_submitted"] = date

        for field, val in update_fields.items():
            try:
                conn.execute(
                    f"UPDATE students SET {field} = ? WHERE id = ?",
                    (val, student["id"])
                )
            except sqlite3.OperationalError:
                pass  # Column might not exist yet

        conn.commit()
        return {
            "student": student["name"],
            "signal": signal_type,
            "channel": channel,
            "date": date,
        }
    finally:
        conn.close()


def calculate_health_score(student_id):
    """Calculate the 5-dimension health score for one student."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if not student:
            return None

        today = datetime.utcnow()
        today_str = today.strftime("%Y-%m-%d")
        cutoff_14d = (today - timedelta(days=14)).strftime("%Y-%m-%d")

        # ── 1. Milestone Progress (25 pts) ──────────────────────────────
        milestone_score = _score_milestone_progress(conn, student)

        # ── 2. Engagement (30 pts) ──────────────────────────────────────
        engagement_score = _score_engagement(conn, student["id"], cutoff_14d)

        # ── 3. Momentum (20 pts) ────────────────────────────────────────
        momentum_score = _score_momentum(conn, student["id"])

        # ── 4. Mood (15 pts) ────────────────────────────────────────────
        mood_score = _score_mood(conn, student["id"])

        # ── 5. Recency (10 pts) ─────────────────────────────────────────
        recency_score = _score_recency(conn, student["id"])

        total = (milestone_score + engagement_score + momentum_score +
                 mood_score + recency_score)

        # ── Penalties ───────────────────────────────────────────────────
        # No contact > 14 days
        last_activity_date = _get_last_activity_date(conn, student["id"])
        if last_activity_date:
            days_since = (today - last_activity_date).days
            if days_since > 14:
                total = max(0, total - 15)

        # 2+ consecutive call_missed
        recent_calls = conn.execute("""
            SELECT signal_type FROM engagement_signals
            WHERE student_id = ? AND signal_type IN ('call_attended', 'call_missed')
            ORDER BY date DESC, id DESC LIMIT 3
        """, (student_id,)).fetchall()
        consecutive_missed = 0
        for s in recent_calls:
            if s["signal_type"] == "call_missed":
                consecutive_missed += 1
            else:
                break
        if consecutive_missed >= 2:
            total = max(0, total - 10)

        total = max(0, min(100, total))
        risk_level = _get_risk_level(total)

        breakdown = {
            "milestone_progress": milestone_score,
            "engagement": engagement_score,
            "momentum": momentum_score,
            "mood": mood_score,
            "recency": recency_score,
        }

        # Save snapshot
        conn.execute("""
            INSERT INTO health_snapshots (student_id, score, breakdown, risk_level, date)
            VALUES (?, ?, ?, ?, ?)
        """, (student_id, total, json.dumps(breakdown), risk_level, today_str))

        # Update student record
        conn.execute(
            "UPDATE students SET health_score = ? WHERE id = ?",
            (total, student_id)
        )
        try:
            conn.execute(
                "UPDATE students SET risk_level = ? WHERE id = ?",
                (risk_level, student_id)
            )
        except sqlite3.OperationalError:
            pass

        conn.commit()
        return {
            "score": total,
            "breakdown": breakdown,
            "risk_level": risk_level,
        }
    finally:
        conn.close()


def _score_milestone_progress(conn, student):
    """Milestone Progress dimension (25 pts)."""
    if student["status"] == "graduated":
        return WEIGHTS["milestone_progress"]

    current_ms = conn.execute("""
        SELECT * FROM milestones
        WHERE student_id = ? AND status = 'in_progress'
        ORDER BY id DESC LIMIT 1
    """, (student["id"],)).fetchone()

    if not current_ms:
        return WEIGHTS["milestone_progress"]

    tier = student["tier"] if student["tier"] in EXPECTED_DAYS else "A"
    tier_expected = EXPECTED_DAYS[tier]
    milestone_name = current_ms["milestone"]
    expected = tier_expected.get(milestone_name, 14)
    stuck_threshold = expected * STUCK_MULTIPLIER

    try:
        started = datetime.strptime(current_ms["started_date"], "%Y-%m-%d")
    except (ValueError, TypeError):
        return round(WEIGHTS["milestone_progress"] * 0.5)

    days_on = (datetime.utcnow() - started).days

    if days_on <= expected:
        # On track
        return WEIGHTS["milestone_progress"]
    elif days_on <= stuck_threshold:
        # Approaching stuck (proportional decrease)
        ratio = (stuck_threshold - days_on) / (stuck_threshold - expected)
        return max(5, round(WEIGHTS["milestone_progress"] * ratio))
    else:
        # Stuck -- heavy penalty
        overshoot = days_on / stuck_threshold
        score = max(5, round(WEIGHTS["milestone_progress"] * (1 / overshoot)))
        return min(score, 10)


def _score_engagement(conn, student_id, cutoff_14d):
    """Engagement dimension (30 pts)."""
    signals = conn.execute("""
        SELECT signal_type, COUNT(*) as cnt
        FROM engagement_signals
        WHERE student_id = ? AND date >= ?
        GROUP BY signal_type
    """, (student_id, cutoff_14d)).fetchall()
    sig = {row["signal_type"]: row["cnt"] for row in signals}

    positive = sum(sig.get(t, 0) for t in POSITIVE_ENGAGEMENT_TYPES)
    negative = sum(sig.get(t, 0) for t in NEGATIVE_ENGAGEMENT_TYPES)
    total = positive + negative

    if total > 0:
        engagement_rate = positive / total
    else:
        engagement_rate = 0.5  # No data = neutral

    return round(engagement_rate * WEIGHTS["engagement"])


def _score_momentum(conn, student_id):
    """Momentum dimension (20 pts) -- compare last 3 weekly snapshots."""
    snapshots = conn.execute("""
        SELECT score, date FROM health_snapshots
        WHERE student_id = ?
        ORDER BY date DESC LIMIT 21
    """, (student_id,)).fetchall()

    if len(snapshots) < 2:
        # Not enough history -- assume stable
        return round(WEIGHTS["momentum"] * 0.6)

    # Bucket into 7-day windows
    now = datetime.utcnow()
    periods = []
    for week_offset in range(3):
        end = now - timedelta(days=week_offset * 7)
        start = end - timedelta(days=7)
        end_str = end.strftime("%Y-%m-%d")
        start_str = start.strftime("%Y-%m-%d")
        week_scores = [
            s["score"] for s in snapshots
            if start_str <= s["date"] <= end_str
        ]
        if week_scores:
            periods.append(sum(week_scores) / len(week_scores))

    if len(periods) < 2:
        return round(WEIGHTS["momentum"] * 0.6)

    latest = periods[0]
    previous = periods[1]
    diff = latest - previous

    if diff > 5:
        # Improving
        return WEIGHTS["momentum"]
    elif diff >= -5:
        # Stable
        return 12
    else:
        # Declining
        decline_ratio = max(0, 1 + (diff / 50))
        return max(0, round(WEIGHTS["momentum"] * decline_ratio))


def _score_mood(conn, student_id):
    """Mood dimension (15 pts) -- average of last 3 mood readings."""
    # Mood from check_ins table
    checkin_moods = conn.execute("""
        SELECT mood FROM check_ins
        WHERE student_id = ? AND mood IS NOT NULL
        ORDER BY date DESC LIMIT 3
    """, (student_id,)).fetchall()

    # Mood from engagement signals (mood_* types)
    signal_moods = conn.execute("""
        SELECT signal_type FROM engagement_signals
        WHERE student_id = ? AND signal_type LIKE 'mood_%'
        ORDER BY date DESC, id DESC LIMIT 3
    """, (student_id,)).fetchall()

    mood_values = []

    for row in checkin_moods:
        mood_str = row["mood"]
        if mood_str in MOOD_MAP:
            mood_values.append(MOOD_MAP[mood_str])

    for row in signal_moods:
        # Extract mood from signal_type like "mood_positive" -> "positive"
        mood_str = row["signal_type"].replace("mood_", "")
        if mood_str in MOOD_MAP:
            mood_values.append(MOOD_MAP[mood_str])

    # Take at most 3 most recent
    mood_values = mood_values[:3]

    if not mood_values:
        # No mood data -- assume neutral
        return round(MOOD_MAP["neutral"])

    return round(sum(mood_values) / len(mood_values))


def _score_recency(conn, student_id):
    """Recency dimension (10 pts) -- days since last activity."""
    last_date = _get_last_activity_date(conn, student_id)

    if not last_date:
        return 0

    days_since = (datetime.utcnow() - last_date).days

    if days_since <= 1:
        return 10
    elif days_since <= 3:
        return 8
    elif days_since <= 5:
        return 5
    elif days_since <= 7:
        return 3
    else:
        return 0


def _get_last_activity_date(conn, student_id):
    """Return datetime of last recorded activity or None."""
    # Check engagement signals
    row = conn.execute("""
        SELECT MAX(date) as last_date FROM engagement_signals
        WHERE student_id = ? AND signal_type IN ({})
    """.format(",".join("?" for _ in ACTIVITY_TYPES)),
        (student_id, *ACTIVITY_TYPES)
    ).fetchone()

    if row and row["last_date"]:
        try:
            return datetime.strptime(row["last_date"], "%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    # Fallback: check_ins table
    row = conn.execute("""
        SELECT MAX(date) as last_date FROM check_ins WHERE student_id = ?
    """, (student_id,)).fetchone()

    if row and row["last_date"]:
        try:
            return datetime.strptime(row["last_date"], "%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    return None


# ── Intervention Recommendations ─────────────────────────────────────────────

def _generate_intervention(student, risk_level, current_milestone):
    """Generate a touchpoint message based on risk level.

    Includes sourcing agent dispatch for product-related milestones and
    milestone-specific help tailored to where the student is stuck.
    """
    name = student["name"]
    ms_display = (current_milestone or "your current step").replace("_", " ")

    # Milestone-specific help actions (sourcing agent integration)
    milestone_actions = {
        "niche_selected": {
            "help": "reviewing trending categories and niches",
            "dispatch": "sourcing-agent: run category scan for trending niches",
        },
        "product_selected": {
            "help": "finding profitable products",
            "dispatch": "sourcing-agent: run reverse sourcing for student's niche",
            "cmd": "python execution/source.py scan --mode clearance --count 10",
        },
        "supplier_contacted": {
            "help": "supplier outreach and negotiation",
            "dispatch": None,
        },
        "sample_received": {
            "help": "tracking your shipment and sample quality",
            "dispatch": None,
        },
        "listing_created": {
            "help": "optimizing your listing for conversions",
            "dispatch": "amazon-agent: listing optimization review",
        },
        "listing_live": {
            "help": "getting your listing indexed and buybox-eligible",
            "dispatch": "amazon-agent: listing health check",
        },
        "first_sale": {
            "help": "PPC strategy and pricing optimization",
            "dispatch": "amazon-agent: PPC campaign review",
        },
        "profitable_month": {
            "help": "scaling and reorder optimization",
            "dispatch": "sourcing-agent: find 5 more products in same category",
        },
        "10k_month": {
            "help": "product expansion and wholesale transition",
            "dispatch": "sourcing-agent: wholesale opportunity scan",
        },
    }

    ms_info = milestone_actions.get(current_milestone, {"help": ms_display, "dispatch": None})

    if risk_level == "yellow":
        return {
            "type": "friendly_dm",
            "channel": "discord",
            "message": (
                f"Hey {name}, noticed you've been quiet. Everything good? "
                f"I'm here if you need help with {ms_info['help']}."
            ),
            "agent_dispatch": ms_info.get("dispatch"),
        }
    elif risk_level == "orange":
        msg = (
            f"Hey {name}, I see you're working on {ms_display}. "
            f"A lot of students get stuck here. Want to hop on a quick "
            f"call this week?"
        )
        # For product-related milestones, proactively offer sourcing help
        if current_milestone in ("niche_selected", "product_selected", "profitable_month"):
            msg += (
                f"\n\nIn the meantime, I'm running a product scan to find some "
                f"opportunities for you. Check your DM for results shortly."
            )
        return {
            "type": "direct_help",
            "channel": "discord",
            "message": msg,
            "agent_dispatch": ms_info.get("dispatch"),
            "sourcing_cmd": ms_info.get("cmd"),
        }
    elif risk_level == "red":
        return {
            "type": "sabbo_flag",
            "channel": "internal",
            "message": (
                f"[SABBO ATTENTION] {name} is RED risk. "
                f"Current milestone: {ms_display}. "
                f"Recommend personal outreach or 1-on-1 call."
            ),
            "agent_dispatch": ms_info.get("dispatch"),
            "recommended_action": f"Review {name}'s specific blockers on {ms_display}. "
                                  f"Consider dispatching: {ms_info.get('dispatch') or 'personal coaching call'}",
        }
    elif risk_level == "critical":
        return {
            "type": "urgent",
            "channel": "internal",
            "message": (
                f"[URGENT] {name} is CRITICAL risk. "
                f"Milestone: {ms_display}. Immediate Sabbo intervention needed. "
                f"Possible churn imminent."
            ),
            "agent_dispatch": ms_info.get("dispatch"),
        }
    return None


# ── High-Level Operations ────────────────────────────────────────────────────

def daily_scan():
    """Calculate health for all active students, queue interventions."""
    conn = get_db()
    try:
        students = conn.execute(
            "SELECT id, name FROM students WHERE status IN ('active', 'at_risk')"
        ).fetchall()
    finally:
        conn.close()

    results = []
    interventions = []

    for s in students:
        score_data = calculate_health_score(s["id"])
        if not score_data:
            continue

        entry = {"name": s["name"], **score_data}
        results.append(entry)

        risk = score_data["risk_level"]
        if risk in ("yellow", "orange", "red", "critical"):
            # Get current milestone for intervention message
            conn2 = get_db()
            try:
                student_row = conn2.execute(
                    "SELECT * FROM students WHERE id = ?", (s["id"],)
                ).fetchone()
                current_ms = student_row["current_milestone"] if student_row else None
            finally:
                conn2.close()

            intervention = _generate_intervention(
                {"name": s["name"]}, risk, current_ms
            )
            if intervention:
                interventions.append({"student": s["name"], **intervention})
                # Queue the touchpoint
                conn3 = get_db()
                try:
                    conn3.execute("""
                        INSERT INTO touchpoints
                            (student_id, type, channel, message, status)
                        VALUES (?, ?, ?, ?, 'queued')
                    """, (s["id"], intervention["type"],
                          intervention["channel"], intervention["message"]))
                    conn3.commit()
                finally:
                    conn3.close()

    return {
        "scanned": len(results),
        "results": sorted(results, key=lambda x: x["score"]),
        "interventions": interventions,
        "scan_time": datetime.utcnow().isoformat(),
    }


def health_report():
    """Formatted table of all students with scores and risk levels."""
    conn = get_db()
    try:
        students = conn.execute(
            "SELECT id, name FROM students WHERE status != 'churned'"
        ).fetchall()
    finally:
        conn.close()

    results = []
    for s in students:
        score_data = calculate_health_score(s["id"])
        if score_data:
            results.append({"name": s["name"], **score_data})

    if not results:
        return "No students found."

    lines = [
        "=== STUDENT HEALTH REPORT ===",
        "",
        f"{'Student':<20} {'Score':>6} {'Risk':<10} {'MP':>4} {'ENG':>4} "
        f"{'MOM':>4} {'MOD':>4} {'REC':>4}",
        "-" * 65,
    ]

    for r in sorted(results, key=lambda x: x["score"]):
        b = r["breakdown"]
        risk_display = r["risk_level"].upper()
        lines.append(
            f"{r['name']:<20} {r['score']:>5}  {risk_display:<10} "
            f"{b['milestone_progress']:>4} {b['engagement']:>4} "
            f"{b['momentum']:>4} {b['mood']:>4} {b['recency']:>4}"
        )

    at_risk = [r for r in results if r["risk_level"] in
               ("yellow", "orange", "red", "critical")]
    green = [r for r in results if r["risk_level"] == "green"]

    lines.extend([
        "",
        f"Total: {len(results)} | Green: {len(green)} | "
        f"At-risk: {len(at_risk)}",
    ])

    for r in at_risk:
        lines.append(
            f"  [{r['risk_level'].upper()}] {r['name']} -- score {r['score']}"
        )

    return "\n".join(lines)


def get_student_detail(name):
    """Full health detail for one student."""
    conn = get_db()
    try:
        student = _find_student(conn, name)
        if not student:
            return None

        sid = student["id"]

        # Calculate fresh score
        score_data = calculate_health_score(sid)

        # Re-open connection (calculate_health_score closes it)
        conn2 = get_db()
        try:
            # Recent signals
            signals = conn2.execute("""
                SELECT signal_type, channel, date, notes
                FROM engagement_signals
                WHERE student_id = ? ORDER BY date DESC LIMIT 20
            """, (sid,)).fetchall()

            # Score history
            snapshots = conn2.execute("""
                SELECT score, breakdown, risk_level, date
                FROM health_snapshots
                WHERE student_id = ? ORDER BY date DESC LIMIT 14
            """, (sid,)).fetchall()

            # Milestones
            milestones = conn2.execute("""
                SELECT * FROM milestones
                WHERE student_id = ? ORDER BY id ASC
            """, (sid,)).fetchall()

            # Recent check-ins
            check_ins = conn2.execute("""
                SELECT * FROM check_ins
                WHERE student_id = ? ORDER BY date DESC LIMIT 5
            """, (sid,)).fetchall()

            # Queued touchpoints
            touchpoints_pending = conn2.execute("""
                SELECT type, channel, message, status
                FROM touchpoints
                WHERE student_id = ? AND status = 'queued'
                ORDER BY id DESC LIMIT 5
            """, (sid,)).fetchall()

            # Refresh student row
            student = conn2.execute(
                "SELECT * FROM students WHERE id = ?", (sid,)
            ).fetchone()

            # Days in program
            try:
                start = datetime.strptime(student["start_date"], "%Y-%m-%d")
                days_in = (datetime.utcnow() - start).days
            except (ValueError, TypeError):
                days_in = 0

            return {
                "student": dict(student),
                "days_in_program": days_in,
                "health": score_data,
                "milestones": [dict(m) for m in milestones],
                "recent_signals": [dict(s) for s in signals],
                "score_history": [dict(s) for s in snapshots],
                "check_ins": [dict(c) for c in check_ins],
                "pending_touchpoints": [dict(t) for t in touchpoints_pending],
            }
        finally:
            conn2.close()
    finally:
        conn.close()


def get_at_risk():
    """List at-risk students sorted by severity."""
    conn = get_db()
    try:
        students = conn.execute(
            "SELECT id, name FROM students WHERE status IN ('active', 'at_risk')"
        ).fetchall()
    finally:
        conn.close()

    all_scored = []
    for s in students:
        score_data = calculate_health_score(s["id"])
        if score_data and score_data["risk_level"] in (
            "yellow", "orange", "red", "critical"
        ):
            # Get current milestone
            conn2 = get_db()
            try:
                student_row = conn2.execute(
                    "SELECT current_milestone FROM students WHERE id = ?",
                    (s["id"],)
                ).fetchone()
                ms = student_row["current_milestone"] if student_row else None
            finally:
                conn2.close()

            intervention = _generate_intervention(
                {"name": s["name"]}, score_data["risk_level"], ms
            )

            all_scored.append({
                "name": s["name"],
                "score": score_data["score"],
                "risk_level": score_data["risk_level"],
                "breakdown": score_data["breakdown"],
                "current_milestone": ms,
                "recommended_intervention": intervention,
            })

    # Sort: critical first, then red, orange, yellow -- by score ascending
    risk_order = {"critical": 0, "red": 1, "orange": 2, "yellow": 3}
    return sorted(
        all_scored,
        key=lambda x: (risk_order.get(x["risk_level"], 4), x["score"])
    )


def leaderboard():
    """Top students by milestone progress + engagement for Discord posting."""
    conn = get_db()
    try:
        students = conn.execute(
            "SELECT id, name, current_milestone, start_date, tier "
            "FROM students WHERE status IN ('active', 'at_risk', 'graduated') "
            "ORDER BY name"
        ).fetchall()
    finally:
        conn.close()

    scored = []
    for s in students:
        score_data = calculate_health_score(s["id"])
        if not score_data:
            continue

        ms_index = (MILESTONE_ORDER.index(s["current_milestone"])
                    if s["current_milestone"] in MILESTONE_ORDER else 0)

        scored.append({
            "name": s["name"],
            "tier": s["tier"],
            "current_milestone": s["current_milestone"],
            "milestone_index": ms_index,
            "health_score": score_data["score"],
            "engagement": score_data["breakdown"]["engagement"],
            "composite": ms_index * 10 + score_data["score"],
        })

    scored.sort(key=lambda x: x["composite"], reverse=True)

    lines = [
        "=== STUDENT LEADERBOARD ===",
        "",
    ]
    for rank, s in enumerate(scored, 1):
        ms_display = s["current_milestone"].replace("_", " ").title()
        lines.append(
            f"  {rank}. {s['name']} (Tier {s['tier']}) -- "
            f"{ms_display} | Health: {s['health_score']} | "
            f"Engagement: {s['engagement']}/30"
        )

    return "\n".join(lines), scored


def engagement_digest():
    """Daily engagement summary as JSON for CEO brain."""
    scan_result = daily_scan()

    conn = get_db()
    try:
        total_students = conn.execute(
            "SELECT COUNT(*) as cnt FROM students WHERE status != 'churned'"
        ).fetchone()["cnt"]

        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Today's signals
        today_signals = conn.execute("""
            SELECT signal_type, COUNT(*) as cnt
            FROM engagement_signals WHERE date = ?
            GROUP BY signal_type ORDER BY cnt DESC
        """, (today,)).fetchall()

        # Queued touchpoints
        pending = conn.execute("""
            SELECT COUNT(*) as cnt FROM touchpoints WHERE status = 'queued'
        """).fetchone()["cnt"]

    finally:
        conn.close()

    risk_counts = {}
    for r in scan_result["results"]:
        level = r["risk_level"]
        risk_counts[level] = risk_counts.get(level, 0) + 1

    return {
        "date": today,
        "total_students": total_students,
        "scanned": scan_result["scanned"],
        "risk_distribution": risk_counts,
        "todays_signals": {s["signal_type"]: s["cnt"] for s in today_signals},
        "interventions_queued": len(scan_result["interventions"]),
        "total_pending_touchpoints": pending,
        "at_risk_students": [
            {"name": r["name"], "score": r["score"], "risk": r["risk_level"]}
            for r in scan_result["results"]
            if r["risk_level"] in ("yellow", "orange", "red", "critical")
        ],
    }


def graduation_check():
    """Find students approaching Day 75-90 who may be ready for graduation."""
    conn = get_db()
    try:
        students = conn.execute(
            "SELECT * FROM students WHERE status IN ('active', 'at_risk')"
        ).fetchall()

        approaching = []
        for s in students:
            try:
                start = datetime.strptime(s["start_date"], "%Y-%m-%d")
            except (ValueError, TypeError):
                continue

            days_in = (datetime.utcnow() - start).days

            if 75 <= days_in <= 90:
                ms_index = (MILESTONE_ORDER.index(s["current_milestone"])
                            if s["current_milestone"] in MILESTONE_ORDER
                            else 0)

                # Check if already has graduation flow
                existing_flow = conn.execute("""
                    SELECT id FROM graduation_flows
                    WHERE student_id = ? AND status = 'active'
                """, (s["id"],)).fetchone()

                approaching.append({
                    "name": s["name"],
                    "tier": s["tier"],
                    "days_in_program": days_in,
                    "current_milestone": s["current_milestone"],
                    "milestone_index": ms_index,
                    "total_milestones": len(MILESTONE_ORDER),
                    "health_score": s["health_score"],
                    "graduation_flow_exists": existing_flow is not None,
                    "recommendation": _graduation_recommendation(
                        ms_index, days_in, s["health_score"]
                    ),
                })

        return sorted(approaching, key=lambda x: x["days_in_program"],
                       reverse=True)
    finally:
        conn.close()


def _graduation_recommendation(ms_index, days_in, health_score):
    """Recommend graduation action based on progress."""
    total = len(MILESTONE_ORDER)
    progress_pct = ms_index / (total - 1) if total > 1 else 0

    if progress_pct >= 0.8 and health_score >= 70:
        return "Ready for graduation flow. Present backend offer."
    elif progress_pct >= 0.6:
        return ("On track but not complete. Extend program 30 days and "
                "push toward next milestone.")
    elif progress_pct >= 0.4:
        return ("Behind schedule. Schedule intensive 1-on-1 sessions to "
                "accelerate progress.")
    else:
        return ("Significantly behind. Evaluate if student needs a full "
                "restart or if coaching approach needs adjusting.")


# ── CLI Handlers ─────────────────────────────────────────────────────────────

def cli_daily_scan(args):
    result = daily_scan()
    print(f"[student_health] Scanned {result['scanned']} students "
          f"at {result['scan_time']}")
    print()

    for r in result["results"]:
        b = r["breakdown"]
        risk = r["risk_level"].upper()
        print(f"  {r['name']:<20} {r['score']:>3}/100  [{risk:<8}]  "
              f"MP:{b['milestone_progress']} ENG:{b['engagement']} "
              f"MOM:{b['momentum']} MOD:{b['mood']} REC:{b['recency']}")

    if result["interventions"]:
        print()
        print(f"  Interventions queued: {len(result['interventions'])}")
        for i in result["interventions"]:
            print(f"    [{i['type']}] {i['student']}: {i['message'][:80]}...")


def cli_health_report(args):
    print(health_report())


def cli_student_detail(args):
    detail = get_student_detail(args.name)
    if not detail:
        print(f"[student_health] Student '{args.name}' not found.",
              file=sys.stderr)
        sys.exit(1)
    print(json.dumps(detail, indent=2, default=str))


def cli_at_risk(args):
    at_risk = get_at_risk()
    if not at_risk:
        print("[student_health] No at-risk students. All green.")
        return

    for r in at_risk:
        intervention = r.get("recommended_intervention") or {}
        print(f"  [{r['risk_level'].upper():<8}] {r['name']:<20} "
              f"score={r['score']:>3}  milestone={r['current_milestone']}")
        if intervention.get("message"):
            print(f"    -> {intervention['message'][:100]}")
    print()
    print(json.dumps(at_risk, indent=2, default=str))


def cli_log_signal(args):
    try:
        result = log_signal(
            args.student, args.type, args.channel, args.value,
            args.date, args.notes
        )
        print(f"[student_health] Logged: {result['student']} -- "
              f"{result['signal']} via {result['channel']} on {result['date']}")
    except ValueError as e:
        print(f"[student_health] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_leaderboard(args):
    text, _ = leaderboard()
    print(text)


def cli_engagement_digest(args):
    digest = engagement_digest()
    print(json.dumps(digest, indent=2))


def cli_graduation_check(args):
    approaching = graduation_check()
    if not approaching:
        print("[student_health] No students in Day 75-90 window.")
        return

    print("=== GRADUATION CHECK (Day 75-90) ===")
    print()
    for s in approaching:
        ms_display = s["current_milestone"].replace("_", " ").title()
        print(f"  {s['name']} (Tier {s['tier']}) -- Day {s['days_in_program']}")
        print(f"    Milestone: {ms_display} "
              f"({s['milestone_index']}/{s['total_milestones']})")
        print(f"    Health: {s['health_score']} | "
              f"Flow exists: {s['graduation_flow_exists']}")
        print(f"    -> {s['recommendation']}")
        print()


# ── CLI Parser ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Student Health Monitor -- multi-dimensional scoring, "
                    "at-risk detection, engagement tracking"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # daily-scan
    p_scan = subparsers.add_parser(
        "daily-scan", help="Score all students and queue interventions"
    )
    p_scan.set_defaults(func=cli_daily_scan)

    # health-report
    p_hr = subparsers.add_parser(
        "health-report", help="Formatted health report table"
    )
    p_hr.set_defaults(func=cli_health_report)

    # student-detail
    p_sd = subparsers.add_parser(
        "student-detail", help="Full health detail for one student"
    )
    p_sd.add_argument("--name", required=True, help="Student name")
    p_sd.set_defaults(func=cli_student_detail)

    # at-risk
    p_ar = subparsers.add_parser(
        "at-risk", help="List at-risk students with interventions"
    )
    p_ar.set_defaults(func=cli_at_risk)

    # log-signal
    p_sig = subparsers.add_parser(
        "log-signal", help="Log an engagement signal"
    )
    p_sig.add_argument("--student", required=True, help="Student name")
    p_sig.add_argument(
        "--type", required=True, choices=VALID_SIGNAL_TYPES,
        help="Signal type"
    )
    p_sig.add_argument(
        "--channel", default="unknown",
        help="Channel (discord, call, platform, etc.)"
    )
    p_sig.add_argument("--value", default="true", help="Signal value")
    p_sig.add_argument("--date", default=None, help="Date (YYYY-MM-DD)")
    p_sig.add_argument("--notes", default=None, help="Optional notes")
    p_sig.set_defaults(func=cli_log_signal)

    # leaderboard
    p_lb = subparsers.add_parser(
        "leaderboard", help="Top students by progress + engagement"
    )
    p_lb.set_defaults(func=cli_leaderboard)

    # engagement-digest
    p_ed = subparsers.add_parser(
        "engagement-digest", help="Daily engagement summary (JSON)"
    )
    p_ed.set_defaults(func=cli_engagement_digest)

    # graduation-check
    p_gc = subparsers.add_parser(
        "graduation-check", help="Students approaching Day 75-90"
    )
    p_gc.set_defaults(func=cli_graduation_check)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
