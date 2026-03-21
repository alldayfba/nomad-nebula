"""Nova Student Learning Engine — learns from every student interaction."""

from __future__ import annotations

import json
import sqlite3
import time as _time
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).parent.parent.parent / ".tmp" / "discord" / "nova_student_learning.db"


class StudentLearningEngine:
    """Tracks student question patterns to improve Nova's responses."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                topic TEXT,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                feedback TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS topic_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL UNIQUE,
                question_count INTEGER DEFAULT 1,
                last_asked TEXT DEFAULT (datetime('now')),
                sample_questions TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_student_interactions_user ON interactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_student_interactions_topic ON interactions(topic);
        """)
        self.conn.commit()

    def log_interaction(self, user_id: str, user_name: str, question: str, answer: str,
                        tokens_in: int = 0, tokens_out: int = 0) -> int:
        topic = self._classify_topic(question)
        cur = self.conn.execute(
            "INSERT INTO interactions (user_id, user_name, question, answer, topic, tokens_in, tokens_out) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, user_name, question[:2000], answer[:4000], topic, tokens_in, tokens_out)
        )
        self.conn.commit()
        self._update_topic_pattern(topic, question)
        return cur.lastrowid

    def get_contextual_insights(self, question: str) -> str:
        """Get learned insights relevant to a question."""
        parts = []
        hot = self.conn.execute(
            "SELECT topic, question_count FROM topic_patterns ORDER BY question_count DESC LIMIT 5"
        ).fetchall()
        if hot:
            parts.append("**Most asked topics in this community:**")
            for h in hot:
                parts.append(f"- {h['topic'].replace('_', ' ').title()} ({h['question_count']} questions)")
        return "\n".join(parts) if parts else ""

    def get_stats(self) -> Dict:
        total = self.conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        unique_users = self.conn.execute("SELECT COUNT(DISTINCT user_id) FROM interactions").fetchone()[0]
        top_topics = self.conn.execute(
            "SELECT topic, question_count FROM topic_patterns ORDER BY question_count DESC LIMIT 5"
        ).fetchall()
        return {
            "total_interactions": total,
            "unique_users": unique_users,
            "top_topics": [{"topic": t["topic"], "count": t["question_count"]} for t in top_topics],
        }

    def _classify_topic(self, question: str) -> str:
        q = question.lower()
        topics = {
            "sourcing": ["source", "sourcing", "find product", "supplier", "wholesale", "retailer", "clearance"],
            "keepa": ["keepa", "keepa graph", "sales rank", "bsr", "price history"],
            "selleramp": ["selleramp", "seller amp", "sas", "scan", "profitability"],
            "ungating": ["ungate", "ungating", "restricted", "approval", "brand approval"],
            "prep_ship": ["prep", "shipping", "fba label", "ship to amazon", "prep center", "fnsku"],
            "listing": ["listing", "list product", "create listing", "asin", "upc", "barcode"],
            "pricing": ["price", "pricing", "reprice", "bqool", "buy box", "competitive"],
            "profit_calc": ["profit", "roi", "margin", "fees", "fba fees", "calculator"],
            "account": ["account", "suspension", "appeal", "policy", "health", "metrics"],
            "tools": ["tool", "software", "app", "extension", "chrome"],
            "getting_started": ["start", "beginner", "new to", "first", "how to begin", "getting started"],
            "scaling": ["scale", "scaling", "grow", "va", "hire", "outsource", "automate"],
            "wholesale": ["wholesale", "brand direct", "distributor", "authorized"],
            "arbitrage": ["arbitrage", "online arbitrage", "oa", "retail arbitrage", "ra"],
            "private_label": ["private label", "pl", "brand", "own brand", "manufacture"],
        }
        for topic, keywords in topics.items():
            if any(kw in q for kw in keywords):
                return topic
        return "general"

    def _update_topic_pattern(self, topic: str, question: str):
        existing = self.conn.execute(
            "SELECT id, question_count, sample_questions FROM topic_patterns WHERE topic = ?",
            (topic,)
        ).fetchone()
        if existing:
            samples = json.loads(existing['sample_questions'] or '[]')
            if len(samples) < 10:
                samples.append(question[:200])
            self.conn.execute(
                "UPDATE topic_patterns SET question_count = question_count + 1, "
                "last_asked = datetime('now'), sample_questions = ? WHERE id = ?",
                (json.dumps(samples), existing['id'])
            )
        else:
            self.conn.execute(
                "INSERT INTO topic_patterns (topic, sample_questions) VALUES (?, ?)",
                (topic, json.dumps([question[:200]]))
            )
        self.conn.commit()
