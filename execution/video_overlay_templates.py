#!/usr/bin/env python3
"""Pre-built Pillow-based motion graphic template renderers for video overlays.

Outputs RGBA PNG frame sequences (transparent background) for compositing
onto video via FFmpeg or similar tools.

Usage (CLI):
    python video_overlay_templates.py subscribe --duration 5.0 --style slide_in
    python video_overlay_templates.py progress-bar --video-duration 600
    python video_overlay_templates.py arrow --x 960 --y 400 --label "Click here" --duration 3.0
    python video_overlay_templates.py lower-third --name "Sabbo" --title "Amazon FBA Coach" --duration 4.0
    python video_overlay_templates.py popup --text "Limited Time Offer!" --duration 3.0

Usage (importable):
    from execution.video_overlay_templates import render_subscribe_button
    count = render_subscribe_button(duration=5.0, style="slide_in")
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Font helper
# ---------------------------------------------------------------------------

_font_cache: dict[str, str] = {}


def find_font(name: str) -> str:
    """Locate a system font by partial name match. Falls back to Helvetica."""
    if name in _font_cache:
        return _font_cache[name]
    search_dirs = [
        "/System/Library/Fonts/",
        "/Library/Fonts/",
        os.path.expanduser("~/Library/Fonts/"),
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if name.lower() in f.lower() and f.endswith((".ttf", ".ttc", ".otf")):
                path = os.path.join(d, f)
                _font_cache[name] = path
                return path
    fallback = "/System/Library/Fonts/Helvetica.ttc"
    _font_cache[name] = fallback
    return fallback


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = find_font(name)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
    """Convert hex color string to RGBA tuple. Supports #RGB, #RRGGBB, #RRGGBBAA."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        r, g, b = (int(c * 2, 16) for c in h)
        return (r, g, b, 255)
    elif len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    elif len(h) == 8:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
    return (255, 255, 255, 255)


def _save_frame(img: Image.Image, output_dir: str, frame_num: int) -> None:
    img.save(os.path.join(output_dir, f"frame_{frame_num:05d}.png"))


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _ease_out_back(t: float) -> float:
    """Overshoot ease-out (for bounce effects). t in [0,1]."""
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * pow(t - 1.0, 3) + c1 * pow(t - 1.0, 2)


def _ease_out_cubic(t: float) -> float:
    return 1.0 - pow(1.0 - t, 3)


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
) -> None:
    """Draw a rounded rectangle (compatible with older Pillow versions)."""
    x0, y0, x1, y1 = xy
    r = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
    # Main body
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
    # Corners
    draw.pieslice([x0, y0, x0 + 2 * r, y0 + 2 * r], 180, 270, fill=fill)
    draw.pieslice([x1 - 2 * r, y0, x1, y0 + 2 * r], 270, 360, fill=fill)
    draw.pieslice([x0, y1 - 2 * r, x0 + 2 * r, y1], 90, 180, fill=fill)
    draw.pieslice([x1 - 2 * r, y1 - 2 * r, x1, y1], 0, 90, fill=fill)


def _draw_bell_icon(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    size: int,
    color: tuple[int, int, int, int],
) -> None:
    """Draw a simplified bell icon (circle + small triangle)."""
    r = size // 2
    # Bell body: circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    # Clapper: small triangle below
    tri_h = size // 3
    draw.polygon(
        [(cx - tri_h // 2, cy + r), (cx + tri_h // 2, cy + r), (cx, cy + r + tri_h)],
        fill=color,
    )


# ---------------------------------------------------------------------------
# 1. Subscribe Button
# ---------------------------------------------------------------------------


def render_subscribe_button(
    duration: float,
    fps: int = 30,
    resolution: tuple[int, int] = (1920, 1080),
    position: str = "bottom_right",
    style: str = "slide_in",
    output_dir: str = ".tmp/overlays/subscribe/",
) -> int:
    """Render an animated YouTube subscribe button overlay.

    Args:
        duration: Total duration in seconds.
        fps: Frames per second.
        resolution: Output resolution (width, height).
        position: bottom_right, bottom_left, or bottom_center.
        style: slide_in, pop, or fade.
        output_dir: Directory for output PNGs.

    Returns:
        Frame count.
    """
    _ensure_dir(output_dir)
    w, h = resolution
    total_frames = int(duration * fps)
    if total_frames < 1:
        total_frames = 1

    font = _load_font("Helvetica", 22)
    text = "SUBSCRIBE"
    # Measure text
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)
    bbox = dd.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    btn_w = tw + 60
    btn_h = th + 24
    bell_size = 14
    btn_w_total = btn_w + bell_size + 16  # button + gap + bell

    margin = 40

    # Base position
    if position == "bottom_left":
        base_x = margin
    elif position == "bottom_center":
        base_x = (w - btn_w_total) // 2
    else:  # bottom_right
        base_x = w - btn_w_total - margin
    base_y = h - btn_h - margin

    yt_red = (255, 0, 0, 255)
    white = (255, 255, 255, 255)

    in_frames = int(0.3 * fps)
    out_frames = int(0.3 * fps)

    for i in range(total_frames):
        img = Image.new("RGBA", resolution, (0, 0, 0, 0))
        t = i / max(total_frames - 1, 1)
        t_sec = i / fps

        # Compute per-style transform
        alpha = 255
        offset_x = 0
        scale = 1.0

        if style == "slide_in":
            if i < in_frames:
                progress = i / max(in_frames, 1)
                ease = _ease_out_cubic(progress)
                offset_x = int((1.0 - ease) * (w - base_x + btn_w_total))
            elif i >= total_frames - out_frames:
                progress = (i - (total_frames - out_frames)) / max(out_frames, 1)
                ease = progress
                offset_x = int(ease * (w - base_x + btn_w_total))

        elif style == "pop":
            if i < in_frames:
                progress = i / max(in_frames, 1)
                scale = _ease_out_back(progress)
                scale = max(0.0, min(scale, 1.1))
            elif i >= total_frames - out_frames:
                progress = (i - (total_frames - out_frames)) / max(out_frames, 1)
                alpha = int(255 * (1.0 - progress))

        elif style == "fade":
            fade_in_frames = int(0.5 * fps)
            if i < fade_in_frames:
                alpha = int(255 * (i / max(fade_in_frames, 1)))
            elif i >= total_frames - out_frames:
                progress = (i - (total_frames - out_frames)) / max(out_frames, 1)
                alpha = int(255 * (1.0 - progress))

        alpha = max(0, min(255, alpha))

        if scale != 1.0 and scale > 0.01:
            # Render at full size then resize
            btn_img = Image.new("RGBA", (btn_w_total + 4, btn_h + bell_size + 4), (0, 0, 0, 0))
            bd = ImageDraw.Draw(btn_img)
            _rounded_rect(bd, (0, 0, btn_w - 1, btn_h - 1), 8, yt_red)
            bd.text(
                ((btn_w - tw) // 2, (btn_h - th) // 2 - 2),
                text,
                font=font,
                fill=white,
            )
            _draw_bell_icon(bd, btn_w + 8 + bell_size // 2, btn_h // 2, bell_size, white)

            new_w = max(1, int(btn_img.width * scale))
            new_h = max(1, int(btn_img.height * scale))
            btn_img = btn_img.resize((new_w, new_h), Image.LANCZOS)

            px = base_x + (btn_w_total - new_w) // 2
            py = base_y + (btn_h - new_h) // 2
            if alpha < 255:
                btn_img.putalpha(
                    btn_img.getchannel("A").point(lambda a: int(a * alpha / 255))
                )
            img.paste(btn_img, (px, py), btn_img)
        else:
            draw = ImageDraw.Draw(img)
            bx = base_x + offset_x
            by = base_y
            btn_color = (yt_red[0], yt_red[1], yt_red[2], alpha)
            text_color = (255, 255, 255, alpha)
            _rounded_rect(draw, (bx, by, bx + btn_w - 1, by + btn_h - 1), 8, btn_color)
            draw.text(
                (bx + (btn_w - tw) // 2, by + (btn_h - th) // 2 - 2),
                text,
                font=font,
                fill=text_color,
            )
            _draw_bell_icon(
                draw, bx + btn_w + 8 + bell_size // 2, by + btn_h // 2, bell_size, text_color
            )

        _save_frame(img, output_dir, i + 1)

    print(f"Rendered {total_frames} frames to {output_dir}")
    return total_frames


# ---------------------------------------------------------------------------
# 2. Progress Bar
# ---------------------------------------------------------------------------


def render_progress_bar(
    video_duration: float,
    bar_duration: Optional[float] = None,
    fps: int = 30,
    resolution: tuple[int, int] = (1920, 1080),
    color: str = "#FF0000",
    bg_color: str = "#FFFFFF40",
    height: int = 4,
    position: str = "bottom",
    output_dir: str = ".tmp/overlays/progress/",
) -> int:
    """Render a thin progress bar showing video position.

    Args:
        video_duration: Total video length in seconds.
        bar_duration: How long the bar is visible (defaults to video_duration).
        fps: Frames per second.
        resolution: Output resolution.
        color: Fill color hex.
        bg_color: Background color hex (supports alpha).
        height: Bar height in pixels.
        position: "bottom" or "top".
        output_dir: Directory for output PNGs.

    Returns:
        Frame count.
    """
    _ensure_dir(output_dir)
    if bar_duration is None:
        bar_duration = video_duration

    w, h = resolution
    total_frames = int(bar_duration * fps)
    if total_frames < 1:
        total_frames = 1

    fill_rgba = _hex_to_rgba(color)
    bg_rgba = _hex_to_rgba(bg_color)

    bar_y = 0 if position == "top" else h - height

    for i in range(total_frames):
        img = Image.new("RGBA", resolution, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        progress = (i + 1) / total_frames
        fill_w = max(1, int(w * progress))

        # Background
        draw.rectangle([0, bar_y, w, bar_y + height - 1], fill=bg_rgba)
        # Fill
        draw.rectangle([0, bar_y, fill_w, bar_y + height - 1], fill=fill_rgba)

        _save_frame(img, output_dir, i + 1)

    print(f"Rendered {total_frames} frames to {output_dir}")
    return total_frames


# ---------------------------------------------------------------------------
# 3. Arrow Callout
# ---------------------------------------------------------------------------


def render_arrow_callout(
    target_x: int,
    target_y: int,
    label: str,
    duration: float,
    fps: int = 30,
    resolution: tuple[int, int] = (1920, 1080),
    color: str = "#FFD700",
    output_dir: str = ".tmp/overlays/arrow/",
) -> int:
    """Render an animated arrow pointing at a specific location.

    Args:
        target_x: X coordinate the arrow points to.
        target_y: Y coordinate the arrow points to.
        label: Text label next to the arrow.
        duration: Duration in seconds.
        fps: Frames per second.
        resolution: Output resolution.
        color: Arrow and label color hex.
        output_dir: Directory for output PNGs.

    Returns:
        Frame count.
    """
    _ensure_dir(output_dir)
    w, h = resolution
    total_frames = int(duration * fps)
    if total_frames < 1:
        total_frames = 1

    fill = _hex_to_rgba(color)
    font = _load_font("Helvetica", 28)

    # Arrow geometry
    arrow_len = 80
    head_size = 20
    shaft_width = 6

    # Arrow comes from left of target
    arrow_from_x = target_x - arrow_len
    arrow_from_y = target_y

    in_frames = int(0.4 * fps)
    out_frames = int(0.3 * fps)

    # Measure label
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)
    lbbox = dd.textbbox((0, 0), label, font=font)
    lw = lbbox[2] - lbbox[0]
    lh = lbbox[3] - lbbox[1]

    for i in range(total_frames):
        img = Image.new("RGBA", resolution, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        alpha = 255
        offset_x = 0

        if i < in_frames:
            progress = i / max(in_frames, 1)
            ease = _ease_out_back(progress)
            ease = max(0.0, min(ease, 1.15))
            offset_x = int((1.0 - ease) * (-arrow_len - lw - 40))
        elif i >= total_frames - out_frames:
            progress = (i - (total_frames - out_frames)) / max(out_frames, 1)
            alpha = int(255 * (1.0 - progress))

        alpha = max(0, min(255, alpha))
        c = (fill[0], fill[1], fill[2], alpha)

        ax = arrow_from_x + offset_x
        ay = arrow_from_y
        tip_x = target_x + offset_x
        tip_y = target_y

        # Shaft
        draw.rectangle(
            [ax, ay - shaft_width // 2, tip_x - head_size, ay + shaft_width // 2],
            fill=c,
        )
        # Arrowhead
        draw.polygon(
            [
                (tip_x, tip_y),
                (tip_x - head_size, tip_y - head_size // 2),
                (tip_x - head_size, tip_y + head_size // 2),
            ],
            fill=c,
        )
        # Label
        label_x = ax - lw - 12
        label_y = ay - lh // 2
        draw.text((label_x, label_y), label, font=font, fill=c)

        _save_frame(img, output_dir, i + 1)

    print(f"Rendered {total_frames} frames to {output_dir}")
    return total_frames


# ---------------------------------------------------------------------------
# 4. Lower Third Bar
# ---------------------------------------------------------------------------


def render_lower_third_bar(
    name: str,
    title: str,
    duration: float,
    fps: int = 30,
    resolution: tuple[int, int] = (1920, 1080),
    style: str = "modern_glass",
    color: str = "#000000CC",
    accent_color: str = "#FF0000",
    output_dir: str = ".tmp/overlays/lower-third/",
) -> int:
    """Render a modern lower-third name/title bar.

    Args:
        name: Primary name text (larger).
        title: Secondary title text (smaller).
        duration: Duration in seconds.
        fps: Frames per second.
        resolution: Output resolution.
        style: modern_glass, solid, or minimal.
        color: Background color hex (supports alpha).
        accent_color: Accent line color hex.
        output_dir: Directory for output PNGs.

    Returns:
        Frame count.
    """
    _ensure_dir(output_dir)
    w, h = resolution
    total_frames = int(duration * fps)
    if total_frames < 1:
        total_frames = 1

    bg_rgba = _hex_to_rgba(color)
    accent_rgba = _hex_to_rgba(accent_color)

    name_font = _load_font("Helvetica", 36)
    title_font = _load_font("Helvetica", 22)
    white = (255, 255, 255, 255)

    # Measure text
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)
    name_bbox = dd.textbbox((0, 0), name, font=name_font)
    title_bbox = dd.textbbox((0, 0), title, font=title_font)
    name_w = name_bbox[2] - name_bbox[0]
    name_h = name_bbox[3] - name_bbox[1]
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]

    padding_x = 30
    padding_y = 16
    accent_w = 5

    bar_w = max(name_w, title_w) + padding_x * 2 + accent_w + 10
    bar_h = name_h + title_h + padding_y * 2 + 8

    bar_x = 60
    bar_y = h - bar_h - 80

    in_frames = int(0.4 * fps)
    out_frames = int(0.3 * fps)

    for i in range(total_frames):
        img = Image.new("RGBA", resolution, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        alpha_mult = 1.0
        offset_x = 0

        if i < in_frames:
            progress = i / max(in_frames, 1)
            ease = _ease_out_cubic(progress)
            offset_x = int((1.0 - ease) * (-bar_w - bar_x))
        elif i >= total_frames - out_frames:
            progress = (i - (total_frames - out_frames)) / max(out_frames, 1)
            ease = progress * progress
            offset_x = int(ease * (-bar_w - bar_x))

        bx = bar_x + offset_x
        by = bar_y

        if style == "modern_glass":
            # Semi-transparent background with gradient alpha edges
            glass_color = (bg_rgba[0], bg_rgba[1], bg_rgba[2], int(bg_rgba[3] * 0.75))
            _rounded_rect(draw, (bx, by, bx + bar_w, by + bar_h), 6, glass_color)
            # Gradient fade on right edge
            for gi in range(20):
                fade_alpha = int(glass_color[3] * (1.0 - gi / 20.0))
                gc = (glass_color[0], glass_color[1], glass_color[2], fade_alpha)
                gx = bx + bar_w + gi
                draw.line([(gx, by), (gx, by + bar_h)], fill=gc)
            # Accent line on left
            draw.rectangle(
                [bx, by, bx + accent_w, by + bar_h],
                fill=accent_rgba,
            )

        elif style == "solid":
            draw.rectangle([bx, by, bx + bar_w, by + bar_h], fill=bg_rgba)
            # Accent top border
            draw.rectangle(
                [bx, by, bx + bar_w, by + 3],
                fill=accent_rgba,
            )

        elif style == "minimal":
            # No background, just an accent underline under name
            underline_y = by + padding_y + name_h + 4
            draw.rectangle(
                [bx + accent_w + 10, underline_y, bx + accent_w + 10 + name_w, underline_y + 2],
                fill=accent_rgba,
            )

        # Text
        text_x = bx + accent_w + 10 + padding_x // 2
        text_y_name = by + padding_y
        text_y_title = text_y_name + name_h + 6

        name_color = white
        title_color = (200, 200, 200, 255)

        draw.text((text_x, text_y_name), name, font=name_font, fill=name_color)
        draw.text((text_x, text_y_title), title, font=title_font, fill=title_color)

        _save_frame(img, output_dir, i + 1)

    print(f"Rendered {total_frames} frames to {output_dir}")
    return total_frames


# ---------------------------------------------------------------------------
# 5. Text Popup
# ---------------------------------------------------------------------------


def render_text_popup(
    text: str,
    duration: float,
    fps: int = 30,
    resolution: tuple[int, int] = (1920, 1080),
    position: str = "center",
    bg_color: str = "#000000DD",
    text_color: str = "#FFFFFF",
    output_dir: str = ".tmp/overlays/popup/",
) -> int:
    """Render a text popup/callout bubble.

    Args:
        text: Popup text content.
        duration: Duration in seconds.
        fps: Frames per second.
        resolution: Output resolution.
        position: center, top, or bottom.
        bg_color: Background color hex (supports alpha).
        text_color: Text color hex.
        output_dir: Directory for output PNGs.

    Returns:
        Frame count.
    """
    _ensure_dir(output_dir)
    w, h = resolution
    total_frames = int(duration * fps)
    if total_frames < 1:
        total_frames = 1

    bg_rgba = _hex_to_rgba(bg_color)
    txt_rgba = _hex_to_rgba(text_color)
    font = _load_font("Helvetica", 36)

    # Measure text
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)
    bbox = dd.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad_x = 40
    pad_y = 24
    box_w = tw + pad_x * 2
    box_h = th + pad_y * 2
    radius = 16

    # Position
    cx = (w - box_w) // 2
    if position == "top":
        cy = h // 6 - box_h // 2
    elif position == "bottom":
        cy = h * 5 // 6 - box_h // 2
    else:  # center
        cy = (h - box_h) // 2

    in_frames = int(0.2 * fps)
    out_frames = int(0.3 * fps)

    for i in range(total_frames):
        img = Image.new("RGBA", resolution, (0, 0, 0, 0))

        alpha = 255
        scale = 1.0

        if i < in_frames:
            progress = i / max(in_frames, 1)
            scale = _ease_out_back(progress)
            scale = max(0.01, min(scale, 1.1))
        elif i >= total_frames - out_frames:
            progress = (i - (total_frames - out_frames)) / max(out_frames, 1)
            alpha = int(255 * (1.0 - progress))

        alpha = max(0, min(255, alpha))

        # Render popup to temp image then scale
        popup = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        pd = ImageDraw.Draw(popup)
        _rounded_rect(pd, (0, 0, box_w - 1, box_h - 1), radius, bg_rgba)
        pd.text((pad_x, pad_y - 2), text, font=font, fill=txt_rgba)

        if scale != 1.0:
            new_w = max(1, int(popup.width * scale))
            new_h = max(1, int(popup.height * scale))
            popup = popup.resize((new_w, new_h), Image.LANCZOS)
        else:
            new_w, new_h = popup.size

        if alpha < 255:
            popup.putalpha(popup.getchannel("A").point(lambda a: int(a * alpha / 255)))

        px = cx + (box_w - new_w) // 2
        py = cy + (box_h - new_h) // 2
        img.paste(popup, (px, py), popup)

        _save_frame(img, output_dir, i + 1)

    print(f"Rendered {total_frames} frames to {output_dir}")
    return total_frames


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_resolution(s: str) -> tuple[int, int]:
    parts = s.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Resolution must be WxH, got: {s}")
    return (int(parts[0]), int(parts[1]))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pillow-based motion graphic template renderers for video overlays."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- subscribe --
    p_sub = sub.add_parser("subscribe", help="YouTube subscribe button overlay")
    p_sub.add_argument("--duration", type=float, required=True)
    p_sub.add_argument("--fps", type=int, default=30)
    p_sub.add_argument("--resolution", type=_parse_resolution, default="1920x1080")
    p_sub.add_argument("--position", default="bottom_right", choices=["bottom_right", "bottom_left", "bottom_center"])
    p_sub.add_argument("--style", default="slide_in", choices=["slide_in", "pop", "fade"])
    p_sub.add_argument("--output-dir", default=".tmp/overlays/subscribe/")

    # -- progress-bar --
    p_prog = sub.add_parser("progress-bar", help="Thin progress bar overlay")
    p_prog.add_argument("--video-duration", type=float, required=True)
    p_prog.add_argument("--bar-duration", type=float, default=None)
    p_prog.add_argument("--fps", type=int, default=30)
    p_prog.add_argument("--resolution", type=_parse_resolution, default="1920x1080")
    p_prog.add_argument("--color", default="#FF0000")
    p_prog.add_argument("--bg-color", default="#FFFFFF40")
    p_prog.add_argument("--height", type=int, default=4)
    p_prog.add_argument("--position", default="bottom", choices=["bottom", "top"])
    p_prog.add_argument("--output-dir", default=".tmp/overlays/progress/")

    # -- arrow --
    p_arrow = sub.add_parser("arrow", help="Arrow callout pointing at a location")
    p_arrow.add_argument("--x", type=int, required=True)
    p_arrow.add_argument("--y", type=int, required=True)
    p_arrow.add_argument("--label", required=True)
    p_arrow.add_argument("--duration", type=float, required=True)
    p_arrow.add_argument("--fps", type=int, default=30)
    p_arrow.add_argument("--resolution", type=_parse_resolution, default="1920x1080")
    p_arrow.add_argument("--color", default="#FFD700")
    p_arrow.add_argument("--output-dir", default=".tmp/overlays/arrow/")

    # -- lower-third --
    p_lt = sub.add_parser("lower-third", help="Lower-third name/title bar")
    p_lt.add_argument("--name", required=True)
    p_lt.add_argument("--title", required=True)
    p_lt.add_argument("--duration", type=float, required=True)
    p_lt.add_argument("--fps", type=int, default=30)
    p_lt.add_argument("--resolution", type=_parse_resolution, default="1920x1080")
    p_lt.add_argument("--style", default="modern_glass", choices=["modern_glass", "solid", "minimal"])
    p_lt.add_argument("--color", default="#000000CC")
    p_lt.add_argument("--accent-color", default="#FF0000")
    p_lt.add_argument("--output-dir", default=".tmp/overlays/lower-third/")

    # -- popup --
    p_pop = sub.add_parser("popup", help="Text popup/callout bubble")
    p_pop.add_argument("--text", required=True)
    p_pop.add_argument("--duration", type=float, required=True)
    p_pop.add_argument("--fps", type=int, default=30)
    p_pop.add_argument("--resolution", type=_parse_resolution, default="1920x1080")
    p_pop.add_argument("--position", default="center", choices=["center", "top", "bottom"])
    p_pop.add_argument("--bg-color", default="#000000DD")
    p_pop.add_argument("--text-color", default="#FFFFFF")
    p_pop.add_argument("--output-dir", default=".tmp/overlays/popup/")

    args = parser.parse_args()

    if args.command == "subscribe":
        render_subscribe_button(
            duration=args.duration,
            fps=args.fps,
            resolution=args.resolution,
            position=args.position,
            style=args.style,
            output_dir=args.output_dir,
        )
    elif args.command == "progress-bar":
        render_progress_bar(
            video_duration=args.video_duration,
            bar_duration=args.bar_duration,
            fps=args.fps,
            resolution=args.resolution,
            color=args.color,
            bg_color=args.bg_color,
            height=args.height,
            position=args.position,
            output_dir=args.output_dir,
        )
    elif args.command == "arrow":
        render_arrow_callout(
            target_x=args.x,
            target_y=args.y,
            label=args.label,
            duration=args.duration,
            fps=args.fps,
            resolution=args.resolution,
            color=args.color,
            output_dir=args.output_dir,
        )
    elif args.command == "lower-third":
        render_lower_third_bar(
            name=args.name,
            title=args.title,
            duration=args.duration,
            fps=args.fps,
            resolution=args.resolution,
            style=args.style,
            color=args.color,
            accent_color=args.accent_color,
            output_dir=args.output_dir,
        )
    elif args.command == "popup":
        render_text_popup(
            text=args.text,
            duration=args.duration,
            fps=args.fps,
            resolution=args.resolution,
            position=args.position,
            bg_color=args.bg_color,
            text_color=args.text_color,
            output_dir=args.output_dir,
        )


if __name__ == "__main__":
    main()
