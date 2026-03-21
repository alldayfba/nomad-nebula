"""Adaptive knowledge system — question tracking, keyword clustering, FAQ injection."""

from __future__ import annotations

import re

# Stop words to exclude from keyword extraction
STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "must",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "their", "this", "that", "these", "those", "what",
    "which", "who", "whom", "when", "where", "why", "how", "not", "no",
    "so", "if", "then", "than", "too", "very", "just", "about", "also",
    "more", "some", "any", "all", "each", "every", "both", "few", "much",
    "many", "most", "other", "into", "up", "out", "as", "its",
    "hi", "hey", "hello", "thanks", "thank", "please", "help", "know",
    "want", "like", "get", "got", "going", "go", "make", "thing",
})

# Category detection keywords — sales-focused
CATEGORY_KEYWORDS = {
    "objection": {"objection", "objections", "handle", "handling", "pushback", "concern", "doubt", "resist"},
    "close": {"close", "closing", "close", "commit", "decision", "deal", "signed", "contract", "payment"},
    "discovery": {"discovery", "nepq", "question", "qualify", "situation", "problem", "gap", "need", "goal"},
    "script": {"script", "word", "track", "line", "phrase", "say", "respond", "language", "opener"},
    "roleplay": {"roleplay", "role", "play", "practice", "scenario", "drill", "mock", "simulate"},
    "tonality": {"tone", "tonality", "voice", "energy", "vibe", "confident", "curious", "concerned"},
    "show_rate": {"show", "rate", "noshow", "no-show", "book", "confirm", "reminder", "attendance"},
    "training": {"training", "train", "learn", "study", "framework", "technique", "method", "hormozi"},
}


def extract_keywords(text: str, max_keywords: int = 5) -> str:
    """Extract top keywords from a question text.

    Returns comma-separated keyword string.
    """
    words = re.findall(r"[a-z0-9]+", text.lower())
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)

    return ",".join(unique[:max_keywords])


def detect_category(text: str) -> str:
    """Auto-detect question category from content."""
    words = set(re.findall(r"[a-z0-9]+", text.lower()))

    best_cat = "general"
    best_score = 0

    for category, cat_words in CATEGORY_KEYWORDS.items():
        score = len(words & cat_words)
        if score > best_score:
            best_score = score
            best_cat = category

    return best_cat


def track_question(db, user_id: str, question: str):
    """Track a user question: extract keywords, find/create cluster, log it.

    Returns:
        (cluster_id, cluster_frequency)
    """
    keywords = extract_keywords(question)
    if not keywords:
        keywords = "general"

    category = detect_category(question)
    cluster_id, frequency = db.find_or_create_cluster(keywords, question, category)
    db.add_question(user_id, question, keywords, cluster_id=cluster_id)

    return cluster_id, frequency


def get_relevant_knowledge(db, question: str, limit: int = 3) -> list:
    """Find approved FAQ entries relevant to a question."""
    keywords = extract_keywords(question)
    if not keywords:
        return []
    return db.get_approved_knowledge(keywords, limit=limit)


def build_knowledge_block(entries: list) -> str:
    """Format FAQ entries into an XML block for Claude's context."""
    if not entries:
        return ""

    lines = [
        "<knowledge_base>",
        "These are verified answers to common sales questions. Use them when relevant:",
        "",
    ]

    for entry in entries:
        lines.append(f"Q: {entry['question']}")
        lines.append(f"A: {entry['answer']}")
        lines.append("")

    lines.append("</knowledge_base>")
    return "\n".join(lines)


def maybe_auto_generate_faq(db, cluster_id: int, frequency: int, threshold: int = 5) -> bool:
    """If a question cluster hits the threshold, create a pending FAQ candidate.

    Returns True if a new candidate was created.
    """
    if frequency < threshold:
        return False

    conn = db._get_conn()
    try:
        existing = conn.execute(
            "SELECT 1 FROM knowledge_base WHERE cluster_id = ?", (cluster_id,)
        ).fetchone()
        if existing:
            return False

        cluster = conn.execute(
            "SELECT representative_question FROM question_clusters WHERE id = ?",
            (cluster_id,)
        ).fetchone()
        if not cluster:
            return False

        db.add_knowledge_entry(
            question=cluster["representative_question"],
            answer="[AUTO-GENERATED — needs admin review. This question has been asked 5+ times. "
                   "Use /faq-approve to set the answer, or /faq-delete to dismiss.]",
            source="auto",
            approved=False,
            cluster_id=cluster_id,
        )
        return True
    finally:
        conn.close()
