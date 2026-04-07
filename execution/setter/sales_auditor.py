"""
Sales Manager audit engine — reviews every conversation for quality.

Runs via Claude CLI (Max plan). Analyzes conversations and produces:
- Quality scores (opener, qualification, objection handling, close attempt)
- What worked / what failed
- Improvement suggestions fed back into winning_patterns

This is the self-improving loop that makes the setter get better over time.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Dict, List

from . import setter_db as db
from .lead_grader import grade_conversation

logger = logging.getLogger("setter.auditor")


def audit_conversation(conversation_id: int) -> Dict:
    """Have the Sales Manager agent audit a single conversation.

    Returns audit results dict.
    """
    conv = db.get_conversation(conversation_id)
    if not conv:
        return {}

    prospect = db.get_prospect(conv["prospect_id"])
    if not prospect:
        return {}

    messages = db.get_messages(conversation_id, limit=50)
    if len(messages) < 2:
        return {}  # Not enough to audit

    # Format conversation for audit
    convo_text = ""
    for msg in messages:
        who = "SETTER" if msg["direction"] == "out" else "PROSPECT"
        convo_text += f"{who}: {msg['content']}\n"

    system = """You are a senior Sales Manager auditing DM setter conversations.

You manage an AI DM setter for an Amazon FBA coaching program ($3K-$10K).
Your job: grade every conversation, find what worked, what failed, and give specific improvement feedback.

AUDIT CRITERIA:
1. Opener Quality (1-10): Was it personalized? Did it get a reply? Natural or robotic?
2. Qualification Quality (1-10): Did we ask either/or questions? Did we uncover commitment, urgency, resources?
3. Objection Handling (1-10): Did we address concerns without being pushy? Did we redirect to the call?
4. Close Attempt (1-10): Did we bridge to booking smoothly? Was the calendar link sent at the right time?

OUTPUT FORMAT (JSON only, no other text):
{
  "grade": "A/B/C/D/F",
  "opener_quality": 1-10,
  "qualification_quality": 1-10,
  "objection_handling": 1-10,
  "close_attempt_quality": 1-10,
  "what_worked": "specific thing that worked well",
  "what_failed": "specific thing that failed or could improve",
  "improvement_suggestions": "concrete, actionable suggestion for next time",
  "outcome": "booked/lost/ongoing/dead"
}"""

    user = f"""Audit this DM conversation:

PROSPECT: @{prospect.get('ig_handle', '')}
Bio: {prospect.get('bio', 'N/A')}
Stage: {conv.get('stage', 'unknown')}
Messages exchanged: {len(messages)}

CONVERSATION:
{convo_text}

Return ONLY the JSON audit. No explanation."""

    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", "claude-haiku-4-5-20251001"],
            input=f"{system}\n\n---\n\n{user}",
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            logger.error("Audit CLI error: %s", proc.stderr[:200])
            return {}

        # Parse JSON from response
        text = proc.stdout.strip()
        # Find JSON in response
        json_match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if not json_match:
            logger.error("No JSON in audit response: %s", text[:200])
            return {}

        audit = json.loads(json_match.group())

        # Store audit
        db.add_conversation_audit(
            conversation_id=conversation_id,
            grade=audit.get("grade", "C"),
            opener_quality=audit.get("opener_quality", 0),
            qualification_quality=audit.get("qualification_quality", 0),
            objection_handling=audit.get("objection_handling", 0),
            close_attempt_quality=audit.get("close_attempt_quality", 0),
            what_worked=audit.get("what_worked", ""),
            what_failed=audit.get("what_failed", ""),
            improvement_suggestions=audit.get("improvement_suggestions", ""),
            outcome=audit.get("outcome", "ongoing"),
        )

        # Also update lead grade
        grade_conversation(conversation_id)

        # If something worked well, record it as a winning pattern
        if audit.get("opener_quality", 0) >= 8:
            opener_msg = next(
                (m["content"] for m in messages if m["direction"] == "out"), ""
            )
            if opener_msg:
                db.record_pattern_success("opener", opener_msg)

        logger.info("Audited @%s: grade=%s opener=%d qual=%d objection=%d close=%d",
                     prospect.get("ig_handle"), audit.get("grade"),
                     audit.get("opener_quality", 0), audit.get("qualification_quality", 0),
                     audit.get("objection_handling", 0), audit.get("close_attempt_quality", 0))

        return audit

    except json.JSONDecodeError as e:
        logger.error("Audit JSON parse error: %s", e)
        return {}
    except Exception as e:
        logger.error("Audit error: %s", e)
        return {}


def batch_audit(limit: int = 20) -> Dict:
    """Audit recent conversations that haven't been audited yet.

    Run daily by the daemon or Sales Manager.
    """
    # Get conversations with enough messages that haven't been audited recently
    d = db.get_db()
    rows = d.execute(
        """SELECT c.id FROM conversations c
           LEFT JOIN conversation_audits ca ON ca.conversation_id = c.id
           WHERE c.messages_sent >= 1 AND c.messages_received >= 1
             AND (ca.id IS NULL OR ca.audited_at < datetime('now', '-1 day'))
           ORDER BY c.updated_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    stats = {"audited": 0, "errors": 0}
    for row in rows:
        result = audit_conversation(row["id"])
        if result:
            stats["audited"] += 1
        else:
            stats["errors"] += 1

    logger.info("Batch audit: %d audited, %d errors", stats["audited"], stats["errors"])
    return stats


def get_improvement_report() -> str:
    """Generate a text report of top improvements needed.

    Used by the daemon to feed back into the system prompt.
    """
    summary = db.get_audit_summary()
    if not summary or summary.get("total_audits", 0) == 0:
        return ""

    report = f"""## Sales Manager Audit Report
- Total conversations audited: {summary.get('total_audits', 0)}
- Avg opener quality: {summary.get('avg_opener', 0):.1f}/10
- Avg qualification quality: {summary.get('avg_qualification', 0):.1f}/10
- Avg objection handling: {summary.get('avg_objection', 0):.1f}/10
- Avg close attempt: {summary.get('avg_close', 0):.1f}/10
- Total booked: {summary.get('total_booked', 0)}
- Total closed: {summary.get('total_closed', 0)}
- Revenue attributed: ${summary.get('total_revenue', 0):.0f}
"""

    # Get recent improvement suggestions
    d = db.get_db()
    recent = d.execute(
        """SELECT improvement_suggestions, what_failed FROM conversation_audits
           WHERE improvement_suggestions != '' ORDER BY audited_at DESC LIMIT 5"""
    ).fetchall()

    if recent:
        report += "\n### Recent Improvement Areas:\n"
        for r in recent:
            if r["improvement_suggestions"]:
                report += f"- {r['improvement_suggestions']}\n"

    return report
