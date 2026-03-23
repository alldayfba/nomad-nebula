#!/usr/bin/env python3
"""
Analyze individual sales call transcripts using Claude API.
Extracts structured JSON per call: NEPQ stages, objections, ICP data, tonality, etc.

Usage:
    python execution/analyze_sales_call.py                    # Analyze all unprocessed calls
    python execution/analyze_sales_call.py --batch-size 5     # Custom batch size
    python execution/analyze_sales_call.py --call 42          # Analyze single call
    python execution/analyze_sales_call.py --dry-run          # Show what would be processed

Output:
    .tmp/sales-audit/analysis/call_NNN.json per call
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not found. Run: pip install anthropic")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CALLS_DIR = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sales-audit", "calls")
ANALYSIS_DIR = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sales-audit", "analysis")
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "..", ".tmp", "sales-audit", "manifest.json")

# Model for analysis (Sonnet for cost efficiency on structured extraction)
MODEL = "claude-sonnet-4-6-20250514"

SYSTEM_PROMPT = """You are a senior sales call analyst with deep expertise in NEPQ (Neuro-Emotional Persuasion Questions), Hormozi's closing frameworks, Johnny Mau's Pre-Frame Psychology, and high-ticket coaching sales.

You are analyzing sales calls for an Amazon FBA coaching program called "AllDay FBA" / "24/7 Profits" run by Sabbo (AllDay FBA). The program costs $5,000-$5,997 (one-time) or $997/mo payment plans. Closers are Sabbo and Rocky Yadav.

## NEPQ 9 STAGES (Grade each A-F)
1. **Connecting** (0-3 min): Build rapport, set agenda, establish authority
2. **Situation** (3-10 min): Current job, income, Amazon experience, capital available
3. **Problem Awareness** (10-18 min): What's not working, how long stuck, what they've tried
4. **Pre-Frame** (18-22 min): Revealing question ("What have you done to try to fix this?"), limiting belief extraction, identity reframe
5. **Solution Awareness** (22-30 min): Present the program customized to THEIR situation
6. **Consequence** (30-35 min): What happens if nothing changes? Future-pace the pain.
7. **Commitment** (35-40 min): Trial closes, check buying temperature
8. **Transition to Pitch** (40-45 min): Price reveal, anchor and discount
9. **Close** (45-60 min): Ask for the sale, handle objections, collect payment

## 5 TONES
- **Curious**: Used during discovery. "Tell me more about that..."
- **Confused**: "Help me understand..." (forces them to clarify their own objection)
- **Concerned**: "I'm genuinely worried that..." (during consequence)
- **Challenging**: "Is that really true?" (during objection handling)
- **Playful**: Light humor to build rapport and reduce tension

## OBJECTION TYPES
- money: "It's too expensive" / "I don't have $5K"
- think_about_it: "Let me think about it" / "Give me a day"
- spouse: "I need to talk to my wife/partner"
- fear: "What if it doesn't work?" / "I've been burned before"
- time: "I don't have time right now"
- youtube_free: "I can learn this on YouTube for free"
- not_ready: "I'm not ready yet" / "Maybe later"
- capital: "If I pay you, I won't have money for inventory"
- tony_competitor: "I know someone else who can help me cheaper"
- other: Any other objection

## OUTCOME TYPES
- closed: Prospect paid or committed to pay
- verbal_yes_pending: Said yes but payment not collected on call
- follow_up: Genuine scheduling of next call with specific date
- lost_money: Lost due to money/price objection
- lost_belief: Lost due to not believing it will work
- lost_think: Lost due to "think about it" / delayed decision
- lost_spouse: Lost due to needing partner approval
- lost_dq: Disqualified (no capital, wrong fit, not coachable)
- no_show: Did not show up (very short call)
- coaching_call: This was a coaching/support call, not a sales call

## ICP TIERS
- tier_a: Beginner, $5K-$20K capital, motivated, no Amazon experience
- tier_b: Existing seller, plateaued, looking to scale
- tier_c: Investor/passive, just wants to put money in
- not_icp: Wrong fit (no capital, no motivation, wrong expectations)

For each call, output a JSON object with the exact structure shown. Be thorough but concise in notes. Use verbatim quotes where possible."""

USER_PROMPT_TEMPLATE = """Analyze the following sales call transcript and return a JSON object.

IMPORTANT: Return ONLY valid JSON. No markdown, no code blocks, no explanation text. Just the JSON object.

Call metadata:
- Call ID: {call_id}
- Prospect: {prospect_name}
- Date: {date}
- Duration: {duration_min} minutes
- Closer: {closer}

TRANSCRIPT:
{transcript}

---

Return this exact JSON structure (fill in all fields):
{{
  "call_id": {call_id},
  "prospect_name": "{prospect_name}",
  "date": "{date}",
  "duration_min": {duration_min},
  "closer": "{closer}",
  "outcome": "<one of: closed, verbal_yes_pending, follow_up, lost_money, lost_belief, lost_think, lost_spouse, lost_dq, no_show, coaching_call>",
  "revenue": <number or 0 if not closed>,
  "payment_type": "<pif, payment_plan, deposit, or none>",

  "icp": {{
    "current_job": "<their job/situation>",
    "amazon_experience": "<none, beginner, intermediate, experienced>",
    "capital_available": "<dollar amount or range mentioned, or unknown>",
    "motivation": "<primary reason for wanting to do Amazon>",
    "age_bracket": "<teen, young_adult, adult, middle_age, or unknown>",
    "tier": "<tier_a, tier_b, tier_c, or not_icp>",
    "content_that_brought_them": "<how they found Sabbo - IG, YouTube, TikTok, referral, etc>",
    "specific_content_named": ["<any specific videos or posts they mentioned>"],
    "stated_problems": ["<list their top problems/struggles>"],
    "stated_goals": "<what they said they want to achieve>"
  }},

  "nepq_stages": {{
    "1_connecting": {{"executed": <true/false>, "quality": "<A-F>", "notes": "<1-2 sentences>"}},
    "2_situation": {{"executed": <true/false>, "quality": "<A-F>", "notes": "<1-2 sentences>"}},
    "3_problem_awareness": {{"executed": <true/false>, "quality": "<A-F>", "notes": "<1-2 sentences>"}},
    "4_preframe": {{"executed": <true/false>, "quality": "<A-F>", "notes": "<1-2 sentences>"}},
    "5_solution_awareness": {{"executed": <true/false>, "quality": "<A-F>", "notes": "<1-2 sentences>"}},
    "6_consequence": {{"executed": <true/false>, "quality": "<A-F>", "notes": "<1-2 sentences>"}},
    "7_commitment": {{"executed": <true/false>, "quality": "<A-F>", "notes": "<1-2 sentences>"}},
    "8_transition": {{"executed": <true/false>, "quality": "<A-F>", "notes": "<1-2 sentences>"}},
    "9_close": {{"executed": <true/false>, "quality": "<A-F>", "notes": "<1-2 sentences>"}}
  }},

  "objections": [
    {{
      "type": "<objection type from list above>",
      "verbatim_quote": "<exact words from prospect, max 100 chars>",
      "rebuttal_used": "<summary of closer's response, max 100 chars>",
      "rebuttal_quality": "<A-F>",
      "resolved": <true/false>
    }}
  ],

  "tonality": {{
    "dominant_tone": "<curious, confused, concerned, challenging, playful, aggressive, passive>",
    "energy_level": "<high, medium, low>",
    "pre_frame_used": <true/false>,
    "revealing_question_used": <true/false>,
    "future_pacing_used": <true/false>,
    "consequence_framing_used": <true/false>
  }},

  "time_allocation": {{
    "rapport_min": <estimated minutes>,
    "discovery_min": <estimated minutes>,
    "pitch_min": <estimated minutes>,
    "close_min": <estimated minutes>,
    "objection_handling_min": <estimated minutes>
  }},

  "notable_quotes": {{
    "best_closer_moment": "<verbatim quote of strongest moment by closer, max 150 chars>",
    "worst_closer_moment": "<verbatim quote of biggest miss by closer, max 150 chars>",
    "prospect_buying_signal": "<verbatim quote showing interest, max 150 chars>",
    "prospect_resistance_signal": "<verbatim quote showing hesitation, max 150 chars>"
  }},

  "overall_grade": "<A, B, C, D, or F>",
  "biggest_improvement": "<one specific thing that would have changed this call's outcome, max 200 chars>",
  "call_summary": "<2-3 sentence summary of what happened on this call>"
}}"""


def load_manifest():
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)


def load_call_transcript(filename):
    filepath = os.path.join(CALLS_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    # Skip the header metadata (everything before the --- separator)
    if "\n---\n" in content:
        content = content.split("\n---\n", 1)[1].strip()
    return content


def analyze_call(client, call_meta, transcript):
    """Analyze a single call via the Anthropic API."""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        call_id=call_meta["call_id"],
        prospect_name=call_meta["prospect_name"],
        date=call_meta["date"],
        duration_min=call_meta["duration_min"],
        closer=call_meta["closer"],
        transcript=transcript,
    )

    # Truncate very long transcripts to ~150K chars to stay within context
    if len(user_prompt) > 150000:
        # Keep first 70K and last 70K chars of transcript
        mid = len(transcript) // 2
        half = 70000
        truncated = transcript[:half] + "\n\n[... MIDDLE SECTION TRUNCATED FOR LENGTH ...]\n\n" + transcript[-half:]
        user_prompt = USER_PROMPT_TEMPLATE.format(
            call_id=call_meta["call_id"],
            prospect_name=call_meta["prospect_name"],
            date=call_meta["date"],
            duration_min=call_meta["duration_min"],
            closer=call_meta["closer"],
            transcript=truncated,
        )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()

    # Try to extract JSON from the response
    # Sometimes the model wraps it in ```json ... ```
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```", 2)[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        # Try to find JSON object in the text
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(raw_text[start:end])
            except json.JSONDecodeError:
                print(f"    ERROR: Could not parse JSON for call {call_meta['call_id']}")
                result = {"error": str(e), "raw_response": raw_text[:500]}
        else:
            print(f"    ERROR: No JSON found in response for call {call_meta['call_id']}")
            result = {"error": str(e), "raw_response": raw_text[:500]}

    # Add usage stats
    result["_api_usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": MODEL,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Analyze sales call transcripts")
    parser.add_argument("--batch-size", type=int, default=1, help="Calls per batch (sequential)")
    parser.add_argument("--call", type=int, help="Analyze a single call by ID")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    parser.add_argument("--force", action="store_true", help="Re-analyze even if JSON exists")
    args = parser.parse_args()

    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    manifest = load_manifest()

    # Determine which calls to process
    calls_to_process = []
    for call in manifest["calls"]:
        call_id = call["call_id"]
        output_path = os.path.join(ANALYSIS_DIR, f"call_{call_id:03d}.json")

        if args.call and call_id != args.call:
            continue

        if os.path.exists(output_path) and not args.force:
            continue

        calls_to_process.append(call)

    if args.dry_run:
        print(f"Would process {len(calls_to_process)} calls:")
        for c in calls_to_process:
            print(f"  #{c['call_id']:3d} | {c['closer']:6s} | {c['duration_min']:3d}m | {c['prospect_name']}")
        return

    if not calls_to_process:
        print("All calls already analyzed. Use --force to re-analyze.")
        return

    print(f"Analyzing {len(calls_to_process)} calls...")
    # Try secondary API key if primary is out of credits
    api_key = os.environ.get("ANTHROPIC_API_KEY2") or os.environ.get("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    total_input = 0
    total_output = 0
    errors = 0
    start_time = time.time()

    for i, call in enumerate(calls_to_process):
        call_id = call["call_id"]
        output_path = os.path.join(ANALYSIS_DIR, f"call_{call_id:03d}.json")

        print(f"  [{i+1}/{len(calls_to_process)}] Call #{call_id}: {call['prospect_name']} ({call['duration_min']}m, {call['closer']})")

        try:
            transcript = load_call_transcript(call["filename"])
            result = analyze_call(client, call, transcript)

            # Save result
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            usage = result.get("_api_usage", {})
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            total_input += inp
            total_output += out

            outcome = result.get("outcome", "?")
            grade = result.get("overall_grade", "?")
            print(f"    → {outcome} | Grade: {grade} | Tokens: {inp:,} in / {out:,} out")

            if "error" in result:
                errors += 1
                print(f"    ⚠ Parse error: {result['error']}")

        except Exception as e:
            errors += 1
            print(f"    ERROR: {e}")
            # Save error file so we can retry
            with open(output_path, "w") as f:
                json.dump({"error": str(e), "call_id": call_id}, f)

        # Brief pause between calls to avoid rate limits
        if i < len(calls_to_process) - 1:
            time.sleep(0.5)

    elapsed = time.time() - start_time
    cost_input = total_input / 1_000_000 * 3.0  # Sonnet input: $3/M
    cost_output = total_output / 1_000_000 * 15.0  # Sonnet output: $15/M
    total_cost = cost_input + cost_output

    print(f"\n{'='*60}")
    print(f"DONE: {len(calls_to_process)} calls analyzed in {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"Tokens: {total_input:,} input + {total_output:,} output")
    print(f"Estimated cost: ${cost_input:.2f} input + ${cost_output:.2f} output = ${total_cost:.2f}")
    print(f"Errors: {errors}")
    print(f"Results: {ANALYSIS_DIR}")


if __name__ == "__main__":
    main()
