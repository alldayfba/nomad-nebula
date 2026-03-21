#!/usr/bin/env python3
"""
consensus_engine.py — Stochastic Multi-Agent Consensus.

Spawns N completions across M models with the same prompt.
Analyzes statistical spread to determine consensus, outliers, and confidence.

Usage:
    # Multi-model consensus (requires API keys for each)
    python execution/consensus_engine.py \
        --prompt "What's the best hook angle for an Amazon FBA coaching ad?" \
        --models claude,gemini,openai \
        --runs 3 \
        --temperature 0.7

    # Single-model consensus (faster, cheaper)
    python execution/consensus_engine.py \
        --prompt "Rank these 3 email subject lines by expected open rate" \
        --models claude \
        --runs 5 \
        --temperature 0.9

    # Programmatic:
    from execution.consensus_engine import run_consensus
    result = run_consensus("prompt here", models=["claude"], runs=3)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── Model Callers ─────────────────────────────────────────────────────────────

def call_claude(prompt: str, temperature: float = 0.7, system_prompt: str = "") -> dict:
    """Call Anthropic Claude API."""
    try:
        import anthropic
    except ImportError:
        return {"error": "pip install anthropic", "model": "claude"}

    client = anthropic.Anthropic()
    try:
        kwargs = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        start = time.time()
        response = client.messages.create(**kwargs)
        elapsed = time.time() - start

        text = response.content[0].text if response.content else ""
        return {
            "model": "claude-sonnet-4-6",
            "provider": "anthropic",
            "text": text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "elapsed_seconds": round(elapsed, 2),
        }
    except Exception as e:
        return {"error": str(e), "model": "claude-sonnet-4-6", "provider": "anthropic"}


def call_gemini(prompt: str, temperature: float = 0.7, system_prompt: str = "") -> dict:
    """Call Google Gemini API."""
    try:
        import google.generativeai as genai
    except ImportError:
        return {"error": "pip install google-generativeai", "model": "gemini"}

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_API_KEY not set", "model": "gemini"}

    genai.configure(api_key=api_key)
    try:
        config = genai.GenerationConfig(temperature=temperature, max_output_tokens=4096)
        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=system_prompt or None,
            generation_config=config,
        )

        start = time.time()
        response = model.generate_content(prompt)
        elapsed = time.time() - start

        text = response.text if response.text else ""
        return {
            "model": "gemini-2.0-flash",
            "provider": "google",
            "text": text,
            "elapsed_seconds": round(elapsed, 2),
        }
    except Exception as e:
        return {"error": str(e), "model": "gemini-2.0-flash", "provider": "google"}


def call_openai(prompt: str, temperature: float = 0.7, system_prompt: str = "") -> dict:
    """Call OpenAI GPT API."""
    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "pip install openai", "model": "openai"}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set", "model": "openai"}

    client = OpenAI(api_key=api_key)
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start = time.time()
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=temperature,
            max_tokens=4096,
        )
        elapsed = time.time() - start

        text = response.choices[0].message.content or ""
        return {
            "model": "gpt-4.1-mini",
            "provider": "openai",
            "text": text,
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
            "elapsed_seconds": round(elapsed, 2),
        }
    except Exception as e:
        return {"error": str(e), "model": "gpt-4.1-mini", "provider": "openai"}


MODEL_CALLERS = {
    "claude": call_claude,
    "gemini": call_gemini,
    "openai": call_openai,
}

# ── Framing Variations (Nick Saraev's 10 stochastic framings) ────────────────

FRAMING_VARIATIONS = [
    {"id": "neutral", "prefix": "Analyze the following problem objectively."},
    {"id": "risk-averse", "prefix": "You are a conservative analyst who weighs downside risks heavily."},
    {"id": "growth-oriented", "prefix": "You are an aggressive strategist who optimizes for upside potential."},
    {"id": "contrarian", "prefix": "Challenge conventional wisdom. What does everyone else get wrong here?"},
    {"id": "first-principles", "prefix": "Reason from first principles. Ignore what's conventional or popular."},
    {"id": "user-empathy", "prefix": "Think from the end-user/customer perspective. What matters most to them?"},
    {"id": "resource-constrained", "prefix": "Assume limited time and budget. What's the highest-leverage move?"},
    {"id": "long-term", "prefix": "Optimize for the 5-year outcome, not the 90-day outcome."},
    {"id": "data-driven", "prefix": "Focus only on what's measurable and provable. Ignore intuition."},
    {"id": "systems-thinker", "prefix": "Map the second and third-order effects. What cascades from each choice?"},
]


def apply_framing(prompt, framing_idx):
    """Prepend a framing variation to the prompt."""
    framing = FRAMING_VARIATIONS[framing_idx % len(FRAMING_VARIATIONS)]
    return "{}\n\n{}".format(framing["prefix"], prompt), framing["id"]


# ── Similarity Analysis ───────────────────────────────────────────────────────

def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Simple word-level Jaccard similarity between two texts."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def analyze_consensus(responses: list[dict]) -> dict:
    """Analyze responses for consensus, outliers, and confidence."""
    valid = [r for r in responses if "error" not in r]
    errors = [r for r in responses if "error" in r]

    if not valid:
        return {"consensus": None, "confidence": "none", "error": "All calls failed", "errors": errors}

    texts = [r["text"] for r in valid]
    n = len(texts)

    # Pairwise similarity matrix
    similarities = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = jaccard_similarity(texts[i], texts[j])
            similarities.append({"pair": (i, j), "similarity": round(sim, 3)})

    avg_similarity = sum(s["similarity"] for s in similarities) / len(similarities) if similarities else 0.0

    # Confidence level
    if avg_similarity >= 0.6:
        confidence = "high"
    elif avg_similarity >= 0.35:
        confidence = "medium"
    else:
        confidence = "low"

    # Find consensus (most similar to all others) and outliers
    if n >= 3:
        avg_sim_per_response = []
        for i in range(n):
            sims = [s["similarity"] for s in similarities if i in s["pair"]]
            avg_sim_per_response.append(sum(sims) / len(sims) if sims else 0)

        consensus_idx = avg_sim_per_response.index(max(avg_sim_per_response))
        outlier_idx = avg_sim_per_response.index(min(avg_sim_per_response))

        consensus_response = valid[consensus_idx]
        outlier_response = valid[outlier_idx] if avg_sim_per_response[outlier_idx] < avg_similarity * 0.7 else None
    else:
        consensus_response = valid[0]  # With only 1-2 responses, first is "consensus"
        outlier_response = None

    return {
        "consensus": {
            "text": consensus_response["text"],
            "model": consensus_response["model"],
        },
        "confidence": confidence,
        "avg_similarity": round(avg_similarity, 3),
        "total_responses": n,
        "errors": len(errors),
        "outlier": {
            "text": outlier_response["text"][:500] + "..." if len(outlier_response["text"]) > 500 else outlier_response["text"],
            "model": outlier_response["model"],
        } if outlier_response else None,
        "all_responses": [
            {"model": r["model"], "preview": r["text"][:200] + "..." if len(r["text"]) > 200 else r["text"]}
            for r in valid
        ],
        "pairwise_similarities": similarities,
    }


# ── Main Engine ───────────────────────────────────────────────────────────────

def run_consensus(
    prompt: str,
    models: list[str] = None,
    runs: int = 3,
    temperature: float = 0.7,
    system_prompt: str = "",
    use_framings: bool = False,
) -> dict:
    """Run consensus across models. Returns analysis.

    When use_framings=True, each run gets a different framing variation
    (Nick Saraev's stochastic diversity approach). This ensures variation
    comes from different perspectives, not just temperature randomness.
    """
    if models is None:
        models = ["claude"]

    # Build task list
    tasks = []
    run_idx = 0
    for model_name in models:
        caller = MODEL_CALLERS.get(model_name)
        if not caller:
            print("Warning: Unknown model '{}', skipping".format(model_name), file=sys.stderr)
            continue
        for _ in range(runs):
            if use_framings:
                framed_prompt, framing_id = apply_framing(prompt, run_idx)
                tasks.append((model_name, caller, framed_prompt, framing_id))
            else:
                tasks.append((model_name, caller, prompt, "none"))
            run_idx += 1

    # Execute in parallel
    responses = []
    with ThreadPoolExecutor(max_workers=min(len(tasks), 10)) as executor:
        futures = {}
        for model_name, caller, task_prompt, framing_id in tasks:
            future = executor.submit(caller, task_prompt, temperature, system_prompt)
            futures[future] = (model_name, framing_id)
        for future in as_completed(futures):
            model_name, framing_id = futures[future]
            result = future.result()
            result["framing"] = framing_id
            responses.append(result)

    # Analyze
    analysis = analyze_consensus(responses)
    analysis["meta"] = {
        "prompt_preview": prompt[:200],
        "models": models,
        "runs_per_model": runs,
        "temperature": temperature,
        "use_framings": use_framings,
        "timestamp": datetime.now().isoformat(),
        "total_calls": len(tasks),
    }

    # Add framing info to response previews
    if use_framings and analysis.get("all_responses"):
        for i, resp in enumerate(analysis["all_responses"]):
            if i < len(responses):
                resp["framing"] = responses[i].get("framing", "none")

    return analysis


def main():
    parser = argparse.ArgumentParser(description="Run stochastic multi-agent consensus")
    parser.add_argument("--prompt", required=True, help="The prompt to send to all models")
    parser.add_argument("--models", default="claude", help="Comma-separated model list: claude,gemini,openai")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per model (default: 3)")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature (default: 0.7)")
    parser.add_argument("--system-prompt", default="", help="Optional system prompt")
    parser.add_argument("--use-framings", action="store_true",
                        help="Apply Nick Saraev's 10 framing variations (stochastic diversity)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--save", help="Save full results to this file path")
    parser.add_argument("--list-framings", action="store_true", help="List available framing variations")
    args = parser.parse_args()

    if args.list_framings:
        print("\nAvailable framing variations:")
        for i, f in enumerate(FRAMING_VARIATIONS):
            print("  {:2d}. {:20s} — {}".format(i + 1, f["id"], f["prefix"][:60]))
        return

    models = [m.strip() for m in args.models.split(",")]
    framing_label = " (with framings)" if args.use_framings else ""
    print("Running consensus{}: {} model(s) x {} runs = {} total calls...".format(
        framing_label, len(models), args.runs, len(models) * args.runs))

    result = run_consensus(
        prompt=args.prompt,
        models=models,
        runs=args.runs,
        temperature=args.temperature,
        system_prompt=args.system_prompt,
        use_framings=args.use_framings,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"CONSENSUS RESULT — Confidence: {result['confidence'].upper()}")
        print(f"Avg similarity: {result['avg_similarity']} | Responses: {result['total_responses']} | Errors: {result['errors']}")
        print(f"{'='*60}")
        if result["consensus"]:
            print(f"\nConsensus ({result['consensus']['model']}):")
            print(result["consensus"]["text"][:2000])
        if result.get("outlier"):
            print(f"\nOutlier ({result['outlier']['model']}):")
            print(result["outlier"]["text"][:500])
        print(f"{'='*60}")

    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(result, indent=2))
        print(f"Saved to {save_path}")


if __name__ == "__main__":
    main()
