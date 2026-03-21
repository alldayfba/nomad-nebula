# Stochastic Multi-Agent Consensus SOP
> directives/consensus-sop.md | Version 1.0

---

## Purpose

Spawn multiple AI agents with the same prompt. Analyze the spread of their responses to find high-confidence consensus and flag divergent outliers. Better than single-agent for high-stakes decisions.

---

## When to Use

**Use consensus for:**
- High-stakes copy (VSL hooks, ad headlines, email subject lines)
- Architecture decisions with multiple valid approaches
- ICP scoring edge cases (borderline leads)
- Offer positioning or pricing decisions
- Any decision where being wrong is expensive

**Don't use for:**
- Deterministic tasks (scraping, file ops, CSV processing)
- Tasks with a single correct answer
- Quick/cheap tasks where latency matters more than quality
- Tasks within a pipeline that runs automatically

---

## Modes

### Lightweight (Single-Model, Multi-Run)
- 3-5 runs of Claude Sonnet at temperature 0.7-0.9
- Cheapest. Fastest. Good for copy ideation.
- `--models claude --runs 5 --temperature 0.9`

### Standard (Multi-Model)
- 1 run each of Claude + Gemini + OpenAI
- Tests cross-model agreement. Good for architecture decisions.
- `--models claude,gemini,openai --runs 1`

### Deep (Multi-Model, Multi-Run)
- 3 runs each across 2-3 models = 6-9 total responses
- Most expensive. Use for $10K+ decisions.
- `--models claude,gemini,openai --runs 3`

---

## Interpreting Results

| Confidence | Avg Similarity | Meaning |
|---|---|---|
| **High** | ≥ 0.60 | Strong agreement. Safe to proceed with consensus answer. |
| **Medium** | 0.35–0.59 | Partial agreement. Review the outlier before deciding. |
| **Low** | < 0.35 | Wide disagreement. The question may be ambiguous or have multiple valid answers. Consider rephrasing or deciding manually. |

---

## Execution

```bash
python execution/consensus_engine.py \
    --prompt "What's the strongest hook for a $10K Amazon FBA coaching offer?" \
    --models claude,gemini \
    --runs 3 \
    --temperature 0.8 \
    --save .tmp/consensus/hooks_$(date +%Y%m%d).json
```

---

## Cost Estimate

| Mode | Models | Runs | Est. Tokens | Est. Cost |
|---|---|---|---|---|
| Lightweight | Claude Sonnet ×5 | 5 | ~15K | ~$0.14 |
| Standard | Claude + Gemini + GPT ×1 | 3 | ~9K | ~$0.05 |
| Deep | Claude + Gemini + GPT ×3 | 9 | ~27K | ~$0.15 |
