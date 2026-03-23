#!/usr/bin/env python3
"""
creator_video_scanner.py -- Scan tracked creators for new YouTube videos.

Reads creator handles from bots/creators/HANDLES.md, checks latest videos
via yt-dlp, transcribes new ones (captions or whisper), analyzes with
Claude Haiku, and appends findings to creator brain files.

Usage:
    # Scan all creators
    python execution/creator_video_scanner.py

    # Dry run (just report new videos, no download/transcribe)
    python execution/creator_video_scanner.py --dry-run

    # Scan a single creator
    python execution/creator_video_scanner.py --creator niksetting

    # Programmatic
    from execution.creator_video_scanner import scan_all_creators
    results = scan_all_creators(dry_run=True)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HANDLES_FILE = PROJECT_ROOT / "bots" / "creators" / "HANDLES.md"
BRAIN_DIR = PROJECT_ROOT / "bots" / "creators"
TMP_DIR = PROJECT_ROOT / ".tmp" / "creators"
STATE_FILE = PROJECT_ROOT / ".tmp" / "creator_video_state.json"
VENV314_PYTHON = PROJECT_ROOT / ".venv314" / "bin" / "python3"
VENV314_YTDLP = PROJECT_ROOT / ".venv314" / "bin" / "yt-dlp"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python3"

# ── Config ───────────────────────────────────────────────────────────────────

HAIKU_MODEL = "claude-haiku-4-5-20251001"
LATEST_N = 3  # Check latest N videos per channel
MAX_TRANSCRIPT_CHARS = 80000

# Secondary channels: main handle -> list of extra handles to also check
SECONDARY_CHANNELS = {
    "niksetting": ["mrniksetting"],
}

# ── Env ──────────────────────────────────────────────────────────────────────

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {msg}", file=sys.stderr)


# ── Parse HANDLES.md ─────────────────────────────────────────────────────────

def parse_handles() -> list[dict]:
    """Parse HANDLES.md and return list of creators with YouTube handles."""
    text = HANDLES_FILE.read_text(encoding="utf-8")
    creators = []

    # Match table rows: | **Name** | [@handle](url) | ...
    # Skip header and separator rows
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("|---") or "Creator" in line:
            continue

        cols = [c.strip() for c in line.split("|")]
        # cols[0] is empty (before first |), cols[1]=Creator, cols[2]=YouTube, ...
        if len(cols) < 3:
            continue

        creator_col = cols[1]
        youtube_col = cols[2]

        # Extract creator name (strip bold markers)
        name = re.sub(r"\*\*", "", creator_col).strip()
        if not name:
            continue

        # Extract YouTube handle from markdown link [@handle](url)
        yt_match = re.search(r"\[@([^\]]+)\]", youtube_col)
        if not yt_match:
            # Check for plain channel links
            ch_match = re.search(r"\[Channel\]\((https://youtube\.com/channel/[^)]+)\)", youtube_col)
            if ch_match:
                creators.append({
                    "name": name,
                    "handle": None,
                    "channel_url": ch_match.group(1),
                    "brain_file": _find_brain_file(name),
                })
            continue

        handle = yt_match.group(1)
        # Skip TBD, skip self (AllDayFBA)
        if handle.lower() in ("tbd", "alldayfba"):
            continue

        creators.append({
            "name": name,
            "handle": handle,
            "channel_url": f"https://youtube.com/@{handle}",
            "brain_file": _find_brain_file(name),
        })

    return creators


def _find_brain_file(name: str) -> Path | None:
    """Find the brain file for a creator by name."""
    # Normalize: "Nik Setting" -> "nik-setting-brain.md"
    slug = name.lower().replace(" ", "-").replace("(", "").replace(")", "")
    candidates = [
        BRAIN_DIR / f"{slug}-brain.md",
        BRAIN_DIR / f"{slug.split('-')[0]}-brain.md",  # first name only
    ]
    # Special cases
    special = {
        "soowei goh": "soowei-goh-brain.md",
        "sabbo alldayfba": "sabbo-alldayfba-brain.md",
        "kabrin johal": "kabrin-brain.md",
    }
    if slug in special:
        candidates.insert(0, BRAIN_DIR / special[slug])

    for p in candidates:
        if p.exists():
            return p
    return None


# ── State Management ─────────────────────────────────────────────────────────

def load_state() -> dict:
    """Load processed video IDs from state file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state: dict) -> None:
    """Save processed video IDs to state file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── yt-dlp Operations (uses .venv314) ───────────────────────────────────────

def get_latest_videos(channel_url: str, count: int = LATEST_N) -> list[dict]:
    """Get latest N videos from a YouTube channel via yt-dlp (.venv314)."""
    cmd = [
        str(VENV314_YTDLP),
        "--flat-playlist",
        "--playlist-end", str(count),
        "--dump-json",
        "--no-warnings",
        f"{channel_url}/videos",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log(f"  yt-dlp error: {result.stderr[:200]}")
            return []

        videos = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                videos.append({
                    "id": data.get("id", ""),
                    "title": data.get("title", "Unknown"),
                    "url": data.get("url") or data.get("webpage_url") or f"https://www.youtube.com/watch?v={data.get('id', '')}",
                    "upload_date": data.get("upload_date", ""),
                    "duration": data.get("duration"),
                    "view_count": data.get("view_count"),
                })
            except json.JSONDecodeError:
                continue
        return videos
    except subprocess.TimeoutExpired:
        log("  yt-dlp timed out")
        return []
    except FileNotFoundError:
        log(f"  yt-dlp not found at {VENV314_YTDLP}")
        return []


def download_audio(video_url: str, output_path: str) -> bool:
    """Download audio from a YouTube video via yt-dlp (.venv314)."""
    cmd = [
        str(VENV314_YTDLP),
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "-o", output_path,
        "--no-playlist",
        "--no-warnings",
        video_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            log(f"  Audio download failed: {result.stderr[:200]}")
            return False
        return Path(output_path).exists() or any(
            Path(output_path).parent.glob(Path(output_path).stem + ".*")
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# ── Transcript Extraction ────────────────────────────────────────────────────

def get_transcript_captions(video_id: str) -> str | None:
    """Try youtube-transcript-api first (free, fast, no download)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
        lines = [entry.text for entry in transcript.snippets]
        return " ".join(lines)
    except Exception as e:
        log(f"  Captions unavailable: {e}")
        return None


def get_transcript_whisper(video_url: str, video_id: str) -> str | None:
    """Fallback: download audio and transcribe with faster_whisper."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = str(TMP_DIR / f"{video_id}_audio.m4a")

    log("  Downloading audio for whisper transcription...")
    if not download_audio(video_url, audio_path):
        # Check for alternate extensions
        audio_glob = list(TMP_DIR.glob(f"{video_id}_audio.*"))
        if audio_glob:
            audio_path = str(audio_glob[0])
        else:
            log("  Audio download failed")
            return None

    log("  Transcribing with faster_whisper (base model)...")
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, beam_size=5)
        text_parts = [segment.text for segment in segments]
        transcript = " ".join(text_parts)
        log(f"  Whisper transcription complete: {len(transcript)} chars")
        return transcript if transcript.strip() else None
    except ImportError:
        log("  faster_whisper not installed")
        return None
    except Exception as e:
        log(f"  Whisper error: {e}")
        return None
    finally:
        # Clean up audio file
        for f in TMP_DIR.glob(f"{video_id}_audio.*"):
            try:
                f.unlink()
            except OSError:
                pass


def get_transcript(video_id: str, video_url: str) -> tuple[str | None, str]:
    """Get transcript, trying captions first then whisper. Returns (text, method)."""
    transcript = get_transcript_captions(video_id)
    if transcript:
        return transcript, "captions"

    transcript = get_transcript_whisper(video_url, video_id)
    if transcript:
        return transcript, "whisper"

    return None, "failed"


# ── Analysis with Claude Haiku ───────────────────────────────────────────────

ANALYSIS_PROMPT = """You are analyzing a YouTube video transcript from {creator_name}, a mentor/creator tracked by Sabbo (AllDayFBA). Extract: 1) Key frameworks or systems revealed, 2) Specific strategies or tactics, 3) Notable quotes, 4) What Sabbo should steal/adapt for his Amazon FBA coaching business (24/7 Profits) or Growth Agency. Be specific and actionable. Format as markdown."""


def analyze_transcript(creator_name: str, video_title: str, transcript: str) -> str:
    """Analyze transcript with Claude Haiku."""
    try:
        import anthropic
    except ImportError:
        log("  anthropic package not installed")
        return ""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log("  ANTHROPIC_API_KEY not set")
        return ""

    # Truncate if needed
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS]

    client = anthropic.Anthropic(api_key=api_key)
    prompt = ANALYSIS_PROMPT.format(creator_name=creator_name)
    user_msg = f"{prompt}\n\n## Video: {video_title}\n\n## Transcript\n{transcript}"

    try:
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text if response.content else ""
    except Exception as e:
        log(f"  Haiku analysis error: {e}")
        return ""


# ── Brain File Update ────────────────────────────────────────────────────────

def append_to_brain(brain_file: Path, creator_name: str, video_title: str,
                    video_url: str, analysis: str) -> bool:
    """Append a dated entry to the creator's brain file under Updates Log."""
    if not brain_file or not brain_file.exists():
        log(f"  No brain file found for {creator_name}")
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    content = brain_file.read_text(encoding="utf-8")

    # Build the entry
    entry = f"\n### Auto-Scan Update ({today}) -- {video_title}\n"
    entry += f"**Source:** [{video_title}]({video_url})\n\n"
    entry += analysis.strip() + "\n"

    # Find "Updates Log" section and append after it
    # Look for pattern: ## N. Updates Log or ## Updates Log
    updates_pattern = re.search(
        r"(## \d+\.\s*Updates Log.*?)(?=\n## \d+\.|\Z)",
        content,
        re.DOTALL,
    )

    if updates_pattern:
        insert_pos = updates_pattern.end()
        new_content = content[:insert_pos] + "\n" + entry + content[insert_pos:]
    else:
        # No Updates Log section found -- append at end
        new_content = content.rstrip() + "\n\n---\n\n## Updates Log\n" + entry

    brain_file.write_text(new_content, encoding="utf-8")
    log(f"  Updated brain file: {brain_file.name}")
    return True


# ── Main Scanner ─────────────────────────────────────────────────────────────

def scan_creator(creator: dict, state: dict, dry_run: bool = False) -> list[dict]:
    """Scan a single creator for new videos. Returns list of processed video dicts."""
    name = creator["name"]
    handle = creator.get("handle")
    channel_url = creator.get("channel_url")

    if not handle and not channel_url:
        log(f"Skipping {name} -- no YouTube handle")
        return []

    # Build list of channels to check (main + secondary)
    channels = []
    if handle:
        channels.append({"handle": handle, "url": f"https://youtube.com/@{handle}"})
        for sec in SECONDARY_CHANNELS.get(handle, []):
            channels.append({"handle": sec, "url": f"https://youtube.com/@{sec}"})
    elif channel_url:
        channels.append({"handle": name.lower().replace(" ", "-"), "url": channel_url})

    processed = []

    for ch in channels:
        ch_handle = ch["handle"]
        ch_url = ch["url"]
        log(f"Checking @{ch_handle} ({name})...")

        videos = get_latest_videos(ch_url)
        if not videos:
            log(f"  No videos found for @{ch_handle}")
            continue

        # Filter to new videos only
        seen_ids = state.get(ch_handle, [])
        new_videos = [v for v in videos if v["id"] and v["id"] not in seen_ids]

        if not new_videos:
            log(f"  No new videos for @{ch_handle} (all {len(videos)} already processed)")
            continue

        log(f"  Found {len(new_videos)} new video(s) for @{ch_handle}")

        for video in new_videos:
            vid = video["id"]
            title = video["title"]
            url = video["url"]
            upload_date = video.get("upload_date", "unknown")

            print(f"\n  NEW: [{ch_handle}] {title}")
            print(f"       URL: {url}")
            print(f"       Date: {upload_date}")

            if dry_run:
                processed.append({
                    "creator": name,
                    "handle": ch_handle,
                    "video_id": vid,
                    "title": title,
                    "url": url,
                    "status": "dry_run",
                })
                continue

            # 1. Get transcript
            log(f"  Getting transcript for: {title}")
            transcript, method = get_transcript(vid, url)

            if not transcript:
                log(f"  Could not get transcript for {vid}")
                processed.append({
                    "creator": name,
                    "handle": ch_handle,
                    "video_id": vid,
                    "title": title,
                    "url": url,
                    "status": "transcript_failed",
                })
                # Still mark as seen so we don't retry forever
                if ch_handle not in state:
                    state[ch_handle] = []
                state[ch_handle].append(vid)
                continue

            print(f"       Transcript: {method} ({len(transcript)} chars)")

            # 2. Save transcript
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            transcript_file = TMP_DIR / f"{ch_handle}-{vid}-transcript.txt"
            transcript_file.write_text(transcript, encoding="utf-8")
            log(f"  Saved transcript: {transcript_file.name}")

            # 3. Analyze with Haiku
            log(f"  Analyzing with {HAIKU_MODEL}...")
            analysis = analyze_transcript(name, title, transcript)

            if analysis:
                # 4. Save analysis
                analysis_file = TMP_DIR / f"{ch_handle}-{vid}-analysis.md"
                analysis_header = f"# Analysis: {title}\n"
                analysis_header += f"**Creator:** {name} (@{ch_handle})\n"
                analysis_header += f"**Date:** {upload_date}\n"
                analysis_header += f"**URL:** {url}\n"
                analysis_header += f"**Transcript method:** {method}\n\n---\n\n"
                analysis_file.write_text(
                    analysis_header + analysis, encoding="utf-8"
                )
                log(f"  Saved analysis: {analysis_file.name}")

                # 5. Update brain file
                append_to_brain(
                    creator.get("brain_file"),
                    name, title, url, analysis,
                )
            else:
                log("  Analysis skipped (no API key or error)")

            # 6. Mark as processed
            if ch_handle not in state:
                state[ch_handle] = []
            state[ch_handle].append(vid)

            processed.append({
                "creator": name,
                "handle": ch_handle,
                "video_id": vid,
                "title": title,
                "url": url,
                "transcript_method": method,
                "transcript_chars": len(transcript),
                "status": "processed",
            })

    return processed


def scan_all_creators(
    dry_run: bool = False,
    creator_filter: str | None = None,
) -> list[dict]:
    """Scan all (or one) creator(s) for new videos."""
    creators = parse_handles()
    state = load_state()
    all_results = []

    # Filter if requested
    if creator_filter:
        cf = creator_filter.lower().lstrip("@")
        creators = [
            c for c in creators
            if cf in (c.get("handle") or "").lower()
            or cf in c["name"].lower()
        ]
        if not creators:
            print(f"No creator found matching '{creator_filter}'")
            return []

    print(f"Scanning {len(creators)} creator(s)...")
    if dry_run:
        print("[DRY RUN] -- will only report new videos, no downloads\n")

    for creator in creators:
        results = scan_creator(creator, state, dry_run=dry_run)
        all_results.extend(results)

    # Save state (even on dry run we don't update -- only real runs mark as seen)
    if not dry_run:
        save_state(state)

    # Print summary
    print(f"\n{'='*60}")
    print("SCAN SUMMARY")
    print(f"{'='*60}")

    new_count = len(all_results)
    processed_count = sum(1 for r in all_results if r["status"] == "processed")
    failed_count = sum(1 for r in all_results if r["status"] == "transcript_failed")
    dry_count = sum(1 for r in all_results if r["status"] == "dry_run")

    if new_count == 0:
        print("No new videos found across all creators.")
    else:
        print(f"New videos found: {new_count}")
        if dry_run:
            print(f"  Dry run: {dry_count} (would process)")
        else:
            print(f"  Processed: {processed_count}")
            if failed_count:
                print(f"  Transcript failed: {failed_count}")

        print()
        for r in all_results:
            status_tag = {
                "processed": "[OK]",
                "transcript_failed": "[FAIL]",
                "dry_run": "[DRY]",
            }.get(r["status"], "[?]")

            method_info = ""
            if r.get("transcript_method"):
                method_info = f" ({r['transcript_method']}, {r.get('transcript_chars', 0)} chars)"

            print(f"  {status_tag} @{r['handle']}: {r['title']}{method_info}")

    return all_results


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scan tracked creators for new YouTube videos"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report new videos without downloading or transcribing",
    )
    parser.add_argument(
        "--creator", type=str, default=None,
        help="Scan a single creator (handle or name, e.g. niksetting)",
    )
    args = parser.parse_args()

    scan_all_creators(dry_run=args.dry_run, creator_filter=args.creator)


if __name__ == "__main__":
    main()
