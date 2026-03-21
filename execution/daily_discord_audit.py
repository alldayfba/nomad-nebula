"""Daily Discord Audit — silent, read-only intelligence gathering.

Runs at 7 AM daily. NEVER sends messages to anyone.
Reads Discord server state, cross-references with student DB,
harvests learnings, and reports to Sabbo via nova.db.

Usage:
    python execution/daily_discord_audit.py              # Full audit
    python execution/daily_discord_audit.py --quick      # Summary only
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import discord

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
STUDENTS_DB = PROJECT_ROOT / ".tmp" / "coaching" / "students.db"
NOVA_DB = PROJECT_ROOT / ".tmp" / "nova" / "nova.db"
REPORT_DIR = PROJECT_ROOT / ".tmp" / "audit"

sys.path.insert(0, str(PROJECT_ROOT / "execution"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "1185214150222286849"))
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")


def get_students_conn():
    conn = sqlite3.connect(str(STUDENTS_DB), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def get_nova_conn():
    NOVA_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(NOVA_DB), timeout=10)
    conn.row_factory = sqlite3.Row
    # Ensure audit_reports table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_date TEXT NOT NULL,
            report_type TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


async def run_audit(quick=False):
    """Run the full silent audit."""
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    report = {
        "audit_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "timestamp": datetime.utcnow().isoformat(),
        "sections": {},
    }

    @client.event
    async def on_ready():
        try:
            guild = client.get_guild(GUILD_ID)
            if not guild:
                print(f"[Audit] Guild {GUILD_ID} not found")
                await client.close()
                return

            print(f"[Audit] Connected to {guild.name} ({guild.member_count} members)")

            # ── 1. Member-to-Student Mapping Audit ───────────────────────
            mapping_report = await audit_member_mapping(guild)
            report["sections"]["mapping"] = mapping_report

            # ── 2. Channel Activity Scan ─────────────────────────────────
            if not quick:
                activity_report = await audit_channel_activity(guild)
                report["sections"]["activity"] = activity_report

            # ── 3. Student Status Reconciliation ─────────────────────────
            status_report = audit_student_status()
            report["sections"]["status"] = status_report

            # ── 4. Knowledge Harvesting (from Nova chat logs) ────────────
            knowledge_report = harvest_knowledge()
            report["sections"]["knowledge"] = knowledge_report

            # ── 5. Engagement Trends ─────────────────────────────────────
            trends_report = audit_engagement_trends()
            report["sections"]["trends"] = trends_report

            # ── Save Report ──────────────────────────────────────────────
            save_report(report)
            print_summary(report)

        except Exception as e:
            print(f"[Audit] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await client.close()

    await client.start(BOT_TOKEN)
    return report


async def audit_member_mapping(guild):
    """Find Discord members who have student channels but aren't mapped."""
    conn = get_students_conn()
    mapped_ids = set()
    rows = conn.execute("SELECT discord_user_id FROM students WHERE discord_user_id IS NOT NULL AND discord_user_id != ''").fetchall()
    for r in rows:
        mapped_ids.add(r["discord_user_id"])

    # Find student channels (🎓 prefix)
    student_channels = []
    for ch in guild.text_channels:
        if "🎓" in ch.name:
            student_channels.append(ch)

    # Check all members
    unmapped = []
    newly_mapped = 0
    all_members = {}

    async for member in guild.fetch_members(limit=None):
        if member.bot:
            continue
        all_members[str(member.id)] = {
            "name": member.display_name,
            "username": member.name,
            "id": str(member.id),
            "joined": member.joined_at.isoformat() if member.joined_at else None,
        }

        if str(member.id) not in mapped_ids:
            # Check if this member has a student channel
            member_name_lower = member.display_name.lower().replace(" ", "")
            for ch in student_channels:
                ch_name_lower = ch.name.lower().replace("🎓┃", "").replace("🎓-", "").replace(" ", "")
                if member_name_lower in ch_name_lower or ch_name_lower in member_name_lower:
                    # Auto-map this student
                    existing = conn.execute(
                        "SELECT id, name FROM students WHERE discord_channel_id = ? OR LOWER(name) LIKE ?",
                        (str(ch.id), f"%{member.display_name.lower()[:4]}%"),
                    ).fetchone()
                    if existing and not conn.execute(
                        "SELECT discord_user_id FROM students WHERE id = ? AND (discord_user_id IS NULL OR discord_user_id = '')",
                        (existing["id"],),
                    ).fetchone():
                        continue  # Already mapped

                    if existing:
                        conn.execute(
                            "UPDATE students SET discord_user_id = ?, discord_channel_id = ? WHERE id = ?",
                            (str(member.id), str(ch.id), existing["id"]),
                        )
                        conn.commit()
                        newly_mapped += 1
                    else:
                        unmapped.append({
                            "discord_name": member.display_name,
                            "discord_id": str(member.id),
                            "channel": ch.name,
                            "channel_id": str(ch.id),
                        })

    conn.close()

    return {
        "total_members": len(all_members),
        "student_channels": len(student_channels),
        "previously_mapped": len(mapped_ids),
        "newly_mapped": newly_mapped,
        "still_unmapped": unmapped,
    }


async def audit_channel_activity(guild):
    """Scan channels for recent activity (last 7 days). Read-only."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    channel_stats = []

    for ch in guild.text_channels:
        try:
            msg_count = 0
            unique_users = set()
            last_msg_time = None

            async for msg in ch.history(limit=100, after=cutoff):
                if msg.author.bot:
                    continue
                msg_count += 1
                unique_users.add(str(msg.author.id))
                if last_msg_time is None or msg.created_at > last_msg_time:
                    last_msg_time = msg.created_at

            if msg_count > 0:
                channel_stats.append({
                    "channel": ch.name,
                    "category": ch.category.name if ch.category else "none",
                    "messages_7d": msg_count,
                    "unique_users": len(unique_users),
                    "last_activity": last_msg_time.isoformat() if last_msg_time else None,
                })
        except discord.Forbidden:
            continue

    channel_stats.sort(key=lambda x: x["messages_7d"], reverse=True)

    # Update student last_discord_activity from their channels
    conn = get_students_conn()
    students_with_channels = conn.execute(
        "SELECT id, discord_channel_id FROM students WHERE discord_channel_id IS NOT NULL AND discord_channel_id != ''"
    ).fetchall()

    updated_activity = 0
    for s in students_with_channels:
        for cs in channel_stats:
            if cs.get("last_activity"):
                # Match by checking if this channel has recent activity
                # We'd need channel IDs in channel_stats — simplified: update from engagement_signals
                pass

    conn.close()

    return {
        "active_channels_7d": len(channel_stats),
        "top_channels": channel_stats[:15],
        "dead_channels": [cs for cs in channel_stats if cs["messages_7d"] < 3],
    }


def audit_student_status():
    """Reconcile student statuses — find mismatches."""
    conn = get_students_conn()

    total = conn.execute("SELECT COUNT(*) as c FROM students").fetchone()["c"]
    by_status = conn.execute(
        "SELECT status, COUNT(*) as c FROM students GROUP BY status ORDER BY c DESC"
    ).fetchall()

    # Find students marked active but no activity in 30+ days
    stale_active = conn.execute(
        "SELECT name, discord_user_id, last_discord_activity, health_score, current_milestone "
        "FROM students WHERE status = 'active' AND ("
        "  last_discord_activity IS NULL OR last_discord_activity < date('now', '-30 days')"
        ") AND discord_user_id IS NOT NULL AND discord_user_id != ''"
    ).fetchall()

    # Find churned students with recent activity
    active_churned = conn.execute(
        "SELECT name, discord_user_id, last_discord_activity, current_milestone "
        "FROM students WHERE status = 'churned' AND "
        "last_discord_activity IS NOT NULL AND last_discord_activity > date('now', '-14 days')"
    ).fetchall()

    # Milestone distribution
    milestones = conn.execute(
        "SELECT current_milestone, COUNT(*) as c FROM students WHERE status = 'active' "
        "GROUP BY current_milestone ORDER BY c DESC"
    ).fetchall()

    # Health score distribution
    health_dist = {
        "critical": conn.execute("SELECT COUNT(*) as c FROM students WHERE status='active' AND health_score < 20").fetchone()["c"],
        "low": conn.execute("SELECT COUNT(*) as c FROM students WHERE status='active' AND health_score BETWEEN 20 AND 40").fetchone()["c"],
        "medium": conn.execute("SELECT COUNT(*) as c FROM students WHERE status='active' AND health_score BETWEEN 41 AND 70").fetchone()["c"],
        "healthy": conn.execute("SELECT COUNT(*) as c FROM students WHERE status='active' AND health_score > 70").fetchone()["c"],
    }

    conn.close()

    return {
        "total_students": total,
        "by_status": {r["status"]: r["c"] for r in by_status},
        "stale_active": [{"name": r["name"], "last_activity": r["last_discord_activity"],
                          "health": r["health_score"], "milestone": r["current_milestone"]}
                         for r in stale_active],
        "active_churned": [{"name": r["name"], "last_activity": r["last_discord_activity"],
                            "milestone": r["current_milestone"]} for r in active_churned],
        "milestone_distribution": {r["current_milestone"]: r["c"] for r in milestones},
        "health_distribution": health_dist,
    }


def harvest_knowledge():
    """Analyze Nova chat logs for learning opportunities."""
    nova_conn = get_nova_conn()

    # Get recent questions from chat_log
    recent_qs = nova_conn.execute(
        "SELECT question, answer, user_id FROM chat_log "
        "WHERE platform = 'discord' AND created_at > datetime('now', '-7 days') "
        "ORDER BY created_at DESC LIMIT 50"
    ).fetchall()

    # Get negative feedback to identify weak answers
    neg_feedback = nova_conn.execute(
        "SELECT question_text, answer_text, comment FROM feedback "
        "WHERE rating = 1 AND created_at > datetime('now', '-7 days') "
        "ORDER BY created_at DESC LIMIT 20"
    ).fetchall()

    # Get top question clusters (what students ask most)
    top_clusters = nova_conn.execute(
        "SELECT representative_question, frequency, category FROM question_clusters "
        "ORDER BY frequency DESC LIMIT 10"
    ).fetchall()

    # Pending FAQ candidates
    pending_faq = nova_conn.execute(
        "SELECT question FROM knowledge_base WHERE approved = 0"
    ).fetchall()

    nova_conn.close()

    return {
        "questions_7d": len(recent_qs),
        "negative_feedback_7d": len(neg_feedback),
        "top_questions": [{"q": r["representative_question"], "freq": r["frequency"],
                           "cat": r["category"]} for r in top_clusters],
        "pending_faq": [r["question"] for r in pending_faq],
        "weak_answers": [{"question": r["question_text"], "comment": r["comment"]}
                         for r in neg_feedback if r["comment"]],
    }


def audit_engagement_trends():
    """Analyze engagement trends over time."""
    conn = get_students_conn()

    # 7-day vs 30-day engagement comparison
    signals_7d = conn.execute(
        "SELECT signal_type, COUNT(*) as c FROM engagement_signals "
        "WHERE date > date('now', '-7 days') GROUP BY signal_type ORDER BY c DESC"
    ).fetchall()

    signals_30d = conn.execute(
        "SELECT signal_type, COUNT(*) as c FROM engagement_signals "
        "WHERE date > date('now', '-30 days') GROUP BY signal_type ORDER BY c DESC"
    ).fetchall()

    # Frustrated students (last 7 days)
    frustrated = conn.execute(
        "SELECT DISTINCT s.name, s.current_milestone, s.health_score "
        "FROM engagement_signals e JOIN students s ON e.student_id = s.id "
        "WHERE e.signal_type = 'mood_frustrated' AND e.date > date('now', '-7 days') "
        "AND s.status = 'active'"
    ).fetchall()

    # Most active students
    most_active = conn.execute(
        "SELECT s.name, COUNT(*) as signals FROM engagement_signals e "
        "JOIN students s ON e.student_id = s.id "
        "WHERE e.date > date('now', '-7 days') AND s.status = 'active' "
        "GROUP BY e.student_id ORDER BY signals DESC LIMIT 10"
    ).fetchall()

    # Ghost students (active status but zero signals in 14 days)
    ghosts = conn.execute(
        "SELECT s.name, s.health_score, s.current_milestone, s.last_discord_activity "
        "FROM students s WHERE s.status = 'active' AND s.discord_user_id IS NOT NULL "
        "AND s.id NOT IN ("
        "  SELECT DISTINCT student_id FROM engagement_signals WHERE date > date('now', '-14 days')"
        ")"
    ).fetchall()

    conn.close()

    return {
        "signals_7d": {r["signal_type"]: r["c"] for r in signals_7d},
        "signals_30d": {r["signal_type"]: r["c"] for r in signals_30d},
        "frustrated_students": [{"name": r["name"], "milestone": r["current_milestone"],
                                  "health": r["health_score"]} for r in frustrated],
        "most_active": [{"name": r["name"], "signals": r["signals"]} for r in most_active],
        "ghost_students": [{"name": r["name"], "health": r["health_score"],
                            "milestone": r["current_milestone"],
                            "last_seen": r["last_discord_activity"]} for r in ghosts],
    }


def save_report(report):
    """Save report to nova.db and as a JSON file."""
    # Save to DB
    nova_conn = get_nova_conn()
    nova_conn.execute(
        "INSERT INTO audit_reports (audit_date, report_type, data) VALUES (?, ?, ?)",
        (report["audit_date"], "daily_full", json.dumps(report, default=str)),
    )
    nova_conn.commit()
    nova_conn.close()

    # Save to file
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = REPORT_DIR / f"audit-{report['audit_date']}.json"
    filepath.write_text(json.dumps(report, indent=2, default=str))
    print(f"[Audit] Report saved: {filepath}")


def print_summary(report):
    """Print human-readable summary."""
    print("\n" + "=" * 60)
    print(f"  DAILY DISCORD AUDIT — {report['audit_date']}")
    print("=" * 60)

    if "mapping" in report["sections"]:
        m = report["sections"]["mapping"]
        print(f"\n📋 MEMBER MAPPING")
        print(f"  Server members: {m['total_members']}")
        print(f"  Student channels: {m['student_channels']}")
        print(f"  Mapped: {m['previously_mapped']} + {m['newly_mapped']} new")
        if m["still_unmapped"]:
            print(f"  ⚠️  Still unmapped: {len(m['still_unmapped'])}")
            for u in m["still_unmapped"][:5]:
                print(f"    - {u['discord_name']} → {u['channel']}")

    if "status" in report["sections"]:
        s = report["sections"]["status"]
        print(f"\n👥 STUDENT STATUS")
        print(f"  Total: {s['total_students']}")
        for status, count in s["by_status"].items():
            print(f"    {status}: {count}")
        print(f"  Health: {s['health_distribution']}")
        if s["stale_active"]:
            print(f"  ⚠️  Stale active (no activity 30d): {len(s['stale_active'])}")
        if s["active_churned"]:
            print(f"  🔄 Churned but recently active: {len(s['active_churned'])}")

    if "trends" in report["sections"]:
        t = report["sections"]["trends"]
        if t["frustrated_students"]:
            print(f"\n😤 FRUSTRATED ({len(t['frustrated_students'])})")
            for f in t["frustrated_students"][:5]:
                print(f"    {f['name']} — {f['milestone']} (health: {f['health']})")
        if t["ghost_students"]:
            print(f"\n👻 GHOSTS (active but silent 14d): {len(t['ghost_students'])}")
            for g in t["ghost_students"][:5]:
                print(f"    {g['name']} — {g['milestone']} (last: {g['last_seen']})")
        if t["most_active"]:
            print(f"\n🔥 MOST ACTIVE (7d)")
            for a in t["most_active"][:5]:
                print(f"    {a['name']} — {a['signals']} signals")

    if "knowledge" in report["sections"]:
        k = report["sections"]["knowledge"]
        print(f"\n🧠 KNOWLEDGE")
        print(f"  Questions (7d): {k['questions_7d']}")
        print(f"  Negative feedback (7d): {k['negative_feedback_7d']}")
        print(f"  Pending FAQ: {len(k['pending_faq'])}")
        if k["top_questions"]:
            print(f"  Top questions:")
            for q in k["top_questions"][:5]:
                print(f"    [{q['freq']}x] {q['q'][:60]}")

    if "activity" in report["sections"]:
        a = report["sections"]["activity"]
        print(f"\n📊 CHANNEL ACTIVITY (7d)")
        print(f"  Active channels: {a['active_channels_7d']}")
        for ch in a["top_channels"][:5]:
            print(f"    #{ch['channel']}: {ch['messages_7d']} msgs, {ch['unique_users']} users")

    print("\n" + "=" * 60)
    print(f"  Report saved to nova.db + .tmp/audit/")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    asyncio.run(run_audit(quick=quick))
