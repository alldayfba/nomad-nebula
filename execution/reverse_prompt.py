#!/usr/bin/env python3
"""
reverse_prompt.py — Generate clarifying questions before task execution.

Loads relevant prompt contract, identifies missing fields, and generates
a prioritized questionnaire for the user.

Usage:
    python execution/reverse_prompt.py --task-type ad_campaign
    python execution/reverse_prompt.py --task-type lead_gen_email --context "Client: KD Amazon FBA"
    python execution/reverse_prompt.py --freeform "build me a landing page for my coaching offer"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

CONTRACTS_DIR = Path(__file__).parent / "prompt_contracts" / "contracts"

# Pre-built question sets for common task types (used when no contract exists)
QUESTION_SETS = {
    "client_onboarding": [
        ("What's the business model?", "(product, service, SaaS, coaching)"),
        ("Who is the ICP?", "(demographics, pain points, buying triggers)"),
        ("What's the current traffic source and volume?", None),
        ("What's the primary goal?", "(leads, sales, awareness)"),
        ("Budget range for this engagement?", None),
        ("Timeline or deadline?", None),
    ],
    "ad_campaign": [
        ("Platform?", "(Meta, Google, YouTube, TikTok)"),
        ("Campaign objective?", "(awareness, leads, sales)"),
        ("Target audience?", "(demographics, interests, behaviors)"),
        ("Budget?", "(daily or total)"),
        ("Do you have existing creative assets?", None),
        ("Landing page URL?", None),
    ],
    "content_piece": [
        ("Topic or subject?", None),
        ("Target audience?", None),
        ("Format?", "(blog, social post, video script, email)"),
        ("Tone?", "(professional, casual, authoritative, friendly)"),
        ("Call-to-action?", None),
        ("Distribution channel?", None),
    ],
    "fba_product_eval": [
        ("ASIN or product URL?", None),
        ("Buy cost (or source)?", None),
        ("Expected sell price?", None),
        ("Category?", None),
        ("Is this OA, RA, or wholesale?", None),
    ],
    "email_sequence": [
        ("Who is the recipient?", "(cold lead, warm lead, existing client)"),
        ("What's the goal of the sequence?", "(book call, close deal, nurture)"),
        ("How many emails in the sequence?", "(default: 3-5)"),
        ("What offer are we promoting?", None),
        ("Any specific pain points to address?", None),
    ],
    "landing_page": [
        ("What offer is this page for?", None),
        ("Target audience?", None),
        ("Primary CTA?", "(book call, buy now, sign up)"),
        ("Do you have testimonials or social proof to include?", None),
        ("Any design preferences?", "(minimal, bold, corporate)"),
        ("Existing brand colors or assets?", None),
    ],
}

# Map contract names to question set fallbacks
CONTRACT_TO_QUESTIONS = {
    "lead_gen_email": "email_sequence",
    "ad_script": "ad_campaign",
    "vsl_section": "content_piece",
    "business_audit": "client_onboarding",
    "sourcing_report": "fba_product_eval",
}


def load_contract(task_type: str) -> dict | None:
    """Try to load a contract for the given task type."""
    contract_file = CONTRACTS_DIR / f"{task_type}.yaml"
    if contract_file.exists():
        with open(contract_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return None


def extract_provided_fields(context: str) -> set[str]:
    """Extract field names that appear to be provided in the context string."""
    provided = set()
    context_lower = context.lower()

    # Simple heuristic: look for "field: value" or "field = value" patterns
    field_indicators = {
        "company": ["company", "business", "brand"],
        "contact_name": ["contact", "name", "person"],
        "platform": ["meta", "google", "youtube", "tiktok", "facebook"],
        "industry": ["industry", "vertical", "niche"],
        "budget": ["budget", "$", "spend"],
        "audience": ["audience", "icp", "target"],
        "asin": ["asin", "b0"],
        "offer": ["agency os", "amazon os", "coaching", "offer"],
        "pain_points": ["pain", "problem", "struggle", "challenge"],
        "url": ["http", "www.", ".com", ".org"],
    }

    for field, keywords in field_indicators.items():
        if any(kw in context_lower for kw in keywords):
            provided.add(field)

    return provided


def generate_questions_from_contract(contract: dict, context: str = "") -> list[tuple[str, str | None]]:
    """Generate questions from contract required fields, excluding already-provided ones."""
    provided = extract_provided_fields(context)
    questions = []

    if "input" in contract and "required" in contract["input"]:
        for field_def in contract["input"]["required"]:
            if isinstance(field_def, dict):
                for field_name, field_info in field_def.items():
                    if field_name not in provided:
                        desc = field_info.get("description", "") if isinstance(field_info, dict) else ""
                        questions.append((f"What is the {field_name.replace('_', ' ')}?", f"({desc})" if desc else None))
            elif isinstance(field_def, str) and field_def not in provided:
                questions.append((f"What is the {field_def.replace('_', ' ')}?", None))

    return questions[:7]  # Max 7 questions


def generate_questions(task_type: str, context: str = "") -> list[tuple[str, str | None]]:
    """Generate clarifying questions for a task type."""
    # Try contract first
    contract = load_contract(task_type)
    if contract:
        questions = generate_questions_from_contract(contract, context)
        if questions:
            return questions

    # Fall back to pre-built question sets
    question_key = CONTRACT_TO_QUESTIONS.get(task_type, task_type)
    if question_key in QUESTION_SETS:
        provided = extract_provided_fields(context)
        questions = []
        for q, hint in QUESTION_SETS[question_key]:
            # Simple check: skip if the question topic seems covered
            q_lower = q.lower()
            skip = False
            for field in provided:
                if field in q_lower or q_lower.split("?")[0].split()[-1] in field:
                    skip = True
                    break
            if not skip:
                questions.append((q, hint))
        return questions[:7]

    return [("Could you describe what you need in more detail?", None)]


def format_questions(questions: list[tuple[str, str | None]], task_type: str) -> str:
    """Format questions as a numbered list."""
    lines = [f"Before I start on **{task_type.replace('_', ' ')}**, a few quick questions:\n"]
    for i, (q, hint) in enumerate(questions, 1):
        if hint:
            lines.append(f"{i}. {q} {hint}")
        else:
            lines.append(f"{i}. {q}")
    lines.append(f"\n(Answer all, or say 'use your best judgment' for any you want me to decide)")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate reverse-prompting questions for a task")
    parser.add_argument("--task-type", help="Task type (matches contract name or question set)")
    parser.add_argument("--context", default="", help="Context already provided by user")
    parser.add_argument("--freeform", help="Freeform task description (auto-detects task type)")
    args = parser.parse_args()

    if args.freeform:
        # Auto-detect task type from freeform description
        freeform_lower = args.freeform.lower()
        type_keywords = {
            "email": "lead_gen_email",
            "ad": "ad_campaign",
            "landing page": "landing_page",
            "vsl": "content_piece",
            "audit": "client_onboarding",
            "sourcing": "fba_product_eval",
            "product": "fba_product_eval",
            "content": "content_piece",
            "onboard": "client_onboarding",
        }
        task_type = "client_onboarding"  # default
        for keyword, ttype in type_keywords.items():
            if keyword in freeform_lower:
                task_type = ttype
                break
        context = args.freeform
    else:
        task_type = args.task_type or "client_onboarding"
        context = args.context

    questions = generate_questions(task_type, context)

    if not questions:
        print("No clarifying questions needed — all required fields appear to be provided.")
        return

    print(format_questions(questions, task_type))


if __name__ == "__main__":
    main()
