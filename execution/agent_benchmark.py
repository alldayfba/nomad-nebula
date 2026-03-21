#!/usr/bin/env python3
"""
Script: agent_benchmark.py
Purpose: Automated quality tests for agents. Sends test prompts to each agent's
         domain, scores the output, tracks quality over time, and generates
         proposals when benchmarks fail.

Usage:
  python execution/agent_benchmark.py --run              # Run all benchmarks
  python execution/agent_benchmark.py --run --agent CEO  # Run CEO benchmarks only
  python execution/agent_benchmark.py --report           # Show benchmark history
  python execution/agent_benchmark.py --add --agent outreach --prompt "..." --criteria "..."

Like unit tests for agents. Run weekly to catch quality drift early.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import anthropic
except ImportError:
    print("[benchmark] ERROR: anthropic not installed")
    sys.exit(1)

PROJECT_ROOT = Path(os.environ.get(
    "NOMAD_NEBULA_ROOT",
    "/Users/Shared/antigravity/projects/nomad-nebula"
))

TMP_DIR = PROJECT_ROOT / ".tmp" / "training-officer"
BENCHMARKS_FILE = TMP_DIR / "benchmarks.json"
BENCHMARK_RESULTS = TMP_DIR / "benchmark-results.json"
QUALITY_FILE = TMP_DIR / "quality-scores.json"
PROPOSALS_DIR = TMP_DIR / "proposals"

# Default benchmark test cases per agent
DEFAULT_BENCHMARKS = {
    "CEO": [
        {
            "id": "ceo-brief",
            "prompt": "Generate a morning brief for a growth agency with these KPIs: MRR $45K, churn 8%, close rate 22%, CPL $85. Constraint: close rate is below 25% threshold.",
            "criteria": "Must include: KPI summary, constraint identification, optimization recommendations, delegation suggestions. Must NOT include: vague advice, missing numbers.",
            "min_score": 7,
        },
        {
            "id": "ceo-delegation",
            "prompt": "A new Dream 100 prospect was identified: John Smith, owns a $2M fitness brand, runs Facebook ads with high CPL. Which agent should handle this and what should the delegation look like?",
            "criteria": "Must delegate to outreach agent. Must include: delegation format (to, why, context, deliverable, deadline). Must NOT delegate Dream 100 to content or ads-copy.",
            "min_score": 7,
        },
    ],
    "outreach": [
        {
            "id": "outreach-dream100",
            "prompt": "Research this prospect for Dream 100 outreach: Sarah Chen, CEO of FitFuel (fitfuel.co), $3M revenue, runs YouTube ads and has a weak landing page. Generate the first touch email.",
            "criteria": "Must reference specific gaps (weak LP). Must include personalized value prop. Must NOT be generic. Must have clear CTA (not 'schedule a call'). Must follow Dream 100 SOP.",
            "min_score": 7,
        },
        {
            "id": "outreach-follow-up",
            "prompt": "Prospect Sarah Chen opened the GammaDoc but didn't reply. Write touch 2 (day 3 follow-up).",
            "criteria": "Must reference that she opened. Must add new value (not just 'checking in'). Must be shorter than first touch. Must maintain professional tone.",
            "min_score": 6,
        },
    ],
    "ads-copy": [
        {
            "id": "ads-meta-hooks",
            "prompt": "Write 3 Meta ad hooks for a growth agency targeting 7-figure founders who are burning ad spend without systems.",
            "criteria": "Must have 3 distinct hooks. Must address specific pain (burning ad spend). Must include ICP language (founder, 7-figure). Must NOT be generic. Each hook < 40 words.",
            "min_score": 7,
        },
    ],
    "content": [
        {
            "id": "content-vsl-hook",
            "prompt": "Write a VSL opening hook (first 30 seconds) for an Amazon FBA coaching program targeting beginners with $10K-$20K capital.",
            "criteria": "Must follow Jeremy Haynes method. Must create urgency. Must address specific ICP (beginner, has capital). Must NOT use value stacks. Must state a specific outcome.",
            "min_score": 7,
        },
    ],
    "lead-gen": [
        {
            "id": "leadgen-strategy",
            "prompt": "Plan a lead generation run: find 50 dentists in Miami FL with websites and emails. What's the scraping strategy?",
            "criteria": "Must reference run_scraper.py. Must specify query, location, max_results. Must mention ICP filtering step. Must mention CSV export.",
            "min_score": 6,
        },
    ],
    "sourcing": [
        {
            "id": "sourcing-pipeline",
            "prompt": "I found a Walmart clearance page with electronics. Walk me through the FBA sourcing pipeline.",
            "criteria": "Must reference: scrape → match → calculate → export. Must mention ROI threshold (50%+), min profit ($5+). Must mention seller competition check. Must reference run_sourcing_pipeline.py.",
            "min_score": 7,
        },
    ],
    "amazon": [
        {
            "id": "amazon-ppc",
            "prompt": "My Amazon PPC has 45% ACOS on a product with 30% margin. What should I do?",
            "criteria": "Must identify ACOS is too high for margin. Must suggest: negative keywords, bid adjustments, campaign restructuring. Must reference target ACOS relative to margin.",
            "min_score": 6,
        },
    ],
}


def ensure_dirs():
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)


def load_env():
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_benchmarks() -> dict:
    """Load custom benchmarks, merged with defaults."""
    benchmarks = dict(DEFAULT_BENCHMARKS)
    if BENCHMARKS_FILE.exists():
        custom = json.loads(BENCHMARKS_FILE.read_text())
        for agent, tests in custom.items():
            if agent in benchmarks:
                benchmarks[agent].extend(tests)
            else:
                benchmarks[agent] = tests
    return benchmarks


def load_results() -> list:
    if BENCHMARK_RESULTS.exists():
        return json.loads(BENCHMARK_RESULTS.read_text())
    return []


def save_results(results: list):
    BENCHMARK_RESULTS.write_text(json.dumps(results[-200:], indent=2, default=str))


def run_benchmark(agent: str, test: dict) -> dict:
    """Run a single benchmark test. Returns score and analysis."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    # Load agent context
    agent_files = {
        "CEO": "SabboOS/Agents/CEO.md",
        "outreach": "bots/outreach/skills.md",
        "ads-copy": "bots/ads-copy/skills.md",
        "content": "bots/content/skills.md",
        "lead-gen": "directives/lead-gen-sop.md",
        "sourcing": "SabboOS/Agents/Sourcing.md",
        "amazon": "bots/amazon/skills.md",
        "WebBuild": "SabboOS/Agents/WebBuild.md",
    }

    context = ""
    agent_file = agent_files.get(agent)
    if agent_file:
        fp = PROJECT_ROOT / agent_file
        if fp.exists():
            context = fp.read_text()[:3000]

    # Step 1: Generate agent output
    try:
        output_msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=f"You are the {agent} agent in SabboOS. Your skills and context:\n{context[:2000]}",
            messages=[{"role": "user", "content": test["prompt"]}],
        )
        agent_output = output_msg.content[0].text
    except Exception as e:
        return {"score": 0, "output": "", "analysis": f"Failed to generate output: {e}", "passed": False}

    # Step 2: Score the output
    try:
        score_msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": f"""Score this agent output on a 1-10 scale.

Agent: {agent}
Test: {test['id']}
Prompt: {test['prompt']}

Output to score:
{agent_output[:1500]}

Scoring criteria:
{test['criteria']}

Respond with JSON only:
{{"score": 1-10, "analysis": "2 sentences: what's good and what's missing", "passed": true/false}}
"""}],
        )
        raw = score_msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        result["output"] = agent_output[:500]
        return result
    except Exception as e:
        return {"score": 5, "output": agent_output[:500], "analysis": f"Scoring failed: {e}", "passed": False}


def generate_benchmark_proposal(agent: str, test: dict, result: dict):
    """Generate a proposal for a failing benchmark."""
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing = list(PROPOSALS_DIR.glob(f"TP-{today}-*.yaml"))
    seq = len(existing) + 1
    pid = f"TP-{today}-{seq:03d}"

    content = f"""# Training Proposal: {pid}

proposal_id: "{pid}"
created: "{now}"
status: "pending"
theme: "benchmark-fail"

# WHO
target_agent: "{agent}"
target_file: "auto-detect"

# WHAT
upgrade_type: "skill"
title: "Benchmark failed: {test['id']} scored {result.get('score', 0)}/10 (min: {test.get('min_score', 7)})"
description: |
  Agent {agent} failed benchmark test '{test['id']}'.
  Score: {result.get('score', 0)}/10 (minimum: {test.get('min_score', 7)})
  Analysis: {result.get('analysis', 'No analysis')}

# WHY
trigger: "Automated benchmark test"
evidence: "Test prompt: {test['prompt'][:100]}..."
expected_impact: "Improve {agent} quality on {test['id']} to score {test.get('min_score', 7)}+"

# HOW
change_type: "review"
proposed_content: |
  BENCHMARK FAILURE: {test['id']}
  Criteria not met: {test['criteria'][:200]}
  Suggested improvement: Review agent skills for gaps in {test['id']} domain.

# RISK
risk_level: "medium"
rollback_plan: "N/A — review-only proposal"
dependencies: []
"""
    (PROPOSALS_DIR / f"{pid}.yaml").write_text(content)
    return pid


def run_all_benchmarks(agent_filter: Optional[str] = None):
    """Run all benchmark tests."""
    benchmarks = load_benchmarks()
    results = load_results()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    total = 0
    passed = 0
    failed = 0

    agents = [agent_filter] if agent_filter else list(benchmarks.keys())

    for agent in agents:
        tests = benchmarks.get(agent, [])
        if not tests:
            continue

        print(f"\n[benchmark] Testing {agent} ({len(tests)} tests)...")

        for test in tests:
            total += 1
            print(f"  [{test['id']}] ", end="", flush=True)

            result = run_benchmark(agent, test)
            score = result.get("score", 0)
            min_score = test.get("min_score", 7)
            test_passed = score >= min_score

            if test_passed:
                passed += 1
                print(f"PASS ({score}/10)")
            else:
                failed += 1
                print(f"FAIL ({score}/10, min: {min_score})")
                print(f"    Analysis: {result.get('analysis', '?')}")
                # Generate proposal for failing benchmark
                pid = generate_benchmark_proposal(agent, test, result)
                print(f"    Proposal: {pid}")

            # Record result
            results.append({
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "agent": agent,
                "test_id": test["id"],
                "score": score,
                "min_score": min_score,
                "passed": test_passed,
                "analysis": result.get("analysis", ""),
            })

            # Also feed into quality tracker
            quality_scores = []
            if QUALITY_FILE.exists():
                quality_scores = json.loads(QUALITY_FILE.read_text())
            quality_scores.append({
                "agent": agent,
                "output_type": f"benchmark:{test['id']}",
                "rating": score,
                "notes": result.get("analysis", ""),
                "timestamp": datetime.now().isoformat(),
            })
            QUALITY_FILE.write_text(json.dumps(quality_scores, indent=2, default=str))

    save_results(results)

    print(f"\n{'=' * 50}")
    print(f"  BENCHMARK RESULTS: {passed} passed, {failed} failed, {total} total")
    print(f"{'=' * 50}")

    if failed:
        print(f"  {failed} proposal(s) generated for failing tests.")


def show_report():
    """Show benchmark history report."""
    results = load_results()
    if not results:
        print("[benchmark] No results yet. Run --run first.")
        return

    # Group by run
    runs = {}
    for r in results:
        rid = r.get("run_id", "?")
        if rid not in runs:
            runs[rid] = []
        runs[rid].append(r)

    print(f"\n{'=' * 60}")
    print(f"  BENCHMARK HISTORY")
    print(f"{'=' * 60}\n")

    for rid, tests in sorted(runs.items(), key=lambda x: x[0])[-5:]:
        passed = sum(1 for t in tests if t.get("passed"))
        total = len(tests)
        ts = tests[0].get("timestamp", "?")[:16]
        print(f"  Run {rid} ({ts}): {passed}/{total} passed")
        for t in tests:
            icon = "PASS" if t.get("passed") else "FAIL"
            print(f"    {icon} {t['agent']}/{t['test_id']}: {t['score']}/{t['min_score']}")

    # Trend per agent
    print(f"\n  Agent trends (last 3 runs):")
    agents = set(r["agent"] for r in results)
    for agent in sorted(agents):
        agent_results = [r for r in results if r["agent"] == agent]
        recent = agent_results[-9:]  # Last ~3 runs worth
        if recent:
            avg = sum(r["score"] for r in recent) / len(recent)
            pass_rate = sum(1 for r in recent if r.get("passed")) / len(recent) * 100
            print(f"    {agent:<15s} avg: {avg:.1f}/10, pass rate: {pass_rate:.0f}%")
    print()


def main():
    parser = argparse.ArgumentParser(description="Agent Benchmark Suite")
    parser.add_argument("--run", action="store_true", help="Run benchmarks")
    parser.add_argument("--agent", type=str, help="Filter by agent")
    parser.add_argument("--report", action="store_true", help="Show benchmark history")
    parser.add_argument("--add", action="store_true", help="Add custom benchmark")
    parser.add_argument("--prompt", type=str, help="Test prompt (with --add)")
    parser.add_argument("--criteria", type=str, help="Scoring criteria (with --add)")
    args = parser.parse_args()

    ensure_dirs()
    load_env()

    if args.run:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("[benchmark] ERROR: ANTHROPIC_API_KEY not set")
            sys.exit(1)
        run_all_benchmarks(args.agent)
    elif args.report:
        show_report()
    elif args.add:
        if not args.agent or not args.prompt or not args.criteria:
            print("[benchmark] --add requires --agent, --prompt, and --criteria")
            sys.exit(1)
        benchmarks = {}
        if BENCHMARKS_FILE.exists():
            benchmarks = json.loads(BENCHMARKS_FILE.read_text())
        if args.agent not in benchmarks:
            benchmarks[args.agent] = []
        benchmarks[args.agent].append({
            "id": f"custom-{len(benchmarks[args.agent])+1}",
            "prompt": args.prompt,
            "criteria": args.criteria,
            "min_score": 7,
        })
        BENCHMARKS_FILE.write_text(json.dumps(benchmarks, indent=2))
        print(f"[benchmark] Added custom benchmark for {args.agent}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
