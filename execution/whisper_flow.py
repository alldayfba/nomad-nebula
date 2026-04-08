#!/usr/bin/env python3
"""
WhisperFlow — Local voice-to-text dictation for macOS.

Free, local, private. Records from your mic, transcribes with faster-whisper,
cleans up filler words, pastes into the active text field. Runs as a menubar app.

Quick Start:
  pip install sounddevice numpy faster-whisper rumps pynput pyobjc-framework-Quartz
  python execution/whisper_flow.py              # Run as menubar app
  python execution/whisper_flow.py --install    # Auto-start at login
  python execution/whisper_flow.py --uninstall  # Remove auto-start

Controls:
  Tap Left Option (⌥)          — Start/stop recording (instant)
  Double-tap Left Option (⌥)   — Locked recording mode (hands-free)
  Long-press Left Option (>1s) — Pause/resume recording
  Click stop button on overlay — Stop recording
  Hold middle mouse button 2s  — Toggle recording (alternative)

Other commands:
  --test-mic          Test microphone capture
  --test-paste        Test paste mechanism
  --dict list         Show dictionary entries
  --dict reset        Reset corrupted dictionary
  --dict add X Y      Add correction X → Y
  --history list      Show transcription history

macOS Permissions (grant to Terminal.app):
  System Settings > Privacy & Security > Accessibility
  System Settings > Privacy & Security > Input Monitoring
  System Settings > Privacy & Security > Microphone
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

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny.en")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_CPU_THREADS = int(os.getenv("WHISPER_CPU_THREADS", str(os.cpu_count() or 4)))
WHISPER_MOUSE_HOLD_SECONDS = float(os.getenv("WHISPER_MOUSE_HOLD_SECONDS", "2.0"))
WHISPER_CLEANUP_MODE = os.getenv("WHISPER_CLEANUP_MODE", "regex")  # regex | api | none
WHISPER_HOTKEY_TAP_TIMEOUT = float(os.getenv("WHISPER_HOTKEY_TAP_TIMEOUT", "0.4"))
WHISPER_DOUBLE_TAP_WINDOW = float(os.getenv("WHISPER_DOUBLE_TAP_WINDOW", "0.6"))
WHISPER_PAUSE_HOLD_THRESHOLD = float(os.getenv("WHISPER_PAUSE_HOLD_THRESHOLD", "1.0"))
WHISPER_RESTORE_CLIPBOARD = os.getenv("WHISPER_RESTORE_CLIPBOARD", "true").lower() == "true"
WHISPER_VAD_FILTER = os.getenv("WHISPER_VAD_FILTER", "true").lower() == "true"
WHISPER_PREROLL_SECONDS = float(os.getenv("WHISPER_PREROLL_SECONDS", "0.75"))

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

    # Common English words that should NEVER be auto-correction sources or targets
    PROTECTED_WORDS = frozenset({
        "i", "a", "an", "the", "it", "is", "in", "to", "do", "we", "he",
        "me", "be", "so", "no", "go", "if", "or", "on", "at", "my", "of",
        "up", "as", "by", "am", "us", "and", "but", "for", "not", "you",
        "all", "can", "had", "her", "was", "one", "our", "out", "are",
        "has", "his", "how", "its", "may", "new", "now", "old", "see",
        "way", "who", "did", "get", "let", "say", "she", "too", "use",
        "bro", "dude", "like", "just", "that", "this", "with", "have",
        "from", "they", "been", "said", "each", "what", "then", "them",
        "will", "when", "make", "time", "very", "your", "here", "know",
        "sell", "self", "cloud", "more", "some", "also", "than", "into",
        "over", "such", "take", "year", "come", "could", "good", "most",
        "need", "does", "back", "work", "only", "well", "about", "would",
    })

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

    def add_correction(self, wrong: str, right: str, auto_learned: bool = False) -> str:
        """Add a spelling correction. Returns notification message.

        auto_learned=True applies stricter validation to prevent garbage entries.
        """
        key = wrong.lower()

        if auto_learned:
            if len(key) < 3 or len(right) < 3:
                return f"Skipped (too short): \"{wrong}\" → \"{right}\""
            if key in self.PROTECTED_WORDS or right.lower() in self.PROTECTED_WORDS:
                return f"Skipped (common word): \"{wrong}\" → \"{right}\""
            if not key.isalpha() or not right.replace("'", "").isalpha():
                return f"Skipped (not alphabetic): \"{wrong}\" → \"{right}\""

        self.corrections[key] = right
        if right not in self.hotwords:
            self.hotwords.append(right)
        self._save()
        return f"Dictionary updated: \"{wrong}\" → \"{right}\""

    def add_hotword(self, word: str):
        """Add a word Whisper should recognize (proper noun, brand, etc.)."""
        if word not in self.hotwords:
            self.hotwords.append(word)
            self._save()

    def reset(self, keep_entries: dict[str, str] | None = None):
        """Delete dictionary and recreate with only known-good entries."""
        self.corrections = keep_entries or {}
        self.hotwords = list(keep_entries.values()) if keep_entries else []
        self._save()

    def apply(self, text: str) -> str:
        """Apply all corrections to transcribed text."""
        for wrong, right in self.corrections.items():
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

    WATCH_SECONDS = 10.0     # how long to monitor after paste
    IDLE_TIMEOUT = 1.5       # seconds of no typing = finalize pending correction
    MIN_WORD_LEN = 3         # ignore fragments shorter than this
    BACKSPACE_KEYCODE = 51
    SPACE_KEYCODE = 49
    ARROW_KEYCODES = {123, 124, 125, 126}   # left, right, down, up
    RETURN_KEYCODES = {36, 76}              # return, numpad enter

    FREQUENCY_THRESHOLD = 3  # must see same correction N times before learning

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
        self._pending_corrections: dict[str, dict] = {}  # key → {"right": str, "count": int}

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

        # Guard: both words must be real words (not fragments)
        if (wrong and right
                and wrong.lower() != right.lower()
                and len(wrong) >= self.MIN_WORD_LEN
                and len(right) >= self.MIN_WORD_LEN
                and wrong.lower() not in WhisperDictionary.PROTECTED_WORDS
                and right.lower() not in WhisperDictionary.PROTECTED_WORDS
                and wrong.isalpha() and right.isalpha()):

            # Frequency gate: must see same correction multiple times before learning
            key = wrong.lower()
            if key in self._pending_corrections and self._pending_corrections[key]["right"] == right:
                self._pending_corrections[key]["count"] += 1
            else:
                self._pending_corrections[key] = {"right": right, "count": 1}

            count = self._pending_corrections[key]["count"]
            if count >= self.FREQUENCY_THRESHOLD:
                msg = self.dictionary.add_correction(key, right, auto_learned=True)
                del self._pending_corrections[key]
                if msg.startswith("Skipped"):
                    print(f"[WhisperFlow] {msg}")
                    return
                print(f"[WhisperFlow] Auto-learned (confirmed {count}x): {msg}")
                try:
                    subprocess.Popen([
                        "osascript", "-e",
                        f'display notification "{msg}" with title "WhisperFlow Dictionary"'
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
                if self.overlay:
                    self.overlay._pending_notification = msg
            else:
                print(f"[WhisperFlow] Pending correction: {wrong} → {right} ({count}/{self.FREQUENCY_THRESHOLD})")

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


# ─── Self-Healing Health Monitor ─────────────────────────────────────────────

class HealthMonitor:
    """Runs every 30s. Detects failures, auto-fixes what it can, alerts the rest.

    Auto-heals:
      - Ring buffer died → restart it
      - CGEventTap disabled by macOS → re-enable
      - Stuck in TRANSCRIBING > 60s → force reset to IDLE
      - Model not loaded after 30s → retry load
      - Mic stream producing silence → restart ring buffer
      - Dictionary JSON corrupted → backup + reset
    """

    CHECK_INTERVAL = 30.0  # seconds between health checks
    TRANSCRIBE_TIMEOUT = 60.0  # max seconds in TRANSCRIBING state
    SILENCE_STREAK_LIMIT = 3  # consecutive silent checks before restart
    MODEL_LOAD_TIMEOUT = 30.0  # seconds to wait before retrying model load

    def __init__(self):
        self.engine = None
        self.app = None
        self._silence_streak = 0
        self._model_retry_count = 0
        self._last_successful_transcription = time.time()
        self._heals_performed: list[tuple[float, str]] = []  # (timestamp, action)
        self._state_entered_at: float = time.time()

    def attach(self, engine, app=None):
        self.engine = engine
        self.app = app
        # Hook into state changes to track timing
        original_set_state = engine._set_state
        def tracked_set_state(new_state):
            self._state_entered_at = time.time()
            if new_state == State.IDLE and engine.state == State.TYPING:
                self._last_successful_transcription = time.time()
            original_set_state(new_state)
        engine._set_state = tracked_set_state

    def check(self):
        """Run all health checks. Called from rumps Timer on main thread."""
        if not self.engine:
            return
        try:
            self._check_stuck_state()
            self._check_ring_buffer()
            self._check_mic_silence()
            self._check_mic_switch()
            self._check_model()
            self._check_event_tap()
            self._check_dictionary()
        except Exception as e:
            print(f"[HealthMonitor] Check error: {e}", flush=True)

    def _heal(self, action: str):
        """Log a self-healing action."""
        self._heals_performed.append((time.time(), action))
        print(f"[HealthMonitor] HEALED: {action}", flush=True)
        # Keep last 50 actions
        if len(self._heals_performed) > 50:
            self._heals_performed = self._heals_performed[-50:]

    def _notify(self, msg: str):
        """Show macOS notification for issues that need user attention."""
        try:
            subprocess.Popen(
                ["osascript", "-e",
                 f'display notification "{msg}" with title "WhisperFlow"'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    # ── Individual checks ──

    def _check_stuck_state(self):
        """Force-reset if stuck in TRANSCRIBING or TYPING too long."""
        e = self.engine
        elapsed = time.time() - self._state_entered_at
        if e.state == State.TRANSCRIBING and elapsed > self.TRANSCRIBE_TIMEOUT:
            self._heal(f"Force-reset from TRANSCRIBING (stuck {elapsed:.0f}s)")
            e.main_queue.put("hide")
            e._recording_active = False
            e._set_state(State.IDLE)
            self._notify("Recording was stuck — auto-reset. Try again.")
        elif e.state == State.TYPING and elapsed > 15.0:
            self._heal(f"Force-reset from TYPING (stuck {elapsed:.0f}s)")
            e.main_queue.put("hide")
            e._set_state(State.IDLE)

    def _check_ring_buffer(self):
        """Restart ring buffer if it died — even during recording.

        The ring buffer stream IS the recording stream. If it dies mid-recording,
        audio capture stops (peak=0). Must restart immediately.
        """
        e = self.engine
        if e.state in (State.TRANSCRIBING, State.TYPING):
            return  # don't touch during transcription
        # Respect exponential backoff on repeated failures
        if e._ring_restart_failures > 0:
            backoff = min(2 ** e._ring_restart_failures, 60.0)
            if backoff > self.CHECK_INTERVAL:
                return
        with e._stream_lock:
            if e.state in (State.TRANSCRIBING, State.TYPING):
                return
            if e._ring_stream is None:
                self._heal("Ring buffer was dead — restarting")
                e.start_ring_buffer()
            elif not e._ring_stream.active:
                self._heal("Ring buffer stream stopped — restarting")
                try:
                    e._ring_stream.close()
                except Exception:
                    pass
                e._ring_stream = None
                e.start_ring_buffer()

    def _check_mic_silence(self):
        """Detect if mic is producing silence (permission revoked, device changed)."""
        e = self.engine
        if e.state != State.IDLE or e._ring_stream is None:
            return
        with e._ring_lock:
            if e._ring_buf:
                samples = np.concatenate(e._ring_buf, axis=0)
                peak = float(np.abs(samples).max())
            else:
                peak = 0.0
        if peak < 0.0001:
            self._silence_streak += 1
            if self._silence_streak >= self.SILENCE_STREAK_LIMIT:
                self._heal(f"Mic silent {self._silence_streak} checks — restarting ring buffer")
                self._silence_streak = 0
                with e._stream_lock:
                    try:
                        e._ring_stream.stop()
                        e._ring_stream.close()
                    except Exception:
                        pass
                    e._ring_stream = None
                    e.start_ring_buffer()
                self._notify("Mic was silent — restarted. Check mic input device.")
        else:
            self._silence_streak = 0

    def _check_mic_switch(self):
        """Detect if user switched their default mic and follow it automatically."""
        e = self.engine
        if e.state != State.IDLE:
            return  # don't switch mid-recording
        new_default = e._detect_active_mic()
        if new_default is None:
            return
        try:
            new_name = sd.query_devices(new_default)['name']
        except Exception:
            return
        if e._current_device_name and new_name != e._current_device_name:
            # Don't switch to a ghost-blacklisted device
            if new_name in e._ghost_devices and time.time() < e._ghost_devices[new_name]:
                return
            # Verify USB connection before switching to non-built-in device
            name_lower = new_name.lower()
            is_builtin = any(k in name_lower for k in ('built-in', 'macbook', 'internal'))
            if not is_builtin and not e._is_usb_device_connected(new_name):
                print(f"[HealthMonitor] Default mic {new_name} not on USB bus — ignoring switch")
                e._ghost_devices[new_name] = time.time() + 60
                return
            self._heal(f"Mic switched: {e._current_device_name} → {new_name}")
            with e._stream_lock:
                if e._ring_stream:
                    try:
                        e._ring_stream.close()
                    except Exception:
                        pass
                    e._ring_stream = None
                e.start_ring_buffer()

    def _check_model(self):
        """Retry model loading if it failed."""
        e = self.engine
        if e.model is None and self._model_retry_count < 3:
            elapsed = time.time() - self._state_entered_at
            if elapsed > self.MODEL_LOAD_TIMEOUT:
                self._model_retry_count += 1
                self._heal(f"Model not loaded — retry #{self._model_retry_count}")
                def retry():
                    try:
                        e.load_model()
                        if self.app:
                            self.app.title = ICON_IDLE
                        self._notify("Model loaded successfully.")
                    except Exception as ex:
                        print(f"[HealthMonitor] Model retry failed: {ex}", flush=True)
                threading.Thread(target=retry, daemon=True).start()

    def _check_event_tap(self):
        """Re-enable CGEventTap if macOS disabled it."""
        if not self.app or not hasattr(self.app, 'hotkey_listener'):
            return
        tap = self.app.hotkey_listener._tap
        if tap is not None:
            try:
                from Quartz import CGEventTapIsEnabled, CGEventTapEnable
                if not CGEventTapIsEnabled(tap):
                    CGEventTapEnable(tap, True)
                    self._heal("CGEventTap was disabled — re-enabled")
            except Exception:
                pass
        elif tap is None:
            # Tap never created (permissions issue) — retry up to 3 times, then stop spamming
            if not hasattr(self, '_tap_retries'):
                self._tap_retries = 0
            if self._tap_retries >= 3:
                return  # stop retrying, user needs to fix permissions
            self._tap_retries += 1
            self._heal(f"CGEventTap was never created — retry #{self._tap_retries}/3")
            result = self.app.hotkey_listener.start()
            if result is None and self._tap_retries >= 3:
                self._notify("Hotkey not working. Grant Accessibility permission in System Settings.")

    def _check_dictionary(self):
        """Verify dictionary file is valid JSON."""
        if not DICTIONARY_PATH.exists():
            return
        try:
            with open(DICTIONARY_PATH) as f:
                json.load(f)
        except (json.JSONDecodeError, ValueError):
            backup = DICTIONARY_PATH.with_suffix('.json.bak')
            try:
                import shutil
                shutil.copy2(DICTIONARY_PATH, backup)
                DICTIONARY_PATH.unlink()
                _dictionary.corrections.clear()
                _dictionary.hotwords.clear()
                self._heal(f"Dictionary was corrupted — backed up to {backup.name}, reset")
                self._notify("Dictionary was corrupted and has been reset.")
            except Exception as ex:
                print(f"[HealthMonitor] Dictionary fix failed: {ex}", flush=True)

    def get_status(self) -> str:
        """Return human-readable health status."""
        lines = [f"State: {self.engine.state.value if self.engine else 'detached'}"]
        lines.append(f"Ring buffer: {'active' if self.engine and self.engine._ring_stream and self.engine._ring_stream.active else 'dead'}")
        lines.append(f"Model: {'loaded' if self.engine and self.engine.model else 'not loaded'}")
        lines.append(f"Silence streak: {self._silence_streak}")
        lines.append(f"Heals: {len(self._heals_performed)}")
        if self._heals_performed:
            last = self._heals_performed[-1]
            ago = time.time() - last[0]
            lines.append(f"Last heal: {last[1]} ({ago:.0f}s ago)")
        return "\n".join(lines)


# Global health monitor instance
_health_monitor = HealthMonitor()


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
        # Always-on ring buffer: captures audio continuously so recording
        # starts instantly with pre-roll (no first-word cutoff)
        self._ring_buf: list[np.ndarray] = []
        self._ring_lock = threading.Lock()
        self._ring_max_samples = int(SAMPLE_RATE * WHISPER_PREROLL_SECONDS)
        self._ring_stream: sd.InputStream | None = None
        self._recording_active = False  # True while actively recording
        self._stream_lock = threading.RLock()  # protects ALL stream open/close/restart
        self._current_device_name: str = ""    # track which mic is active
        self._ring_restart_failures: int = 0   # exponential backoff counter
        self._ghost_devices: dict[str, float] = {}  # name → blacklisted_until timestamp

    def start_ring_buffer(self):
        """Start the always-on mic stream. Call once at app startup.

        Audio flows continuously into a ring buffer. When recording starts,
        the last PREROLL_SECONDS are grabbed instantly — no mic-open delay,
        no first-word cutoff.
        """
        with self._stream_lock:
            try:
                self._ring_stream, self._native_rate = self._open_mic()
                self._ring_stream.start()
                self._ring_restart_failures = 0
                print(f"[WhisperFlow] Ring buffer active ({WHISPER_PREROLL_SECONDS}s pre-roll)")
            except Exception as e:
                self._ring_restart_failures += 1
                backoff = min(2 ** self._ring_restart_failures, 60.0)
                print(f"[WhisperFlow] Ring buffer failed (attempt {self._ring_restart_failures},"
                      f" backoff {backoff:.0f}s): {e}", flush=True)

    def load_model(self):
        from faster_whisper import WhisperModel
        print(f"[WhisperFlow] Loading model '{WHISPER_MODEL}' ({WHISPER_COMPUTE_TYPE})...")
        self.model = WhisperModel(
            WHISPER_MODEL, device="cpu", compute_type=WHISPER_COMPUTE_TYPE,
            cpu_threads=WHISPER_CPU_THREADS,
        )
        print("[WhisperFlow] Model loaded.")

    def _set_state(self, new_state: State):
        self.state = new_state
        self.on_state_change(new_state)

    def toggle_recording(self):
        """Toggle recording state."""
        with self.lock:
            self._toggle_recording_inner()

    def _toggle_recording_inner(self):
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
            if 'error' in str(status).lower():
                self.main_queue.put("restart_ring_buffer")
        if indata is None or len(indata) == 0:
            return
        data = indata.copy()  # copy early to avoid use-after-free on stream restart
        # Downsample to 16kHz mono if mic is at native rate
        if data.shape[1] > 1:
            data = data.mean(axis=1, keepdims=True)
        if self._native_rate and self._native_rate != SAMPLE_RATE:
            ratio = int(round(self._native_rate / SAMPLE_RATE))
            if ratio > 1:
                data = data[::ratio]
        chunk = data.copy()

        if self._recording_active:
            # Active recording — append to chunks
            self.audio_chunks.append(chunk)
            rms = float(np.sqrt(np.mean(indata ** 2)))
            peak = float(np.abs(indata).max())
            if peak > self._peak_amplitude:
                self._peak_amplitude = peak
            amp = min(1.0, (peak * 0.6 + rms * 0.4) * 25.0)
            self.overlay.update_amplitude(amp)
        else:
            # Idle — feed ring buffer (rolling window of last PREROLL_SECONDS)
            with self._ring_lock:
                self._ring_buf.append(chunk)
                # Trim to max size
                total = sum(c.shape[0] for c in self._ring_buf)
                while total > self._ring_max_samples and len(self._ring_buf) > 1:
                    total -= self._ring_buf[0].shape[0]
                    self._ring_buf.pop(0)

    def _start_recording(self):
        play_sound(SOUND_START)
        self._peak_amplitude = 0.0
        self.recording_start = time.time()
        # NOTE: do NOT reset toggle_locked here — it's set by double-tap
        self.main_queue.put("show")

        # Grab pre-roll audio from ring buffer (last ~0.75s before key press)
        with self._ring_lock:
            preroll = list(self._ring_buf)
            self._ring_buf.clear()
        self.audio_chunks = preroll

        if self._ring_stream is not None:
            # Ring buffer stream already running — just switch to recording mode
            self._recording_active = True
            self._set_state(State.RECORDING)
            preroll_ms = sum(c.shape[0] for c in preroll) / SAMPLE_RATE * 1000
            print(f"[WhisperFlow] Recording started (pre-roll: {preroll_ms:.0f}ms)")
        else:
            # Fallback: open mic on demand (ring buffer failed to start)
            with self._stream_lock:
                try:
                    self.stream, self._native_rate = self._open_mic()
                    self.stream.start()
                    self._recording_active = True
                    self._set_state(State.RECORDING)
                    print("[WhisperFlow] Recording started (no pre-roll, fallback mic).")
                except Exception as e:
                    print(f"[WhisperFlow] ERROR opening mic: {e}", flush=True)
                    self.main_queue.put("hide")
                    self._set_state(State.IDLE)

    def _detect_active_mic(self) -> int | None:
        """Return the device index of macOS's current default input device."""
        try:
            default = sd.query_devices(kind='input')
            if default and default['max_input_channels'] > 0:
                all_devs = sd.query_devices()
                for i in range(len(all_devs)):
                    if sd.query_devices(i)['name'] == default['name']:
                        return i
        except Exception:
            pass
        return None

    @staticmethod
    def _is_usb_device_connected(name: str) -> bool:
        """Check if a USB audio device is actually present on the USB bus.

        macOS caches audio devices even after USB disconnect. This checks
        ioreg to verify the device is physically connected, preventing
        ghost device loops (silence → fallback → switch back → silence).
        """
        try:
            result = subprocess.run(
                ['ioreg', '-p', 'IOUSB', '-w0'],
                capture_output=True, text=True, timeout=3,
            )
            # Match against the device name (case-insensitive)
            # USB audio devices register with their product name
            search_terms = name.lower().split()
            output_lower = result.stdout.lower()
            return any(term in output_lower for term in search_terms if len(term) > 3)
        except Exception:
            return True  # if ioreg fails, assume connected (don't block)

    def _open_mic(self):
        """Open mic stream at native rate, resample later. Falls back on error.

        Prefers the system default input device (follows user's Sound Settings).
        Falls back to priority scan (USB > built-in > virtual) if default fails.
        """
        # Only reinitialize PortAudio if no streams are open
        # (avoids destroying ring buffer mid-callback — the primary crash cause)
        if self._ring_stream is None and self.stream is None:
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass

        # Build candidate list: (device_index, info_dict)
        VIRTUAL_KEYWORDS = ('iphone', 'ipad', 'continuity', 'loom', 'zoom', 'virtual', 'aggregate', 'airpods', 'bluetooth', 'bt ', '🎧')
        raw_candidates = []
        seen_indices = set()

        try:
            all_devs = sd.query_devices()
            for i in range(len(all_devs)):
                info = sd.query_devices(i)
                if info['max_input_channels'] > 0 and i not in seen_indices:
                    raw_candidates.append((i, info))
                    seen_indices.add(i)
        except Exception:
            pass

        # Sort: system default first, then USB > built-in > virtual
        default_idx = self._detect_active_mic()

        def _mic_priority(item):
            idx, info = item
            name = info['name'].lower()
            if idx == default_idx:
                return -1  # system default — always try first
            if any(v in name for v in VIRTUAL_KEYWORDS):
                return 2  # virtual / phone — last resort
            if 'built-in' in name or 'macbook' in name or 'internal' in name:
                return 1  # built-in — good fallback
            return 0  # USB / external — preferred

        candidates = sorted(raw_candidates, key=_mic_priority)

        if not candidates:
            raise RuntimeError("No input audio devices found")

        for dev_idx, dev_info in candidates:
            name = dev_info['name']
            native_rate = int(dev_info['default_samplerate'])
            max_ch = dev_info['max_input_channels']

            # Skip ghost devices (blacklisted after repeated silence)
            blacklisted_until = self._ghost_devices.get(name, 0)
            if time.time() < blacklisted_until:
                print(f"[WhisperFlow] Mic: {name} — ghost-blacklisted for {blacklisted_until - time.time():.0f}s, skipping")
                continue

            # For non-built-in devices, verify USB connection before wasting time
            name_lower = name.lower()
            is_builtin = any(k in name_lower for k in ('built-in', 'macbook', 'internal'))
            if not is_builtin and not self._is_usb_device_connected(name):
                print(f"[WhisperFlow] Mic: {name} — NOT on USB bus (ghost device), skipping")
                self._ghost_devices[name] = time.time() + 60  # blacklist 60s
                continue

            configs = [
                (SAMPLE_RATE, 1),
                (native_rate, 1),
                (native_rate, min(max_ch, 2)),
            ]
            for rate, ch in configs:
                try:
                    print(f"[WhisperFlow] Mic: {name} — trying {rate}Hz/{ch}ch")
                    stream = sd.InputStream(
                        samplerate=rate, channels=ch, device=dev_idx,
                        dtype=DTYPE, callback=self._audio_callback,
                    )
                    stream.start()
                    time.sleep(0.3)
                    with self._ring_lock:
                        if self._ring_buf:
                            samples = np.concatenate(self._ring_buf, axis=0)
                            peak = float(np.abs(samples).max())
                        else:
                            peak = 0.0
                    stream.stop()
                    if peak < 0.0001:
                        print(f"[WhisperFlow] Mic {name} {rate}Hz/{ch}ch — silence (peak={peak:.6f}), skipping")
                        stream.close()
                        continue
                    # Device is alive — clear any ghost blacklist
                    self._ghost_devices.pop(name, None)
                    print(f"[WhisperFlow] Mic: {name} — verified at {rate}Hz/{ch}ch (peak={peak:.4f})")
                    self._current_device_name = name
                    return stream, rate
                except Exception as e:
                    print(f"[WhisperFlow] Mic config {name} {rate}Hz/{ch}ch failed: {e}")
                    continue

        raise RuntimeError("Could not open any microphone with any config")

    def _stop_recording(self):
        play_sound(SOUND_STOP)
        self.toggle_locked = False  # clear locked mode on explicit stop
        self._recording_active = False

        # Close fallback stream if used (ring buffer stream stays alive)
        with self._stream_lock:
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
        """Pause: stop capturing but keep accumulated chunks."""
        play_sound(SOUND_STOP)
        self._recording_active = False
        with self._stream_lock:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
        self.main_queue.put("pause")
        self._set_state(State.PAUSED)
        print("[WhisperFlow] Recording paused.")

    def _resume_recording(self):
        """Resume: switch back to recording mode (ring buffer stream still alive)."""
        play_sound(SOUND_START)
        self.main_queue.put("resume")
        if self._ring_stream is not None:
            self._recording_active = True
        else:
            with self._stream_lock:
                self.stream, self._native_rate = self._open_mic()
                self.stream.start()
                self._recording_active = True
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
                elif action == "restart_ring_buffer":
                    # Restart ring buffer even during recording — audio dies without it
                    with self._stream_lock:
                        if self._ring_stream:
                            try:
                                self._ring_stream.close()
                            except Exception:
                                pass
                            self._ring_stream = None
                        self.start_ring_buffer()
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
                self.overlay.show_notification("No speech detected", duration=2.0)
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
        prompt = hotwords + "The following is a clear, professional business dictation. Use standard English words."
        segments, _ = self.model.transcribe(
            audio_path,
            beam_size=1,
            best_of=1,
            vad_filter=WHISPER_VAD_FILTER,
            initial_prompt=prompt,
            language="en",
            condition_on_previous_text=False,
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
    """Paste text into active field via AppleScript keystroke Cmd+V."""
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
    time.sleep(0.05)

    # Paste via AppleScript (works without Accessibility permission)
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            timeout=3, capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[WhisperFlow] AppleScript paste error: {result.stderr.strip()}", flush=True)
        else:
            print("[WhisperFlow] Pasted via AppleScript", flush=True)
    except Exception as e:
        print(f"[WhisperFlow] Paste failed: {e}", flush=True)

    # Restore clipboard after a delay (enough for paste to complete)
    if saved_clipboard is not None:
        def restore():
            time.sleep(1.0)
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(saved_clipboard)
        threading.Thread(target=restore, daemon=True).start()


# ─── Input Listeners ────────────────────────────────────────────────────────

class CGEventTapHotkeyListener:
    """Listens for Left Option key gestures via CGEventTap (no pynput needed).

    Gestures:
      - Single tap (<0.4s press, release): toggle recording start/stop
      - Double-tap (two taps within 0.6s): toggle locked (persistent) recording mode
      - Long-press (hold >1s): pause/resume recording
    """

    LEFT_OPTION_KEYCODE = 58

    def __init__(self, engine: WhisperFlowEngine):
        self.engine = engine
        self._ropt_down_time: float = 0
        self._last_tap_time: float = 0     # time of last tap (for double-tap detection)
        self._other_key_pressed = False
        self._long_press_timer: threading.Timer | None = None
        self._tap = None  # CFMachPort reference

    def _on_long_press(self):
        """Held >1.0s — pause/resume."""
        self._ropt_down_time = 0  # prevent UP handler from also acting
        print("[WhisperFlow] LONG PRESS — pause/resume", flush=True)
        self.engine.pause_or_resume()

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
                    # Start long-press detection (only while recording/paused)
                    if self.engine.state in (State.RECORDING, State.PAUSED):
                        self._long_press_timer = threading.Timer(
                            WHISPER_PAUSE_HOLD_THRESHOLD, self._on_long_press)
                        self._long_press_timer.start()
                else:
                    # Key released
                    if self._long_press_timer:
                        self._long_press_timer.cancel()
                        self._long_press_timer = None
                    if self._ropt_down_time <= 0:
                        return event  # long-press already handled
                    held = time.time() - self._ropt_down_time
                    self._ropt_down_time = 0
                    if self._other_key_pressed:
                        return event  # modifier combo, ignore
                    if held >= WHISPER_PAUSE_HOLD_THRESHOLD:
                        return event  # long-press already handled by timer

                    # It's a tap — act INSTANTLY (no delay)
                    now = time.time()
                    is_double = (now - self._last_tap_time) < WHISPER_DOUBLE_TAP_WINDOW
                    self._last_tap_time = now

                    if is_double:
                        # Double-tap: if we just started recording, upgrade to locked
                        if self.engine.state == State.RECORDING:
                            self.engine.toggle_locked = True
                            print("[WhisperFlow] DOUBLE-TAP — locked mode ON", flush=True)
                        elif self.engine.state == State.IDLE:
                            # Edge case: double-tap while idle = start locked
                            self.engine.toggle_locked = True
                            self.engine.toggle_recording()
                            print("[WhisperFlow] DOUBLE-TAP — locked recording started", flush=True)
                    else:
                        # Single tap — toggle immediately
                        print(f"[WhisperFlow] TAP — toggle ({self.engine.state.value})", flush=True)
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
            "  Tap Left Option (⌥)        → start/stop recording\n"
            "  Double-tap Left Option      → locked (hands-free) mode\n"
            "  Long-press Left Option >1s  → pause/resume",
            flush=True,
        )
        return t


class NSEventHotkeyListener:
    """Listens for Left Option key via NSEvent global monitor.

    Unlike CGEventTap, this only needs Input Monitoring permission (not Accessibility).
    Must be started from the main thread (after NSApplication is running, e.g. in a rumps app).
    Same gesture logic as CGEventTapHotkeyListener: single-tap, double-tap, long-press.
    """

    LEFT_OPTION_KEYCODE = 58

    def __init__(self, engine: WhisperFlowEngine):
        self.engine = engine
        self._down_time: float = 0
        self._last_tap_time: float = 0
        self._other_key_pressed = False
        self._long_press_timer: threading.Timer | None = None
        self._monitor_flags = None
        self._monitor_keys = None

    def _on_long_press(self):
        self._down_time = 0
        print("[WhisperFlow] LONG PRESS — pause/resume", flush=True)
        self.engine.pause_or_resume()

    def start(self):
        from AppKit import NSEvent, NSFlagsChangedMask, NSKeyDownMask

        def on_flags_changed(event):
            keycode = event.keyCode()
            if keycode != self.LEFT_OPTION_KEYCODE:
                return
            is_down = bool(event.modifierFlags() & (1 << 19))

            if is_down:
                self._down_time = time.time()
                self._other_key_pressed = False
                if self.engine.state in (State.RECORDING, State.PAUSED):
                    self._long_press_timer = threading.Timer(
                        WHISPER_PAUSE_HOLD_THRESHOLD, self._on_long_press)
                    self._long_press_timer.start()
            else:
                if self._long_press_timer:
                    self._long_press_timer.cancel()
                    self._long_press_timer = None
                if self._down_time <= 0:
                    return
                held = time.time() - self._down_time
                self._down_time = 0
                if self._other_key_pressed:
                    return
                if held >= WHISPER_PAUSE_HOLD_THRESHOLD:
                    return

                # Instant tap — same logic as CGEventTap listener
                now = time.time()
                is_double = (now - self._last_tap_time) < WHISPER_DOUBLE_TAP_WINDOW
                self._last_tap_time = now

                if is_double:
                    if self.engine.state == State.RECORDING:
                        self.engine.toggle_locked = True
                        print("[WhisperFlow] DOUBLE-TAP — locked mode ON", flush=True)
                    elif self.engine.state == State.IDLE:
                        self.engine.toggle_locked = True
                        self.engine.toggle_recording()
                else:
                    self.engine.toggle_recording()

        def on_key_down(event):
            self._other_key_pressed = True

        self._monitor_flags = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSFlagsChangedMask, on_flags_changed
        )
        self._monitor_keys = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSKeyDownMask, on_key_down
        )
        if self._monitor_flags:
            print("[WhisperFlow] NSEvent hotkey active — Left Option (⌥) tap/double-tap/long-press")
            return True
        else:
            print("[WhisperFlow] NSEvent monitor failed — grant Input Monitoring permission")
            return None


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
    # Redirect stdout/stderr to log file if not already going to a file
    log_path = TMP_DIR / "whisper_flow.log"
    if not sys.stdout.isatty():
        # Already redirected by launchd — just ensure it exists
        pass
    else:
        try:
            log_file = open(log_path, "a", buffering=1)
            sys.stdout = log_file
            sys.stderr = log_file
        except Exception:
            pass
    print(f"[WhisperFlow] Starting...", flush=True)
    import rumps

    class WhisperFlowApp(rumps.App):
        def __init__(self):
            super().__init__("WhisperFlow", title=ICON_IDLE, quit_button="Quit")
            self.menu = [
                rumps.MenuItem("Toggle Recording (tap ⌥)", callback=self._toggle),
                rumps.MenuItem("Teach Correction...", callback=self._teach_correction),
                rumps.MenuItem("Show Dictionary", callback=self._show_dictionary),
                rumps.MenuItem("Health Check", callback=self._show_health),
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

            # Start always-on ring buffer immediately (so first recording has pre-roll)
            self.engine.start_ring_buffer()

            # Request mic permission + run audio self-test after run loop starts
            self._mic_perm_timer = rumps.Timer(self._request_mic_perm, 2.0)
            self._mic_perm_timer.start()
            self._selftest_timer = rumps.Timer(self._run_audio_selftest, 5.0)
            self._selftest_timer.start()

            # Start input listeners
            # If launched by Swift wrapper (WHISPERFLOW_HOTKEY_MODE=signal),
            # use signal-based hotkey (SIGUSR1=toggle, SIGUSR2=stop).
            # Otherwise, use CGEventTap (needs Accessibility permission).
            # Try hotkey methods in order: CGEventTap → NSEvent monitor → signal
            hotkey_mode = os.environ.get("WHISPERFLOW_HOTKEY_MODE", "cgeventtap")
            hotkey_ok = False

            # 1. CGEventTap (needs Accessibility permission)
            self.hotkey_listener = CGEventTapHotkeyListener(self.engine)
            if self.hotkey_listener.start() is not None:
                print("[WhisperFlow] Hotkey mode: CGEventTap")
                hotkey_ok = True

            # 2. NSEvent global monitor (needs Input Monitoring only)
            if not hotkey_ok:
                ns_listener = NSEventHotkeyListener(self.engine)
                if ns_listener.start() is not None:
                    hotkey_ok = True

            # 3. Signal from Swift launcher (fallback)
            if not hotkey_ok and hotkey_mode == "signal":
                self._setup_signal_hotkey()
                print("[WhisperFlow] Hotkey mode: signal (managed by Swift launcher)")
                hotkey_ok = True

            if not hotkey_ok:
                print("[WhisperFlow] WARNING: No hotkey — use menubar to toggle")

            # Poll the engine's main_queue on main thread (every 30ms)
            self._queue_timer = rumps.Timer(self._poll_queue, 0.03)
            self._queue_timer.start()

            # Self-healing health monitor (every 30s)
            _health_monitor.attach(self.engine, app=self)
            self._health_timer = rumps.Timer(self._health_check, HealthMonitor.CHECK_INTERVAL)
            self._health_timer.start()

            print("[WhisperFlow] Menubar app running. Tap Left Option (⌥) to record. Double-tap for locked mode. Long-press to pause.")

        def _setup_signal_hotkey(self):
            """Use SIGUSR1/SIGUSR2 from the Swift launcher instead of CGEventTap."""
            import signal as sig

            # Use a thread-safe queue — signal handlers can't safely call
            # toggle_recording() (it acquires locks). Instead, flag it and
            # let the existing main-thread queue timer process it.
            self._signal_queue = queue_mod.Queue()

            def _on_sigusr1(signum, frame):
                self._signal_queue.put("toggle")

            def _on_sigusr2(signum, frame):
                self._signal_queue.put("stop")

            sig.signal(sig.SIGUSR1, _on_sigusr1)
            sig.signal(sig.SIGUSR2, _on_sigusr2)

        def _request_mic_perm(self, _):
            self._mic_perm_timer.stop()
            threading.Thread(target=_request_mic_permission, daemon=True).start()

        def _run_audio_selftest(self, _):
            self._selftest_timer.stop()
            threading.Thread(target=self._audio_selftest, daemon=True).start()

        def _audio_selftest(self):
            """Check ring buffer for audio to verify mic captures (not silent)."""
            try:
                # Wait a moment for ring buffer to accumulate samples
                time.sleep(0.5)
                with self.engine._ring_lock:
                    if self.engine._ring_buf:
                        samples = np.concatenate(self.engine._ring_buf, axis=0)
                        peak = float(np.abs(samples).max())
                    else:
                        peak = 0.0
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

        def _health_check(self, _):
            """Run self-healing health check (every 30s)."""
            _health_monitor.check()

        def _show_health(self, sender):
            """Show health status in a dialog."""
            status = _health_monitor.get_status()
            try:
                subprocess.Popen(
                    ["osascript", "-e",
                     f'display dialog "{status}" with title "WhisperFlow Health" buttons {{"OK"}} default button "OK"'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

        def _poll_queue(self, _):
            """Process overlay show/hide + signal hotkey actions on main thread."""
            self.engine.process_main_queue()
            # Process signal-based hotkey events (SIGUSR1/SIGUSR2 from Swift launcher)
            if hasattr(self, '_signal_queue'):
                try:
                    while True:
                        action = self._signal_queue.get_nowait()
                        if action == "toggle":
                            print("[WhisperFlow] Signal: toggle recording", flush=True)
                            self.engine.toggle_recording()
                        elif action == "stop":
                            if self.engine.state == State.RECORDING:
                                print("[WhisperFlow] Signal: stop recording", flush=True)
                                self.engine.toggle_recording()
                except queue_mod.Empty:
                    pass
            # Process pending title updates from background threads
            if hasattr(self, '_title_queue'):
                try:
                    while True:
                        self.title = self._title_queue.get_nowait()
                except queue_mod.Empty:
                    pass

        def _set_title_safe(self, title):
            """Thread-safe title update — queues for main thread."""
            if not hasattr(self, '_title_queue'):
                self._title_queue = queue_mod.Queue()
            self._title_queue.put(title)

        def _load_model(self):
            self._set_title_safe("⏳ Loading...")
            try:
                self.engine.load_model()
                self._set_title_safe(ICON_IDLE)
            except Exception as e:
                self._set_title_safe("❌ ERR")
                rumps.notification("WhisperFlow Error", "Failed to load model", str(e))

        def _on_state_change(self, new_state: State):
            self._set_title_safe(STATE_ICONS.get(new_state, ICON_IDLE))

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
      --dict reset                  — Nuke dictionary, keep only known-good entries
      --dict show                   — Quick view of current state
    """
    if len(sys.argv) < 3:
        print("Usage: whisper_flow.py --dict [add|hotword|list|remove|reset|show] [args...]")
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
    elif action in ("list", "show"):
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
    elif action == "reset":
        known_good = {"savo": "Sabbo"}
        d.reset(known_good)
        print(f"[Dictionary] Reset with {len(known_good)} known-good entries:")
        for wrong, right in known_good.items():
            print(f"    \"{wrong}\" → \"{right}\"")
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


# ─── Install (auto-start at login) ──────────────────────────────────────────

def install_cmd():
    """Install WhisperFlow to auto-start at login via launchd + Terminal.app.

    Creates:
      ~/Library/LaunchAgents/com.sabbo.whisper-flow.plist
    Requires:
      Terminal.app must have Accessibility + Input Monitoring permissions
      (System Settings > Privacy & Security > Accessibility / Input Monitoring)
    """
    import plistlib

    launch_script = PROJECT_ROOT / "execution" / "launch_whisperflow.sh"
    if not launch_script.exists():
        print(f"[Install] ERROR: {launch_script} not found")
        sys.exit(1)

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "com.sabbo.whisper-flow.plist"

    plist_data = {
        "Label": "com.sabbo.whisper-flow",
        "ProgramArguments": [
            "/usr/bin/open", "-a", "Terminal",
            str(launch_script),
        ],
        "RunAtLoad": True,
        "KeepAlive": False,
        "LimitLoadToSessionType": "Aqua",
    }

    # Unload existing if present
    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True,
    )

    with open(plist_path, "wb") as f:
        plistlib.dump(plist_data, f)

    # Load the new agent
    result = subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        print(f"[Install] Installed: {plist_path}")
        print(f"[Install] WhisperFlow will auto-start at login via Terminal.app")
        print(f"[Install] Make sure Terminal.app has these permissions:")
        print(f"  System Settings > Privacy & Security > Accessibility > Terminal ✓")
        print(f"  System Settings > Privacy & Security > Input Monitoring > Terminal ✓")
        print(f"  System Settings > Privacy & Security > Microphone > Terminal ✓")
    else:
        print(f"[Install] WARNING: launchctl load failed: {result.stderr.strip()}")
        print(f"[Install] Plist written to {plist_path} — try loading manually")


def uninstall_cmd():
    """Remove WhisperFlow auto-start."""
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.sabbo.whisper-flow.plist"
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        plist_path.unlink()
        print(f"[Uninstall] Removed: {plist_path}")
    else:
        print("[Uninstall] Not installed.")
    # Kill running instance
    subprocess.run(["pkill", "-f", "python.*whisper_flow.py"], capture_output=True)
    print("[Uninstall] Stopped WhisperFlow.")


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
            "--install": install_cmd,
            "--uninstall": uninstall_cmd,
            "--help": lambda: print(__doc__),
        }
        if cmd in cmds:
            cmds[cmd]()
        else:
            print(f"Unknown: {cmd}")
            print("Usage: whisper_flow.py [--install | --uninstall | --test-mic | --test-paste | --dict | --history | --help]")
            sys.exit(1)
    else:
        run_menubar_app()


if __name__ == "__main__":
    main()
