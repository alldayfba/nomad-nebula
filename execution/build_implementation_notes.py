#!/usr/bin/env python3
"""
build_implementation_notes.py — Per-Video Implementation Breakdown
Takes raw scraped transcripts and produces a detailed per-video implementation
notes document with specific action items.

Unlike build_creator_brain.py (which synthesizes themes), this preserves
per-video granularity for "line by line" analysis.

Usage:
  python execution/build_implementation_notes.py \
    --name "nick-saraev" \
    --context "Agency OS (growth agency for 7-8 figure founders), Amazon OS (FBA coaching)"
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

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
MODEL = "claude-sonnet-4-6"
MAX_TOKENS_PER_VIDEO = 4096


def log(msg):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Per-video analysis prompt
# ---------------------------------------------------------------------------
ANALYSIS_PROMPT = """You are analyzing a single YouTube video transcript. Extract EVERY actionable implementation item.

**Video Title:** {title}
**Upload Date:** {upload_date}
**URL:** https://www.youtube.com/watch?v={video_id}

**Business Context:** {context}

For this video, provide:

### Key Teachings
Bullet-point list of the main concepts, frameworks, or ideas taught in this video.

### Implementation Items
For EACH actionable item, use this format:
- [ ] **[Item name]** — [What it is and how to implement it]. Priority: [must-do / should-do / nice-to-have]. Tools/tech: [if mentioned]

### Direct Quotes
Any powerful or defining quotes (max 3-5).

### Relevance to Business
How this specifically applies to the user's businesses (if context provided).

**RULES:**
- Be EXHAUSTIVE — extract every single actionable item, no matter how small
- Preserve specificity — keep all numbers, names, tools, URLs, exact steps
- If the creator references a specific tool, framework, or service — name it
- If they give a step-by-step process — list every step
- If the transcript is empty or too short to analyze, just note "No transcript available"

---

TRANSCRIPT:

{transcript}"""


# ---------------------------------------------------------------------------
# Process each video
# ---------------------------------------------------------------------------
def analyze_video(client: anthropic.Anthropic, video: dict, context: str) -> str:
    """Analyze a single video transcript and return markdown notes."""
    title = video.get("title", "Untitled")
    video_id = video.get("video_id", "unknown")
    upload_date = video.get("upload_date", "Unknown")
    transcript = video.get("transcript", "").strip()

    if not transcript or len(transcript) < 50:
        return f"*No transcript available for this video.*\n"

    # Format date nicely if in YYYYMMDD format
    date_display = upload_date
    if upload_date and len(upload_date) == 8 and upload_date.isdigit():
        date_display = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_PER_VIDEO,
        messages=[{
            "role": "user",
            "content": ANALYSIS_PROMPT.format(
                title=title,
                upload_date=date_display,
                video_id=video_id,
                transcript=transcript[:60000],  # Cap at ~15K tokens
                context=context or "Not specified",
            )
        }]
    )

    return response.content[0].text


def build_master_checklist(client: anthropic.Anthropic, all_notes: str, context: str) -> str:
    """Synthesize all per-video notes into a deduplicated master checklist."""
    log("Building master implementation checklist...")

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": f"""Below are per-video implementation notes from a YouTube channel analysis.

Create a **Master Implementation Checklist** that:
1. Deduplicates items mentioned across multiple videos
2. Groups by category (e.g., "AI Agents", "Content Strategy", "Business Systems", "Claude Code", etc.)
3. Prioritizes: must-do first, then should-do, then nice-to-have
4. For each item, note which video(s) it came from

Business context: {context or "Not specified"}

Format as a markdown checklist with categories and priorities.

---

SOURCE NOTES:

{all_notes[:100000]}"""
        }]
    )

    return response.content[0].text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Build per-video implementation notes from scraped transcripts")
    parser.add_argument("--name", required=True, help="Creator slug (must match scrape output)")
    parser.add_argument("--input", default=None, help="Path to raw JSON (default: .tmp/creators/{name}-raw.json)")
    parser.add_argument("--context", default="", help="Business context for relevance mapping")
    parser.add_argument("--skip-master", action="store_true", help="Skip master checklist synthesis")
    return parser.parse_args()


def main():
    args = parse_args()

    TMP_DIR.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input) if args.input else TMP_DIR / f"{args.name}-raw.json"
    output_path = TMP_DIR / f"{args.name}-implementation-notes.md"

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        print(f"Run scrape_creator_intel.py first with --name \"{args.name}\"", file=sys.stderr)
        sys.exit(1)

    log(f"=== Building Implementation Notes: {args.name} ===")
    start_time = time.time()

    # Load raw data
    with open(input_path) as f:
        data = json.load(f)

    client = anthropic.Anthropic()

    # Get all videos with transcripts
    yt = data.get("youtube") or {}
    videos = yt.get("videos") or []
    videos_with_transcripts = [v for v in videos if v.get("transcript", "").strip()]

    log(f"Found {len(videos_with_transcripts)} videos with transcripts (out of {len(videos)} total)")

    # Process each video
    all_sections = []
    for i, video in enumerate(videos_with_transcripts):
        title = video.get("title", "Untitled")
        upload_date = video.get("upload_date", "")
        video_id = video.get("video_id", "")
        duration = video.get("duration")
        views = video.get("view_count")

        # Format date
        date_display = upload_date
        if upload_date and len(upload_date) == 8 and upload_date.isdigit():
            date_display = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

        log(f"[{i+1}/{len(videos_with_transcripts)}] Analyzing: {title[:55]}...")

        analysis = analyze_video(client, video, args.context)

        # Build section header
        duration_str = f"{duration // 60}m{duration % 60:02d}s" if duration else "?"
        views_str = f"{views:,}" if views else "?"

        section = f"### {i+1}. {title} ({date_display})\n"
        section += f"**URL:** https://www.youtube.com/watch?v={video_id} | **Duration:** {duration_str} | **Views:** {views_str}\n\n"
        section += analysis
        section += "\n\n---\n\n"

        all_sections.append(section)

        # Small delay to avoid rate limits
        if i < len(videos_with_transcripts) - 1:
            time.sleep(0.5)

    # Assemble the document
    header = f"# {args.name} — Implementation Notes\n"
    header += f"> {len(videos_with_transcripts)} videos analyzed | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    header += f"> Source: {yt.get('channel_url', 'YouTube')}\n\n"
    header += "---\n\n"
    header += "## Video-by-Video Breakdown\n\n"

    full_notes = header + "".join(all_sections)

    # Build master checklist
    if not args.skip_master and all_sections:
        master = build_master_checklist(client, full_notes, args.context)
        full_notes += "\n\n## Master Implementation Checklist\n\n"
        full_notes += master

    # Save
    with open(output_path, "w") as f:
        f.write(full_notes)

    elapsed = time.time() - start_time
    log(f"=== Done in {elapsed:.0f}s ===")
    log(f"Output: {output_path}")
    log(f"Length: {len(full_notes):,} chars (~{len(full_notes.splitlines())} lines)")

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"IMPLEMENTATION NOTES: {args.name}", file=sys.stderr)
    print(f"  Videos analyzed: {len(videos_with_transcripts)}", file=sys.stderr)
    print(f"  Output: {output_path} ({len(full_notes):,} chars)", file=sys.stderr)
    print(f"  Time: {elapsed:.0f}s", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)

    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
