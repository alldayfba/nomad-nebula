#!/usr/bin/env python3
"""
voice_memo_generator.py — Generate personalized voice memos via Eleven Labs.

Clones a voice and generates personalized audio messages for outreach follow-ups.
Based on Kabrin's Eleven Labs + ManyChat voice memo pattern.

Usage:
    # Generate a voice memo
    python execution/voice_memo_generator.py generate \
        --text "Hey John, just wanted to follow up on the growth system I sent over..." \
        --voice-id "your_cloned_voice_id" \
        --output .tmp/voice-memos/john-followup.mp3

    # Clone a voice from audio samples
    python execution/voice_memo_generator.py clone \
        --name "Sabbo" \
        --files audio1.mp3 audio2.mp3

    # List available voices
    python execution/voice_memo_generator.py list-voices

    # Batch generate from CSV
    python execution/voice_memo_generator.py batch \
        --csv .tmp/leads/follow-ups.csv \
        --template "Hey {name}, just built you a complete {offer} system..."
        --voice-id "your_voice_id"

    # Programmatic:
    from execution.voice_memo_generator import generate_voice_memo
    path = generate_voice_memo("Hey John...", voice_id="abc123")
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
BASE_URL = "https://api.elevenlabs.io/v1"
OUTPUT_DIR = Path(__file__).parent.parent / ".tmp" / "voice-memos"


def _headers():
    return {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }


def list_voices():
    """List all available Eleven Labs voices."""
    if not ELEVENLABS_API_KEY:
        return {"error": "ELEVENLABS_API_KEY not set in .env"}

    try:
        import requests
        resp = requests.get("{}/voices".format(BASE_URL), headers=_headers(), timeout=10)
        if resp.status_code != 200:
            return {"error": "API error: {}".format(resp.status_code)}

        voices = resp.json().get("voices", [])
        return {
            "count": len(voices),
            "voices": [
                {
                    "voice_id": v["voice_id"],
                    "name": v["name"],
                    "category": v.get("category", "unknown"),
                }
                for v in voices
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def clone_voice(name, audio_files):
    """Clone a voice from audio samples."""
    if not ELEVENLABS_API_KEY:
        return {"error": "ELEVENLABS_API_KEY not set in .env"}

    try:
        import requests

        files = []
        for f in audio_files:
            fp = Path(f)
            if not fp.exists():
                return {"error": "File not found: {}".format(f)}
            files.append(("files", (fp.name, open(fp, "rb"), "audio/mpeg")))

        resp = requests.post(
            "{}/voices/add".format(BASE_URL),
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            data={"name": name, "description": "Cloned voice for outreach"},
            files=files,
            timeout=60,
        )

        # Close file handles
        for _, (_, fh, _) in files:
            fh.close()

        if resp.status_code != 200:
            return {"error": "Clone failed: {} {}".format(resp.status_code, resp.text[:200])}

        voice_id = resp.json().get("voice_id")
        return {"voice_id": voice_id, "name": name, "status": "cloned"}
    except Exception as e:
        return {"error": str(e)}


def generate_voice_memo(text, voice_id=None, output_path=None, stability=0.5, clarity=0.75):
    """Generate a voice memo from text."""
    if not ELEVENLABS_API_KEY:
        return {"error": "ELEVENLABS_API_KEY not set in .env"}

    vid = voice_id or DEFAULT_VOICE_ID
    if not vid:
        return {"error": "No voice_id provided and ELEVENLABS_VOICE_ID not set"}

    try:
        import requests

        url = "{}/text-to-speech/{}".format(BASE_URL, vid)
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": stability,
                "similarity_boost": clarity,
            },
        }

        resp = requests.post(url, json=payload, headers=_headers(), timeout=30)

        if resp.status_code != 200:
            return {"error": "TTS failed: {} {}".format(resp.status_code, resp.text[:200])}

        # Save audio
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if not output_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = OUTPUT_DIR / "memo_{}.mp3".format(ts)
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_bytes(resp.content)

        return {
            "status": "generated",
            "output_path": str(output_path),
            "text_length": len(text),
            "file_size_kb": round(len(resp.content) / 1024, 1),
        }
    except Exception as e:
        return {"error": str(e)}


def batch_generate(csv_path, template, voice_id=None):
    """Batch generate voice memos from a CSV with personalization."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return {"error": "CSV not found: {}".format(csv_path)}

    results = []
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            name = row.get("name", row.get("contact_name", "there"))
            company = row.get("company", row.get("company_name", ""))
            offer = row.get("offer", "growth")

            text = template.replace("{name}", name.split()[0] if name else "there")
            text = text.replace("{company}", company)
            text = text.replace("{offer}", offer)

            slug = name.lower().replace(" ", "-")[:30] if name else "prospect-{}".format(i)
            out_path = OUTPUT_DIR / "{}.mp3".format(slug)

            result = generate_voice_memo(text, voice_id, out_path)
            result["prospect"] = name
            results.append(result)

    return {"total": len(results), "results": results}


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate personalized voice memos via Eleven Labs")
    sub = parser.add_subparsers(dest="command")

    # generate
    p_gen = sub.add_parser("generate", help="Generate a single voice memo")
    p_gen.add_argument("--text", required=True)
    p_gen.add_argument("--voice-id")
    p_gen.add_argument("--output")

    # clone
    p_clone = sub.add_parser("clone", help="Clone a voice from audio files")
    p_clone.add_argument("--name", required=True)
    p_clone.add_argument("--files", nargs="+", required=True)

    # list-voices
    sub.add_parser("list-voices", help="List available voices")

    # batch
    p_batch = sub.add_parser("batch", help="Batch generate from CSV")
    p_batch.add_argument("--csv", required=True)
    p_batch.add_argument("--template", required=True)
    p_batch.add_argument("--voice-id")

    args = parser.parse_args()

    if args.command == "generate":
        result = generate_voice_memo(args.text, args.voice_id, args.output)
        if "error" in result:
            print("ERROR: {}".format(result["error"]))
            sys.exit(1)
        print("Generated: {}".format(result["output_path"]))

    elif args.command == "clone":
        result = clone_voice(args.name, args.files)
        if "error" in result:
            print("ERROR: {}".format(result["error"]))
            sys.exit(1)
        print("Voice cloned: {} (ID: {})".format(result["name"], result["voice_id"]))

    elif args.command == "list-voices":
        result = list_voices()
        if "error" in result:
            print("ERROR: {}".format(result["error"]))
            sys.exit(1)
        for v in result["voices"]:
            print("  {} — {} ({})".format(v["voice_id"][:12], v["name"], v["category"]))

    elif args.command == "batch":
        result = batch_generate(args.csv, args.template, args.voice_id)
        if "error" in result:
            print("ERROR: {}".format(result["error"]))
            sys.exit(1)
        ok = sum(1 for r in result["results"] if r.get("status") == "generated")
        print("Generated {}/{} voice memos".format(ok, result["total"]))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
