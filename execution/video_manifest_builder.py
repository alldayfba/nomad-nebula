#!/usr/bin/env python3
"""
Video Manifest Builder — Convert simple editing instructions into a full JSON manifest.

Bridges the gap between human-readable instructions (cut timestamps, add captions,
color grade) and the structured JSON manifest that video_editor.py expects.

Usage:
    python video_manifest_builder.py \
        --input video.mp4 \
        --name "my-project" \
        --cuts "0:00-1:30, 3:00-5:15, 8:00-12:00" \
        --speed 1.0 \
        --captions auto \
        --caption-style capcut_pop \
        --color-grade warm_cinematic \
        --music background.mp3 \
        --music-volume 0.15 \
        --normalize \
        --subscribe-button 15.0 \
        --lower-third "Sabbo|Amazon FBA Coach|3.0" \
        --output manifest.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FFPROBE = shutil.which("ffprobe") or "ffprobe"
TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp" / "video-edits"

VALID_CAPTION_STYLES = [
    "capcut_pop", "subtitle_bar", "karaoke", "minimal", "bold_outline",
]

VALID_COLOR_PRESETS = [
    "warm_cinematic", "cool_moody", "vibrant", "desaturated", "orange_teal",
]

DEFAULT_CODEC = "libx264"
DEFAULT_FPS = 30
DEFAULT_RESOLUTION = (1920, 1080)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ts_to_seconds(ts: str) -> float:
    """Convert a timestamp string to seconds.

    Accepts "M:SS" or "H:MM:SS" formats.

    Examples:
        "1:30"    -> 90.0
        "0:00"    -> 0.0
        "1:05:30" -> 3930.0
    """
    ts = ts.strip()
    parts = ts.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60 + float(seconds)
    elif len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    else:
        raise ValueError(f"Invalid timestamp format: {ts!r} (expected M:SS or H:MM:SS)")


def parse_cuts(cuts_str: str) -> List[Tuple[float, float]]:
    """Parse a cuts string into a list of (start, end) tuples in seconds.

    Input format: "0:00-1:30, 3:00-5:15, 8:00-12:00"
    Output: [(0.0, 90.0), (180.0, 315.0), (480.0, 720.0)]
    """
    cuts = []  # type: List[Tuple[float, float]]
    for segment in cuts_str.split(","):
        segment = segment.strip()
        if not segment:
            continue
        if "-" not in segment:
            raise ValueError(f"Cut segment missing '-' separator: {segment!r}")
        # Split on first '-' only would break H:MM:SS-H:MM:SS, so split smartly
        # Strategy: find the '-' that separates two timestamps (not inside a timestamp)
        # Timestamps use ':' so we split by '-' and rejoin if needed
        parts = segment.split("-")
        if len(parts) == 2:
            start_ts, end_ts = parts
        elif len(parts) == 4:
            # H:MM:SS-H:MM:SS won't hit this, but M:SS-M:SS with all single
            # digits also won't. This handles edge cases like negative...
            # Actually for "0:00-1:30" we get ["0:00", "1:30"] which is 2 parts.
            # For "1:05:30-2:10:00" we get ["1:05:30", "2:10:00"] which is 2 parts.
            # So len > 2 shouldn't happen with valid timestamps.
            raise ValueError(f"Ambiguous cut segment: {segment!r}")
        else:
            raise ValueError(f"Invalid cut segment: {segment!r}")

        start = ts_to_seconds(start_ts)
        end = ts_to_seconds(end_ts)
        if end <= start:
            raise ValueError(f"Cut end ({end_ts}) must be after start ({start_ts})")
        cuts.append((start, end))
    return cuts


def probe_video(input_path: str) -> Dict[str, Any]:
    """Probe a video file with ffprobe and return key metadata.

    Returns dict with keys: width, height, fps, duration, has_audio.
    Falls back to sensible defaults if ffprobe is unavailable.
    """
    try:
        cmd = [
            FFPROBE, "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(input_path),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=30,
        )
        info = json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        print(f"  WARNING: ffprobe failed ({exc}), using defaults")
        return {
            "width": DEFAULT_RESOLUTION[0],
            "height": DEFAULT_RESOLUTION[1],
            "fps": DEFAULT_FPS,
            "duration": 0.0,
            "has_audio": True,
        }

    video_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    audio_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "audio"),
        None,
    )
    fmt = info.get("format", {})

    meta = {
        "width": DEFAULT_RESOLUTION[0],
        "height": DEFAULT_RESOLUTION[1],
        "fps": DEFAULT_FPS,
        "duration": float(fmt.get("duration", 0)),
        "has_audio": audio_stream is not None,
    }  # type: Dict[str, Any]

    if video_stream:
        meta["width"] = int(video_stream.get("width", DEFAULT_RESOLUTION[0]))
        meta["height"] = int(video_stream.get("height", DEFAULT_RESOLUTION[1]))
        rfr = video_stream.get("r_frame_rate", "30/1")
        if "/" in rfr:
            num, den = rfr.split("/")
            meta["fps"] = round(int(num) / max(int(den), 1), 2)
        else:
            meta["fps"] = float(rfr)

    return meta


def build_manifest(
    input_path: str,
    name: Optional[str] = None,
    cuts: Optional[str] = None,
    speed: float = 1.0,
    captions: Optional[str] = None,
    caption_style: Optional[str] = None,
    color_grade: Optional[str] = None,
    music_path: Optional[str] = None,
    music_volume: float = 0.15,
    normalize: bool = False,
    subscribe_button_time: Optional[float] = None,
    lower_third_str: Optional[str] = None,
    output_codec: str = DEFAULT_CODEC,
) -> Dict[str, Any]:
    """Build a complete video editor manifest dict.

    Args:
        input_path: Path to the source video file.
        name: Project name (defaults to input filename stem).
        cuts: Comma-separated cut ranges, e.g. "0:00-1:30, 3:00-5:15".
        speed: Playback speed multiplier (1.0 = normal).
        captions: Caption mode ("auto" or None).
        caption_style: Caption visual style (e.g. "capcut_pop").
        color_grade: Color grading preset name.
        music_path: Path to background music file.
        music_volume: Music volume (0.0-1.0).
        normalize: Whether to normalize audio loudness.
        subscribe_button_time: Timestamp (seconds) to show subscribe button overlay.
        lower_third_str: Lower third overlay in "Name|Title|start_time" format.
        output_codec: FFmpeg output codec.

    Returns:
        Complete manifest dict matching video_editor.py schema.
    """
    input_abs = str(Path(input_path).resolve())
    if name is None:
        name = Path(input_path).stem

    # Probe video for metadata
    meta = probe_video(input_abs)
    resolution = [meta["width"], meta["height"]]
    fps = meta["fps"]
    duration = meta["duration"]

    project_dir = TMP_ROOT / name
    output_path = str(project_dir / "output.mp4")

    # --- Project ---
    manifest = {
        "version": "1.0",
        "project": {
            "name": name,
            "resolution": resolution,
            "fps": fps,
            "output_format": "mp4",
            "output_codec": output_codec,
            "output_path": output_path,
        },
        "sources": {
            "main": {"path": input_abs, "type": "video"},
        },
        "timeline": [],
        "effects": {},
        "overlays": [],
    }  # type: Dict[str, Any]

    # --- Music source ---
    if music_path:
        manifest["sources"]["music"] = {
            "path": str(Path(music_path).resolve()),
            "type": "audio",
        }

    # --- Timeline clips ---
    cut_ranges = []  # type: List[Tuple[float, float]]
    if cuts:
        cut_ranges = parse_cuts(cuts)
    else:
        # Single clip covering the whole video
        if duration > 0:
            cut_ranges = [(0.0, duration)]
        else:
            # Duration unknown (ffprobe failed), create a placeholder
            cut_ranges = [(0.0, 0.0)]

    effects_dict = {}  # type: Dict[str, Any]
    timeline = []  # type: List[Dict[str, Any]]

    for i, (start, end) in enumerate(cut_ranges):
        clip_id = "clip_%d" % i
        clip = {
            "id": clip_id,
            "source": "main",
            "in": start,
            "out": end,
            "speed": speed,
            "effects": [],
            "audio": {"volume": 1.0},
        }  # type: Dict[str, Any]

        # Fade in on first clip
        if i == 0:
            fade_key = "fade_in_0"
            clip["effects"].append(fade_key)
            effects_dict[fade_key] = {"type": "fade_in", "duration": 1.0}

        timeline.append(clip)

    manifest["timeline"] = timeline
    manifest["effects"] = effects_dict

    # --- Captions ---
    if captions == "auto":
        caption_config = {"mode": "auto", "generate": True}  # type: Dict[str, Any]
        if caption_style:
            if caption_style not in VALID_CAPTION_STYLES:
                print(
                    "  WARNING: Unknown caption style %r, valid: %s"
                    % (caption_style, ", ".join(VALID_CAPTION_STYLES))
                )
            caption_config["style"] = caption_style
        manifest["captions"] = caption_config

    # --- Color grade ---
    if color_grade:
        if color_grade not in VALID_COLOR_PRESETS:
            print(
                "  WARNING: Unknown color preset %r, valid: %s"
                % (color_grade, ", ".join(VALID_COLOR_PRESETS))
            )
        manifest["color_grade"] = {"preset": color_grade}

    # --- Audio mix ---
    if music_path or normalize:
        audio_mix = {
            "normalize": normalize,
            "target_lufs": -14.0,
        }  # type: Dict[str, Any]
        if music_path:
            audio_mix["music_track"] = "music"
            audio_mix["music_volume"] = music_volume
            audio_mix["duck_on_speech"] = True
        manifest["audio_mix"] = audio_mix

    # --- Overlays ---
    overlays = []  # type: List[Dict[str, Any]]

    if subscribe_button_time is not None:
        overlays.append({
            "type": "subscribe_button",
            "start": subscribe_button_time,
            "duration": 5.0,
            "position": "bottom_right",
            "animation": "slide_in",
        })

    if lower_third_str:
        parts = lower_third_str.split("|")
        if len(parts) < 2:
            raise ValueError(
                "Lower third must be 'Name|Title' or 'Name|Title|start_time', "
                "got: %r" % lower_third_str
            )
        lt_name = parts[0].strip()
        lt_title = parts[1].strip()
        lt_start = float(parts[2].strip()) if len(parts) >= 3 else 0.0
        overlays.append({
            "type": "lower_third",
            "name": lt_name,
            "title": lt_title,
            "start": lt_start,
            "duration": 5.0,
            "position": "bottom_left",
            "animation": "fade_slide",
        })

    manifest["overlays"] = overlays

    return manifest


def print_summary(manifest: Dict[str, Any]) -> None:
    """Print a human-readable summary of the manifest."""
    proj = manifest["project"]
    sources = manifest["sources"]
    timeline = manifest["timeline"]

    print("\n--- Manifest Summary ---")
    print("  Project:    %s" % proj["name"])
    print("  Resolution: %dx%d @ %s fps" % (proj["resolution"][0], proj["resolution"][1], proj["fps"]))
    print("  Codec:      %s" % proj["output_codec"])
    print("  Output:     %s" % proj["output_path"])
    print("  Sources:    %d" % len(sources))
    print("  Clips:      %d" % len(timeline))

    if timeline:
        total_dur = sum((c["out"] - c["in"]) / c.get("speed", 1.0) for c in timeline)
        print("  Duration:   %.1f seconds (%.1f min)" % (total_dur, total_dur / 60))

    if "captions" in manifest:
        style = manifest["captions"].get("style", "default")
        print("  Captions:   auto (%s)" % style)

    if "color_grade" in manifest:
        print("  Color:      %s" % manifest["color_grade"]["preset"])

    if "audio_mix" in manifest:
        mix = manifest["audio_mix"]
        parts = []
        if mix.get("music_track"):
            parts.append("music @ %.0f%%" % (mix.get("music_volume", 0.15) * 100))
        if mix.get("normalize"):
            parts.append("normalize to %s LUFS" % mix.get("target_lufs", -14))
        print("  Audio:      %s" % ", ".join(parts))

    overlays = manifest.get("overlays", [])
    if overlays:
        for ov in overlays:
            print("  Overlay:    %s at %.1fs" % (ov["type"], ov["start"]))

    print("------------------------\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a video editor manifest from simple instructions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", required=True, help="Path to source video file")
    parser.add_argument("--name", default=None, help="Project name (default: input filename)")
    parser.add_argument("--cuts", default=None, help="Cut ranges, e.g. '0:00-1:30, 3:00-5:15'")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed (default: 1.0)")
    parser.add_argument("--captions", default=None, choices=["auto"], help="Caption mode")
    parser.add_argument("--caption-style", default=None, choices=VALID_CAPTION_STYLES, help="Caption visual style")
    parser.add_argument("--color-grade", default=None, help="Color grading preset")
    parser.add_argument("--music", default=None, help="Path to background music file")
    parser.add_argument("--music-volume", type=float, default=0.15, help="Music volume 0.0-1.0 (default: 0.15)")
    parser.add_argument("--normalize", action="store_true", help="Normalize audio loudness to -14 LUFS")
    parser.add_argument("--subscribe-button", type=float, default=None, metavar="TIME", help="Show subscribe button at TIME seconds")
    parser.add_argument("--lower-third", default=None, metavar="'Name|Title|start'", help="Lower third overlay (Name|Title|start_time)")
    parser.add_argument("--codec", default=DEFAULT_CODEC, help="Output codec (default: libx264)")
    parser.add_argument("--output", default=None, help="Output path for manifest JSON")

    args = parser.parse_args()

    # Validate input exists
    input_path = Path(args.input)
    if not input_path.exists():
        print("ERROR: Input file not found: %s" % args.input)
        sys.exit(1)

    project_name = args.name or input_path.stem

    # Build the manifest
    manifest = build_manifest(
        input_path=str(input_path),
        name=project_name,
        cuts=args.cuts,
        speed=args.speed,
        captions=args.captions,
        caption_style=args.caption_style,
        color_grade=args.color_grade,
        music_path=args.music,
        music_volume=args.music_volume,
        normalize=args.normalize,
        subscribe_button_time=args.subscribe_button,
        lower_third_str=args.lower_third,
        output_codec=args.codec,
    )

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = TMP_ROOT / project_name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "manifest.json"

    # Ensure parent directory exists
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write manifest
    with open(str(out_path), "w") as f:
        json.dump(manifest, f, indent=2)

    print("Manifest written to: %s" % out_path)
    print_summary(manifest)


if __name__ == "__main__":
    main()
