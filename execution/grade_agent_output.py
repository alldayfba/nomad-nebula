#!/usr/bin/env python3
"""
Script: grade_agent_output.py
Purpose: Grade any agent's output on 5 dimensions (1-10 each).
         Auto-generates Training Proposals when quality drops below threshold.
         Tracks grade history for trend analysis.
Inputs:  Agent name, output file, task type
Outputs: Grade scores JSON, trend analysis, auto-generated proposals

CLI:
    python execution/grade_agent_output.py grade --agent ads-copy --output-file .tmp/ad_copy.md --task-type ad_copy
    python execution/grade_agent_output.py trends --agent ads-copy [--days 30]
    python execution/grade_agent_output.py report [--agent ads-copy] [--days 30]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("NOMAD_NEBULA_ROOT",
                                    "/Users/Shared/antigravity/projects/nomad-nebula"))
GRADE_HISTORY_PATH = PROJECT_ROOT / ".tmp" / "training-officer" / "grade-history.json"
PROPOSALS_DIR = PROJECT_ROOT / ".tmp" / "training-officer" / "proposals"

PASS_THRESHOLD = 35  # out of 50

# ── Grading Dimensions ──────────────────────────────────────────────────────

DIMENSIONS = {
    "specificity": "Does the output contain specific details, numbers, names, and concrete examples rather than generic statements?",
    "persuasion": "Does the output use proven persuasion techniques (social proof, urgency, specificity, objection handling)?",
    "relevance": "Does the output directly address the assigned task and ICP pain points?",
    "clarity": "Is the output clear, well-structured, and easy to follow?",
    "format_compliance": "Does the output follow the format rules specified in the agent's skills.md?",
}

TASK_TYPE_WEIGHTS = {
    "ad_copy": {"specificity": 1.2, "persuasion": 1.5, "relevance": 1.0, "clarity": 1.0, "format_compliance": 1.3},
    "email": {"specificity": 1.3, "persuasion": 1.2, "relevance": 1.3, "clarity": 1.0, "format_compliance": 1.2},
    "vsl_script": {"specificity": 1.0, "persuasion": 1.5, "relevance": 1.2, "clarity": 1.0, "format_compliance": 1.3},
    "content": {"specificity": 1.2, "persuasion": 1.0, "relevance": 1.3, "clarity": 1.3, "format_compliance": 1.2},
    "brief": {"specificity": 1.3, "persuasion": 0.8, "relevance": 1.5, "clarity": 1.2, "format_compliance": 1.2},
    "listing": {"specificity": 1.4, "persuasion": 1.2, "relevance": 1.3, "clarity": 1.0, "format_compliance": 1.1},
    "outreach": {"specificity": 1.3, "persuasion": 1.3, "relevance": 1.2, "clarity": 1.0, "format_compliance": 1.2},
    "default": {"specificity": 1.0, "persuasion": 1.0, "relevance": 1.0, "clarity": 1.0, "format_compliance": 1.0},
}

AGENT_SKILLS_MAP = {
    "ads-copy": "bots/ads-copy/skills.md",
    "content": "bots/content/skills.md",
    "outreach": "bots/outreach/skills.md",
    "amazon": "bots/amazon/skills.md",
    "sourcing": "bots/sourcing/skills.md",
    "webbuild": "SabboOS/Agents/WebBuild.md",
    "ceo": "SabboOS/Agents/CEO.md",
}


# ── Grade History ────────────────────────────────────────────────────────────

def _load_history():
    GRADE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if GRADE_HISTORY_PATH.exists():
        with open(GRADE_HISTORY_PATH) as f:
            return json.load(f)
    return []


def _save_history(history):
    GRADE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GRADE_HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def record_grade(agent, task_type, grade_result):
    history = _load_history()
    history.append({
        "agent": agent,
        "task_type": task_type,
        "scores": grade_result["scores"],
        "weighted_total": grade_result["weighted_total"],
        "passed": grade_result["passed"],
        "feedback": grade_result.get("feedback", ""),
        "output_file": grade_result.get("output_file", ""),
        "graded_at": datetime.utcnow().isoformat(),
    })
    _save_history(history)


# ── Grading ──────────────────────────────────────────────────────────────────

def grade_output(agent, output_file, task_type="default"):
    output_path = Path(output_file)
    if not output_path.exists():
        raise FileNotFoundError(f"Output file not found: {output_file}")

    output_content = output_path.read_text()[:4000]  # Cap at 4K chars for grading

    # Load agent skills for format compliance context
    skills_path = PROJECT_ROOT / AGENT_SKILLS_MAP.get(agent, f"bots/{agent}/skills.md")
    skills_excerpt = ""
    if skills_path.exists():
        skills_excerpt = skills_path.read_text()[:2000]

    weights = TASK_TYPE_WEIGHTS.get(task_type, TASK_TYPE_WEIGHTS["default"])

    # Try LLM grading first, fall back to heuristic
    try:
        scores, feedback = _grade_with_llm(agent, output_content, skills_excerpt, task_type, weights)
    except Exception as e:
        print(f"[grade_agent_output] LLM grading failed ({e}), using heuristic.", file=sys.stderr)
        scores, feedback = _grade_heuristic(output_content, weights)

    # Calculate weighted total
    weighted_total = 0
    for dim, score in scores.items():
        w = weights.get(dim, 1.0)
        weighted_total += score * w

    # Normalize to 50-point scale
    total_weight = sum(weights.values())
    normalized_total = round(weighted_total / total_weight * 5, 1)  # Scale to ~50 max
    raw_total = sum(scores.values())

    result = {
        "agent": agent,
        "task_type": task_type,
        "scores": scores,
        "raw_total": raw_total,
        "weighted_total": round(normalized_total * 10, 1),
        "max_score": 50,
        "passed": raw_total >= PASS_THRESHOLD,
        "feedback": feedback,
        "output_file": str(output_file),
    }

    # Record to history
    record_grade(agent, task_type, result)

    # Auto-generate Training Proposal if failed
    if raw_total < PASS_THRESHOLD:
        proposal_path = auto_generate_proposal(agent, result, output_file)
        result["proposal_generated"] = str(proposal_path)
        print(f"[grade_agent_output] BELOW THRESHOLD ({raw_total}/50). Training Proposal generated: {proposal_path}",
              file=sys.stderr)

    return result


def _grade_with_llm(agent, output_content, skills_excerpt, task_type, weights):
    import anthropic
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    dim_text = "\n".join(f"{i+1}. {dim.replace('_', ' ').title()} (1-10): {desc}"
                         for i, (dim, desc) in enumerate(DIMENSIONS.items()))

    prompt = f"""Grade this {task_type} output from the {agent} agent on 5 dimensions (1-10 each).

Output to grade:
---
{output_content}
---

Agent's format rules (from skills.md):
---
{skills_excerpt[:1500] if skills_excerpt else "No skills.md found for this agent."}
---

Grade each dimension:
{dim_text}

Respond with ONLY valid JSON (no markdown, no explanation):
{{"specificity": N, "persuasion": N, "relevance": N, "clarity": N, "format_compliance": N, "feedback": "1-2 sentences on the single most impactful improvement"}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Handle potential markdown wrapping
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data = json.loads(text)
    scores = {
        "specificity": max(1, min(10, int(data.get("specificity", 5)))),
        "persuasion": max(1, min(10, int(data.get("persuasion", 5)))),
        "relevance": max(1, min(10, int(data.get("relevance", 5)))),
        "clarity": max(1, min(10, int(data.get("clarity", 5)))),
        "format_compliance": max(1, min(10, int(data.get("format_compliance", 5)))),
    }
    feedback = data.get("feedback", "")
    return scores, feedback


def _grade_heuristic(content, weights):
    """Fallback heuristic grading when LLM is unavailable."""
    word_count = len(content.split())
    has_numbers = any(c.isdigit() for c in content)
    has_structure = content.count("\n#") > 0 or content.count("\n-") > 2
    line_count = content.count("\n")

    scores = {
        "specificity": 7 if has_numbers else 4,
        "persuasion": 5,  # Can't assess without LLM
        "relevance": 5,   # Can't assess without LLM
        "clarity": 7 if has_structure else 5,
        "format_compliance": 6 if line_count > 5 else 4,
    }

    # Boost for longer, more detailed output
    if word_count > 500:
        scores["specificity"] = min(10, scores["specificity"] + 1)
    if word_count < 50:
        for k in scores:
            scores[k] = max(1, scores[k] - 2)

    return scores, "Heuristic grading — LLM unavailable. Review manually for persuasion and relevance."


# ── Training Proposal Generation ─────────────────────────────────────────────

def auto_generate_proposal(agent, grade_result, output_file):
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

    # Find next sequence number
    existing = list(PROPOSALS_DIR.glob("TP-*.yaml"))
    seq = len(existing) + 1
    date_str = datetime.utcnow().strftime("%Y%m%d")
    proposal_id = f"TP-{date_str}-{seq:03d}"
    proposal_path = PROPOSALS_DIR / f"{proposal_id}.yaml"

    scores = grade_result["scores"]
    weakest = min(scores, key=scores.get)
    weakest_score = scores[weakest]

    content = f"""id: {proposal_id}
target_agent: {agent}
theme: quality_improvement
priority: high
status: pending
created_at: {datetime.utcnow().isoformat()}
source: grade_agent_output.py (auto-generated)

why: |
  Agent output scored {grade_result['raw_total']}/50 (threshold: {PASS_THRESHOLD}).
  Weakest dimension: {weakest} ({weakest_score}/10).
  Task type: {grade_result['task_type']}
  Output file: {output_file}
  Feedback: {grade_result.get('feedback', 'N/A')}

what: |
  Improve {agent} agent's {weakest.replace('_', ' ')} capability.
  Current score: {weakest_score}/10. Target: 7+/10.

how: |
  1. Review the failing output at {output_file}
  2. Identify specific patterns causing low {weakest} scores
  3. Update {agent} skills.md with improved instructions for {weakest}
  4. Add examples of good vs bad output for this dimension
  5. Re-grade after update to confirm improvement

risk: low
rollback: Revert skills.md changes
"""

    proposal_path.write_text(content)
    return proposal_path


# ── Trend Analysis ───────────────────────────────────────────────────────────

def get_trends(agent, days=30):
    history = _load_history()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    agent_grades = [g for g in history
                    if g["agent"] == agent and g["graded_at"] >= cutoff]

    if not agent_grades:
        return {"agent": agent, "period_days": days, "grades_count": 0, "message": "No grades found."}

    # Average scores per dimension
    dim_totals = {d: 0 for d in DIMENSIONS}
    for g in agent_grades:
        for d in DIMENSIONS:
            dim_totals[d] += g["scores"].get(d, 0)

    count = len(agent_grades)
    dim_avgs = {d: round(t / count, 1) for d, t in dim_totals.items()}
    avg_total = round(sum(g.get("weighted_total", sum(g["scores"].values())) for g in agent_grades) / count, 1)
    pass_rate = round(len([g for g in agent_grades if g["passed"]]) / count * 100, 1)

    # Trend: compare first half vs second half
    mid = count // 2
    if mid > 0:
        first_half_avg = sum(sum(g["scores"].values()) for g in agent_grades[:mid]) / mid
        second_half_avg = sum(sum(g["scores"].values()) for g in agent_grades[mid:]) / (count - mid)
        trend = "improving" if second_half_avg > first_half_avg + 1 else \
                "declining" if second_half_avg < first_half_avg - 1 else "stable"
    else:
        trend = "insufficient_data"

    weakest = min(dim_avgs, key=dim_avgs.get)

    return {
        "agent": agent,
        "period_days": days,
        "grades_count": count,
        "avg_total": avg_total,
        "pass_rate": pass_rate,
        "dimension_averages": dim_avgs,
        "trend": trend,
        "weakest_dimension": weakest,
        "weakest_avg": dim_avgs[weakest],
    }


def grade_report(agent=None, days=30):
    history = _load_history()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    if agent:
        agents = [agent]
    else:
        agents = sorted(set(g["agent"] for g in history if g["graded_at"] >= cutoff))

    if not agents:
        return "No grade data found."

    lines = [
        f"═══ AGENT OUTPUT QUALITY REPORT (last {days} days) ═══",
        "",
    ]

    for a in agents:
        trends = get_trends(a, days)
        if trends.get("grades_count", 0) == 0:
            continue

        trend_icon = {"improving": "^", "declining": "v", "stable": "=", "insufficient_data": "?"}.get(trends["trend"], "?")
        lines.append(f"  {a:<15} Avg: {trends['avg_total']:>5}/50 | Pass: {trends['pass_rate']:>5}% | "
                     f"Trend: {trend_icon} {trends['trend']} | Weak: {trends['weakest_dimension']} ({trends['weakest_avg']})")

    return "\n".join(lines)


# ── CLI Handlers ─────────────────────────────────────────────────────────────

def cli_grade(args):
    try:
        result = grade_output(args.agent, args.output_file, args.task_type)
        print(json.dumps(result, indent=2))
    except FileNotFoundError as e:
        print(f"[grade_agent_output] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_trends(args):
    result = get_trends(args.agent, args.days)
    print(json.dumps(result, indent=2))


def cli_report(args):
    print(grade_report(args.agent, args.days))


# ── CLI Parser ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Agent Output Grader — grade quality, detect drift, auto-generate Training Proposals"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # grade
    p_grade = subparsers.add_parser("grade", help="Grade an agent's output")
    p_grade.add_argument("--agent", required=True, help="Agent name (ads-copy, content, outreach, etc.)")
    p_grade.add_argument("--output-file", required=True, help="Path to the output file to grade")
    p_grade.add_argument("--task-type", default="default",
                         choices=list(TASK_TYPE_WEIGHTS.keys()),
                         help="Task type for weight adjustment")
    p_grade.set_defaults(func=cli_grade)

    # trends
    p_trends = subparsers.add_parser("trends", help="View quality trends for an agent")
    p_trends.add_argument("--agent", required=True, help="Agent name")
    p_trends.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")
    p_trends.set_defaults(func=cli_trends)

    # report
    p_report = subparsers.add_parser("report", help="Quality report for all agents")
    p_report.add_argument("--agent", default=None, help="Filter to specific agent")
    p_report.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")
    p_report.set_defaults(func=cli_report)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
