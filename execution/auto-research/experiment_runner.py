#!/usr/bin/env python3
"""
experiment_runner.py — Shared base for all auto-research optimizers.

Inspired by Karpathy's autoresearch pattern:
- Baseline → Hypothesis → Challenger → Measure → Keep/Discard → Learn → Repeat

Each optimizer subclasses ExperimentRunner and implements:
- get_baseline_metric() → float
- generate_challenger(baseline, resources, history) → dict
- deploy_challenger(challenger) → str (experiment_id)
- measure_experiment(experiment_id) → dict {metric: float, details: ...}
- format_learning(experiment) → str

Usage:
    Subclass ExperimentRunner, implement abstract methods, call run_cycle().
"""
from __future__ import annotations

import json
import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from execution.memory_store import MemoryStore, DB_PATH

AUTORESEARCH_DIR = Path(__file__).parent


class Experiment:
    """Single experiment record."""
    def __init__(self, id, hypothesis, challenger, baseline_metric, challenger_metric=None,
                 status="pending", details=None, created_at=None):
        self.id = id
        self.hypothesis = hypothesis
        self.challenger = challenger
        self.baseline_metric = baseline_metric
        self.challenger_metric = challenger_metric
        self.status = status  # pending, running, keep, discard, crash
        self.details = details or {}
        self.created_at = created_at or datetime.now().isoformat()

    def to_dict(self):
        return {
            "id": self.id,
            "hypothesis": self.hypothesis,
            "challenger": self.challenger,
            "baseline_metric": self.baseline_metric,
            "challenger_metric": self.challenger_metric,
            "status": self.status,
            "details": self.details,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


class ExperimentRunner(ABC):
    """
    Base class for auto-research optimizers.

    Subclasses live in their own directories:
      execution/auto-research/{optimizer-name}/
        orchestrator.py    — the subclass
        baseline.md        — current best config/content
        resources.md       — accumulated learnings
        experiments/       — JSON logs of all experiments
        results.tsv        — summary table
    """

    def __init__(self, optimizer_name, optimizer_dir=None):
        self.name = optimizer_name
        self.dir = Path(optimizer_dir) if optimizer_dir else AUTORESEARCH_DIR / optimizer_name
        self.experiments_dir = self.dir / "experiments"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_path = self.dir / "baseline.md"
        self.resources_path = self.dir / "resources.md"
        self.results_path = self.dir / "results.tsv"
        self.memory = MemoryStore(DB_PATH)

        # Init results.tsv if missing
        if not self.results_path.exists():
            self.results_path.write_text(
                "id\tbaseline_metric\tchallenger_metric\tstatus\thypothesis\n"
            )

        # Init resources.md if missing
        if not self.resources_path.exists():
            self.resources_path.write_text(
                "# {} — Accumulated Learnings\n\n"
                "This file grows automatically as experiments complete.\n"
                "Each entry represents a tested hypothesis and its outcome.\n\n"
                "---\n\n".format(self.name)
            )

    def load_baseline(self):
        """Load current baseline content."""
        if self.baseline_path.exists():
            return self.baseline_path.read_text()
        return ""

    def save_baseline(self, content):
        """Save new baseline."""
        self.baseline_path.write_text(content)

    def load_resources(self):
        """Load accumulated learnings."""
        if self.resources_path.exists():
            return self.resources_path.read_text()
        return ""

    def append_learning(self, learning_text):
        """Append a learning to resources.md."""
        with open(self.resources_path, "a") as f:
            f.write("\n### Experiment {} — {}\n".format(
                self._next_experiment_id() - 1,
                datetime.now().strftime("%Y-%m-%d %H:%M")))
            f.write(learning_text + "\n")

    def load_history(self, limit=20):
        """Load recent experiment history."""
        experiments = sorted(self.experiments_dir.glob("exp_*.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        history = []
        for exp_file in experiments[:limit]:
            try:
                data = json.loads(exp_file.read_text())
                history.append(Experiment.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return history

    def _next_experiment_id(self):
        """Get next experiment number."""
        existing = list(self.experiments_dir.glob("exp_*.json"))
        return len(existing) + 1

    def log_experiment(self, experiment):
        """Save experiment to JSON and append to results.tsv."""
        exp_id = experiment.id
        exp_file = self.experiments_dir / "exp_{:04d}.json".format(exp_id)
        exp_file.write_text(json.dumps(experiment.to_dict(), indent=2, default=str))

        # Append to TSV
        with open(self.results_path, "a") as f:
            f.write("{}\t{}\t{}\t{}\t{}\n".format(
                exp_id,
                experiment.baseline_metric,
                experiment.challenger_metric or 0.0,
                experiment.status,
                experiment.hypothesis[:200].replace("\t", " "),
            ))

    def store_to_memory(self, experiment, learning_text):
        """Store experiment result in the memory system."""
        self.memory.add(
            type="learning",
            category="technical",
            title="[{}] {}".format(self.name, experiment.hypothesis[:100]),
            content="Status: {}\nBaseline: {}\nChallenger: {}\n\n{}".format(
                experiment.status,
                experiment.baseline_metric,
                experiment.challenger_metric,
                learning_text,
            ),
            source="auto-research/{}".format(self.name),
            tags="auto-research,{},experiment".format(self.name),
        )

    def run_cycle(self, dry_run=False):
        """
        Execute one full experiment cycle:
        1. Measure current baseline
        2. Generate hypothesis + challenger
        3. Deploy challenger
        4. Measure results
        5. Keep or discard
        6. Log learnings
        """
        print("\n" + "=" * 60)
        print("[{}] Auto-Research Cycle — {}".format(
            self.name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        print("=" * 60 + "\n")

        # 1. Get baseline metric
        print("[1/6] Measuring baseline...")
        baseline_metric = self.get_baseline_metric()
        print("      Baseline metric: {:.4f}".format(baseline_metric))

        # 2. Generate challenger
        print("[2/6] Generating hypothesis + challenger...")
        baseline = self.load_baseline()
        resources = self.load_resources()
        history = self.load_history(limit=10)

        challenger_data = self.generate_challenger(baseline, resources, history)
        hypothesis = challenger_data.get("hypothesis", "No hypothesis provided")
        print("      Hypothesis: {}".format(hypothesis))

        if dry_run:
            print("\n[DRY RUN] Would deploy challenger:")
            print(json.dumps(challenger_data, indent=2, default=str)[:500])
            return {"status": "dry_run", "hypothesis": hypothesis}

        # 3. Deploy
        print("[3/6] Deploying challenger...")
        exp_id = self._next_experiment_id()
        experiment = Experiment(
            id=exp_id,
            hypothesis=hypothesis,
            challenger=challenger_data,
            baseline_metric=baseline_metric,
            status="running",
        )

        try:
            experiment_ref = self.deploy_challenger(challenger_data)
            experiment.details["ref"] = experiment_ref
        except Exception as e:
            print("      CRASH: {}".format(e))
            experiment.status = "crash"
            experiment.details["error"] = str(e)
            self.log_experiment(experiment)
            return experiment.to_dict()

        # 4. Measure
        print("[4/6] Measuring challenger...")
        try:
            result = self.measure_experiment(experiment_ref)
            experiment.challenger_metric = result.get("metric", 0.0)
            experiment.details.update(result)
            print("      Challenger metric: {:.4f}".format(experiment.challenger_metric))
        except Exception as e:
            print("      CRASH during measurement: {}".format(e))
            experiment.status = "crash"
            experiment.details["error"] = str(e)
            self.log_experiment(experiment)
            return experiment.to_dict()

        # 5. Keep or discard
        print("[5/6] Evaluating...")
        if self.is_improvement(baseline_metric, experiment.challenger_metric):
            experiment.status = "keep"
            print("      KEEP — challenger wins ({:.4f} > {:.4f})".format(
                experiment.challenger_metric, baseline_metric))
            # Update baseline
            new_baseline = challenger_data.get("baseline_update")
            if new_baseline:
                self.save_baseline(new_baseline)
        else:
            experiment.status = "discard"
            print("      DISCARD — baseline holds ({:.4f} <= {:.4f})".format(
                experiment.challenger_metric, baseline_metric))

        # 6. Log + learn
        print("[6/6] Logging learnings...")
        learning = self.format_learning(experiment)
        self.append_learning(learning)
        self.log_experiment(experiment)
        self.store_to_memory(experiment, learning)
        print("      Logged experiment #{} to results.tsv + resources.md + memory.db".format(exp_id))

        return experiment.to_dict()

    def is_improvement(self, baseline, challenger):
        """Default: higher is better. Override for lower-is-better metrics."""
        return challenger > baseline

    def consolidate_resources(self, max_entries=100):
        """Compress resources.md when it gets too long (every ~100 experiments)."""
        content = self.load_resources()
        sections = content.split("### Experiment")
        if len(sections) <= max_entries:
            return

        # Keep header + last 50 entries, summarize the rest
        header = sections[0]
        recent = sections[-50:]
        old = sections[1:-50]

        summary = "\n## Consolidated Learnings (experiments 1-{})\n\n".format(len(old))
        for section in old:
            # Extract just the key finding line
            lines = section.strip().split("\n")
            for line in lines:
                if line.startswith("- ") or line.startswith("**"):
                    summary += line + "\n"
                    break

        new_content = header + summary + "\n" + "\n### Experiment".join([""] + recent)
        self.resources_path.write_text(new_content)
        print("[consolidate] Compressed resources.md: {} → {} entries".format(
            len(sections) - 1, 50 + 1))

    # ── Abstract methods (implement per optimizer) ──────────────────────

    @abstractmethod
    def get_baseline_metric(self):
        """Return the current baseline metric value (float)."""
        ...

    @abstractmethod
    def generate_challenger(self, baseline, resources, history):
        """
        Generate a new challenger based on:
        - baseline: current best config/content (str)
        - resources: accumulated learnings (str)
        - history: list of recent Experiment objects

        Returns dict with at least:
        - hypothesis: str
        - baseline_update: str (new baseline content if this wins)
        - ... any other challenger-specific data
        """
        ...

    @abstractmethod
    def deploy_challenger(self, challenger_data):
        """Deploy the challenger. Return an experiment reference (str/id)."""
        ...

    @abstractmethod
    def measure_experiment(self, experiment_ref):
        """
        Measure the experiment results.
        Return dict with at least: {metric: float, ...details}
        """
        ...

    @abstractmethod
    def format_learning(self, experiment):
        """Format the experiment result as a learning string for resources.md."""
        ...
