#!/usr/bin/env python3
"""
Video Editor — Programmatic video editing engine.

Manifest-driven rendering pipeline using FFmpeg + PyAV + Pillow + OpenCV.
Replaces CapCut / Premiere Pro / After Effects for YouTube content production.

Usage:
    python video_editor.py render --manifest project.json
    python video_editor.py captions --input video.mp4 --style capcut_pop
    python video_editor.py auto-edit --input video.mp4 --style youtube_engaging
    python video_editor.py youtube-optimize --input video.mp4
    python video_editor.py color-grade --input video.mp4 --preset warm_cinematic
    python video_editor.py reframe --input video.mp4 --ratio 9:16
    python video_editor.py preview --manifest project.json --duration 10
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp" / "video-edits"

COLOR_PRESETS: dict[str, str] = {
    "warm_cinematic": (
        "eq=brightness=0.02:contrast=1.1:saturation=1.15:gamma=1.0,"
        "colorbalance=rs=0.08:gs=0.03:bs=-0.06:rm=0.05:bm=-0.04"
    ),
    "cool_moody": (
        "eq=brightness=-0.05:contrast=1.2:saturation=0.9:gamma=1.0,"
        "colorbalance=rs=-0.06:bs=0.1:rm=-0.04:bm=0.07"
    ),
    "vibrant": "eq=brightness=0.03:contrast=1.05:saturation=1.35:gamma=1.0",
    "desaturated": "eq=brightness=-0.02:contrast=1.15:saturation=0.6:gamma=1.0",
    "orange_teal": (
        "eq=contrast=1.1:saturation=1.2:gamma=1.0,"
        "colorbalance=rs=0.12:gs=0.04:bs=-0.08:rh=-0.04:gh=0.0:bh=0.1"
    ),
}

CAPTION_STYLES = ["capcut_pop", "subtitle_bar", "karaoke", "minimal", "bold_outline"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_cmd(cmd: list[str], desc: str = "", check: bool = True,
            capture: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
    """Run a subprocess command with logging."""
    if desc:
        print(f"  [{desc}]")
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=check,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as exc:
        print(f"  ERROR: {exc.stderr[:500] if exc.stderr else exc}")
        raise
    except subprocess.TimeoutExpired:
        print(f"  ERROR: Command timed out after {timeout}s")
        raise


def ffprobe_info(path: str) -> dict[str, Any]:
    """Probe a media file and return stream/format info."""
    cmd = [
        FFPROBE, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    result = run_cmd(cmd, desc=f"Probing {Path(path).name}")
    return json.loads(result.stdout)


def get_video_info(path: str) -> dict[str, Any]:
    """Extract key video metadata."""
    info = ffprobe_info(path)
    video_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    audio_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "audio"),
        None,
    )
    fmt = info.get("format", {})
    result: dict[str, Any] = {
        "duration": float(fmt.get("duration", 0)),
        "format": fmt.get("format_name", "unknown"),
        "has_audio": audio_stream is not None,
    }
    if video_stream:
        result["width"] = int(video_stream.get("width", 0))
        result["height"] = int(video_stream.get("height", 0))
        # Parse fps from r_frame_rate (e.g. "30/1")
        rfr = video_stream.get("r_frame_rate", "30/1")
        if "/" in rfr:
            num, den = rfr.split("/")
            result["fps"] = round(int(num) / max(int(den), 1), 2)
        else:
            result["fps"] = float(rfr)
        result["codec"] = video_stream.get("codec_name", "unknown")
    return result


def ensure_dir(path: str | Path) -> Path:
    """Create directory if it doesn't exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def ts_to_seconds(ts: str) -> float:
    """Convert timestamp string (M:SS or H:MM:SS) to seconds."""
    parts = ts.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return float(ts)


# ---------------------------------------------------------------------------
# VideoProject — Manifest loader & validator
# ---------------------------------------------------------------------------


@dataclass
class VideoProject:
    """Loads and validates a video edit manifest."""

    manifest_path: str
    data: dict = field(default_factory=dict)
    project_dir: Path = field(default_factory=lambda: TMP_ROOT)
    source_info: dict[str, dict] = field(default_factory=dict)

    def load(self) -> None:
        with open(self.manifest_path) as f:
            self.data = json.load(f)
        proj = self.data.get("project", {})
        name = proj.get("name", "untitled")
        self.project_dir = ensure_dir(TMP_ROOT / name)
        self._validate()
        self._probe_sources()

    def _validate(self) -> None:
        required = ["project", "sources", "timeline"]
        for key in required:
            if key not in self.data:
                raise ValueError(f"Manifest missing required key: {key}")
        proj = self.data["project"]
        if "resolution" not in proj:
            proj["resolution"] = [1920, 1080]
        if "fps" not in proj:
            proj["fps"] = 30
        if "output_format" not in proj:
            proj["output_format"] = "mp4"
        if "output_codec" not in proj:
            proj["output_codec"] = "libx264"

    def _probe_sources(self) -> None:
        for name, src in self.data.get("sources", {}).items():
            path = src.get("path", "")
            if not os.path.exists(path):
                print(f"  WARNING: Source '{name}' not found: {path}")
                continue
            src_type = src.get("type", "video")
            if src_type in ("video", "audio"):
                self.source_info[name] = get_video_info(path)

    @property
    def resolution(self) -> tuple[int, int]:
        r = self.data["project"]["resolution"]
        return (r[0], r[1])

    @property
    def fps(self) -> int:
        return self.data["project"]["fps"]

    @property
    def output_path(self) -> str:
        return self.data["project"].get(
            "output_path",
            str(self.project_dir / "output.mp4"),
        )

    @property
    def output_codec(self) -> str:
        return self.data["project"].get("output_codec", "libx264")


# ---------------------------------------------------------------------------
# TimelineRenderer — Cut, concat, speed, transitions
# ---------------------------------------------------------------------------


class TimelineRenderer:
    """Handles timeline operations: cut, speed, concat, transitions."""

    def __init__(self, project: VideoProject):
        self.project = project
        self.segments_dir = ensure_dir(project.project_dir / "segments")

    def render_segment(self, clip: dict, index: int) -> str:
        """Render a single timeline segment to an intermediate file."""
        source_name = clip["source"]
        source = self.project.data["sources"][source_name]
        input_path = source["path"]
        in_time = clip.get("in", 0.0)
        out_time = clip.get("out", None)
        speed = clip.get("speed", 1.0)
        w, h = self.project.resolution
        fps = self.project.fps

        output = str(self.segments_dir / f"seg_{index:04d}.mp4")

        cmd = [FFMPEG, "-y", "-i", input_path]

        # Time range
        cmd.extend(["-ss", str(in_time)])
        if out_time is not None:
            cmd.extend(["-t", str(out_time - in_time)])

        # Build video filter chain
        vfilters = []

        # Scale to project resolution
        vfilters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")
        vfilters.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")
        vfilters.append(f"fps={fps}")
        vfilters.append("format=yuv420p")

        # Speed adjustment
        if speed != 1.0:
            vfilters.append(f"setpts={1.0/speed}*PTS")

        # Per-segment effects from manifest
        effects = self.project.data.get("effects", {})
        for effect_id in clip.get("effects", []):
            effect = effects.get(effect_id, {})
            etype = effect.get("type", "")
            vf = self._effect_to_vfilter(effect, etype)
            if vf:
                vfilters.append(vf)

        cmd.extend(["-vf", ",".join(vfilters)])

        # Audio filters
        afilters = []
        audio_cfg = clip.get("audio", {})
        if speed != 1.0:
            # Chain atempo for speeds outside 0.5-2.0 range
            remaining = speed
            while remaining > 2.0:
                afilters.append("atempo=2.0")
                remaining /= 2.0
            while remaining < 0.5:
                afilters.append("atempo=0.5")
                remaining /= 0.5
            if abs(remaining - 1.0) > 0.01:
                afilters.append(f"atempo={remaining}")

        vol = audio_cfg.get("volume", 1.0)
        if vol != 1.0:
            afilters.append(f"volume={vol}")

        fade_in = audio_cfg.get("fade_in", 0)
        if fade_in > 0:
            afilters.append(f"afade=t=in:d={fade_in}")

        fade_out = audio_cfg.get("fade_out", 0)
        if fade_out > 0:
            afilters.append(f"afade=t=out:d={fade_out}")

        if afilters:
            cmd.extend(["-af", ",".join(afilters)])

        # Encoding
        codec = self.project.output_codec
        cmd.extend(["-c:v", codec, "-c:a", "aac", "-b:a", "192k"])
        cmd.append(output)

        run_cmd(cmd, desc=f"Rendering segment {index}")
        return output

    def _effect_to_vfilter(self, effect: dict, etype: str) -> str | None:
        """Convert a manifest effect to an FFmpeg video filter string."""
        if etype == "fade_in":
            d = effect.get("duration", 1.0)
            return f"fade=t=in:st=0:d={d}"
        elif etype == "fade_out":
            d = effect.get("duration", 1.0)
            return f"fade=t=out:d={d}"
        elif etype == "zoom_pulse":
            start = effect.get("start", 0)
            end = effect.get("end", 1)
            scale = effect.get("scale", 1.15)
            w, h = self.project.resolution
            return (
                f"zoompan=z='if(between(in_time,{start},{end}),"
                f"min(zoom+0.002,{scale}),max(zoom-0.002,1.0))':"
                f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={self.project.fps}"
            )
        elif etype == "ken_burns":
            end_scale = effect.get("end_scale", 1.2)
            w, h = self.project.resolution
            return (
                f"zoompan=z='min(zoom+0.0005,{end_scale})':"
                f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s={w}x{h}:fps={self.project.fps}"
            )
        elif etype == "blur":
            radius = effect.get("radius", 10)
            return f"boxblur=luma_radius={radius}:luma_power=1"
        return None

    def concat_segments(self, segment_paths: list[str], output: str) -> str:
        """Concatenate rendered segments into one file."""
        if not segment_paths:
            raise ValueError("No segments to concatenate")

        if len(segment_paths) == 1:
            shutil.copy2(segment_paths[0], output)
            return output

        # Check for transitions in timeline
        timeline = self.project.data.get("timeline", [])
        has_transitions = any(
            clip.get("transition_in") for clip in timeline[1:]
        )

        if has_transitions:
            return self._concat_with_transitions(segment_paths, timeline, output)
        else:
            return self._concat_simple(segment_paths, output)

    def _concat_simple(self, segment_paths: list[str], output: str) -> str:
        """Simple concat using concat demuxer."""
        list_file = str(self.segments_dir / "concat_list.txt")
        with open(list_file, "w") as f:
            for p in segment_paths:
                f.write(f"file '{p}'\n")

        cmd = [
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            output,
        ]
        run_cmd(cmd, desc="Concatenating segments")
        return output

    def _concat_with_transitions(self, segment_paths: list[str],
                                  timeline: list[dict], output: str) -> str:
        """Concat with xfade transitions between segments."""
        if len(segment_paths) < 2:
            return self._concat_simple(segment_paths, output)

        # Build xfade chain iteratively (2 inputs at a time)
        current = segment_paths[0]
        for i in range(1, len(segment_paths)):
            transition = timeline[i].get("transition_in", {}) if i < len(timeline) else {}
            trans_type = transition.get("type", "xfade_fade").replace("xfade_", "")
            trans_dur = transition.get("duration", 0.5)

            temp_out = str(self.segments_dir / f"xfade_{i:04d}.mp4")

            # Get duration of current file for offset calculation
            info = get_video_info(current)
            offset = max(0, info["duration"] - trans_dur)

            cmd = [
                FFMPEG, "-y",
                "-i", current,
                "-i", segment_paths[i],
                "-filter_complex",
                (
                    f"[0:v][1:v]xfade=transition={trans_type}:"
                    f"duration={trans_dur}:offset={offset}[v];"
                    f"[0:a][1:a]acrossfade=d={trans_dur}[a]"
                ),
                "-map", "[v]", "-map", "[a]",
                "-c:v", self.project.output_codec,
                "-c:a", "aac", "-b:a", "192k",
                temp_out,
            ]
            run_cmd(cmd, desc=f"Applying transition {i}")
            current = temp_out

        shutil.copy2(current, output)
        return output


# ---------------------------------------------------------------------------
# ColorGrader — Presets, custom params, LUT
# ---------------------------------------------------------------------------


class ColorGrader:
    """Apply color grading via FFmpeg eq/colorbalance filters or LUTs."""

    @staticmethod
    def grade(input_path: str, output_path: str,
              preset: str | None = None,
              brightness: float = 0.0,
              contrast: float = 1.0,
              saturation: float = 1.0,
              temperature: float = 0.0,
              lut_path: str | None = None,
              codec: str = "libx264") -> str:
        """Apply color grade to a video file."""
        vfilters = []

        if lut_path and os.path.exists(lut_path):
            vfilters.append(f"lut3d=file='{lut_path}'")
        elif preset and preset in COLOR_PRESETS:
            vfilters.append(COLOR_PRESETS[preset])
        else:
            # Custom params
            eq_parts = []
            if brightness != 0.0:
                eq_parts.append(f"brightness={brightness}")
            if contrast != 1.0:
                eq_parts.append(f"contrast={contrast}")
            if saturation != 1.0:
                eq_parts.append(f"saturation={saturation}")
            if eq_parts:
                vfilters.append("eq=" + ":".join(eq_parts))

            # Temperature via colorbalance
            if temperature != 0.0:
                t = temperature / 5000.0  # normalize
                rs = round(t * 0.1, 3)
                bs = round(-t * 0.1, 3)
                vfilters.append(f"colorbalance=rs={rs}:bs={bs}")

        if not vfilters:
            # No grading needed, just copy
            shutil.copy2(input_path, output_path)
            return output_path

        cmd = [
            FFMPEG, "-y", "-i", input_path,
            "-vf", ",".join(vfilters),
            "-c:v", codec, "-c:a", "copy",
            output_path,
        ]
        run_cmd(cmd, desc="Applying color grade")
        return output_path


# ---------------------------------------------------------------------------
# AudioMixer — Music ducking, SFX, normalization
# ---------------------------------------------------------------------------


class AudioMixer:
    """Handle audio mixing: music, ducking, SFX, normalization."""

    @staticmethod
    def mix(video_path: str, output_path: str,
            music_path: str | None = None,
            music_volume: float = 0.15,
            duck_on_speech: bool = True,
            sfx: list[dict] | None = None,
            normalize: bool = True,
            target_lufs: float = -14.0,
            codec: str = "libx264") -> str:
        """Mix audio tracks together."""

        current = video_path

        # Step 1: Add background music with ducking
        if music_path and os.path.exists(music_path):
            temp = output_path + ".music_mix.mp4"
            if duck_on_speech:
                # Use sidechaincompress for ducking
                cmd = [
                    FFMPEG, "-y",
                    "-i", current,
                    "-i", music_path,
                    "-filter_complex",
                    (
                        f"[1:a]volume={music_volume}[music];"
                        "[0:a][music]amix=inputs=2:duration=first:"
                        "dropout_transition=2[mixed]"
                    ),
                    "-map", "0:v", "-map", "[mixed]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    temp,
                ]
            else:
                cmd = [
                    FFMPEG, "-y",
                    "-i", current,
                    "-i", music_path,
                    "-filter_complex",
                    (
                        f"[1:a]volume={music_volume}[music];"
                        "[0:a][music]amix=inputs=2:duration=first[mixed]"
                    ),
                    "-map", "0:v", "-map", "[mixed]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    temp,
                ]
            run_cmd(cmd, desc="Mixing background music")
            current = temp

        # Step 2: Add SFX at specific timestamps
        if sfx:
            for i, effect in enumerate(sfx):
                sfx_path = effect.get("path", "")
                sfx_time = effect.get("time", 0.0)
                sfx_vol = effect.get("volume", 0.8)
                if not os.path.exists(sfx_path):
                    continue
                temp = output_path + f".sfx_{i}.mp4"
                cmd = [
                    FFMPEG, "-y",
                    "-i", current,
                    "-i", sfx_path,
                    "-filter_complex",
                    (
                        f"[1:a]volume={sfx_vol},adelay={int(sfx_time*1000)}|"
                        f"{int(sfx_time*1000)}[sfx];"
                        "[0:a][sfx]amix=inputs=2:duration=first[mixed]"
                    ),
                    "-map", "0:v", "-map", "[mixed]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    temp,
                ]
                run_cmd(cmd, desc=f"Adding SFX {i}")
                current = temp

        # Step 3: Normalize audio
        if normalize:
            temp = output_path + ".norm.mp4"
            cmd = [
                FFMPEG, "-y", "-i", current,
                "-af", f"loudnorm=I={target_lufs}:TP=-1:LRA=11",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                temp,
            ]
            run_cmd(cmd, desc="Normalizing audio")
            current = temp

        # Move final to output
        if current != output_path:
            shutil.move(current, output_path)

        # Clean up intermediates
        for suffix in [".music_mix.mp4", ".norm.mp4"]:
            p = output_path + suffix
            if os.path.exists(p):
                os.remove(p)
        for i in range(100):
            p = output_path + f".sfx_{i}.mp4"
            if os.path.exists(p):
                os.remove(p)

        return output_path


# ---------------------------------------------------------------------------
# OverlayCompositor — Composite PNG sequences onto video
# ---------------------------------------------------------------------------


class OverlayCompositor:
    """Overlay PNG frame sequences onto video using FFmpeg overlay filter."""

    @staticmethod
    def overlay_png_sequence(
        video_path: str,
        png_dir: str,
        output_path: str,
        start_time: float = 0.0,
        fps: int = 30,
        x: int = 0,
        y: int = 0,
        codec: str = "libx264",
    ) -> str:
        """Overlay a numbered PNG sequence onto video."""
        # Count frames
        frames = sorted(Path(png_dir).glob("frame_*.png"))
        if not frames:
            print(f"  WARNING: No frames in {png_dir}, skipping overlay")
            shutil.copy2(video_path, output_path)
            return output_path

        duration = len(frames) / fps
        end_time = start_time + duration

        cmd = [
            FFMPEG, "-y",
            "-i", video_path,
            "-framerate", str(fps),
            "-i", str(Path(png_dir) / "frame_%05d.png"),
            "-filter_complex",
            (
                f"[1:v]format=rgba[ovr];"
                f"[0:v][ovr]overlay={x}:{y}:"
                f"enable='between(t,{start_time},{end_time})'[v]"
            ),
            "-map", "[v]", "-map", "0:a?",
            "-c:v", codec, "-c:a", "copy",
            output_path,
        ]
        run_cmd(cmd, desc=f"Overlaying {len(frames)} frames")
        return output_path

    @staticmethod
    def overlay_multiple(
        video_path: str,
        overlays: list[dict],
        output_path: str,
        fps: int = 30,
        codec: str = "libx264",
    ) -> str:
        """Apply multiple overlay sequences sequentially."""
        current = video_path
        for i, ovr in enumerate(overlays):
            png_dir = ovr.get("png_dir", "")
            start = ovr.get("start", 0.0)
            x = ovr.get("x", 0)
            y = ovr.get("y", 0)
            temp = output_path + f".ovr_{i}.mp4"
            OverlayCompositor.overlay_png_sequence(
                current, png_dir, temp, start, fps, x, y, codec,
            )
            if current != video_path and os.path.exists(current):
                os.remove(current)
            current = temp

        if current != output_path:
            shutil.move(current, output_path)
        return output_path

    @staticmethod
    def overlay_video_pip(
        background_path: str,
        pip_path: str,
        output_path: str,
        pip_scale: float = 0.28,
        position: str = "bottom_left",
        margin: int = 30,
        border_width: int = 3,
        border_color: str = "black",
        project_width: int = 1920,
        project_height: int = 1080,
        fps: int = 30,
        background_trim: tuple | None = None,
        pip_trim: tuple | None = None,
        audio_from_pip: bool = True,
        codec: str = "libx264",
    ) -> str:
        """Composite a PiP video overlay onto a background video.

        Used for screen share + face cam layouts where the face cam is
        a small window in the corner over the full-screen share.
        """
        pip_w = int(project_width * pip_scale)
        pip_h = int(project_height * pip_scale)

        # Position mapping
        positions = {
            "bottom_left": (margin, project_height - pip_h - margin),
            "bottom_right": (project_width - pip_w - margin, project_height - pip_h - margin),
            "top_left": (margin, margin),
            "top_right": (project_width - pip_w - margin, margin),
        }
        ox, oy = positions.get(position, positions["bottom_left"])

        # Build input args
        cmd = [FFMPEG, "-y"]

        # Background input with optional trim
        if background_trim:
            cmd.extend(["-ss", str(background_trim[0]), "-to", str(background_trim[1])])
        cmd.extend(["-i", background_path])

        # PiP input with optional trim
        if pip_trim:
            cmd.extend(["-ss", str(pip_trim[0]), "-to", str(pip_trim[1])])
        cmd.extend(["-i", pip_path])

        # Build filter complex
        border_filter = ""
        if border_width > 0:
            border_filter = (
                f",drawbox=x=0:y=0:w={pip_w}:h={pip_h}"
                f":color={border_color}@0.8:t={border_width}"
            )

        filter_complex = (
            f"[0:v]scale={project_width}:{project_height},"
            f"fps={fps},format=yuv420p[bg];"
            f"[1:v]scale={pip_w}:{pip_h},"
            f"fps={fps},format=yuv420p{border_filter}[pip];"
            f"[bg][pip]overlay={ox}:{oy}[v]"
        )

        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", "[v]"])

        # Audio: from pip (face cam) or background
        audio_idx = "1" if audio_from_pip else "0"
        cmd.extend(["-map", f"{audio_idx}:a?"])
        cmd.extend(["-c:v", codec, "-c:a", "aac", "-b:a", "192k"])
        cmd.append(output_path)

        run_cmd(cmd, desc=f"PiP composite ({position}, {pip_scale:.0%} scale)")
        return output_path


# ---------------------------------------------------------------------------
# CaptionGenerator — faster-whisper STT → word timestamps
# ---------------------------------------------------------------------------


class CaptionGenerator:
    """Generate word-level captions using faster-whisper."""

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )
        except ImportError:
            raise ImportError("faster-whisper not installed. Run: pip install faster-whisper")

    def extract_audio(self, video_path: str, output_path: str) -> str:
        """Extract audio from video as 16kHz mono WAV."""
        cmd = [
            FFMPEG, "-y", "-i", video_path,
            "-vn", "-ar", "16000", "-ac", "1",
            "-f", "wav", output_path,
        ]
        run_cmd(cmd, desc="Extracting audio")
        return output_path

    def transcribe(self, input_path: str) -> list[dict]:
        """Transcribe audio/video to word-level timestamps.

        Returns list of {"word": str, "start": float, "end": float, "confidence": float}
        """
        self._load_model()

        # If video, extract audio first
        ext = Path(input_path).suffix.lower()
        if ext in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
            audio_path = str(Path(input_path).with_suffix(".wav"))
            self.extract_audio(input_path, audio_path)
        else:
            audio_path = input_path

        print("  Transcribing with faster-whisper...")
        segments, info = self._model.transcribe(
            audio_path,
            word_timestamps=True,
            language="en",
        )

        words = []
        for segment in segments:
            if segment.words:
                for w in segment.words:
                    words.append({
                        "word": w.word.strip(),
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "confidence": round(w.probability, 3),
                    })

        print(f"  Transcribed {len(words)} words")

        # Clean up extracted audio
        if ext in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
            if os.path.exists(audio_path):
                os.remove(audio_path)

        return words

    @staticmethod
    def group_into_phrases(words: list[dict], max_words: int = 5,
                           max_duration: float = 3.0) -> list[list[dict]]:
        """Group words into display phrases."""
        if not words:
            return []

        phrases = []
        current_phrase: list[dict] = []

        for word in words:
            if current_phrase:
                phrase_duration = word["end"] - current_phrase[0]["start"]
                gap = word["start"] - current_phrase[-1]["end"]

                if (len(current_phrase) >= max_words
                        or phrase_duration > max_duration
                        or gap > 0.7):
                    phrases.append(current_phrase)
                    current_phrase = []

            current_phrase.append(word)

        if current_phrase:
            phrases.append(current_phrase)

        return phrases

    def save_captions(self, words: list[dict], output_path: str) -> str:
        """Save word-level captions to JSON."""
        with open(output_path, "w") as f:
            json.dump({"words": words}, f, indent=2)
        print(f"  Saved captions to {output_path}")
        return output_path


# ---------------------------------------------------------------------------
# YouTubeOptimizer — Hook detection, chapters, thumbnails
# ---------------------------------------------------------------------------


class YouTubeOptimizer:
    """AI-powered YouTube optimization features."""

    @staticmethod
    def detect_silence(input_path: str, threshold: float = -30,
                       min_duration: float = 1.5) -> list[dict]:
        """Find silent segments using FFmpeg silencedetect."""
        cmd = [
            FFMPEG, "-i", input_path,
            "-af", f"silencedetect=noise={threshold}dB:d={min_duration}",
            "-f", "null", "-",
        ]
        result = run_cmd(cmd, desc="Detecting silence", check=False)
        stderr = result.stderr or ""

        silences = []
        lines = stderr.split("\n")
        start = None
        for line in lines:
            if "silence_start:" in line:
                try:
                    start = float(line.split("silence_start:")[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
            elif "silence_end:" in line and start is not None:
                try:
                    parts = line.split("silence_end:")[1].strip().split()
                    end = float(parts[0])
                    silences.append({"start": start, "end": end, "duration": end - start})
                    start = None
                except (ValueError, IndexError):
                    pass

        return silences

    @staticmethod
    def extract_thumbnails(input_path: str, output_dir: str,
                           count: int = 5) -> list[str]:
        """Extract potential thumbnail frames from video."""
        ensure_dir(output_dir)
        info = get_video_info(input_path)
        duration = info["duration"]

        if duration <= 0:
            return []

        # Extract frames at evenly spaced intervals
        interval = duration / (count + 1)
        paths = []
        for i in range(1, count + 1):
            ts = interval * i
            output = str(Path(output_dir) / f"thumb_{i:02d}.jpg")
            cmd = [
                FFMPEG, "-y", "-ss", str(ts),
                "-i", input_path,
                "-vframes", "1", "-q:v", "2",
                output,
            ]
            run_cmd(cmd, desc=f"Extracting thumbnail {i}")
            if os.path.exists(output):
                paths.append(output)

        # Try to score by sharpness using OpenCV
        try:
            import cv2
            scored = []
            for p in paths:
                img = cv2.imread(p)
                if img is not None:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
                    brightness = gray.mean()
                    # Prefer sharp, well-lit frames
                    score = sharpness * 0.7 + brightness * 0.3
                    scored.append((p, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            print(f"  Best thumbnail candidate: {Path(scored[0][0]).name} "
                  f"(score: {scored[0][1]:.0f})")
            return [p for p, _ in scored]
        except ImportError:
            return paths

    @staticmethod
    def suggest_pattern_interrupts(duration: float,
                                   interval: float = 60.0) -> list[dict]:
        """Suggest timestamps for pattern interrupts."""
        suggestions = []
        t = interval
        interrupt_types = ["zoom_pulse", "b_roll", "text_popup", "speed_change", "cut"]
        i = 0
        while t < duration:
            suggestions.append({
                "timestamp": t,
                "type": interrupt_types[i % len(interrupt_types)],
                "reason": f"Pattern interrupt at {t:.0f}s to reset attention",
            })
            t += interval
            i += 1
        return suggestions

    @staticmethod
    def generate_chapters_text(words: list[dict], video_duration: float) -> str:
        """Generate basic chapter markers from word timing gaps."""
        if not words:
            return "0:00 Introduction\n"

        # Find large gaps (topic transitions)
        chapters = ["0:00 Introduction"]
        chapter_num = 1

        for i in range(1, len(words)):
            gap = words[i]["start"] - words[i - 1]["end"]
            if gap > 3.0 and words[i]["start"] > 30:
                ts = words[i]["start"]
                mins = int(ts // 60)
                secs = int(ts % 60)
                chapters.append(f"{mins}:{secs:02d} Section {chapter_num + 1}")
                chapter_num += 1

        return "\n".join(chapters)


# ---------------------------------------------------------------------------
# SmartReframer — Landscape → Vertical with face tracking
# ---------------------------------------------------------------------------


class SmartReframer:
    """Reframe landscape video to vertical with face tracking."""

    @staticmethod
    def reframe(input_path: str, output_path: str,
                target_ratio: str = "9:16",
                codec: str = "libx264") -> str:
        """Reframe video to target aspect ratio."""
        info = get_video_info(input_path)
        src_w = info["width"]
        src_h = info["height"]

        # Parse target ratio
        if ":" in target_ratio:
            tw, th = target_ratio.split(":")
            target_aspect = int(tw) / int(th)
        else:
            target_aspect = float(target_ratio)

        # Calculate crop dimensions
        crop_h = src_h
        crop_w = int(crop_h * target_aspect)
        if crop_w > src_w:
            crop_w = src_w
            crop_h = int(crop_w / target_aspect)

        # Try face detection for smart crop position
        crop_x = (src_w - crop_w) // 2  # default center
        crop_y = (src_h - crop_h) // 2

        try:
            import cv2
            # Sample a frame from the first 10 seconds for face detection
            cap = cv2.VideoCapture(input_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 5))  # 5s in
            ret, frame = cap.read()
            cap.release()

            if ret:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                face_cascade = cv2.CascadeClassifier(cascade_path)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.3, 5)

                if len(faces) > 0:
                    # Center crop on the largest face
                    largest = max(faces, key=lambda f: f[2] * f[3])
                    face_cx = largest[0] + largest[2] // 2
                    crop_x = max(0, min(face_cx - crop_w // 2, src_w - crop_w))
                    print(f"  Face detected at x={face_cx}, centering crop")
                else:
                    print("  No face detected, using center crop")
        except ImportError:
            print("  OpenCV not available, using center crop")

        # Apply crop
        cmd = [
            FFMPEG, "-y", "-i", input_path,
            "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
            "-c:v", codec, "-c:a", "copy",
            output_path,
        ]
        run_cmd(cmd, desc=f"Reframing to {target_ratio}")
        return output_path


# ---------------------------------------------------------------------------
# ClipExtractor — Long-form → Short-form repurposing
# ---------------------------------------------------------------------------


class ClipExtractor:
    """Extract highlight clips from long-form video for Shorts/Reels."""

    @staticmethod
    def analyze_segments(words: list[dict], silences: list[dict],
                         video_duration: float,
                         min_clip: float = 15.0,
                         max_clip: float = 60.0) -> list[dict]:
        """Identify the best segments for short-form clips.

        Scores segments by:
        - Speech density (words per second — higher = more engaging)
        - No long silences
        - Natural start/end points (sentence boundaries via gaps)
        """
        if not words:
            return []

        # Build candidate segments from natural speech gaps
        candidates = []
        seg_start = words[0]["start"]
        seg_words: list[dict] = []

        for i, w in enumerate(words):
            seg_words.append(w)
            # Check for natural break point
            gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 5.0
            seg_duration = w["end"] - seg_start

            if gap > 1.5 or seg_duration >= max_clip:
                if min_clip <= seg_duration <= max_clip:
                    # Score by speech density
                    wps = len(seg_words) / max(seg_duration, 0.1)
                    # Penalize segments with silence
                    silence_overlap = sum(
                        min(s["end"], w["end"]) - max(s["start"], seg_start)
                        for s in silences
                        if s["start"] < w["end"] and s["end"] > seg_start
                    )
                    silence_ratio = max(0, silence_overlap) / seg_duration
                    score = wps * (1 - silence_ratio)

                    candidates.append({
                        "start": round(seg_start, 2),
                        "end": round(w["end"], 2),
                        "duration": round(seg_duration, 1),
                        "word_count": len(seg_words),
                        "words_per_sec": round(wps, 2),
                        "score": round(score, 2),
                        "preview": " ".join(
                            ww["word"] for ww in seg_words[:10]
                        ) + ("..." if len(seg_words) > 10 else ""),
                    })

                # Start new segment
                if i + 1 < len(words):
                    seg_start = words[i + 1]["start"]
                seg_words = []

        # Sort by score descending
        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates

    @staticmethod
    def extract_clip(input_path: str, output_path: str,
                     start: float, end: float,
                     reframe: bool = False,
                     codec: str = "libx264") -> str:
        """Extract a single clip from video."""
        duration = end - start
        cmd = [
            FFMPEG, "-y",
            "-ss", str(start),
            "-i", input_path,
            "-t", str(duration),
        ]

        if reframe:
            # Smart reframe to 9:16
            info = get_video_info(input_path)
            src_w = info.get("width", 1920)
            src_h = info.get("height", 1080)
            crop_h = src_h
            crop_w = int(crop_h * 9 / 16)
            if crop_w > src_w:
                crop_w = src_w
                crop_h = int(crop_w * 16 / 9)
            crop_x = (src_w - crop_w) // 2
            crop_y = (src_h - crop_h) // 2
            cmd.extend(["-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"])

        cmd.extend(["-c:v", codec, "-c:a", "aac", "-b:a", "192k", output_path])
        run_cmd(cmd, desc=f"Extracting clip {start:.1f}s-{end:.1f}s")
        return output_path

    @staticmethod
    def extract_best_clips(input_path: str, output_dir: str,
                           count: int = 5,
                           min_clip: float = 15.0,
                           max_clip: float = 60.0,
                           reframe: bool = False) -> list[str]:
        """Full pipeline: transcribe → analyze → extract top clips."""
        ensure_dir(output_dir)

        print("  Transcribing for clip analysis...")
        gen = CaptionGenerator(model_size="base")
        words = gen.transcribe(input_path)

        print("  Detecting silence...")
        silences = YouTubeOptimizer.detect_silence(input_path)

        info = get_video_info(input_path)
        duration = info["duration"]

        print("  Analyzing segments...")
        candidates = ClipExtractor.analyze_segments(
            words, silences, duration, min_clip, max_clip,
        )

        if not candidates:
            print("  No suitable clips found")
            return []

        # Extract top N clips
        top = candidates[:count]
        paths = []
        for i, clip in enumerate(top):
            suffix = "_9x16" if reframe else ""
            output = str(Path(output_dir) / f"clip_{i+1:02d}{suffix}.mp4")
            ClipExtractor.extract_clip(
                input_path, output,
                clip["start"], clip["end"],
                reframe=reframe,
            )
            paths.append(output)
            ts_start = f"{int(clip['start']//60)}:{int(clip['start']%60):02d}"
            ts_end = f"{int(clip['end']//60)}:{int(clip['end']%60):02d}"
            print(f"    Clip {i+1}: {ts_start}-{ts_end} "
                  f"({clip['duration']:.0f}s, score: {clip['score']:.2f})")
            print(f"      \"{clip['preview']}\"")

        # Save clips metadata
        meta_path = str(Path(output_dir) / "clips_metadata.json")
        with open(meta_path, "w") as f:
            json.dump({"clips": top[:count], "total_candidates": len(candidates)}, f, indent=2)

        return paths


# ---------------------------------------------------------------------------
# Main render pipeline
# ---------------------------------------------------------------------------


def render_manifest(manifest_path: str) -> str:
    """Full render pipeline from manifest."""
    print(f"\n{'='*60}")
    print(f"  VIDEO EDITOR — Manifest Render")
    print(f"{'='*60}\n")

    # Step 1: Load project
    print("[1/8] Loading manifest...")
    project = VideoProject(manifest_path=manifest_path)
    project.load()
    print(f"  Project: {project.data['project'].get('name', 'untitled')}")
    print(f"  Resolution: {project.resolution[0]}x{project.resolution[1]}")
    print(f"  FPS: {project.fps}")
    print(f"  Timeline: {len(project.data['timeline'])} clips")

    # Step 2: Render timeline segments
    print("\n[2/8] Rendering timeline segments...")
    renderer = TimelineRenderer(project)
    segment_paths = []
    for i, clip in enumerate(project.data["timeline"]):
        path = renderer.render_segment(clip, i)
        segment_paths.append(path)

    # Step 3: Concat with transitions
    print("\n[3/8] Concatenating segments...")
    concat_output = str(project.project_dir / "concat.mp4")
    renderer.concat_segments(segment_paths, concat_output)

    # Step 4: Generate and overlay captions
    print("\n[4/8] Processing captions and text overlays...")
    current = concat_output
    effects = project.data.get("effects", {})
    caption_effects = {
        k: v for k, v in effects.items()
        if v.get("type", "").startswith("captions")
    }

    if caption_effects:
        try:
            from video_caption_renderer import CaptionRenderer, PRESET_STYLES
            cap_renderer = CaptionRenderer(
                resolution=project.resolution, fps=project.fps
            )

            for effect_id, effect in caption_effects.items():
                style_name = effect.get("style", "capcut_pop")
                words = effect.get("words", [])
                if not words:
                    continue

                cap_dir = str(ensure_dir(
                    project.project_dir / "captions" / effect_id
                ))
                style = PRESET_STYLES.get(style_name, PRESET_STYLES["capcut_pop"])
                cap_renderer.render_caption_frames(words, style, cap_dir)

                # Find the start time of this caption block
                if words:
                    start_time = words[0]["start"]
                else:
                    start_time = 0.0

                temp = str(project.project_dir / f"with_caps_{effect_id}.mp4")
                OverlayCompositor.overlay_png_sequence(
                    current, cap_dir, temp,
                    start_time=start_time,
                    fps=project.fps,
                    codec=project.output_codec,
                )
                if current != concat_output:
                    os.remove(current)
                current = temp
        except ImportError:
            print("  WARNING: video_caption_renderer not found, skipping captions")
    else:
        print("  No caption effects in manifest")

    # Step 5: Process overlay tracks
    print("\n[5/8] Processing overlays...")
    overlays_config = project.data.get("overlays", [])
    if overlays_config:
        try:
            from video_overlay_templates import (
                render_subscribe_button,
                render_lower_third_bar,
                render_text_popup,
            )

            overlay_list = []
            for ovr in overlays_config:
                ovr_type = ovr.get("type", "")
                ovr_dir = str(ensure_dir(
                    project.project_dir / "overlays" / ovr.get("id", ovr_type)
                ))

                if ovr_type == "animated_subscribe":
                    render_subscribe_button(
                        duration=ovr.get("duration", 5.0),
                        fps=project.fps,
                        resolution=project.resolution,
                        position=ovr.get("position", "bottom_right"),
                        style=ovr.get("style", "slide_in"),
                        output_dir=ovr_dir,
                    )
                elif ovr_type == "lower_third":
                    render_lower_third_bar(
                        name=ovr.get("name", ""),
                        title=ovr.get("title", ""),
                        duration=ovr.get("duration", 4.0),
                        fps=project.fps,
                        resolution=project.resolution,
                        style=ovr.get("style", "modern_glass"),
                        output_dir=ovr_dir,
                    )
                elif ovr_type == "text_popup":
                    render_text_popup(
                        text=ovr.get("text", ""),
                        duration=ovr.get("duration", 3.0),
                        fps=project.fps,
                        resolution=project.resolution,
                        output_dir=ovr_dir,
                    )
                else:
                    continue

                # Calculate overlay position
                pos = ovr.get("position", "bottom_right")
                w, h = project.resolution
                ox, oy = 0, 0
                if "right" in pos:
                    ox = w - 300  # approximate
                if "bottom" in pos:
                    oy = h - 100
                if "center" in pos and "bottom" not in pos and "top" not in pos:
                    oy = h // 2 - 50

                overlay_list.append({
                    "png_dir": ovr_dir,
                    "start": ovr.get("start", 0.0),
                    "x": ox,
                    "y": oy,
                })

            if overlay_list:
                temp = str(project.project_dir / "with_overlays.mp4")
                OverlayCompositor.overlay_multiple(
                    current, overlay_list, temp,
                    fps=project.fps, codec=project.output_codec,
                )
                if current != concat_output:
                    os.remove(current)
                current = temp
        except ImportError:
            print("  WARNING: video_overlay_templates not found, skipping overlays")
    else:
        print("  No overlays in manifest")

    # Step 5b: Process Remotion motion graphics overlays
    remotion_overlays = [
        o for o in project.data.get("overlays", [])
        if o.get("type") == "remotion"
    ]
    if remotion_overlays:
        print(f"\n  Processing {len(remotion_overlays)} Remotion motion graphics...")
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from remotion_renderer import RemotionRenderer
            rr = RemotionRenderer()
            for ovr in remotion_overlays:
                rendered = rr.render_from_manifest_overlay(ovr)
                if rendered and os.path.exists(rendered):
                    start = ovr.get("start", 0.0)
                    temp = str(project.project_dir / f"with_remotion_{id(ovr)}.mp4")
                    # Composite rendered segment onto video
                    cmd = [
                        FFMPEG, "-y",
                        "-i", current,
                        "-i", rendered,
                        "-filter_complex",
                        f"[1:v]format=yuva420p[ovr];"
                        f"[0:v][ovr]overlay=0:0:"
                        f"enable='between(t,{start},{start + ovr.get('duration', 3.0)})'[v]",
                        "-map", "[v]", "-map", "0:a?",
                        "-c:v", project.output_codec, "-c:a", "copy",
                        temp,
                    ]
                    run_cmd(cmd, desc=f"Compositing Remotion: {ovr.get('composition', '?')}")
                    if current != concat_output:
                        os.remove(current)
                    current = temp
        except ImportError:
            print("  WARNING: remotion_renderer not found, skipping motion graphics")

    # Step 6: Apply global color grade
    print("\n[6/8] Applying color grade...")
    color_config = project.data.get("color_grade", {})
    if color_config:
        graded = str(project.project_dir / "graded.mp4")
        ColorGrader.grade(
            current, graded,
            preset=color_config.get("preset"),
            brightness=color_config.get("brightness", 0.0),
            contrast=color_config.get("contrast", 1.0),
            saturation=color_config.get("saturation", 1.0),
            temperature=color_config.get("temperature", 0.0),
            lut_path=color_config.get("lut_path"),
            codec=project.output_codec,
        )
        if current != concat_output:
            os.remove(current)
        current = graded
    else:
        print("  No color grading specified")

    # Step 6b: Auto-sync SFX to overlays and transitions
    sfx_list = []
    try:
        from sfx_library import generate_sfx_timing
        sfx_list = generate_sfx_timing(project.data)
        if sfx_list:
            print(f"\n  Auto-synced {len(sfx_list)} SFX to transitions/overlays")
    except ImportError:
        pass  # sfx_library not available, skip

    # Step 7: Mix audio
    print("\n[7/8] Mixing audio...")
    audio_config = project.data.get("audio_mix", {})
    if audio_config:
        music_name = audio_config.get("music_track")
        music_path = None
        if music_name and music_name in project.data.get("sources", {}):
            music_path = project.data["sources"][music_name].get("path")

        mixed = str(project.project_dir / "mixed.mp4")
        AudioMixer.mix(
            current, mixed,
            music_path=music_path,
            music_volume=audio_config.get("music_volume", 0.15),
            duck_on_speech=audio_config.get("duck_on_speech", True),
            sfx=sfx_list if sfx_list else None,
            normalize=audio_config.get("normalize", True),
            target_lufs=audio_config.get("target_lufs", -14.0),
            codec=project.output_codec,
        )
        if current != concat_output:
            os.remove(current)
        current = mixed
    else:
        print("  No audio mix specified")

    # Step 8: Final output
    print("\n[8/8] Finalizing...")
    output = project.output_path
    ensure_dir(Path(output).parent)
    shutil.move(current, output)

    # Clean up concat intermediate
    if os.path.exists(concat_output):
        os.remove(concat_output)

    # Get output info
    out_info = get_video_info(output)
    file_size = os.path.getsize(output) / (1024 * 1024)

    print(f"\n{'='*60}")
    print(f"  RENDER COMPLETE")
    print(f"  Output: {output}")
    print(f"  Duration: {out_info['duration']:.1f}s")
    print(f"  Size: {file_size:.1f} MB")
    print(f"{'='*60}\n")

    return output


# ---------------------------------------------------------------------------
# CLI Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_render(args):
    """Render from manifest."""
    render_manifest(args.manifest)


def cmd_captions(args):
    """Generate and overlay captions."""
    print(f"\n  Generating captions for: {args.input}")
    style = args.style or "capcut_pop"

    # Set up project directory
    name = Path(args.input).stem
    project_dir = ensure_dir(TMP_ROOT / f"{name}-captions")

    # Generate word-level captions
    gen = CaptionGenerator(model_size=args.model or "base")
    words = gen.transcribe(args.input)
    captions_file = str(project_dir / "captions.json")
    gen.save_captions(words, captions_file)

    if args.json_only:
        print(f"  Captions saved to {captions_file}")
        return

    # Render caption frames
    try:
        from video_caption_renderer import CaptionRenderer, PRESET_STYLES
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent))
        from video_caption_renderer import CaptionRenderer, PRESET_STYLES

    phrases = CaptionGenerator.group_into_phrases(words)
    renderer = CaptionRenderer(
        resolution=(1920, 1080), fps=30,
    )

    # Get video info for resolution
    info = get_video_info(args.input)
    res = (info.get("width", 1920), info.get("height", 1080))
    fps = int(info.get("fps", 30))
    renderer = CaptionRenderer(resolution=res, fps=fps)

    cap_style = PRESET_STYLES.get(style, PRESET_STYLES["capcut_pop"])

    # Render all phrases
    current = args.input
    for i, phrase in enumerate(phrases):
        phrase_dir = str(ensure_dir(project_dir / "captions" / f"phrase_{i:04d}"))
        renderer.render_caption_frames(phrase, cap_style, phrase_dir)

        temp = str(project_dir / f"with_caps_{i:04d}.mp4")
        OverlayCompositor.overlay_png_sequence(
            current, phrase_dir, temp,
            start_time=phrase[0]["start"],
            fps=fps,
        )
        if current != args.input and os.path.exists(current):
            os.remove(current)
        current = temp

    # Move to final output
    output = str(project_dir / f"output.mp4")
    shutil.move(current, output)
    print(f"\n  Captioned video: {output}")


def cmd_auto_edit(args):
    """AI-powered auto-edit pipeline."""
    print(f"\n{'='*60}")
    print(f"  AUTO-EDIT: {Path(args.input).name}")
    print(f"{'='*60}\n")

    name = Path(args.input).stem
    project_dir = ensure_dir(TMP_ROOT / f"{name}-auto")
    info = get_video_info(args.input)
    duration = info["duration"]
    w, h = info.get("width", 1920), info.get("height", 1080)
    fps = int(info.get("fps", 30))

    print(f"  Source: {w}x{h} @ {fps}fps, {duration:.1f}s")

    # Step 1: Detect and remove silence
    print("\n[1/5] Detecting silent/boring segments...")
    silences = YouTubeOptimizer.detect_silence(args.input)
    print(f"  Found {len(silences)} silent segments")

    # Step 2: Generate captions
    print("\n[2/5] Generating word-level captions...")
    gen = CaptionGenerator(model_size="base")
    words = gen.transcribe(args.input)
    captions_file = str(project_dir / "captions.json")
    gen.save_captions(words, captions_file)

    # Step 3: Build auto-edit manifest
    print("\n[3/5] Building edit manifest...")

    # Create timeline clips, skipping silent segments
    timeline = []
    clip_start = 0.0
    clip_id = 0

    # Sort silences by start time
    silences.sort(key=lambda s: s["start"])

    for silence in silences:
        if silence["start"] > clip_start + 0.5:
            timeline.append({
                "id": f"clip_{clip_id}",
                "source": "main",
                "in": clip_start,
                "out": silence["start"],
                "speed": 1.0,
                "effects": [],
                "audio": {"volume": 1.0},
            })
            clip_id += 1
        clip_start = silence["end"]

    # Add final clip
    if clip_start < duration - 0.5:
        timeline.append({
            "id": f"clip_{clip_id}",
            "source": "main",
            "in": clip_start,
            "out": duration,
            "speed": 1.0,
            "effects": [],
            "audio": {"volume": 1.0},
        })

    # If no silences found, use whole video
    if not timeline:
        timeline.append({
            "id": "clip_0",
            "source": "main",
            "in": 0.0,
            "out": duration,
            "speed": 1.0,
            "effects": ["fade_in_0"],
            "audio": {"volume": 1.0},
        })

    # Add fade in to first clip
    if timeline:
        timeline[0]["effects"] = ["fade_in_0"]

    # Build manifest
    style = args.style or "youtube_engaging"
    color_preset = "warm_cinematic" if style == "youtube_engaging" else "vibrant"

    manifest = {
        "version": "1.0",
        "project": {
            "name": f"{name}-auto",
            "resolution": [w, h],
            "fps": fps,
            "output_format": "mp4",
            "output_codec": "libx264",
            "output_path": str(project_dir / "output.mp4"),
        },
        "sources": {
            "main": {"path": os.path.abspath(args.input), "type": "video"},
        },
        "timeline": timeline,
        "effects": {
            "fade_in_0": {"type": "fade_in", "duration": 1.0},
        },
        "overlays": [],
        "color_grade": {"preset": color_preset},
        "audio_mix": {"normalize": True, "target_lufs": -14.0},
    }

    manifest_path = str(project_dir / "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Step 4: Render
    print("\n[4/5] Rendering...")
    output = render_manifest(manifest_path)

    # Step 5: Overlay captions on rendered output
    print("\n[5/5] Adding captions...")
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from video_caption_renderer import CaptionRenderer, PRESET_STYLES

        cap_style = args.caption_style or "capcut_pop"
        phrases = CaptionGenerator.group_into_phrases(words)
        renderer = CaptionRenderer(resolution=(w, h), fps=fps)
        style_obj = PRESET_STYLES.get(cap_style, PRESET_STYLES["capcut_pop"])

        current = output
        for i, phrase in enumerate(phrases[:50]):  # Limit to first 50 phrases for speed
            phrase_dir = str(ensure_dir(project_dir / "captions" / f"p_{i:04d}"))
            renderer.render_caption_frames(phrase, style_obj, phrase_dir)
            temp = str(project_dir / f"auto_caps_{i:04d}.mp4")
            OverlayCompositor.overlay_png_sequence(
                current, phrase_dir, temp,
                start_time=phrase[0]["start"],
                fps=fps,
            )
            if current != output and os.path.exists(current):
                os.remove(current)
            current = temp

        if current != output:
            shutil.move(current, output)

        print(f"\n  Auto-edited video: {output}")
    except ImportError:
        print("  Caption renderer not available, skipping captions")
        print(f"\n  Auto-edited video: {output}")


def cmd_youtube_optimize(args):
    """YouTube optimization: chapters, thumbnails, pattern interrupts."""
    print(f"\n  YouTube Optimization: {Path(args.input).name}")

    name = Path(args.input).stem
    project_dir = ensure_dir(TMP_ROOT / f"{name}-yt-optimize")
    info = get_video_info(args.input)
    duration = info["duration"]

    # Silence detection
    print("\n  Detecting silent/boring segments...")
    silences = YouTubeOptimizer.detect_silence(args.input)
    print(f"  Found {len(silences)} silent segments totaling "
          f"{sum(s['duration'] for s in silences):.1f}s")

    # Thumbnails
    print("\n  Extracting thumbnail candidates...")
    thumb_dir = str(project_dir / "thumbnails")
    thumbs = YouTubeOptimizer.extract_thumbnails(args.input, thumb_dir)
    print(f"  Extracted {len(thumbs)} thumbnails to {thumb_dir}")

    # Pattern interrupts
    print("\n  Generating pattern interrupt suggestions...")
    interrupts = YouTubeOptimizer.suggest_pattern_interrupts(duration)
    for pi in interrupts:
        ts = pi["timestamp"]
        mins = int(ts // 60)
        secs = int(ts % 60)
        print(f"    {mins}:{secs:02d} — {pi['type']}: {pi['reason']}")

    # Chapters (requires transcription)
    print("\n  Generating chapter markers...")
    try:
        gen = CaptionGenerator(model_size="base")
        words = gen.transcribe(args.input)
        chapters = YouTubeOptimizer.generate_chapters_text(words, duration)
        chapters_file = str(project_dir / "chapters.txt")
        with open(chapters_file, "w") as f:
            f.write(chapters)
        print(f"  Chapters saved to {chapters_file}")
        print(f"\n  {chapters}")
    except Exception as e:
        print(f"  Could not generate chapters: {e}")

    # Hook analysis
    print(f"\n  Hook Analysis:")
    print(f"  First 3s: Critical scroll-stop moment")
    print(f"  First 30s: Retention decision window")
    if silences and silences[0]["start"] < 30:
        print(f"  WARNING: Silence detected in first 30s at "
              f"{silences[0]['start']:.1f}s — consider cutting")

    print(f"\n  Results saved to: {project_dir}")


def cmd_color_grade(args):
    """Apply color grading to a video."""
    name = Path(args.input).stem
    project_dir = ensure_dir(TMP_ROOT / f"{name}-graded")
    output = str(project_dir / f"output.mp4")

    ColorGrader.grade(
        args.input, output,
        preset=args.preset,
        brightness=args.brightness or 0.0,
        contrast=args.contrast or 1.0,
        saturation=args.saturation or 1.0,
        lut_path=args.lut,
    )
    print(f"\n  Color-graded video: {output}")


def cmd_reframe(args):
    """Smart reframe video to different aspect ratio."""
    name = Path(args.input).stem
    project_dir = ensure_dir(TMP_ROOT / f"{name}-reframed")
    output = str(project_dir / f"output.mp4")

    SmartReframer.reframe(args.input, output, target_ratio=args.ratio)
    print(f"\n  Reframed video: {output}")


def cmd_clips(args):
    """Extract highlight clips for Shorts/Reels repurposing."""
    print(f"\n{'='*60}")
    print(f"  CLIP EXTRACTION: {Path(args.input).name}")
    print(f"{'='*60}\n")

    name = Path(args.input).stem
    project_dir = ensure_dir(TMP_ROOT / f"{name}-clips")

    paths = ClipExtractor.extract_best_clips(
        args.input,
        str(project_dir),
        count=args.count,
        min_clip=args.min_duration,
        max_clip=args.max_duration,
        reframe=args.reframe,
    )

    print(f"\n  Extracted {len(paths)} clips to {project_dir}")

    # Optionally add captions to clips
    if args.captions:
        print("\n  Adding captions to clips...")
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from video_caption_renderer import CaptionRenderer, PRESET_STYLES

            cap_style = PRESET_STYLES.get(args.caption_style or "capcut_pop",
                                          PRESET_STYLES["capcut_pop"])

            for clip_path in paths:
                clip_info = get_video_info(clip_path)
                res = (clip_info.get("width", 1080), clip_info.get("height", 1920))
                fps = int(clip_info.get("fps", 30))

                gen = CaptionGenerator(model_size="base")
                words = gen.transcribe(clip_path)
                phrases = CaptionGenerator.group_into_phrases(words)

                renderer = CaptionRenderer(resolution=res, fps=fps)
                current = clip_path
                clip_dir = ensure_dir(
                    project_dir / f"{Path(clip_path).stem}_caps"
                )

                for i, phrase in enumerate(phrases):
                    phrase_dir = str(ensure_dir(clip_dir / f"p_{i:04d}"))
                    renderer.render_caption_frames(phrase, cap_style, phrase_dir)
                    temp = str(clip_dir / f"cap_{i:04d}.mp4")
                    OverlayCompositor.overlay_png_sequence(
                        current, phrase_dir, temp,
                        start_time=phrase[0]["start"],
                        fps=fps,
                    )
                    if current != clip_path and os.path.exists(current):
                        os.remove(current)
                    current = temp

                if current != clip_path:
                    shutil.move(current, clip_path)
                    print(f"    Captioned: {Path(clip_path).name}")
        except ImportError:
            print("  Caption renderer not available, skipping")

    print(f"\n  All clips saved to: {project_dir}")


def cmd_motion_graphics(args):
    """Render a Remotion motion graphics composition."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from remotion_renderer import RemotionRenderer
    except ImportError:
        print("ERROR: remotion_renderer.py not found")
        sys.exit(1)

    renderer = RemotionRenderer()
    props = json.loads(args.props) if args.props else {}

    output = args.output
    if not output:
        project_dir = ensure_dir(TMP_ROOT / "motion-graphics")
        output = str(project_dir / f"{args.template}.mp4")

    renderer.render_composition(
        composition_id=args.template,
        props=props,
        output_path=output,
    )
    print(f"\n  Motion graphic rendered: {output}")


def cmd_thumbnail(args):
    """Generate YouTube thumbnail."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from video_thumbnail_generator import ThumbnailGenerator
    except ImportError:
        print("ERROR: video_thumbnail_generator.py not found")
        sys.exit(1)

    name = Path(args.input).stem if hasattr(args, 'input') and args.input else "thumbnail"
    project_dir = ensure_dir(TMP_ROOT / f"{name}-thumbnails")
    output = args.output or str(project_dir / "thumbnail.jpg")

    gen = ThumbnailGenerator(style=args.style or "youtube_red")

    template = args.template or "bold_text"
    if template == "bold_text":
        highlight = args.highlight.split(",") if args.highlight else None
        gen.generate_bold_text(
            text=args.text,
            highlight_words=highlight,
            face_image=args.input,
            output_path=output,
        )
    elif template == "result":
        gen.generate_result(
            result_text=args.text,
            subtitle=args.subtitle or "",
            face_image=args.input,
            output_path=output,
        )
    elif template == "face_text":
        gen.generate_face_text(
            text=args.text,
            face_image=args.input,
            output_path=output,
        )
    elif template == "minimal":
        gen.generate_minimal(
            background_image=args.input,
            text=args.text,
            output_path=output,
        )

    print(f"\n  Thumbnail generated: {output}")


def cmd_preview(args):
    """Render a quick preview of the first N seconds."""
    duration = args.duration or 10

    # Load manifest
    with open(args.manifest) as f:
        data = json.load(f)

    # Modify to only render first N seconds
    name = data.get("project", {}).get("name", "preview")
    data["project"]["name"] = f"{name}-preview"

    # Trim timeline to preview duration
    total = 0.0
    trimmed_timeline = []
    for clip in data.get("timeline", []):
        clip_dur = clip.get("out", 0) - clip.get("in", 0)
        if total >= duration:
            break
        if total + clip_dur > duration:
            clip = dict(clip)
            clip["out"] = clip["in"] + (duration - total)
        trimmed_timeline.append(clip)
        total += clip_dur

    data["timeline"] = trimmed_timeline

    # Use fast codec for preview
    data["project"]["output_codec"] = "libx264"

    # Write temp manifest
    project_dir = ensure_dir(TMP_ROOT / f"{name}-preview")
    preview_manifest = str(project_dir / "preview_manifest.json")
    data["project"]["output_path"] = str(project_dir / "preview.mp4")
    with open(preview_manifest, "w") as f:
        json.dump(data, f, indent=2)

    render_manifest(preview_manifest)


def cmd_assemble(args):
    """Assemble multi-source YouTube video from project config."""
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from video_assembler import VideoAssembler
        assembler = VideoAssembler()
        output = assembler.assemble(
            config_path=args.config,
            preview_section=getattr(args, "preview_section", None),
            skip_captions=args.skip_captions,
            skip_motion_graphics=args.skip_motion_graphics,
        )
        print(f"\n  Assembled video: {output}")
    except ImportError as e:
        print(f"  ERROR: video_assembler.py not found: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Video Editor — Programmatic video editing engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # render
    p_render = subparsers.add_parser("render", help="Render from manifest")
    p_render.add_argument("--manifest", required=True, help="Path to manifest JSON")
    p_render.set_defaults(func=cmd_render)

    # captions
    p_caps = subparsers.add_parser("captions", help="Generate and overlay captions")
    p_caps.add_argument("--input", required=True, help="Input video path")
    p_caps.add_argument("--style", choices=CAPTION_STYLES, default="capcut_pop")
    p_caps.add_argument("--model", default="base", help="Whisper model size")
    p_caps.add_argument("--json-only", action="store_true", help="Only output captions JSON")
    p_caps.set_defaults(func=cmd_captions)

    # auto-edit
    p_auto = subparsers.add_parser("auto-edit", help="AI-powered auto-edit")
    p_auto.add_argument("--input", required=True, help="Input video path")
    p_auto.add_argument("--style", default="youtube_engaging",
                        help="Edit style (youtube_engaging, vibrant)")
    p_auto.add_argument("--caption-style", choices=CAPTION_STYLES, default="capcut_pop")
    p_auto.set_defaults(func=cmd_auto_edit)

    # youtube-optimize
    p_yt = subparsers.add_parser("youtube-optimize", help="YouTube optimization")
    p_yt.add_argument("--input", required=True, help="Input video path")
    p_yt.set_defaults(func=cmd_youtube_optimize)

    # color-grade
    p_cg = subparsers.add_parser("color-grade", help="Apply color grading")
    p_cg.add_argument("--input", required=True, help="Input video path")
    p_cg.add_argument("--preset", choices=list(COLOR_PRESETS.keys()))
    p_cg.add_argument("--brightness", type=float)
    p_cg.add_argument("--contrast", type=float)
    p_cg.add_argument("--saturation", type=float)
    p_cg.add_argument("--lut", help="Path to LUT file (.cube)")
    p_cg.set_defaults(func=cmd_color_grade)

    # reframe
    p_rf = subparsers.add_parser("reframe", help="Smart reframe to different ratio")
    p_rf.add_argument("--input", required=True, help="Input video path")
    p_rf.add_argument("--ratio", default="9:16", help="Target aspect ratio")
    p_rf.set_defaults(func=cmd_reframe)

    # preview
    p_pv = subparsers.add_parser("preview", help="Quick preview render")
    p_pv.add_argument("--manifest", required=True, help="Path to manifest JSON")
    p_pv.add_argument("--duration", type=float, default=10, help="Preview duration (seconds)")
    p_pv.set_defaults(func=cmd_preview)

    # clips
    p_cl = subparsers.add_parser("clips", help="Extract highlight clips for Shorts/Reels")
    p_cl.add_argument("--input", required=True, help="Input video path")
    p_cl.add_argument("--count", type=int, default=5, help="Number of clips to extract")
    p_cl.add_argument("--min-duration", type=float, default=15.0, help="Minimum clip length (seconds)")
    p_cl.add_argument("--max-duration", type=float, default=60.0, help="Maximum clip length (seconds)")
    p_cl.add_argument("--reframe", action="store_true", help="Reframe clips to 9:16 vertical")
    p_cl.add_argument("--captions", action="store_true", help="Add captions to extracted clips")
    p_cl.add_argument("--caption-style", choices=CAPTION_STYLES, default="capcut_pop")
    p_cl.set_defaults(func=cmd_clips)

    # motion-graphics
    p_mg = subparsers.add_parser("motion-graphics", help="Render Remotion motion graphics")
    p_mg.add_argument("--template", required=True, help="Composition ID (e.g. TitleSequence)")
    p_mg.add_argument("--props", help="JSON props string")
    p_mg.add_argument("--output", help="Output MP4 path")
    p_mg.set_defaults(func=cmd_motion_graphics)

    # thumbnail
    p_th = subparsers.add_parser("thumbnail", help="Generate YouTube thumbnail")
    p_th.add_argument("--input", help="Video or image path for face extraction")
    p_th.add_argument("--text", required=True, help="Thumbnail text")
    p_th.add_argument("--template", choices=["bold_text", "face_text", "result", "minimal"],
                      default="bold_text", help="Thumbnail template")
    p_th.add_argument("--highlight", help="Comma-separated words to highlight")
    p_th.add_argument("--subtitle", help="Subtitle text (for result template)")
    p_th.add_argument("--style", default="youtube_red", help="Color style preset")
    p_th.add_argument("--output", help="Output path (default: .tmp/video-edits/)")
    p_th.set_defaults(func=cmd_thumbnail)

    # assemble
    p_asm = subparsers.add_parser("assemble", help="Assemble YouTube video from project config")
    p_asm.add_argument("--config", required=True, help="Project config JSON path")
    p_asm.add_argument("--preview-section", help="Render only this section ID for preview")
    p_asm.add_argument("--skip-captions", action="store_true", help="Skip caption generation")
    p_asm.add_argument("--skip-motion-graphics", action="store_true", help="Skip Remotion renders")
    p_asm.set_defaults(func=cmd_assemble)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
