"""Adaptive knowledge system — thin wrapper around nova_core.knowledge.

All knowledge logic lives in nova_core/knowledge.py. This module re-exports
for backwards compatibility with existing discord_bot imports.

The flywheel:
  Users ask questions → tracked + clustered by keywords →
  Frequent clusters auto-generate FAQ candidates →
  Admin approves → approved entries injected into Claude context →
  Better answers → user ratings feed back → bot gets smarter
"""

from nova_core.knowledge import (
    extract_keywords,
    detect_category,
    get_relevant_faq,
    build_knowledge_block,
    maybe_auto_generate_faq,
)


def track_question(db, user_id, question):
    """Track a user question (backwards-compat wrapper).

    The `db` parameter is ignored — nova_core uses its own shared DB.
    """
    from nova_core.knowledge import track_question as _track
    return _track(str(user_id), question, "discord")


def get_relevant_knowledge(db, question, limit=3):
    """Find approved FAQ entries (backwards-compat wrapper)."""
    return get_relevant_faq(question, limit=limit)


def maybe_auto_generate_faq_compat(db, cluster_id, frequency, threshold=5):
    """Auto-generate FAQ candidate (backwards-compat wrapper)."""
    return maybe_auto_generate_faq(cluster_id, frequency, threshold)


__all__ = [
    "extract_keywords",
    "detect_category",
    "track_question",
    "get_relevant_knowledge",
    "build_knowledge_block",
    "maybe_auto_generate_faq",
]
