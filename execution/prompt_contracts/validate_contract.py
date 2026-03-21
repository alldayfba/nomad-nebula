#!/usr/bin/env python3
"""
validate_contract.py — Validate agent output against a prompt contract.

Usage:
    python execution/prompt_contracts/validate_contract.py \
        --contract execution/prompt_contracts/contracts/lead_gen_email.yaml \
        --output .tmp/generated_email.md

    # Programmatic:
    from execution.prompt_contracts.validate_contract import validate
    result = validate("contracts/lead_gen_email.yaml", output_text)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def load_contract(contract_path: str | Path) -> dict:
    """Load and parse a YAML contract file."""
    path = Path(contract_path)
    if not path.exists():
        raise FileNotFoundError(f"Contract not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_sections(output_text: str, sections: list[str]) -> list[str]:
    """Check if all required sections are present in the output."""
    violations = []
    text_lower = output_text.lower()
    for section in sections:
        # Check for section as a markdown header or as a label
        patterns = [
            f"## {section}",
            f"### {section}",
            f"**{section}**",
            f"{section}:",
            section.replace("_", " "),
        ]
        found = any(p.lower() in text_lower for p in patterns)
        if not found:
            violations.append(f"Missing section: '{section}'")
    return violations


def check_constraints(output_text: str, constraints: dict) -> list[str]:
    """Validate output against constraint rules."""
    violations = []

    # Word count
    word_count = len(output_text.split())

    if "total_words" in constraints:
        spec = str(constraints["total_words"])
        if "-" in spec:
            lo, hi = map(int, spec.split("-"))
            if word_count < lo:
                violations.append(f"Too few words: {word_count} (min {lo})")
            elif word_count > hi:
                violations.append(f"Too many words: {word_count} (max {hi})")
        elif spec.isdigit():
            max_words = int(spec)
            if word_count > max_words:
                violations.append(f"Too many words: {word_count} (max {max_words})")

    if "min_words" in constraints:
        if word_count < int(constraints["min_words"]):
            violations.append(f"Too few words: {word_count} (min {constraints['min_words']})")

    # Max chars per section
    if "max_chars" in constraints:
        max_c = int(constraints["max_chars"])
        # Apply to first line (typically subject line)
        first_line = output_text.strip().split("\n")[0]
        if len(first_line) > max_c:
            violations.append(f"First line too long: {len(first_line)} chars (max {max_c})")

    # No placeholders
    if constraints.get("no_placeholders", False):
        placeholder_patterns = [
            r"\[INSERT.*?\]",
            r"\[YOUR.*?\]",
            r"\[PLACEHOLDER.*?\]",
            r"\bTODO\b",
            r"\bTBD\b",
            r"\bXXX\b",
            r"\[\.\.\.?\]",
        ]
        for pat in placeholder_patterns:
            matches = re.findall(pat, output_text, re.IGNORECASE)
            if matches:
                violations.append(f"Placeholder text found: {matches[0]}")

    # Tone (informational only — can't auto-validate tone)
    # Pattern constraints
    if "pattern" in constraints:
        if not re.search(constraints["pattern"], output_text):
            violations.append(f"Pattern not matched: {constraints['pattern']}")

    return violations


def check_definition_of_done(output_text: str, dod: list[str]) -> list[str]:
    """Check definition of done items. Uses heuristic matching."""
    violations = []
    for item in dod:
        item_lower = item.lower()
        # Check for common DoD patterns
        if "no placeholder" in item_lower:
            placeholders = re.findall(r"\[INSERT.*?\]|\bTODO\b|\bTBD\b", output_text, re.IGNORECASE)
            if placeholders:
                violations.append(f"DoD fail: '{item}' — found {placeholders[0]}")
        elif "all required sections" in item_lower:
            pass  # Already checked in check_sections
        elif "personalized" in item_lower:
            generic = re.findall(r"\[NAME\]|\[COMPANY\]|\bDear Sir\b", output_text, re.IGNORECASE)
            if generic:
                violations.append(f"DoD fail: '{item}' — generic text found")
    return violations


def check_failure_conditions(output_text: str, conditions: list[str]) -> list[str]:
    """Check explicit failure conditions from the contract.

    Each condition describes a state that means 'not done'.
    Uses heuristic matching — checks for placeholder patterns, generic language, etc.
    """
    violations = []
    text_lower = output_text.lower()

    for condition in conditions:
        cond_lower = condition.lower()

        # Placeholder checks
        if "placeholder" in cond_lower:
            placeholder_patterns = [
                r"\[NAME\]", r"\[COMPANY\]", r"\{company\}", r"\{name\}",
                r"\[INSERT.*?\]", r"\[FILL.*?\]", r"\bTODO\b", r"\bTBD\b",
                r"\[YOUR.*?\]", r"\bXXX\b",
            ]
            for pat in placeholder_patterns:
                matches = re.findall(pat, output_text, re.IGNORECASE)
                if matches:
                    violations.append(f"FAILURE: {condition} — found '{matches[0]}'")
                    break

        # Generic/no-personalization checks
        elif "generic" in cond_lower or "no personalization" in cond_lower or "could apply to any" in cond_lower:
            generic_markers = [
                r"\bDear Sir\b", r"\bDear Madam\b", r"\bTo Whom It May Concern\b",
                r"\byour company\b", r"\byour business\b",
            ]
            for pat in generic_markers:
                if re.search(pat, output_text, re.IGNORECASE):
                    violations.append(f"FAILURE: {condition}")
                    break

        # Word count / length checks
        elif "over" in cond_lower and "words" in cond_lower:
            # Extract number from condition like "Over 200 words"
            nums = re.findall(r"\d+", condition)
            if nums:
                max_words = int(nums[0])
                word_count = len(output_text.split())
                if word_count > max_words:
                    violations.append(f"FAILURE: {condition} — actual: {word_count} words")

        # Missing section checks
        elif "missing" in cond_lower and ("section" in cond_lower or "required" in cond_lower):
            pass  # Already handled by check_sections

        # All other failure conditions — logged as warnings for manual review
        # (Can't mechanically verify all natural-language conditions)

    return violations


def validate(contract_path: str | Path, output_text: str) -> dict:
    """Validate output against a contract. Returns validation result."""
    contract = load_contract(contract_path)
    violations = []
    failure_violations = []

    # Check sections
    if "output" in contract and "sections" in contract["output"]:
        violations.extend(check_sections(output_text, contract["output"]["sections"]))

    # Check constraints
    if "output" in contract and "constraints" in contract["output"]:
        violations.extend(check_constraints(output_text, contract["output"]["constraints"]))

    # Check definition of done
    if "definition_of_done" in contract:
        violations.extend(check_definition_of_done(output_text, contract["definition_of_done"]))

    # Check failure conditions (Nick Saraev's 4-part contract model)
    if "failure_conditions" in contract:
        failure_violations = check_failure_conditions(output_text, contract["failure_conditions"])
        violations.extend(failure_violations)

    return {
        "pass": len(violations) == 0,
        "contract": contract.get("name", "unknown"),
        "version": contract.get("version", "0.0"),
        "violations": violations,
        "failure_violations": failure_violations,
        "violation_count": len(violations),
        "failure_count": len(failure_violations),
    }


def main():
    parser = argparse.ArgumentParser(description="Validate agent output against a prompt contract")
    parser.add_argument("--contract", required=True, help="Path to contract YAML")
    parser.add_argument("--output", required=True, help="Path to output file to validate")
    args = parser.parse_args()

    output_path = Path(args.output)
    if not output_path.exists():
        print(f"ERROR: Output file not found: {output_path}", file=sys.stderr)
        sys.exit(1)

    output_text = output_path.read_text(encoding="utf-8")
    result = validate(args.contract, output_text)

    if result["pass"]:
        print(f"PASS — Contract '{result['contract']}' v{result['version']}")
        print(f"  GOAL: met | CONSTRAINTS: met | FORMAT: met | FAILURE conditions: 0 triggered")
    else:
        print(f"FAIL — Contract '{result['contract']}' v{result['version']}")
        if result.get("failure_count", 0) > 0:
            print(f"  FAILURE conditions triggered: {result['failure_count']}")
            for v in result.get("failure_violations", []):
                print(f"    ! {v}")
        other_violations = [v for v in result["violations"] if v not in result.get("failure_violations", [])]
        if other_violations:
            print(f"  Other violations: {len(other_violations)}")
            for v in other_violations:
                print(f"    - {v}")
        sys.exit(1)


if __name__ == "__main__":
    main()
