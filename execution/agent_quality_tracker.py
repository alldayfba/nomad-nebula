#!/usr/bin/env python3
"""
Script: agent_quality_tracker.py
Purpose: Track agent output quality over time, detect drift, and auto-generate
         improvement proposals when quality drops.

Usage:
  python execution/agent_quality_tracker.py --score CEO --output "CEO brief" --rating 8
  python execution/agent_quality_tracker.py --score outreach --output "Dream 100 email" --rating 6 --notes "Too generic"
  python execution/agent_quality_tracker.py --report
  python execution/agent_quality_tracker.py --report --agent CEO
  python execution/agent_quality_tracker.py --drift
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula"
))

TMP_DIR = PROJECT_ROOT / ".tmp" / "training-officer"
QUALITY_FILE = TMP_DIR / "quality-scores.json"
PROPOSALS_DIR = TMP_DIR / "proposals"


def ensure_dirs():
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)


def load_scores() -> list:
    """Load all quality scores."""
    if QUALITY_FILE.exists():
        return json.loads(QUALITY_FILE.read_text())
    return []


def save_scores(scores: list):
    """Save quality scores."""
    QUALITY_FILE.write_text(json.dumps(scores, indent=2, default=str))


def add_score(agent: str, output_type: str, rating: int, notes: str = ""):
    """Add a quality score for an agent output."""
    scores = load_scores()
    scores.append({
        "agent": agent,
        "output_type": output_type,
        "rating": rating,
        "notes": notes,
        "timestamp": datetime.now().isoformat(),
    })
    save_scores(scores)
    print(f"[quality-tracker] Scored {agent}/{output_type}: {rating}/10" + (f" — {notes}" if notes else ""))


def get_agent_scores(scores: list, agent: str) -> list:
    """Filter scores for a specific agent."""
    return [s for s in scores if s["agent"].lower() == agent.lower()]


def compute_stats(agent_scores: list) -> dict:
    """Compute stats for an agent's scores."""
    if not agent_scores:
        return {"avg": 0, "min": 0, "max": 0, "count": 0, "trend": "N/A"}

    ratings = [s["rating"] for s in agent_scores]
    avg = sum(ratings) / len(ratings)

    # Trend: compare last 5 vs previous 5
    trend = "stable"
    if len(ratings) >= 10:
        recent = sum(ratings[-5:]) / 5
        previous = sum(ratings[-10:-5]) / 5
        if recent < previous - 0.5:
            trend = "DECLINING"
        elif recent > previous + 0.5:
            trend = "improving"

    return {
        "avg": round(avg, 1),
        "min": min(ratings),
        "max": max(ratings),
        "count": len(ratings),
        "trend": trend,
    }


def detect_drift(scores: list) -> list:
    """Detect agents with quality drift (declining scores)."""
    agents = set(s["agent"] for s in scores)
    drifting = []

    for agent in agents:
        agent_scores = get_agent_scores(scores, agent)
        if len(agent_scores) < 5:
            continue

        stats = compute_stats(agent_scores)

        # Flag if average drops below 6 or trend is declining
        if stats["avg"] < 6.0 or stats["trend"] == "DECLINING":
            # Check for low-scoring outputs
            low_outputs = [s for s in agent_scores[-10:] if s["rating"] <= 5]
            drifting.append({
                "agent": agent,
                "avg": stats["avg"],
                "trend": stats["trend"],
                "low_count": len(low_outputs),
                "recent_issues": [s.get("notes", "") for s in low_outputs if s.get("notes")],
            })

    return drifting


def generate_drift_proposal(drift_info: dict):
    """Generate a Training Proposal for a drifting agent."""
    agent = drift_info["agent"]
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Find next proposal ID
    existing = list(PROPOSALS_DIR.glob(f"TP-{today}-*.yaml"))
    seq = len(existing) + 1
    pid = f"TP-{today}-{seq:03d}"

    issues = "; ".join(drift_info.get("recent_issues", [])[:3]) or "Quality scores declining"

    content = f"""# Training Proposal: {pid}

proposal_id: "{pid}"
created: "{now}"
status: "pending"
theme: "quality-drift"

# WHO
target_agent: "{agent}"
target_file: "auto-detect"

# WHAT
upgrade_type: "skill"
title: "Quality drift detected — {agent} agent needs attention"
description: |
  Agent {agent} has a declining quality trend. Average score: {drift_info['avg']}/10.
  {drift_info['low_count']} low-scoring outputs in recent history.
  Issues: {issues}

# WHY
trigger: "Quality tracker drift detection"
evidence: "Average score {drift_info['avg']}/10, trend: {drift_info['trend']}"
expected_impact: "Restore agent output quality to 7+ average"

# HOW
change_type: "review"
proposed_content: |
  QUALITY ALERT: Review and improve {agent} agent's output patterns.
  Focus areas: {issues}
  Consider retraining with recent high-quality examples.

# RISK
risk_level: "medium"
rollback_plan: "Revert skill file changes"
dependencies: []
"""
    proposal_path = PROPOSALS_DIR / f"{pid}.yaml"
    proposal_path.write_text(content)
    print(f"[quality-tracker] Generated drift proposal: {pid} for {agent}")
    return pid


def print_report(scores: list, agent_filter: Optional[str] = None):
    """Print quality report."""
    agents = set(s["agent"] for s in scores)
    if agent_filter:
        agents = {a for a in agents if a.lower() == agent_filter.lower()}

    print(f"\n{'=' * 60}")
    print(f"  AGENT QUALITY REPORT — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"{'=' * 60}\n")
    print(f"  {'Agent':<15s} {'Avg':<6s} {'Min':<5s} {'Max':<5s} {'Count':<7s} {'Trend':<12s}")
    print(f"  {'─' * 50}")

    for agent in sorted(agents):
        agent_scores = get_agent_scores(scores, agent)
        stats = compute_stats(agent_scores)
        trend_marker = ""
        if stats["trend"] == "DECLINING":
            trend_marker = " !!!"
        elif stats["trend"] == "improving":
            trend_marker = " +++"
        print(f"  {agent:<15s} {stats['avg']:<6.1f} {stats['min']:<5d} {stats['max']:<5d} {stats['count']:<7d} {stats['trend']}{trend_marker}")

    if agent_filter and agents:
        agent = list(agents)[0]
        agent_scores = get_agent_scores(scores, agent)
        print(f"\n  Recent scores for {agent}:")
        for s in agent_scores[-10:]:
            ts = s["timestamp"][:16]
            notes = f" — {s['notes']}" if s.get("notes") else ""
            print(f"    {ts} | {s['output_type']:20s} | {s['rating']}/10{notes}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Agent Quality Tracker")
    parser.add_argument("--score", type=str, help="Agent name to score")
    parser.add_argument("--output", type=str, help="Output type being scored")
    parser.add_argument("--rating", type=int, help="Quality rating 1-10")
    parser.add_argument("--notes", type=str, default="", help="Optional notes")
    parser.add_argument("--report", action="store_true", help="Show quality report")
    parser.add_argument("--agent", type=str, help="Filter report by agent")
    parser.add_argument("--drift", action="store_true", help="Run drift detection")
    args = parser.parse_args()

    ensure_dirs()

    if args.score:
        if not args.output or args.rating is None:
            print("[quality-tracker] --score requires --output and --rating")
            sys.exit(1)
        if args.rating < 1 or args.rating > 10:
            print("[quality-tracker] Rating must be 1-10")
            sys.exit(1)
        add_score(args.score, args.output, args.rating, args.notes)
        return

    if args.report:
        scores = load_scores()
        if not scores:
            print("[quality-tracker] No scores recorded yet.")
            return
        print_report(scores, args.agent)
        return

    if args.drift:
        scores = load_scores()
        if not scores:
            print("[quality-tracker] No scores recorded yet.")
            return
        drifting = detect_drift(scores)
        if not drifting:
            print("[quality-tracker] No quality drift detected. All agents performing well.")
            return
        print(f"[quality-tracker] Drift detected in {len(drifting)} agent(s):")
        for d in drifting:
            print(f"  {d['agent']}: avg={d['avg']}/10, trend={d['trend']}, {d['low_count']} low scores")
            generate_drift_proposal(d)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
