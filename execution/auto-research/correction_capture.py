#!/usr/bin/env python3
"""
correction_capture.py — Captures user corrections as negative signals
for all auto-research optimizers.

When Sabbo corrects the system, this script:
1. Stores the correction in memory DB
2. Logs it as a negative signal for the skill optimizer
3. Feeds it into the memory optimizer's quality scoring
4. Creates a learned rule candidate

Usage:
    # Log a correction
    python execution/auto-research/correction_capture.py \
        --skill "lead-gen" \
        --correction "ICP filter was too broad, missed dentists with <50 reviews" \
        --score 4

    # Log a general system correction (not skill-specific)
    python execution/auto-research/correction_capture.py \
        --correction "Memory search returned irrelevant results for 'Kabrin'"

    # View recent corrections
    python execution/auto-research/correction_capture.py --recent
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from execution.memory_store import MemoryStore, DB_PATH

AUTORESEARCH_DIR = Path(__file__).parent


def capture_correction(correction, skill=None, score=None):
    """
    Store a correction and propagate to all optimizers.
    """
    store = MemoryStore(DB_PATH)
    results = {"stored": [], "propagated": []}

    # 1. Store in memory DB as correction type
    title = correction[:120]
    if skill:
        title = "[{}] {}".format(skill, title)

    store.add(
        type="correction",
        category="technical" if not skill else "agent",
        title=title,
        content="Correction: {}\nSkill: {}\nScore: {}\nTimestamp: {}".format(
            correction, skill or "general", score or "N/A",
            datetime.now().isoformat()),
        source="correction_capture",
        tags="correction,auto-research,{}".format(skill or "system"),
    )
    results["stored"].append("memory_db")

    # 2. Log to skill optimizer telemetry if skill-specific
    if skill and score is not None:
        telemetry_path = AUTORESEARCH_DIR / "skill-optimizer" / "telemetry.json"
        try:
            entries = []
            if telemetry_path.exists():
                entries = json.loads(telemetry_path.read_text())
            entries.append({
                "skill": skill,
                "score": score,
                "correction": correction,
                "details": {"source": "correction_capture"},
                "timestamp": datetime.now().isoformat(),
            })
            telemetry_path.write_text(json.dumps(entries, indent=2, default=str))
            results["propagated"].append("skill-optimizer/telemetry")
        except Exception as e:
            results["propagated"].append("skill-optimizer FAILED: {}".format(e))

    # 3. Append to all optimizer resources.md as a negative signal
    for optimizer in ["memory-optimizer", "skill-optimizer", "growth-optimizer"]:
        resources_path = AUTORESEARCH_DIR / optimizer / "resources.md"
        if resources_path.exists():
            try:
                with open(resources_path, "a") as f:
                    f.write("\n### CORRECTION SIGNAL — {}\n".format(
                        datetime.now().strftime("%Y-%m-%d %H:%M")))
                    f.write("- **What went wrong:** {}\n".format(correction))
                    if skill:
                        f.write("- **Skill:** {}\n".format(skill))
                    if score is not None:
                        f.write("- **Quality score:** {}/10\n".format(score))
                    f.write("- **Action needed:** Investigate and prevent recurrence\n")
                results["propagated"].append(optimizer)
            except Exception as e:
                results["propagated"].append("{} FAILED: {}".format(optimizer, e))

    return results


def show_recent(days=30):
    """Show recent corrections from memory DB."""
    store = MemoryStore(DB_PATH)
    corrections = store.get_recent(days=days, type_filter="correction", limit=20)

    if not corrections:
        print("No corrections in the last {} days.".format(days))
        return

    print("\nRecent Corrections (last {} days):".format(days))
    print("-" * 60)
    for c in corrections:
        print("[{}] {}".format(c["created_at"][:10], c["title"][:100]))
        if c.get("content"):
            # Show first 2 lines of content
            content_lines = c["content"].split("\n")[:2]
            for line in content_lines:
                print("    {}".format(line[:100]))
        print()


def main():
    parser = argparse.ArgumentParser(description="Capture corrections as optimizer signals")
    parser.add_argument("--correction", "-c", help="The correction text")
    parser.add_argument("--skill", "-s", help="Skill name (if skill-specific)")
    parser.add_argument("--score", type=int, help="Quality score 1-10 (10=perfect)")
    parser.add_argument("--recent", action="store_true", help="Show recent corrections")
    parser.add_argument("--days", type=int, default=30, help="Days for --recent")
    args = parser.parse_args()

    if args.recent:
        show_recent(days=args.days)
        return

    if not args.correction:
        parser.print_help()
        return

    results = capture_correction(args.correction, skill=args.skill, score=args.score)
    print("Correction captured:")
    print("  Stored: {}".format(", ".join(results["stored"])))
    print("  Propagated to: {}".format(", ".join(results["propagated"])))


if __name__ == "__main__":
    main()
