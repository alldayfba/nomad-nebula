#!/usr/bin/env python3
"""
verification_loop.py — Sub-Agent Verification Loops.

Agent A (producer) generates output. Agent B (reviewer) reviews it.
If issues found, producer revises. Max 3 cycles.

Usage:
    python execution/verification_loop.py \
        --task "Write a cold email for a dental clinic owner in Miami" \
        --producer-model claude \
        --reviewer-model claude \
        --contract execution/prompt_contracts/contracts/lead_gen_email.yaml

    python execution/verification_loop.py \
        --task "Write an ad script for Amazon FBA coaching" \
        --producer-model claude \
        --reviewer-model gemini

    # Programmatic:
    from execution.verification_loop import run_verification_loop
    result = run_verification_loop(task="...", producer="claude", reviewer="claude")
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# Reuse callers from consensus engine
from consensus_engine import call_claude, call_gemini, call_openai

MODEL_CALLERS = {
    "claude": call_claude,
    "gemini": call_gemini,
    "openai": call_openai,
}

MAX_CYCLES = 3

# ── Review Prompt ─────────────────────────────────────────────────────────────

REVIEW_SYSTEM_PROMPT = """You are a senior quality reviewer. Your job is to review agent output against the original task requirements.

For each review, provide:
1. **VERDICT**: PASS or REVISE
2. **Score**: 1-10 (10 = perfect)
3. **Issues**: Specific problems found (empty if PASS)
4. **Suggestions**: Concrete fixes for each issue

Be strict but fair. Only PASS if the output genuinely meets all requirements.
Format your response as JSON:
{
  "verdict": "PASS" or "REVISE",
  "score": 7,
  "issues": ["issue 1", "issue 2"],
  "suggestions": ["fix 1", "fix 2"]
}"""

REVISION_SYSTEM_PROMPT = """You are revising your previous output based on reviewer feedback.
Apply ALL suggested fixes. Do not explain what you changed — just output the revised version."""


def build_review_prompt(task: str, output: str, contract_text: str = "") -> str:
    """Build the review prompt for the reviewer agent."""
    parts = [f"## Original Task\n{task}\n\n## Output to Review\n{output}"]
    if contract_text:
        parts.append(f"\n## Contract (validation rules)\n{contract_text}")
    parts.append("\nReview this output. Return your assessment as JSON.")
    return "\n".join(parts)


def build_revision_prompt(task: str, output: str, review: dict) -> str:
    """Build the revision prompt for the producer agent."""
    issues = "\n".join(f"- {i}" for i in review.get("issues", []))
    suggestions = "\n".join(f"- {s}" for s in review.get("suggestions", []))
    return (
        f"## Original Task\n{task}\n\n"
        f"## Your Previous Output\n{output}\n\n"
        f"## Reviewer Feedback\nScore: {review.get('score', '?')}/10\n"
        f"Issues:\n{issues}\n\nSuggestions:\n{suggestions}\n\n"
        f"Revise your output to address ALL issues. Output the revised version only."
    )


def parse_review(text: str) -> dict:
    """Parse reviewer response (tries JSON, falls back to heuristic)."""
    # Try JSON parse
    try:
        # Find JSON block in response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass

    # Heuristic fallback
    text_lower = text.lower()
    verdict = "PASS" if "pass" in text_lower and "revise" not in text_lower else "REVISE"

    return {
        "verdict": verdict,
        "score": 5,
        "issues": ["Could not parse structured review — manual review recommended"],
        "suggestions": [],
        "raw": text[:500],
    }


# ── Main Loop ─────────────────────────────────────────────────────────────────

def run_verification_loop(
    task: str,
    producer: str = "claude",
    reviewer: str = "claude",
    contract_path: str = None,
    max_cycles: int = MAX_CYCLES,
    temperature: float = 0.7,
) -> dict:
    """Run the producer → reviewer → revise loop."""
    producer_caller = MODEL_CALLERS.get(producer)
    reviewer_caller = MODEL_CALLERS.get(reviewer)

    if not producer_caller:
        return {"error": f"Unknown producer model: {producer}"}
    if not reviewer_caller:
        return {"error": f"Unknown reviewer model: {reviewer}"}

    # Load contract if provided
    contract_text = ""
    if contract_path:
        cp = Path(contract_path)
        if cp.exists():
            contract_text = cp.read_text(encoding="utf-8")

    cycles = []
    current_output = None

    for cycle_num in range(1, max_cycles + 1):
        # Step 1: Produce (or revise)
        if current_output is None:
            # Initial production
            prod_response = producer_caller(task, temperature=temperature)
        else:
            # Revision based on feedback
            last_review = cycles[-1]["review"]
            revision_prompt = build_revision_prompt(task, current_output, last_review)
            prod_response = producer_caller(revision_prompt, temperature=max(0.3, temperature - 0.2),
                                            system_prompt=REVISION_SYSTEM_PROMPT)

        if "error" in prod_response:
            cycles.append({"cycle": cycle_num, "error": f"Producer error: {prod_response['error']}"})
            break

        current_output = prod_response["text"]

        # Step 2: Review
        review_prompt = build_review_prompt(task, current_output, contract_text)
        rev_response = reviewer_caller(review_prompt, temperature=0.3, system_prompt=REVIEW_SYSTEM_PROMPT)

        if "error" in rev_response:
            cycles.append({
                "cycle": cycle_num,
                "output_preview": current_output[:300],
                "error": f"Reviewer error: {rev_response['error']}",
            })
            break

        review = parse_review(rev_response["text"])

        cycles.append({
            "cycle": cycle_num,
            "producer_model": prod_response.get("model", producer),
            "reviewer_model": rev_response.get("model", reviewer),
            "output_preview": current_output[:300] + "..." if len(current_output) > 300 else current_output,
            "review": review,
        })

        # Step 3: Check verdict
        if review.get("verdict") == "PASS":
            break

    return {
        "task": task[:200],
        "final_output": current_output,
        "final_score": cycles[-1].get("review", {}).get("score") if cycles else None,
        "final_verdict": cycles[-1].get("review", {}).get("verdict") if cycles else None,
        "total_cycles": len(cycles),
        "cycles": cycles,
        "producer_model": producer,
        "reviewer_model": reviewer,
        "timestamp": datetime.now().isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Run sub-agent verification loop")
    parser.add_argument("--task", required=True, help="The task for the producer agent")
    parser.add_argument("--producer-model", default="claude", choices=list(MODEL_CALLERS.keys()))
    parser.add_argument("--reviewer-model", default="claude", choices=list(MODEL_CALLERS.keys()))
    parser.add_argument("--contract", help="Path to prompt contract YAML")
    parser.add_argument("--max-cycles", type=int, default=MAX_CYCLES)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--save", help="Save results to file")
    args = parser.parse_args()

    print(f"Verification loop: {args.producer_model} (producer) → {args.reviewer_model} (reviewer)")
    print(f"Max cycles: {args.max_cycles}")

    result = run_verification_loop(
        task=args.task,
        producer=args.producer_model,
        reviewer=args.reviewer_model,
        contract_path=args.contract,
        max_cycles=args.max_cycles,
        temperature=args.temperature,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"VERIFICATION RESULT — {result['final_verdict']} (Score: {result['final_score']}/10)")
        print(f"Cycles: {result['total_cycles']}/{args.max_cycles}")
        print(f"{'='*60}")
        if result["final_output"]:
            print(f"\nFinal Output:")
            print(result["final_output"][:3000])
        for cycle in result["cycles"]:
            review = cycle.get("review", {})
            if review.get("issues"):
                print(f"\nCycle {cycle['cycle']} issues: {review['issues']}")
        print(f"{'='*60}")

    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(result, indent=2))
        print(f"Saved to {save_path}")


if __name__ == "__main__":
    main()
