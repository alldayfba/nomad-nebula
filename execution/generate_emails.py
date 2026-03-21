#!/usr/bin/env python3
"""
Script: generate_emails.py
Purpose: Generate personalized cold outreach emails for each lead using Claude.
         Reads filtered leads CSV, adds email_subject and email_body columns.
Inputs:  --input  (CSV — ideally output from filter_icp.py)
         --output (CSV with email columns, default: .tmp/emails_<ts>.csv)
Outputs: CSV with two new columns: email_subject, email_body
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

_MODEL = "claude-sonnet-4-6"
_PRICING = {"claude-haiku-4-5-20251001": (0.25, 1.25), "claude-sonnet-4-6": (3.0, 15.0), "claude-opus-4-6": (15.0, 75.0)}

def _cost(model: str, inp: int, out: int) -> float:
    p = _PRICING.get(model, (3.0, 15.0))
    return (inp * p[0] + out * p[1]) / 1_000_000

# --- Sender Context (edit this to match your agency voice) ---
# Full context lives in SabboOS/Agency_OS.md — keep this in sync.
SENDER_CONTEXT = """
You are a direct response copywriter writing cold outreach emails on behalf of a growth marketing agency.

About the agency:
- Done-For-You growth operating system for founder-led businesses
- Retainer-based ($5K–$25K/mo)
- Core promise: Install a full-stack growth system in 30 days and run it month-over-month
- Differentiator: Operators embedded in the business — not an account manager + junior team
- Channels: Meta, YouTube, LinkedIn, Google Search

Email style rules:
- Max 120 words in the body
- Written operator-to-operator — direct, no corporate fluff, no buzzwords
- One specific observation about their business (use their category, location, rating, name)
- One clear CTA: book a 20-minute strategy call
- Subject line that reads like a real person sent it — not a marketing email
- No: "I hope this email finds you well", "synergy", "leverage", "reaching out", "circle back"
- Tone: confident, peer-level, brief
"""


def generate_email(client: anthropic.Anthropic, lead: dict, totals: dict) -> dict:
    """Generate subject + body for one lead. Returns {subject, body}."""
    lead_data = {k: v for k, v in lead.items() if k in [
        "business_name", "owner_name", "category", "address",
        "website", "rating", "phone"
    ]}

    prompt = f"""{SENDER_CONTEXT}

Lead data:
{json.dumps(lead_data, indent=2)}

Write a personalized cold outreach email for this specific business.
Use details from their data (category, location, name) to make it feel 1:1.

Return ONLY valid JSON — no markdown, no explanation:
{{
  "subject": "<subject line>",
  "body": "<email body — use \\n for line breaks>"
}}"""

    message = client.messages.create(
        model=_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    totals["input"] += message.usage.input_tokens
    totals["output"] += message.usage.output_tokens

    raw = message.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description="Generate personalized outreach emails using Claude")
    parser.add_argument("--input", required=True, help="Input CSV path (filtered leads)")
    parser.add_argument("--output", default=None, help="Output CSV path (default: .tmp/emails_<ts>.csv)")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    TMP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or str(TMP_DIR / f"emails_{ts}.csv")

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path) as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    print(f"Generating emails for {len(leads)} leads...\n")

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    totals = {"input": 0, "output": 0}

    for i, lead in enumerate(leads):
        name = lead.get("business_name", "Unknown")
        print(f"  [{i+1}/{len(leads)}] {name}", end="", flush=True)

        try:
            email = generate_email(client, lead, totals)
            lead["email_subject"] = email.get("subject", "")
            lead["email_body"] = email.get("body", "")
            print(f" ✓")
        except Exception as e:
            lead["email_subject"] = ""
            lead["email_body"] = f"ERROR: {e}"
            print(f" ✗ ERROR: {e}")

        results.append(lead)

    fieldnames = list(results[0].keys())
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    usd = _cost(_MODEL, totals["input"], totals["output"])
    print(f"\n{'='*60}")
    print(f"Emails generated: {len(results)}")
    print(f"Output: {output_path}")
    print(f"Tokens: {totals['input']:,} in / {totals['output']:,} out  |  Cost: ${usd:.4f}  [{_MODEL}]")

    return output_path


if __name__ == "__main__":
    main()
