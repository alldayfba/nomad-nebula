#!/usr/bin/env python3
"""
Skill Quality Optimizer — Auto-Research Pipeline

Continuously improves skill execution quality by tracking outcomes
and refining skill prompts, directives, and execution patterns.

Metrics:
  - Skill execution success rate (completions without user correction)
  - Directive coverage (% of skills with linked SOPs)
  - Prompt contract compliance (% of outputs passing validation)

Changeable inputs:
  - Skill prompt templates (.claude/skills/*.md)
  - Directive instructions (directives/*.md)
  - Execution order and guardrails

Feedback signals:
  - Skill telemetry log (execution/auto-research/skill-optimizer/telemetry.json)
  - User corrections captured in memory DB (type=correction)
  - Learned rules in CLAUDE.md

Usage:
    python execution/auto-research/skill-optimizer/orchestrator.py
    python execution/auto-research/skill-optimizer/orchestrator.py --dry-run
    python execution/auto-research/skill-optimizer/orchestrator.py --log-execution <skill> <score> [correction_note]
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from execution.memory_store import MemoryStore, DB_PATH
from execution.auto_research.experiment_runner import ExperimentRunner

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"
DIRECTIVES_DIR = PROJECT_ROOT / "directives"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"


class SkillTelemetry:
    """Track skill execution outcomes."""

    def __init__(self, log_path=None):
        self.log_path = log_path or Path(__file__).parent / "telemetry.json"
        self.entries = self._load()

    def _load(self):
        if self.log_path.exists():
            try:
                return json.loads(self.log_path.read_text())
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self):
        self.log_path.write_text(json.dumps(self.entries, indent=2, default=str))

    def log(self, skill_name, score, correction=None, details=None):
        """Log a skill execution.
        score: 1-10 (10=perfect, 1=completely wrong)
        correction: optional user correction text
        """
        entry = {
            "skill": skill_name,
            "score": score,
            "correction": correction,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
        }
        self.entries.append(entry)
        self._save()
        return entry

    def get_stats(self):
        """Aggregate stats per skill."""
        stats = defaultdict(lambda: {"runs": 0, "scores": [], "corrections": 0})
        for e in self.entries:
            s = stats[e["skill"]]
            s["runs"] += 1
            s["scores"].append(e["score"])
            if e.get("correction"):
                s["corrections"] += 1

        result = {}
        for skill, data in stats.items():
            avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
            result[skill] = {
                "runs": data["runs"],
                "avg_score": round(avg_score, 2),
                "correction_rate": round(data["corrections"] / data["runs"], 2) if data["runs"] else 0,
                "trend": self._trend(data["scores"]),
            }
        return result

    def _trend(self, scores):
        """Simple trend: compare first half avg to second half avg."""
        if len(scores) < 4:
            return "insufficient_data"
        mid = len(scores) // 2
        first_half = sum(scores[:mid]) / mid
        second_half = sum(scores[mid:]) / (len(scores) - mid)
        if second_half > first_half + 0.5:
            return "improving"
        elif second_half < first_half - 0.5:
            return "degrading"
        return "stable"


class SkillOptimizer(ExperimentRunner):
    """
    Self-improving skill system optimizer.

    Analyzes:
    1. Which skills exist but lack directives
    2. Which skills have high correction rates
    3. Which directives have gaps or missing edge cases
    4. Common patterns in user corrections
    """

    def __init__(self):
        super().__init__(
            optimizer_name="skill-optimizer",
            optimizer_dir=Path(__file__).parent,
        )
        self.telemetry = SkillTelemetry()

    def get_baseline_metric(self):
        """
        Skill system health score (0-100):
        - 30% directive coverage (skills with linked SOPs)
        - 30% skill completeness (skills with all required fields)
        - 20% telemetry performance (avg score across logged executions)
        - 20% correction signals (inverse of correction rate from memory DB)
        """
        scores = {}

        # 1. Directive coverage
        skills = list(SKILLS_DIR.glob("*.md"))
        skills = [s for s in skills if s.name != "_skillspec.md"]
        skills_with_directive = 0
        for skill_path in skills:
            content = skill_path.read_text()
            if "directive" in content.lower() and ("directives/" in content or "sop" in content.lower()):
                skills_with_directive += 1
        scores["directive_coverage"] = (skills_with_directive / len(skills) * 100) if skills else 0

        # 2. Skill completeness (has trigger, tools, steps)
        complete = 0
        for skill_path in skills:
            content = skill_path.read_text()
            has_trigger = "trigger:" in content.lower() or "trigger" in content.lower()
            has_tools = "tools:" in content.lower() or "tools" in content.lower()
            has_steps = "step" in content.lower() or "execution" in content.lower()
            if has_trigger and has_tools and has_steps:
                complete += 1
        scores["completeness"] = (complete / len(skills) * 100) if skills else 0

        # 3. Telemetry performance
        stats = self.telemetry.get_stats()
        if stats:
            avg_scores = [s["avg_score"] for s in stats.values()]
            scores["telemetry"] = (sum(avg_scores) / len(avg_scores)) * 10  # Scale 1-10 to 0-100
        else:
            scores["telemetry"] = 50  # Neutral if no data

        # 4. Correction signals from memory DB
        conn = sqlite3.connect(str(DB_PATH))
        total_corrections = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE type = 'correction' AND is_archived = 0"
        ).fetchone()[0]
        recent_corrections = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE type = 'correction' AND is_archived = 0 AND created_at >= ?",
            ((datetime.now() - timedelta(days=30)).isoformat(),),
        ).fetchone()[0]
        conn.close()
        # Fewer recent corrections = better (inverse relationship)
        correction_score = max(0, 100 - (recent_corrections * 10))
        scores["correction_health"] = correction_score

        composite = (
            scores["directive_coverage"] * 0.30 +
            scores["completeness"] * 0.30 +
            scores["telemetry"] * 0.20 +
            scores["correction_health"] * 0.20
        )
        return round(composite, 2)

    def generate_challenger(self, baseline, resources, history):
        """
        Scan skills and directives for improvement opportunities.
        """
        issues = []

        # 1. Skills missing directives
        skills = list(SKILLS_DIR.glob("*.md"))
        skills = [s for s in skills if s.name != "_skillspec.md"]
        for skill_path in skills:
            content = skill_path.read_text()
            if "directives/" not in content and "sop" not in content.lower():
                issues.append({
                    "type": "missing_directive",
                    "skill": skill_path.name,
                    "fix": "Link skill to appropriate directive or create one",
                })

        # 2. Skills with poor telemetry
        stats = self.telemetry.get_stats()
        for skill_name, data in stats.items():
            if data["avg_score"] < 6:
                issues.append({
                    "type": "low_score",
                    "skill": skill_name,
                    "avg_score": data["avg_score"],
                    "correction_rate": data["correction_rate"],
                    "fix": "Review and improve skill prompt",
                })
            if data["trend"] == "degrading":
                issues.append({
                    "type": "degrading",
                    "skill": skill_name,
                    "fix": "Skill quality declining — investigate recent changes",
                })

        # 3. Directives without linked skills
        directives = list(DIRECTIVES_DIR.glob("*-sop.md"))
        skill_contents = {s.name: s.read_text() for s in skills}
        for directive in directives:
            linked = False
            for skill_name, skill_content in skill_contents.items():
                if directive.name in skill_content:
                    linked = True
                    break
            if not linked:
                issues.append({
                    "type": "orphan_directive",
                    "directive": directive.name,
                    "fix": "Create a skill that references this directive",
                })

        # 4. Learned rules not yet reflected in directives
        if CLAUDE_MD.exists():
            claude_content = CLAUDE_MD.read_text()
            rules_section = ""
            if "## Learned Rules" in claude_content:
                rules_section = claude_content.split("## Learned Rules")[1]
            rule_count = rules_section.count("[WORKFLOW]") + rules_section.count("[BACKEND]") + \
                        rules_section.count("[FRONTEND]") + rules_section.count("[GENERAL]") + \
                        rules_section.count("[TOOLING]") + rules_section.count("[DATA]")
            if rule_count > 10:
                issues.append({
                    "type": "rules_overflow",
                    "count": rule_count,
                    "fix": "Consolidate learned rules into relevant directives",
                })

        # 5. Skills with incomplete fields (missing description, tools, etc.)
        for skill_path in skills:
            content = skill_path.read_text()
            missing = []
            if "description:" not in content:
                missing.append("description")
            if "tools:" not in content:
                missing.append("tools")
            if "trigger:" not in content and "trigger" not in content.lower():
                missing.append("trigger")
            if missing:
                issues.append({
                    "type": "incomplete_skill",
                    "skill": skill_path.name,
                    "missing": missing,
                    "fix": "Add missing fields: {}".format(", ".join(missing)),
                })

        # Prioritize: low_score > degrading > missing_directive > incomplete > orphan
        priority = {"low_score": 0, "degrading": 1, "missing_directive": 2,
                    "incomplete_skill": 3, "rules_overflow": 4, "orphan_directive": 5}
        issues.sort(key=lambda x: priority.get(x["type"], 99))

        return {
            "hypothesis": "Fix {} skill system issues to improve execution quality".format(len(issues)),
            "issues": issues[:20],  # Cap at 20 per cycle
            "total_issues": len(issues),
        }

    # Known directive mappings for skills that reference SOPs indirectly
    DIRECTIVE_MAP = {
        "auto-outreach.md": "outreach-sequencer-sop.md",
        "deal-drop.md": "amazon-sourcing-sop.md",
        "pipeline.md": "agent-execution-loop-sop.md",
        "sales-prep.md": "lead-gen-sop.md",
        "memory.md": None,  # Tool skill, no SOP needed
        "doe.md": None,  # Meta skill, references multiple
        "build-site.md": None,  # References SabboOS/Agents/WebBuild.md (not directives/)
    }

    def deploy_challenger(self, challenger_data):
        """
        Apply safe fixes directly to skill files:
        1. Add missing directive references to skills
        2. Add missing frontmatter fields (description, tools, trigger)
        3. Queue complex fixes (low scores, orphan directives) as proposals
        """
        issues = challenger_data.get("issues", [])
        results = {"fixed": [], "queued": [], "skipped": []}

        for issue in issues:
            if issue["type"] == "missing_directive":
                skill_name = issue["skill"]
                # Check if we have a known mapping
                directive = self.DIRECTIVE_MAP.get(skill_name)
                if directive is None and skill_name in self.DIRECTIVE_MAP:
                    # Explicitly mapped to None = no fix needed
                    results["skipped"].append(
                        "Skill '{}' intentionally has no directive".format(skill_name))
                    continue
                elif directive is None:
                    # Try to find a matching directive by name
                    skill_stem = skill_name.replace(".md", "")
                    candidates = list(DIRECTIVES_DIR.glob("*{}*sop*.md".format(skill_stem)))
                    if candidates:
                        directive = candidates[0].name
                    else:
                        results["queued"].append(
                            "Skill '{}' needs a directive — no auto-match found".format(skill_name))
                        continue

                # Apply the fix: add directive reference to skill
                skill_path = SKILLS_DIR / skill_name
                if skill_path.exists():
                    content = skill_path.read_text()
                    # Add directive reference after the frontmatter closing ---
                    # Find the second --- (end of frontmatter)
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        # Check if there's already a ## Directive section
                        if "## Directive" not in parts[2]:
                            directive_block = "\n\n## Directive\nRead `directives/{}` for the full SOP before proceeding.\n".format(directive)
                            # Insert after first heading or at start of body
                            body = parts[2]
                            lines = body.split("\n")
                            insert_idx = 0
                            for i, line in enumerate(lines):
                                if line.startswith("# "):
                                    insert_idx = i + 1
                                    break
                            lines.insert(insert_idx, directive_block)
                            parts[2] = "\n".join(lines)
                            new_content = "---".join(parts)
                            skill_path.write_text(new_content)
                            results["fixed"].append(
                                "Added directive link '{}' to skill '{}'".format(directive, skill_name))
                        else:
                            results["skipped"].append(
                                "Skill '{}' already has ## Directive section".format(skill_name))
                    else:
                        results["queued"].append(
                            "Skill '{}' has unexpected format — can't auto-fix".format(skill_name))

            elif issue["type"] == "incomplete_skill":
                skill_name = issue["skill"]
                skill_path = SKILLS_DIR / skill_name
                missing = issue.get("missing", [])
                if not skill_path.exists():
                    continue

                content = skill_path.read_text()

                # Check if it has frontmatter
                if not content.startswith("---"):
                    results["queued"].append(
                        "Skill '{}' has no frontmatter — needs manual fix".format(skill_name))
                    continue

                # Parse frontmatter
                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue

                frontmatter = parts[1]
                changed = False

                if "description" in missing and "description:" not in frontmatter:
                    # Infer description from first heading or skill name
                    body = parts[2]
                    desc = skill_name.replace(".md", "").replace("-", " ").title()
                    # Try to get from ## Goal section
                    if "## Goal" in body:
                        goal_text = body.split("## Goal")[1].split("\n")[1].strip()
                        if goal_text:
                            desc = goal_text[:120]
                    frontmatter += "description: {}\n".format(desc)
                    changed = True

                if "tools" in missing and "tools:" not in frontmatter:
                    frontmatter += "tools: [Bash, Read, Write, Edit, Glob, Grep]\n"
                    changed = True

                if "trigger" in missing and "trigger:" not in frontmatter:
                    trigger = 'when user says "{}"'.format(
                        skill_name.replace(".md", "").replace("-", " "))
                    frontmatter += "trigger: {}\n".format(trigger)
                    changed = True

                if changed:
                    parts[1] = frontmatter
                    skill_path.write_text("---".join(parts))
                    results["fixed"].append(
                        "Added missing fields {} to skill '{}'".format(missing, skill_name))
                else:
                    results["skipped"].append(
                        "Skill '{}' — nothing to fix".format(skill_name))

            elif issue["type"] in ("low_score", "degrading"):
                results["queued"].append(
                    "Skill '{}' needs prompt improvement (avg: {}, trend: {})".format(
                        issue["skill"],
                        issue.get("avg_score", "?"),
                        issue.get("trend", issue["type"]),
                    ))

            elif issue["type"] == "orphan_directive":
                results["queued"].append(
                    "Directive '{}' has no linked skill".format(issue["directive"]))

            elif issue["type"] == "rules_overflow":
                results["queued"].append(
                    "{} learned rules need consolidation into directives".format(issue["count"]))

            else:
                results["skipped"].append(str(issue))

        return json.dumps(results)

    def measure_experiment(self, experiment_ref):
        """Re-measure after changes."""
        metric = self.get_baseline_metric()
        ref_data = json.loads(experiment_ref)
        return {
            "metric": metric,
            "fixed_count": len(ref_data.get("fixed", [])),
            "queued_count": len(ref_data.get("queued", [])),
            "queued": ref_data.get("queued", []),
        }

    def format_learning(self, experiment):
        """Format for resources.md."""
        lines = []
        status_label = {"keep": "WIN", "discard": "LOSS", "crash": "CRASH"}
        lines.append("**[{}]** {:.2f} → {:.2f} (delta: {:+.2f})".format(
            status_label.get(experiment.status, "?"),
            experiment.baseline_metric,
            experiment.challenger_metric or 0,
            (experiment.challenger_metric or 0) - experiment.baseline_metric,
        ))
        lines.append("- Hypothesis: {}".format(experiment.hypothesis))

        details = experiment.details
        if details.get("queued"):
            lines.append("- Queued fixes:")
            for q in details["queued"][:5]:
                lines.append("  - {}".format(q))

        return "\n".join(lines)


def log_skill_execution(skill_name, score, correction=None):
    """Convenience function for logging skill executions from other scripts."""
    telemetry = SkillTelemetry()
    entry = telemetry.log(skill_name, score, correction)
    print("Logged: {} score={} correction={}".format(skill_name, score, bool(correction)))
    return entry


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Skill Quality Optimizer")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--log-execution", nargs="+", metavar=("SKILL", "SCORE"),
                       help="Log a skill execution: <skill_name> <score> [correction_note]")
    parser.add_argument("--stats", action="store_true", help="Show telemetry stats")
    args = parser.parse_args()

    if args.log_execution:
        skill = args.log_execution[0]
        score = int(args.log_execution[1])
        correction = args.log_execution[2] if len(args.log_execution) > 2 else None
        log_skill_execution(skill, score, correction)
        return

    if args.stats:
        telemetry = SkillTelemetry()
        stats = telemetry.get_stats()
        if not stats:
            print("No telemetry data yet. Log executions with --log-execution.")
            return
        print("\nSkill Telemetry Stats:")
        print("{:<25} {:>6} {:>8} {:>12} {:>10}".format(
            "Skill", "Runs", "Avg", "Corrections", "Trend"))
        print("-" * 65)
        for skill, data in sorted(stats.items()):
            print("{:<25} {:>6} {:>8.1f} {:>12.0%} {:>10}".format(
                skill, data["runs"], data["avg_score"],
                data["correction_rate"], data["trend"]))
        return

    optimizer = SkillOptimizer()
    for i in range(args.cycles):
        if args.cycles > 1:
            print("\n--- Cycle {}/{} ---".format(i + 1, args.cycles))
        result = optimizer.run_cycle(dry_run=args.dry_run)
        print("\nResult: {}".format(result.get("status", "unknown")))

    optimizer.consolidate_resources()


if __name__ == "__main__":
    main()
