#!/usr/bin/env python3
"""
smart_router.py — Route tasks to the cheapest sufficient model.

Classifies task complexity and returns the recommended model + estimated cost.

Usage:
    python execution/smart_router.py --task "scrape Google Maps for dentists in Miami"
    python execution/smart_router.py --task "write a VSL script for Agency OS"
    python execution/smart_router.py --task "analyze this screenshot for UI issues"

    # Programmatic:
    from execution.smart_router import route_task
    result = route_task("write a cold email for dental clinic lead")
"""
from __future__ import annotations

import argparse
import re
import sys

# ── Model Definitions ─────────────────────────────────────────────────────────

MODELS = {
    "claude-haiku-4-5-20251001": {
        "provider": "anthropic",
        "tier": 1,
        "cost_per_1k_tokens": 0.00075,  # blended average
        "strengths": ["fast", "cheap", "classification", "parsing", "file_ops"],
    },
    "gemini-2.0-flash": {
        "provider": "google",
        "tier": 1,
        "cost_per_1k_tokens": 0.00025,
        "strengths": ["fast", "cheap", "classification", "multimodal"],
    },
    "gpt-4.1-mini": {
        "provider": "openai",
        "tier": 1,
        "cost_per_1k_tokens": 0.001,
        "strengths": ["fast", "cheap", "backend", "math"],
    },
    "claude-sonnet-4-6": {
        "provider": "anthropic",
        "tier": 2,
        "cost_per_1k_tokens": 0.009,
        "strengths": ["code", "orchestration", "email", "ads", "research"],
    },
    "gemini-2.0-pro": {
        "provider": "google",
        "tier": 2,
        "cost_per_1k_tokens": 0.003125,
        "strengths": ["frontend", "design", "multimodal", "video"],
    },
    "gpt-4.1": {
        "provider": "openai",
        "tier": 2,
        "cost_per_1k_tokens": 0.005,
        "strengths": ["backend", "math", "tdd", "code_review"],
    },
    "claude-opus-4-6": {
        "provider": "anthropic",
        "tier": 3,
        "cost_per_1k_tokens": 0.045,
        "strengths": ["vsl", "high_stakes_copy", "complex_reasoning", "architecture"],
    },
}

# ── Task Classification ───────────────────────────────────────────────────────

TASK_PATTERNS = {
    # Tier 1 (cheap) tasks
    "scrape|parse|csv|classify|tag|format|heartbeat|check|ping|validate|lint": {
        "tier": 1,
        "category": "routine",
    },
    # Tier 2 (moderate) tasks
    "email|ad\\s*script|code|debug|research|brief|outreach|content|blog": {
        "tier": 2,
        "category": "generation",
    },
    # Tier 2 with Gemini preference
    "frontend|design|ui|ux|landing\\s*page|screenshot|image|video|visual": {
        "tier": 2,
        "category": "design",
        "prefer_provider": "google",
    },
    # Tier 2 with OpenAI preference
    "backend|algorithm|math|calcul|test|tdd|code\\s*review|refactor": {
        "tier": 2,
        "category": "backend",
        "prefer_provider": "openai",
    },
    # Tier 3 (expensive) tasks
    "vsl|video\\s*sales|high.?stakes|gammadoc|positioning|strategy|architect": {
        "tier": 3,
        "category": "high_stakes",
    },
}


def classify_task(task_description: str) -> dict:
    """Classify a task and return routing info."""
    task_lower = task_description.lower()

    best_match = {"tier": 2, "category": "generation", "prefer_provider": None}

    for pattern, info in TASK_PATTERNS.items():
        if re.search(pattern, task_lower):
            # Higher tier wins (more specific match)
            if info["tier"] >= best_match["tier"]:
                best_match = {
                    "tier": info["tier"],
                    "category": info["category"],
                    "prefer_provider": info.get("prefer_provider"),
                }

    return best_match


def route_task(task_description: str) -> dict:
    """Route a task to the best model. Returns model + reasoning."""
    classification = classify_task(task_description)
    tier = classification["tier"]
    prefer = classification["prefer_provider"]

    # Find best model for this tier + provider preference
    candidates = [
        (name, info) for name, info in MODELS.items()
        if info["tier"] == tier
    ]

    if prefer:
        preferred = [(n, i) for n, i in candidates if i["provider"] == prefer]
        if preferred:
            candidates = preferred

    if not candidates:
        # Fallback to Sonnet
        candidates = [("claude-sonnet-4-6", MODELS["claude-sonnet-4-6"])]

    # Pick cheapest among candidates
    best = min(candidates, key=lambda x: x[1]["cost_per_1k_tokens"])
    model_name, model_info = best

    # Estimate cost (assume ~2K input + ~1K output tokens for typical task)
    est_input = 2000
    est_output = 1000
    if tier == 3:
        est_input, est_output = 5000, 3000
    elif tier == 1:
        est_input, est_output = 500, 200

    from token_tracker import TokenTracker
    tracker = TokenTracker()
    est_cost = tracker.calculate_cost(model_name, est_input, est_output)

    return {
        "model": model_name,
        "provider": model_info["provider"],
        "tier": tier,
        "category": classification["category"],
        "estimated_cost_usd": est_cost,
        "strengths": model_info["strengths"],
        "reasoning": f"Tier {tier} task ({classification['category']})"
                     + (f", prefer {prefer}" if prefer else "")
                     + f" → {model_name}",
    }


def main():
    parser = argparse.ArgumentParser(description="Route a task to the best model")
    parser.add_argument("--task", required=True, help="Task description")
    args = parser.parse_args()

    result = route_task(args.task)

    print(f"Model: {result['model']}")
    print(f"Provider: {result['provider']}")
    print(f"Tier: {result['tier']} | Category: {result['category']}")
    print(f"Est. cost: ${result['estimated_cost_usd']:.6f}")
    print(f"Reasoning: {result['reasoning']}")


if __name__ == "__main__":
    main()
