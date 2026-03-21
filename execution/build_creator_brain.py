#!/usr/bin/env python3
"""
build_creator_brain.py — Creator Brain Synthesizer
Takes raw scraped transcripts from scrape_creator_intel.py and uses Claude
to synthesize them into a comprehensive reference document.

Output is a Jeremy-Haynes-style brain doc capturing:
- Frameworks, mechanisms, named concepts
- Strategies and SOPs
- Buyer psychology insights
- Offer architecture
- Content strategy
- Key terminology
- Specific examples and case studies

Usage:
  python execution/build_creator_brain.py \
    --name "nik-setting" \
    --focus "offer positioning, content strategy, funnel architecture"

  python execution/build_creator_brain.py \
    --name "nik-setting" \
    --input ".tmp/creators/nik-setting-raw.json"
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Load .env for ANTHROPIC_API_KEY
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TMP_DIR = Path(".tmp/creators")
OUTPUT_DIR = Path("bots/creators")

# Model routing per CLAUDE.md: Sonnet for extraction, Opus for synthesis
EXTRACTION_MODEL = "claude-sonnet-4-6"
SYNTHESIS_MODEL = "claude-opus-4-6"

# Max tokens per chunk (leave room for prompt + response)
MAX_CHUNK_CHARS = 80000  # ~20K tokens of transcript per chunk
MAX_EXTRACTION_TOKENS = 8192
MAX_SYNTHESIS_TOKENS = 16384


def log(msg):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Load and prepare transcripts
# ---------------------------------------------------------------------------
def load_raw_data(input_path: Path) -> dict:
    """Load the raw JSON from scrape_creator_intel.py."""
    with open(input_path) as f:
        return json.load(f)


def prepare_transcript_chunks(data: dict) -> list[str]:
    """Combine all transcripts and split into chunks for Claude processing."""
    all_content = []

    # YouTube transcripts
    yt = data.get("youtube") or {}
    for vid in (yt.get("videos") or []):
        transcript = vid.get("transcript", "").strip()
        if transcript:
            title = vid.get("title", "Untitled")
            all_content.append(f"## YouTube Video: {title}\n\n{transcript}")

    # Instagram reel transcripts
    ig = data.get("instagram") or {}
    for reel in (ig.get("reels") or []):
        transcript = reel.get("transcript", "").strip()
        if transcript:
            reel_id = reel.get("reel_id", "unknown")
            all_content.append(f"## Instagram Reel: {reel_id}\n\n{transcript}")

    # Instagram captions (lightweight but useful for voice/positioning)
    captions = ig.get("captions") or []
    if captions:
        caption_block = "\n---\n".join(captions[:30])
        all_content.append(f"## Instagram Captions\n\n{caption_block}")

    # Combine and chunk
    full_text = "\n\n---\n\n".join(all_content)
    log(f"Total content: {len(full_text):,} chars (~{len(full_text)//4:,} tokens)")

    if not full_text.strip():
        log("WARNING: No transcript content found!")
        return []

    # Split into chunks
    chunks = []
    current = ""
    for section in all_content:
        if len(current) + len(section) > MAX_CHUNK_CHARS and current:
            chunks.append(current)
            current = section
        else:
            current += "\n\n---\n\n" + section if current else section
    if current:
        chunks.append(current)

    log(f"Split into {len(chunks)} chunks for processing")
    return chunks


# ---------------------------------------------------------------------------
# Pass 1: Extract intelligence from each chunk
# ---------------------------------------------------------------------------
EXTRACTION_PROMPT = """You are analyzing transcripts from a content creator. Your job is to extract EVERY piece of actionable intelligence.

Extract the following from these transcripts:

1. **Named Frameworks & Mechanisms** — Any named process, system, method, or concept they teach. Include the name AND a full explanation of how it works.
2. **Strategies & Step-by-Step Processes** — Specific tactical advice. How-to sequences. SOPs they describe.
3. **Core Beliefs & Philosophy** — What they believe about their industry, business, success, failure. Their worldview.
4. **Buyer Psychology Insights** — What they say about why people buy, objections, decision-making.
5. **Offer Architecture** — How they structure offers, pricing, packaging, guarantees.
6. **Specific Examples & Case Studies** — Real examples they reference (client names, numbers, scenarios).
7. **Key Terminology** — Unique terms, phrases, or jargon they use with specific meanings.
8. **Anti-patterns** — Things they explicitly say NOT to do, with their reasoning.
9. **Content & Marketing Strategy** — How they approach content creation, distribution, audience building.
10. **Quotable Lines** — Direct quotes that capture their voice and philosophy.

Be exhaustive. Extract everything. Do not summarize — preserve specificity and detail. If they give a number, keep the number. If they name a person, keep the name. If they describe a step-by-step process, list every step.

{focus_instruction}

---

TRANSCRIPTS TO ANALYZE:

{transcript_chunk}"""


def extract_intelligence(client: anthropic.Anthropic, chunk: str, chunk_num: int, total_chunks: int, focus: str = "") -> str:
    """Extract intelligence from a single transcript chunk using Sonnet."""
    log(f"Extracting intelligence from chunk {chunk_num}/{total_chunks}...")

    focus_instruction = ""
    if focus:
        focus_instruction = f"Pay special attention to content related to: {focus}"

    response = client.messages.create(
        model=EXTRACTION_MODEL,
        max_tokens=MAX_EXTRACTION_TOKENS,
        messages=[{
            "role": "user",
            "content": EXTRACTION_PROMPT.format(
                transcript_chunk=chunk,
                focus_instruction=focus_instruction,
            )
        }]
    )

    return response.content[0].text


# ---------------------------------------------------------------------------
# Pass 2: Synthesize all extractions into final brain doc
# ---------------------------------------------------------------------------
SYNTHESIS_PROMPT = """You are building a comprehensive reference document for a content creator named "{creator_name}".

Below are intelligence extractions from ALL of their public content (YouTube videos and Instagram Reels). Your job is to synthesize this into a SINGLE, authoritative reference document — like a master SOP that captures their entire intellectual framework.

This document will be used as a reference when building offers, VSLs, launches, content strategies, or any other business asset. When someone says "reference the {creator_name} doc," this is what they pull up.

**DOCUMENT STRUCTURE (follow this exactly):**

# {creator_name} — Creator Intelligence Report
> Synthesized from [X] YouTube videos and [Y] Instagram Reels
> Generated: [date]

## Table of Contents
[auto-generate based on sections below]

## 1. Core Philosophy & Beliefs
[Their fundamental worldview. What they believe about their industry, success, failure, their audience. The operating principles that drive everything they teach.]

## 2. Named Frameworks & Mechanisms
[Every named framework, system, or method — with FULL explanations. Each gets its own subsection. Include: what it is, how it works, when to use it, specific examples they gave.]

## 3. Strategies & SOPs
[Step-by-step processes they teach. Tactical playbooks. How-to sequences. Written as actionable instructions.]

## 4. Offer Architecture
[How they structure offers. Pricing philosophy. Packaging. Guarantees. What they include, what they don't, and why.]

## 5. Buyer Psychology & Sales Insights
[What they teach about why people buy, objections, decision-making. Sales process insights. Qualification frameworks.]

## 6. Content & Marketing Strategy
[How they approach content. Distribution channels. Audience building tactics. What content formats they use and why.]

## 7. Case Studies & Examples
[Specific examples they reference — client stories, numbers, scenarios. Keep all specifics (names, numbers, timelines).]

## 8. Anti-Patterns
[Everything they explicitly say NOT to do, organized by category. Include their reasoning.]

## 9. Key Terminology
[Table format: Term | Definition — every unique term or phrase they use with specific meaning.]

## 10. Quick Reference
[The 10-15 most important takeaways condensed into bullet points for fast scanning.]

**RULES:**
- Be EXHAUSTIVE. This is a reference doc, not a summary. Length is good.
- Preserve specificity — numbers, names, timelines, exact processes.
- Use their actual language and terminology where possible.
- Include direct quotes where they're powerful or defining.
- If multiple extractions mention the same concept, merge them into the most complete version.
- Organize logically within each section (not by source video).
- Write in a way that someone with NO context can understand and act on every section.

{focus_instruction}

---

SOURCE STATS:
- YouTube videos analyzed: {youtube_count}
- Instagram Reels analyzed: {instagram_count}
- Total words of transcript: ~{total_words:,}

---

EXTRACTED INTELLIGENCE:

{all_extractions}"""


def synthesize_brain(client: anthropic.Anthropic, extractions: list[str], creator_name: str,
                     youtube_count: int, instagram_count: int, total_words: int, focus: str = "") -> str:
    """Synthesize all extractions into the final brain document using Opus."""
    log(f"Synthesizing brain document with {SYNTHESIS_MODEL}...")

    all_extractions = "\n\n===== EXTRACTION BATCH =====\n\n".join(extractions)

    focus_instruction = ""
    if focus:
        focus_instruction = f"Give extra depth and detail to sections related to: {focus}"

    response = client.messages.create(
        model=SYNTHESIS_MODEL,
        max_tokens=MAX_SYNTHESIS_TOKENS,
        messages=[{
            "role": "user",
            "content": SYNTHESIS_PROMPT.format(
                creator_name=creator_name,
                youtube_count=youtube_count,
                instagram_count=instagram_count,
                total_words=total_words,
                all_extractions=all_extractions,
                focus_instruction=focus_instruction,
            )
        }]
    )

    return response.content[0].text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Synthesize creator brain doc from scraped transcripts")
    parser.add_argument("--name", required=True, help="Creator slug (must match scrape_creator_intel output)")
    parser.add_argument("--input", default=None, help="Path to raw JSON (default: .tmp/creators/{name}-raw.json)")
    parser.add_argument("--focus", default="", help="Optional focus areas (comma-separated)")
    parser.add_argument("--extraction-only", action="store_true", help="Only run extraction pass, skip synthesis")
    parser.add_argument("--synthesis-only", action="store_true", help="Only run synthesis (requires prior extraction)")
    return parser.parse_args()


def main():
    args = parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input) if args.input else TMP_DIR / f"{args.name}-raw.json"
    output_path = OUTPUT_DIR / f"{args.name}-brain.md"
    extraction_cache = TMP_DIR / f"{args.name}-extractions.json"

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        print(f"Run scrape_creator_intel.py first with --name \"{args.name}\"", file=sys.stderr)
        sys.exit(1)

    log(f"=== Building Creator Brain: {args.name} ===")
    start_time = time.time()

    client = anthropic.Anthropic()

    # Load raw data
    data = load_raw_data(input_path)

    # Calculate stats
    yt = data.get("youtube") or {}
    ig = data.get("instagram") or {}
    youtube_count = yt.get("transcripts_success", 0)
    instagram_count = ig.get("transcripts_success", 0)
    total_words = 0
    for v in (yt.get("videos") or []):
        total_words += len(v.get("transcript", "").split())
    for r in (ig.get("reels") or []):
        total_words += len(r.get("transcript", "").split())

    log(f"Stats: {youtube_count} YT transcripts, {instagram_count} IG transcripts, ~{total_words:,} words")

    # --- Pass 1: Extract ---
    extractions = []

    if args.synthesis_only and extraction_cache.exists():
        log("Loading cached extractions...")
        with open(extraction_cache) as f:
            extractions = json.load(f)
    else:
        chunks = prepare_transcript_chunks(data)
        if not chunks:
            print("ERROR: No transcript content to process.", file=sys.stderr)
            sys.exit(1)

        for i, chunk in enumerate(chunks):
            extraction = extract_intelligence(client, chunk, i + 1, len(chunks), args.focus)
            extractions.append(extraction)
            log(f"Extraction {i+1}/{len(chunks)}: {len(extraction):,} chars")

        # Cache extractions
        with open(extraction_cache, "w") as f:
            json.dump(extractions, f, indent=2, ensure_ascii=False)
        log(f"Extractions cached to: {extraction_cache}")

    if args.extraction_only:
        elapsed = time.time() - start_time
        log(f"Extraction-only mode. Done in {elapsed:.0f}s.")
        print(f"Extractions saved: {extraction_cache}")
        return

    # --- Pass 2: Synthesize ---
    brain_doc = synthesize_brain(
        client, extractions, args.name,
        youtube_count, instagram_count, total_words, args.focus
    )

    # Save output
    with open(output_path, "w") as f:
        f.write(brain_doc)

    elapsed = time.time() - start_time
    log(f"=== Brain doc complete in {elapsed:.0f}s ===")
    log(f"Output: {output_path}")
    log(f"Length: {len(brain_doc):,} chars (~{len(brain_doc.splitlines())} lines)")

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"CREATOR BRAIN: {args.name}", file=sys.stderr)
    print(f"  Source: {youtube_count} YouTube + {instagram_count} Instagram (~{total_words:,} words)", file=sys.stderr)
    print(f"  Extraction passes: {len(extractions)} chunks via {EXTRACTION_MODEL}", file=sys.stderr)
    print(f"  Synthesis: {SYNTHESIS_MODEL}", file=sys.stderr)
    print(f"  Output: {output_path} ({len(brain_doc):,} chars)", file=sys.stderr)
    print(f"  Time: {elapsed:.0f}s", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)

    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
