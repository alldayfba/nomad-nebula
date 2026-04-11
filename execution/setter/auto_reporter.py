"""
Auto Reporter — daily performance digest + anomaly detection + optimization
suggestions for the AI setter system.

Reads from .tmp/setter/setter.db (SQLite), computes funnel metrics, flags
anomalies against 7-day rolling averages, produces actionable suggestions,
and delivers to Discord.

Usage:
    python -m execution.setter.auto_reporter              # Full report + Discord
    python -m execution.setter.auto_reporter --dry-run     # Print only
    python -m execution.setter.auto_reporter --suggestions  # Suggestions only
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Path bootstrap ──────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DB_PATH = _PROJECT_ROOT / ".tmp" / "setter" / "setter.db"

# ── Stage definitions ───────────────────────────────────────────────────────

FUNNEL_STAGES = [
    "new", "opener_sent", "replied", "qualifying", "qualified",
    "booking", "booked", "show", "no_show", "nurture",
    "disqualified", "dead",
]

POSITIVE_STAGES = {"qualifying", "qualified", "booking", "booked", "show"}
TERMINAL_STAGES = {"disqualified", "dead", "no_show"}


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class FunnelMetrics:
    total_prospects: int = 0
    stage_counts: Dict[str, int] = field(default_factory=dict)
    today_new: int = 0
    today_messages_out: int = 0
    today_messages_in: int = 0
    reply_rate: float = 0.0
    qualification_rate: float = 0.0
    booking_rate: float = 0.0
    show_rate: float = 0.0
    avg_messages_to_booking: float = 0.0
    stale_leads: int = 0
    consecutive_no_reply: int = 0


@dataclass
class Anomaly:
    severity: str  # WARNING, CRITICAL
    metric: str
    message: str


@dataclass
class Suggestion:
    priority: int  # 1=highest
    area: str
    message: str


# ── DB helpers ──────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    """Open a read-only connection to the setter DB."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Setter DB not found at {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Any:
    """Return a single scalar value."""
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else 0


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


# ── Metric collection ──────────────────────────────────────────────────────

def collect_metrics(conn: sqlite3.Connection) -> FunnelMetrics:
    m = FunnelMetrics()
    today = _today()

    # Total prospects
    m.total_prospects = _scalar(conn, "SELECT COUNT(*) FROM prospects")

    # Stage breakdown
    rows = conn.execute(
        "SELECT stage, COUNT(*) as cnt FROM conversations GROUP BY stage"
    ).fetchall()
    m.stage_counts = {r["stage"]: r["cnt"] for r in rows}

    # Today's new conversations
    m.today_new = _scalar(
        conn,
        "SELECT COUNT(*) FROM conversations WHERE created_at LIKE ?",
        (f"{today}%",),
    )

    # Today's messages
    m.today_messages_out = _scalar(
        conn,
        "SELECT COUNT(*) FROM messages WHERE direction='out' AND sent_at LIKE ?",
        (f"{today}%",),
    )
    m.today_messages_in = _scalar(
        conn,
        "SELECT COUNT(*) FROM messages WHERE direction='in' AND sent_at LIKE ?",
        (f"{today}%",),
    )

    # Reply rate: replied / opener_sent
    opener_sent = m.stage_counts.get("opener_sent", 0)
    # Count everyone who has progressed past opener_sent
    replied_plus = sum(
        m.stage_counts.get(s, 0)
        for s in FUNNEL_STAGES
        if s not in ("new", "opener_sent")
    )
    total_sent = opener_sent + replied_plus
    m.reply_rate = (replied_plus / total_sent * 100) if total_sent > 0 else 0.0

    # Qualification rate: positive stages / replied+
    replied_count = m.stage_counts.get("replied", 0)
    qualified_plus = sum(m.stage_counts.get(s, 0) for s in POSITIVE_STAGES)
    total_replied = replied_count + qualified_plus + sum(
        m.stage_counts.get(s, 0) for s in TERMINAL_STAGES
    ) + m.stage_counts.get("nurture", 0)
    m.qualification_rate = (
        (qualified_plus / total_replied * 100) if total_replied > 0 else 0.0
    )

    # Booking rate: booked / (qualified + booking + booked)
    bookable = sum(
        m.stage_counts.get(s, 0) for s in ("qualified", "booking", "booked")
    )
    booked = m.stage_counts.get("booked", 0)
    m.booking_rate = (booked / bookable * 100) if bookable > 0 else 0.0

    # Show rate: show / (booked + show + no_show)
    show_pool = sum(
        m.stage_counts.get(s, 0) for s in ("booked", "show", "no_show")
    )
    showed = m.stage_counts.get("show", 0)
    m.show_rate = (showed / show_pool * 100) if show_pool > 0 else 0.0

    # Average messages per conversation before booking
    avg_row = conn.execute("""
        SELECT AVG(messages_sent + messages_received) as avg_msgs
        FROM conversations
        WHERE stage IN ('booked', 'show', 'no_show')
    """).fetchone()
    m.avg_messages_to_booking = round(avg_row["avg_msgs"] or 0, 1)

    # Stale leads: same stage >7 days with no messages
    seven_days_ago = _days_ago(7)
    m.stale_leads = _scalar(
        conn,
        """SELECT COUNT(*) FROM conversations
           WHERE updated_at < ?
           AND stage NOT IN ('booked', 'show', 'no_show', 'disqualified', 'dead')
           AND (last_message_at IS NULL OR last_message_at < ?)""",
        (seven_days_ago, seven_days_ago),
    )

    # Consecutive no-reply streak (most recent openers with no reply)
    m.consecutive_no_reply = _scalar(
        conn,
        """SELECT COUNT(*) FROM conversations
           WHERE stage = 'opener_sent'
           AND messages_received = 0
           AND created_at >= ?""",
        (_days_ago(3),),
    )

    return m


# ── 7-day rolling averages from daily_metrics ──────────────────────────────

def collect_rolling_averages(conn: sqlite3.Connection) -> Dict[str, float]:
    """Pull 7-day rolling averages from daily_metrics table."""
    seven_days_ago = _days_ago(7)
    avgs = {}
    try:
        row = conn.execute("""
            SELECT
                AVG(total_dms_sent) as avg_dms_sent,
                AVG(replies_received) as avg_replies,
                AVG(response_rate) as avg_response_rate,
                AVG(booked) as avg_booked,
                AVG(qualified) as avg_qualified,
                AVG(api_cost) as avg_api_cost,
                AVG(action_blocks) as avg_action_blocks
            FROM daily_metrics
            WHERE date >= ?
        """, (seven_days_ago,)).fetchone()
        if row:
            avgs = {
                "dms_sent": row["avg_dms_sent"] or 0,
                "replies": row["avg_replies"] or 0,
                "response_rate": row["avg_response_rate"] or 0,
                "booked": row["avg_booked"] or 0,
                "qualified": row["avg_qualified"] or 0,
                "api_cost": row["avg_api_cost"] or 0,
                "action_blocks": row["avg_action_blocks"] or 0,
            }
    except sqlite3.OperationalError:
        pass  # Table might not be populated yet
    return avgs


def collect_7day_trend(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Pull last 7 days of daily_metrics for trend display."""
    seven_days_ago = _days_ago(7)
    try:
        rows = conn.execute("""
            SELECT date, total_dms_sent, replies_received, response_rate,
                   booked, qualified, api_cost, action_blocks
            FROM daily_metrics
            WHERE date >= ?
            ORDER BY date ASC
        """, (seven_days_ago,)).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


# ── Anomaly detection ───────────────────────────────────────────────────────

def detect_anomalies(
    metrics: FunnelMetrics,
    rolling: Dict[str, float],
) -> List[Anomaly]:
    anomalies = []

    # Reply rate dropped >20% vs rolling average
    if rolling.get("response_rate", 0) > 0:
        drop = (rolling["response_rate"] - metrics.reply_rate) / rolling["response_rate"]
        if drop > 0.20:
            anomalies.append(Anomaly(
                "WARNING",
                "reply_rate",
                f"Reply rate dropped {drop*100:.0f}% vs 7-day avg "
                f"({metrics.reply_rate:.1f}% vs {rolling['response_rate']:.1f}%)",
            ))

    # Zero replies but >10 openers sent today
    if metrics.today_messages_in == 0 and metrics.today_messages_out > 10:
        anomalies.append(Anomaly(
            "CRITICAL",
            "zero_replies",
            f"Zero replies received today despite {metrics.today_messages_out} "
            f"outbound messages — possible action block or broken openers",
        ))

    # >50 consecutive openers with 0 replies
    if metrics.consecutive_no_reply > 50:
        anomalies.append(Anomaly(
            "CRITICAL",
            "consecutive_no_reply",
            f"{metrics.consecutive_no_reply} consecutive openers with 0 replies "
            f"in last 3 days — likely action blocked or openers are dead",
        ))

    # Avg messages to booking increased >30%
    # (We'd need historical avg to compare — use rolling booked as proxy)
    if metrics.avg_messages_to_booking > 20:
        anomalies.append(Anomaly(
            "WARNING",
            "long_conversations",
            f"Avg {metrics.avg_messages_to_booking} messages to booking — "
            f"conversations are dragging, tighten qualification flow",
        ))

    # Stale leads
    if metrics.stale_leads > 10:
        anomalies.append(Anomaly(
            "WARNING",
            "stale_leads",
            f"{metrics.stale_leads} conversations stuck at same stage for >7 days "
            f"with no messages — dead weight in pipeline",
        ))

    return anomalies


# ── Optimization suggestions ────────────────────────────────────────────────

def generate_suggestions(metrics: FunnelMetrics) -> List[Suggestion]:
    suggestions = []
    priority = 1

    # Bottleneck waterfall — check from top of funnel down
    if metrics.reply_rate < 10:
        suggestions.append(Suggestion(
            priority, "OPENER QUALITY",
            f"Reply rate is {metrics.reply_rate:.1f}% (target: >15%). "
            f"Review top-performing openers, test new bio-based variations. "
            f"Consider switching opener_type or adding story replies.",
        ))
        priority += 1

    if metrics.reply_rate >= 10 and metrics.qualification_rate < 30:
        suggestions.append(Suggestion(
            priority, "QUALIFICATION FLOW",
            f"Qualification rate is {metrics.qualification_rate:.1f}% (target: >30%). "
            f"Are we asking the right questions? Review qual scripts — "
            f"commitment/urgency/resources framework may need adjustment.",
        ))
        priority += 1

    if metrics.qualification_rate >= 30 and metrics.booking_rate < 20:
        suggestions.append(Suggestion(
            priority, "BOOKING BRIDGE",
            f"Booking rate is {metrics.booking_rate:.1f}% (target: >30%). "
            f"Review tie-downs and booking CTA. Consider urgency hooks: "
            f"'I have 2 spots this week' or calendar link drop timing.",
        ))
        priority += 1

    if metrics.booking_rate >= 20 and metrics.show_rate < 70:
        suggestions.append(Suggestion(
            priority, "SHOW RATE",
            f"Show rate is {metrics.show_rate:.1f}% (target: >70%). "
            f"Review pre-call nurture sequence. Add same-day reminder, "
            f"value video, and 'looking forward to chatting' nudge.",
        ))
        priority += 1

    dead_count = metrics.stage_counts.get("dead", 0)
    if dead_count > 100:
        suggestions.append(Suggestion(
            priority, "DEAD LEADS",
            f"{dead_count} leads at 'dead' stage. Consider a re-engagement "
            f"campaign: value-share DM, story mention, or new offer angle.",
        ))
        priority += 1

    nurture_count = metrics.stage_counts.get("nurture", 0)
    if nurture_count > 50:
        suggestions.append(Suggestion(
            priority, "NURTURE POOL",
            f"{nurture_count} leads in nurture. Run a value-share campaign — "
            f"case study drop, testimonial, or 'quick question' re-opener.",
        ))
        priority += 1

    if metrics.stale_leads > 20:
        suggestions.append(Suggestion(
            priority, "STALE PIPELINE",
            f"{metrics.stale_leads} leads stuck for 7+ days. Bulk-move "
            f"stale leads to nurture or dead. Clean pipeline = clear picture.",
        ))
        priority += 1

    # If funnel is actually healthy, say so
    if not suggestions:
        suggestions.append(Suggestion(
            1, "FUNNEL HEALTH",
            "All funnel metrics within target ranges. Keep pushing volume "
            "and let compounding do its work.",
        ))

    return suggestions


# ── Health score ────────────────────────────────────────────────────────────

def compute_health_score(metrics: FunnelMetrics) -> Tuple[str, int]:
    """
    Grade A-F based on weighted funnel performance.
    Returns (letter_grade, numeric_score 0-100).
    """
    score = 0

    # Reply rate (0-30 pts) — target 15%+
    if metrics.reply_rate >= 20:
        score += 30
    elif metrics.reply_rate >= 15:
        score += 25
    elif metrics.reply_rate >= 10:
        score += 18
    elif metrics.reply_rate >= 5:
        score += 10
    else:
        score += 3

    # Qualification rate (0-25 pts) — target 30%+
    if metrics.qualification_rate >= 40:
        score += 25
    elif metrics.qualification_rate >= 30:
        score += 20
    elif metrics.qualification_rate >= 20:
        score += 14
    elif metrics.qualification_rate >= 10:
        score += 8
    else:
        score += 2

    # Booking rate (0-25 pts) — target 30%+
    if metrics.booking_rate >= 40:
        score += 25
    elif metrics.booking_rate >= 30:
        score += 20
    elif metrics.booking_rate >= 20:
        score += 14
    elif metrics.booking_rate >= 10:
        score += 8
    else:
        score += 2

    # Pipeline activity (0-10 pts)
    if metrics.today_messages_out > 0:
        score += 5
    if metrics.today_messages_in > 0:
        score += 5

    # Stale penalty (0 to -10)
    if metrics.stale_leads > 50:
        score -= 10
    elif metrics.stale_leads > 20:
        score -= 5

    score = max(0, min(100, score))

    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    return grade, score


# ── Report formatting ───────────────────────────────────────────────────────

def format_report(
    metrics: FunnelMetrics,
    anomalies: List[Anomaly],
    suggestions: List[Suggestion],
    trend: List[Dict[str, Any]],
    grade: str,
    score: int,
) -> List[str]:
    """
    Build the report as a list of Discord messages (each <=2000 chars).
    """
    today = _today()
    chunks = []

    # ── Part 1: Header + Funnel ──
    lines = []
    lines.append(f"# AI Setter Daily Report — {today}")
    lines.append(f"**Health Score: {grade} ({score}/100)**\n")

    lines.append("## Funnel Snapshot")
    lines.append("```")
    total_convos = sum(metrics.stage_counts.values())
    lines.append(f"Total Prospects:  {metrics.total_prospects:,}")
    lines.append(f"Total Convos:     {total_convos:,}")
    lines.append(f"New Today:        {metrics.today_new}")
    lines.append("")
    # Stage breakdown as a compact table
    for stage in FUNNEL_STAGES:
        count = metrics.stage_counts.get(stage, 0)
        bar = "#" * min(count, 30)
        lines.append(f"  {stage:<15} {count:>5}  {bar}")
    lines.append("```")

    lines.append("## Key Rates")
    lines.append("```")
    lines.append(f"Reply Rate:          {metrics.reply_rate:>6.1f}%  (target: >15%)")
    lines.append(f"Qualification Rate:  {metrics.qualification_rate:>6.1f}%  (target: >30%)")
    lines.append(f"Booking Rate:        {metrics.booking_rate:>6.1f}%  (target: >30%)")
    lines.append(f"Show Rate:           {metrics.show_rate:>6.1f}%  (target: >70%)")
    lines.append(f"Avg Msgs to Book:    {metrics.avg_messages_to_booking:>6.1f}")
    lines.append("```")

    lines.append("## Today's Activity")
    lines.append("```")
    lines.append(f"Messages Sent:     {metrics.today_messages_out}")
    lines.append(f"Messages Received: {metrics.today_messages_in}")
    lines.append(f"Stale Leads:       {metrics.stale_leads}")
    lines.append("```")

    chunks.append("\n".join(lines))

    # ── Part 2: Anomalies ──
    if anomalies:
        anom_lines = ["## Anomalies Detected"]
        for a in anomalies:
            icon = "!!" if a.severity == "CRITICAL" else "!"
            anom_lines.append(f"**[{a.severity}]** {icon} {a.message}")
        chunks.append("\n".join(anom_lines))

    # ── Part 3: Suggestions ──
    if suggestions:
        sug_lines = ["## Optimization Suggestions"]
        for s in suggestions:
            sug_lines.append(f"**{s.priority}. {s.area}** — {s.message}")
        chunks.append("\n".join(sug_lines))

    # ── Part 4: 7-day trend (if data exists) ──
    if trend:
        trend_lines = ["## 7-Day Trend"]
        trend_lines.append("```")
        trend_lines.append(f"{'Date':<12} {'DMs':>5} {'Replies':>8} {'Rate':>6} {'Booked':>7} {'Cost':>7}")
        trend_lines.append("-" * 50)
        for day in trend:
            trend_lines.append(
                f"{day.get('date',''):<12} "
                f"{day.get('total_dms_sent',0):>5} "
                f"{day.get('replies_received',0):>8} "
                f"{day.get('response_rate',0):>5.1f}% "
                f"{day.get('booked',0):>7} "
                f"${day.get('api_cost',0):>6.2f}"
            )
        trend_lines.append("```")
        chunks.append("\n".join(trend_lines))

    # Ensure no chunk exceeds 2000 chars
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= 2000:
            final_chunks.append(chunk)
        else:
            # Split on double newlines, then recombine within limit
            sections = chunk.split("\n\n")
            current = ""
            for section in sections:
                if len(current) + len(section) + 2 > 1950:
                    if current:
                        final_chunks.append(current)
                    current = section
                else:
                    current = f"{current}\n\n{section}" if current else section
            if current:
                final_chunks.append(current)

    return final_chunks


def format_suggestions_only(suggestions: List[Suggestion]) -> str:
    lines = [f"## AI Setter — Optimization Suggestions ({_today()})"]
    for s in suggestions:
        lines.append(f"\n**{s.priority}. {s.area}**")
        lines.append(f"   {s.message}")
    return "\n".join(lines)


# ── Discord delivery ────────────────────────────────────────────────────────

def send_to_discord(chunks: List[str]) -> bool:
    """Send report chunks to Discord. Returns True on success."""
    webhook_url = (
        os.getenv("DISCORD_SETTER_WEBHOOK")
        or os.getenv("DISCORD_WEBHOOK_URL")
    )
    if not webhook_url:
        print("[auto_reporter] No Discord webhook configured "
              "(DISCORD_SETTER_WEBHOOK or DISCORD_WEBHOOK_URL)")
        return False

    import requests

    success = True
    for i, chunk in enumerate(chunks):
        resp = requests.post(
            webhook_url,
            json={"content": chunk},
            timeout=10,
        )
        if resp.status_code not in (200, 204):
            print(f"[auto_reporter] Discord send failed for chunk {i+1}: "
                  f"{resp.status_code} {resp.text}")
            success = False

    return success


# ── Main ────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, suggestions_only: bool = False) -> str:
    """
    Generate and optionally send the daily report.
    Returns the full report text.
    """
    conn = _connect()
    try:
        metrics = collect_metrics(conn)
        rolling = collect_rolling_averages(conn)
        trend = collect_7day_trend(conn)
        anomalies = detect_anomalies(metrics, rolling)
        suggestions = generate_suggestions(metrics)
        grade, score = compute_health_score(metrics)
    finally:
        conn.close()

    if suggestions_only:
        text = format_suggestions_only(suggestions)
        print(text)
        return text

    chunks = format_report(metrics, anomalies, suggestions, trend, grade, score)
    full_text = "\n\n".join(chunks)
    print(full_text)

    if not dry_run:
        ok = send_to_discord(chunks)
        if ok:
            print("\n[auto_reporter] Report sent to Discord.")
        else:
            print("\n[auto_reporter] Discord delivery failed or not configured.")

    return full_text


def main():
    parser = argparse.ArgumentParser(
        description="AI Setter daily performance report",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report without sending to Discord",
    )
    parser.add_argument(
        "--suggestions",
        action="store_true",
        help="Only print optimization suggestions",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, suggestions_only=args.suggestions)


if __name__ == "__main__":
    main()
