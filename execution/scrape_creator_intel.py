#!/usr/bin/env python3
"""
scrape_creator_intel.py — Creator Intelligence Scraper
Pulls ALL videos + transcripts from a YouTube channel and/or Instagram Reels.
Outputs structured JSON to .tmp/creators/{name}-raw.json.

Usage:
  python execution/scrape_creator_intel.py \
    --name "nik-setting" \
    --youtube "https://youtube.com/@niksetting" \
    --instagram "niksetting" \
    --max-videos 100

Dependencies (all pre-installed):
  yt-dlp, youtube-transcript-api, playwright, ffmpeg (system)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        CouldNotRetrieveTranscript,
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ImportError:
    print("ERROR: pip install youtube-transcript-api", file=sys.stderr)
    sys.exit(1)

try:
    import yt_dlp
except ImportError:
    print("ERROR: pip install yt-dlp", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DELAY_BETWEEN_TRANSCRIPTS = 1.0  # seconds between transcript API calls
DELAY_BETWEEN_REELS = 3.0  # seconds between Instagram reel downloads
TMP_DIR = Path(".tmp/creators")
AUDIO_DIR = TMP_DIR / "audio"


def log(msg):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# YouTube — List all videos from a channel
# ---------------------------------------------------------------------------
def list_youtube_videos(channel_url: str, max_videos: int = 0) -> list[dict]:
    """Use yt-dlp to list all video IDs, titles, durations from a channel."""
    log(f"Listing videos from: {channel_url}")

    # Ensure we're hitting the videos tab
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
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=False)
        if not result:
            log("ERROR: Could not extract channel info")
            return []

        entries = result.get("entries", []) or []
        for entry in entries:
            if entry is None:
                continue
            vid = {
                "video_id": entry.get("id", ""),
                "title": entry.get("title", ""),
                "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                "duration": entry.get("duration"),
                "view_count": entry.get("view_count"),
                "upload_date": entry.get("upload_date"),
            }
            videos.append(vid)

    log(f"Found {len(videos)} videos")
    return videos


# ---------------------------------------------------------------------------
# YouTube — Pull transcript for a single video
# ---------------------------------------------------------------------------
def fetch_youtube_transcript(video_id: str) -> dict:
    """Try youtube-transcript-api first, then yt-dlp subtitle extraction as fallback."""

    # Method 1: youtube-transcript-api (fast, no download)
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
        lines = []
        for snippet in transcript.snippets:
            lines.append(snippet.text)
        full_text = " ".join(lines)
        return {"method": "youtube-transcript-api", "text": full_text, "error": None}
    except (CouldNotRetrieveTranscript, NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as e:
        pass
    except Exception as e:
        pass

    # Method 2: yt-dlp auto-sub extraction
    try:
        out_path = str(AUDIO_DIR / f"{video_id}")
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

        # Check for subtitle file
        for ext in [".en.vtt", ".en.auto.vtt"]:
            sub_file = Path(f"{out_path}{ext}")
            if sub_file.exists():
                raw = sub_file.read_text(encoding="utf-8")
                # Strip VTT headers and timestamps, keep text
                lines = []
                for line in raw.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                        continue
                    if re.match(r"^\d{2}:\d{2}", line) or line == "-->" or "-->" in line:
                        continue
                    if re.match(r"^\d+$", line):
                        continue
                    # Strip VTT tags
                    clean = re.sub(r"<[^>]+>", "", line)
                    if clean:
                        lines.append(clean)
                sub_file.unlink(missing_ok=True)
                # Deduplicate consecutive duplicate lines (VTT often repeats)
                deduped = []
                for ln in lines:
                    if not deduped or ln != deduped[-1]:
                        deduped.append(ln)
                return {"method": "yt-dlp-autosub", "text": " ".join(deduped), "error": None}

        return {"method": None, "text": "", "error": "no_captions_available"}
    except Exception as e:
        return {"method": None, "text": "", "error": str(e)}


# ---------------------------------------------------------------------------
# YouTube — Full pipeline: list + transcribe
# ---------------------------------------------------------------------------
def _fetch_video_upload_date(video_id: str) -> Optional[str]:
    """Fetch upload_date for a single video via yt-dlp metadata (no download)."""
    try:
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return info.get("upload_date") if info else None
    except Exception:
        return None


def scrape_youtube_channel(channel_url: str, max_videos: int = 0, since: Optional[str] = None) -> dict:
    """Scrape all videos + transcripts from a YouTube channel."""
    videos = list_youtube_videos(channel_url, max_videos)

    results = []
    success = 0
    failed = 0
    skipped_date = 0

    for i, vid in enumerate(videos):
        video_id = vid["video_id"]
        title = vid.get("title", "Unknown")

        # Fetch upload_date if not already present (flat extraction often misses it)
        if not vid.get("upload_date") and since:
            log(f"[{i+1}/{len(videos)}] Fetching date for: {title[:50]}...")
            vid["upload_date"] = _fetch_video_upload_date(video_id)

        # Date filter: skip videos older than --since cutoff
        if since and vid.get("upload_date"):
            if vid["upload_date"] < since:
                log(f"[{i+1}/{len(videos)}] SKIP (before {since}): {title[:50]} ({vid['upload_date']})")
                skipped_date += 1
                # Videos are newest-first — once we hit an old one, the rest are older
                log(f"Hit date boundary. Skipping remaining {len(videos) - i - 1} older videos.")
                break

        log(f"[{i+1}/{len(videos)}] Transcribing: {title[:60]}...")

        transcript = fetch_youtube_transcript(video_id)

        vid["transcript"] = transcript["text"]
        vid["transcript_method"] = transcript["method"]
        vid["transcript_error"] = transcript["error"]
        vid["transcript_length"] = len(transcript["text"])

        if transcript["text"]:
            success += 1
        else:
            failed += 1

        results.append(vid)
        if i < len(videos) - 1:
            time.sleep(DELAY_BETWEEN_TRANSCRIPTS)

    log(f"YouTube done: {success} transcripts pulled, {failed} failed, {skipped_date} skipped (date), {len(videos)} total")
    return {
        "channel_url": channel_url,
        "total_videos": len(results),
        "total_listed": len(videos),
        "skipped_date_filter": skipped_date,
        "transcripts_success": success,
        "transcripts_failed": failed,
        "videos": results,
    }


# ---------------------------------------------------------------------------
# Instagram — List Reels from a profile
# ---------------------------------------------------------------------------
def list_instagram_reels(handle: str, max_reels: int = 50) -> list[dict]:
    """Use yt-dlp to list Instagram reels from a profile's reels tab."""
    log(f"Listing Instagram reels for: @{handle}")

    reels_url = f"https://www.instagram.com/{handle}/reels/"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "ignoreerrors": True,
        "playlistend": max_reels,
    }

    reels = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(reels_url, download=False)
            if not result:
                log("yt-dlp returned no results for Instagram. Trying Playwright fallback...")
                return _list_instagram_reels_playwright(handle, max_reels)

            entries = result.get("entries", []) or []
            for entry in entries:
                if entry is None:
                    continue
                reels.append({
                    "reel_id": entry.get("id", ""),
                    "url": entry.get("url", ""),
                    "title": entry.get("title", ""),
                    "duration": entry.get("duration"),
                    "upload_date": entry.get("upload_date"),
                })
    except Exception as e:
        log(f"yt-dlp Instagram failed: {e}. Trying Playwright fallback...")
        return _list_instagram_reels_playwright(handle, max_reels)

    if not reels:
        log("yt-dlp returned 0 reels. Trying Playwright fallback...")
        return _list_instagram_reels_playwright(handle, max_reels)

    log(f"Found {len(reels)} reels via yt-dlp")
    return reels


def _list_instagram_reels_playwright(handle: str, max_reels: int = 50) -> list[dict]:
    """Fallback: use Playwright to scrape reel URLs from the profile page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Playwright not available for fallback")
        return []

    log(f"Playwright fallback: scraping @{handle}/reels/")
    reels = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
            )
            page = context.new_page()
            page.goto(f"https://www.instagram.com/{handle}/reels/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)

            # Scroll to load more reels
            for _ in range(min(5, max_reels // 12 + 1)):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

            html = page.content()
            browser.close()

        # Extract reel URLs from the page
        reel_urls = re.findall(r'href="(/reel/[A-Za-z0-9_-]+/)"', html)
        seen = set()
        for url_path in reel_urls:
            if url_path in seen:
                continue
            seen.add(url_path)
            reel_id = url_path.strip("/").split("/")[-1]
            reels.append({
                "reel_id": reel_id,
                "url": f"https://www.instagram.com{url_path}",
                "title": "",
                "duration": None,
                "upload_date": None,
            })
            if len(reels) >= max_reels:
                break

        log(f"Found {len(reels)} reels via Playwright")
    except Exception as e:
        log(f"Playwright Instagram fallback failed: {e}")

    return reels


# ---------------------------------------------------------------------------
# Instagram — Transcribe a single Reel
# ---------------------------------------------------------------------------
def transcribe_instagram_reel(reel_url: str, reel_id: str) -> dict:
    """Download reel audio, transcribe it. Returns transcript text."""

    audio_path = AUDIO_DIR / f"{reel_id}.mp3"
    video_path = AUDIO_DIR / f"{reel_id}.mp4"

    # Method 1: Try yt-dlp subtitles first (fastest, no download needed)
    try:
        sub_path = str(AUDIO_DIR / reel_id)
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": ["en"],
            "subtitlesformat": "vtt",
            "outtmpl": sub_path,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([reel_url])

        for ext in [".en.vtt", ".en.auto.vtt"]:
            sub_file = Path(f"{sub_path}{ext}")
            if sub_file.exists():
                raw = sub_file.read_text(encoding="utf-8")
                lines = []
                for line in raw.split("\n"):
                    line = line.strip()
                    if not line or "-->" in line or re.match(r"^\d+$", line):
                        continue
                    if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
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
                if text.strip():
                    return {"method": "yt-dlp-autosub", "text": text, "error": None}
    except Exception:
        pass

    # Method 2: Download video → extract audio → transcribe with Whisper API or Claude
    try:
        # Download video
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": str(video_path),
            "format": "worst[ext=mp4]/worst",  # smallest file for audio extraction
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([reel_url])

        if not video_path.exists():
            return {"method": None, "text": "", "error": "download_failed"}

        # Extract audio with ffmpeg
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(video_path), "-q:a", "0", "-map", "a", str(audio_path)],
                capture_output=True,
                timeout=30,
            )
        except Exception as e:
            print(f"[CQ-004] ffmpeg subprocess failed: {e}")
            video_path.unlink(missing_ok=True)
            return {"method": None, "text": "", "error": f"ffmpeg_failed: {e}"}

        # Clean up video immediately
        video_path.unlink(missing_ok=True)

        if not audio_path.exists():
            return {"method": None, "text": "", "error": "audio_extraction_failed"}

        # Try Whisper API first (if openai is installed)
        transcript_text = _transcribe_with_whisper(audio_path)
        if transcript_text:
            audio_path.unlink(missing_ok=True)
            return {"method": "whisper", "text": transcript_text, "error": None}

        # Fallback: Claude API with audio (if supported and file is small enough)
        transcript_text = _transcribe_with_claude(audio_path)
        if transcript_text:
            audio_path.unlink(missing_ok=True)
            return {"method": "claude", "text": transcript_text, "error": None}

        audio_path.unlink(missing_ok=True)
        return {"method": None, "text": "", "error": "no_transcription_method_available"}

    except Exception as e:
        # Clean up
        video_path.unlink(missing_ok=True)
        audio_path.unlink(missing_ok=True)
        return {"method": None, "text": "", "error": str(e)}


def _transcribe_with_whisper(audio_path: Path) -> str:
    """Try OpenAI Whisper API for transcription."""
    try:
        from openai import OpenAI
        client = OpenAI()  # Uses OPENAI_API_KEY env var
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(model="whisper-1", file=f)
        return result.text
    except ImportError:
        return ""
    except Exception as e:
        log(f"Whisper transcription failed: {e}")
        return ""


def _transcribe_with_claude(audio_path: Path) -> str:
    """Try Claude API for audio transcription (via base64 audio input)."""
    try:
        import anthropic
        import base64

        # Claude supports audio input — encode as base64
        file_size = audio_path.stat().st_size
        if file_size > 25 * 1024 * 1024:  # 25MB limit
            log(f"Audio file too large for Claude ({file_size / 1024 / 1024:.1f}MB)")
            return ""

        with open(audio_path, "rb") as f:
            audio_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Use Haiku for transcription (cost-efficient)
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "audio/mpeg",
                            "data": audio_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Transcribe this audio word for word. Output ONLY the transcription, no commentary."
                    }
                ]
            }]
        )
        return response.content[0].text.strip()
    except ImportError:
        return ""
    except Exception as e:
        log(f"Claude transcription failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Instagram — Full pipeline: list + transcribe
# ---------------------------------------------------------------------------
def scrape_instagram_reels(handle: str, max_reels: int = 50) -> dict:
    """Scrape all reels + transcripts from an Instagram profile."""
    reels = list_instagram_reels(handle, max_reels)

    results = []
    success = 0
    failed = 0

    for i, reel in enumerate(reels):
        reel_id = reel["reel_id"]
        reel_url = reel["url"]
        log(f"[{i+1}/{len(reels)}] Transcribing reel: {reel_id}...")

        transcript = transcribe_instagram_reel(reel_url, reel_id)

        reel["transcript"] = transcript["text"]
        reel["transcript_method"] = transcript["method"]
        reel["transcript_error"] = transcript["error"]
        reel["transcript_length"] = len(transcript["text"])

        if transcript["text"]:
            success += 1
        else:
            failed += 1

        results.append(reel)
        if i < len(reels) - 1:
            time.sleep(DELAY_BETWEEN_REELS)

    log(f"Instagram done: {success} transcripts pulled, {failed} failed, {len(reels)} total")
    return {
        "handle": handle,
        "total_reels": len(reels),
        "transcripts_success": success,
        "transcripts_failed": failed,
        "reels": results,
    }


# ---------------------------------------------------------------------------
# Instagram — Scrape post captions (lightweight, always works)
# ---------------------------------------------------------------------------
def scrape_instagram_captions(handle: str) -> list[str]:
    """Quick scrape of Instagram post captions via Playwright (no video download)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    log(f"Scraping Instagram captions for @{handle}...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
            )
            page = context.new_page()
            page.goto(f"https://www.instagram.com/{handle}/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()

        captions = re.findall(r'"text"\s*:\s*"([^"]{20,1000})"', html)
        log(f"Found {len(captions)} captions")
        return captions[:50]
    except Exception as e:
        log(f"Caption scrape failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Scrape creator content for intelligence extraction")
    parser.add_argument("--name", required=True, help="Creator slug (e.g. 'nik-setting')")
    parser.add_argument("--youtube", default=None, help="YouTube channel URL")
    parser.add_argument("--instagram", default=None, help="Instagram handle (without @)")
    parser.add_argument("--max-videos", type=int, default=0, help="Max YouTube videos (0 = all)")
    parser.add_argument("--max-reels", type=int, default=50, help="Max Instagram reels (default 50)")
    parser.add_argument("--skip-ig-video", action="store_true", help="Skip Instagram video download, only get captions")
    parser.add_argument("--since", default=None, help="Only include videos uploaded on or after this date (YYYYMMDD)")
    return parser.parse_args()


def main():
    args = parse_args()

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    output_path = TMP_DIR / f"{args.name}-raw.json"

    log(f"=== Creator Intelligence Scrape: {args.name} ===")
    start_time = time.time()

    result = {
        "creator_slug": args.name,
        "scraped_at": datetime.now().isoformat(),
        "youtube": None,
        "instagram": None,
    }

    if args.youtube:
        result["youtube"] = scrape_youtube_channel(args.youtube, args.max_videos, args.since)

    if args.instagram:
        if args.skip_ig_video:
            captions = scrape_instagram_captions(args.instagram)
            result["instagram"] = {
                "handle": args.instagram,
                "total_reels": 0,
                "transcripts_success": 0,
                "transcripts_failed": 0,
                "reels": [],
                "captions": captions,
            }
        else:
            ig_result = scrape_instagram_reels(args.instagram, args.max_reels)
            ig_result["captions"] = scrape_instagram_captions(args.instagram)
            result["instagram"] = ig_result

    if not any([args.youtube, args.instagram]):
        print("ERROR: Provide at least --youtube or --instagram", file=sys.stderr)
        sys.exit(1)

    # Save output
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - start_time
    log(f"=== Done in {elapsed:.0f}s. Output: {output_path} ===")

    # Print summary
    yt = result.get("youtube") or {}
    ig = result.get("instagram") or {}
    total_content = (yt.get("transcripts_success", 0) + ig.get("transcripts_success", 0))
    total_words = 0
    for v in (yt.get("videos") or []):
        total_words += len(v.get("transcript", "").split())
    for r in (ig.get("reels") or []):
        total_words += len(r.get("transcript", "").split())

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"SUMMARY: {args.name}", file=sys.stderr)
    print(f"  YouTube: {yt.get('transcripts_success', 0)}/{yt.get('total_videos', 0)} transcripts", file=sys.stderr)
    print(f"  Instagram: {ig.get('transcripts_success', 0)}/{ig.get('total_reels', 0)} reel transcripts + {len(ig.get('captions', []))} captions", file=sys.stderr)
    print(f"  Total words: ~{total_words:,}", file=sys.stderr)
    print(f"  Output: {output_path}", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)

    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
