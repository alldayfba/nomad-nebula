#!/usr/bin/env python3
"""
creator_youtube_scanner.py — Daily Creator YouTube Scanner

Checks all registered mentor YouTube channels for new videos since last scan.
For each new video: fetches transcript (API → Whisper fallback), then appends
a structured summary to the creator's brain file.

Usage:
  # Scan all creators for new videos
  python execution/creator_youtube_scanner.py

  # Scan a specific creator
  python execution/creator_youtube_scanner.py --creator sowei-goh

  # Force re-scan last N days
  python execution/creator_youtube_scanner.py --days 7

  # Dry run (list new videos, don't update brains)
  python execution/creator_youtube_scanner.py --dry-run

  # Initial full scrape for a new creator (all videos)
  python execution/creator_youtube_scanner.py --creator jace-england --full-scrape --max-videos 50

State file: .tmp/creators/scan-state.json (tracks last scan date per creator)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp" / "creators"
STATE_FILE = TMP_DIR / "scan-state.json"
CREATORS_DIR = PROJECT_ROOT / "bots" / "creators"
AUDIO_DIR = TMP_DIR / "audio"

# Use .venv314 yt-dlp binary if available (2026.3.13 — handles YouTube SABR enforcement)
# The .venv (Python 3.9) yt-dlp 2025.10.14 gets 403'd on downloads
YTDLP_314 = PROJECT_ROOT / ".venv314" / "bin" / "yt-dlp"
YTDLP_BIN = str(YTDLP_314) if YTDLP_314.exists() else "yt-dlp"

# Load .env
try:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Creator Registry — YouTube channels for all mentors
# ---------------------------------------------------------------------------
CREATORS = {
    "sowei-goh": {
        "name": "SoWei Goh",
        "youtube": "https://youtube.com/channel/UCZUZ5l2tyq1BrxlnKDR6CSg",
        "brain_file": "soowei-goh-brain.md",
        "focus": "organic scaling, personal branding, B2B coaching, content strategy",
    },
    "nik-setting": {
        "name": "Nik Setting",
        "youtube": "https://youtube.com/@niksetting",
        "brain_file": "nik-setting-brain.md",
        "focus": "offer positioning, IG story selling, acquisition, AI automation",
    },
    "alex-hormozi": {
        "name": "Alex Hormozi",
        "youtube": "https://youtube.com/@alexhormozi",
        "brain_file": "alex-hormozi-brain.md",
        "focus": "offer creation, scaling, gym launch, acquisition.com, $100M frameworks",
    },
    "jeremy-haynes": {
        "name": "Jeremy Haynes",
        "youtube": "https://youtube.com/@JeremyHaynesDMM",
        "brain_file": "jeremy-haynes-brain.md",
        "focus": "paid ads, VSLs, direct response marketing, agency scaling",
    },
    "johnny-mau": {
        "name": "Johnny Mau",
        "youtube": "https://youtube.com/@johnnymauu",
        "brain_file": "johnny-mau-brain.md",
        "focus": "high ticket sales, closing, B2B coaching",
    },
    "tim-luong": {
        "name": "Tim Luong",
        "youtube": "https://youtube.com/@TimothyLuong_",
        "brain_file": "tim-luong-brain.md",
        "focus": "agency scaling, client acquisition, content systems",
    },
    "pierre-khoury": {
        "name": "Pierre Khoury",
        "youtube": "https://youtube.com/@Pierre.Khoury",
        "brain_file": "pierre-khoury-brain.md",
        "focus": "coaching business, scaling, organic content",
    },
    "jace-england": {
        "name": "Jace England",
        "youtube": "https://youtube.com/@jaceengland",
        "brain_file": "jace-england-brain.md",
        "focus": "info agency, coaching scaling, real estate ads, growth systems",
    },
    "caleb-canales": {
        "name": "Caleb Canales",
        "youtube": "https://youtube.com/@calebcanales",
        "brain_file": "caleb-canales-brain.md",
        "focus": "agency building, client acquisition",
    },
    "ben-bader": {
        "name": "Ben Bader",
        "youtube": "https://youtube.com/@benbader",
        "brain_file": "ben-bader-brain.md",
        "focus": "Amazon FBA, YouTube for coaches, AI positioning, traffic",
    },
}


def log(msg: str):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# YouTube — list videos via yt-dlp
# ---------------------------------------------------------------------------
def list_youtube_videos(channel_url: str, max_videos: int = 20) -> list[dict]:
    """List recent videos from a YouTube channel."""
    try:
        import yt_dlp
    except ImportError:
        log("ERROR: pip install yt-dlp")
        return []

    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ignoreerrors": True,
    }
    if max_videos > 0:
        ydl_opts["playlistend"] = max_videos

    videos = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
            if not result:
                return []
            for entry in (result.get("entries") or []):
                if entry is None:
                    continue
                videos.append({
                    "video_id": entry.get("id", ""),
                    "title": entry.get("title", ""),
                    "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                    "duration": entry.get("duration"),
                    "view_count": entry.get("view_count"),
                    "upload_date": entry.get("upload_date"),
                })
    except Exception as e:
        log(f"ERROR listing videos: {e}")

    return videos


def fetch_video_metadata(video_id: str) -> dict:
    """Fetch full metadata for a single video (title, date, description)."""
    try:
        import yt_dlp
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            if info:
                return {
                    "title": info.get("title", ""),
                    "upload_date": info.get("upload_date"),
                    "description": (info.get("description") or "")[:500],
                    "duration": info.get("duration"),
                    "view_count": info.get("view_count"),
                }
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# Transcript — API first, then Whisper fallback
# ---------------------------------------------------------------------------
def fetch_transcript_api(video_id: str) -> Optional[str]:
    """Try youtube-transcript-api first."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
        lines = [s.text for s in transcript.snippets]
        text = " ".join(lines)
        if len(text) > 100:
            return text
    except Exception:
        pass

    # Try yt-dlp auto-subs
    try:
        import yt_dlp
        out_path = str(AUDIO_DIR / f"{video_id}")
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": ["en"],
            "subtitlesformat": "vtt",
            "outtmpl": out_path,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        for ext in [".en.vtt", ".en.auto.vtt"]:
            sub_file = Path(f"{out_path}{ext}")
            if sub_file.exists():
                raw = sub_file.read_text(encoding="utf-8")
                lines = []
                for line in raw.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                        continue
                    if re.match(r"^\d{2}:\d{2}", line) or "-->" in line or re.match(r"^\d+$", line):
                        continue
                    clean = re.sub(r"<[^>]+>", "", line)
                    if clean:
                        lines.append(clean)
                sub_file.unlink(missing_ok=True)
                deduped = []
                for ln in lines:
                    if not deduped or ln != deduped[-1]:
                        deduped.append(ln)
                text = " ".join(deduped)
                if len(text) > 100:
                    return text
    except Exception:
        pass

    return None


def fetch_transcript_whisper(video_id: str) -> Optional[str]:
    """Download audio via CLI yt-dlp (.venv314) and transcribe with faster-whisper."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = AUDIO_DIR / f"{video_id}.wav"
    mp4_path = AUDIO_DIR / f"{video_id}.mp4"

    # Download audio using the newer yt-dlp binary (handles SABR/403)
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        result = subprocess.run(
            [YTDLP_BIN, "-f", "18", "-o", str(mp4_path), url],
            capture_output=True, text=True, timeout=180,
        )
        if not mp4_path.exists():
            # Try without format constraint
            subprocess.run(
                [YTDLP_BIN, "-f", "worstaudio", "-o", str(mp4_path), url],
                capture_output=True, text=True, timeout=180,
            )

        if not mp4_path.exists():
            log(f"  Could not download audio for {video_id}")
            return None

        # Convert to WAV
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp4_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path)
        ], capture_output=True, timeout=120)

        mp4_path.unlink(missing_ok=True)

        if not audio_path.exists():
            return None
    except Exception as e:
        log(f"  Download/convert error: {e}")
        return None

    # Transcribe with faster-whisper
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path), language="en", beam_size=1)
        lines = [seg.text.strip() for seg in segments]
        audio_path.unlink(missing_ok=True)
        text = " ".join(lines)
        if len(text) > 100:
            return text
    except ImportError:
        log("  faster-whisper not installed, skipping Whisper fallback")
    except Exception as e:
        log(f"  Whisper error: {e}")

    audio_path.unlink(missing_ok=True)
    return None


def get_transcript(video_id: str) -> tuple[Optional[str], str]:
    """Get transcript using API first, then Whisper fallback. Returns (text, method)."""
    text = fetch_transcript_api(video_id)
    if text:
        return text, "api"

    log(f"  No API transcript, trying Whisper for {video_id}...")
    text = fetch_transcript_whisper(video_id)
    if text:
        return text, "whisper"

    return None, "failed"


# ---------------------------------------------------------------------------
# Brain file update — append new video findings
# ---------------------------------------------------------------------------
def summarize_transcript(creator_name: str, title: str, transcript: str, focus: str) -> Optional[str]:
    """Use Claude to extract key insights from a video transcript."""
    try:
        import anthropic
    except ImportError:
        log("ERROR: pip install anthropic")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log("ERROR: ANTHROPIC_API_KEY not set")
        return None

    # Truncate transcript if too long (keep ~15K chars for Haiku)
    max_chars = 40000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n\n[TRANSCRIPT TRUNCATED]"

    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"""Analyze this YouTube video transcript from {creator_name} and extract the key insights.

**Video Title:** {title}
**Creator Focus Areas:** {focus}

**Transcript:**
{transcript}

---

Extract and return a structured summary in this EXACT markdown format (no other text):

#### Key Frameworks/Concepts
- [List any named frameworks, mental models, or concepts introduced — with brief explanation]

#### Strategies & Tactics
- [List specific actionable strategies discussed — be concrete, include numbers/specifics when mentioned]

#### Key Quotes
- "[Any memorable/notable direct quotes]"

#### Insights for Sabbo
- [1-3 bullet points on how this specifically applies to Agency OS or Amazon OS coaching business]

Keep it concise but capture everything actionable. Skip sections if nothing relevant was discussed."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        log(f"  Claude API error: {e}")
        return None


def append_to_brain_file(creator_slug: str, video_id: str, title: str,
                         upload_date: str, summary: str, transcript_method: str):
    """Append a new video entry to the creator's brain file."""
    brain_file = CREATORS_DIR / CREATORS[creator_slug]["brain_file"]

    if not brain_file.exists():
        log(f"  Brain file not found: {brain_file}")
        return False

    content = brain_file.read_text(encoding="utf-8")

    # Update the Last Updated timestamp
    today = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(
        r"<!-- Last Updated: \d{4}-\d{2}-\d{2} -->",
        f"<!-- Last Updated: {today} -->",
        content,
    )

    # Format upload date
    if upload_date and len(upload_date) == 8:
        date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    else:
        date_str = today

    # Build the entry
    entry = f"""
### {date_str} — "{title}"
**Source:** https://www.youtube.com/watch?v={video_id}
**Transcript method:** {transcript_method}

{summary}
"""

    # Find or create Updates Log section
    if "## Updates Log" in content:
        # Insert after the Updates Log header
        idx = content.index("## Updates Log")
        # Find the end of the header line
        newline_idx = content.index("\n", idx)
        content = content[:newline_idx + 1] + entry + content[newline_idx + 1:]
    else:
        # Append Updates Log section at end
        content = content.rstrip() + "\n\n---\n\n## Updates Log\n" + entry

    brain_file.write_text(content, encoding="utf-8")
    log(f"  Updated brain file: {brain_file.name}")
    return True


# ---------------------------------------------------------------------------
# Main scan logic
# ---------------------------------------------------------------------------
def scan_creator(creator_slug: str, state: dict, days: int = 3,
                 dry_run: bool = False, full_scrape: bool = False,
                 max_videos: int = 20) -> dict:
    """Scan a single creator's YouTube for new videos."""
    creator = CREATORS[creator_slug]
    log(f"\n{'='*60}")
    log(f"Scanning: {creator['name']} ({creator_slug})")
    log(f"Channel: {creator['youtube']}")

    # Determine since date
    last_scan = state.get(creator_slug, {}).get("last_scan")
    if full_scrape:
        since_date = None
        fetch_count = max_videos
        log(f"Full scrape mode — fetching up to {fetch_count} videos")
    elif last_scan:
        since_date = last_scan
        fetch_count = max_videos
        log(f"Last scan: {last_scan} — checking for new videos")
    else:
        # First scan — look back N days
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        fetch_count = max_videos
        log(f"First scan — looking back {days} days (since {since_date})")

    # List videos
    videos = list_youtube_videos(creator["youtube"], fetch_count)
    if not videos:
        log(f"No videos found for {creator['name']}")
        return {"creator": creator_slug, "new_videos": 0, "updated": 0, "errors": 0}

    log(f"Found {len(videos)} videos listed")

    # Filter to new videos
    already_scanned = set(state.get(creator_slug, {}).get("scanned_ids", []))
    new_videos = []

    for vid in videos:
        vid_id = vid["video_id"]
        if vid_id in already_scanned and not full_scrape:
            continue

        # Check upload date if available
        if since_date and vid.get("upload_date"):
            if vid["upload_date"] < since_date:
                continue

        new_videos.append(vid)

    if not new_videos:
        log(f"No new videos for {creator['name']}")
        return {"creator": creator_slug, "new_videos": 0, "updated": 0, "errors": 0}

    log(f"{len(new_videos)} new videos to process")

    if dry_run:
        for v in new_videos:
            log(f"  [DRY RUN] Would process: {v['title'][:60]} ({v['video_id']})")
        return {"creator": creator_slug, "new_videos": len(new_videos), "updated": 0, "errors": 0}

    # Process each new video
    updated = 0
    errors = 0
    scanned_ids = list(already_scanned)

    for i, vid in enumerate(new_videos):
        vid_id = vid["video_id"]
        title = vid.get("title", "Unknown")
        log(f"\n  [{i+1}/{len(new_videos)}] Processing: {title[:60]}")

        # Get metadata if missing
        if not vid.get("upload_date"):
            meta = fetch_video_metadata(vid_id)
            vid.update(meta)

        # Get transcript
        transcript, method = get_transcript(vid_id)
        if not transcript:
            log(f"  FAILED: No transcript for {vid_id}")
            errors += 1
            scanned_ids.append(vid_id)  # Don't retry
            continue

        log(f"  Transcript: {len(transcript)} chars via {method}")

        # Save raw transcript to disk for later use
        transcript_file = TMP_DIR / f"{creator_slug}-{vid_id}-transcript.txt"
        transcript_file.write_text(transcript, encoding="utf-8")
        log(f"  Saved transcript: {transcript_file.name}")

        # Summarize with Claude
        summary = summarize_transcript(
            creator["name"], title, transcript, creator["focus"]
        )
        if not summary:
            log(f"  WARNING: Could not summarize {vid_id} (transcript saved, summary skipped)")
            # Still count as success — transcript is saved
            scanned_ids.append(vid_id)
            errors += 1
            continue

        # Append to brain file
        success = append_to_brain_file(
            creator_slug, vid_id, title,
            vid.get("upload_date", ""), summary, method
        )
        if success:
            updated += 1
        else:
            errors += 1

        scanned_ids.append(vid_id)
        time.sleep(1)  # Rate limit

    # Update state
    state[creator_slug] = {
        "last_scan": datetime.now().strftime("%Y%m%d"),
        "scanned_ids": scanned_ids[-500:],  # Keep last 500 IDs
        "last_updated": datetime.now().isoformat(),
        "total_scanned": len(scanned_ids),
    }

    log(f"\nDone: {creator['name']} — {updated} updated, {errors} errors")
    return {"creator": creator_slug, "new_videos": len(new_videos), "updated": updated, "errors": errors}


# ---------------------------------------------------------------------------
# Initial brain file creation for new creators
# ---------------------------------------------------------------------------
def create_initial_brain_file(creator_slug: str):
    """Create a starter brain file for a new creator."""
    creator = CREATORS[creator_slug]
    brain_path = CREATORS_DIR / creator["brain_file"]

    if brain_path.exists():
        log(f"Brain file already exists: {brain_path}")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    content = f"""<!-- Last Updated: {today} -->
<!-- Sources: YouTube -->
# {creator['name']} — Creator Intelligence Report
> Auto-generated by creator_youtube_scanner.py
> Generated: {today}

---

## Overview

**Name:** {creator['name']}
**Focus Areas:** {creator['focus']}
**YouTube:** {creator['youtube']}

---

## Updates Log
"""
    brain_path.write_text(content, encoding="utf-8")
    log(f"Created brain file: {brain_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Daily Creator YouTube Scanner")
    parser.add_argument("--creator", help="Scan specific creator (slug)")
    parser.add_argument("--days", type=int, default=3, help="Look back N days on first scan (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="List new videos without processing")
    parser.add_argument("--full-scrape", action="store_true", help="Full scrape (ignore last scan date)")
    parser.add_argument("--max-videos", type=int, default=20, help="Max videos to list per channel (default: 20)")
    parser.add_argument("--list-creators", action="store_true", help="List registered creators")
    args = parser.parse_args()

    if args.list_creators:
        print("\nRegistered creators:")
        for slug, info in CREATORS.items():
            print(f"  {slug:20s} → {info['name']:20s} | {info['youtube']}")
        return

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    state = load_state()

    # Determine which creators to scan
    if args.creator:
        if args.creator not in CREATORS:
            print(f"ERROR: Unknown creator '{args.creator}'. Use --list-creators to see options.")
            sys.exit(1)
        slugs = [args.creator]
    else:
        slugs = list(CREATORS.keys())

    log(f"Creator YouTube Scanner — {len(slugs)} creator(s) to scan")
    log(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")

    results = []
    for slug in slugs:
        # Create brain file if it doesn't exist
        brain_path = CREATORS_DIR / CREATORS[slug]["brain_file"]
        if not brain_path.exists():
            create_initial_brain_file(slug)

        result = scan_creator(
            slug, state, days=args.days, dry_run=args.dry_run,
            full_scrape=args.full_scrape, max_videos=args.max_videos
        )
        results.append(result)
        save_state(state)  # Save after each creator in case of crash

    # Summary
    log(f"\n{'='*60}")
    log("SCAN COMPLETE")
    total_new = sum(r["new_videos"] for r in results)
    total_updated = sum(r["updated"] for r in results)
    total_errors = sum(r["errors"] for r in results)
    log(f"  Creators scanned: {len(results)}")
    log(f"  New videos found: {total_new}")
    log(f"  Brain files updated: {total_updated}")
    log(f"  Errors: {total_errors}")

    # Output JSON summary
    print(json.dumps({
        "scan_date": datetime.now().isoformat(),
        "creators_scanned": len(results),
        "total_new_videos": total_new,
        "total_updated": total_updated,
        "total_errors": total_errors,
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
