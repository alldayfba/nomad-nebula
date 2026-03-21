#!/usr/bin/env python3
"""
Script: generate_ad_scripts.py
Purpose: Generate Meta/YouTube ad scripts targeting the lead's industry/ICP using Claude.
         Produces hook + body + CTA for a direct response video ad.
Inputs:  --input    (CSV — filtered leads or a specific lead)
         --output   (CSV with ad script columns, default: .tmp/ad_scripts_<ts>.csv)
         --platform (meta | youtube, default: meta)
Outputs: CSV with new columns: ad_hook, ad_body, ad_cta, ad_platform
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

AGENCY_CONTEXT = """
You are a direct response ad copywriter for a growth marketing agency.

Agency offer:
- Done-For-You growth operating system for founder-led businesses (7-8 figure revenue)
- Core promise: Install a full-stack growth system in 30 days and run it month-over-month
- Retainer: $5K–$25K/mo
- Differentiator: Operators embedded in the business, not an account manager + junior team
- Channels: Meta, YouTube, LinkedIn, Google Search
"""

PLATFORM_SPECS = {
    "meta": {
        "name": "Meta (Facebook/Instagram)",
        "hook_words": "2-3 seconds, pattern interrupt — must stop the scroll",
        "body_words": "30-60 seconds of spoken content",
        "cta": "Book a free strategy call / Click the link in bio",
        "format": "Hook (1-2 sentences) → Problem agitation (2-3 sentences) → Solution tease (1-2 sentences) → CTA",
        "tone": "Direct, conversational, slightly urgent — like talking to a peer"
    },
    "youtube": {
        "name": "YouTube pre-roll",
        "hook_words": "First 5 seconds before skip — must earn attention",
        "body_words": "60-90 seconds of spoken content",
        "cta": "Click the link below / Visit the website",
        "format": "Hook (compelling question or bold claim) → Credentials drop (fast) → Problem → Solution → Proof → CTA",
        "tone": "Direct, educational, authoritative — earn trust fast"
    }
}


def generate_ad_script(client: anthropic.Anthropic, lead: dict, platform: str, totals: dict) -> dict:
    """Generate an ad script for one lead's industry/category."""
    spec = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["meta"])

    lead_data = {k: v for k, v in lead.items() if k in [
        "business_name", "category", "address", "website"
    ]}

    prompt = f"""{AGENCY_CONTEXT}

Platform: {spec["name"]}
Format: {spec["format"]}
Hook guidance: {spec["hook_words"]}
Body guidance: {spec["body_words"]}
CTA options: {spec["cta"]}
Tone: {spec["tone"]}

Target lead (use their industry/category to make the ad hyper-relevant to their world):
{json.dumps(lead_data, indent=2)}

Write a direct response video ad script targeting business owners in the {lead_data.get("category", "this industry")} space.
The ad should speak directly to the pain of being a founder stuck at a plateau — not growing despite working hard.

Return ONLY valid JSON — no markdown, no explanation:
{{
  "hook": "<hook line — the first thing spoken on camera>",
  "body": "<full script body — use \\n for line breaks between beats>",
  "cta": "<closing call to action>",
  "platform": "{platform}"
}}"""

    message = client.messages.create(
        model=_MODEL,
        max_tokens=800,
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
    parser = argparse.ArgumentParser(description="Generate ad scripts using Claude")
    parser.add_argument("--input", required=True, help="Input CSV path (filtered leads)")
    parser.add_argument("--output", default=None, help="Output CSV path (default: .tmp/ad_scripts_<ts>.csv)")
    parser.add_argument("--platform", choices=["meta", "youtube"], default="meta",
                        help="Ad platform (meta or youtube, default: meta)")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    TMP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or str(TMP_DIR / f"ad_scripts_{ts}.csv")

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path) as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    print(f"Generating {args.platform.upper()} ad scripts for {len(leads)} leads...\n")

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    totals = {"input": 0, "output": 0}

    for i, lead in enumerate(leads):
        name = lead.get("business_name", "Unknown")
        category = lead.get("category", "")
        print(f"  [{i+1}/{len(leads)}] {name} ({category})", end="", flush=True)

        try:
            script = generate_ad_script(client, lead, args.platform, totals)
            lead["ad_hook"] = script.get("hook", "")
            lead["ad_body"] = script.get("body", "")
            lead["ad_cta"] = script.get("cta", "")
            lead["ad_platform"] = script.get("platform", args.platform)
            print(f" ✓")
        except Exception as e:
            lead["ad_hook"] = ""
            lead["ad_body"] = f"ERROR: {e}"
            lead["ad_cta"] = ""
            lead["ad_platform"] = args.platform
            print(f" ✗ ERROR: {e}")

        results.append(lead)

    fieldnames = list(results[0].keys())
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    usd = _cost(_MODEL, totals["input"], totals["output"])
    print(f"\n{'='*60}")
    print(f"Ad scripts generated: {len(results)}")
    print(f"Platform: {args.platform}")
    print(f"Output: {output_path}")
    print(f"Tokens: {totals['input']:,} in / {totals['output']:,} out  |  Cost: ${usd:.4f}  [{_MODEL}]")

    return output_path


if __name__ == "__main__":
    main()
