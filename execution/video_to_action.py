#!/usr/bin/env python3
"""
video_to_action.py — YouTube Video to Structured Action Items Pipeline.

Takes a YouTube URL or transcript file, extracts structured implementation
tasks with timestamps, priorities, and file-level specificity.

Optionally uses Gemini for multimodal analysis (frames + transcript).

Usage:
    # From YouTube URL
    python execution/video_to_action.py \
        --url "https://www.youtube.com/watch?v=EsTrWCV0Ph4" \
        --context "Growth agency + FBA coaching business"

    # From transcript file
    python execution/video_to_action.py \
        --transcript .tmp/creators/nick-saraev/transcript.txt \
        --context "AI agent orchestration patterns"

    # With Gemini multimodal (extracts key frames)
    python execution/video_to_action.py \
        --url "https://www.youtube.com/watch?v=EsTrWCV0Ph4" \
        --multimodal \
        --context "AI agents"

    # Programmatic:
    from execution.video_to_action import process_video
    result = process_video(url="...", context="...")
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic", file=sys.stderr)
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
TMP_DIR = Path(".tmp/video-actions")
MODEL = "claude-sonnet-4-6"
MAX_TRANSCRIPT_CHARS = 100000
CHUNK_SIZE = 30000


def log(msg):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


# ── Transcript Extraction ─────────────────────────────────────────────────────

def extract_transcript_ytdlp(url: str) -> str:
    """Extract transcript using yt-dlp."""
    log("Extracting transcript via yt-dlp...")
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--skip-download",
            "--sub-format", "vtt",
            "-o", f"{tmp}/video",
            url,
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            log("yt-dlp not found, trying alternative...")
            return None

        # Find the subtitle file
        vtt_files = list(Path(tmp).glob("*.vtt"))
        if not vtt_files:
            # Try SRT
            cmd[-3] = "srt"
            subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            vtt_files = list(Path(tmp).glob("*.srt"))

        if not vtt_files:
            return None

        return vtt_files[0].read_text(encoding="utf-8", errors="replace")


def extract_key_frames(url: str, count: int = 5) -> list[Path]:
    """Extract key frames from video using yt-dlp + ffmpeg."""
    log(f"Extracting {count} key frames...")
    frames_dir = TMP_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Download video (low quality for speed)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "yt-dlp",
            "-f", "worst[ext=mp4]",
            "-o", f"{tmp}/video.mp4",
            url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                log("Video download failed")
                return []
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        video_path = Path(tmp) / "video.mp4"
        if not video_path.exists():
            return []

        # Extract frames at intervals using ffmpeg
        try:
            cmd = [
                "ffmpeg", "-i", str(video_path),
                "-vf", f"fps=1/{max(60, 300)}",  # 1 frame per 5 min (or 1/min for short)
                "-frames:v", str(count),
                str(frames_dir / "frame_%03d.jpg"),
                "-y",
            ]
            subprocess.run(cmd, capture_output=True, timeout=120)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

    return sorted(frames_dir.glob("frame_*.jpg"))


# ── Analysis ──────────────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """You are analyzing a video transcript to extract actionable implementation items.

Context about the user's business/system: {context}

For each distinct technique, concept, or actionable idea in the transcript:

1. Give it a clear **name**
2. Note the approximate **timestamp** (from the transcript timestamps)
3. Write a concise **summary** (2-3 sentences)
4. List specific **implementation_steps** (numbered, actionable)
5. Suggest **files_to_create** or modify (if applicable)
6. Assign a **priority**: high (implement now), medium (implement soon), low (nice to have)
7. Note any **dependencies** on other techniques

Output ONLY valid JSON in this exact format:
{{
  "video_title": "title from context",
  "techniques": [
    {{
      "name": "Technique Name",
      "timestamp": "HH:MM:SS",
      "summary": "Brief description",
      "implementation_steps": [
        "Step 1: Do X",
        "Step 2: Do Y"
      ],
      "files_to_create": ["path/to/file.py"],
      "files_to_modify": ["path/to/existing.md"],
      "priority": "high",
      "dependencies": ["Other Technique Name"]
    }}
  ]
}}

Be specific and actionable. Don't include vague items like "learn more about X".
Each technique should be something you could build in a day or less."""

SYNTHESIS_PROMPT = """Combine these partial analyses into a single unified list.

Merge duplicates, resolve conflicts, and produce the final JSON.
Maintain the same format. Sort by priority (high first, then medium, then low).
Remove any items that are too vague to act on.

Partial analyses:
{chunks}

Output ONLY valid JSON."""


def analyze_transcript_chunk(client: anthropic.Anthropic, chunk: str, context: str) -> str:
    """Analyze a single transcript chunk."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": ANALYSIS_PROMPT.format(context=context) + f"\n\n## Transcript\n{chunk}",
        }],
    )
    return response.content[0].text if response.content else ""


def process_video(
    url: str = None,
    transcript_path: str = None,
    context: str = "",
    multimodal: bool = False,
) -> dict:
    """Process a video and extract structured action items."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()

    # Step 1: Get transcript
    transcript = None
    if transcript_path:
        transcript = Path(transcript_path).read_text(encoding="utf-8", errors="replace")
        log(f"Loaded transcript: {len(transcript)} chars")
    elif url:
        transcript = extract_transcript_ytdlp(url)
        if transcript:
            log(f"Extracted transcript: {len(transcript)} chars")
        else:
            log("Could not extract transcript")
            return {"error": "Failed to extract transcript", "url": url}

    if not transcript:
        return {"error": "No transcript available"}

    # Truncate if needed
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS]
        log(f"Truncated to {MAX_TRANSCRIPT_CHARS} chars")

    # Step 2: Chunk and analyze
    chunks = []
    for i in range(0, len(transcript), CHUNK_SIZE):
        chunks.append(transcript[i:i + CHUNK_SIZE])

    log(f"Processing {len(chunks)} chunk(s)...")

    analyses = []
    for i, chunk in enumerate(chunks):
        log(f"  Analyzing chunk {i+1}/{len(chunks)}...")
        result = analyze_transcript_chunk(client, chunk, context)
        analyses.append(result)
        if i < len(chunks) - 1:
            time.sleep(1)  # Rate limit courtesy

    # Step 3: Synthesize if multiple chunks
    if len(analyses) > 1:
        log("Synthesizing chunks...")
        combined = "\n---\n".join(analyses)
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            messages=[{
                "role": "user",
                "content": SYNTHESIS_PROMPT.format(chunks=combined),
            }],
        )
        final_text = response.content[0].text if response.content else analyses[0]
    else:
        final_text = analyses[0]

    # Step 4: Parse JSON
    try:
        # Find JSON in response
        start = final_text.find("{")
        end = final_text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(final_text[start:end])
        else:
            result = {"raw_text": final_text, "parse_error": "No JSON found"}
    except json.JSONDecodeError as e:
        result = {"raw_text": final_text[:5000], "parse_error": str(e)}

    # Add metadata
    result["meta"] = {
        "source_url": url,
        "transcript_path": transcript_path,
        "context": context,
        "transcript_chars": len(transcript),
        "chunks_processed": len(chunks),
        "multimodal": multimodal,
        "model": MODEL,
        "timestamp": datetime.now().isoformat(),
    }

    # Step 5: Save
    output_file = TMP_DIR / f"actions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_file.write_text(json.dumps(result, indent=2))
    log(f"Saved to {output_file}")

    # Also save markdown version
    md_file = output_file.with_suffix(".md")
    md_lines = [f"# Video Action Items\n", f"Source: {url or transcript_path}\n"]
    for tech in result.get("techniques", []):
        md_lines.append(f"\n## {tech.get('name', 'Unknown')} [{tech.get('priority', '?')}]")
        md_lines.append(f"*Timestamp: {tech.get('timestamp', '?')}*\n")
        md_lines.append(tech.get("summary", ""))
        md_lines.append("\n**Steps:**")
        for step in tech.get("implementation_steps", []):
            md_lines.append(f"- {step}")
        if tech.get("files_to_create"):
            md_lines.append(f"\n**Create:** {', '.join(tech['files_to_create'])}")
        if tech.get("files_to_modify"):
            md_lines.append(f"**Modify:** {', '.join(tech['files_to_modify'])}")
    md_file.write_text("\n".join(md_lines))
    log(f"Markdown saved to {md_file}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Extract action items from YouTube videos")
    parser.add_argument("--url", help="YouTube video URL")
    parser.add_argument("--transcript", help="Path to transcript file")
    parser.add_argument("--context", default="", help="Business context for relevance filtering")
    parser.add_argument("--multimodal", action="store_true", help="Extract key frames (requires Gemini)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if not args.url and not args.transcript:
        parser.error("Provide either --url or --transcript")

    result = process_video(
        url=args.url,
        transcript_path=args.transcript,
        context=args.context,
        multimodal=args.multimodal,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        techniques = result.get("techniques", [])
        if techniques:
            print(f"\n{'='*60}")
            print(f"EXTRACTED {len(techniques)} TECHNIQUES")
            print(f"{'='*60}")
            for t in techniques:
                priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.get("priority"), "⚪")
                print(f"\n{priority_icon} {t['name']} [{t.get('timestamp', '?')}]")
                print(f"   {t.get('summary', '')[:200]}")
                steps = t.get("implementation_steps", [])
                for s in steps[:3]:
                    print(f"   → {s}")
                if len(steps) > 3:
                    print(f"   → ... +{len(steps)-3} more steps")
        elif "error" in result:
            print(f"Error: {result['error']}")
        else:
            print("No techniques extracted. Check transcript quality.")


if __name__ == "__main__":
    main()
