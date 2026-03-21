from __future__ import annotations
"""
Feedback Engine — The self-improving brain of the sourcing system.

Collects three types of signals:
1. Product review rejections (auto — from product_review_agent.py)
2. Student outcome feedback (manual + auto — did the deal make money?)
3. Retailer health signals (auto — from self_healing_monitor.py)

Analyzes these signals and produces:
- Updated confidence thresholds (if too many false positives)
- Updated brand risk flags (if a brand keeps producing bad matches)
- Retailer reliability scores (if a retailer keeps failing)
- Proposed directive updates (queued for Training Officer review)

Runs: automatically after every scan + as a daily cron job
"""
import os
import sys
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sourcing", "feedback.db")


# ─────────────────────────────────────────────
# DB SETUP
# ─────────────────────────────────────────────
def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS rejection_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT, retailer TEXT, retail_title TEXT, amazon_title TEXT,
        match_method TEXT, match_confidence REAL,
        issues TEXT, fix_suggestion TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS student_outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT NOT NULL, retailer TEXT,
        predicted_roi REAL, actual_roi REAL,
        feedback_type TEXT NOT NULL,
        notes TEXT,
        submitted_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS retailer_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        retailer TEXT NOT NULL,
        event_type TEXT NOT NULL,
        product_count INTEGER DEFAULT 0,
        error_detail TEXT,
        recorded_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS system_improvements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        improvement_type TEXT,
        description TEXT, old_value TEXT, new_value TEXT,
        auto_applied INTEGER DEFAULT 0,
        applied_at TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rejections_asin ON rejection_events(asin)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_type ON student_outcomes(feedback_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_retailer_health ON retailer_health(retailer, event_type)")
    conn.commit()
    return conn


# ─────────────────────────────────────────────
# RECORD FUNCTIONS
# ─────────────────────────────────────────────
def record_rejection(asin, retail_title, amazon_title, retailer,
                      issues, fix_suggestion, match_method="",
                      match_confidence=0):
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO rejection_events (asin, retailer, retail_title, amazon_title, match_method, match_confidence, issues, fix_suggestion) VALUES (?,?,?,?,?,?,?,?)",
            (asin, retailer, retail_title[:200], amazon_title[:200], match_method, match_confidence, json.dumps(issues), fix_suggestion[:300])
        )


def record_student_outcome(asin, retailer, predicted_roi,
                             actual_roi, feedback_type, notes=""):
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO student_outcomes (asin, retailer, predicted_roi, actual_roi, feedback_type, notes) VALUES (?,?,?,?,?,?)",
            (asin, retailer, predicted_roi, actual_roi, feedback_type, notes[:500])
        )


def record_retailer_event(retailer, event_type, product_count=0,
                           error_detail=""):
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO retailer_health (retailer, event_type, product_count, error_detail) VALUES (?,?,?,?)",
            (retailer, event_type, product_count, error_detail[:200])
        )


# ─────────────────────────────────────────────
# ANALYSIS
# ─────────────────────────────────────────────
def analyze_rejection_patterns(days=7):
    """Find systematic issues causing rejections."""
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    # Total rejections
    total = conn.execute("SELECT COUNT(*) FROM rejection_events WHERE created_at > ?", (cutoff,)).fetchone()[0]

    # Rejections by retailer
    by_retailer = dict(conn.execute(
        "SELECT retailer, COUNT(*) FROM rejection_events WHERE created_at > ? GROUP BY retailer ORDER BY COUNT(*) DESC LIMIT 10",
        (cutoff,)
    ).fetchall())

    # Rejections by match method
    by_method = dict(conn.execute(
        "SELECT match_method, COUNT(*) FROM rejection_events WHERE created_at > ? GROUP BY match_method",
        (cutoff,)
    ).fetchall())

    # Most common issues
    all_issues = conn.execute(
        "SELECT issues FROM rejection_events WHERE created_at > ?", (cutoff,)
    ).fetchall()
    issue_counts = {}
    for row in all_issues:
        for issue in json.loads(row[0] or "[]"):
            key = issue[:80]
            issue_counts[key] = issue_counts.get(key, 0) + 1
    top_issues = dict(sorted(issue_counts.items(), key=lambda x: -x[1])[:10])

    conn.close()
    return {
        "total_rejections": total,
        "by_retailer": by_retailer,
        "by_match_method": by_method,
        "top_issues": top_issues,
    }


def analyze_student_outcomes(days=30):
    """Analyze how accurate our predictions are."""
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    outcomes = conn.execute(
        "SELECT feedback_type, COUNT(*), AVG(predicted_roi), AVG(actual_roi) FROM student_outcomes WHERE submitted_at > ? GROUP BY feedback_type",
        (cutoff,)
    ).fetchall()
    conn.close()

    result = {}
    for feedback_type, count, avg_predicted, avg_actual in outcomes:
        result[feedback_type] = {
            "count": count,
            "avg_predicted_roi": round(avg_predicted or 0, 1),
            "avg_actual_roi": round(avg_actual or 0, 1),
            "prediction_error": round((avg_actual or 0) - (avg_predicted or 0), 1),
        }
    return result


def analyze_retailer_health(days=7):
    """Score each retailer's reliability."""
    conn = _get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    rows = conn.execute(
        "SELECT retailer, event_type, COUNT(*) FROM retailer_health WHERE recorded_at > ? GROUP BY retailer, event_type",
        (cutoff,)
    ).fetchall()
    conn.close()

    health = {}
    for retailer, event_type, count in rows:
        if retailer not in health:
            health[retailer] = {"success": 0, "timeout": 0, "zero_results": 0, "selector_fail": 0}
        health[retailer][event_type] = count

    # Compute reliability score
    scored = {}
    for retailer, events in health.items():
        total = sum(events.values())
        successes = events.get("success", 0)
        score = round(successes / total * 100, 0) if total > 0 else 0
        scored[retailer] = dict(list(events.items()) + [("reliability_score", score), ("total_events", total)])

    return dict(sorted(scored.items(), key=lambda x: x[1]["reliability_score"]))


# ─────────────────────────────────────────────
# AUTO-IMPROVEMENT PROPOSALS
# ─────────────────────────────────────────────
def generate_improvement_proposals():
    """
    Analyze all feedback and generate specific improvement proposals.
    Low-risk proposals are auto-applied. High-risk ones go to Training Officer.
    """
    proposals = []

    # Check rejection patterns
    rejections = analyze_rejection_patterns(days=7)
    total_rejections = rejections["total_rejections"]

    if total_rejections > 50:
        # High rejection rate — check for systematic issues
        top_issue = next(iter(rejections["top_issues"]), "")
        if "brand" in top_issue.lower():
            proposals.append({
                "type": "matching_rule",
                "description": f"High brand mismatch rate ({total_rejections} rejections in 7d). Consider tightening brand gate.",
                "auto_apply": False,
                "directive": "amazon-sourcing-sop.md",
                "suggested_change": "Add stricter brand normalization (handle brand abbreviations, parent brands)",
            })

        # Check if specific retailers are causing most rejections
        for retailer, count in rejections["by_retailer"].items():
            if total_rejections > 0 and count / total_rejections > 0.4:
                proposals.append({
                    "type": "retailer_flag",
                    "description": f"{retailer} causing {count}/{total_rejections} rejections ({count/total_rejections:.0%}). May need selector update.",
                    "auto_apply": False,
                    "directive": "amazon-sourcing-sop.md",
                })

    # Check retailer health
    health = analyze_retailer_health(days=7)
    for retailer, data in health.items():
        if data["reliability_score"] < 30 and data["total_events"] >= 5:
            proposals.append({
                "type": "retailer_health",
                "description": f"{retailer} has {data['reliability_score']:.0f}% reliability score ({data['total_events']} events). Auto-deprioritizing.",
                "auto_apply": True,  # Safe to auto-apply — just deprioritize
                "action": f"Move {retailer} to lower priority in retailer_registry.py",
            })

    # Check student outcomes
    outcomes = analyze_student_outcomes(days=30)
    false_matches = outcomes.get("false_match", {}).get("count", 0)
    if false_matches >= 3:
        proposals.append({
            "type": "match_quality",
            "description": f"{false_matches} false matches reported by students in last 30 days. Consider raising confidence threshold.",
            "auto_apply": False,
            "suggested_change": "Raise MIN_CONFIDENCE from 0.70 to 0.75",
        })

    # Record proposals
    conn = _get_conn()
    for p in proposals:
        conn.execute(
            "INSERT INTO system_improvements (improvement_type, description, auto_applied) VALUES (?,?,?)",
            (p["type"], p["description"], 1 if p.get("auto_apply") else 0)
        )
    conn.commit()
    conn.close()

    logger.info(
        f"Generated {len(proposals)} improvement proposals "
        f"({sum(1 for p in proposals if p.get('auto_apply'))} auto-apply)"
    )
    return proposals


def run_daily_feedback_cycle():
    """
    Full daily feedback analysis cycle.
    Call this from a cron job or after every N scans.
    """
    logger.info("Running daily feedback cycle...")

    rejections = analyze_rejection_patterns(days=7)
    outcomes = analyze_student_outcomes(days=30)
    health = analyze_retailer_health(days=7)
    proposals = generate_improvement_proposals()

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "rejection_analysis": rejections,
        "student_outcome_analysis": outcomes,
        "retailer_health": health,
        "improvement_proposals": proposals,
        "summary": (
            f"{rejections['total_rejections']} rejections (7d), "
            f"{sum(v.get('count', 0) for v in outcomes.values())} student outcomes (30d), "
            f"{len(proposals)} improvement proposals"
        ),
    }

    # Write report to .tmp for Training Officer to read
    report_path = os.path.join(os.path.dirname(__file__), "..", ".tmp", "feedback_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Feedback cycle complete: {report['summary']}")
    return report


if __name__ == "__main__":
    report = run_daily_feedback_cycle()
    print(json.dumps(report, indent=2))
