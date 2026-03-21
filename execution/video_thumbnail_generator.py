#!/usr/bin/env python3
"""YouTube thumbnail generator using Pillow + OpenCV.

Generates high-converting thumbnails following YouTube Foundations SOP:
- High contrast, one clear focal point
- Max 3-4 words of text
- Expressive facial reactions
- Visual consistency with brand colors
- Simple and visually readable

Templates: bold_text, face_text, split, minimal, result

Usage:
    # Bold text thumbnail
    python video_thumbnail_generator.py bold-text \\
        --text "I Made $14K In 48 Hours" \\
        --highlight "14K,48 Hours" \\
        --face video.mp4 \\
        --style youtube_red \\
        --output thumbnail.jpg

    # Face + text
    python video_thumbnail_generator.py face-text \\
        --text "The Amazon FBA System" \\
        --face headshot.jpg \\
        --position right \\
        --output thumbnail.jpg

    # Result highlight
    python video_thumbnail_generator.py result \\
        --result "$10K/mo" \\
        --subtitle "First Month on Amazon" \\
        --face video.mp4 \\
        --output thumbnail.jpg

    # From video (auto-extract best frame + face)
    python video_thumbnail_generator.py from-video \\
        --input video.mp4 \\
        --text "How I Source Products" \\
        --style allday_blue \\
        --output thumbnail.jpg
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp" / "thumbnails"

YOUTUBE_WIDTH = 1280
YOUTUBE_HEIGHT = 720
YOUTUBE_SIZE = (YOUTUBE_WIDTH, YOUTUBE_HEIGHT)

_font_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# ThumbnailStyle
# ---------------------------------------------------------------------------

@dataclass
class ThumbnailStyle:
    """Style configuration for thumbnail rendering."""
    bg_color: str = "#1a1a2e"
    text_color: str = "#FFFFFF"
    accent_color: str = "#FF0000"
    secondary_color: str = "#FFD700"
    font_name: str = "Impact"
    font_size_primary: int = 120
    font_size_secondary: int = 60
    resolution: Tuple[int, int] = (1280, 720)


PRESET_STYLES: dict[str, ThumbnailStyle] = {
    "youtube_red": ThumbnailStyle(accent_color="#FF0000"),
    "allday_blue": ThumbnailStyle(
        bg_color="#0a0a1a",
        accent_color="#4169E1",
        secondary_color="#00BFFF",
    ),
    "gold_black": ThumbnailStyle(
        bg_color="#0a0a0a",
        accent_color="#FFD700",
        text_color="#FFFFFF",
    ),
    "clean_white": ThumbnailStyle(
        bg_color="#FFFFFF",
        text_color="#1a1a1a",
        accent_color="#FF4444",
    ),
    "gradient_dark": ThumbnailStyle(bg_color="#1a1a2e"),
}


# ---------------------------------------------------------------------------
# Font finder (same pattern as video_overlay_templates.py)
# ---------------------------------------------------------------------------

def find_font(name: str) -> str:
    """Locate a system font by partial name match. Falls back to Helvetica."""
    if name in _font_cache:
        return _font_cache[name]

    # Direct path
    if os.path.isfile(name):
        _font_cache[name] = name
        return name

    search_dirs = [
        "/System/Library/Fonts/",
        "/Library/Fonts/",
        os.path.expanduser("~/Library/Fonts/"),
    ]
    target = name.lower()
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in files:
                if target in f.lower() and f.endswith((".ttf", ".ttc", ".otf")):
                    path = os.path.join(root, f)
                    _font_cache[name] = path
                    return path

    # Fallback
    fallbacks = ["Helvetica", "Arial", "DejaVuSans"]
    for fb in fallbacks:
        if fb.lower() != target:
            try:
                return find_font(fb)
            except Exception:
                continue

    # Last resort: Pillow default
    _font_cache[name] = ""
    return ""


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font at the given size."""
    path = find_font(name)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    # Pillow built-in default
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def hex_to_rgba(color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    """Convert hex color string to RGBA tuple."""
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    return (r, g, b, alpha)


def hex_to_rgb(color: str) -> Tuple[int, int, int]:
    """Convert hex color string to RGB tuple."""
    return hex_to_rgba(color)[:3]


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def create_gradient(
    width: int,
    height: int,
    color1: str,
    color2: str,
    direction: str = "vertical",
) -> Image.Image:
    """Create a gradient background image."""
    img = Image.new("RGBA", (width, height))
    c1 = hex_to_rgba(color1)
    c2 = hex_to_rgba(color2)

    for i in range(height if direction == "vertical" else width):
        ratio = i / max((height if direction == "vertical" else width) - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
        a = int(c1[3] + (c2[3] - c1[3]) * ratio)
        if direction == "vertical":
            ImageDraw.Draw(img).line([(0, i), (width, i)], fill=(r, g, b, a))
        else:
            ImageDraw.Draw(img).line([(i, 0), (i, height)], fill=(r, g, b, a))

    return img


def draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    position: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str | Tuple = "#FFFFFF",
    shadow_color: str = "#000000",
    offset: int = 4,
) -> None:
    """Draw text with a drop shadow for depth."""
    x, y = position
    if isinstance(fill, str):
        fill = hex_to_rgb(fill)
    shadow_rgb = hex_to_rgb(shadow_color) if isinstance(shadow_color, str) else shadow_color

    # Shadow (draw twice for thicker shadow)
    draw.text((x + offset, y + offset), text, font=font, fill=shadow_rgb)
    draw.text((x + offset - 1, y + offset - 1), text, font=font, fill=shadow_rgb)
    # Main text
    draw.text((x, y), text, font=font, fill=fill)


def draw_highlight_bar(
    draw: ImageDraw.ImageDraw,
    position: Tuple[int, int],
    size: Tuple[int, int],
    color: str,
    padding: int = 10,
) -> None:
    """Draw a colored rectangle (highlight bar) behind text."""
    x, y = position
    w, h = size
    bar_color = hex_to_rgba(color, alpha=230)
    draw.rectangle(
        [x - padding, y - padding // 2, x + w + padding, y + h + padding // 2],
        fill=bar_color,
    )


def auto_wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> List[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: List[str] = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip() if current_line else word
        bbox = font.getbbox(test_line)
        text_width = bbox[2] - bbox[0]
        if text_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    return lines


def get_text_size(
    font: ImageFont.FreeTypeFont,
    text: str,
) -> Tuple[int, int]:
    """Get the pixel dimensions of rendered text."""
    bbox = font.getbbox(text)
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])


# ---------------------------------------------------------------------------
# Video/ffmpeg helpers
# ---------------------------------------------------------------------------

def run_cmd(
    cmd: list[str],
    desc: str = "",
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run a subprocess command with logging."""
    if desc:
        print(f"  [{desc}]")
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        print(f"  ERROR: {exc.stderr[:500] if exc.stderr else exc}")
        raise


def extract_frame_from_video(
    video_path: str,
    timestamp: float = 5.0,
    output_path: str | None = None,
) -> str:
    """Extract a single frame from a video at the given timestamp."""
    if output_path is None:
        tmp_dir = str(TMP_ROOT / "frames")
        os.makedirs(tmp_dir, exist_ok=True)
        output_path = os.path.join(tmp_dir, f"frame_{timestamp:.1f}.jpg")

    cmd = [
        FFMPEG, "-y", "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1", "-q:v", "2",
        output_path,
    ]
    run_cmd(cmd, desc=f"Extracting frame at {timestamp:.1f}s")
    return output_path


def find_best_video_frame(
    video_path: str,
    count: int = 8,
) -> str:
    """Extract multiple frames, score by sharpness + brightness, return best."""
    tmp_dir = str(TMP_ROOT / "frame_candidates")
    os.makedirs(tmp_dir, exist_ok=True)

    # Get duration via ffprobe
    try:
        result = run_cmd([
            FFPROBE, "-v", "quiet", "-print_format", "json",
            "-show_format", video_path,
        ], desc="Probing video duration")
        import json
        info = json.loads(result.stdout)
        duration = float(info.get("format", {}).get("duration", 30))
    except Exception:
        duration = 30.0

    # Extract frames at intervals
    interval = duration / (count + 1)
    frames: List[str] = []
    for i in range(1, count + 1):
        ts = interval * i
        out = os.path.join(tmp_dir, f"candidate_{i:02d}.jpg")
        try:
            extract_frame_from_video(video_path, ts, out)
            if os.path.exists(out):
                frames.append(out)
        except Exception:
            continue

    if not frames:
        # Fallback: frame at 5s
        fallback = os.path.join(tmp_dir, "fallback.jpg")
        extract_frame_from_video(video_path, 5.0, fallback)
        return fallback

    # Score frames using OpenCV
    try:
        import cv2
        scored: List[Tuple[str, float]] = []
        for p in frames:
            img = cv2.imread(p)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            brightness = gray.mean()

            # Detect faces (bonus score)
            face_bonus = 0.0
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(cascade_path):
                cascade = cv2.CascadeClassifier(cascade_path)
                faces = cascade.detectMultiScale(gray, 1.3, 5)
                if len(faces) > 0:
                    face_bonus = 200.0  # Strongly prefer frames with faces

            score = sharpness * 0.5 + brightness * 0.2 + face_bonus
            scored.append((p, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        if scored:
            print(f"  Best frame: {Path(scored[0][0]).name} (score: {scored[0][1]:.0f})")
            return scored[0][0]
    except ImportError:
        print("  WARNING: OpenCV not available, using first extracted frame")

    return frames[0]


# ---------------------------------------------------------------------------
# FaceExtractor
# ---------------------------------------------------------------------------

class FaceExtractor:
    """Extract and crop faces from images or video frames using OpenCV."""

    @staticmethod
    def extract_face(
        image_path: str,
        padding_ratio: float = 0.5,
    ) -> Image.Image:
        """Detect face in image, crop with padding, return as PIL Image.

        If no face is detected, returns the right half of the image (common
        thumbnail layout).
        """
        try:
            import cv2
        except ImportError:
            # No OpenCV -- return right half of image
            img = Image.open(image_path).convert("RGBA")
            w, h = img.size
            return img.crop((w // 2, 0, w, h))

        cv_img = cv2.imread(image_path)
        if cv_img is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(cascade_path)
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(80, 80),
        )

        h_img, w_img = cv_img.shape[:2]

        if len(faces) == 0:
            # No face found -- return right half
            pil_img = Image.open(image_path).convert("RGBA")
            w, h = pil_img.size
            return pil_img.crop((w // 2, 0, w, h))

        # Use largest face
        faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        fx, fy, fw, fh = faces_sorted[0]

        # Add padding around face
        pad_x = int(fw * padding_ratio)
        pad_y = int(fh * padding_ratio)
        x1 = max(0, fx - pad_x)
        y1 = max(0, fy - pad_y)
        x2 = min(w_img, fx + fw + pad_x)
        y2 = min(h_img, fy + fh + pad_y)

        # Convert to PIL
        cropped = cv_img[y1:y2, x1:x2]
        cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
        return Image.fromarray(cropped_rgb).convert("RGBA")

    @staticmethod
    def extract_face_from_video(
        video_path: str,
        timestamp: float = 5.0,
    ) -> Image.Image:
        """Extract frame at timestamp, detect face, return as PIL Image."""
        frame_path = extract_frame_from_video(video_path, timestamp)
        return FaceExtractor.extract_face(frame_path)

    @staticmethod
    def extract_best_face_from_video(video_path: str) -> Image.Image:
        """Find the best frame in a video and extract the face from it."""
        best_frame = find_best_video_frame(video_path)
        return FaceExtractor.extract_face(best_frame)


# ---------------------------------------------------------------------------
# ThumbnailGenerator
# ---------------------------------------------------------------------------

class ThumbnailGenerator:
    """Main thumbnail generator with multiple template styles."""

    def __init__(self, style: ThumbnailStyle | str = "youtube_red"):
        if isinstance(style, str):
            if style not in PRESET_STYLES:
                print(f"  WARNING: Unknown style '{style}', using youtube_red")
                style = "youtube_red"
            self.style = PRESET_STYLES[style]
        else:
            self.style = style

        self.width, self.height = self.style.resolution
        self.face_extractor = FaceExtractor()

    def _ensure_output_dir(self, output_path: str) -> None:
        """Create parent directory if it doesn't exist."""
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _load_face(self, face_image: str) -> Optional[Image.Image]:
        """Load face from image file or extract from video."""
        if face_image is None:
            return None
        ext = Path(face_image).suffix.lower()
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
        if ext in video_exts:
            return self.face_extractor.extract_best_face_from_video(face_image)
        else:
            return self.face_extractor.extract_face(face_image)

    def _create_background(self) -> Image.Image:
        """Create gradient background based on style."""
        # Darken the bg_color slightly for gradient bottom
        bg = hex_to_rgba(self.style.bg_color)
        darker = tuple(max(0, c - 30) for c in bg[:3])
        darker_hex = "#{:02x}{:02x}{:02x}".format(*darker)
        return create_gradient(
            self.width, self.height,
            self.style.bg_color, darker_hex,
            direction="vertical",
        )

    def _add_face_to_canvas(
        self,
        canvas: Image.Image,
        face: Image.Image,
        position: str = "right",
        width_ratio: float = 0.4,
    ) -> None:
        """Place a face cutout on the canvas with shadow/glow effect."""
        target_h = self.height
        target_w = int(self.width * width_ratio)

        # Resize face to fill the allocated area
        face_ratio = face.width / face.height
        if face_ratio > (target_w / target_h):
            new_h = target_h
            new_w = int(new_h * face_ratio)
        else:
            new_w = target_w
            new_h = int(new_w / face_ratio)

        face_resized = face.resize((new_w, new_h), Image.LANCZOS)

        # Crop to fit target area
        crop_x = max(0, (new_w - target_w) // 2)
        crop_y = max(0, (new_h - target_h) // 2)
        face_cropped = face_resized.crop((
            crop_x, crop_y,
            crop_x + target_w, min(new_h, crop_y + target_h),
        ))

        # Create shadow/glow behind face
        shadow = Image.new("RGBA", face_cropped.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        accent = hex_to_rgba(self.style.accent_color, alpha=40)
        shadow_draw.rectangle([0, 0, face_cropped.width, face_cropped.height], fill=accent)
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=20))

        # Create fade gradient on the edge facing text
        fade = Image.new("RGBA", face_cropped.size, (0, 0, 0, 0))
        fade_draw = ImageDraw.Draw(fade)
        bg_rgba = hex_to_rgba(self.style.bg_color)
        fade_width = int(target_w * 0.3)

        for i in range(fade_width):
            alpha = int(200 * (1 - i / fade_width))
            if position == "right":
                fade_draw.line([(i, 0), (i, target_h)], fill=(*bg_rgba[:3], alpha))
            else:
                x = target_w - i - 1
                fade_draw.line([(x, 0), (x, target_h)], fill=(*bg_rgba[:3], alpha))

        # Position
        if position == "right":
            x_pos = self.width - target_w
        else:
            x_pos = 0

        y_pos = max(0, (self.height - face_cropped.height) // 2)

        # Composite: shadow, then face, then fade
        canvas.paste(shadow, (x_pos, y_pos), shadow)
        if face_cropped.mode == "RGBA":
            canvas.paste(face_cropped, (x_pos, y_pos), face_cropped)
        else:
            canvas.paste(face_cropped, (x_pos, y_pos))
        canvas.paste(fade, (x_pos, y_pos), fade)

    def generate_bold_text(
        self,
        text: str,
        highlight_words: Optional[List[str]] = None,
        face_image: Optional[str] = None,
        output_path: str = "thumbnail.jpg",
    ) -> str:
        """Generate bold text style thumbnail.

        Large uppercase text with optional highlighted words and face cutout.
        """
        self._ensure_output_dir(output_path)
        canvas = self._create_background()
        draw = ImageDraw.Draw(canvas)

        # Load and place face if provided
        face = self._load_face(face_image)
        if face is not None:
            self._add_face_to_canvas(canvas, face, position="right", width_ratio=0.4)
            draw = ImageDraw.Draw(canvas)  # Re-create draw after compositing
            text_area_width = int(self.width * 0.55)
        else:
            text_area_width = int(self.width * 0.85)

        # Load font and wrap text
        font = load_font(self.style.font_name, self.style.font_size_primary)
        upper_text = text.upper()
        lines = auto_wrap_text(upper_text, font, text_area_width)

        # Calculate total text block height
        line_heights = []
        for line in lines:
            _, h = get_text_size(font, line)
            line_heights.append(h)
        spacing = 15
        total_height = sum(line_heights) + spacing * (len(lines) - 1)

        # Center vertically
        y_start = (self.height - total_height) // 2
        x_margin = int(self.width * 0.06)

        highlight_set = set()
        if highlight_words:
            for hw in highlight_words:
                highlight_set.add(hw.upper())

        # Render each line
        y = y_start
        for i, line in enumerate(lines):
            # Check if any word in this line should be highlighted
            words = line.split()
            x = x_margin

            has_highlight = any(
                w.strip(".,!?") in highlight_set or
                any(hw in line for hw in highlight_set)
                for w in words
            )

            if has_highlight and highlight_words:
                # Draw highlight bar behind the entire line
                line_w, line_h = get_text_size(font, line)
                draw_highlight_bar(
                    draw,
                    (x, y),
                    (line_w, line_h),
                    self.style.accent_color,
                    padding=12,
                )

            draw_text_with_shadow(
                draw, (x, y), line, font,
                fill=self.style.text_color,
                shadow_color="#000000",
                offset=5,
            )
            y += line_heights[i] + spacing

        # Save
        output = canvas.convert("RGB")
        output.save(output_path, "JPEG", quality=95)
        print(f"  Saved: {output_path} ({self.width}x{self.height})")
        return output_path

    def generate_face_text(
        self,
        text: str,
        face_image: str,
        face_position: str = "right",
        output_path: str = "thumbnail.jpg",
    ) -> str:
        """Face cutout + text overlay style thumbnail."""
        self._ensure_output_dir(output_path)
        canvas = self._create_background()

        # Place face
        face = self._load_face(face_image)
        if face is not None:
            self._add_face_to_canvas(canvas, face, position=face_position, width_ratio=0.45)

        draw = ImageDraw.Draw(canvas)

        # Text on opposite side of face
        if face_position == "right":
            text_x_start = int(self.width * 0.05)
            text_max_w = int(self.width * 0.48)
        else:
            text_x_start = int(self.width * 0.5)
            text_max_w = int(self.width * 0.45)

        font = load_font(self.style.font_name, self.style.font_size_primary)
        upper_text = text.upper()
        lines = auto_wrap_text(upper_text, font, text_max_w)

        # Calculate block height
        line_heights = []
        for line in lines:
            _, h = get_text_size(font, line)
            line_heights.append(h)
        spacing = 12
        total_height = sum(line_heights) + spacing * (len(lines) - 1)
        y = (self.height - total_height) // 2

        for i, line in enumerate(lines):
            draw_text_with_shadow(
                draw, (text_x_start, y), line, font,
                fill=self.style.text_color,
                shadow_color="#000000",
                offset=5,
            )
            y += line_heights[i] + spacing

        # Accent line under text
        accent_y = y + 10
        accent_color = hex_to_rgb(self.style.accent_color)
        draw.rectangle(
            [text_x_start, accent_y, text_x_start + text_max_w // 2, accent_y + 6],
            fill=accent_color,
        )

        output = canvas.convert("RGB")
        output.save(output_path, "JPEG", quality=95)
        print(f"  Saved: {output_path} ({self.width}x{self.height})")
        return output_path

    def generate_result(
        self,
        result_text: str,
        subtitle: str,
        face_image: Optional[str] = None,
        output_path: str = "thumbnail.jpg",
    ) -> str:
        """Result/number highlight style thumbnail.

        Large result number with supporting text and optional face.
        """
        self._ensure_output_dir(output_path)
        canvas = self._create_background()

        # Place face on right if provided
        face = self._load_face(face_image)
        if face is not None:
            self._add_face_to_canvas(canvas, face, position="right", width_ratio=0.35)

        draw = ImageDraw.Draw(canvas)

        text_area_w = int(self.width * 0.58) if face else int(self.width * 0.85)
        x_margin = int(self.width * 0.06)

        # Result number (extra large)
        result_font_size = int(self.style.font_size_primary * 1.5)
        result_font = load_font(self.style.font_name, result_font_size)
        result_upper = result_text.upper()
        rw, rh = get_text_size(result_font, result_upper)

        # Center the result text vertically, offset up
        result_y = (self.height // 2) - rh - 20

        # Highlight bar behind result
        draw_highlight_bar(
            draw,
            (x_margin, result_y),
            (rw, rh),
            self.style.accent_color,
            padding=15,
        )
        draw_text_with_shadow(
            draw, (x_margin, result_y), result_upper, result_font,
            fill=self.style.text_color,
            shadow_color="#000000",
            offset=6,
        )

        # Subtitle below
        sub_font = load_font(self.style.font_name, self.style.font_size_secondary)
        subtitle_upper = subtitle.upper()
        sub_lines = auto_wrap_text(subtitle_upper, sub_font, text_area_w)
        sub_y = result_y + rh + 30

        for line in sub_lines:
            _, sh = get_text_size(sub_font, line)
            draw_text_with_shadow(
                draw, (x_margin, sub_y), line, sub_font,
                fill=hex_to_rgb(self.style.secondary_color),
                shadow_color="#000000",
                offset=3,
            )
            sub_y += sh + 8

        output = canvas.convert("RGB")
        output.save(output_path, "JPEG", quality=95)
        print(f"  Saved: {output_path} ({self.width}x{self.height})")
        return output_path

    def generate_split(
        self,
        left_image: str,
        right_image: str,
        left_label: str,
        right_label: str,
        output_path: str = "thumbnail.jpg",
    ) -> str:
        """Before/after split comparison thumbnail."""
        self._ensure_output_dir(output_path)
        canvas = Image.new("RGBA", (self.width, self.height))

        half_w = self.width // 2
        divider_w = 6

        # Load and resize both images
        for img_path, x_offset, label in [
            (left_image, 0, left_label),
            (right_image, half_w + divider_w // 2, right_label),
        ]:
            img = Image.open(img_path).convert("RGBA")
            # Resize to fill half
            img_ratio = img.width / img.height
            target_ratio = half_w / self.height
            if img_ratio > target_ratio:
                new_h = self.height
                new_w = int(new_h * img_ratio)
            else:
                new_w = half_w
                new_h = int(new_w / img_ratio)

            img_resized = img.resize((new_w, new_h), Image.LANCZOS)
            # Center-crop
            cx = max(0, (new_w - half_w) // 2)
            cy = max(0, (new_h - self.height) // 2)
            img_cropped = img_resized.crop((cx, cy, cx + half_w, cy + self.height))
            canvas.paste(img_cropped, (x_offset, 0))

        draw = ImageDraw.Draw(canvas)

        # Divider line
        accent_rgb = hex_to_rgba(self.style.accent_color)
        draw.rectangle(
            [half_w - divider_w // 2, 0, half_w + divider_w // 2, self.height],
            fill=accent_rgb,
        )

        # Labels
        label_font = load_font(self.style.font_name, self.style.font_size_secondary)

        for label_text, x_center in [
            (left_label.upper(), half_w // 2),
            (right_label.upper(), half_w + half_w // 2),
        ]:
            lw, lh = get_text_size(label_font, label_text)
            label_x = x_center - lw // 2
            label_y = self.height - lh - 40

            # Dark bar behind label
            draw_highlight_bar(
                draw,
                (label_x, label_y),
                (lw, lh),
                "#000000",
                padding=15,
            )
            draw_text_with_shadow(
                draw, (label_x, label_y), label_text, label_font,
                fill=self.style.text_color,
                shadow_color="#000000",
                offset=3,
            )

        output = canvas.convert("RGB")
        output.save(output_path, "JPEG", quality=95)
        print(f"  Saved: {output_path} ({self.width}x{self.height})")
        return output_path

    def generate_minimal(
        self,
        background_image: str,
        text: str,
        text_position: str = "bottom_left",
        output_path: str = "thumbnail.jpg",
    ) -> str:
        """Clean minimal style with background image and small text overlay."""
        self._ensure_output_dir(output_path)

        # Load and resize background
        bg = Image.open(background_image).convert("RGBA")
        bg_ratio = bg.width / bg.height
        target_ratio = self.width / self.height
        if bg_ratio > target_ratio:
            new_h = self.height
            new_w = int(new_h * bg_ratio)
        else:
            new_w = self.width
            new_h = int(new_w / bg_ratio)

        bg_resized = bg.resize((new_w, new_h), Image.LANCZOS)
        cx = max(0, (new_w - self.width) // 2)
        cy = max(0, (new_h - self.height) // 2)
        canvas = bg_resized.crop((cx, cy, cx + self.width, cy + self.height)).copy()

        # Darken overlay for text readability
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 80))
        canvas = Image.alpha_composite(canvas, overlay)

        draw = ImageDraw.Draw(canvas)
        font = load_font(self.style.font_name, self.style.font_size_secondary)
        upper_text = text.upper()
        lines = auto_wrap_text(upper_text, font, int(self.width * 0.6))

        # Position calculation
        line_heights = []
        for line in lines:
            _, h = get_text_size(font, line)
            line_heights.append(h)
        spacing = 8
        total_h = sum(line_heights) + spacing * (len(lines) - 1)

        margin = 50
        if text_position == "bottom_left":
            x = margin
            y = self.height - total_h - margin
        elif text_position == "bottom_right":
            x = self.width - int(self.width * 0.6) - margin
            y = self.height - total_h - margin
        elif text_position == "top_left":
            x = margin
            y = margin
        elif text_position == "top_right":
            x = self.width - int(self.width * 0.6) - margin
            y = margin
        else:  # center
            x = (self.width - int(self.width * 0.6)) // 2
            y = (self.height - total_h) // 2

        for i, line in enumerate(lines):
            draw_text_with_shadow(
                draw, (x, y), line, font,
                fill=self.style.text_color,
                shadow_color="#000000",
                offset=3,
            )
            y += line_heights[i] + spacing

        output = canvas.convert("RGB")
        output.save(output_path, "JPEG", quality=95)
        print(f"  Saved: {output_path} ({self.width}x{self.height})")
        return output_path

    def generate_from_video(
        self,
        video_path: str,
        text: str,
        template: str = "bold_text",
        highlight_words: Optional[List[str]] = None,
        output_path: str = "thumbnail.jpg",
    ) -> str:
        """Auto-extract best frame + face from video and generate thumbnail."""
        print(f"  Analyzing video for best thumbnail frame...")
        best_frame = find_best_video_frame(video_path)

        if template == "face_text":
            return self.generate_face_text(
                text=text,
                face_image=best_frame,
                output_path=output_path,
            )
        elif template == "result":
            # Split text into result and subtitle
            parts = text.split(" ", 1)
            result_text = parts[0]
            subtitle = parts[1] if len(parts) > 1 else ""
            return self.generate_result(
                result_text=result_text,
                subtitle=subtitle,
                face_image=best_frame,
                output_path=output_path,
            )
        elif template == "minimal":
            return self.generate_minimal(
                background_image=best_frame,
                text=text,
                output_path=output_path,
            )
        else:
            # Default: bold_text
            return self.generate_bold_text(
                text=text,
                highlight_words=highlight_words,
                face_image=best_frame,
                output_path=output_path,
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="YouTube thumbnail generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Thumbnail template")

    # bold-text
    p_bold = subparsers.add_parser("bold-text", help="Bold text + accent bar + optional face")
    p_bold.add_argument("--text", required=True, help="Main text (2-4 words ideal)")
    p_bold.add_argument("--highlight", default=None, help="Comma-separated words to highlight")
    p_bold.add_argument("--face", default=None, help="Path to face image or video")
    p_bold.add_argument("--style", default="youtube_red", help="Preset style name")
    p_bold.add_argument("--output", default="thumbnail.jpg", help="Output path")

    # face-text
    p_face = subparsers.add_parser("face-text", help="Face cutout + text overlay")
    p_face.add_argument("--text", required=True, help="Main text")
    p_face.add_argument("--face", required=True, help="Path to face image or video")
    p_face.add_argument("--position", default="right", choices=["left", "right"],
                        help="Face position")
    p_face.add_argument("--style", default="youtube_red", help="Preset style name")
    p_face.add_argument("--output", default="thumbnail.jpg", help="Output path")

    # result
    p_result = subparsers.add_parser("result", help="Result/number highlight")
    p_result.add_argument("--result", required=True, help='Result text (e.g., "$14K")')
    p_result.add_argument("--subtitle", required=True, help='Supporting text (e.g., "in 48 Hours")')
    p_result.add_argument("--face", default=None, help="Path to face image or video")
    p_result.add_argument("--style", default="youtube_red", help="Preset style name")
    p_result.add_argument("--output", default="thumbnail.jpg", help="Output path")

    # split
    p_split = subparsers.add_parser("split", help="Before/after split comparison")
    p_split.add_argument("--left-image", required=True, help="Left side image")
    p_split.add_argument("--right-image", required=True, help="Right side image")
    p_split.add_argument("--left-label", required=True, help="Left side label")
    p_split.add_argument("--right-label", required=True, help="Right side label")
    p_split.add_argument("--style", default="youtube_red", help="Preset style name")
    p_split.add_argument("--output", default="thumbnail.jpg", help="Output path")

    # minimal
    p_minimal = subparsers.add_parser("minimal", help="Clean minimal with background")
    p_minimal.add_argument("--background", required=True, help="Background image")
    p_minimal.add_argument("--text", required=True, help="Overlay text")
    p_minimal.add_argument("--text-position", default="bottom_left",
                           choices=["bottom_left", "bottom_right", "top_left", "top_right", "center"],
                           help="Text position")
    p_minimal.add_argument("--style", default="youtube_red", help="Preset style name")
    p_minimal.add_argument("--output", default="thumbnail.jpg", help="Output path")

    # from-video
    p_video = subparsers.add_parser("from-video", help="Auto-extract frame + generate thumbnail")
    p_video.add_argument("--input", required=True, help="Video file")
    p_video.add_argument("--text", required=True, help="Thumbnail text")
    p_video.add_argument("--template", default="bold_text",
                         choices=["bold_text", "face_text", "result", "minimal"],
                         help="Template to use")
    p_video.add_argument("--highlight", default=None, help="Comma-separated words to highlight")
    p_video.add_argument("--style", default="youtube_red", help="Preset style name")
    p_video.add_argument("--output", default="thumbnail.jpg", help="Output path")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    style_name = getattr(args, "style", "youtube_red")
    gen = ThumbnailGenerator(style=style_name)

    if args.command == "bold-text":
        highlight = args.highlight.split(",") if args.highlight else None
        gen.generate_bold_text(
            text=args.text,
            highlight_words=highlight,
            face_image=args.face,
            output_path=args.output,
        )

    elif args.command == "face-text":
        gen.generate_face_text(
            text=args.text,
            face_image=args.face,
            face_position=args.position,
            output_path=args.output,
        )

    elif args.command == "result":
        gen.generate_result(
            result_text=args.result,
            subtitle=args.subtitle,
            face_image=args.face,
            output_path=args.output,
        )

    elif args.command == "split":
        gen.generate_split(
            left_image=args.left_image,
            right_image=args.right_image,
            left_label=args.left_label,
            right_label=args.right_label,
            output_path=args.output,
        )

    elif args.command == "minimal":
        gen.generate_minimal(
            background_image=args.background,
            text=args.text,
            text_position=args.text_position,
            output_path=args.output,
        )

    elif args.command == "from-video":
        highlight = args.highlight.split(",") if args.highlight else None
        gen.generate_from_video(
            video_path=args.input,
            text=args.text,
            template=args.template,
            highlight_words=highlight,
            output_path=args.output,
        )


if __name__ == "__main__":
    main()
