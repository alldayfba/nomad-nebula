"""
Setter metrics — daily aggregation, reporting, and Discord summaries.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Dict

from . import setter_db as db
from .setter_config import DISCORD_WEBHOOK_URL, PROJECT_ROOT

logger = logging.getLogger("setter.metrics")


def aggregate_daily_metrics():
    """Aggregate today's metrics from conversations and messages."""
    d = db.get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    # Count conversations by stage
    active = d.execute(
        """SELECT COUNT(*) as cnt FROM conversations
           WHERE stage NOT IN ('dead', 'disqualified', 'show')"""
    ).fetchone()["cnt"]

    booked_today = d.execute(
        """SELECT COUNT(*) as cnt FROM conversations
           WHERE stage = 'booked' AND updated_at LIKE ?""",
        (f"{today}%",),
    ).fetchone()["cnt"]

    showed_today = d.execute(
        """SELECT COUNT(*) as cnt FROM conversations
           WHERE stage = 'show' AND updated_at LIKE ?""",
        (f"{today}%",),
    ).fetchone()["cnt"]

    # Response rate
    total_sent = d.execute(
        """SELECT COUNT(DISTINCT conversation_id) as cnt FROM messages
           WHERE direction = 'out' AND sent_at LIKE ?""",
        (f"{today}%",),
    ).fetchone()["cnt"]

    total_replied = d.execute(
        """SELECT COUNT(DISTINCT conversation_id) as cnt FROM messages
           WHERE direction = 'in' AND sent_at LIKE ?""",
        (f"{today}%",),
    ).fetchone()["cnt"]

    response_rate = (total_replied / total_sent * 100) if total_sent else 0

    # API cost
    api_cost = d.execute(
        """SELECT SUM(cost_usd) as total FROM messages
           WHERE sent_at LIKE ?""",
        (f"{today}%",),
    ).fetchone()["total"] or 0.0

    # Total DMs
    total_dms = d.execute(
        """SELECT COUNT(*) as cnt FROM messages
           WHERE direction = 'out' AND sent_at LIKE ?""",
        (f"{today}%",),
    ).fetchone()["cnt"]

    db.update_daily_metrics(
        conversations_active=active,
        booked=booked_today,
        showed=showed_today,
        response_rate=round(response_rate, 1),
        api_cost=round(api_cost, 2),
        total_dms_sent=total_dms,
    )

    logger.info("Metrics aggregated: active=%d booked=%d response_rate=%.1f%% cost=$%.2f",
                 active, booked_today, response_rate, api_cost)


def send_daily_summary():
    """Send daily summary to Discord."""
    metrics = db.get_daily_metrics()
    pipeline = db.get_pipeline_stats()
    sends = db.get_today_send_counts()

    if not metrics:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    summary = f"""**AI Setter Daily Summary — {today}**

**DMs Sent:**
- Cold outbound: {metrics.get('cold_dms_sent', 0)}
- Warm outreach: {metrics.get('warm_dms_sent', 0)}
- Follow-ups: {metrics.get('follow_ups_sent', 0)}
- Inbox replies: {metrics.get('inbox_replies_sent', 0)}
- **Total: {metrics.get('total_dms_sent', 0)}**

**Results:**
- Replies received: {metrics.get('replies_received', 0)}
- Response rate: {metrics.get('response_rate', 0):.1f}%
- Calls booked: {metrics.get('booked', 0)}
- Shows: {metrics.get('showed', 0)}

**Pipeline:**
- Active conversations: {pipeline.get('qualifying', 0) + pipeline.get('replied', 0) + pipeline.get('booking', 0)}
- Qualified: {pipeline.get('qualified', 0)}
- Booked (pending): {pipeline.get('booked', 0)}
- Nurture: {pipeline.get('nurture', 0)}

**Costs:** ${metrics.get('api_cost', 0):.2f}
**Escalations:** {metrics.get('escalations', 0)}
**Action blocks:** {metrics.get('action_blocks', 0)}
"""

    _discord_send(summary)
    logger.info("Daily summary sent to Discord")


def _discord_send(message: str):
    """Send message to Discord webhook."""
    webhook = DISCORD_WEBHOOK_URL
    if not webhook:
        logger.debug("No Discord webhook configured, skipping notification")
        return

    try:
        import urllib.request
        data = json.dumps({"content": message}).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.error("Discord send error: %s", e)
