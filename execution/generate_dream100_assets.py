"""
generate_dream100_assets.py

Step 2 of the Dream 100 pipeline.

Takes prospect research JSON and generates actual deliverables FOR the prospect's business:
- 3 Meta ad hooks (they can run today)
- 1 YouTube pre-roll script
- 3-email welcome/nurture sequence (for their list)
- 5 landing page headline options
- VSL hook + problem-agitation section
- Confirmation page copy (boosts show rates 30-50%)

These are BUILT FOR THE PROSPECT — not your own marketing assets.
The goal: they open the GammaDoc and think "I can implement all of this right now."

Outputs JSON to .tmp/assets_<name>_<ts>.json

Usage:
    python execution/generate_dream100_assets.py \
        --research .tmp/research_Alex_Hormozi_20260220.json \
        --prospect-name "Alex Hormozi"

    # If no research file, provide context manually:
    python execution/generate_dream100_assets.py \
        --prospect-name "Alex Hormozi" \
        --niche "business education" \
        --offer "high-ticket business programs at $10K+" \
        --funnel-type "vsl" \
        --gaps "weak ad hooks, no confirmation page nurture, no email sequence post-optin"
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_PRICING = {"claude-haiku-4-5-20251001": (0.25, 1.25), "claude-sonnet-4-6": (3.0, 15.0), "claude-opus-4-6": (15.0, 75.0)}
_usage: dict[str, dict[str, int]] = {}  # model -> {input, output}

def _track(model: str, resp_usage) -> None:
    if model not in _usage:
        _usage[model] = {"input": 0, "output": 0}
    _usage[model]["input"] += resp_usage.input_tokens
    _usage[model]["output"] += resp_usage.output_tokens

def _print_cost() -> None:
    total_usd = 0.0
    for model, tok in _usage.items():
        p = _PRICING.get(model, (3.0, 15.0))
        usd = (tok["input"] * p[0] + tok["output"] * p[1]) / 1_000_000
        total_usd += usd
        print(f"  {model}: {tok['input']:,} in / {tok['output']:,} out  ${usd:.4f}")
    print(f"  Total cost: ${total_usd:.4f}")

# Your agency context — informs the tone and positioning of assets we build
AGENCY_CONTEXT = """
You are building these assets for a growth marketing operator who specializes in
full-stack marketing systems for founder-led businesses. The assets should feel like
they were built by someone who deeply understands the prospect's business and their customers —
not generic templates. Every piece should be immediately deployable.
"""


def generate_meta_ad_hooks(prospect: dict) -> list[dict]:
    """Generate 3 Meta ad hooks for the prospect's offer."""
    prompt = f"""You are writing Meta (Facebook/Instagram) ad hooks FOR {prospect['name']}'s business — not for us, FOR THEM.

THEIR OFFER: {prospect['offer']}
THEIR NICHE: {prospect['niche']}
THEIR FUNNEL TYPE: {prospect['funnel_type']}
THEIR TARGET CUSTOMER PAIN: {prospect['pain_summary']}

Write 3 distinct Meta ad hooks they can use to drive traffic to their offer. Each hook:
- Must grab attention in the first 2-3 seconds (pattern interrupt)
- Is written as spoken word (for a talking-head or UGC style video)
- Is 1-3 sentences MAX
- Each uses a DIFFERENT formula:
  Hook 1: Bold contrarian claim or myth bust
  Hook 2: "If [condition], then [result]" format
  Hook 3: Direct call-out of their ideal customer's exact situation

Return JSON array with exactly 3 objects:
[
  {{"hook_number": 1, "formula": "contrarian claim", "hook_text": "...", "why_it_works": "1 sentence"}},
  {{"hook_number": 2, "formula": "if-then", "hook_text": "...", "why_it_works": "1 sentence"}},
  {{"hook_number": 3, "formula": "direct callout", "hook_text": "...", "why_it_works": "1 sentence"}}
]

Return ONLY the JSON array. No fences. No commentary."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    _track("claude-sonnet-4-6", resp.usage)
    raw = _clean_json(resp.content[0].text)
    return json.loads(raw)


def generate_youtube_ad(prospect: dict) -> dict:
    """Generate a YouTube pre-roll script for the prospect's offer."""
    prompt = f"""You are writing a YouTube pre-roll ad script FOR {prospect['name']}'s business.

THEIR OFFER: {prospect['offer']}
THEIR NICHE: {prospect['niche']}
THEIR TARGET CUSTOMER: {prospect['pain_summary']}

Write a 60-90 second YouTube pre-roll script (they must hook in the first 5 seconds before viewer can skip).

Structure:
- HOOK (0-5 sec): Bold statement or specific result — must make viewer NOT skip
- CREDENTIALS DROP (5-15 sec): Who is this person / why listen
- PROBLEM (15-35 sec): Describe the viewer's exact situation (pain, frustration, what they've tried)
- SOLUTION (35-55 sec): The mechanism — what makes their approach different
- CTA (55-65 sec): One action — visit this page or click the link below

Tone: Direct, confident, authoritative. No fluff. No "Hi guys" intros.

Return JSON:
{{
  "hook": "exact script for seconds 0-5",
  "credentials": "exact script for seconds 5-15",
  "problem": "exact script for seconds 15-35",
  "solution": "exact script for seconds 35-55",
  "cta": "exact script for seconds 55-65",
  "full_script": "entire script stitched together",
  "estimated_runtime_seconds": 75
}}

Return ONLY the JSON. No fences. No commentary."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    _track("claude-sonnet-4-6", resp.usage)
    raw = _clean_json(resp.content[0].text)
    return json.loads(raw)


def generate_email_sequence(prospect: dict) -> list[dict]:
    """Generate a 3-email welcome/nurture sequence for the prospect's list."""
    prompt = f"""You are writing a 3-email welcome/nurture sequence FOR {prospect['name']}'s email list.

THEIR OFFER: {prospect['offer']}
THEIR NICHE: {prospect['niche']}
THEIR FUNNEL TYPE: {prospect['funnel_type']}
SUBSCRIBER PAIN: {prospect['pain_summary']}

These emails go out AFTER someone opts in to their list or lead magnet.

Email 1 (sent immediately): Welcome + deliver the promise. Short, warm, direct.
Email 2 (sent Day 2): One actionable insight or quick win they can use right now. Builds trust.
Email 3 (sent Day 4): Case study or transformation story from a customer. Soft pitch to their main offer.

Each email:
- Subject line that reads like a real person sent it (no all-caps, no gimmicks)
- 100-150 words MAX in body
- One CTA per email (no multiple links)
- P.S. line that teases the next email or adds a micro-insight

Return JSON array with exactly 3 emails:
[
  {{
    "email_number": 1,
    "send_timing": "immediately",
    "subject": "...",
    "preview_text": "...",
    "body": "...",
    "cta": "what you want them to click or do",
    "ps_line": "..."
  }},
  ...
]

Return ONLY the JSON array. No fences. No commentary."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1800,
        messages=[{"role": "user", "content": prompt}],
    )
    _track("claude-sonnet-4-6", resp.usage)
    raw = _clean_json(resp.content[0].text)
    return json.loads(raw)


def generate_landing_page_headlines(prospect: dict) -> list[dict]:
    """Generate 5 landing page headline options."""
    prompt = f"""You are writing landing page headlines FOR {prospect['name']}'s offer.

THEIR OFFER: {prospect['offer']}
THEIR NICHE: {prospect['niche']}
THEIR TARGET CUSTOMER: {prospect['pain_summary']}
FUNNEL TYPE: {prospect['funnel_type']}

Write 5 headline options (H1 + supporting subheadline) for their landing page.

Each set should:
- Lead with the specific outcome/transformation (not the feature or mechanism)
- Be written at a grade-6 reading level
- Be under 12 words for the H1
- The subheadline (1-2 sentences) adds the "how" and "for whom"
- Each option uses a DIFFERENT angle: result, time frame, social proof, problem, identity

Return JSON array with 5 objects:
[
  {{
    "option": 1,
    "angle": "result-focused",
    "headline": "...",
    "subheadline": "..."
  }},
  ...
]

Return ONLY the JSON array. No fences. No commentary."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )
    _track("claude-sonnet-4-6", resp.usage)
    raw = _clean_json(resp.content[0].text)
    return json.loads(raw)


def generate_vsl_hook(prospect: dict) -> dict:
    """Generate a VSL hook + problem-agitation section."""
    prompt = f"""You are writing the opening section of a VSL (Video Sales Letter) FOR {prospect['name']}'s offer.

THEIR OFFER: {prospect['offer']}
THEIR NICHE: {prospect['niche']}
THEIR TARGET CUSTOMER: {prospect['pain_summary']}

Write:
1. HOOK (0:00-0:30) — Bold claim, provocative question, or specific result. Makes viewer stop and watch.
2. PROBLEM (0:30-1:30) — Describe their exact situation in painful detail. Mirror their inner monologue.
3. AGITATION (1:30-2:30) — Amplify the cost of inaction. What happens if they don't fix this?

Tone: Direct, empathetic, specific. Avoid clichés. Write like a real operator talking to a peer.

Return JSON:
{{
  "hook": {{
    "timestamp": "0:00-0:30",
    "script": "exact spoken script"
  }},
  "problem": {{
    "timestamp": "0:30-1:30",
    "script": "exact spoken script"
  }},
  "agitation": {{
    "timestamp": "1:30-2:30",
    "script": "exact spoken script"
  }},
  "total_word_count": 250
}}

Return ONLY the JSON. No fences. No commentary."""

    resp = client.messages.create(
        model="claude-opus-4-6",  # VSL hook = high-stakes copy → Opus
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    _track("claude-opus-4-6", resp.usage)
    raw = _clean_json(resp.content[0].text)
    return json.loads(raw)


def generate_confirmation_page(prospect: dict) -> dict:
    """Generate confirmation page copy to boost show rates after booking."""
    prompt = f"""You are writing a booking confirmation page for {prospect['name']}'s sales call funnel.

THEIR OFFER: {prospect['offer']}
THEIR NICHE: {prospect['niche']}

Someone just booked a strategy/sales call with them. Write the confirmation page copy that:
1. Confirms the booking (reassures, reduces cancellation anxiety)
2. Builds excitement about the call (what they'll get out of it)
3. Sets expectations (what to prepare, what the call looks like)
4. Adds a micro-commitment (1 action to do before the call — watch a video, fill a form, etc.)
5. Reduces no-shows (urgency without being pushy)

Stat context: Without a good confirmation page, show rates average 36%. With proper nurture, 72-80%.

Return JSON:
{{
  "headline": "confirmation page H1",
  "subheadline": "1-2 sentences under the headline",
  "what_to_expect": ["bullet 1", "bullet 2", "bullet 3"],
  "before_the_call": "1-2 sentences on what they should do/prepare",
  "micro_commitment_cta": "the one action to take now (e.g. watch this 8-min video)",
  "reminder_copy": "2-3 sentences to reduce no-shows / build anticipation",
  "ps_line": "optional P.S. that adds warmth or social proof"
}}

Return ONLY the JSON. No fences. No commentary."""

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    _track("claude-sonnet-4-6", resp.usage)
    raw = _clean_json(resp.content[0].text)
    return json.loads(raw)


def _clean_json(text: str) -> str:
    """Strip markdown code fences if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def build_prospect_context(args: argparse.Namespace) -> dict:
    """Build a prospect context dict from either research file or manual args."""
    if args.research:
        research_path = Path(args.research)
        if not research_path.exists():
            print(f"ERROR: Research file not found: {args.research}")
            sys.exit(1)
        data = json.loads(research_path.read_text())
        analysis = data.get("analysis", {})
        return {
            "name": data.get("prospect_name", args.prospect_name),
            "niche": data.get("niche", ""),
            "offer": data.get("offer", ""),
            "funnel_type": analysis.get("funnel_type", "unknown"),
            "pain_summary": analysis.get("prospect_pain_summary", ""),
            "gaps": analysis.get("marketing_gaps", []),
        }
    else:
        # Manual mode — require args
        required = ["niche", "offer"]
        for r in required:
            if not getattr(args, r.replace("-", "_"), None):
                print(f"ERROR: --{r} required when not using --research")
                sys.exit(1)
        return {
            "name": args.prospect_name,
            "niche": args.niche,
            "offer": args.offer,
            "funnel_type": args.funnel_type or "unknown",
            "pain_summary": args.gaps or "Not specified — inferred from niche",
            "gaps": [],
        }


def save_output(assets: dict, name: str) -> str:
    """Save assets JSON to .tmp/ and return the path."""
    tmp = Path(".tmp")
    tmp.mkdir(exist_ok=True)
    safe_name = re.sub(r"[^\w]", "_", name)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = tmp / f"assets_{safe_name}_{ts}.json"
    path.write_text(json.dumps(assets, indent=2))
    return str(path)


def main():
    parser = argparse.ArgumentParser(description="Generate Dream 100 deliverables for a prospect")
    parser.add_argument("--research", help="Path to research JSON from research_prospect.py")
    parser.add_argument("--prospect-name", required=True, help="Prospect name (used in output filename)")
    # Manual overrides (used when no research file)
    parser.add_argument("--niche", help="Prospect niche/industry")
    parser.add_argument("--offer", help="What they sell")
    parser.add_argument("--funnel-type", help="Their funnel type (vsl, webinar, application, etc.)")
    parser.add_argument("--gaps", help="Known marketing gaps (comma-separated or plain text)")
    args = parser.parse_args()

    print(f"\n[dream100] Generating assets for: {args.prospect_name}\n")

    prospect = build_prospect_context(args)

    assets = {
        "prospect_name": prospect["name"],
        "generated_at": datetime.now().isoformat(),
    }

    steps = [
        ("Meta ad hooks (3x)", "meta_ad_hooks", generate_meta_ad_hooks),
        ("YouTube pre-roll script", "youtube_ad", generate_youtube_ad),
        ("Email sequence (3 emails)", "email_sequence", generate_email_sequence),
        ("Landing page headlines (5x)", "landing_page_headlines", generate_landing_page_headlines),
        ("VSL hook + problem section", "vsl_hook", generate_vsl_hook),
        ("Confirmation page copy", "confirmation_page", generate_confirmation_page),
    ]

    for label, key, fn in steps:
        print(f"  Generating {label}...")
        try:
            assets[key] = fn(prospect)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  WARNING: {label} failed — {e}. Skipping.")
            assets[key] = {"error": str(e)}

    output_path = save_output(assets, args.prospect_name)

    print(f"\n✓ Assets generated: {output_path}")
    print(f"\nDeliverables built:")
    for label, key, _ in steps:
        status = "✓" if "error" not in assets.get(key, {}) else "✗ (failed)"
        print(f"  {status} {label}")
    print(f"\nAPI cost breakdown:")
    _print_cost()
    print(f"\nNext: python execution/assemble_gammadoc.py --assets {output_path}" +
          (f" --research {args.research}" if args.research else "") +
          f" --prospect-name \"{args.prospect_name}\"")


if __name__ == "__main__":
    main()
