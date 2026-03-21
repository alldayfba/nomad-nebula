#!/usr/bin/env python3
"""
video_caption_renderer.py -- Pillow-based text frame renderer for video captions,
titles, and lower thirds.

Needed because the system's FFmpeg build lacks drawtext (no libfreetype).
All text rendering goes through Pillow -> RGBA PNG frames -> FFmpeg overlay filter.

Usage:
    # Captions from word-level JSON
    python video_caption_renderer.py captions --words captions.json --style capcut_pop \
        --resolution 1920x1080 --fps 30 --output-dir .tmp/captions/

    # Title card
    python video_caption_renderer.py title --text "How I Made \$14K in 48 Hours" \
        --style capcut_pop --duration 3.0 --output-dir .tmp/title/

    # Lower third
    python video_caption_renderer.py lower-third --name "Sabbo" --title "Amazon FBA Coach" \
        --duration 4.0 --output-dir .tmp/lower-third/
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hex_to_rgba(hex_color: str) -> Tuple[int, int, int, int]:
    """Convert '#RRGGBB' or '#RRGGBBAA' to (R, G, B, A)."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (r, g, b, 255)
    elif len(h) == 8:
        r, g, b, a = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
        return (r, g, b, a)
    raise ValueError(f"Invalid hex color: {hex_color}")


def draw_text_with_stroke(
    draw: ImageDraw.ImageDraw,
    position: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Tuple[int, int, int, int],
    stroke_color: str,
    stroke_width: int,
) -> None:
    """Draw text with an outline by rendering in 8 directions + center."""
    x, y = position
    if stroke_width > 0:
        sc = hex_to_rgba(stroke_color)
        offsets = [
            (-1, -1), (0, -1), (1, -1),
            (-1,  0),          (1,  0),
            (-1,  1), (0,  1), (1,  1),
        ]
        for sw in range(1, stroke_width + 1):
            for ox, oy in offsets:
                draw.text((x + ox * sw, y + oy * sw), text, font=font, fill=sc)
    draw.text((x, y), text, font=font, fill=fill)


def group_words_into_phrases(
    words: List[Dict],
    max_words: int = 5,
    max_duration: float = 3.0,
) -> List[List[Dict]]:
    """Group words into display phrases by count and duration constraints."""
    if not words:
        return []
    phrases: List[List[Dict]] = []
    current: List[Dict] = []
    for w in words:
        if not current:
            current.append(w)
            continue
        phrase_dur = w["end"] - current[0]["start"]
        gap = w["start"] - current[-1]["end"]
        if len(current) >= max_words or phrase_dur > max_duration or gap > 0.7:
            phrases.append(current)
            current = [w]
        else:
            current.append(w)
    if current:
        phrases.append(current)
    return phrases


# ---------------------------------------------------------------------------
# CaptionStyle
# ---------------------------------------------------------------------------

@dataclass
class CaptionStyle:
    """All visual parameters for caption rendering."""
    font_name: str = "Helvetica"
    font_size: int = 64
    color: str = "#FFFFFF"
    highlight_color: str = "#FFD700"
    stroke_color: str = "#000000"
    stroke_width: int = 3
    bg_color: Optional[str] = None
    position: str = "bottom_center"
    y_offset: int = -100
    highlight_scale: float = 1.2
    shadow_offset: Tuple[int, int] = (3, 3)
    shadow_color: str = "#000000"
    shadow_opacity: int = 128


PRESET_STYLES: Dict[str, CaptionStyle] = {
    "capcut_pop": CaptionStyle(
        font_name="Montserrat-Bold", font_size=72, color="#FFFFFF",
        highlight_color="#FFD700", stroke_color="#000000", stroke_width=4,
        highlight_scale=1.2, position="bottom_center", y_offset=-120,
    ),
    "subtitle_bar": CaptionStyle(
        font_name="Helvetica", font_size=48, color="#FFFFFF",
        stroke_width=0, bg_color="#000000AA", position="bottom_center", y_offset=-60,
    ),
    "karaoke": CaptionStyle(
        font_name="Impact", font_size=64, color="#666666",
        highlight_color="#FFFFFF", stroke_color="#000000", stroke_width=2,
        position="bottom_center", y_offset=-100,
    ),
    "minimal": CaptionStyle(
        font_name="Helvetica-Light", font_size=42, color="#FFFFFF",
        stroke_width=0, shadow_offset=(2, 2), shadow_color="#000000",
        shadow_opacity=100, position="bottom_center", y_offset=-80,
    ),
    "bold_outline": CaptionStyle(
        font_name="Arial-Black", font_size=80, color="#FFFFFF",
        stroke_color="#000000", stroke_width=6, position="center", y_offset=0,
    ),
}


# ---------------------------------------------------------------------------
# FontFinder
# ---------------------------------------------------------------------------

class FontFinder:
    """Discover fonts on macOS with caching."""

    _cache: Dict[str, str] = {}

    SEARCH_DIRS = [
        "/System/Library/Fonts/",
        "/Library/Fonts/",
        os.path.expanduser("~/Library/Fonts/"),
    ]

    FALLBACK = "/System/Library/Fonts/Helvetica.ttc"

    @classmethod
    def find_font(cls, name: str) -> str:
        if name in cls._cache:
            return cls._cache[name]

        # Direct path
        if os.path.isfile(name):
            cls._cache[name] = name
            return name

        target = name.lower()
        candidates: List[Tuple[int, str]] = []  # (priority, path)

        for search_dir in cls.SEARCH_DIRS:
            if not os.path.isdir(search_dir):
                continue
            for root, _dirs, files in os.walk(search_dir):
                for f in files:
                    if not f.lower().endswith((".ttf", ".ttc", ".otf")):
                        continue
                    stem = os.path.splitext(f)[0].lower()
                    full = os.path.join(root, f)
                    if stem == target:
                        cls._cache[name] = full
                        return full
                    if target in stem or target.replace("-", "") in stem.replace("-", ""):
                        candidates.append((len(stem), full))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            best = candidates[0][1]
            cls._cache[name] = best
            return best

        cls._cache[name] = cls.FALLBACK
        return cls.FALLBACK


# ---------------------------------------------------------------------------
# CaptionRenderer
# ---------------------------------------------------------------------------

class CaptionRenderer:
    """Render caption frames, title cards, and lower thirds as RGBA PNGs."""

    def __init__(self, resolution: Tuple[int, int] = (1920, 1080), fps: int = 30):
        self.width, self.height = resolution
        self.fps = fps

    # -- internal helpers --------------------------------------------------

    def _resolve_style(self, style: CaptionStyle | str) -> CaptionStyle:
        if isinstance(style, str):
            if style not in PRESET_STYLES:
                raise ValueError(f"Unknown preset '{style}'. Choose from: {list(PRESET_STYLES.keys())}")
            return PRESET_STYLES[style]
        return style

    def _load_font(self, name: str, size: int) -> ImageFont.FreeTypeFont:
        path = FontFinder.find_font(name)
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.truetype(FontFinder.FALLBACK, size)

    def _anchor_y(self, style: CaptionStyle, text_height: int) -> int:
        if style.position == "top_center":
            base = int(self.height * 0.1)
        elif style.position == "center":
            base = (self.height - text_height) // 2
        else:  # bottom_center
            base = int(self.height * 0.85) - text_height
        return base + style.y_offset

    def _measure_text(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def _ensure_dir(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)

    # -- render captions ---------------------------------------------------

    def render_caption_frames(
        self,
        words: List[Dict],
        style: CaptionStyle | str,
        output_dir: str,
    ) -> int:
        """Render word-by-word highlighted caption frames.

        Args:
            words: list of {"word": str, "start": float, "end": float}
            style: CaptionStyle instance or preset name string
            output_dir: directory to write frame_NNNNN.png files

        Returns:
            Total frame count written.
        """
        st = self._resolve_style(style)
        self._ensure_dir(output_dir)

        phrases = group_words_into_phrases(words)
        if not phrases:
            return 0

        font_normal = self._load_font(st.font_name, st.font_size)
        font_highlight = self._load_font(st.font_name, int(st.font_size * st.highlight_scale))

        # Determine style behavior
        style_name = style if isinstance(style, str) else ""
        uses_word_highlight = style_name in ("capcut_pop", "karaoke")
        uses_scale = style_name == "capcut_pop"

        color_normal = hex_to_rgba(st.color)
        color_highlight = hex_to_rgba(st.highlight_color)
        shadow_rgba = hex_to_rgba(st.shadow_color)[:3] + (st.shadow_opacity,)

        # We need a scratch draw for measurements
        scratch = Image.new("RGBA", (1, 1))
        scratch_draw = ImageDraw.Draw(scratch)

        total_start = phrases[0][0]["start"]
        total_end = phrases[-1][-1]["end"]
        total_frames = math.ceil((total_end - total_start) * self.fps)

        frame_idx = 0

        for phrase in phrases:
            phrase_start = phrase[0]["start"]
            phrase_end = phrase[-1]["end"]
            f_start = int((phrase_start - total_start) * self.fps)
            f_end = int(math.ceil((phrase_end - total_start) * self.fps))

            for fi in range(f_start, f_end):
                t = total_start + fi / self.fps
                img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                # Find active word index
                active_idx = -1
                for wi, w in enumerate(phrase):
                    if w["start"] <= t < w["end"]:
                        active_idx = wi
                        break
                # If no exact match, use nearest
                if active_idx == -1:
                    for wi, w in enumerate(phrase):
                        if t < w["start"]:
                            active_idx = wi
                            break
                    else:
                        active_idx = len(phrase) - 1

                # Measure each word and compute total width
                word_metrics: List[Tuple[str, ImageFont.FreeTypeFont, int, int, Tuple[int, int, int, int]]] = []
                spacing = int(st.font_size * 0.35)  # space between words

                for wi, w in enumerate(phrase):
                    is_active = (wi == active_idx) and uses_word_highlight
                    fnt = font_highlight if (is_active and uses_scale) else font_normal
                    clr = color_highlight if is_active else color_normal
                    tw, th = self._measure_text(scratch_draw, w["word"], fnt)
                    word_metrics.append((w["word"], fnt, tw, th, clr))

                total_w = sum(m[2] for m in word_metrics) + spacing * (len(word_metrics) - 1)
                max_h = max(m[3] for m in word_metrics)
                y_base = self._anchor_y(st, max_h)

                # Draw background bar if needed
                if st.bg_color:
                    bg_rgba = hex_to_rgba(st.bg_color)
                    pad_x, pad_y = 20, 10
                    x0 = (self.width - total_w) // 2 - pad_x
                    draw.rectangle(
                        [x0, y_base - pad_y, x0 + total_w + 2 * pad_x, y_base + max_h + pad_y],
                        fill=bg_rgba,
                    )

                # Draw each word
                cursor_x = (self.width - total_w) // 2
                for word_text, fnt, tw, th, clr in word_metrics:
                    # Vertically center each word relative to max height
                    wy = y_base + (max_h - th) // 2

                    # Shadow
                    if st.shadow_offset != (0, 0) and st.stroke_width == 0:
                        sx = cursor_x + st.shadow_offset[0]
                        sy = wy + st.shadow_offset[1]
                        draw.text((sx, sy), word_text, font=fnt, fill=shadow_rgba)

                    # Stroke + fill
                    draw_text_with_stroke(
                        draw, (cursor_x, wy), word_text, fnt,
                        fill=clr,
                        stroke_color=st.stroke_color,
                        stroke_width=st.stroke_width,
                    )
                    cursor_x += tw + spacing

                out_path = os.path.join(output_dir, f"frame_{frame_idx:05d}.png")
                img.save(out_path, "PNG")
                frame_idx += 1

        return frame_idx

    # -- render title ------------------------------------------------------

    def render_title(
        self,
        text: str,
        style: CaptionStyle | str,
        duration: float,
        output_dir: str,
        animation: str = "fade_in",
    ) -> int:
        """Render an animated title card.

        Animations: fade_in, scale_up, typewriter.
        Returns frame count.
        """
        st = self._resolve_style(style)
        self._ensure_dir(output_dir)
        font = self._load_font(st.font_name, st.font_size)
        total_frames = int(duration * self.fps)
        anim_frames = int(0.5 * self.fps)  # 0.5s transition

        scratch = Image.new("RGBA", (1, 1))
        sd = ImageDraw.Draw(scratch)
        tw, th = self._measure_text(sd, text, font)

        color = hex_to_rgba(st.color)

        for fi in range(total_frames):
            progress = min(fi / max(anim_frames, 1), 1.0)

            if animation == "typewriter":
                # Reveal letters over anim period
                chars = max(1, int(len(text) * progress))
                visible_text = text[:chars] if fi < anim_frames else text
                img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                vtw, vth = self._measure_text(draw, visible_text, font)
                x = (self.width - vtw) // 2
                y = self._anchor_y(st, vth)
                draw_text_with_stroke(
                    draw, (x, y), visible_text, font,
                    fill=color, stroke_color=st.stroke_color, stroke_width=st.stroke_width,
                )

            elif animation == "scale_up":
                scale = 0.8 + 0.2 * progress if fi < anim_frames else 1.0
                scaled_size = max(8, int(st.font_size * scale))
                sfont = self._load_font(st.font_name, scaled_size)
                img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                stw, sth = self._measure_text(draw, text, sfont)
                x = (self.width - stw) // 2
                y = self._anchor_y(st, sth)
                draw_text_with_stroke(
                    draw, (x, y), text, sfont,
                    fill=color, stroke_color=st.stroke_color, stroke_width=st.stroke_width,
                )

            else:  # fade_in
                alpha = int(255 * progress) if fi < anim_frames else 255
                fade_color = color[:3] + (alpha,)
                img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                x = (self.width - tw) // 2
                y = self._anchor_y(st, th)
                # For fade, render onto temp layer and composite with alpha
                layer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
                layer_draw = ImageDraw.Draw(layer)
                draw_text_with_stroke(
                    layer_draw, (x, y), text, font,
                    fill=color, stroke_color=st.stroke_color, stroke_width=st.stroke_width,
                )
                if alpha < 255:
                    # Apply global alpha
                    r, g, b, a = layer.split()
                    from PIL import ImageEnhance
                    a = a.point(lambda p: int(p * alpha / 255))
                    layer = Image.merge("RGBA", (r, g, b, a))
                img = Image.alpha_composite(img, layer)

            out_path = os.path.join(output_dir, f"frame_{fi:05d}.png")
            img.save(out_path, "PNG")

        return total_frames

    # -- render lower third ------------------------------------------------

    def render_lower_third(
        self,
        name: str,
        title: str,
        style: str,
        duration: float,
        output_dir: str,
    ) -> int:
        """Render an animated lower-third bar.

        Slides in from left (10 frames), holds, slides out right (10 frames).
        Returns frame count.
        """
        st = self._resolve_style(style)
        self._ensure_dir(output_dir)

        font_name = self._load_font(st.font_name, st.font_size)
        font_title = self._load_font(st.font_name, int(st.font_size * 0.6))

        total_frames = int(duration * self.fps)
        slide_frames = 10

        scratch = Image.new("RGBA", (1, 1))
        sd = ImageDraw.Draw(scratch)
        nw, nh = self._measure_text(sd, name, font_name)
        tw, th = self._measure_text(sd, title, font_title)

        bar_w = max(nw, tw) + 60
        bar_h = nh + th + 30
        bar_y = int(self.height * 0.78)
        bar_x_final = 40  # left margin when fully visible

        bar_bg = hex_to_rgba(st.bg_color if st.bg_color else "#000000CC")
        name_color = hex_to_rgba(st.color)
        title_color = hex_to_rgba(st.highlight_color)

        for fi in range(total_frames):
            img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Calculate bar x position for slide animation
            if fi < slide_frames:
                # Slide in from left
                progress = fi / max(slide_frames - 1, 1)
                bar_x = int(-bar_w + (bar_w + bar_x_final) * progress)
            elif fi >= total_frames - slide_frames:
                # Slide out to left
                progress = (fi - (total_frames - slide_frames)) / max(slide_frames - 1, 1)
                bar_x = int(bar_x_final - (bar_w + bar_x_final) * progress)
            else:
                bar_x = bar_x_final

            # Draw bar background
            draw.rectangle(
                [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                fill=bar_bg,
            )

            # Accent stripe on left edge
            stripe_w = 5
            draw.rectangle(
                [bar_x, bar_y, bar_x + stripe_w, bar_y + bar_h],
                fill=hex_to_rgba(st.highlight_color),
            )

            # Name text
            name_x = bar_x + 25
            name_y = bar_y + 10
            draw.text((name_x, name_y), name, font=font_name, fill=name_color)

            # Title text
            title_x = bar_x + 25
            title_y = bar_y + 10 + nh + 5
            draw.text((title_x, title_y), title, font=font_title, fill=title_color)

            out_path = os.path.join(output_dir, f"frame_{fi:05d}.png")
            img.save(out_path, "PNG")

        return total_frames


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_resolution(s: str) -> Tuple[int, int]:
    parts = s.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Resolution must be WxH, got '{s}'")
    return (int(parts[0]), int(parts[1]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pillow-based video caption/title/lower-third frame renderer",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- captions --
    p_cap = sub.add_parser("captions", help="Render word-by-word caption frames")
    p_cap.add_argument("--words", required=True, help="JSON file with word timings")
    p_cap.add_argument("--style", default="capcut_pop", help="Style preset or name")
    p_cap.add_argument("--resolution", type=_parse_resolution, default=(1920, 1080))
    p_cap.add_argument("--fps", type=int, default=30)
    p_cap.add_argument("--output-dir", required=True)

    # -- title --
    p_title = sub.add_parser("title", help="Render animated title card")
    p_title.add_argument("--text", required=True)
    p_title.add_argument("--style", default="capcut_pop")
    p_title.add_argument("--duration", type=float, default=3.0)
    p_title.add_argument("--animation", default="fade_in", choices=["fade_in", "scale_up", "typewriter"])
    p_title.add_argument("--resolution", type=_parse_resolution, default=(1920, 1080))
    p_title.add_argument("--fps", type=int, default=30)
    p_title.add_argument("--output-dir", required=True)

    # -- lower-third --
    p_lt = sub.add_parser("lower-third", help="Render animated lower third")
    p_lt.add_argument("--name", required=True)
    p_lt.add_argument("--title", required=True)
    p_lt.add_argument("--style", default="subtitle_bar")
    p_lt.add_argument("--duration", type=float, default=4.0)
    p_lt.add_argument("--resolution", type=_parse_resolution, default=(1920, 1080))
    p_lt.add_argument("--fps", type=int, default=30)
    p_lt.add_argument("--output-dir", required=True)

    args = parser.parse_args()
    renderer = CaptionRenderer(resolution=args.resolution, fps=args.fps)

    if args.command == "captions":
        with open(args.words, "r") as f:
            words = json.load(f)
        count = renderer.render_caption_frames(words, args.style, args.output_dir)
        print(f"Rendered {count} caption frames to {args.output_dir}")

    elif args.command == "title":
        count = renderer.render_title(
            args.text, args.style, args.duration, args.output_dir,
            animation=args.animation,
        )
        print(f"Rendered {count} title frames to {args.output_dir}")

    elif args.command == "lower-third":
        count = renderer.render_lower_third(
            args.name, args.title, args.style, args.duration, args.output_dir,
        )
        print(f"Rendered {count} lower-third frames to {args.output_dir}")


if __name__ == "__main__":
    main()
