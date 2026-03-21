#!/usr/bin/env python3
"""
Meta Orchestrator — Runs all auto-research optimizers and cross-pollinates learnings.

This is the Karpathy "NEVER STOP" loop applied to the entire system.
Runs all three optimizers in sequence, shares learnings between them,
and tracks compound improvement over time.

Usage:
    # Run one full cycle of all optimizers
    python execution/auto-research/meta_orchestrator.py

    # Run continuously (Karpathy-style: NEVER STOP)
    python execution/auto-research/meta_orchestrator.py --loop --interval 3600

    # Dry run
    python execution/auto-research/meta_orchestrator.py --dry-run

    # Status report
    python execution/auto-research/meta_orchestrator.py --status
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

AUTORESEARCH_DIR = Path(__file__).parent
PROJECT_ROOT = AUTORESEARCH_DIR.parent.parent


def import_optimizers():
    """Lazy import to avoid circular deps."""
    # Use importlib to handle hyphenated directory
    import importlib.util

    optimizers = {}

    for name in ["memory-optimizer", "skill-optimizer", "growth-optimizer"]:
        orch_path = AUTORESEARCH_DIR / name / "orchestrator.py"
        if not orch_path.exists():
            continue
        spec = importlib.util.spec_from_file_location(
            "{}_orchestrator".format(name.replace("-", "_")), str(orch_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Find the optimizer class (ends with "Optimizer")
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if (isinstance(obj, type) and attr_name.endswith("Optimizer")
                    and attr_name != "ExperimentRunner"):
                optimizers[name] = obj
                break

    return optimizers


def cross_pollinate(optimizers_results):
    """
    Share learnings across optimizers.

    If memory optimizer learns something about categorization,
    skill optimizer should know. If growth optimizer finds a broken script,
    memory should track it.
    """
    shared_learnings = []

    for name, result in optimizers_results.items():
        if result.get("status") == "keep":
            learning = {
                "source": name,
                "hypothesis": result.get("hypothesis", ""),
                "improvement": result.get("challenger_metric", 0) - result.get("baseline_metric", 0),
            }
            shared_learnings.append(learning)

    if not shared_learnings:
        return

    # Append shared learnings to each optimizer's resources.md
    for name in optimizers_results:
        resources_path = AUTORESEARCH_DIR / name / "resources.md"
        if not resources_path.exists():
            continue

        with open(resources_path, "a") as f:
            f.write("\n### Cross-Optimizer Learnings — {}\n".format(
                datetime.now().strftime("%Y-%m-%d %H:%M")))
            for learning in shared_learnings:
                if learning["source"] != name:  # Don't echo back to source
                    f.write("- From **{}**: {} (improvement: {:+.2f})\n".format(
                        learning["source"], learning["hypothesis"][:150],
                        learning["improvement"]))


def get_status():
    """Get status of all optimizers."""
    status = {}

    for name in ["memory-optimizer", "skill-optimizer", "growth-optimizer"]:
        opt_dir = AUTORESEARCH_DIR / name
        results_path = opt_dir / "results.tsv"
        resources_path = opt_dir / "resources.md"
        experiments_dir = opt_dir / "experiments"

        info = {
            "total_experiments": 0,
            "keeps": 0,
            "discards": 0,
            "crashes": 0,
            "latest_metric": None,
            "improvement_trajectory": [],
            "learnings_size": 0,
        }

        if results_path.exists():
            lines = results_path.read_text().strip().split("\n")
            if len(lines) > 1:  # Skip header
                for line in lines[1:]:
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        info["total_experiments"] += 1
                        status_val = parts[3]
                        if status_val == "keep":
                            info["keeps"] += 1
                        elif status_val == "discard":
                            info["discards"] += 1
                        elif status_val == "crash":
                            info["crashes"] += 1

                        try:
                            metric = float(parts[2])
                            info["improvement_trajectory"].append(metric)
                            info["latest_metric"] = metric
                        except (ValueError, IndexError):
                            pass

        if resources_path.exists():
            info["learnings_size"] = len(resources_path.read_text())

        if experiments_dir.exists():
            info["total_experiments"] = len(list(experiments_dir.glob("exp_*.json")))

        status[name] = info

    return status


def print_status():
    """Print formatted status report."""
    status = get_status()

    print("\n" + "=" * 70)
    print("AUTO-RESEARCH STATUS REPORT — {}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 70)

    for name, info in status.items():
        print("\n## {}".format(name))
        print("   Experiments: {} total ({} keep, {} discard, {} crash)".format(
            info["total_experiments"], info["keeps"], info["discards"], info["crashes"]))

        if info["improvement_trajectory"]:
            first = info["improvement_trajectory"][0]
            last = info["improvement_trajectory"][-1]
            print("   Metric: {:.2f} → {:.2f} (total delta: {:+.2f})".format(
                first, last, last - first))
        else:
            print("   Metric: no data yet")

        win_rate = (info["keeps"] / info["total_experiments"] * 100) if info["total_experiments"] else 0
        print("   Win rate: {:.0f}%".format(win_rate))
        print("   Learnings: {} bytes".format(info["learnings_size"]))

    # Overall
    total_exp = sum(s["total_experiments"] for s in status.values())
    total_keeps = sum(s["keeps"] for s in status.values())
    print("\n" + "-" * 70)
    print("TOTAL: {} experiments, {} wins ({:.0f}% win rate)".format(
        total_exp, total_keeps,
        (total_keeps / total_exp * 100) if total_exp else 0))
    print("=" * 70)


def run_all(dry_run=False):
    """Run one cycle of all optimizers."""
    optimizers = import_optimizers()
    results = {}

    for name, OptimizerClass in optimizers.items():
        print("\n>>> Running {} <<<".format(name))
        try:
            optimizer = OptimizerClass()
            result = optimizer.run_cycle(dry_run=dry_run)
            results[name] = result
        except Exception as e:
            print("!!! {} CRASHED: {} !!!".format(name, e))
            results[name] = {"status": "crash", "error": str(e)}

    # Cross-pollinate learnings
    if not dry_run:
        cross_pollinate(results)

    return results


def run_loop(interval_seconds=3600, dry_run=False):
    """Run continuously like Karpathy's NEVER STOP loop."""
    cycle = 0
    print("\nStarting NEVER STOP loop (interval: {}s)".format(interval_seconds))
    print("Press Ctrl+C to stop\n")

    while True:
        cycle += 1
        print("\n{'*'*60}")
        print("META CYCLE {} — {}".format(cycle, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        print("{'*'*60}")

        try:
            results = run_all(dry_run=dry_run)

            # Print summary
            wins = sum(1 for r in results.values() if r.get("status") == "keep")
            total = len(results)
            print("\n[Cycle {} complete] {}/{} wins".format(cycle, wins, total))

            # Consolidate resources every 25 cycles
            if cycle % 25 == 0:
                print("\n[Consolidating resources.md files...]")
                optimizers = import_optimizers()
                for name, OptimizerClass in optimizers.items():
                    OptimizerClass().consolidate_resources()

        except KeyboardInterrupt:
            print("\n\nStopped by user after {} cycles.".format(cycle))
            print_status()
            break
        except Exception as e:
            print("\n!!! Meta cycle error: {} !!!".format(e))

        if dry_run:
            print("\n[Dry run — exiting after 1 cycle]")
            break

        print("\nSleeping {}s until next cycle...".format(interval_seconds))
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n\nStopped by user after {} cycles.".format(cycle))
            print_status()
            break


def main():
    parser = argparse.ArgumentParser(description="Meta Orchestrator — runs all auto-research optimizers")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--loop", action="store_true", help="Run continuously (NEVER STOP)")
    parser.add_argument("--interval", type=int, default=3600,
                       help="Seconds between loop cycles (default: 3600 = 1hr)")
    parser.add_argument("--status", action="store_true", help="Show status report")
    args = parser.parse_args()

    if args.status:
        print_status()
        return

    if args.loop:
        run_loop(interval_seconds=args.interval, dry_run=args.dry_run)
    else:
        run_all(dry_run=args.dry_run)
        print_status()


if __name__ == "__main__":
    main()
