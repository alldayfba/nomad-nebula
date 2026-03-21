#!/usr/bin/env python3
"""
SFX Library — Sound effect auto-sync for video editing.

Maps motion graphic overlay types and transitions to appropriate SFX files,
generates timing lists for AudioMixer integration.

Usage:
    python sfx_library.py map --overlay-type title_reveal
    python sfx_library.py generate --manifest manifest.json
    python sfx_library.py list
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# SFX files directory
SFX_DIR = Path(__file__).resolve().parent / "remotion" / "public" / "sfx"

# Fallback: check for local sfx directory too
SFX_DIR_LOCAL = Path(__file__).resolve().parent.parent / ".tmp" / "sfx"


@dataclass
class SFXEntry:
    """A sound effect with metadata."""
    filename: str
    category: str  # transition, reveal, emphasis, ambient
    duration_hint: float  # approximate duration in seconds
    default_volume: float  # 0.0-1.0


# Master SFX mapping
SFX_CATALOG = {
    # Transition SFX
    "whoosh": SFXEntry("whoosh.wav", "transition", 0.4, 0.7),
    "swoosh": SFXEntry("swoosh.wav", "transition", 0.3, 0.6),
    "glitch": SFXEntry("glitch.wav", "transition", 0.5, 0.5),

    # Reveal SFX
    "impact": SFXEntry("impact.wav", "reveal", 0.3, 0.8),
    "riser": SFXEntry("riser.wav", "reveal", 1.5, 0.5),
    "shine": SFXEntry("shine.wav", "reveal", 0.6, 0.4),

    # UI SFX
    "pop": SFXEntry("pop.wav", "emphasis", 0.2, 0.6),
    "click": SFXEntry("click.wav", "emphasis", 0.1, 0.5),

    # Ambient
    "drone": SFXEntry("drone.wav", "ambient", 3.0, 0.2),
}

# Auto-mapping: overlay/transition type -> SFX name
TYPE_TO_SFX = {
    # Remotion compositions
    "TitleSequence": "impact",
    "RevenueChart": "riser",
    "BlueprintOverview": "shine",
    "TestimonialCard": "pop",
    "ChapterTransition": "whoosh",
    "EndScreen": "shine",

    # Transitions
    "whoosh_transition": "whoosh",
    "zoom_transition": "swoosh",
    "glitch_transition": "glitch",
    "xfade_fade": None,  # no SFX for simple fades

    # Overlays
    "animated_subscribe": "pop",
    "lower_third": "swoosh",
    "text_popup": "pop",
    "title_reveal": "impact",
    "glow_appear": "shine",
    "element_pop": "pop",
    "slide_in": "swoosh",
    "slide_out": "swoosh",

    # Caption events (usually no SFX)
    "captions_word_highlight": None,
}


def find_sfx_path(sfx_name: str) -> str | None:
    """Find the full path to an SFX file."""
    if sfx_name not in SFX_CATALOG:
        return None

    entry = SFX_CATALOG[sfx_name]

    # Check Remotion public dir first
    path = SFX_DIR / entry.filename
    if path.exists():
        return str(path)

    # Check local .tmp/sfx
    path = SFX_DIR_LOCAL / entry.filename
    if path.exists():
        return str(path)

    return None


def get_sfx_for_type(overlay_type: str) -> str | None:
    """Get the SFX name for a given overlay/transition type."""
    return TYPE_TO_SFX.get(overlay_type)


def generate_sfx_timing(manifest: dict) -> list[dict]:
    """Scan a manifest and generate SFX timing list for AudioMixer.

    Returns list of {"path": str, "time": float, "volume": float}
    """
    sfx_list = []

    # Scan overlays
    for overlay in manifest.get("overlays", []):
        # Check explicit sfx key first
        sfx_name = overlay.get("sfx")
        if not sfx_name:
            # Auto-detect from type
            ovr_type = overlay.get("type", "")
            composition = overlay.get("composition", "")
            sfx_name = get_sfx_for_type(composition or ovr_type)

        if not sfx_name:
            continue

        path = find_sfx_path(sfx_name)
        if not path:
            continue

        entry = SFX_CATALOG.get(sfx_name)
        volume = entry.default_volume if entry else 0.6

        # Override volume if specified
        if "sfx_volume" in overlay:
            volume = overlay["sfx_volume"]

        sfx_list.append({
            "path": path,
            "time": overlay.get("start", 0.0),
            "volume": volume,
        })

    # Scan timeline transitions
    for clip in manifest.get("timeline", []):
        transition = clip.get("transition_in", {})
        if transition:
            trans_type = transition.get("type", "")
            sfx_name = get_sfx_for_type(trans_type)
            if sfx_name:
                path = find_sfx_path(sfx_name)
                if path:
                    entry = SFX_CATALOG.get(sfx_name)
                    # SFX plays slightly before transition starts
                    clip_start = clip.get("in", 0.0)
                    sfx_list.append({
                        "path": path,
                        "time": max(0, clip_start - 0.1),
                        "volume": entry.default_volume if entry else 0.5,
                    })

    return sfx_list


def list_available_sfx() -> list[dict]:
    """List all SFX with availability status."""
    result = []
    for name, entry in SFX_CATALOG.items():
        path = find_sfx_path(name)
        result.append({
            "name": name,
            "filename": entry.filename,
            "category": entry.category,
            "duration": entry.duration_hint,
            "volume": entry.default_volume,
            "available": path is not None,
            "path": path,
        })
    return result


def main():
    parser = argparse.ArgumentParser(description="SFX Library — Sound effect auto-sync")
    subparsers = parser.add_subparsers(dest="command")

    # map
    p_map = subparsers.add_parser("map", help="Get SFX for an overlay type")
    p_map.add_argument("--overlay-type", required=True)

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate SFX timing from manifest")
    p_gen.add_argument("--manifest", required=True)

    # list
    subparsers.add_parser("list", help="List all available SFX")

    args = parser.parse_args()

    if args.command == "map":
        sfx = get_sfx_for_type(args.overlay_type)
        if sfx:
            path = find_sfx_path(sfx)
            print(f"  Type: {args.overlay_type} -> SFX: {sfx}")
            print(f"  Path: {path or 'NOT FOUND'}")
        else:
            print(f"  No SFX mapped for: {args.overlay_type}")

    elif args.command == "generate":
        with open(args.manifest) as f:
            manifest = json.load(f)
        timing = generate_sfx_timing(manifest)
        print(json.dumps(timing, indent=2))

    elif args.command == "list":
        sfx_list = list_available_sfx()
        print(f"\n  {'Name':<15} {'File':<15} {'Category':<12} {'Available'}")
        print(f"  {chr(9472)*15} {chr(9472)*15} {chr(9472)*12} {chr(9472)*10}")
        for s in sfx_list:
            avail = "Y" if s["available"] else "N"
            print(f"  {s['name']:<15} {s['filename']:<15} {s['category']:<12} {avail}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
