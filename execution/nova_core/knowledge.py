"""Unified knowledge system — question tracking, keyword clustering, FAQ injection.

Ported from discord_bot/knowledge.py. Now cross-platform with shared nova.db.
"""

from __future__ import annotations

import re

from . import database as db

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

CATEGORY_KEYWORDS = {
    "sourcing": {"sourcing", "source", "supplier", "wholesale", "oa", "arbitrage", "product", "find", "buy"},
    "ppc": {"ppc", "ads", "advertising", "acos", "campaign", "keyword", "bid", "sponsored", "tacos"},
    "listing": {"listing", "title", "bullet", "description", "image", "photo", "seo", "keyword", "a+"},
    "pricing": {"price", "pricing", "profit", "margin", "fee", "cost", "roi", "revenue"},
    "shipping": {"shipping", "fba", "fbm", "freight", "logistics", "inventory", "prep", "label"},
    "account": {"account", "suspension", "appeal", "trademark", "brand", "registry", "ip"},
    "sales": {"close", "closer", "objection", "pipeline", "lead", "call", "booking", "revenue", "commission"},
}


def extract_keywords(text: str, max_keywords: int = 5) -> str:
    """Extract top keywords from text. Returns comma-separated string."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    seen: set[str] = set()
    unique: list[str] = []
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


def _jaccard_similarity(kw1: str, kw2: str) -> float:
    """Compute Jaccard similarity between two comma-separated keyword strings."""
    set1 = set(kw1.split(","))
    set2 = set(kw2.split(","))
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)


def track_question(user_id: str, question: str, platform: str = "discord") -> tuple[int, int]:
    """Track a user question: extract keywords, find/create cluster, log it.

    Returns (cluster_id, cluster_frequency).
    """
    keywords = extract_keywords(question)
    if not keywords:
        keywords = "general"

    category = detect_category(question)
    conn = db.get_conn()

    # Find matching cluster (Jaccard ≥ 0.6)
    clusters = conn.execute(
        "SELECT id, keywords, frequency FROM question_clusters"
    ).fetchall()

    best_cluster_id = None
    best_similarity = 0.0

    for cluster in clusters:
        sim = _jaccard_similarity(keywords, cluster["keywords"])
        if sim > best_similarity and sim >= 0.6:
            best_similarity = sim
            best_cluster_id = cluster["id"]

    if best_cluster_id:
        conn.execute(
            "UPDATE question_clusters SET frequency = frequency + 1, last_asked = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (best_cluster_id,),
        )
        frequency = conn.execute(
            "SELECT frequency FROM question_clusters WHERE id = ?",
            (best_cluster_id,),
        ).fetchone()["frequency"]
    else:
        cursor = conn.execute(
            "INSERT INTO question_clusters (representative_question, keywords, category) VALUES (?, ?, ?)",
            (question[:500], keywords, category),
        )
        best_cluster_id = cursor.lastrowid
        frequency = 1

    conn.execute(
        "INSERT INTO question_tracker (cluster_id, user_id, platform, raw_question, keywords) "
        "VALUES (?, ?, ?, ?, ?)",
        (best_cluster_id, user_id, platform, question[:1000], keywords),
    )
    conn.commit()

    return best_cluster_id, frequency


def get_relevant_faq(query: str, limit: int = 3) -> list[dict]:
    """Find approved FAQ entries relevant to a query.

    Returns list of dicts with 'question' and 'answer' keys.
    """
    keywords = extract_keywords(query)
    if not keywords:
        return []

    conn = db.get_conn()
    entries = conn.execute(
        "SELECT id, question, answer FROM knowledge_base WHERE approved = 1"
    ).fetchall()

    # Rank by keyword overlap against question text
    scored: list[tuple[float, dict]] = []
    query_kws = set(keywords.split(","))

    for entry in entries:
        q_lower = entry["question"].lower()
        text_match = sum(1 for kw in query_kws if kw in q_lower)
        # Extract keywords from the FAQ question for overlap scoring
        entry_kws = set(extract_keywords(entry["question"]).split(","))
        kw_overlap = len(query_kws & entry_kws)
        score = kw_overlap + text_match * 0.5

        if score > 0:
            scored.append((score, {"question": entry["question"], "answer": entry["answer"]}))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def build_knowledge_block(entries: list[dict]) -> str:
    """Format FAQ entries into an XML block for the system prompt."""
    if not entries:
        return ""

    lines = [
        "<knowledge_base>",
        "These are verified answers to common questions. Use them when relevant:",
        "",
    ]

    for entry in entries:
        lines.append(f"Q: {entry['question']}")
        lines.append(f"A: {entry['answer']}")
        lines.append("")

    lines.append("</knowledge_base>")
    return "\n".join(lines)


def maybe_auto_generate_faq(cluster_id: int, frequency: int, threshold: int = 5) -> bool:
    """If a cluster hits the threshold, create a candidate FAQ entry."""
    if frequency < threshold:
        return False

    conn = db.get_conn()

    existing = conn.execute(
        "SELECT 1 FROM knowledge_base WHERE cluster_id = ?", (cluster_id,)
    ).fetchone()
    if existing:
        return False

    cluster = conn.execute(
        "SELECT representative_question FROM question_clusters WHERE id = ?",
        (cluster_id,),
    ).fetchone()
    if not cluster:
        return False

    conn.execute(
        "INSERT INTO knowledge_base (cluster_id, question, answer, source, approved) "
        "VALUES (?, ?, ?, 'auto', 0)",
        (
            cluster_id,
            cluster["representative_question"],
            "[AUTO-GENERATED — needs admin review. This question has been asked 5+ times. "
            "Use /faq-approve to set the answer, or /faq-delete to dismiss.]",
        ),
    )
    conn.commit()
    return True


def get_knowledge_stats() -> dict:
    """Get knowledge base stats for the digest."""
    conn = db.get_conn()

    approved = conn.execute("SELECT COUNT(*) as cnt FROM knowledge_base WHERE approved = 1").fetchone()["cnt"]
    pending = conn.execute("SELECT COUNT(*) as cnt FROM knowledge_base WHERE approved = 0").fetchone()["cnt"]

    top_clusters = conn.execute(
        "SELECT representative_question, frequency, category FROM question_clusters "
        "ORDER BY frequency DESC LIMIT 5"
    ).fetchall()

    platform_counts = conn.execute(
        "SELECT platform, COUNT(*) as cnt FROM question_tracker "
        "WHERE asked_at > datetime('now', '-24 hours') GROUP BY platform"
    ).fetchall()

    return {
        "approved_faq": approved,
        "pending_faq": pending,
        "top_questions": [
            {"question": r["representative_question"], "frequency": r["frequency"], "category": r["category"]}
            for r in top_clusters
        ],
        "questions_24h": {r["platform"]: r["cnt"] for r in platform_counts},
    }
