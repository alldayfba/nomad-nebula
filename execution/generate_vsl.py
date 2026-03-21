#!/usr/bin/env python3
"""
Script: generate_vsl.py
Purpose: Generate a full VSL (Video Sales Letter) script targeted to a lead's industry.
         Produces a complete, structured VSL broken into beats: hook, problem, solution, proof, offer, CTA.
Inputs:  --input   (CSV — single lead or filtered leads list)
         --output  (CSV with VSL columns, default: .tmp/vsl_<ts>.csv)
         --single  (business_name to generate VSL for just one lead from the CSV)
Outputs: CSV with vsl_script column; also writes full script to .tmp/vsl_<business>_<ts>.txt for readability
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
TMP_DIR = BASE_DIR / ".tmp"

# VSL = high-stakes copy → Opus per cost SOP
_MODEL = "claude-opus-4-6"
_PRICING = {"claude-haiku-4-5-20251001": (0.25, 1.25), "claude-sonnet-4-6": (3.0, 15.0), "claude-opus-4-6": (15.0, 75.0)}

def _cost(model: str, inp: int, out: int) -> float:
    p = _PRICING.get(model, (3.0, 15.0))
    return (inp * p[0] + out * p[1]) / 1_000_000

# --- VSL Framework ---
# Based on proven direct response structure: Hook → Problem → Agitation → Solution → Proof → Offer → CTA
VSL_FRAMEWORK = """
You are a master VSL (Video Sales Letter) copywriter specializing in direct response for B2B service businesses.

VSL structure you must follow (label each section clearly):
1. HOOK (0:00-0:30) — Bold claim or provocative question that stops the right person. Immediately qualify the viewer.
2. PROBLEM (0:30-1:30) — Describe their exact situation in painful detail. Make them feel seen.
3. AGITATION (1:30-2:30) — Amplify the cost of inaction. What happens if they keep doing what they're doing?
4. SOLUTION INTRO (2:30-3:30) — Introduce the mechanism. Not the product yet — the approach/philosophy.
5. CREDIBILITY (3:30-4:30) — Who you are, why you can solve this, proof without being braggy.
6. OFFER REVEAL (4:30-6:00) — What they get, how it works, what's included. Make it concrete.
7. PROOF/RESULTS (6:00-7:00) — Outcomes other clients got. Specific numbers > vague claims.
8. OBJECTION HANDLING (7:00-8:00) — Address the top 2-3 objections before they're asked.
9. CTA (8:00-8:30) — One action, clear, with urgency. Tell them exactly what to do.

Agency context:
- Done-For-You growth operating system for founder-led businesses
- Retainer: $5K–$25K/mo
- Promise: Install full-stack growth system in 30 days, run it month-over-month
- Differentiator: Operators embedded in the business — you're not hiring an agency, you're getting an operator

Writing rules:
- Conversational, spoken word — no corporate jargon
- Specific > vague at every turn
- Each section transitions naturally to the next
- Target audience: founder-led businesses 7-8 figures, stuck at a plateau
"""


def generate_vsl(client: anthropic.Anthropic, lead: dict, totals: dict) -> str:
    """Generate a full VSL script for one lead's industry. Returns the full script as a string."""
    lead_data = {k: v for k, v in lead.items() if k in [
        "business_name", "category", "address", "website", "rating"
    ]}

    category = lead_data.get("category", "business")

    prompt = f"""{VSL_FRAMEWORK}

Target lead's industry: {category}
Lead context: {json.dumps(lead_data, indent=2)}

Write a complete VSL script tailored to founders in the {category} space.
The script should speak directly to the pain of a {category} owner who's growing but feels stuck —
doing everything right but not breaking through.

Label each section clearly (e.g., "## HOOK", "## PROBLEM", etc.)
Write it as spoken word — exactly what someone would say on camera.
Target total length: 8-10 minutes of spoken content (approximately 1,200-1,500 words).

Return the full VSL script as plain text (no JSON needed for this one)."""

    message = client.messages.create(
        model=_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    totals["input"] += message.usage.input_tokens
    totals["output"] += message.usage.output_tokens

    return message.content[0].text.strip()


def main():
    parser = argparse.ArgumentParser(description="Generate VSL scripts using Claude")
    parser.add_argument("--input", required=True, help="Input CSV path (filtered leads)")
    parser.add_argument("--output", default=None, help="Output CSV path (default: .tmp/vsl_<ts>.csv)")
    parser.add_argument("--single", default=None,
                        help="Generate VSL for one business by name (partial match). Skips others.")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    TMP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or str(TMP_DIR / f"vsl_{ts}.csv")

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path) as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    # Filter to single lead if requested
    if args.single:
        leads = [l for l in leads if args.single.lower() in l.get("business_name", "").lower()]
        if not leads:
            print(f"ERROR: No lead found matching '{args.single}'")
            sys.exit(1)
        print(f"Generating VSL for: {leads[0]['business_name']}")
    else:
        print(f"Generating VSLs for {len(leads)} leads...")
        print("Note: VSL generation is token-intensive. Consider using --single for targeted use.\n")

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    totals = {"input": 0, "output": 0}

    for i, lead in enumerate(leads):
        name = lead.get("business_name", "Unknown")
        category = lead.get("category", "")
        print(f"  [{i+1}/{len(leads)}] {name} ({category})...", flush=True)

        try:
            script = generate_vsl(client, lead, totals)
            lead["vsl_script"] = script

            # Also write to readable .txt file
            safe_name = str(re.sub(r"[^a-z0-9]+", "_", name.lower()))[0:40]
            txt_path = TMP_DIR / f"vsl_{safe_name}_{ts}.txt"
            with open(txt_path, "w") as f:
                f.write(f"VSL Script: {name}\n")
                f.write(f"Industry: {category}\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write("=" * 60 + "\n\n")
                f.write(script)
            print(f"  ✓ Script saved to {txt_path.name}")

        except Exception as e:
            lead["vsl_script"] = f"ERROR: {e}"
            print(f"  ✗ ERROR: {e}")

        results.append(lead)

    fieldnames = list(results[0].keys())
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    usd = _cost(_MODEL, totals["input"], totals["output"])
    print(f"\n{'='*60}")
    print(f"VSLs generated: {len(results)}")
    print(f"Output CSV: {output_path}")
    print(f"Full scripts: {TMP_DIR}/vsl_*.txt")
    print(f"Tokens: {totals['input']:,} in / {totals['output']:,} out  |  Cost: ${usd:.4f}  [{_MODEL}]")

    return output_path


if __name__ == "__main__":
    main()
