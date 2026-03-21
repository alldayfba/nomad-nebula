"""Nova Sales Learning Engine — self-evolving knowledge from every interaction."""

from __future__ import annotations

import json
import os
import sqlite3
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent.parent.parent / ".tmp" / "discord" / "nova_sales_learning.db"


class LearningEngine:
    """Tracks patterns, learns from outcomes, evolves knowledge base."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """Create tables for learning data."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                topic TEXT,
                intent TEXT,
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
                sample_questions TEXT,
                auto_answer TEXT,
                confidence REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS sales_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rep_name TEXT,
                prospect_name TEXT,
                offer TEXT,
                outcome TEXT,
                objections TEXT,
                objection_notes TEXT,
                revenue REAL DEFAULT 0,
                report_date TEXT,
                coaching_notes TEXT,
                synced_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern TEXT NOT NULL,
                insight TEXT NOT NULL,
                source TEXT,
                confidence REAL DEFAULT 0.5,
                times_validated INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rep_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rep_name TEXT NOT NULL UNIQUE,
                strengths TEXT,
                weaknesses TEXT,
                common_objections TEXT,
                close_rate REAL,
                show_rate REAL,
                coaching_history TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_interactions_topic ON interactions(topic);
            CREATE INDEX IF NOT EXISTS idx_outcomes_rep ON sales_outcomes(rep_name);
            CREATE INDEX IF NOT EXISTS idx_patterns_type ON learned_patterns(pattern_type);
        """)
        self.conn.commit()

    def log_interaction(self, user_id: str, user_name: str, question: str, answer: str,
                        tokens_in: int = 0, tokens_out: int = 0) -> int:
        """Log every Q&A interaction for pattern mining."""
        topic = self._classify_topic(question)
        intent = self._classify_intent(question)

        cur = self.conn.execute(
            "INSERT INTO interactions (user_id, user_name, question, answer, topic, intent, tokens_in, tokens_out) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, user_name, question[:2000], answer[:4000], topic, intent, tokens_in, tokens_out)
        )
        self.conn.commit()

        # Update topic patterns
        self._update_topic_pattern(topic, question)

        return cur.lastrowid

    def record_feedback(self, interaction_id: int, feedback: str):
        """Record thumbs up/down feedback on an interaction."""
        self.conn.execute(
            "UPDATE interactions SET feedback = ? WHERE id = ?",
            (feedback, interaction_id)
        )
        self.conn.commit()

    def sync_sales_outcomes(self, eoc_reports: List[Dict], member_map: Dict[str, str]):
        """Sync EOC reports into learning DB for pattern analysis.

        Uses sync_state to track last synced date and skip already-processed reports,
        preventing count inflation from repeated INSERT OR REPLACE calls.
        """
        # Check last sync date to avoid re-processing
        last_sync = self.conn.execute(
            "SELECT value FROM sync_state WHERE key = 'last_eoc_sync_date'"
        ).fetchone()
        last_date = last_sync[0] if last_sync else "2000-01-01"

        # Filter to only new reports
        new_reports = [r for r in eoc_reports if (r.get("report_date") or "") > last_date]
        if not new_reports:
            return

        for report in new_reports:
            rep_name = member_map.get(report.get("team_member_id", ""), "Unknown")
            self.conn.execute("""
                INSERT OR REPLACE INTO sales_outcomes
                (rep_name, prospect_name, offer, outcome, objections, objection_notes,
                 revenue, report_date, coaching_notes, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                rep_name,
                report.get("prospect_name", ""),
                report.get("offer", ""),
                report.get("outcome", ""),
                json.dumps(report.get("objections", [])),
                report.get("objection_notes", ""),
                float(report.get("revenue_collected", 0) or 0),
                report.get("report_date", ""),
                report.get("coaching_notes", ""),
            ))

        # Update sync state with latest date processed
        latest_date = max(r.get("report_date", "") for r in new_reports)
        self.conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('last_eoc_sync_date', ?, datetime('now'))",
            (latest_date,)
        )
        self.conn.commit()

        # Mine patterns after sync
        self._mine_objection_patterns()
        self._mine_rep_profiles()

    def get_contextual_insights(self, question: str) -> str:
        """Get learned insights relevant to a question. Injected into system prompt."""
        topic = self._classify_topic(question)
        parts = []

        # Get hot topics (what the team asks about most)
        hot = self.conn.execute(
            "SELECT topic, question_count FROM topic_patterns ORDER BY question_count DESC LIMIT 5"
        ).fetchall()
        if hot:
            parts.append("**Hot topics this team asks about:**")
            for h in hot:
                parts.append(f"- {h['topic']} ({h['question_count']} questions)")

        # Get relevant learned patterns
        patterns = self.conn.execute(
            "SELECT pattern, insight, confidence FROM learned_patterns "
            "WHERE pattern_type = ? OR pattern_type = 'general' "
            "ORDER BY confidence DESC, times_validated DESC LIMIT 5",
            (topic,)
        ).fetchall()
        if patterns:
            parts.append("\n**Learned patterns from real sales data:**")
            for p in patterns:
                parts.append(f"- {p['insight']} (confidence: {p['confidence']:.0%})")

        # Get recent outcomes summary
        recent = self.conn.execute(
            "SELECT outcome, COUNT(*) as cnt, SUM(revenue) as rev "
            "FROM sales_outcomes WHERE synced_at > datetime('now', '-7 days') "
            "GROUP BY outcome ORDER BY cnt DESC"
        ).fetchall()
        if recent:
            parts.append("\n**Last 7 days outcomes:**")
            for r in recent:
                parts.append(f"- {r['outcome']}: {r['cnt']}x (${r['rev']:,.0f} revenue)")

        # Get top objections from real calls
        objections = self.conn.execute(
            "SELECT objections FROM sales_outcomes WHERE objections != '[]' AND objections IS NOT NULL "
            "AND synced_at > datetime('now', '-30 days')"
        ).fetchall()
        if objections:
            obj_counts = {}
            for row in objections:
                try:
                    objs = json.loads(row['objections'])
                    for o in objs:
                        o_clean = o.strip().lower() if isinstance(o, str) else str(o).lower()
                        if o_clean and o_clean != '[]':
                            obj_counts[o_clean] = obj_counts.get(o_clean, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass
            if obj_counts:
                sorted_objs = sorted(obj_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                parts.append("\n**Real objections from recent calls (ranked by frequency):**")
                for obj, cnt in sorted_objs:
                    parts.append(f"- \"{obj}\" -- {cnt}x")

        # Get rep-specific context if question mentions a name
        q_lower = question.lower()
        reps = self.conn.execute("SELECT * FROM rep_profiles").fetchall()
        for rep in reps:
            if rep['rep_name'].lower() in q_lower:
                parts.append(f"\n**{rep['rep_name']} profile:**")
                if rep['strengths']:
                    parts.append(f"- Strengths: {rep['strengths']}")
                if rep['weaknesses']:
                    parts.append(f"- Areas to improve: {rep['weaknesses']}")
                if rep['close_rate']:
                    parts.append(f"- Close rate: {rep['close_rate']:.1f}%")

        return "\n".join(parts) if parts else ""

    def _classify_topic(self, question: str) -> str:
        """Simple keyword-based topic classification."""
        q = question.lower()
        topics = {
            "objection_handling": ["objection", "handle", "rebut", "overcome", "pushback", "they said"],
            "closing": ["close", "closing", "seal the deal", "ask for the sale", "commitment"],
            "discovery": ["discovery", "nepq", "question", "needs", "pain point", "excavate"],
            "scripts": ["script", "word track", "what do i say", "how do i say", "opening", "opener"],
            "pipeline": ["pipeline", "kpi", "numbers", "how many", "stats", "performance", "revenue"],
            "training": ["training", "roleplay", "role play", "practice", "drill", "scenario"],
            "preframe": ["preframe", "pre-frame", "frame", "positioning", "before the call"],
            "follow_up": ["follow up", "no show", "no-show", "didn't show", "ghost", "text", "reach out"],
            "offer": ["offer", "pricing", "investment", "package", "tier", "inner circle", "semi"],
            "tonality": ["tone", "tonality", "voice", "energy", "pace", "inflection"],
            "mindset": ["mindset", "motivation", "confidence", "belief", "fear", "scared", "nervous"],
            "ads": ["ads", "creative", "cpm", "ctr", "meta", "facebook", "campaign", "roas"],
            "setter": ["setter", "setting", "book", "booking", "appointment", "qualify"],
        }
        for topic, keywords in topics.items():
            if any(kw in q for kw in keywords):
                return topic
        return "general"

    def _classify_intent(self, question: str) -> str:
        """Classify what the user wants."""
        q = question.lower()
        if any(w in q for w in ["how do i", "how to", "what should i", "help me", "teach me"]):
            return "how_to"
        if any(w in q for w in ["what is", "what's", "explain", "define", "what does"]):
            return "definition"
        if any(w in q for w in ["roleplay", "role play", "practice", "simulate", "pretend"]):
            return "roleplay"
        if any(w in q for w in ["how many", "stats", "numbers", "data", "performance", "kpi"]):
            return "data_query"
        if any(w in q for w in ["review", "feedback", "coach", "improve", "what went wrong"]):
            return "coaching"
        return "general"

    def _update_topic_pattern(self, topic: str, question: str):
        """Track topic frequency and sample questions."""
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

    def _mine_objection_patterns(self):
        """Mine objection patterns from sales outcomes."""
        rows = self.conn.execute(
            "SELECT objections, outcome, revenue FROM sales_outcomes "
            "WHERE objections IS NOT NULL AND objections != '[]'"
        ).fetchall()

        obj_outcomes = {}
        for row in rows:
            try:
                objs = json.loads(row['objections'])
                for o in objs:
                    o_clean = o.strip().lower() if isinstance(o, str) else str(o).lower()
                    if not o_clean or o_clean == '[]':
                        continue
                    if o_clean not in obj_outcomes:
                        obj_outcomes[o_clean] = {"total": 0, "closed": 0, "revenue": 0}
                    obj_outcomes[o_clean]["total"] += 1
                    if row["outcome"] == "showed_closed":
                        obj_outcomes[o_clean]["closed"] += 1
                        obj_outcomes[o_clean]["revenue"] += float(row["revenue"] or 0)
            except (json.JSONDecodeError, TypeError):
                pass

        for obj, stats in obj_outcomes.items():
            close_rate = (stats["closed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            insight = (
                f'Objection "{obj}" appeared {stats["total"]}x. '
                f'Close rate when this objection comes up: {close_rate:.0f}%. '
                f'Revenue from deals with this objection: ${stats["revenue"]:,.0f}'
            )
            self.conn.execute("""
                INSERT INTO learned_patterns (pattern_type, pattern, insight, source, confidence)
                VALUES ('objection_handling', ?, ?, 'eoc_mining', ?)
                ON CONFLICT DO UPDATE SET
                    insight = excluded.insight,
                    confidence = excluded.confidence,
                    times_validated = times_validated + 1,
                    updated_at = datetime('now')
            """, (obj, insight, min(stats["total"] / 10.0, 1.0)))

        self.conn.commit()

    def _mine_rep_profiles(self):
        """Build/update rep profiles from outcome data."""
        reps = self.conn.execute(
            "SELECT rep_name, "
            "COUNT(*) as total_calls, "
            "SUM(CASE WHEN outcome = 'showed_closed' THEN 1 ELSE 0 END) as closed, "
            "SUM(CASE WHEN outcome = 'no_show' THEN 1 ELSE 0 END) as no_shows, "
            "SUM(CASE WHEN outcome IN ('showed_closed', 'showed_not_closed') THEN 1 ELSE 0 END) as showed, "
            "SUM(revenue) as total_revenue, "
            "GROUP_CONCAT(DISTINCT objections) as all_objections "
            "FROM sales_outcomes GROUP BY rep_name"
        ).fetchall()

        for rep in reps:
            if not rep['rep_name'] or rep['rep_name'] == 'Unknown':
                continue
            showed = rep['showed'] or 0
            total = rep['total_calls'] or 0
            closed = rep['closed'] or 0
            close_rate = (closed / showed * 100) if showed > 0 else 0
            show_rate = ((total - (rep['no_shows'] or 0)) / total * 100) if total > 0 else 0

            # Determine strengths/weaknesses
            strengths = []
            weaknesses = []
            if close_rate >= 30:
                strengths.append("Strong closer")
            elif close_rate > 0:
                weaknesses.append(f"Close rate at {close_rate:.0f}% (target: 30%+)")
            if show_rate >= 75:
                strengths.append("High show rate")
            elif show_rate < 60:
                weaknesses.append(f"Show rate at {show_rate:.0f}% (target: 75%+)")

            self.conn.execute("""
                INSERT INTO rep_profiles (rep_name, strengths, weaknesses, close_rate, show_rate, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(rep_name) DO UPDATE SET
                    strengths = excluded.strengths,
                    weaknesses = excluded.weaknesses,
                    close_rate = excluded.close_rate,
                    show_rate = excluded.show_rate,
                    updated_at = datetime('now')
            """, (
                rep['rep_name'],
                ", ".join(strengths) if strengths else None,
                ", ".join(weaknesses) if weaknesses else None,
                close_rate,
                show_rate,
            ))
        self.conn.commit()

    def get_stats(self) -> Dict:
        """Return learning engine stats."""
        total_interactions = self.conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        total_outcomes = self.conn.execute("SELECT COUNT(*) FROM sales_outcomes").fetchone()[0]
        total_patterns = self.conn.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0]
        total_reps = self.conn.execute("SELECT COUNT(*) FROM rep_profiles").fetchone()[0]
        top_topics = self.conn.execute(
            "SELECT topic, question_count FROM topic_patterns ORDER BY question_count DESC LIMIT 5"
        ).fetchall()

        return {
            "total_interactions": total_interactions,
            "total_outcomes_tracked": total_outcomes,
            "learned_patterns": total_patterns,
            "rep_profiles": total_reps,
            "top_topics": [{"topic": t["topic"], "count": t["question_count"]} for t in top_topics],
        }
