#!/usr/bin/env python3
"""
WhisperFlow — Local voice-to-text dictation for macOS (WisprFlow replacement).

Records from system mic, transcribes locally with faster-whisper,
cleans up filler words, pastes into the active text field. Runs as a macOS menubar app.

Usage:
  python execution/whisper_flow.py              # Run as menubar app
  python execution/whisper_flow.py --test-mic   # Test microphone capture
  python execution/whisper_flow.py --test-paste # Test paste mechanism
  python execution/whisper_flow.py --test-cleanup "text"  # Test filler cleanup

Controls:
  Single tap Left Option (⌥)   — Start/stop recording
  Double-tap Left Option (⌥)   — Toggle locked recording mode (hands-free)
  Long-press Right Option (>1s) — Pause/resume recording
  Click stop button on overlay  — Stop recording
  Hold middle mouse button 2s   — Toggle recording (alternative)

Dependencies:
  pip install sounddevice numpy faster-whisper rumps pynput pyobjc-framework-Quartz

Permissions required:
  System Settings > Privacy & Security > Accessibility > Terminal (or IDE)
  System Settings > Privacy & Security > Input Monitoring > Terminal (or IDE)
  System Settings > Privacy & Security > Microphone > Terminal (or IDE)
"""

from __future__ import annotations

import os
import sys
import signal
import wave
import time
import math
import queue as queue_mod
import threading
import subprocess
from enum import Enum
from pathlib import Path

import json

import numpy as np
import sounddevice as sd

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# ─── Configuration ───────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_MOUSE_HOLD_SECONDS = float(os.getenv("WHISPER_MOUSE_HOLD_SECONDS", "2.0"))
WHISPER_CLEANUP_MODE = os.getenv("WHISPER_CLEANUP_MODE", "regex")  # regex | api | none
WHISPER_HOTKEY_TAP_TIMEOUT = float(os.getenv("WHISPER_HOTKEY_TAP_TIMEOUT", "0.4"))
WHISPER_DOUBLE_TAP_WINDOW = float(os.getenv("WHISPER_DOUBLE_TAP_WINDOW", "0.6"))
WHISPER_PAUSE_HOLD_THRESHOLD = float(os.getenv("WHISPER_PAUSE_HOLD_THRESHOLD", "1.0"))
WHISPER_RESTORE_CLIPBOARD = os.getenv("WHISPER_RESTORE_CLIPBOARD", "true").lower() == "true"
WHISPER_VAD_FILTER = os.getenv("WHISPER_VAD_FILTER", "true").lower() == "true"

MIN_RECORDING_SECONDS = 0.5

TMP_DIR = PROJECT_ROOT / ".tmp" / "whisper"
TMP_DIR.mkdir(parents=True, exist_ok=True)

SOUND_START = "/System/Library/Sounds/Tink.aiff"
SOUND_STOP = "/System/Library/Sounds/Pop.aiff"

DICTIONARY_PATH = TMP_DIR / "dictionary.json"


# ─── Sound Effects ───────────────────────────────────────────────────────────

def play_sound(path: str):
    """Play a system sound asynchronously."""
    subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ─── Custom Dictionary (learns spelling corrections) ────────────────────────

class WhisperDictionary:
    """Persistent dictionary that learns user corrections.

    Stores word mappings in JSON. Used for:
    1. Hotwords prompt for Whisper (improves recognition of known names/terms)
    2. Post-transcription find/replace for misspellings Whisper consistently gets wrong
    """

    def __init__(self, path: Path = DICTIONARY_PATH):
        self.path = path
        self.corrections: dict[str, str] = {}  # wrong → right (case-insensitive keys)
        self.hotwords: list[str] = []  # known proper nouns/terms
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.corrections = data.get("corrections", {})
                self.hotwords = data.get("hotwords", [])
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self):
        self.path.write_text(json.dumps({
            "corrections": self.corrections,
            "hotwords": self.hotwords,
        }, indent=2, ensure_ascii=False))

    def add_correction(self, wrong: str, right: str) -> str:
        """Add a spelling correction. Returns notification message."""
        key = wrong.lower()
        self.corrections[key] = right
        # Also add the correct spelling as a hotword for Whisper
        if right not in self.hotwords:
            self.hotwords.append(right)
        self._save()
        return f"Dictionary updated: \"{wrong}\" → \"{right}\""

    def add_hotword(self, word: str):
        """Add a word Whisper should recognize (proper noun, brand, etc.)."""
        if word not in self.hotwords:
            self.hotwords.append(word)
            self._save()

    def apply(self, text: str) -> str:
        """Apply all corrections to transcribed text."""
        for wrong, right in self.corrections.items():
            # Case-insensitive replacement preserving word boundaries
            pattern = re.compile(r'\b' + re.escape(wrong) + r'\b', re.IGNORECASE)
            text = pattern.sub(right, text)
        return text

    def get_hotwords_prompt(self) -> str:
        """Build a prompt hint string for Whisper initial_prompt."""
        if not self.hotwords:
            return ""
        return "Known names and terms: " + ", ".join(self.hotwords) + ". "


# Global dictionary instance
_dictionary = WhisperDictionary()


# ─── Transcription History (SQLite) ─────────────────────────────────────────

import sqlite3
from datetime import datetime

HISTORY_DB_PATH = TMP_DIR / "history.db"

class TranscriptionHistory:
    def __init__(self, db_path: Path = HISTORY_DB_PATH):
        self.db_path = db_path
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL, duration_s REAL NOT NULL,
                raw_text TEXT NOT NULL, cleaned_text TEXT NOT NULL,
                word_count INTEGER NOT NULL)""")
            conn.commit()

    def save(self, duration_s: float, raw_text: str, cleaned_text: str):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO transcriptions (timestamp, duration_s, raw_text, cleaned_text, word_count) VALUES (?,?,?,?,?)",
                (datetime.now().isoformat(), duration_s, raw_text, cleaned_text, len(cleaned_text.split())))
            conn.commit()

    def list_recent(self, limit=20):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM transcriptions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    def search(self, query: str, limit=20):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM transcriptions WHERE cleaned_text LIKE ? ORDER BY id DESC LIMIT ?", (f"%{query}%", limit)).fetchall()]

    def stats(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            r = conn.execute("SELECT COUNT(*), COALESCE(SUM(word_count),0), COALESCE(SUM(duration_s),0) FROM transcriptions").fetchone()
            return {"total": r[0], "words": r[1], "minutes": round(r[2]/60, 1)}

_history = TranscriptionHistory()


# ─── Correction Tracker (Keystroke Monitoring) ───────────────────────────────

class CorrectionTracker:
    """Monitors keystrokes after paste to detect word corrections.

    After WhisperFlow pastes text, if the user backspaces over a word and retypes
    it differently, auto-learns the correction into the dictionary. Works in any
    app (VS Code, terminals, browsers) — no Accessibility API needed.

    For corrections in the middle of text (not from the end), use the menubar
    'Teach Correction...' dialog instead.
    """

    WATCH_SECONDS = 20.0     # how long to monitor after paste
    IDLE_TIMEOUT = 1.5       # seconds of no typing = finalize pending correction
    BACKSPACE_KEYCODE = 51
    SPACE_KEYCODE = 49
    ARROW_KEYCODES = {123, 124, 125, 126}   # left, right, down, up
    RETURN_KEYCODES = {36, 76}              # return, numpad enter

    def __init__(self, dictionary: WhisperDictionary, overlay=None):
        self.dictionary = dictionary
        self.overlay = overlay
        self._watching = False
        self._pasted_text = ""
        self._backspace_count = 0
        self._typed_chars: list[str] = []
        self._last_keystroke_time = 0.0
        self._watch_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_paste(self, text: str, engine=None):
        """Start monitoring keystrokes for corrections after a paste."""
        with self._lock:
            self._pasted_text = text
            self._watching = True
            self._backspace_count = 0
            self._typed_chars = []
            self._last_keystroke_time = time.time()

        if self._watch_timer:
            self._watch_timer.cancel()
        self._watch_timer = threading.Timer(self.WATCH_SECONDS, self._stop_watching)
        self._watch_timer.start()
        print(f"[WhisperFlow] Correction watch active ({self.WATCH_SECONDS}s)")

    @property
    def watching(self) -> bool:
        return self._watching

    def on_key_event(self, keycode: int, char: str | None = None):
        """Called from CGEventTap on each key-down while watching."""
        with self._lock:
            if not self._watching:
                return

            now = time.time()

            # Idle gap with pending data = finalize the correction
            if (self._typed_chars and self._backspace_count > 0
                    and (now - self._last_keystroke_time) > self.IDLE_TIMEOUT):
                self._analyze_and_notify()
                self._backspace_count = 0
                self._typed_chars = []

            self._last_keystroke_time = now

            # Arrow keys = cursor moved away from end, can't track position
            if keycode in self.ARROW_KEYCODES:
                if self._typed_chars and self._backspace_count > 0:
                    self._analyze_and_notify()
                self._backspace_count = 0
                self._typed_chars = []
                return

            # Return/Enter = finalize pending correction
            if keycode in self.RETURN_KEYCODES:
                if self._typed_chars and self._backspace_count > 0:
                    self._analyze_and_notify()
                self._backspace_count = 0
                self._typed_chars = []
                return

            # Backspace
            if keycode == self.BACKSPACE_KEYCODE:
                if self._typed_chars:
                    # Backspacing over their own new typing
                    self._typed_chars.pop()
                else:
                    self._backspace_count += 1
                return

            # Space after a correction = word boundary, finalize
            if keycode == self.SPACE_KEYCODE and self._backspace_count > 0 and self._typed_chars:
                self._analyze_and_notify()
                self._backspace_count = 0
                self._typed_chars = []
                return

            # Printable character
            if char and len(char) == 1 and char.isprintable():
                self._typed_chars.append(char)

    def _analyze_and_notify(self):
        """Check if backspace+retype was a word correction. Caller must hold _lock."""
        if not self._typed_chars or self._backspace_count == 0 or not self._pasted_text:
            return

        typed_text = "".join(self._typed_chars).strip()
        if not typed_text:
            return

        # What was deleted from the end of the pasted text?
        if self._backspace_count > len(self._pasted_text):
            return
        deleted = self._pasted_text[-self._backspace_count:].strip()
        if not deleted or deleted.lower() == typed_text.lower():
            return

        # Extract last word deleted vs first word typed
        deleted_words = deleted.split()
        typed_words = typed_text.split()
        if not deleted_words or not typed_words:
            return

        wrong = deleted_words[-1].strip(".,!?;:\"'()")
        right = typed_words[0].strip(".,!?;:\"'()")

        if (wrong and right
                and wrong.lower() != right.lower()
                and len(wrong) > 1 and len(right) > 1):
            msg = self.dictionary.add_correction(wrong.lower(), right)
            print(f"[WhisperFlow] Auto-learned: {msg}")
            # Immediate macOS notification
            try:
                subprocess.Popen([
                    "osascript", "-e",
                    f'display notification "{msg}" with title "WhisperFlow Dictionary"'
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            # Also queue for overlay pill on next recording
            if self.overlay:
                self.overlay._pending_notification = msg
            # Update pasted text to reflect correction
            self._pasted_text = self._pasted_text[:-self._backspace_count] + typed_text

    def _stop_watching(self):
        """End correction watch window. Finalize any pending correction."""
        with self._lock:
            if self._typed_chars and self._backspace_count > 0:
                self._analyze_and_notify()
            self._watching = False
            self._backspace_count = 0
            self._typed_chars = []
        print("[WhisperFlow] Correction watch ended")

_correction_tracker = None  # initialized after overlay is created


# ─── Waveform Overlay (Native Cocoa) ────────────────────────────────────────
# IMPORTANT: All methods except update_amplitude() must be called from the main thread.
# The WhisperFlowApp ensures this by processing the engine's main_queue via a rumps Timer.

# Module-level ObjC class — MUST be at module level to prevent PyObjC garbage collection.
# If defined as a nested class inside a method, the ObjC runtime loses the Python class
# reference and crashes with SIGTRAP (exit 133).
_waveform_overlay_ref = None  # Set before creating the view

def _create_waveform_view_class():
    """Create the WaveformView NSView subclass at module level."""
    from AppKit import NSView, NSTrackingArea

    class WaveformView(NSView):
        def drawRect_(self, rect):
            if _waveform_overlay_ref is not None:
                _waveform_overlay_ref._draw(rect)

        def mouseDown_(self, event):
            if _waveform_overlay_ref is not None:
                loc = self.convertPoint_fromView_(event.locationInWindow(), None)
                _waveform_overlay_ref._handle_click(loc.x, loc.y)

        def mouseEntered_(self, event):
            if _waveform_overlay_ref is not None:
                _waveform_overlay_ref._hovering = True
                self.setNeedsDisplay_(True)

        def mouseExited_(self, event):
            if _waveform_overlay_ref is not None:
                _waveform_overlay_ref._hovering = False
                self.setNeedsDisplay_(True)

        def updateTrackingAreas(self):
            for ta in self.trackingAreas():
                self.removeTrackingArea_(ta)
            ta = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                self.bounds(), 0x01 | 0x80, self, None)  # mouseEnteredAndExited | activeAlways
            self.addTrackingArea_(ta)
            NSView.updateTrackingAreas(self)

    return WaveformView

# Lazy-init: class created once on first use (after AppKit is available)
_WaveformViewClass = None

def _get_waveform_view_class():
    global _WaveformViewClass
    if _WaveformViewClass is None:
        _WaveformViewClass = _create_waveform_view_class()
    return _WaveformViewClass


class WaveformOverlay:
    """Native macOS floating pill with animated dots — WisprFlow style.

    Must be instantiated on the main thread (e.g., in WhisperFlowApp.__init__).
    """

    NUM_DOTS = 15
    DOT_RADIUS = 2.5
    DOT_GAP = 5
    PADDING_H = 16
    PILL_HEIGHT = 36

    def __init__(self):
        self.panel = None
        self.view = None
        self.anim_timer = None
        self.amplitude = 0.0
        self.dot_levels = [0.0] * self.NUM_DOTS
        self._lock = threading.Lock()
        self._win_width = 0
        self._win_height = self.PILL_HEIGHT
        self._visual_state = "recording"  # recording | paused | locked | transcribing
        self._engine = None
        self._stop_btn_rect = (0, 0, 0, 0)
        self._progress = 0.0  # 0.0–1.0 for transcribing progress bar
        self._notification_text = ""  # e.g. "Dictionary updated: Savo → Sabbo"
        self._notification_until = 0.0  # timestamp when notification expires
        self._hovering = False
        self._pause_btn_rect = (0, 0, 0, 0)
        self._pending_notification = ""

        self._create_panel()

    def set_engine(self, engine):
        self._engine = engine

    def set_visual_state(self, state: str):
        self._visual_state = state

    def _create_panel(self):
        """Create the NSPanel and custom view. MUST run on main thread."""
        from AppKit import (
            NSPanel, NSColor, NSScreen,
            NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
        )
        from Foundation import NSMakeRect

        dots_w = self.NUM_DOTS * (self.DOT_RADIUS * 2 + self.DOT_GAP) - self.DOT_GAP
        h = self.PILL_HEIGHT
        w = self.PADDING_H + dots_w + self.PADDING_H
        self._win_width = w
        self._win_height = h

        screen = NSScreen.mainScreen()
        sf = screen.frame()
        x = (sf.size.width - w) / 2
        y = 140  # above dock

        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(101)  # above fullscreen apps
        panel.setCollectionBehavior_(
            1 << 0 |   # canJoinAllSpaces
            1 << 4 |   # fullScreenAuxiliary
            1 << 7     # stationary
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setAlphaValue_(0.95)
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(False)
        panel.setAcceptsMouseMovedEvents_(True)
        panel.setFloatingPanel_(True)
        panel.setWorksWhenModal_(True)
        panel.setHidesOnDeactivate_(False)

        global _waveform_overlay_ref
        _waveform_overlay_ref = self

        WaveformView = _get_waveform_view_class()
        view = WaveformView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        panel.setContentView_(view)

        self.panel = panel
        self.view = view

    def _draw(self, rect):
        """Draw the pill: dark rounded rect with animated dots or progress bar."""
        from AppKit import NSColor, NSBezierPath, NSFont, NSAttributedString
        from AppKit import NSFontAttributeName, NSForegroundColorAttributeName
        from Foundation import NSMakeRect

        w = self._win_width
        h = self._win_height
        vs = self._visual_state
        radius = h / 2

        # Dark pill background
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.08, 0.12, 0.95).setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(0, 0, w, h), radius, radius
        ).fill()

        # Notification toast (e.g. "Dictionary updated: X → Y")
        now = time.time()
        if self._notification_text and now < self._notification_until:
            fade = min(1.0, (self._notification_until - now) / 0.5)
            attrs = {
                NSFontAttributeName: NSFont.systemFontOfSize_(11),
                NSForegroundColorAttributeName: NSColor.colorWithCalibratedRed_green_blue_alpha_(0.4, 0.85, 0.6, fade),
            }
            ns_label = NSAttributedString.alloc().initWithString_attributes_(self._notification_text, attrs)
            lw, lh = ns_label.size().width, ns_label.size().height
            ns_label.drawAtPoint_(((w - lw) / 2, (h - lh) / 2))
            return

        if vs == "transcribing":
            # Progress bar mode: "Transcribing..." text + animated fill bar
            with self._lock:
                progress = self._progress

            # Progress bar track
            bar_h = 4
            bar_margin = self.PADDING_H + 4
            bar_w = w - bar_margin * 2
            bar_y = 8
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.25, 0.25, 0.3, 1.0).setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(bar_margin, bar_y, bar_w, bar_h), 2, 2
            ).fill()

            # Progress bar fill
            fill_w = bar_w * progress
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.55, 0.75, 1.0, 1.0).setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(bar_margin, bar_y, fill_w, bar_h), 2, 2
            ).fill()

            # "Transcribing..." label
            label = "Thinking..." if progress < 0.3 else "Transcribing..."
            attrs = {
                NSFontAttributeName: NSFont.systemFontOfSize_(11),
                NSForegroundColorAttributeName: NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.7, 0.7, 0.75, 1.0
                ),
            }
            ns_label = NSAttributedString.alloc().initWithString_attributes_(label, attrs)
            label_w = ns_label.size().width
            ns_label.drawAtPoint_((((w - label_w) / 2), bar_y + bar_h + 5))
            return

        # Recording/paused mode: animated dots
        dots_total_w = self.NUM_DOTS * (self.DOT_RADIUS * 2 + self.DOT_GAP) - self.DOT_GAP
        start_x = (w - dots_total_w) / 2
        cy = h / 2

        for i in range(self.NUM_DOTS):
            val = self.dot_levels[i]
            dot_h = self.DOT_RADIUS * 2 + val * 24  # more dynamic range
            dot_w = self.DOT_RADIUS * 2
            dx = start_x + i * (self.DOT_RADIUS * 2 + self.DOT_GAP)
            dy = cy - dot_h / 2

            if vs == "paused":
                NSColor.colorWithCalibratedRed_green_blue_alpha_(0.5, 0.5, 0.5, 0.7).setFill()
            else:
                brightness = 0.6 + val * 0.4
                NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    brightness, brightness, brightness, 1.0
                ).setFill()

            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(dx, dy, dot_w, dot_h),
                self.DOT_RADIUS, self.DOT_RADIUS
            ).fill()

        # Pause/play button on hover
        if self._hovering and vs in ("recording", "paused", "locked"):
            self._draw_pause_btn(w, h, vs)

    def _draw_pause_btn(self, w, h, vs):
        """Draw pause/play button on right side when hovering."""
        from AppKit import NSColor, NSBezierPath
        from Foundation import NSMakeRect
        size = 20
        bx = w - self.PADDING_H - size
        by = (h - size) / 2
        self._pause_btn_rect = (bx, by, size, size)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.2, 0.25, 0.8).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(bx, by, size, size)).fill()
        cx, cy = bx + size / 2, by + size / 2
        if vs == "paused":
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.4, 0.85, 0.6, 1.0).setFill()
            p = NSBezierPath.bezierPath()
            s = size * 0.3
            p.moveToPoint_((cx - s * 0.4, cy + s))
            p.lineToPoint_((cx - s * 0.4, cy - s))
            p.lineToPoint_((cx + s * 0.8, cy))
            p.closePath()
            p.fill()
        else:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.85, 0.4, 1.0).setFill()
            bw, bh, gap = 2.5, size * 0.35, 2.5
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(cx-gap-bw, cy-bh/2, bw, bh), 1, 1).fill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(cx+gap, cy-bh/2, bw, bh), 1, 1).fill()

    def _handle_click(self, x: float, y: float):
        """Click pause button or stop recording."""
        if self._hovering and self._visual_state in ("recording", "paused", "locked"):
            bx, by, bw, bh = self._pause_btn_rect
            if bx <= x <= bx + bw and by <= y <= by + bh:
                if self._engine:
                    self._engine.pause_or_resume()
                return
        if self._engine:
            self._engine.toggle_recording()

    def update_amplitude(self, amp: float):
        with self._lock:
            self.amplitude = amp

    def update_progress(self, progress: float):
        with self._lock:
            self._progress = min(1.0, max(0.0, progress))

    def show_notification(self, text: str, duration: float = 3.0):
        """Show a brief notification on the pill (e.g., dictionary update)."""
        with self._lock:
            self._notification_text = text
            self._notification_until = time.time() + duration

    def animate(self):
        """Update dot levels and trigger redraw. MUST be called on main thread."""
        with self._lock:
            amp = self.amplitude

        if self._visual_state == "paused":
            for i in range(self.NUM_DOTS):
                self.dot_levels[i] *= 0.9
        elif self._visual_state == "transcribing":
            # Pulsing thinking animation — dots sweep left to right
            t = time.time()
            for i in range(self.NUM_DOTS):
                phase = (t * 3.0 - i * 0.3) % (math.pi * 2)
                self.dot_levels[i] = max(0.08, abs(math.sin(phase)) * 0.6)
        else:
            t = time.time()
            for i in range(self.NUM_DOTS):
                # More variation per dot — each reacts differently to amplitude
                wave1 = math.sin(t * 6.0 + i * 0.7) * 0.25
                wave2 = math.sin(t * 10.0 + i * 1.3) * 0.2
                jitter = math.sin(t * 15.0 + i * 2.1) * 0.1
                center_w = 1.0 - abs(i - self.NUM_DOTS / 2) / (self.NUM_DOTS / 2) * 0.25
                target = max(0.01, min(1.0, amp * center_w * (0.3 + wave1 + wave2 + jitter)))
                # Fast attack (0.6), slower decay (0.2) — snappy response
                if target > self.dot_levels[i]:
                    self.dot_levels[i] += (target - self.dot_levels[i]) * 0.6
                else:
                    self.dot_levels[i] += (target - self.dot_levels[i]) * 0.2

        if self.view:
            self.view.setNeedsDisplay_(True)

    def show(self):
        """Show the overlay and start animation. MUST be called on main thread."""
        from Foundation import NSTimer, NSRunLoop, NSDefaultRunLoopMode

        self.dot_levels = [0.0] * self.NUM_DOTS
        self.amplitude = 0.0
        # Show any pending dictionary notification
        if self._pending_notification:
            self.show_notification(self._pending_notification)
            self._pending_notification = ""
        if self.panel:
            self.panel.orderFront_(None)

        if self.anim_timer:
            self.anim_timer.invalidate()
        self.anim_timer = NSTimer.timerWithTimeInterval_repeats_block_(
            0.033, True, lambda t: self.animate()
        )
        NSRunLoop.mainRunLoop().addTimer_forMode_(self.anim_timer, NSDefaultRunLoopMode)

    def hide(self):
        """Hide the overlay immediately. MUST be called on main thread."""
        if self.anim_timer:
            self.anim_timer.invalidate()
            self.anim_timer = None
        if self.panel:
            self.panel.orderOut_(None)


# ─── State Machine ───────────────────────────────────────────────────────────

class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    TRANSCRIBING = "transcribing"
    TYPING = "typing"


class WhisperFlowEngine:
    """Core engine: recording, transcription, text insertion.

    The overlay is passed in (pre-created on main thread by the app).
    All overlay show/hide goes through main_queue, processed on main thread.
    """

    def __init__(self, overlay: WaveformOverlay, on_state_change=None):
        self.state = State.IDLE
        self.lock = threading.Lock()
        self.audio_chunks: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self.recording_start: float = 0
        self._peak_amplitude: float = 0.0
        self.model = None
        self.on_state_change = on_state_change or (lambda s: None)
        self.overlay = overlay
        self.main_queue: queue_mod.Queue = queue_mod.Queue()
        self.toggle_locked = False  # double-tap persistent recording mode
        self._native_rate: int = SAMPLE_RATE  # set properly by _open_mic

    def load_model(self):
        from faster_whisper import WhisperModel
        print(f"[WhisperFlow] Loading model '{WHISPER_MODEL}' ({WHISPER_COMPUTE_TYPE})...")
        self.model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type=WHISPER_COMPUTE_TYPE)
        print("[WhisperFlow] Model loaded.")

    def _set_state(self, new_state: State):
        self.state = new_state
        self.on_state_change(new_state)

    def toggle_recording(self):
        with self.lock:
            if self.state == State.IDLE:
                self._start_recording()
            elif self.state == State.RECORDING:
                self._stop_recording()
            elif self.state == State.PAUSED:
                self._stop_recording()
            elif self.state in (State.TRANSCRIBING, State.TYPING):
                # Force hide overlay if stuck
                self.main_queue.put("hide")

    def pause_or_resume(self):
        """Long-press action: pause if recording, resume if paused."""
        with self.lock:
            if self.state == State.RECORDING:
                self._pause_recording()
            elif self.state == State.PAUSED:
                self._resume_recording()

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[WhisperFlow] Audio warning: {status}")
        data = indata
        # Downsample to 16kHz mono if mic is at native rate
        if data.shape[1] > 1:
            data = data.mean(axis=1, keepdims=True)
        if self._native_rate and self._native_rate != SAMPLE_RATE:
            ratio = int(round(self._native_rate / SAMPLE_RATE))
            if ratio > 1:
                data = data[::ratio]
        self.audio_chunks.append(data.copy())
        # Use original for amplitude (full-rate = more responsive)
        rms = float(np.sqrt(np.mean(indata ** 2)))
        peak = float(np.abs(indata).max())
        if peak > self._peak_amplitude:
            self._peak_amplitude = peak
        amp = min(1.0, (peak * 0.6 + rms * 0.4) * 25.0)
        self.overlay.update_amplitude(amp)

    def _start_recording(self):
        play_sound(SOUND_START)
        self.audio_chunks = []
        self._peak_amplitude = 0.0
        self.recording_start = time.time()
        self.toggle_locked = False
        self.main_queue.put("show")

        try:
            self.stream, self._native_rate = self._open_mic()
            self.stream.start()
            self._set_state(State.RECORDING)
            print("[WhisperFlow] Recording started.")
        except Exception as e:
            print(f"[WhisperFlow] ERROR opening mic: {e}", flush=True)
            self.main_queue.put("hide")
            self._set_state(State.IDLE)

    def _open_mic(self):
        """Open mic stream at native rate, resample later. Falls back on error."""
        dev_info = sd.query_devices(kind='input')
        name = dev_info['name']
        native_rate = int(dev_info['default_samplerate'])
        max_ch = dev_info['max_input_channels']

        # Try configs in order: 16kHz mono (proven working), then native rate fallbacks
        configs = [
            (SAMPLE_RATE, 1),
            (native_rate, 1),
            (native_rate, min(max_ch, 2)),
        ]
        for rate, ch in configs:
            try:
                print(f"[WhisperFlow] Mic: {name} — trying {rate}Hz/{ch}ch")
                stream = sd.InputStream(
                    samplerate=rate, channels=ch,
                    dtype=DTYPE, callback=self._audio_callback,
                )
                print(f"[WhisperFlow] Mic: {name} — opened at {rate}Hz/{ch}ch")
                return stream, rate
            except Exception as e:
                print(f"[WhisperFlow] Mic config {rate}Hz/{ch}ch failed: {e}")
                continue

        raise RuntimeError(f"Could not open mic '{name}' with any config")

    def _stop_recording(self):
        play_sound(SOUND_STOP)
        self.toggle_locked = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        duration = time.time() - self.recording_start
        if duration < MIN_RECORDING_SECONDS:
            print(f"[WhisperFlow] Recording too short ({duration:.1f}s), discarding.")
            self.main_queue.put("hide")
            self._set_state(State.IDLE)
            return

        # Switch pill to transcribing mode (progress bar) instead of hiding
        self.overlay.update_progress(0.0)
        self.main_queue.put("transcribing")
        print(f"[WhisperFlow] Recording stopped ({duration:.1f}s). Peak amplitude: {self._peak_amplitude:.4f}. Transcribing...")
        self._set_state(State.TRANSCRIBING)
        threading.Thread(target=self._transcribe_and_paste, args=(duration,), daemon=True).start()

    def _pause_recording(self):
        """Pause: stop the audio stream but keep accumulated chunks."""
        play_sound(SOUND_STOP)
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.main_queue.put("pause")
        self._set_state(State.PAUSED)
        print("[WhisperFlow] Recording paused.")

    def _resume_recording(self):
        """Resume: open a new stream, append to existing chunks."""
        play_sound(SOUND_START)
        self.main_queue.put("resume")
        self.stream, self._native_rate = self._open_mic()
        self.stream.start()
        self._set_state(State.RECORDING)
        print("[WhisperFlow] Recording resumed.")

    def process_main_queue(self):
        """Process pending overlay actions. Call from main thread only."""
        try:
            while True:
                action = self.main_queue.get_nowait()
                if action == "show":
                    self.overlay.set_visual_state("recording")
                    self.overlay.show()
                elif action == "hide":
                    self.overlay.hide()
                elif action == "transcribing":
                    self.overlay.set_visual_state("transcribing")
                    # Pill stays visible — switches to progress bar mode
                elif action == "pause":
                    self.overlay.set_visual_state("paused")
                elif action == "resume":
                    self.overlay.set_visual_state("recording")
                elif action == "lock":
                    self.overlay.set_visual_state("locked")
        except queue_mod.Empty:
            pass

    def _transcribe_and_paste(self, duration=0.0):
        try:
            if not self.audio_chunks:
                self.main_queue.put("hide")
                self._set_state(State.IDLE)
                return

            self.overlay.update_progress(0.1)
            audio_data = np.concatenate(self.audio_chunks, axis=0)
            wav_path = TMP_DIR / f"recording_{int(time.time())}.wav"
            self._save_wav(wav_path, audio_data)

            self.overlay.update_progress(0.3)
            text = self._transcribe(str(wav_path))

            self.overlay.update_progress(0.7)
            try:
                wav_path.unlink()
            except OSError:
                pass

            if not text or not text.strip():
                print("[WhisperFlow] No speech detected.")
                self.main_queue.put("hide")
                self._set_state(State.IDLE)
                return

            # Clean up filler words and formatting
            text = clean_transcript(text.strip())
            # Apply custom dictionary corrections
            text = _dictionary.apply(text)

            # Save to history
            try:
                _history.save(duration, text.strip(), text)
            except Exception:
                pass

            self.overlay.update_progress(0.9)
            print(f"[WhisperFlow] Transcribed: {text[:100]}{'...' if len(text) > 100 else ''}")
            self._set_state(State.TYPING)
            self.overlay.update_progress(1.0)
            time.sleep(0.15)  # brief moment at 100% so user sees completion
            self.main_queue.put("hide")
            paste_text(text)

            # Watch for user corrections to auto-learn dictionary
            if _correction_tracker:
                _correction_tracker.on_paste(text, engine=self)

        except Exception as e:
            print(f"[WhisperFlow] Error: {e}", file=sys.stderr)
            self.main_queue.put("hide")
        finally:
            self._set_state(State.IDLE)

    def _save_wav(self, path: Path, audio_data: np.ndarray):
        audio_int16 = (audio_data * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())

    def _transcribe(self, audio_path: str) -> str:
        if not self.model:
            self.load_model()
        # Build initial prompt with dictionary hotwords for better recognition
        hotwords = _dictionary.get_hotwords_prompt()
        prompt = hotwords + "The following is a clear, well-structured dictation."
        segments, _ = self.model.transcribe(
            audio_path,
            beam_size=5,
            vad_filter=WHISPER_VAD_FILTER,
            initial_prompt=prompt,
        )
        return " ".join(seg.text for seg in segments).strip()


# ─── Text Cleanup ────────────────────────────────────────────────────────────

import re

FILLER_PATTERNS = [
    re.compile(r'\b(um+|uh+m?|er+m?|ah+|eh+|hm+|hmm+)\b', re.IGNORECASE),
    re.compile(r'\b(you know,?\s*|I mean,?\s*|like,?\s+(?=you know|basically|literally))', re.IGNORECASE),
    re.compile(r'\s*\.\.\.\s*'),  # ellipsis from hesitation
]


def clean_transcript(text: str) -> str:
    """Clean up transcription: remove filler words, fix punctuation, capitalize."""
    if WHISPER_CLEANUP_MODE == "none":
        return text

    # Regex cleanup (always runs for 'regex' and 'api' modes)
    for pattern in FILLER_PATTERNS:
        text = pattern.sub(' ', text)

    # Collapse multiple spaces
    text = re.sub(r'\s{2,}', ' ', text)
    # Fix orphaned punctuation (space before comma/period)
    text = re.sub(r'\s+([,.\?!;:])', r'\1', text)
    # Capitalize first letter of sentences
    text = re.sub(r'(^|[.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
    text = text.strip()

    # Optional Claude Haiku API polish
    if WHISPER_CLEANUP_MODE == "api" and text:
        text = _api_cleanup(text)

    return text


def _api_cleanup(text: str) -> str:
    """Use Claude Haiku to polish transcription. ~$0.001 per call."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "Clean up this voice transcription. Remove filler words, fix grammar, "
                    "add proper punctuation and capitalization. Keep the meaning identical. "
                    "Return ONLY the cleaned text, nothing else.\n\n" + text
                ),
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[WhisperFlow] API cleanup failed: {e}, using regex-only")
        return text


# ─── Text Paste ──────────────────────────────────────────────────────────────

def paste_text(text: str):
    """Paste text into active field via CGEvent Cmd+V with clipboard save/restore."""
    from Quartz import (
        CGEventCreateKeyboardEvent, CGEventPost, CGEventSetFlags,
        kCGHIDEventTap, kCGEventFlagMaskCommand,
    )

    # Save current clipboard
    saved_clipboard = None
    if WHISPER_RESTORE_CLIPBOARD:
        try:
            saved_clipboard = subprocess.run(
                ["pbpaste"], capture_output=True, timeout=2
            ).stdout
        except Exception:
            pass

    # Set clipboard to our text
    proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    proc.communicate(text.encode("utf-8"))

    # Simulate Cmd+V via CGEvent (keycode 9 = 'v')
    time.sleep(0.05)
    V_KEYCODE = 9
    event_down = CGEventCreateKeyboardEvent(None, V_KEYCODE, True)
    CGEventSetFlags(event_down, kCGEventFlagMaskCommand)
    event_up = CGEventCreateKeyboardEvent(None, V_KEYCODE, False)
    CGEventSetFlags(event_up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, event_down)
    CGEventPost(kCGHIDEventTap, event_up)

    # Restore clipboard after a brief delay
    if saved_clipboard is not None:
        def restore():
            time.sleep(0.5)
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(saved_clipboard)
        threading.Thread(target=restore, daemon=True).start()


# ─── Input Listeners ────────────────────────────────────────────────────────

class CGEventTapHotkeyListener:
    """Listens for Left Option key gestures via CGEventTap (no pynput needed).

    Gestures:
      - Single tap (<400ms): toggle recording start/stop
      - Double-tap (<600ms between taps): toggle locked (persistent) recording mode
      - Long-press (>1s): pause/resume recording
    """

    LEFT_OPTION_KEYCODE = 58

    def __init__(self, engine: WhisperFlowEngine):
        self.engine = engine
        self._ropt_down_time: float = 0
        self._other_key_pressed = False
        self._last_tap_time: float = 0
        self._tap = None  # CFMachPort reference

    def _callback(self, proxy, event_type, event, refcon):
        from Quartz import (
            CGEventGetIntegerValueField, CGEventGetFlags,
            kCGKeyboardEventKeycode, kCGEventFlagsChanged,
            kCGEventKeyDown, kCGEventFlagMaskAlternate,
        )

        if event_type == kCGEventFlagsChanged:
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            if keycode == self.LEFT_OPTION_KEYCODE:
                current_flags = CGEventGetFlags(event)
                is_down = bool(current_flags & kCGEventFlagMaskAlternate)

                if is_down:
                    self._ropt_down_time = time.time()
                    self._other_key_pressed = False
                else:
                    # Key released
                    if self._ropt_down_time > 0:
                        held = time.time() - self._ropt_down_time
                        self._ropt_down_time = 0

                        if self._other_key_pressed:
                            return event  # ignore if other keys were pressed

                        if held >= WHISPER_PAUSE_HOLD_THRESHOLD:
                            # Long-press: pause/resume
                            print(f"[WhisperFlow] LONG PRESS ({held:.2f}s) — pause/resume", flush=True)
                            self.engine.pause_or_resume()
                        elif held < WHISPER_HOTKEY_TAP_TIMEOUT:
                            # Tap detected — check for double-tap
                            now = time.time()
                            if now - self._last_tap_time < WHISPER_DOUBLE_TAP_WINDOW:
                                # Double-tap: toggle locked mode
                                self._last_tap_time = 0
                                with self.engine.lock:
                                    if self.engine.state == State.RECORDING:
                                        self.engine.toggle_locked = True
                                        self.engine.main_queue.put("lock")
                                        print("[WhisperFlow] DOUBLE TAP — locked recording mode", flush=True)
                                    elif self.engine.state == State.IDLE:
                                        self.engine.toggle_recording()
                                        self.engine.toggle_locked = True
                                        self.engine.main_queue.put("lock")
                                        print("[WhisperFlow] DOUBLE TAP — started locked recording", flush=True)
                                    else:
                                        self.engine.toggle_recording()
                            else:
                                # Single tap: toggle
                                self._last_tap_time = now
                                print(f"[WhisperFlow] TAP ({held:.2f}s) — toggle", flush=True)
                                self.engine.toggle_recording()

        elif event_type == kCGEventKeyDown:
            self._other_key_pressed = True
            # Forward keystrokes to correction tracker when watching
            if _correction_tracker and _correction_tracker.watching:
                keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
                char = None
                try:
                    from AppKit import NSEvent as _NSEvent
                    ns_evt = _NSEvent.eventWithCGEvent_(event)
                    if ns_evt:
                        c = ns_evt.characters()
                        if c and len(c) == 1:
                            char = c
                except Exception:
                    pass
                _correction_tracker.on_key_event(keycode, char)
        elif event_type == 0xFFFFFFFF:
            # Tap was disabled by the system (timeout) — re-enable it
            if self._tap:
                from Quartz import CGEventTapEnable
                CGEventTapEnable(self._tap, True)
                print("[WhisperFlow] CGEventTap re-enabled after system timeout.", flush=True)

        return event

    def start(self):
        from Quartz import (
            CGEventTapCreate, kCGSessionEventTap, kCGHeadInsertEventTap,
            CGEventTapEnable, CFMachPortCreateRunLoopSource,
            kCGEventFlagsChanged, kCGEventKeyDown, CGEventMaskBit,
        )
        from Quartz import CFRunLoopAddSource, CFRunLoopRun, CFRunLoopGetCurrent
        from Quartz import kCFRunLoopDefaultMode

        mask = CGEventMaskBit(kCGEventFlagsChanged) | CGEventMaskBit(kCGEventKeyDown)
        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            0,  # kCGEventTapOptionDefault — passive, passes events through
            mask,
            self._callback,
            None,
        )
        if tap is None:
            print(
                "[WhisperFlow] ERROR: CGEventTap creation failed.\n"
                "  → Grant Accessibility permission to your terminal/IDE:\n"
                "    System Settings > Privacy & Security > Accessibility\n"
                "  → Also grant Input Monitoring permission:\n"
                "    System Settings > Privacy & Security > Input Monitoring\n"
                "  → Toggle OFF then ON if already listed, then restart.",
                flush=True,
            )
            return None

        self._tap = tap
        source = CFMachPortCreateRunLoopSource(None, tap, 0)

        def run():
            loop = CFRunLoopGetCurrent()
            CFRunLoopAddSource(loop, source, kCFRunLoopDefaultMode)
            CGEventTapEnable(tap, True)
            CFRunLoopRun()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        print(
            "[WhisperFlow] CGEventTap hotkey active:\n"
            "  Tap Left Option (⌥)       → start/stop recording\n"
            "  Double-tap Right Option     → locked (hands-free) mode\n"
            "  Long-press Right Option >1s → pause/resume",
            flush=True,
        )
        return t


class MouseHoldListener:
    def __init__(self, engine: WhisperFlowEngine):
        self.engine = engine
        self.hold_timer: threading.Timer | None = None

    def start(self):
        from pynput import mouse

        def on_click(x, y, button, pressed):
            if button != mouse.Button.middle:
                return
            if pressed:
                self.hold_timer = threading.Timer(
                    WHISPER_MOUSE_HOLD_SECONDS, self._on_hold
                )
                self.hold_timer.start()
            else:
                if self.hold_timer:
                    self.hold_timer.cancel()
                    self.hold_timer = None

        listener = mouse.Listener(on_click=on_click)
        listener.daemon = True
        listener.start()
        return listener

    def _on_hold(self):
        print("[WhisperFlow] Mouse hold detected — toggling recording.")
        self.engine.toggle_recording()


# ─── Menubar App ─────────────────────────────────────────────────────────────

ICON_IDLE = "🎤"
ICON_RECORDING = "🔴 REC"
ICON_PAUSED = "⏸️ PAUSED"
ICON_TRANSCRIBING = "⏳"
ICON_TYPING = "✍️"

STATE_ICONS = {
    State.IDLE: ICON_IDLE,
    State.RECORDING: ICON_RECORDING,
    State.PAUSED: ICON_PAUSED,
    State.TRANSCRIBING: ICON_TRANSCRIBING,
    State.TYPING: ICON_TYPING,
}


def _request_mic_permission():
    """Trigger macOS mic permission dialog for this process/app bundle."""
    try:
        import AVFoundation
        status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(
            AVFoundation.AVMediaTypeAudio
        )
        # 0=notDetermined, 1=restricted, 2=denied, 3=authorized
        if status == 0:
            print("[WhisperFlow] Requesting microphone permission...")
            done = threading.Event()
            def handler(granted):
                print(f"[WhisperFlow] Mic permission {'granted' if granted else 'DENIED'}")
                done.set()
            AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                AVFoundation.AVMediaTypeAudio, handler
            )
            done.wait(timeout=30)
        elif status == 2:
            print("[WhisperFlow] WARNING: Microphone access DENIED. Enable in System Settings → Privacy → Microphone.")
        elif status == 3:
            print("[WhisperFlow] Microphone permission already granted.")
    except Exception as e:
        print(f"[WhisperFlow] Mic permission check skipped: {e}")


def run_menubar_app():
    """Run WhisperFlow as a macOS menubar app."""
    import rumps

    class WhisperFlowApp(rumps.App):
        def __init__(self):
            super().__init__("WhisperFlow", title=ICON_IDLE, quit_button="Quit")
            self.menu = [
                rumps.MenuItem("Toggle Recording (tap ⌥)", callback=self._toggle),
                rumps.MenuItem("Teach Correction...", callback=self._teach_correction),
                rumps.MenuItem("Show Dictionary", callback=self._show_dictionary),
                None,
                rumps.MenuItem(f"Model: {WHISPER_MODEL}"),
                rumps.MenuItem("Status: Idle"),
            ]
            self.status_item = self.menu["Status: Idle"]

            # Create overlay on main thread (here in __init__, guaranteed safe)
            overlay = WaveformOverlay()

            # Create engine with pre-built overlay
            self.engine = WhisperFlowEngine(
                overlay=overlay,
                on_state_change=self._on_state_change,
            )

            # Wire overlay → engine for stop button callback
            overlay.set_engine(self.engine)

            # Initialize correction tracker with overlay for notifications
            global _correction_tracker
            _correction_tracker = CorrectionTracker(_dictionary, overlay)

            # Load model in background
            threading.Thread(target=self._load_model, daemon=True).start()

            # Request mic permission + run audio self-test after run loop starts
            self._mic_perm_timer = rumps.Timer(self._request_mic_perm, 2.0)
            self._mic_perm_timer.start()
            self._selftest_timer = rumps.Timer(self._run_audio_selftest, 5.0)
            self._selftest_timer.start()

            # Start input listeners
            self.hotkey_listener = CGEventTapHotkeyListener(self.engine)
            self.hotkey_listener.start()
            self.mouse_listener = MouseHoldListener(self.engine)
            self.mouse_listener.start()

            # Poll the engine's main_queue on main thread (every 30ms)
            self._queue_timer = rumps.Timer(self._poll_queue, 0.03)
            self._queue_timer.start()

            print("[WhisperFlow] Menubar app running. Tap Left Option (⌥) to record.")

        def _request_mic_perm(self, _):
            self._mic_perm_timer.stop()
            threading.Thread(target=_request_mic_permission, daemon=True).start()

        def _run_audio_selftest(self, _):
            self._selftest_timer.stop()
            threading.Thread(target=self._audio_selftest, daemon=True).start()

        def _audio_selftest(self):
            """Record 0.5s on startup to verify mic actually captures audio (not silent)."""
            try:
                test_audio = sd.rec(
                    int(SAMPLE_RATE * 0.5), samplerate=SAMPLE_RATE,
                    channels=1, dtype=DTYPE,
                )
                sd.wait()
                peak = float(np.abs(test_audio).max())
                if peak < 0.0001:
                    print(
                        "[WhisperFlow] WARNING: Audio self-test got silence (peak=0.0000).\n"
                        "  Mic permission may be denied for this binary.\n"
                        "  Fix: System Settings > Privacy & Security > Microphone > enable WhisperFlow",
                        flush=True,
                    )
                    self.title = "⚠️ MIC"
                else:
                    print(f"[WhisperFlow] Audio self-test passed (peak={peak:.4f})", flush=True)
            except Exception as e:
                print(f"[WhisperFlow] Audio self-test failed: {e}", flush=True)
                self.title = "⚠️ MIC"

        def _poll_queue(self, _):
            """Process overlay show/hide actions on the main thread."""
            self.engine.process_main_queue()

        def _load_model(self):
            self.title = "⏳ Loading..."
            try:
                self.engine.load_model()
                self.title = ICON_IDLE
            except Exception as e:
                self.title = "❌ ERR"
                rumps.notification("WhisperFlow Error", "Failed to load model", str(e))

        def _on_state_change(self, new_state: State):
            self.title = STATE_ICONS.get(new_state, ICON_IDLE)
            if self.status_item:
                self.status_item.title = f"Status: {new_state.value.capitalize()}"

        def _toggle(self, sender):
            self.engine.toggle_recording()

        def _teach_correction(self, sender):
            """Show an input dialog to teach a spelling correction."""
            try:
                result = subprocess.run(
                    ["osascript", "-e",
                     'set userInput to text returned of (display dialog '
                     '"Enter correction (wrong > right):\\n'
                     'Example: sabo > Sabbo" '
                     'default answer "" with title "WhisperFlow Dictionary")'],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode != 0:
                    return  # user cancelled
                raw = result.stdout.strip()
                if ">" not in raw:
                    subprocess.Popen(["osascript", "-e",
                        'display notification "Use format: wrong > right" with title "WhisperFlow"'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                wrong, right = [s.strip() for s in raw.split(">", 1)]
                if wrong and right:
                    msg = _dictionary.add_correction(wrong, right)
                    print(f"[WhisperFlow] Manual correction: {msg}")
                    subprocess.Popen(["osascript", "-e",
                        f'display notification "{msg}" with title "WhisperFlow Dictionary"'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"[WhisperFlow] Teach correction error: {e}")

        def _show_dictionary(self, sender):
            """Show current dictionary entries as a notification."""
            d = _dictionary
            if not d.corrections and not d.hotwords:
                msg = "Dictionary is empty"
            else:
                lines = []
                for wrong, right in d.corrections.items():
                    lines.append(f'"{wrong}" → "{right}"')
                if d.hotwords:
                    lines.append(f"Hotwords: {', '.join(d.hotwords[:10])}")
                msg = "\n".join(lines[:10])
                if len(d.corrections) > 10:
                    msg += f"\n...and {len(d.corrections) - 10} more"
            try:
                subprocess.Popen(["osascript", "-e",
                    f'display dialog "{msg}" with title "WhisperFlow Dictionary" buttons {{"OK"}} default button "OK"'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    app = WhisperFlowApp()
    app.run()


# ─── CLI Test Commands ───────────────────────────────────────────────────────

def test_mic():
    print("[Test] Recording 3 seconds from default mic...")
    print(sd.query_devices())
    audio = sd.rec(int(3 * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
    sd.wait()
    print(f"[Test] Captured {len(audio)} samples ({len(audio)/SAMPLE_RATE:.1f}s)")
    print(f"[Test] Max amplitude: {np.abs(audio).max():.4f}")
    if np.abs(audio).max() < 0.01:
        print("[Test] WARNING: Very low audio level — check your microphone!")
    else:
        print("[Test] Microphone is working.")


def test_paste():
    print("[Test] In 3 seconds, 'Hello from WhisperFlow!' will be pasted.")
    print("[Test] Click into a text field NOW...")
    time.sleep(3)
    paste_text("Hello from WhisperFlow!")
    print("[Test] Done.")


def test_transcribe():
    test_path = TMP_DIR / "test_recording.wav"
    if not test_path.exists():
        print("[Test] No test recording found. Run --test-mic first.")
        return
    engine = WhisperFlowEngine(overlay=WaveformOverlay.__new__(WaveformOverlay))
    engine.load_model()
    text = engine._transcribe(str(test_path))
    print(f"[Test] Raw transcription: '{text}'")
    cleaned = clean_transcript(text)
    print(f"[Test] After cleanup: '{cleaned}'")


def test_cleanup():
    if len(sys.argv) < 3:
        sample = "So um basically I was like thinking about uh the thing you know and I mean it's like really important"
    else:
        sample = " ".join(sys.argv[2:])
    print(f"[Test] Input:   '{sample}'")
    result = clean_transcript(sample)
    print(f"[Test] Cleaned: '{result}'")


def dict_cmd():
    """Manage the custom dictionary. Usage:
      --dict add "Savo" "Sabbo"     — Add correction
      --dict hotword "Sabbo"        — Add hotword (proper noun)
      --dict list                   — Show all entries
      --dict remove "savo"          — Remove a correction
    """
    if len(sys.argv) < 3:
        print("Usage: whisper_flow.py --dict [add|hotword|list|remove] [args...]")
        return

    action = sys.argv[2]
    d = _dictionary

    if action == "add" and len(sys.argv) >= 5:
        wrong, right = sys.argv[3], sys.argv[4]
        msg = d.add_correction(wrong, right)
        print(f"[Dictionary] {msg}")
    elif action == "hotword" and len(sys.argv) >= 4:
        word = sys.argv[3]
        d.add_hotword(word)
        print(f"[Dictionary] Added hotword: {word}")
    elif action == "list":
        print(f"[Dictionary] File: {d.path}")
        if d.corrections:
            print("  Corrections:")
            for wrong, right in d.corrections.items():
                print(f"    \"{wrong}\" → \"{right}\"")
        else:
            print("  No corrections.")
        if d.hotwords:
            print(f"  Hotwords: {', '.join(d.hotwords)}")
        else:
            print("  No hotwords.")
    elif action == "remove" and len(sys.argv) >= 4:
        key = sys.argv[3].lower()
        if key in d.corrections:
            d.corrections.pop(key)
            d._save()
            print(f"[Dictionary] Removed: {key}")
        else:
            print(f"[Dictionary] Not found: {key}")
    else:
        print(dict_cmd.__doc__)


def history_cmd():
    if len(sys.argv) < 3:
        action = "list"
    else:
        action = sys.argv[2]
    if action == "list":
        for r in _history.list_recent():
            ts = r['timestamp'][:19].replace('T', ' ')
            print(f"  [{r['id']}] {ts} ({r['duration_s']:.1f}s, {r['word_count']}w) {r['cleaned_text'][:80]}")
    elif action == "search" and len(sys.argv) >= 4:
        for r in _history.search(" ".join(sys.argv[3:])):
            print(f"  [{r['id']}] {r['cleaned_text'][:100]}")
    elif action == "stats":
        s = _history.stats()
        print(f"  {s['total']} transcriptions, {s['words']} words, {s['minutes']} minutes")
    else:
        print("Usage: --history [list|search <query>|stats]")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        cmds = {
            "--test-mic": test_mic,
            "--test-paste": test_paste,
            "--test-transcribe": test_transcribe,
            "--test-cleanup": test_cleanup,
            "--dict": dict_cmd,
            "--history": history_cmd,
            "--help": lambda: print(__doc__),
        }
        if cmd in cmds:
            cmds[cmd]()
        else:
            print(f"Unknown: {cmd}\nUsage: whisper_flow.py [--test-mic | --test-paste | --test-transcribe | --test-cleanup]")
            sys.exit(1)
    else:
        run_menubar_app()


if __name__ == "__main__":
    main()
