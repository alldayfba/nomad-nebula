#!/usr/bin/env python3
"""
Script: student_saas_sync.py
Purpose: Sync student progress between local student_tracker DB and 247profits.org SaaS.
         Pushes milestones/health scores to Supabase so students see progress in their dashboard.
         Pulls module completion, lesson progress, and coaching call data back to enrich health scoring.

         247profits.org Supabase tables used:
           Push: academy_milestones, student_profiles, student_program_level
           Pull: academy_lesson_progress, coaching_call_attendees, student_sales, activity_log
           Match: users (by email)

Inputs:  CLI subcommands
Outputs: Sync reports, activity signals for student_health_monitor

CLI:
    python execution/student_saas_sync.py push-milestones          # Push local milestones → Supabase
    python execution/student_saas_sync.py pull-activity             # Pull platform activity → local signals
    python execution/student_saas_sync.py push-students             # Create/update student profiles on SaaS
    python execution/student_saas_sync.py sync                      # Full bidirectional sync
    python execution/student_saas_sync.py status                    # Show sync status for all students
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("[student_saas_sync] Error: requests not installed", file=sys.stderr)
    sys.exit(1)

DB_PATH = Path(__file__).parent.parent / ".tmp" / "coaching" / "students.db"

# 247profits.org Supabase (STUDENT platform — separate from 247growth agency dashboard)
SUPABASE_URL = os.getenv("STUDENT_SAAS_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("STUDENT_SAAS_SUPABASE_KEY", "")

# Fallback to generic vars if student-specific not set
if not SUPABASE_URL:
    SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
if not SUPABASE_KEY:
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Milestone → SaaS program level mapping
MILESTONE_TO_LEVEL = {
    "enrolled": "beginner",
    "niche_selected": "beginner",
    "product_selected": "intermediate",
    "supplier_contacted": "intermediate",
    "sample_received": "intermediate",
    "listing_created": "advanced",
    "listing_live": "advanced",
    "first_sale": "advanced",
    "profitable_month": "expert",
    "10k_month": "master",
}


# ── Database ────────────────────────────────────────────────────────────────

def get_db():
    if not DB_PATH.exists():
        print("[student_saas_sync] Error: Student DB not found.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── Supabase Client ─────────────────────────────────────────────────────────

def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _get(table, params=None):
    """GET from Supabase REST API."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(), params=params or {}, timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def _upsert(table, data):
    """UPSERT to Supabase REST API."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    headers = _headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers, json=data, timeout=10
        )
        if resp.status_code in (200, 201):
            return resp.json()
        print(f"[saas_sync] UPSERT {table}: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[saas_sync] Error: {e}", file=sys.stderr)
        return None


def _patch(table, match_params, data):
    """PATCH (update) rows matching params."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    headers = _headers()
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers, params=match_params, json=data, timeout=10
        )
        if resp.status_code in (200, 204):
            return True
        print(f"[saas_sync] PATCH {table}: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[saas_sync] Error: {e}", file=sys.stderr)
        return None


# ── SaaS User Lookup ────────────────────────────────────────────────────────

def _get_saas_users():
    """Get all users from 247profits.org Supabase."""
    users = _get("users", {"select": "id,email,full_name,role,student_tier,is_active"})
    if not users:
        return {}
    return {u["email"]: u for u in users if u.get("email")}


# ── Push: Students → SaaS ──────────────────────────────────────────────────

def push_students():
    """Push all student progress data to 247profits.org activity_log.

    Uses activity_log table (user_id is optional) so we don't need SaaS accounts.
    The CSM agent and Sabbo can track all students from the SaaS dashboard.
    Each sync overwrites the previous snapshot with fresh data.
    """
    conn = get_db()
    try:
        students = conn.execute("""
            SELECT s.*,
                   (SELECT score FROM health_snapshots WHERE student_id = s.id ORDER BY date DESC LIMIT 1) as latest_health,
                   (SELECT risk_level FROM health_snapshots WHERE student_id = s.id ORDER BY date DESC LIMIT 1) as latest_risk,
                   (SELECT GROUP_CONCAT(m.milestone || ':' || m.status, ',')
                    FROM milestones m WHERE m.student_id = s.id) as milestone_summary,
                   (SELECT COUNT(*) FROM engagement_signals WHERE student_id = s.id AND date >= date('now', '-14 days')) as recent_signals
            FROM students s
            WHERE s.status != 'churned'
        """).fetchall()

        if not students:
            print("[saas_sync] No students to sync.")
            return []

        pushed = []
        for s in students:
            milestones_raw = s["milestone_summary"] or ""
            milestone_map = {}
            for pair in milestones_raw.split(","):
                if ":" in pair:
                    ms, status = pair.split(":", 1)
                    milestone_map[ms.strip()] = status.strip()

            details = {
                "student_name": s["name"],
                "email": s["email"],
                "discord_user_id": s["discord_user_id"],
                "tier": s["tier"],
                "start_date": s["start_date"],
                "target_date": s["target_date"],
                "current_milestone": s["current_milestone"],
                "status": s["status"],
                "health_score": s["latest_health"] or s["health_score"],
                "risk_level": s["latest_risk"] or "unknown",
                "milestones": milestone_map,
                "recent_signals": s["recent_signals"],
                "days_in_program": (datetime.utcnow() - datetime.strptime(s["start_date"], "%Y-%m-%d")).days if s["start_date"] else 0,
                "synced_at": datetime.utcnow().isoformat(),
            }

            result = _upsert("activity_log", {
                "action": "csm_student_sync",
                "entity_type": "student",
                "entity_id": s["discord_user_id"] or str(s["id"]),
                "details": json.dumps(details),
            })
            if result:
                pushed.append(s["name"])

        print(f"[saas_sync] Pushed {len(pushed)}/{len(students)} students to SaaS activity_log")
        return pushed
    finally:
        conn.close()


def push_milestones():
    """Push milestone progress to 247profits.org academy_milestones table."""
    conn = get_db()
    try:
        students = conn.execute("""
            SELECT s.id, s.name, s.email, s.current_milestone, s.status, s.health_score,
                   s.start_date, s.target_date, s.tier
            FROM students s
            WHERE s.status IN ('active', 'at_risk', 'graduated', 'continuation', 'mastermind')
        """).fetchall()

        if not students:
            print("[saas_sync] No students to sync.")
            return []

        saas_users = _get_saas_users()
        pushed = []

        for s in students:
            email = s["email"]
            if not email or email not in saas_users:
                continue

            user_id = saas_users[email]["id"]

            # Get all milestones for this student
            milestones = conn.execute("""
                SELECT milestone, status, started_date, completed_date, days_on_milestone
                FROM milestones WHERE student_id = ? ORDER BY id
            """, (s["id"],)).fetchall()

            for m in milestones:
                if m["status"] == "completed" and m["completed_date"]:
                    _upsert("academy_milestones", {
                        "user_id": user_id,
                        "milestone_key": m["milestone"],
                        "status": "completed",
                        "completed_at": m["completed_date"],
                        "days_taken": m["days_on_milestone"] or 0,
                    })

            # Update program level
            level = MILESTONE_TO_LEVEL.get(s["current_milestone"], "beginner")
            _upsert("student_program_level", {
                "user_id": user_id,
                "level": level,
                "current_milestone": s["current_milestone"],
                "updated_at": datetime.utcnow().isoformat(),
            })

            pushed.append(s["name"])

        print(f"[saas_sync] Pushed milestones for {len(pushed)} students")
        for name in pushed:
            print(f"  ✓ {name}")
        return pushed
    finally:
        conn.close()


# ── Pull: SaaS → Local ──────────────────────────────────────────────────────

def pull_activity():
    """Pull platform activity from 247profits.org to enrich local engagement signals.

    Checks actual SaaS tables:
    - academy_lesson_progress — course module completion
    - coaching_call_attendees — call attendance
    - student_sales — revenue reported through SaaS
    - activity_log — general platform activity
    """
    conn = get_db()
    try:
        students = conn.execute(
            "SELECT id, name, email FROM students WHERE status IN ('active', 'at_risk') AND email IS NOT NULL"
        ).fetchall()

        if not students:
            print("[saas_sync] No active students with emails.")
            return []

        saas_users = _get_saas_users()
        signals_logged = []
        today = datetime.utcnow().strftime("%Y-%m-%d")
        week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        now_iso = datetime.utcnow().isoformat()

        for s in students:
            email = s["email"]
            if not email or email not in saas_users:
                continue

            user_id = saas_users[email]["id"]

            # 1. Lesson progress (last 7 days)
            progress = _get("academy_lesson_progress", {
                "user_id": f"eq.{user_id}",
                "completed_at": f"gte.{week_ago}",
                "select": "lesson_id,completed_at",
            })

            if progress and len(progress) > 0:
                # Check if we already logged this today
                existing = conn.execute("""
                    SELECT id FROM engagement_signals
                    WHERE student_id = ? AND signal_type = 'module_completed'
                    AND channel = 'saas' AND date = ?
                """, (s["id"], today)).fetchone()

                if not existing:
                    conn.execute("""
                        INSERT INTO engagement_signals
                        (student_id, signal_type, channel, value, date, notes, created_at)
                        VALUES (?, 'module_completed', 'saas', ?, ?, ?, ?)
                    """, (s["id"], str(len(progress)), today,
                          f"Completed {len(progress)} lessons on SaaS this week", now_iso))
                    signals_logged.append(f"{s['name']}: {len(progress)} lessons completed")

            # 2. Coaching call attendance (last 7 days)
            attendance = _get("coaching_call_attendees", {
                "user_id": f"eq.{user_id}",
                "created_at": f"gte.{week_ago}",
                "select": "coaching_call_id,created_at",
            })

            if attendance and len(attendance) > 0:
                existing = conn.execute("""
                    SELECT id FROM engagement_signals
                    WHERE student_id = ? AND signal_type = 'call_attended'
                    AND channel = 'saas' AND date = ?
                """, (s["id"], today)).fetchone()

                if not existing:
                    conn.execute("""
                        INSERT INTO engagement_signals
                        (student_id, signal_type, channel, value, date, notes, created_at)
                        VALUES (?, 'call_attended', 'saas', ?, ?, ?, ?)
                    """, (s["id"], str(len(attendance)), today,
                          f"Attended {len(attendance)} coaching calls via SaaS", now_iso))
                    signals_logged.append(f"{s['name']}: {len(attendance)} calls attended")

            # 3. Sales reported through SaaS
            sales = _get("student_sales", {
                "user_id": f"eq.{user_id}",
                "created_at": f"gte.{week_ago}",
                "select": "amount,created_at",
            })

            if sales and len(sales) > 0:
                total_revenue = sum(float(sale.get("amount", 0)) for sale in sales)
                existing = conn.execute("""
                    SELECT id FROM engagement_signals
                    WHERE student_id = ? AND signal_type = 'revenue_milestone'
                    AND channel = 'saas' AND date = ?
                """, (s["id"], today)).fetchone()

                if not existing:
                    conn.execute("""
                        INSERT INTO engagement_signals
                        (student_id, signal_type, channel, value, date, notes, created_at)
                        VALUES (?, 'revenue_milestone', 'saas', ?, ?, ?, ?)
                    """, (s["id"], str(total_revenue), today,
                          f"${total_revenue:.2f} in sales reported on SaaS", now_iso))
                    signals_logged.append(f"{s['name']}: ${total_revenue:.2f} sales")

            # 4. General platform activity (logins)
            activity = _get("activity_log", {
                "user_id": f"eq.{user_id}",
                "created_at": f"gte.{week_ago}",
                "select": "action,created_at",
                "limit": "10",
            })

            if activity and len(activity) > 0:
                existing = conn.execute("""
                    SELECT id FROM engagement_signals
                    WHERE student_id = ? AND signal_type = 'platform_login'
                    AND channel = 'saas' AND date = ?
                """, (s["id"], today)).fetchone()

                if not existing:
                    conn.execute("""
                        INSERT INTO engagement_signals
                        (student_id, signal_type, channel, value, date, notes, created_at)
                        VALUES (?, 'platform_login', 'saas', ?, ?, ?, ?)
                    """, (s["id"], str(len(activity)), today,
                          f"{len(activity)} platform activities on SaaS this week", now_iso))
                    signals_logged.append(f"{s['name']}: {len(activity)} platform activities")

        conn.commit()
        print(f"[saas_sync] Pulled {len(signals_logged)} activity signals from SaaS")
        for sig in signals_logged:
            print(f"  ← {sig}")
        return signals_logged
    finally:
        conn.close()


# ── Full Sync ────────────────────────────────────────────────────────────────

def full_sync():
    """Bidirectional sync: push students + milestones, pull activity."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[saas_sync] ⚠ Supabase credentials not configured.")
        print("  Set STUDENT_SAAS_SUPABASE_URL and STUDENT_SAAS_SUPABASE_KEY in .env")
        print("  (These should point to the 247profits.org Supabase, NOT the 247growth agency dashboard)")
        return {"pushed": 0, "pulled": 0}

    print("[saas_sync] === FULL SYNC with 247profits.org ===")
    print(f"  Supabase: {SUPABASE_URL}")
    print()

    print("── Push: Student Profiles → SaaS ──")
    pushed_profiles = push_students()
    print()

    print("── Push: Milestones → SaaS ──")
    pushed_ms = push_milestones()
    print()

    print("── Pull: SaaS Activity → Local ──")
    pulled = pull_activity()
    print()

    total_pushed = len(pushed_profiles) + len(pushed_ms)
    print(f"[saas_sync] Sync complete. Pushed: {total_pushed}, Pulled: {len(pulled)} signals")
    return {"pushed": total_pushed, "pulled": len(pulled)}


def sync_status():
    """Show sync status for all students."""
    conn = get_db()
    try:
        students = conn.execute("""
            SELECT s.name, s.email, s.current_milestone, s.status, s.health_score,
                   (SELECT MAX(date) FROM engagement_signals
                    WHERE student_id = s.id AND channel = 'saas') as last_saas_activity,
                   (SELECT COUNT(*) FROM engagement_signals
                    WHERE student_id = s.id AND channel = 'saas') as total_saas_signals
            FROM students s
            WHERE s.status IN ('active', 'at_risk', 'graduated', 'continuation', 'mastermind')
            ORDER BY s.name
        """).fetchall()

        if not students:
            print("[saas_sync] No students.")
            return

        print("═══ STUDENT SAAS SYNC STATUS ═══")
        print(f"  Supabase: {SUPABASE_URL or 'NOT CONFIGURED'}")
        print()
        print(f"{'Student':<20} {'Email':<30} {'Milestone':<18} {'Last SaaS':>12} {'Signals':>8}")
        print("─" * 92)

        for s in students:
            last_saas = s["last_saas_activity"] or "never"
            email_display = (s["email"] or "no email")[:28]
            print(
                f"{s['name']:<20} {email_display:<30} "
                f"{s['current_milestone']:<18} {last_saas:>12} {s['total_saas_signals']:>8}"
            )

        with_email = sum(1 for s in students if s["email"])
        with_saas = sum(1 for s in students if s["total_saas_signals"] and s["total_saas_signals"] > 0)
        print()
        print(f"Total: {len(students)} | With email: {with_email} | SaaS active: {with_saas}")

        # Check SaaS connectivity
        saas_users = _get_saas_users()
        if saas_users is None:
            print()
            print("⚠ Cannot connect to 247profits.org Supabase")
            print("  Check STUDENT_SAAS_SUPABASE_URL and STUDENT_SAAS_SUPABASE_KEY in .env")
        else:
            matched = sum(1 for s in students if s["email"] and s["email"] in saas_users)
            print(f"  SaaS users matched: {matched}/{with_email}")
            if matched < with_email:
                print(f"  ⚠ {with_email - matched} students have emails but no SaaS account")
                print("    They need to register at 247profits.org or be created via push-students")

    finally:
        conn.close()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Student SaaS Sync — bidirectional progress sync with 247profits.org"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("push-students", help="Push student profiles to SaaS")
    subparsers.add_parser("push-milestones", help="Push milestones to SaaS")
    subparsers.add_parser("pull-activity", help="Pull SaaS activity to local signals")
    subparsers.add_parser("sync", help="Full bidirectional sync")
    subparsers.add_parser("status", help="Show sync status")

    args = parser.parse_args()

    commands = {
        "push-students": push_students,
        "push-milestones": push_milestones,
        "pull-activity": pull_activity,
        "sync": full_sync,
        "status": sync_status,
    }

    func = commands.get(args.command)
    if func:
        func()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
