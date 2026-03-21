#!/usr/bin/env python3
"""
Video Assembler — YouTube video assembly orchestrator.

Takes a project config JSON with multiple source clips, section layouts,
motion graphics, and styling -> produces a fully assembled YouTube video.

Usage:
    python video_assembler.py --config project-config.json
    python video_assembler.py --config project-config.json --preview-section hook
    python video_assembler.py --config project-config.json --skip-captions
    python video_assembler.py --config project-config.json --skip-motion-graphics
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent to path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))

from video_editor import (
    run_cmd,
    FFMPEG,
    FFPROBE,
    ffprobe_info,
    get_video_info,
    OverlayCompositor,
    ColorGrader,
    AudioMixer,
    CaptionGenerator,
    TMP_ROOT,
    ensure_dir,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SectionConfig:
    """Parsed section from project config."""

    id: str
    name: str
    layout: str  # fullscreen_facecam | pip_screenshare

    # Fullscreen fields
    source_path: str = ""
    trim_in: float = 0.0
    trim_out: float = 0.0

    # PiP fields
    facecam_path: str = ""
    screen_path: str = ""
    facecam_trim_in: float = 0.0
    facecam_trim_out: float = 0.0
    screen_trim_in: float = 0.0
    screen_trim_out: float = 0.0
    pip_position: str = "bottom_left"
    pip_scale: float = 0.28
    pip_margin: int = 30
    pip_border: int = 3

    # Optional per-section features
    motion_graphics: List[Dict[str, Any]] = field(default_factory=list)
    lower_third: Dict[str, Any] = field(default_factory=dict)
    transition_out: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Compute section duration from trim points."""
        if self.layout == "fullscreen_facecam":
            return max(0.0, self.trim_out - self.trim_in)
        elif self.layout == "pip_screenshare":
            return max(0.0, self.screen_trim_out - self.screen_trim_in)
        return 0.0


# ---------------------------------------------------------------------------
# Config parser
# ---------------------------------------------------------------------------


class AssemblyConfig:
    """Parse and validate a project config JSON file."""

    def __init__(self, config_path: str):
        with open(config_path) as f:
            self.raw: Dict[str, Any] = json.load(f)

        proj = self.raw.get("project", {})
        self.name: str = proj.get("name", "untitled")
        self.resolution: Tuple[int, int] = tuple(proj.get("resolution", [1920, 1080]))  # type: ignore[assignment]
        self.width: int = self.resolution[0]
        self.height: int = self.resolution[1]
        self.fps: int = proj.get("fps", 30)
        self.output_path: str = proj.get("output_path", "")

        # Source map: id -> file path
        self.sources: Dict[str, str] = {}
        for sid, sinfo in self.raw.get("sources", {}).items():
            self.sources[sid] = sinfo["path"]

        self.sections: List[SectionConfig] = self._parse_sections()

        self.captions: Dict[str, Any] = self.raw.get(
            "captions", {"enabled": True, "style": "capcut_pop", "model": "base"}
        )
        self.color_grade: Dict[str, Any] = self.raw.get(
            "color_grade", {"preset": "warm_cinematic"}
        )
        self.audio_mix: Dict[str, Any] = self.raw.get(
            "audio_mix", {"normalize": True, "target_lufs": -14.0}
        )
        self.sfx: Dict[str, Any] = self.raw.get("sfx", {"auto_sync": True})

    # ------------------------------------------------------------------

    def _parse_sections(self) -> List[SectionConfig]:
        sections: List[SectionConfig] = []
        for sec in self.raw.get("sections", []):
            s = SectionConfig(
                id=sec["id"],
                name=sec.get("name", sec["id"]),
                layout=sec.get("layout", "fullscreen_facecam"),
            )

            if s.layout == "fullscreen_facecam":
                source_id = sec.get("source", "")
                s.source_path = self.sources.get(source_id, source_id)
                trim = sec.get("trim", {})
                s.trim_in = float(trim.get("in", 0.0))
                s.trim_out = float(trim.get("out", 0.0))

            elif s.layout == "pip_screenshare":
                fc_id = sec.get("facecam_source", "")
                sc_id = sec.get("screen_source", "")
                s.facecam_path = self.sources.get(fc_id, fc_id)
                s.screen_path = self.sources.get(sc_id, sc_id)
                fc_trim = sec.get("facecam_trim", {})
                sc_trim = sec.get("screen_trim", {})
                s.facecam_trim_in = float(fc_trim.get("in", 0.0))
                s.facecam_trim_out = float(fc_trim.get("out", 0.0))
                s.screen_trim_in = float(sc_trim.get("in", 0.0))
                s.screen_trim_out = float(sc_trim.get("out", 0.0))
                pip = sec.get("pip", {})
                s.pip_position = pip.get("position", "bottom_left")
                s.pip_scale = float(pip.get("scale", 0.28))
                s.pip_margin = int(pip.get("margin", 30))
                s.pip_border = int(pip.get("border_width", 3))

            s.motion_graphics = sec.get("motion_graphics", [])
            s.lower_third = sec.get("lower_third", {})
            s.transition_out = sec.get("transition_out", {})

            sections.append(s)
        return sections

    # ------------------------------------------------------------------

    def validate(self) -> List[str]:
        """Validate config, return a list of warnings (empty = all good)."""
        warnings: List[str] = []
        if not self.sections:
            warnings.append("No sections defined in config")

        for sec in self.sections:
            if sec.layout == "fullscreen_facecam":
                if sec.source_path and not os.path.exists(sec.source_path):
                    warnings.append(
                        f"Section '{sec.id}': source not found: {sec.source_path}"
                    )
                if sec.trim_out <= sec.trim_in:
                    warnings.append(
                        f"Section '{sec.id}': trim_out ({sec.trim_out}) <= trim_in ({sec.trim_in})"
                    )
            elif sec.layout == "pip_screenshare":
                if sec.facecam_path and not os.path.exists(sec.facecam_path):
                    warnings.append(
                        f"Section '{sec.id}': facecam not found: {sec.facecam_path}"
                    )
                if sec.screen_path and not os.path.exists(sec.screen_path):
                    warnings.append(
                        f"Section '{sec.id}': screen not found: {sec.screen_path}"
                    )
            else:
                warnings.append(
                    f"Section '{sec.id}': unknown layout '{sec.layout}'"
                )
        return warnings


# ---------------------------------------------------------------------------
# Section renderer
# ---------------------------------------------------------------------------


class SectionRenderer:
    """Render individual sections based on their layout type."""

    def __init__(self, config: AssemblyConfig, work_dir: Path):
        self.config = config
        self.work_dir = work_dir
        self.w = config.width
        self.h = config.height
        self.fps = config.fps

    def render_section(self, section: SectionConfig) -> str:
        """Render a single section and return the output file path."""
        output = str(self.work_dir / f"section_{section.id}.mp4")

        if section.layout == "fullscreen_facecam":
            return self._render_fullscreen(section, output)
        elif section.layout == "pip_screenshare":
            return self._render_pip(section, output)
        else:
            raise ValueError(f"Unknown layout: {section.layout}")

    # ------------------------------------------------------------------

    def _render_fullscreen(self, section: SectionConfig, output: str) -> str:
        """Trim, scale, and pad a single source to project resolution."""
        print(f"  Rendering fullscreen: {section.name}")

        cmd = [
            FFMPEG, "-y",
            "-ss", str(section.trim_in),
            "-to", str(section.trim_out),
            "-i", section.source_path,
            "-vf", (
                f"scale={self.w}:{self.h}:force_original_aspect_ratio=decrease,"
                f"pad={self.w}:{self.h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"fps={self.fps},format=yuv420p"
            ),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            output,
        ]
        run_cmd(cmd, desc=f"Fullscreen: {section.name}")
        return output

    # ------------------------------------------------------------------

    def _render_pip(self, section: SectionConfig, output: str) -> str:
        """Render a PiP layout (screen share background + face cam overlay)."""
        print(f"  Rendering PiP: {section.name}")

        OverlayCompositor.overlay_video_pip(
            background_path=section.screen_path,
            pip_path=section.facecam_path,
            output_path=output,
            pip_scale=section.pip_scale,
            position=section.pip_position,
            margin=section.pip_margin,
            border_width=section.pip_border,
            project_width=self.w,
            project_height=self.h,
            fps=self.fps,
            background_trim=(section.screen_trim_in, section.screen_trim_out),
            pip_trim=(section.facecam_trim_in, section.facecam_trim_out),
            audio_from_pip=True,
        )
        return output


# ---------------------------------------------------------------------------
# Main assembler
# ---------------------------------------------------------------------------


class VideoAssembler:
    """Top-level YouTube video assembly orchestrator.

    Pipeline:
        1. Parse + validate config
        2. Render each section (fullscreen / PiP)
        3. Concatenate sections
        4. Overlay motion graphics (Remotion)
        5. Color grade
        6. Generate + burn captions
        7. Audio mix (normalize, music, SFX)
        8. Write final output
    """

    def assemble(
        self,
        config_path: str,
        preview_section: Optional[str] = None,
        skip_captions: bool = False,
        skip_motion_graphics: bool = False,
    ) -> str:
        """Run the full assembly pipeline. Returns the final output path."""
        start_time = time.time()

        # -- Step 1: Parse config -----------------------------------------
        print("\n========================================")
        print("  VIDEO ASSEMBLER")
        print("========================================\n")

        config = AssemblyConfig(config_path)
        warnings = config.validate()
        for w in warnings:
            print(f"  WARNING: {w}")

        # Prepare work directories
        work_dir = ensure_dir(TMP_ROOT / config.name)
        sections_dir = ensure_dir(work_dir / "sections")
        mg_dir = ensure_dir(work_dir / "motion-graphics")
        captions_dir = ensure_dir(work_dir / "captions")

        output_path = config.output_path or str(work_dir / "final.mp4")

        print(f"  Project: {config.name}")
        print(f"  Resolution: {config.width}x{config.height} @ {config.fps}fps")
        print(f"  Sections: {len(config.sections)}")
        print(f"  Output: {output_path}")

        # Filter to a single section in preview mode
        sections = config.sections
        if preview_section:
            sections = [s for s in sections if s.id == preview_section]
            if not sections:
                print(f"  ERROR: Section '{preview_section}' not found")
                sys.exit(1)
            print(f"  PREVIEW MODE: rendering only section '{preview_section}'")

        # Count total pipeline steps for progress display
        total_steps = 4  # render + concat + color + audio
        if not skip_motion_graphics:
            total_steps += 1
        if not skip_captions:
            total_steps += 1
        step = 0

        # -- Step 2: Render each section ----------------------------------
        step += 1
        print(f"\n[{step}/{total_steps}] Rendering sections...")
        renderer = SectionRenderer(config, sections_dir)
        section_files: List[str] = []

        for i, section in enumerate(sections):
            print(
                f"\n  --- Section {i+1}/{len(sections)}: "
                f"{section.name} ({section.layout}) ---"
            )
            try:
                out = renderer.render_section(section)
                section_files.append(out)
                print(f"  Done: {section.name}")
            except Exception as e:
                print(f"  ERROR rendering {section.name}: {e}")
                continue

        if not section_files:
            print("  ERROR: No sections rendered successfully")
            sys.exit(1)

        # -- Step 3: Concatenate ------------------------------------------
        step += 1
        print(f"\n[{step}/{total_steps}] Concatenating {len(section_files)} sections...")

        if len(section_files) == 1:
            concat_output = section_files[0]
        else:
            concat_output = str(work_dir / "concat.mp4")
            concat_list = str(work_dir / "concat_list.txt")
            with open(concat_list, "w") as f:
                for sf in section_files:
                    # Escape single quotes in paths for ffmpeg concat
                    escaped = sf.replace("'", "'\\''")
                    f.write(f"file '{escaped}'\n")

            cmd = [
                FFMPEG, "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
                concat_output,
            ]
            run_cmd(cmd, desc="Concatenating sections")

        current = concat_output

        # -- Step 4: Motion graphics (Remotion) ---------------------------
        if not skip_motion_graphics:
            step += 1
            print(f"\n[{step}/{total_steps}] Rendering motion graphics...")
            current = self._apply_motion_graphics(
                config, sections, current, mg_dir, work_dir
            )

        # -- Step 5: Color grade ------------------------------------------
        step += 1
        print(f"\n[{step}/{total_steps}] Applying color grade...")
        preset = config.color_grade.get("preset", "warm_cinematic")
        if preset:
            graded = str(work_dir / "graded.mp4")
            ColorGrader.grade(current, graded, preset=preset)
            current = graded

        # -- Step 6: Captions --------------------------------------------
        if not skip_captions and config.captions.get("enabled", True):
            step += 1
            print(f"\n[{step}/{total_steps}] Generating captions...")
            current = self._apply_captions(config, current, work_dir, captions_dir)

        # -- Step 7: Audio mix + SFX -------------------------------------
        step += 1
        print(f"\n[{step}/{total_steps}] Mixing audio...")
        current = self._mix_audio(config, sections, current, work_dir)

        # -- Step 8: Final output ----------------------------------------
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        if os.path.abspath(current) != os.path.abspath(output_path):
            shutil.move(current, output_path)

        elapsed = time.time() - start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)

        print(f"\n========================================")
        print(f"  ASSEMBLY COMPLETE")
        print(f"  Output: {output_path}")
        print(f"  Time: {mins}m {secs}s")
        print(f"========================================\n")

        return output_path

    # ------------------------------------------------------------------
    # Internal pipeline stages
    # ------------------------------------------------------------------

    def _apply_motion_graphics(
        self,
        config: AssemblyConfig,
        sections: List[SectionConfig],
        current: str,
        mg_dir: Path,
        work_dir: Path,
    ) -> str:
        """Render Remotion motion graphics and overlay them onto the video."""
        mg_overlays: List[Dict[str, Any]] = []
        cumulative_time = 0.0

        for section in sections:
            for mg in section.motion_graphics:
                if mg.get("type") != "remotion":
                    continue

                composition = mg.get("composition", "")
                props = mg.get("props", {})
                mg_start = float(mg.get("start", 0.0))
                mg_duration = float(mg.get("duration", 4.0))
                abs_start = cumulative_time + mg_start

                try:
                    from remotion_renderer import RemotionRenderer

                    rr = RemotionRenderer()
                    mg_output = str(mg_dir / f"mg_{section.id}_{composition}.mp4")
                    rr.render_composition(
                        composition_id=composition,
                        props=props,
                        output_path=mg_output,
                        width=config.width,
                        height=config.height,
                        fps=config.fps,
                    )

                    # Convert to transparent PNG sequence for overlay
                    png_subdir = str(
                        ensure_dir(mg_dir / f"mg_{section.id}_{composition}_frames")
                    )
                    cmd = [
                        FFMPEG, "-y", "-i", mg_output,
                        "-vf", "format=rgba",
                        str(Path(png_subdir) / "frame_%05d.png"),
                    ]
                    run_cmd(cmd, desc=f"Converting {composition} to PNG sequence")

                    mg_overlays.append({
                        "png_dir": png_subdir,
                        "start": abs_start,
                        "x": 0,
                        "y": 0,
                    })
                    print(f"  {composition} at {abs_start:.1f}s")
                except ImportError:
                    print(f"  WARNING: remotion_renderer not available, skipping {composition}")
                except Exception as e:
                    print(f"  WARNING: Could not render {composition}: {e}")

            cumulative_time += section.duration

        if mg_overlays:
            mg_output_path = str(work_dir / "with_mg.mp4")
            OverlayCompositor.overlay_multiple(
                current, mg_overlays, mg_output_path, config.fps
            )
            return mg_output_path

        return current

    # ------------------------------------------------------------------

    def _apply_captions(
        self,
        config: AssemblyConfig,
        current: str,
        work_dir: Path,
        captions_dir: Path,
    ) -> str:
        """Transcribe audio, render caption frames, and overlay them."""
        try:
            from video_caption_renderer import CaptionRenderer, PRESET_STYLES
        except ImportError as e:
            print(f"  WARNING: Caption renderer not available: {e}")
            return current

        cap_style = config.captions.get("style", "capcut_pop")
        cap_model = config.captions.get("model", "base")

        try:
            # Transcribe
            gen = CaptionGenerator(model_size=cap_model)
            words = gen.transcribe(current)

            # Persist captions JSON for reference
            captions_json = str(work_dir / "captions.json")
            gen.save_captions(words, captions_json)

            # Group into display phrases
            phrases = CaptionGenerator.group_into_phrases(words)
            if not phrases:
                print("  WARNING: No caption phrases generated")
                return current

            cap_renderer = CaptionRenderer(
                resolution=(config.width, config.height),
                fps=config.fps,
            )
            style_obj = PRESET_STYLES.get(cap_style, PRESET_STYLES.get("capcut_pop"))
            if style_obj is None:
                print(f"  WARNING: Caption style '{cap_style}' not found, skipping")
                return current

            print(f"  Rendering {len(phrases)} caption phrases ({cap_style})...")

            captioned = current
            for i, phrase in enumerate(phrases):
                phrase_dir = str(ensure_dir(captions_dir / f"p_{i:04d}"))
                cap_renderer.render_caption_frames(phrase, style_obj, phrase_dir)

                temp = str(work_dir / f"cap_{i:04d}.mp4")
                OverlayCompositor.overlay_png_sequence(
                    captioned,
                    phrase_dir,
                    temp,
                    start_time=phrase[0]["start"],
                    fps=config.fps,
                )
                # Clean intermediate to save disk space
                if captioned != current and os.path.exists(captioned):
                    os.remove(captioned)
                captioned = temp

                if (i + 1) % 25 == 0:
                    print(f"    {i+1}/{len(phrases)} phrases rendered...")

            print(f"  {len(phrases)} caption phrases applied")
            return captioned

        except Exception as e:
            print(f"  WARNING: Caption generation failed: {e}")
            return current

    # ------------------------------------------------------------------

    def _mix_audio(
        self,
        config: AssemblyConfig,
        sections: List[SectionConfig],
        current: str,
        work_dir: Path,
    ) -> str:
        """Normalize audio, mix in background music, and apply SFX."""
        audio_cfg = config.audio_mix
        normalize = audio_cfg.get("normalize", True)
        target_lufs = float(audio_cfg.get("target_lufs", -14.0))
        music_path = audio_cfg.get("music_path")
        music_volume = float(audio_cfg.get("music_volume", 0.12))

        # Build SFX list from section events
        sfx_list: List[Dict[str, Any]] = []
        if config.sfx.get("auto_sync", False):
            sfx_list = self._build_sfx_list(sections)

        final_audio = str(work_dir / "final_audio.mp4")
        AudioMixer.mix(
            video_path=current,
            output_path=final_audio,
            music_path=music_path,
            music_volume=music_volume,
            sfx=sfx_list if sfx_list else None,
            normalize=normalize,
            target_lufs=target_lufs,
        )
        return final_audio

    # ------------------------------------------------------------------

    def _build_sfx_list(
        self, sections: List[SectionConfig]
    ) -> List[Dict[str, Any]]:
        """Attempt to auto-generate SFX timing from section events."""
        try:
            from sfx_library import SFXLibrary

            sfx_lib = SFXLibrary()
            overlay_events: List[Dict[str, Any]] = []
            cumulative = 0.0

            for section in sections:
                for mg in section.motion_graphics:
                    overlay_events.append({
                        "type": mg.get("composition", "unknown").lower(),
                        "start": cumulative + float(mg.get("start", 0.0)),
                    })
                if section.transition_out:
                    overlay_events.append({
                        "type": section.transition_out.get("type", "fade"),
                        "start": cumulative + section.duration,
                    })
                cumulative += section.duration

            result = sfx_lib.generate_sfx_timing(overlay_events)
            if result:
                print(f"  Auto-synced {len(result)} SFX events")
            return result or []
        except ImportError:
            print("  WARNING: sfx_library not available, skipping SFX auto-sync")
            return []
        except Exception as e:
            print(f"  WARNING: SFX auto-sync failed: {e}")
            return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Video Assembler -- YouTube video assembly orchestrator",
    )
    parser.add_argument(
        "--config", required=True, help="Path to project config JSON"
    )
    parser.add_argument(
        "--preview-section",
        default=None,
        help="Render only this section ID (for quick preview)",
    )
    parser.add_argument(
        "--skip-captions",
        action="store_true",
        help="Skip caption generation and overlay",
    )
    parser.add_argument(
        "--skip-motion-graphics",
        action="store_true",
        help="Skip Remotion motion graphics rendering",
    )

    args = parser.parse_args()

    assembler = VideoAssembler()
    assembler.assemble(
        config_path=args.config,
        preview_section=args.preview_section,
        skip_captions=args.skip_captions,
        skip_motion_graphics=args.skip_motion_graphics,
    )


if __name__ == "__main__":
    main()
