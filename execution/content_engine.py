#!/usr/bin/env python3
"""
Script: content_engine.py
Purpose: Generate platform-native content from topics + ICP context.
         Supports Instagram carousel, LinkedIn post, Twitter thread,
         YouTube outline, TikTok/short-form script.
         Also: content calendar generation, long-form repurposing, idea generation.
Inputs:  CLI subcommands
Outputs: Platform-specific content files in .tmp/content/

CLI:
    python execution/content_engine.py generate --topic "why agencies need systems" --platforms instagram,linkedin
    python execution/content_engine.py calendar --weeks 4 --frequency 3 --business agency
    python execution/content_engine.py repurpose --input .tmp/vsl_script.md --platforms short-form,instagram
    python execution/content_engine.py ideas --business agency --count 10
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv

PROJECT_ROOT = Path(os.environ.get("NOMAD_NEBULA_ROOT",
                                    "/Users/Shared/antigravity/projects/nomad-nebula"))
load_dotenv(PROJECT_ROOT / ".env")

TMP_DIR = PROJECT_ROOT / ".tmp" / "content"
_MODEL = "claude-sonnet-4-6"
_PRICING = {"claude-sonnet-4-6": (3.0, 15.0)}

def _cost(model, inp, out):
    p = _PRICING.get(model, (3.0, 15.0))
    return (inp * p[0] + out * p[1]) / 1_000_000

# ── Platform Specs ───────────────────────────────────────────────────────────

PLATFORMS = {
    "instagram": {
        "format": "carousel",
        "description": "Instagram carousel post (5-10 slides)",
        "rules": "Slide 1 = hook headline. Slides 2-9 = one idea per slide, max 30 words each. Last slide = CTA. Use line breaks for readability. Caption: 150-200 words with relevant hashtags.",
    },
    "linkedin": {
        "format": "post",
        "description": "LinkedIn text post",
        "rules": "Hook in first line (pattern interrupt). 200-300 words. Short paragraphs (1-2 sentences). Use line breaks liberally. End with a question or CTA. No hashtags in body, 3-5 hashtags at very end.",
    },
    "twitter": {
        "format": "thread",
        "description": "Twitter/X thread (5-8 tweets)",
        "rules": "Tweet 1 = hook (max 280 chars). Tweets 2-7 = one point per tweet (max 280 chars each). Last tweet = CTA + retweet ask. Number each tweet (1/, 2/, etc).",
    },
    "youtube": {
        "format": "script_outline",
        "description": "YouTube video script outline (8-12 min)",
        "rules": "Hook (30 sec), Intro (30 sec), 3-5 main points with talking points, CTA (30 sec), Outro. Include B-roll suggestions. Target 1500-2000 words for 10 min video.",
    },
    "tiktok": {
        "format": "script",
        "description": "TikTok/Reel script (30-60 sec)",
        "rules": "Hook in first 3 seconds (pattern interrupt). One single idea. Conversational tone. End with CTA or cliff-hanger. Max 150 words.",
    },
    "short-form": {
        "format": "reel_script",
        "description": "Short-form video script (30-90 sec)",
        "rules": "Hook (3 sec), Setup (10 sec), Value (30-60 sec), CTA (5 sec). Conversational, direct-to-camera feel. One takeaway per video.",
    },
}

# ── Voice Context Loading ────────────────────────────────────────────────────

def load_voice_context(business="agency"):
    """Load business OS and ICP context for voice matching."""
    if business == "agency":
        os_path = PROJECT_ROOT / "SabboOS" / "Agency_OS.md"
    else:
        os_path = PROJECT_ROOT / "SabboOS" / "Amazon_OS.md"

    context = ""
    if os_path.exists():
        content = os_path.read_text()
        # Extract ICP and positioning sections (first 2000 chars)
        context = content[:2000]

    # Also load content bot skills for style rules
    skills_path = PROJECT_ROOT / "bots" / "content" / "skills.md"
    if skills_path.exists():
        context += "\n\nContent bot style rules:\n" + skills_path.read_text()[:1000]

    return context


def get_icp_pain_points(business="agency"):
    """Extract ICP pain points from business OS."""
    if business == "agency":
        os_path = PROJECT_ROOT / "SabboOS" / "Agency_OS.md"
    else:
        os_path = PROJECT_ROOT / "SabboOS" / "Amazon_OS.md"

    if not os_path.exists():
        return []

    content = os_path.read_text()
    # Simple extraction: find bullet points after "pain" or "problem" or "challenge" keywords
    pain_points = []
    lines = content.split("\n")
    in_section = False
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in ["pain", "problem", "challenge", "frustrat", "struggle"]):
            in_section = True
        elif in_section and line.strip().startswith(("-", "*", "•")):
            pain_points.append(line.strip().lstrip("-*• "))
        elif in_section and line.strip() and not line.strip().startswith(("-", "*", "•")):
            in_section = False

    return pain_points[:15]


# ── Content Generation ───────────────────────────────────────────────────────

def generate_content(topic, platforms, business="agency", angle=None):
    """Generate content variants for each platform."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    voice_context = load_voice_context(business)

    results = {}
    total_cost = 0
    today = datetime.utcnow().strftime("%Y-%m-%d")

    for platform in platforms:
        spec = PLATFORMS.get(platform)
        if not spec:
            print(f"[content_engine] Unknown platform '{platform}', skipping.", file=sys.stderr)
            continue

        angle_text = f"\nAngle/hook: {angle}" if angle else ""

        prompt = f"""Create a {spec['description']} about: {topic}{angle_text}

Business context:
{voice_context[:1500]}

Platform rules:
{spec['rules']}

Write as the business owner — confident, experienced, direct. No corporate speak.
The audience is {('7-8 figure founders who need growth systems' if business == 'agency' else 'people interested in starting an Amazon FBA business')}.

Output the complete ready-to-post content. No meta-commentary."""

        response = client.messages.create(
            model=_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        content_text = response.content[0].text
        cost = _cost(_MODEL, response.usage.input_tokens, response.usage.output_tokens)
        total_cost += cost

        # Save to file
        slug = re.sub(r'[^a-z0-9]+', '_', topic.lower())[:40]
        filename = f"{today}_{platform}_{slug}.md"
        filepath = TMP_DIR / filename
        filepath.write_text(f"# {platform.title()} — {topic}\n\n{content_text}\n")

        results[platform] = {
            "file": str(filepath),
            "format": spec["format"],
            "word_count": len(content_text.split()),
            "cost": round(cost, 4),
        }

        print(f"[content_engine] {platform}: {len(content_text.split())} words → {filepath.name}")

    print(f"[content_engine] Total cost: ${total_cost:.4f}")
    return results


def generate_calendar(weeks, frequency, business="agency", topics=None):
    """Generate a content calendar."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    voice_context = load_voice_context(business)
    pain_points = get_icp_pain_points(business)

    topics_context = ""
    if topics:
        topics_context = f"\nPre-selected topics to include: {', '.join(topics)}"
    if pain_points:
        topics_context += f"\nICP pain points to address: {', '.join(pain_points[:8])}"

    prompt = f"""Create a {weeks}-week content calendar posting {frequency}x per week.

Business context:
{voice_context[:1500]}
{topics_context}

For each post, provide:
- Day and date (starting from tomorrow)
- Platform (rotate between: Instagram, LinkedIn, Twitter)
- Topic/headline
- Content angle (educational, story, controversial take, case study, how-to)
- Hook (first line)
- Format (carousel, text post, thread, reel)

Output as JSON array:
[{{"week": 1, "day": "Monday", "date": "YYYY-MM-DD", "platform": "instagram", "topic": "...", "angle": "...", "hook": "...", "format": "carousel"}}]

Make it strategic: alternate between value posts, proof posts, and engagement posts. No two consecutive posts should have the same angle."""

    response = client.messages.create(
        model=_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    cost = _cost(_MODEL, response.usage.input_tokens, response.usage.output_tokens)

    # Extract JSON from response
    try:
        # Handle markdown code blocks
        if "```" in text:
            json_str = text.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
            calendar = json.loads(json_str.strip())
        else:
            calendar = json.loads(text)
    except json.JSONDecodeError:
        calendar = [{"error": "Could not parse calendar JSON", "raw": text[:500]}]

    # Save
    today = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = TMP_DIR / f"calendar_{today}_{business}.json"
    with open(filepath, "w") as f:
        json.dump(calendar, f, indent=2)

    print(f"[content_engine] Calendar: {len(calendar)} posts over {weeks} weeks → {filepath.name}")
    print(f"[content_engine] Cost: ${cost:.4f}")

    return {"file": str(filepath), "posts": len(calendar), "weeks": weeks, "cost": round(cost, 4)}


def repurpose_content(input_file, platforms):
    """Repurpose long-form content into short-form variants."""
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    source_content = input_path.read_text()[:6000]

    results = {}
    total_cost = 0
    today = datetime.utcnow().strftime("%Y-%m-%d")

    for platform in platforms:
        spec = PLATFORMS.get(platform)
        if not spec:
            continue

        prompt = f"""Repurpose this long-form content into a {spec['description']}.

Source content:
---
{source_content[:4000]}
---

Platform rules:
{spec['rules']}

Extract the most compelling insights and reformat for {platform}. Keep the same voice and authority.
Output only the final ready-to-post content."""

        response = client.messages.create(
            model=_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        content_text = response.content[0].text
        cost = _cost(_MODEL, response.usage.input_tokens, response.usage.output_tokens)
        total_cost += cost

        slug = input_path.stem[:30]
        filename = f"repurposed_{today}_{platform}_{slug}.md"
        filepath = TMP_DIR / filename
        filepath.write_text(f"# Repurposed: {platform.title()} from {input_path.name}\n\n{content_text}\n")

        results[platform] = {
            "file": str(filepath),
            "format": spec["format"],
            "word_count": len(content_text.split()),
            "cost": round(cost, 4),
        }

        print(f"[content_engine] {platform} (repurposed): {len(content_text.split())} words → {filepath.name}")

    print(f"[content_engine] Total cost: ${total_cost:.4f}")
    return results


def generate_ideas(business="agency", count=10):
    """Generate content topic ideas from ICP pain points."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    voice_context = load_voice_context(business)
    pain_points = get_icp_pain_points(business)

    prompt = f"""Generate {count} content topic ideas for social media.

Business context:
{voice_context[:1500]}

Known ICP pain points:
{chr(10).join(f'- {p}' for p in pain_points) if pain_points else 'Extract from business context above.'}

For each idea, provide:
1. Topic headline
2. Best platform (Instagram, LinkedIn, Twitter, YouTube, TikTok)
3. Content angle (educational, story, controversial, case study, how-to, myth-busting)
4. Why this would resonate with the ICP

Output as JSON array:
[{{"topic": "...", "platform": "...", "angle": "...", "why": "..."}}]

Prioritize topics that demonstrate expertise and build trust. Mix educational with proof-based content."""

    response = client.messages.create(
        model=_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    cost = _cost(_MODEL, response.usage.input_tokens, response.usage.output_tokens)

    try:
        if "```" in text:
            json_str = text.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
            ideas = json.loads(json_str.strip())
        else:
            ideas = json.loads(text)
    except json.JSONDecodeError:
        ideas = [{"error": "Could not parse ideas JSON", "raw": text[:500]}]

    today = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = TMP_DIR / f"ideas_{today}_{business}.json"
    with open(filepath, "w") as f:
        json.dump(ideas, f, indent=2)

    print(f"[content_engine] Generated {len(ideas)} topic ideas → {filepath.name}")
    print(f"[content_engine] Cost: ${cost:.4f}")

    return {"file": str(filepath), "ideas": ideas, "cost": round(cost, 4)}


# ── CLI Handlers ─────────────────────────────────────────────────────────────

def cli_generate(args):
    platforms = [p.strip() for p in args.platforms.split(",")]
    results = generate_content(args.topic, platforms, args.business, args.angle)
    print(json.dumps(results, indent=2))


def cli_calendar(args):
    topics = [t.strip() for t in args.topics.split(",")] if args.topics else None
    result = generate_calendar(args.weeks, args.frequency, args.business, topics)
    print(json.dumps(result, indent=2))


def cli_repurpose(args):
    platforms = [p.strip() for p in args.platforms.split(",")]
    try:
        results = repurpose_content(args.input, platforms)
        print(json.dumps(results, indent=2))
    except FileNotFoundError as e:
        print(f"[content_engine] Error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_ideas(args):
    result = generate_ideas(args.business, args.count)
    for i, idea in enumerate(result.get("ideas", []), 1):
        if isinstance(idea, dict) and "topic" in idea:
            print(f"  {i}. [{idea.get('platform', '?')}] {idea['topic']} ({idea.get('angle', '?')})")


# ── CLI Parser ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Content Engine — generate platform-native content from topics + ICP context"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate content for platforms")
    p_gen.add_argument("--topic", required=True, help="Content topic")
    p_gen.add_argument("--platforms", required=True, help="Comma-separated platforms (instagram,linkedin,twitter,youtube,tiktok,short-form)")
    p_gen.add_argument("--business", default="agency", choices=["agency", "coaching"])
    p_gen.add_argument("--angle", default=None, help="Content angle/hook")
    p_gen.set_defaults(func=cli_generate)

    # calendar
    p_cal = subparsers.add_parser("calendar", help="Generate content calendar")
    p_cal.add_argument("--weeks", type=int, default=4, help="Number of weeks (default: 4)")
    p_cal.add_argument("--frequency", type=int, default=3, help="Posts per week (default: 3)")
    p_cal.add_argument("--business", default="agency", choices=["agency", "coaching"])
    p_cal.add_argument("--topics", default=None, help="Comma-separated pre-selected topics")
    p_cal.set_defaults(func=cli_calendar)

    # repurpose
    p_rep = subparsers.add_parser("repurpose", help="Repurpose long-form into short-form")
    p_rep.add_argument("--input", required=True, help="Path to source content file")
    p_rep.add_argument("--platforms", required=True, help="Comma-separated target platforms")
    p_rep.set_defaults(func=cli_repurpose)

    # ideas
    p_ideas = subparsers.add_parser("ideas", help="Generate topic ideas from ICP")
    p_ideas.add_argument("--business", default="agency", choices=["agency", "coaching"])
    p_ideas.add_argument("--count", type=int, default=10, help="Number of ideas (default: 10)")
    p_ideas.set_defaults(func=cli_ideas)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
