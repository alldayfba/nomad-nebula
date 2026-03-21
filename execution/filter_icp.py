#!/usr/bin/env python3
"""
Script: filter_icp.py
Purpose: Score and filter scraped leads against your ICP using Claude.
         Adds icp_score, icp_include, and icp_reason columns to the CSV.
Inputs:  --input  (CSV from run_scraper.py)
         --output (filtered CSV, default: .tmp/filtered_leads.csv)
         --threshold (min score to include, default: 6)
Outputs: Filtered CSV in .tmp/ with ICP scoring columns appended
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
TMP_DIR = BASE_DIR / ".tmp"

# Model routing — classification is a Haiku task
_MODEL = "claude-haiku-4-5-20251001"
_PRICING = {"claude-haiku-4-5-20251001": (0.25, 1.25), "claude-sonnet-4-6": (3.0, 15.0), "claude-opus-4-6": (15.0, 75.0)}

def _cost(model: str, inp: int, out: int) -> float:
    p = _PRICING.get(model, (3.0, 15.0))
    return (inp * p[0] + out * p[1]) / 1_000_000

# --- ICP Definition (edit this to match your target client) ---
ICP_DEFINITION = """
You are a B2B lead qualification specialist for a growth marketing and advertising agency.

Ideal Customer Profile (ICP):
- Business type: Founder-led service businesses, e-commerce brands, coaching/consulting firms, professional services
- Revenue signals: Established business (has website, real phone, physical address, 4+ Google rating)
- Size: Small-to-mid market — not a solo freelancer, not a Fortune 500
- Pain point: Revenue plateau — growing but stuck, likely underinvesting in marketing or lacking a growth system
- Good signals: Has a website, has reviews/rating, professional category, real email address
- Bad signals: Government entity, nonprofit, residential address, very generic category (e.g. "Store"), no website, no phone

Score 1-10. Include if score >= threshold (default 6).
"""


def score_lead(client: anthropic.Anthropic, lead: dict, totals: dict) -> dict:
    """Score a single lead against the ICP. Returns {score, include, reason}."""
    lead_data = {k: v for k, v in lead.items() if k in [
        "business_name", "owner_name", "category", "phone",
        "email", "website", "address", "rating"
    ]}

    prompt = f"""{ICP_DEFINITION}

Lead data:
{json.dumps(lead_data, indent=2)}

Return ONLY valid JSON — no markdown, no explanation, just the JSON object:
{{
  "score": <integer 1-10>,
  "include": <true or false>,
  "reason": "<one sentence>"
}}"""

    message = client.messages.create(
        model=_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    totals["input"] += message.usage.input_tokens
    totals["output"] += message.usage.output_tokens

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description="Filter leads by ICP using Claude")
    parser.add_argument("--input", required=True, help="Input CSV path (from run_scraper.py)")
    parser.add_argument("--output", default=None, help="Output CSV path (default: .tmp/filtered_leads_<ts>.csv)")
    parser.add_argument("--threshold", type=int, default=6, help="Minimum ICP score to include (1-10, default: 6)")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    TMP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or str(TMP_DIR / f"filtered_leads_{ts}.csv")

    # Load leads
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path) as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    print(f"Loaded {len(leads)} leads from {input_path.name}")
    print(f"Scoring against ICP (threshold: {args.threshold}/10)...\n")

    client = anthropic.Anthropic(api_key=api_key)
    passed = []
    failed = []
    totals = {"input": 0, "output": 0}

    for i, lead in enumerate(leads):
        name = lead.get("business_name", "Unknown")
        print(f"  [{i+1}/{len(leads)}] {name}", end="", flush=True)

        try:
            result = score_lead(client, lead, totals)
            score = result.get("score", 0)
            include = result.get("include", False) and score >= args.threshold
            reason = result.get("reason", "")

            lead["icp_score"] = score
            lead["icp_include"] = include
            lead["icp_reason"] = reason

            if include:
                passed.append(lead)
                print(f" ✓  {score}/10 — {reason}")
            else:
                failed.append(lead)
                print(f" ✗  {score}/10 — {reason}")

        except Exception as e:
            lead["icp_score"] = 0
            lead["icp_include"] = False
            lead["icp_reason"] = f"Scoring error: {e}"
            failed.append(lead)
            print(f" ✗  ERROR: {e}")

    # Write filtered output
    print(f"\n{'='*60}")
    print(f"Passed: {len(passed)}/{len(leads)} leads")

    if passed:
        fieldnames = list(passed[0].keys())
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(passed)
        print(f"Output: {output_path}")
    else:
        print("No leads passed the ICP filter. Try lowering --threshold.")

    usd = _cost(_MODEL, totals["input"], totals["output"])
    print(f"Tokens: {totals['input']:,} in / {totals['output']:,} out  |  Cost: ${usd:.4f}  [{_MODEL}]")

    return output_path if passed else None


if __name__ == "__main__":
    main()
