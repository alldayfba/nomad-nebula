#!/usr/bin/env python3
"""
Remotion Renderer — Python bridge to Remotion CLI.

Renders Remotion compositions to MP4 via subprocess calls to npx remotion render.
Integrates with the video_editor.py manifest pipeline.

Usage:
    python remotion_renderer.py render --composition TitleSequence --props '{"title":"Test"}' --output segment.mp4
    python remotion_renderer.py list
    python remotion_renderer.py install
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

REMOTION_DIR = Path(__file__).resolve().parent / "remotion"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / ".tmp" / "remotion-renders"
NPX = shutil.which("npx") or "npx"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


class RemotionRenderer:
    """Renders Remotion compositions via CLI."""

    def __init__(self, remotion_dir: str | Path | None = None):
        self.remotion_dir = Path(remotion_dir) if remotion_dir else REMOTION_DIR
        self.output_dir = ensure_dir(OUTPUT_DIR)

    def is_installed(self) -> bool:
        """Check if Remotion project has node_modules."""
        return (self.remotion_dir / "node_modules").exists()

    def ensure_installed(self) -> bool:
        """Install npm dependencies if needed."""
        if self.is_installed():
            return True

        if not (self.remotion_dir / "package.json").exists():
            print(f"  ERROR: No package.json found at {self.remotion_dir}")
            return False

        print("  Installing Remotion dependencies...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=str(self.remotion_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print(f"  ERROR: npm install failed: {result.stderr[:500]}")
            return False

        print("  Dependencies installed successfully")
        return True

    def render_composition(
        self,
        composition_id: str,
        props: dict | None = None,
        output_path: str | None = None,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        duration_in_frames: int | None = None,
    ) -> str:
        """Render a Remotion composition to MP4.

        Args:
            composition_id: Name of the composition (registered in Root.tsx)
            props: JSON-serializable props to pass to the composition
            output_path: Where to save the rendered MP4
            width: Video width
            height: Video height
            fps: Frames per second
            duration_in_frames: Override composition duration

        Returns:
            Path to rendered MP4
        """
        if not self.ensure_installed():
            raise RuntimeError("Remotion not installed")

        # Default output path
        if not output_path:
            output_path = str(self.output_dir / f"{composition_id}.mp4")

        ensure_dir(Path(output_path).parent)

        # Write props to temp file
        props_file = None
        if props:
            props_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            json.dump(props, props_file)
            props_file.close()

        try:
            # Build render command
            cmd = [
                NPX, "remotion", "render",
                "src/index.ts",
                composition_id,
                output_path,
            ]

            if props_file:
                cmd.extend(["--props", props_file.name])

            if width != 1920 or height != 1080:
                cmd.extend(["--width", str(width), "--height", str(height)])

            if duration_in_frames:
                cmd.extend(["--frames", f"0-{duration_in_frames - 1}"])

            print(f"  Rendering {composition_id}...")
            result = subprocess.run(
                cmd,
                cwd=str(self.remotion_dir),
                capture_output=True,
                text=True,
                timeout=600,
            )

            if result.returncode != 0:
                print(f"  ERROR: Render failed: {result.stderr[:500]}")
                raise RuntimeError(f"Remotion render failed for {composition_id}")

            print(f"  Rendered: {output_path}")
            return output_path

        finally:
            if props_file and os.path.exists(props_file.name):
                os.remove(props_file.name)

    def list_compositions(self) -> list[str]:
        """List available Remotion compositions."""
        if not self.ensure_installed():
            return []

        cmd = [
            NPX, "remotion", "compositions",
            "src/index.ts",
        ]

        result = subprocess.run(
            cmd,
            cwd=str(self.remotion_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            print(f"  ERROR: Could not list compositions: {result.stderr[:300]}")
            return []

        # Parse output — each line has composition info
        compositions = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("(") and not line.startswith("Webpack"):
                # Try to extract composition ID
                parts = line.split()
                if parts:
                    compositions.append(parts[0])

        return compositions

    def render_from_manifest_overlay(self, overlay: dict) -> str | None:
        """Render a Remotion overlay from a manifest entry.

        Expected overlay format:
        {
            "type": "remotion",
            "composition": "TitleSequence",
            "props": {"title": "...", "subtitle": "..."},
            "start": 0.0,
            "duration": 4.0,
            "sfx": "impact"
        }
        """
        if overlay.get("type") != "remotion":
            return None

        composition = overlay.get("composition")
        if not composition:
            print("  ERROR: Remotion overlay missing 'composition' field")
            return None

        props = overlay.get("props", {})
        duration = overlay.get("duration", 3.0)
        fps = 30  # default
        duration_in_frames = int(duration * fps)

        # Add duration to props so composition knows its length
        props["durationInFrames"] = duration_in_frames

        output_path = str(
            self.output_dir / f"{composition}_{id(overlay)}.mp4"
        )

        return self.render_composition(
            composition_id=composition,
            props=props,
            output_path=output_path,
            duration_in_frames=duration_in_frames,
        )


def cmd_render(args):
    """Render a composition."""
    renderer = RemotionRenderer()
    props = json.loads(args.props) if args.props else {}

    renderer.render_composition(
        composition_id=args.composition,
        props=props,
        output_path=args.output,
        width=args.width or 1920,
        height=args.height or 1080,
    )


def cmd_list(args):
    """List compositions."""
    renderer = RemotionRenderer()
    compositions = renderer.list_compositions()

    if compositions:
        print(f"\n  Available compositions:")
        for c in compositions:
            print(f"    - {c}")
    else:
        print("  No compositions found (or Remotion not installed)")


def cmd_install(args):
    """Install Remotion dependencies."""
    renderer = RemotionRenderer()
    renderer.ensure_installed()


def main():
    parser = argparse.ArgumentParser(description="Remotion Renderer — Python bridge")
    subparsers = parser.add_subparsers(dest="command")

    # render
    p_render = subparsers.add_parser("render", help="Render a composition")
    p_render.add_argument("--composition", required=True, help="Composition ID")
    p_render.add_argument("--props", help="JSON props string")
    p_render.add_argument("--output", help="Output MP4 path")
    p_render.add_argument("--width", type=int)
    p_render.add_argument("--height", type=int)
    p_render.set_defaults(func=cmd_render)

    # list
    p_list = subparsers.add_parser("list", help="List available compositions")
    p_list.set_defaults(func=cmd_list)

    # install
    p_install = subparsers.add_parser("install", help="Install Remotion dependencies")
    p_install.set_defaults(func=cmd_install)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
