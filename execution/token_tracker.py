#!/usr/bin/env python3
"""
token_tracker.py — Track API token usage and costs across all models.

Logs every API call to SQLite. Generates daily/weekly/monthly reports.
Alerts when approaching budget thresholds.

Usage:
    # Log a call
    python execution/token_tracker.py log \
        --model claude-sonnet-4-6 \
        --input-tokens 1500 \
        --output-tokens 800 \
        --task-type email_gen

    # Daily report
    python execution/token_tracker.py report --period day

    # Weekly report
    python execution/token_tracker.py report --period week

    # Check budget
    python execution/token_tracker.py budget

    # Programmatic:
    from execution.token_tracker import TokenTracker
    tracker = TokenTracker()
    tracker.log_call("claude-sonnet-4-6", 1500, 800, "email_gen")
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "token_usage.db"

# ── Pricing (per 1M tokens, as of 2026-03) ──────────────────────────────────

PRICING = {
    # Anthropic
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    # Google
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-pro": {"input": 1.25, "output": 5.00},
    # OpenAI
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
}

# Budget enforcement (Kabrin pattern: hard monthly cap + model approval gates)
DAILY_BUDGET = 6.67  # $200/month ÷ 30
MONTHLY_BUDGET = 200.00  # Hard monthly cap (adjustable)

# Models that require approval before use (expensive models)
APPROVAL_REQUIRED_MODELS = {
    "claude-opus-4-6",  # $15/$75 per 1M — only for high-stakes tasks
}

# Models that are auto-approved (cheap, use freely)
AUTO_APPROVED_MODELS = {
    "claude-haiku-4-5-20251001",  # $0.25/$1.25
    "gemini-2.0-flash",  # $0.10/$0.40
    "gpt-4.1-mini",  # $0.40/$1.60
    "claude-sonnet-4-6",  # $3/$15 — default workhorse
}


class TokenTracker:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                task_type TEXT,
                notes TEXT
            )
        """)
        self.conn.commit()

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for a given call."""
        pricing = PRICING.get(model)
        if not pricing:
            # Unknown model — estimate at Sonnet pricing
            pricing = PRICING["claude-sonnet-4-6"]
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    def log_call(self, model: str, input_tokens: int, output_tokens: int,
                 task_type: str = "unknown", notes: str = "") -> dict:
        """Log an API call."""
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        now = datetime.now().isoformat()

        self.conn.execute(
            "INSERT INTO usage_log (timestamp, model, input_tokens, output_tokens, cost_usd, task_type, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, model, input_tokens, output_tokens, cost, task_type, notes),
        )
        self.conn.commit()

        return {
            "timestamp": now,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "task_type": task_type,
        }

    def get_report(self, period: str = "day") -> dict:
        """Generate usage report for a time period."""
        now = datetime.now()
        if period == "day":
            since = now - timedelta(days=1)
        elif period == "week":
            since = now - timedelta(weeks=1)
        elif period == "month":
            since = now - timedelta(days=30)
        else:
            since = now - timedelta(days=1)

        since_str = since.isoformat()

        # Total stats
        row = self.conn.execute(
            "SELECT COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cost_usd) "
            "FROM usage_log WHERE timestamp >= ?",
            (since_str,),
        ).fetchone()

        total_calls = row[0] or 0
        total_input = row[1] or 0
        total_output = row[2] or 0
        total_cost = row[3] or 0.0

        # Per-model breakdown
        model_rows = self.conn.execute(
            "SELECT model, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cost_usd) "
            "FROM usage_log WHERE timestamp >= ? GROUP BY model ORDER BY SUM(cost_usd) DESC",
            (since_str,),
        ).fetchall()

        models = {}
        for m_row in model_rows:
            models[m_row[0]] = {
                "calls": m_row[1],
                "input_tokens": m_row[2],
                "output_tokens": m_row[3],
                "cost_usd": round(m_row[4], 4),
            }

        # Per-task breakdown
        task_rows = self.conn.execute(
            "SELECT task_type, COUNT(*), SUM(cost_usd) "
            "FROM usage_log WHERE timestamp >= ? GROUP BY task_type ORDER BY SUM(cost_usd) DESC",
            (since_str,),
        ).fetchall()

        tasks = {}
        for t_row in task_rows:
            tasks[t_row[0]] = {"calls": t_row[1], "cost_usd": round(t_row[2], 4)}

        return {
            "period": period,
            "since": since_str,
            "total_calls": total_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": round(total_cost, 4),
            "daily_budget_usd": DAILY_BUDGET,
            "budget_used_pct": round((total_cost / DAILY_BUDGET) * 100, 1) if period == "day" else None,
            "by_model": models,
            "by_task": tasks,
        }

    def check_budget(self) -> dict:
        """Check today's spending against budget."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        row = self.conn.execute(
            "SELECT SUM(cost_usd) FROM usage_log WHERE timestamp >= ?",
            (today,),
        ).fetchone()

        spent = row[0] or 0.0
        remaining = DAILY_BUDGET - spent
        pct = (spent / DAILY_BUDGET) * 100

        status = "OK"
        if pct >= 90:
            status = "CRITICAL"
        elif pct >= 75:
            status = "WARNING"
        elif pct >= 50:
            status = "MODERATE"

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "spent_usd": round(spent, 4),
            "remaining_usd": round(remaining, 4),
            "budget_usd": DAILY_BUDGET,
            "used_pct": round(pct, 1),
            "status": status,
        }

    def check_monthly_budget(self) -> dict:
        """Check this month's spending against monthly cap."""
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        row = self.conn.execute(
            "SELECT SUM(cost_usd), COUNT(*) FROM usage_log WHERE timestamp >= ?",
            (month_start,),
        ).fetchone()

        spent = row[0] or 0.0
        calls = row[1] or 0
        remaining = MONTHLY_BUDGET - spent
        pct = (spent / MONTHLY_BUDGET) * 100

        status = "OK"
        if pct >= 100:
            status = "EXCEEDED"
        elif pct >= 90:
            status = "CRITICAL"
        elif pct >= 75:
            status = "WARNING"

        return {
            "month": datetime.now().strftime("%Y-%m"),
            "spent_usd": round(spent, 4),
            "remaining_usd": round(max(0, remaining), 4),
            "budget_usd": MONTHLY_BUDGET,
            "used_pct": round(pct, 1),
            "total_calls": calls,
            "status": status,
            "exceeded": spent >= MONTHLY_BUDGET,
        }

    def can_use_model(self, model) -> dict:
        """Check if a model can be used (budget + approval gate check)."""
        monthly = self.check_monthly_budget()

        # Hard budget cap — block all if exceeded
        if monthly["exceeded"]:
            return {
                "allowed": False,
                "reason": "Monthly budget exceeded (${:.2f}/${:.2f})".format(
                    monthly["spent_usd"], MONTHLY_BUDGET),
                "model": model,
            }

        # Model approval gate
        if model in APPROVAL_REQUIRED_MODELS:
            return {
                "allowed": False,
                "reason": "Model '{}' requires explicit approval (expensive). Use sonnet/haiku for routine tasks.".format(model),
                "model": model,
                "requires_approval": True,
            }

        # Auto-approved models
        return {
            "allowed": True,
            "model": model,
            "monthly_remaining": monthly["remaining_usd"],
        }


def format_report(report: dict) -> str:
    """Format report as readable text."""
    lines = [
        f"Token Usage Report — {report['period']}",
        f"Since: {report['since'][:10]}",
        f"",
        f"Total calls: {report['total_calls']}",
        f"Total tokens: {report['total_input_tokens']:,} in / {report['total_output_tokens']:,} out",
        f"Total cost: ${report['total_cost_usd']:.4f}",
    ]
    if report.get("budget_used_pct") is not None:
        lines.append(f"Budget used: {report['budget_used_pct']}% of ${DAILY_BUDGET}/day")

    if report["by_model"]:
        lines.append(f"\nBy Model:")
        for model, stats in report["by_model"].items():
            lines.append(f"  {model}: {stats['calls']} calls, ${stats['cost_usd']:.4f}")

    if report["by_task"]:
        lines.append(f"\nBy Task:")
        for task, stats in report["by_task"].items():
            lines.append(f"  {task}: {stats['calls']} calls, ${stats['cost_usd']:.4f}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Track API token usage and costs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Log command
    log_parser = subparsers.add_parser("log", help="Log an API call")
    log_parser.add_argument("--model", required=True)
    log_parser.add_argument("--input-tokens", type=int, required=True)
    log_parser.add_argument("--output-tokens", type=int, required=True)
    log_parser.add_argument("--task-type", default="unknown")
    log_parser.add_argument("--notes", default="")

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate usage report")
    report_parser.add_argument("--period", choices=["day", "week", "month"], default="day")
    report_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Budget command
    subparsers.add_parser("budget", help="Check today's budget status")

    args = parser.parse_args()
    tracker = TokenTracker()

    if args.command == "log":
        result = tracker.log_call(args.model, args.input_tokens, args.output_tokens, args.task_type, args.notes)
        print(f"✓ Logged: {result['model']} — ${result['cost_usd']:.6f}")

    elif args.command == "report":
        report = tracker.get_report(args.period)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(format_report(report))

    elif args.command == "budget":
        budget = tracker.check_budget()
        status_icon = {"OK": "✓", "MODERATE": "⚠", "WARNING": "⚠", "CRITICAL": "✗"}
        icon = status_icon.get(budget["status"], "?")
        print(f"{icon} {budget['status']}: ${budget['spent_usd']:.4f} / ${budget['budget_usd']} ({budget['used_pct']}%)")
        print(f"  Remaining: ${budget['remaining_usd']:.4f}")


if __name__ == "__main__":
    main()
