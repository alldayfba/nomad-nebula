#!/usr/bin/env python3
"""
append_learned_rule.py — Append a numbered learned rule to any instruction file.

Finds the ## Learned Rules section, deduplicates, and appends a new rule.

Usage:
    python execution/append_learned_rule.py \
        --file .claude/CLAUDE.md \
        --category FRONTEND \
        --rule "Never use dark mode" \
        --reason "User preference from 2026-03-15"

    python execution/append_learned_rule.py \
        --file CLAUDE.md \
        --category WORKFLOW \
        --rule "Always run ICP filter before email gen" \
        --reason "Unfiltered leads waste API tokens"
"""
from __future__ import annotations

import argparse
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

VALID_CATEGORIES = [
    "FRONTEND", "BACKEND", "COPY", "WORKFLOW",
    "TOOLING", "DATA", "SECURITY", "GENERAL",
]

SIMILARITY_THRESHOLD = 0.75  # above this = duplicate


def find_learned_rules_section(lines: list[str]) -> int | None:
    """Return the line index of '## Learned Rules' header, or None."""
    for i, line in enumerate(lines):
        if line.strip().lower() == "## learned rules":
            return i
    return None


def get_last_rule_number(lines: list[str], section_start: int) -> int:
    """Find the highest rule number after the section header."""
    highest = 0
    pattern = re.compile(r"^(\d+)\.\s*\[")
    for line in lines[section_start + 1:]:
        # Stop if we hit another ## header
        if line.strip().startswith("## ") and line.strip().lower() != "## learned rules":
            break
        m = pattern.match(line.strip())
        if m:
            highest = max(highest, int(m.group(1)))
    return highest


def get_existing_rules(lines: list[str], section_start: int) -> list[str]:
    """Extract all rule text (without number prefix) after the section header."""
    rules = []
    pattern = re.compile(r"^\d+\.\s*(.+)")
    for line in lines[section_start + 1:]:
        if line.strip().startswith("## ") and line.strip().lower() != "## learned rules":
            break
        m = pattern.match(line.strip())
        if m:
            rules.append(m.group(1))
    return rules


def is_duplicate(new_rule: str, existing_rules: list[str]) -> bool:
    """Check if the new rule is too similar to any existing rule."""
    new_lower = new_rule.lower()
    for existing in existing_rules:
        ratio = SequenceMatcher(None, new_lower, existing.lower()).ratio()
        if ratio >= SIMILARITY_THRESHOLD:
            return True
    return False


def format_rule(number: int, category: str, rule: str, reason: str) -> str:
    """Format a rule line."""
    # Normalize: ensure rule starts with Always/Never
    rule = rule.strip().rstrip(".")
    reason = reason.strip().rstrip(".")
    return f"{number}. [{category}] {rule} because {reason}."


def append_rule(file_path: Path, category: str, rule: str, reason: str) -> dict:
    """Append a learned rule to the file. Returns status dict."""
    if not file_path.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    section_idx = find_learned_rules_section(lines)

    if section_idx is None:
        # Create the section at the end
        lines.append("")
        lines.append("## Learned Rules")
        lines.append("")
        section_idx = len(lines) - 2  # points to the "## Learned Rules" line

    existing = get_existing_rules(lines, section_idx)
    candidate = f"[{category}] {rule} because {reason}."

    if is_duplicate(candidate, existing):
        return {"success": False, "error": "Duplicate rule detected", "similar_to": candidate}

    last_num = get_last_rule_number(lines, section_idx)
    new_num = last_num + 1
    formatted = format_rule(new_num, category, rule, reason)

    # Find insertion point: after last rule or after header + blank line
    insert_idx = section_idx + 1
    for i in range(section_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("## ") and stripped.lower() != "## learned rules":
            insert_idx = i
            break
        if stripped:
            insert_idx = i + 1
    else:
        insert_idx = len(lines)

    lines.insert(insert_idx, formatted)
    file_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "success": True,
        "rule_number": new_num,
        "rule": formatted,
        "file": str(file_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Append a learned rule to an instruction file")
    parser.add_argument("--file", required=True, help="Path to the instruction file (CLAUDE.md, AGENTS.md, etc.)")
    parser.add_argument("--category", required=True, choices=VALID_CATEGORIES, help="Rule category")
    parser.add_argument("--rule", required=True, help='The rule itself (e.g., "Never use dark mode")')
    parser.add_argument("--reason", required=True, help='Why this rule exists (e.g., "User preference")')
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_absolute():
        # Try relative to project root
        project_root = Path(__file__).parent.parent
        file_path = project_root / args.file

    result = append_rule(file_path, args.category, args.rule, args.reason)

    if result["success"]:
        print(f"✓ Rule #{result['rule_number']} appended to {result['file']}")
        print(f"  {result['rule']}")
    else:
        print(f"✗ {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
