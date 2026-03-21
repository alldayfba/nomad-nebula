"""Centralized feedback store — ratings from all platforms, gap detection.

Feedback is READ-ONLY for improvement:
- Never used for targeting, profiling, or malicious intent
- User questions + answers stored only for quality improvement
- No PII beyond opaque user IDs
- Admin reviews feedback → updates FAQ → bot gets smarter
"""

from __future__ import annotations

from . import database as db
from .knowledge import extract_keywords, _jaccard_similarity


def store_feedback(
    platform: str,
    user_id: str,
    rating: int,
    question_text: str = "",
    answer_text: str = "",
    comment: str = "",
    conversation_id: str = "",
    message_id: str = "",
) -> int:
    """Store feedback from any platform. Returns feedback ID."""
    conn = db.get_conn()

    # Try to link to a question cluster
    cluster_id = None
    if question_text:
        keywords = extract_keywords(question_text)
        if keywords:
            clusters = conn.execute(
                "SELECT id, keywords FROM question_clusters"
            ).fetchall()
            best_id = None
            best_sim = 0.0
            for c in clusters:
                sim = _jaccard_similarity(keywords, c["keywords"])
                if sim > best_sim and sim >= 0.4:
                    best_sim = sim
                    best_id = c["id"]
            cluster_id = best_id

    cursor = conn.execute(
        "INSERT INTO feedback (platform, user_id, conversation_id, message_id, "
        "rating, comment, question_text, answer_text, cluster_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (platform, user_id, conversation_id, message_id,
         rating, comment, question_text[:1000], answer_text[:2000], cluster_id),
    )
    conn.commit()
    return cursor.lastrowid


def get_pending_review(limit: int = 20) -> list[dict]:
    """Get unreviewed feedback, prioritizing negative ratings."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, platform, user_id, rating, comment, question_text, answer_text, "
        "cluster_id, created_at FROM feedback "
        "WHERE reviewed_by IS NULL ORDER BY rating ASC, created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()

    return [dict(r) for r in rows]


def mark_reviewed(feedback_id: int, reviewer: str, action: str):
    """Mark feedback as reviewed."""
    conn = db.get_conn()
    conn.execute(
        "UPDATE feedback SET reviewed_by = ?, review_action = ? WHERE id = ?",
        (reviewer, action, feedback_id),
    )
    conn.commit()


def get_feedback_stats(hours: int = 24) -> dict:
    """Get cross-platform feedback stats."""
    conn = db.get_conn()

    total = conn.execute(
        "SELECT platform, rating, COUNT(*) as cnt FROM feedback "
        "WHERE created_at > datetime('now', ?) GROUP BY platform, rating",
        (f"-{hours} hours",),
    ).fetchall()

    unreviewed = conn.execute(
        "SELECT COUNT(*) as cnt FROM feedback WHERE reviewed_by IS NULL"
    ).fetchone()["cnt"]

    # Find clusters with high negative feedback (knowledge gaps)
    gaps = conn.execute(
        "SELECT qc.representative_question, qc.category, "
        "COUNT(*) as neg_count, qc.frequency "
        "FROM feedback f JOIN question_clusters qc ON f.cluster_id = qc.id "
        "WHERE f.rating = 1 AND f.created_at > datetime('now', '-7 days') "
        "GROUP BY f.cluster_id HAVING neg_count >= 2 "
        "ORDER BY neg_count DESC LIMIT 5",
    ).fetchall()

    stats: dict[str, dict[str, int]] = {}
    for row in total:
        plat = row["platform"]
        if plat not in stats:
            stats[plat] = {"positive": 0, "negative": 0}
        if row["rating"] >= 4:
            stats[plat]["positive"] += row["cnt"]
        else:
            stats[plat]["negative"] += row["cnt"]

    return {
        "by_platform": stats,
        "unreviewed": unreviewed,
        "knowledge_gaps": [
            {"question": r["representative_question"], "category": r["category"],
             "negative_count": r["neg_count"], "total_asks": r["frequency"]}
            for r in gaps
        ],
    }


def get_digest(hours: int = 24) -> dict:
    """Full cross-platform digest for morning briefing."""
    from .security import get_abuse_summary
    from .knowledge import get_knowledge_stats

    feedback = get_feedback_stats(hours)
    abuse = get_abuse_summary(hours)
    knowledge = get_knowledge_stats()

    return {
        "period_hours": hours,
        "feedback": feedback,
        "abuse": abuse,
        "knowledge": knowledge,
    }
