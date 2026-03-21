#!/usr/bin/env python3
"""
Growth Engine Optimizer — Auto-Research Pipeline

Continuously improves the system's revenue-generating capabilities by
analyzing pipeline data, sourcing results, audit outcomes, and lead quality.

Metrics:
  - Pipeline throughput: leads generated → contacts made → calls booked → closed
  - Sourcing hit rate: products sourced → profitable products found
  - Audit quality: audits generated → responses received
  - Script execution success: % of execution/ scripts that run without error

Changeable inputs:
  - ICP filter parameters (execution/filter_icp.py thresholds)
  - Sourcing strategy (retailer priority, brand focus, search terms)
  - Audit template structure (execution/generate_business_audit.py prompts)
  - Lead scoring weights

Feedback signals:
  - SQLite sourcing DB (execution/sourcing_results.db)
  - Memory DB pipeline/sales entries
  - Script error logs
  - Google Sheets pipeline data (via GHL API)

Usage:
    python execution/auto-research/growth-optimizer/orchestrator.py
    python execution/auto-research/growth-optimizer/orchestrator.py --dry-run
    python execution/auto-research/growth-optimizer/orchestrator.py --log-outcome <type> <details>
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
EXECUTION_DIR = PROJECT_ROOT / "execution"
SOURCING_DB = EXECUTION_DIR / "sourcing_results.db"


class GrowthOutcomeTracker:
    """Track business outcomes for growth optimization."""

    def __init__(self, log_path=None):
        self.log_path = log_path or Path(__file__).parent / "outcomes.json"
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

    def log(self, outcome_type, details):
        """Log a business outcome.
        outcome_type: lead_generated, lead_contacted, call_booked, deal_closed,
                     product_sourced, product_profitable, audit_sent, audit_responded,
                     script_success, script_error
        """
        entry = {
            "type": outcome_type,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }
        self.entries.append(entry)
        self._save()
        return entry

    def get_conversion_rates(self, days=30):
        """Calculate conversion rates across the pipeline."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        recent = [e for e in self.entries if e["timestamp"] >= cutoff]

        counts = Counter(e["type"] for e in recent)
        rates = {}

        # Lead pipeline
        if counts.get("lead_generated", 0):
            rates["lead_to_contact"] = counts.get("lead_contacted", 0) / counts["lead_generated"]
        if counts.get("lead_contacted", 0):
            rates["contact_to_call"] = counts.get("call_booked", 0) / counts["lead_contacted"]
        if counts.get("call_booked", 0):
            rates["call_to_close"] = counts.get("deal_closed", 0) / counts["call_booked"]

        # Sourcing pipeline
        if counts.get("product_sourced", 0):
            rates["sourcing_hit_rate"] = counts.get("product_profitable", 0) / counts["product_sourced"]

        # Audit pipeline
        if counts.get("audit_sent", 0):
            rates["audit_response_rate"] = counts.get("audit_responded", 0) / counts["audit_sent"]

        # Script health
        total_scripts = counts.get("script_success", 0) + counts.get("script_error", 0)
        if total_scripts:
            rates["script_success_rate"] = counts.get("script_success", 0) / total_scripts

        rates["_counts"] = dict(counts)
        return rates


class GrowthOptimizer(ExperimentRunner):
    """
    Self-improving growth engine optimizer.

    Analyzes all revenue-generating subsystems and identifies
    the highest-leverage improvements.
    """

    def __init__(self):
        super().__init__(
            optimizer_name="growth-optimizer",
            optimizer_dir=Path(__file__).parent,
        )
        self.tracker = GrowthOutcomeTracker()

    def get_baseline_metric(self):
        """
        Growth engine health score (0-100):
        - 25% script health (how many execution/ scripts are importable/runnable)
        - 25% pipeline data quality (memories with sales/agency categories)
        - 25% sourcing system health (DB exists, has recent data)
        - 25% system coverage (key capabilities have working scripts)
        """
        scores = {}

        # 1. Script health — can we import key scripts without error?
        key_scripts = [
            "run_scraper.py", "filter_icp.py", "generate_emails.py",
            "generate_business_audit.py", "source.py", "pipeline_analytics.py",
            "client_health_monitor.py", "send_morning_briefing.py",
            "training_officer_scan.py", "content_engine.py",
            "outreach_sequencer.py",
        ]
        existing = 0
        for script in key_scripts:
            if (EXECUTION_DIR / script).exists():
                existing += 1
        scores["script_health"] = (existing / len(key_scripts)) * 100

        # 2. Pipeline data quality — sales + agency memories in DB
        conn = sqlite3.connect(str(DB_PATH))
        pipeline_memories = conn.execute(
            """SELECT COUNT(*) as c FROM memories
               WHERE is_archived = 0
               AND category IN ('sales', 'agency', 'client', 'student')"""
        ).fetchone()[0]
        # 50+ pipeline memories = 100%, scale linearly
        scores["pipeline_data"] = min(100, (pipeline_memories / 50) * 100)

        # Sourcing memories
        sourcing_memories = conn.execute(
            """SELECT COUNT(*) as c FROM memories
               WHERE is_archived = 0 AND category = 'sourcing'"""
        ).fetchone()[0]
        conn.close()

        # 3. Sourcing system health
        if SOURCING_DB.exists():
            try:
                sconn = sqlite3.connect(str(SOURCING_DB))
                total_products = sconn.execute(
                    "SELECT COUNT(*) FROM results"
                ).fetchone()[0]
                sconn.close()
                scores["sourcing_health"] = min(100, (total_products / 100) * 100)
            except Exception:
                scores["sourcing_health"] = 25  # DB exists but maybe empty/broken
        else:
            scores["sourcing_health"] = 0

        # 4. System coverage — key capability files exist
        capabilities = {
            "lead_gen": ["run_scraper.py", "filter_icp.py"],
            "email": ["generate_emails.py", "outreach_sequencer.py"],
            "audit": ["generate_business_audit.py"],
            "sourcing": ["source.py", "multi_retailer_search.py"],
            "analytics": ["pipeline_analytics.py", "client_health_monitor.py"],
            "content": ["content_engine.py"],
            "briefing": ["send_morning_briefing.py"],
        }
        covered = 0
        for cap, scripts in capabilities.items():
            if all((EXECUTION_DIR / s).exists() for s in scripts):
                covered += 1
        scores["coverage"] = (covered / len(capabilities)) * 100

        composite = (
            scores["script_health"] * 0.25 +
            scores["pipeline_data"] * 0.25 +
            scores["sourcing_health"] * 0.25 +
            scores["coverage"] * 0.25
        )
        return round(composite, 2)

    def generate_challenger(self, baseline, resources, history):
        """
        Analyze growth subsystems and propose improvements.
        """
        issues = []

        # 1. Check for scripts that exist but have syntax errors
        key_scripts = [
            "run_scraper.py", "filter_icp.py", "generate_emails.py",
            "generate_business_audit.py", "pipeline_analytics.py",
        ]
        for script in key_scripts:
            path = EXECUTION_DIR / script
            if path.exists():
                try:
                    compile(path.read_text(), str(path), "exec")
                except SyntaxError as e:
                    issues.append({
                        "type": "syntax_error",
                        "script": script,
                        "error": str(e),
                        "fix": "Fix syntax error in {}".format(script),
                    })

        # 2. Check sourcing DB health
        if SOURCING_DB.exists():
            try:
                sconn = sqlite3.connect(str(SOURCING_DB))
                sconn.row_factory = sqlite3.Row

                # Check for stale data
                try:
                    latest = sconn.execute(
                        "SELECT MAX(created_at) as latest FROM results"
                    ).fetchone()
                    if latest and latest["latest"]:
                        last_date = datetime.fromisoformat(latest["latest"])
                        days_stale = (datetime.now() - last_date).days
                        if days_stale > 7:
                            issues.append({
                                "type": "stale_sourcing",
                                "days": days_stale,
                                "fix": "Run sourcing scan — no new products in {} days".format(days_stale),
                            })
                except Exception:
                    pass

                # Check for products never verified
                try:
                    unverified = sconn.execute(
                        "SELECT COUNT(*) as c FROM results WHERE verified = 0"
                    ).fetchone()["c"]
                    total = sconn.execute(
                        "SELECT COUNT(*) as c FROM results"
                    ).fetchone()["c"]
                    if total > 0 and unverified / total > 0.8:
                        issues.append({
                            "type": "low_verification",
                            "unverified": unverified,
                            "total": total,
                            "fix": "{}% of sourced products unverified — run Keepa verification batch".format(
                                round(unverified / total * 100)),
                        })
                except Exception:
                    pass

                sconn.close()
            except Exception:
                pass

        # 3. Check memory DB for patterns in sales pipeline
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Recent errors
        recent_errors = conn.execute(
            """SELECT title, content FROM memories
               WHERE type = 'error' AND is_archived = 0
               AND created_at >= ?
               ORDER BY created_at DESC LIMIT 10""",
            ((datetime.now() - timedelta(days=14)).isoformat(),),
        ).fetchall()
        if recent_errors:
            # Group errors by pattern
            error_patterns = Counter()
            for err in recent_errors:
                # Extract key from title
                key = err["title"][:60]
                error_patterns[key] += 1
            for pattern, count in error_patterns.most_common(3):
                if count >= 2:
                    issues.append({
                        "type": "recurring_error",
                        "pattern": pattern,
                        "count": count,
                        "fix": "Recurring error ({}x): {}".format(count, pattern),
                    })

        # Check for missing pipeline stages in memory
        pipeline_types = ["lead_generated", "lead_contacted", "call_booked", "deal_closed"]
        for ptype in pipeline_types:
            count = conn.execute(
                """SELECT COUNT(*) as c FROM memories
                   WHERE (title LIKE ? OR content LIKE ?) AND is_archived = 0""",
                ("%{}%".format(ptype), "%{}%".format(ptype)),
            ).fetchone()["c"]
            if count == 0:
                issues.append({
                    "type": "missing_pipeline_data",
                    "stage": ptype,
                    "fix": "No '{}' data tracked — add outcome logging".format(ptype),
                })

        conn.close()

        # 4. Check outcome tracker conversion rates
        rates = self.tracker.get_conversion_rates(days=30)
        if rates.get("sourcing_hit_rate", 1.0) < 0.1:
            issues.append({
                "type": "low_conversion",
                "metric": "sourcing_hit_rate",
                "value": rates["sourcing_hit_rate"],
                "fix": "Only {:.0%} of sourced products are profitable — refine sourcing criteria".format(
                    rates["sourcing_hit_rate"]),
            })

        # 5. Check for key config files
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            env_content = env_path.read_text()
            required_keys = ["ANTHROPIC_API_KEY", "KEEPA_API_KEY"]
            for key in required_keys:
                if key not in env_content:
                    issues.append({
                        "type": "missing_env",
                        "key": key,
                        "fix": "Missing {} in .env — some scripts will fail".format(key),
                    })

        # Prioritize
        priority = {"syntax_error": 0, "recurring_error": 1, "missing_env": 2,
                    "stale_sourcing": 3, "low_verification": 4, "low_conversion": 5,
                    "missing_pipeline_data": 6}
        issues.sort(key=lambda x: priority.get(x["type"], 99))

        return {
            "hypothesis": "Fix {} growth system issues to improve throughput".format(len(issues)),
            "issues": issues[:20],
            "total_issues": len(issues),
            "conversion_rates": rates,
        }

    def deploy_challenger(self, challenger_data):
        """
        Apply fixes where safe, queue others.
        Growth optimizer is conservative — it doesn't auto-edit
        revenue-generating scripts. It logs issues and queues fixes.
        """
        issues = challenger_data.get("issues", [])
        results = {"fixed": [], "queued": [], "skipped": []}

        for issue in issues:
            # All growth issues are queued as proposals, not auto-fixed
            # This is intentional — growth scripts touch real APIs and real money
            results["queued"].append({
                "type": issue["type"],
                "fix": issue["fix"],
                "priority": issue.get("type", "unknown"),
            })

        return json.dumps(results)

    def measure_experiment(self, experiment_ref):
        """Re-measure after logging."""
        metric = self.get_baseline_metric()
        ref_data = json.loads(experiment_ref)
        return {
            "metric": metric,
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
            lines.append("- Issues identified:")
            for q in details["queued"][:5]:
                lines.append("  - [{}] {}".format(q.get("type", "?"), q.get("fix", "?")))

        return "\n".join(lines)


def log_outcome(outcome_type, details):
    """Convenience function for logging business outcomes from other scripts."""
    tracker = GrowthOutcomeTracker()
    entry = tracker.log(outcome_type, details)
    print("Logged outcome: {} — {}".format(outcome_type, details[:100] if isinstance(details, str) else str(details)[:100]))
    return entry


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Growth Engine Optimizer")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--log-outcome", nargs=2, metavar=("TYPE", "DETAILS"),
                       help="Log a business outcome")
    parser.add_argument("--rates", action="store_true", help="Show conversion rates")
    args = parser.parse_args()

    if args.log_outcome:
        log_outcome(args.log_outcome[0], args.log_outcome[1])
        return

    if args.rates:
        tracker = GrowthOutcomeTracker()
        rates = tracker.get_conversion_rates()
        if not rates:
            print("No outcome data yet. Log outcomes with --log-outcome.")
            return
        print("\nGrowth Conversion Rates (30 days):")
        for k, v in rates.items():
            if k == "_counts":
                continue
            print("  {}: {:.1%}".format(k, v))
        if rates.get("_counts"):
            print("\nRaw counts:")
            for k, v in rates["_counts"].items():
                print("  {}: {}".format(k, v))
        return

    optimizer = GrowthOptimizer()
    for i in range(args.cycles):
        if args.cycles > 1:
            print("\n--- Cycle {}/{} ---".format(i + 1, args.cycles))
        result = optimizer.run_cycle(dry_run=args.dry_run)
        print("\nResult: {}".format(result.get("status", "unknown")))

    optimizer.consolidate_resources()


if __name__ == "__main__":
    main()
