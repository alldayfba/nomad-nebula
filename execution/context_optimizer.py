#!/usr/bin/env python3
"""
context_optimizer.py — Context Management & Optimization.

Prevents context bloat from degrading agent quality. Compresses completed steps,
filters irrelevant context, and manages context budgets per model/task.

Usage:
    # Compress a conversation log
    python execution/context_optimizer.py compress \
        --input .tmp/conversation.json \
        --output .tmp/compressed.json

    # Check brain.md health
    python execution/context_optimizer.py brain-health

    # Archive old brain.md sections
    python execution/context_optimizer.py archive-brain --max-lines 500

    # Programmatic:
    from execution.context_optimizer import ContextOptimizer
    optimizer = ContextOptimizer()
    compressed = optimizer.compress_context(conversation_history)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

BRAIN_PATH = Path("/Users/Shared/antigravity/memory/ceo/brain.md")
BRAIN_ARCHIVE_PATH = Path("/Users/Shared/antigravity/memory/ceo/brain_archive.md")

# Context budgets: max tokens per model-task combo
CONTEXT_BUDGETS = {
    # (model_tier, task_type) → max_context_tokens
    (1, "routine"): 4000,      # Haiku/Flash: keep context small
    (1, "classification"): 2000,
    (2, "generation"): 16000,   # Sonnet/Pro: moderate context
    (2, "code"): 32000,        # Code tasks need more context
    (2, "research"): 48000,    # Research needs lots of reference material
    (3, "high_stakes"): 64000, # Opus: full context for complex tasks
    (3, "architecture"): 64000,
}
DEFAULT_BUDGET = 16000


class ContextOptimizer:
    """Manages and optimizes context for agent interactions."""

    def compress_context(self, messages: list[dict], keep_last_n: int = 5) -> list[dict]:
        """Compress a conversation by summarizing older messages.

        Keeps the last N messages intact, summarizes everything before that.
        """
        if len(messages) <= keep_last_n:
            return messages

        # Split into old and recent
        old_messages = messages[:-keep_last_n]
        recent_messages = messages[-keep_last_n:]

        # Summarize old messages
        summary_parts = []
        for msg in old_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "tool_result" or role == "tool_use":
                # Compress tool calls to just the outcome
                summary_parts.append(f"[Tool: {msg.get('name', '?')} → {content[:100]}...]")
            elif role == "assistant":
                # Keep first sentence of assistant messages
                first_sentence = content.split(".")[0] + "." if "." in content else content[:100]
                summary_parts.append(f"[Assistant: {first_sentence}]")
            elif role == "user":
                summary_parts.append(f"[User: {content[:150]}]")

        summary = {
            "role": "system",
            "content": f"[COMPRESSED CONTEXT — {len(old_messages)} messages summarized]\n" +
                       "\n".join(summary_parts),
        }

        return [summary] + recent_messages

    def relevance_filter(self, context_chunks: list[str], current_task: str,
                         threshold: float = 0.2) -> list[str]:
        """Filter context chunks by relevance to the current task.

        Uses keyword overlap as a fast heuristic (no API calls).
        """
        task_words = set(current_task.lower().split())
        # Remove common stop words
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "have", "has", "had", "do", "does", "did", "will", "would",
                      "could", "should", "may", "might", "can", "to", "of", "in",
                      "for", "on", "with", "at", "by", "from", "this", "that", "it",
                      "and", "or", "but", "not", "no", "if", "then", "so", "as"}
        task_words -= stop_words

        if not task_words:
            return context_chunks  # Can't filter without keywords

        scored = []
        for chunk in context_chunks:
            chunk_words = set(chunk.lower().split()) - stop_words
            if not chunk_words:
                scored.append((0, chunk))
                continue
            overlap = len(task_words & chunk_words)
            score = overlap / max(len(task_words), 1)
            scored.append((score, chunk))

        # Keep chunks above threshold, plus always keep first and last
        filtered = []
        for i, (score, chunk) in enumerate(scored):
            if score >= threshold or i == 0 or i == len(scored) - 1:
                filtered.append(chunk)

        return filtered

    def context_budget(self, model_tier: int = 2, task_type: str = "generation") -> int:
        """Return optimal context size (in tokens) for model+task combo."""
        return CONTEXT_BUDGETS.get((model_tier, task_type), DEFAULT_BUDGET)

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate: 1 token ≈ 4 chars for English."""
        return len(text) // 4

    def trim_to_budget(self, text: str, model_tier: int = 2, task_type: str = "generation") -> str:
        """Trim text to fit within context budget."""
        budget = self.context_budget(model_tier, task_type)
        budget_chars = budget * 4  # Convert tokens back to chars

        if len(text) <= budget_chars:
            return text

        # Trim from the middle (keep start and end)
        keep_start = budget_chars // 2
        keep_end = budget_chars // 2
        return (
            text[:keep_start] +
            f"\n\n[... {len(text) - budget_chars} chars trimmed ...]\n\n" +
            text[-keep_end:]
        )


# ── Brain Health ──────────────────────────────────────────────────────────────

def check_brain_health() -> dict:
    """Check brain.md health metrics."""
    if not BRAIN_PATH.exists():
        return {"error": "brain.md not found", "path": str(BRAIN_PATH)}

    content = BRAIN_PATH.read_text(encoding="utf-8")
    lines = content.split("\n")
    sections = [l for l in lines if l.startswith("## ")]

    # Find potential issues
    issues = []
    if len(lines) > 500:
        issues.append(f"Brain is {len(lines)} lines (recommended max: 500). Consider archiving.")
    if len(content) > 50000:
        issues.append(f"Brain is {len(content)} chars. Large brains slow down boot sequence.")

    # Check for duplicate entries (simple heuristic)
    seen_lines = set()
    duplicates = 0
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 20 and stripped in seen_lines:
            duplicates += 1
        seen_lines.add(stripped)

    if duplicates > 5:
        issues.append(f"{duplicates} likely duplicate lines detected.")

    # Check freshness
    # Look for dates in the content
    date_pattern = re.compile(r"20\d{2}-\d{2}-\d{2}")
    dates = date_pattern.findall(content)
    if dates:
        latest = max(dates)
        try:
            latest_date = datetime.strptime(latest, "%Y-%m-%d")
            age_days = (datetime.now() - latest_date).days
            if age_days > 7:
                issues.append(f"Latest entry is {age_days} days old. Brain may be stale.")
        except ValueError:
            pass

    return {
        "path": str(BRAIN_PATH),
        "lines": len(lines),
        "chars": len(content),
        "sections": len(sections),
        "section_names": [s.replace("## ", "") for s in sections[:20]],
        "estimated_tokens": len(content) // 4,
        "issues": issues,
        "health": "healthy" if not issues else "needs_attention",
    }


def archive_brain(max_lines: int = 500) -> dict:
    """Archive old brain.md content beyond max_lines threshold."""
    if not BRAIN_PATH.exists():
        return {"error": "brain.md not found"}

    content = BRAIN_PATH.read_text(encoding="utf-8")
    lines = content.split("\n")

    if len(lines) <= max_lines:
        return {"action": "none", "reason": f"Brain is {len(lines)} lines (under {max_lines} limit)"}

    # Keep first max_lines, archive the rest
    keep = lines[:max_lines]
    archive = lines[max_lines:]

    # Write archive
    archive_header = f"\n\n---\n## Archived {datetime.now().strftime('%Y-%m-%d')}\n\n"
    if BRAIN_ARCHIVE_PATH.exists():
        existing_archive = BRAIN_ARCHIVE_PATH.read_text(encoding="utf-8")
    else:
        existing_archive = "# CEO Brain Archive\n\nArchived sections from brain.md.\n"

    BRAIN_ARCHIVE_PATH.write_text(
        existing_archive + archive_header + "\n".join(archive),
        encoding="utf-8",
    )

    # Trim brain.md
    keep.append(f"\n\n<!-- Archived {len(archive)} lines to brain_archive.md on {datetime.now().strftime('%Y-%m-%d')} -->")
    BRAIN_PATH.write_text("\n".join(keep), encoding="utf-8")

    return {
        "action": "archived",
        "lines_archived": len(archive),
        "lines_remaining": len(keep),
        "archive_path": str(BRAIN_ARCHIVE_PATH),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Context management and optimization")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Compress
    compress_parser = subparsers.add_parser("compress", help="Compress a conversation log")
    compress_parser.add_argument("--input", required=True, help="Input JSON file")
    compress_parser.add_argument("--output", required=True, help="Output JSON file")
    compress_parser.add_argument("--keep-last", type=int, default=5, help="Messages to keep uncompressed")

    # Brain health
    subparsers.add_parser("brain-health", help="Check brain.md health")

    # Archive brain
    archive_parser = subparsers.add_parser("archive-brain", help="Archive old brain.md sections")
    archive_parser.add_argument("--max-lines", type=int, default=500)

    # Budget check
    budget_parser = subparsers.add_parser("budget", help="Show context budgets")
    budget_parser.add_argument("--tier", type=int, default=2)
    budget_parser.add_argument("--task", default="generation")

    args = parser.parse_args()
    optimizer = ContextOptimizer()

    if args.command == "compress":
        input_data = json.loads(Path(args.input).read_text())
        messages = input_data if isinstance(input_data, list) else input_data.get("messages", [])
        compressed = optimizer.compress_context(messages, args.keep_last)
        Path(args.output).write_text(json.dumps(compressed, indent=2))
        print(f"✓ Compressed {len(messages)} → {len(compressed)} messages")

    elif args.command == "brain-health":
        health = check_brain_health()
        print(f"Brain Health: {health['health'].upper()}")
        print(f"  Lines: {health.get('lines', '?')} | Chars: {health.get('chars', '?')} | Tokens: ~{health.get('estimated_tokens', '?')}")
        print(f"  Sections: {health.get('sections', '?')}")
        if health.get("issues"):
            print(f"  Issues:")
            for issue in health["issues"]:
                print(f"    ⚠ {issue}")
        else:
            print(f"  No issues detected.")

    elif args.command == "archive-brain":
        result = archive_brain(args.max_lines)
        if result.get("action") == "archived":
            print(f"✓ Archived {result['lines_archived']} lines to {result['archive_path']}")
            print(f"  Brain now: {result['lines_remaining']} lines")
        else:
            print(f"No action needed: {result.get('reason', result.get('error', '?'))}")

    elif args.command == "budget":
        budget = optimizer.context_budget(args.tier, args.task)
        print(f"Context budget: {budget:,} tokens (~{budget * 4:,} chars)")
        print(f"  Tier {args.tier} / Task: {args.task}")


if __name__ == "__main__":
    main()
