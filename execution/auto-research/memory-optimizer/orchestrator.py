#!/usr/bin/env python3
"""
Memory Quality Optimizer — Auto-Research Pipeline

Continuously improves the memory system's ability to store and retrieve
the right information at the right time.

Metrics:
  - Recall precision: % of retrieved memories that were actually useful
  - Storage efficiency: ratio of accessed vs never-accessed memories
  - Categorization accuracy: % of memories in the right category

Changeable inputs:
  - FTS5 BM25 weights (recency boost, access boost)
  - Category taxonomy and auto-categorization rules
  - Dedup similarity threshold
  - Tag extraction strategy
  - Memory title/content formatting rules

Feedback signals:
  - retrieval_log table (what was searched, what was returned)
  - access_count on memories (high = useful, 0 = dead weight)
  - user corrections (type=correction in memory DB)
  - memory_versions table (how often things get updated = volatility)

Usage:
    python execution/auto-research/memory-optimizer/orchestrator.py
    python execution/auto-research/memory-optimizer/orchestrator.py --dry-run
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from execution.memory_store import MemoryStore, DB_PATH
from execution.auto_research.experiment_runner import ExperimentRunner


class MemoryOptimizer(ExperimentRunner):
    """
    Self-improving memory system optimizer.

    The Karpathy loop applied to memory quality:
    1. Measure current recall precision + storage efficiency
    2. Hypothesize an improvement (better weights, better categorization, etc.)
    3. Apply the change
    4. Measure again
    5. Keep or revert
    6. Log what worked
    """

    def __init__(self):
        super().__init__(
            optimizer_name="memory-optimizer",
            optimizer_dir=Path(__file__).parent,
        )
        self.db_path = DB_PATH

    def get_baseline_metric(self):
        """
        Composite memory health score (0-100):
        - 25% recall coverage (% of categories with at least 1 accessed memory)
        - 25% categorization quality (non-general / total)
        - 20% retrieval activity (unique queries in retrieval_log last 7 days, capped at 50)
        - 15% freshness (memories updated in last 30 days / total)
        - 15% dedup cleanliness (unique titles / total)

        This metric rewards a WORKING memory system — one that is being
        actively searched and used, not just a clean database.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        total = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE is_archived = 0"
        ).fetchone()["c"]
        if total == 0:
            conn.close()
            return 0.0

        # Recall coverage: what % of categories have at least 1 accessed memory
        total_categories = conn.execute(
            "SELECT COUNT(DISTINCT category) as c FROM memories WHERE is_archived = 0"
        ).fetchone()["c"]
        categories_with_access = conn.execute(
            """SELECT COUNT(DISTINCT category) as c FROM memories
               WHERE is_archived = 0 AND access_count > 0"""
        ).fetchone()["c"]
        recall_score = (categories_with_access / total_categories * 100) if total_categories else 0

        # Categorization: what % are NOT in the catch-all "general" bucket
        non_general = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE is_archived = 0 AND category != 'general'"
        ).fetchone()["c"]
        cat_score = (non_general / total) * 100

        # Retrieval activity: unique queries in last 7 days (capped at 50 = 100%)
        recent_cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        unique_queries = conn.execute(
            "SELECT COUNT(DISTINCT query) as c FROM retrieval_log WHERE retrieved_at >= ?",
            (recent_cutoff,),
        ).fetchone()["c"]
        retrieval_score = min(100, (unique_queries / 50) * 100)

        # Freshness: what % were updated in last 30 days
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        fresh = conn.execute(
            "SELECT COUNT(*) as c FROM memories WHERE is_archived = 0 AND updated_at >= ?",
            (cutoff,),
        ).fetchone()["c"]
        fresh_score = (fresh / total) * 100

        # Dedup cleanliness: unique titles / total (1.0 = no dupes)
        unique_titles = conn.execute(
            "SELECT COUNT(DISTINCT LOWER(SUBSTR(title, 1, 80))) as c FROM memories WHERE is_archived = 0"
        ).fetchone()["c"]
        dedup_score = (unique_titles / total) * 100

        conn.close()

        # Weighted composite
        composite = (
            recall_score * 0.25 +
            cat_score * 0.25 +
            retrieval_score * 0.20 +
            fresh_score * 0.15 +
            dedup_score * 0.15
        )
        return round(composite, 2)

    def generate_challenger(self, baseline, resources, history):
        """
        Analyze current memory system state and propose an improvement.

        Unlike external-facing optimizers, this one modifies the system itself:
        - Recategorize misplaced memories
        - Merge near-duplicates
        - Archive dead-weight memories (0 access, old, low confidence)
        - Improve title/tag quality on frequently-accessed memories
        - Tune retrieval weights
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        # Gather diagnostic data
        diagnostics = {}

        # 1. Find "general" category memories that should be recategorized
        general_memories = conn.execute(
            """SELECT id, title, content, tags FROM memories
               WHERE category = 'general' AND is_archived = 0
               ORDER BY access_count DESC LIMIT 50"""
        ).fetchall()
        diagnostics["general_count"] = len(general_memories)
        diagnostics["recategorize_candidates"] = []
        category_keywords = {
            "sourcing": ["keepa", "asin", "fba", "amazon", "retailer", "sourcing", "product", "wholesale"],
            "agency": ["agency", "client", "retainer", "growth", "ppc", "ads", "campaign"],
            "sales": ["prospect", "lead", "close", "pipeline", "outreach", "call", "demo"],
            "technical": ["script", "api", "python", "bug", "error", "deploy", "code", "flask"],
            "agent": ["bot", "agent", "directive", "sop", "training", "skill"],
            "content": ["content", "video", "youtube", "post", "reel", "thumbnail"],
            "amazon": ["amazon", "fba", "listing", "bsr", "ppc", "acos"],
            "client": ["client", "kd-amazon", "deliverable"],
            "student": ["student", "coaching", "onboard"],
        }
        for mem in general_memories:
            text = "{} {} {}".format(mem["title"], mem["content"], mem["tags"] or "").lower()
            best_cat = None
            best_score = 0
            for cat, keywords in category_keywords.items():
                score = sum(1 for kw in keywords if kw in text)
                if score > best_score:
                    best_score = score
                    best_cat = cat
            if best_cat and best_score >= 2:
                diagnostics["recategorize_candidates"].append({
                    "id": mem["id"], "title": mem["title"][:80],
                    "from": "general", "to": best_cat, "score": best_score,
                })

        # 2. Find near-duplicate titles
        titles = conn.execute(
            "SELECT id, LOWER(SUBSTR(title, 1, 60)) as norm_title FROM memories WHERE is_archived = 0"
        ).fetchall()
        title_groups = {}
        for t in titles:
            key = t["norm_title"]
            if key not in title_groups:
                title_groups[key] = []
            title_groups[key].append(t["id"])
        diagnostics["duplicate_groups"] = {k: v for k, v in title_groups.items() if len(v) > 1}

        # 3. Find dead-weight memories (0 access, old, low confidence)
        dead = conn.execute(
            """SELECT id, title, confidence, created_at FROM memories
               WHERE is_archived = 0 AND access_count = 0
               AND created_at < ? AND confidence < 0.7
               ORDER BY confidence ASC LIMIT 20""",
            ((datetime.now() - timedelta(days=30)).isoformat(),),
        ).fetchall()
        diagnostics["dead_weight"] = [
            {"id": d["id"], "title": d["title"][:80], "confidence": d["confidence"]}
            for d in dead
        ]

        # 4. Find memories with missing or poor tags
        no_tags = conn.execute(
            """SELECT COUNT(*) as c FROM memories
               WHERE is_archived = 0 AND (tags IS NULL OR tags = '')"""
        ).fetchone()["c"]
        diagnostics["no_tags_count"] = no_tags

        conn.close()

        # Build hypothesis based on biggest opportunity
        actions = []
        hypothesis_parts = []

        if diagnostics["recategorize_candidates"]:
            n = len(diagnostics["recategorize_candidates"])
            actions.append(("recategorize", diagnostics["recategorize_candidates"]))
            hypothesis_parts.append("recategorize {} memories from 'general'".format(n))

        if diagnostics["duplicate_groups"]:
            n = len(diagnostics["duplicate_groups"])
            actions.append(("merge_dupes", diagnostics["duplicate_groups"]))
            hypothesis_parts.append("merge {} duplicate groups".format(n))

        if diagnostics["dead_weight"]:
            n = len(diagnostics["dead_weight"])
            actions.append(("archive_dead", diagnostics["dead_weight"]))
            hypothesis_parts.append("archive {} dead-weight memories".format(n))

        if not actions:
            hypothesis_parts.append("no actionable improvements found — system is clean")

        return {
            "hypothesis": "If we {}, recall precision should improve".format(
                " + ".join(hypothesis_parts) if hypothesis_parts else "make no changes"),
            "actions": actions,
            "diagnostics": diagnostics,
        }

    def deploy_challenger(self, challenger_data):
        """Apply the proposed changes to the memory DB."""
        store = MemoryStore(self.db_path)
        actions = challenger_data.get("actions", [])
        results = {"applied": [], "errors": []}

        for action_type, action_data in actions:
            if action_type == "recategorize":
                for item in action_data:
                    try:
                        store.conn.execute(
                            "UPDATE memories SET category = ?, updated_at = ? WHERE id = ?",
                            (item["to"], datetime.now().isoformat(), item["id"]),
                        )
                        results["applied"].append(
                            "Recategorized #{} '{}' → {}".format(
                                item["id"], item["title"][:40], item["to"]))
                    except Exception as e:
                        results["errors"].append("Recategorize #{}: {}".format(item["id"], e))
                store.conn.commit()

            elif action_type == "merge_dupes":
                for norm_title, ids in action_data.items():
                    if len(ids) < 2:
                        continue
                    try:
                        # Keep the one with highest access_count, archive others
                        rows = store.conn.execute(
                            "SELECT id, access_count FROM memories WHERE id IN ({})".format(
                                ",".join("?" * len(ids))),
                            ids,
                        ).fetchall()
                        keep_id = max(rows, key=lambda r: r[1])[0]
                        archive_ids = [r[0] for r in rows if r[0] != keep_id]
                        for aid in archive_ids:
                            store.conn.execute(
                                "UPDATE memories SET is_archived = 1, updated_at = ? WHERE id = ?",
                                (datetime.now().isoformat(), aid),
                            )
                        store.conn.commit()
                        results["applied"].append(
                            "Merged dupes '{}': kept #{}, archived {}".format(
                                norm_title[:40], keep_id, archive_ids))
                    except Exception as e:
                        results["errors"].append("Merge '{}': {}".format(norm_title[:30], e))

            elif action_type == "archive_dead":
                for item in action_data:
                    try:
                        store.conn.execute(
                            "UPDATE memories SET is_archived = 1, updated_at = ? WHERE id = ?",
                            (datetime.now().isoformat(), item["id"]),
                        )
                        results["applied"].append(
                            "Archived dead-weight #{} '{}'".format(item["id"], item["title"][:40]))
                    except Exception as e:
                        results["errors"].append("Archive #{}: {}".format(item["id"], e))
                store.conn.commit()

        return json.dumps(results)

    def measure_experiment(self, experiment_ref):
        """Re-measure the composite metric after changes."""
        metric = self.get_baseline_metric()
        ref_data = json.loads(experiment_ref)
        return {
            "metric": metric,
            "applied_count": len(ref_data.get("applied", [])),
            "error_count": len(ref_data.get("errors", [])),
            "applied": ref_data.get("applied", []),
        }

    def format_learning(self, experiment):
        """Format experiment for resources.md."""
        lines = []
        status_emoji = {"keep": "WIN", "discard": "LOSS", "crash": "CRASH"}
        lines.append("**[{}]** {} → {} (delta: {:+.2f})".format(
            status_emoji.get(experiment.status, "?"),
            experiment.baseline_metric,
            experiment.challenger_metric or 0,
            (experiment.challenger_metric or 0) - experiment.baseline_metric,
        ))
        lines.append("- Hypothesis: {}".format(experiment.hypothesis))

        details = experiment.details
        if details.get("applied_count"):
            lines.append("- Applied {} changes".format(details["applied_count"]))
        if details.get("applied"):
            for a in details["applied"][:5]:
                lines.append("  - {}".format(a))

        return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Memory Quality Optimizer")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cycles", type=int, default=1, help="Number of cycles to run")
    args = parser.parse_args()

    optimizer = MemoryOptimizer()

    for i in range(args.cycles):
        if args.cycles > 1:
            print("\n--- Cycle {}/{} ---".format(i + 1, args.cycles))
        result = optimizer.run_cycle(dry_run=args.dry_run)
        print("\nResult: {}".format(result.get("status", "unknown")))

    # Consolidate if needed
    optimizer.consolidate_resources()


if __name__ == "__main__":
    main()
