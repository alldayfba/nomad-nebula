#!/usr/bin/env python3
"""
SalesCopilot — Real-Time AI Sales Call Assistant

Listens to live sales calls, transcribes both sides in real-time, and provides
AI-powered response suggestions using your sales training library (NEPQ, battle
cards, Hormozi closes, Johnny Mau pre-frame psychology, 5 Tones).

Usage:
  python execution/sales_copilot.py              # Run as menubar app
  python execution/sales_copilot.py --test       # Test all components
  python execution/sales_copilot.py --devices    # List audio devices
  python execution/sales_copilot.py --test-ai    # Test AI only (no audio)

Setup:
  1. For Zoom calls: just run — ZoomAudioDevice is auto-detected
  2. For other calls: brew install blackhole-2ch
     Then create Multi-Output Device in Audio MIDI Setup
  3. Grant Microphone permission in System Settings

Hotkeys:
  Cmd+Shift+S — Toggle overlay visibility
  Cmd+Shift+R — Force request suggestions
  Cmd+Shift+N — New call (reset transcript)

Controls:
  Menubar icon → Start Listening / Stop / Quit
"""

from __future__ import annotations

import os
import sys
import time
import threading
import queue as queue_mod
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "execution"))
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from sales_copilot_audio import DualAudioCapture, list_devices
from sales_copilot_pipeline import TranscriptionPipeline
from sales_copilot_corpus import SalesCorpus
from sales_copilot_ai import AIEngine
from sales_copilot_overlay import CopilotOverlay


# ─── Configuration ───────────────────────────────────────────────────────────

CHECK_TRIGGER_INTERVAL = 2.0  # How often to check if we should fire suggestions


# ─── Main App ────────────────────────────────────────────────────────────────

class SalesCopilotApp:
    """Main orchestrator: menubar app + audio + pipeline + AI + overlay."""

    def __init__(self):
        self.capture = None
        self.pipeline = None
        self.corpus = SalesCorpus()
        self.ai_engine = None
        self.overlay = CopilotOverlay()
        self.main_queue = queue_mod.Queue()
        self._listening = False
        self._trigger_thread = None

    def run(self):
        """Run as a rumps menubar app."""
        import rumps

        # Load corpus
        self.corpus.load()

        # Create AI engine
        self.ai_engine = AIEngine(self.corpus)
        self.ai_engine.on_stage_change = self._on_stage_change
        self.ai_engine.on_suggestions = self._on_suggestions
        self.ai_engine.on_suggestion_chunk = self._on_suggestion_chunk
        self.ai_engine.on_objection = self._on_objection

        app = self

        class CopilotMenuApp(rumps.App):
            def __init__(self_menu):
                super().__init__(
                    "SalesCopilot",
                    icon=None,
                    quit_button=None,
                    menu=[
                        rumps.MenuItem("Start Listening", callback=self_menu._toggle),
                        rumps.MenuItem("Force Suggest (⌘⇧R)", callback=self_menu._force_suggest),
                        rumps.MenuItem("New Call (⌘⇧N)", callback=self_menu._new_call),
                        None,  # separator
                        rumps.MenuItem("Show/Hide (⌘⇧S)", callback=self_menu._toggle_overlay),
                        None,
                        rumps.MenuItem("Quit", callback=self_menu._quit),
                    ],
                )
                # Create overlay on main thread
                app.overlay.create_panel()

                # Process main queue on timer
                rumps.Timer(self_menu._process_queue, 0.1).start()

            def _toggle(self_menu, sender):
                if app._listening:
                    app.stop_listening()
                    sender.title = "Start Listening"
                else:
                    app.start_listening()
                    sender.title = "Stop Listening"

            def _force_suggest(self_menu, _):
                app.force_suggestions()

            def _new_call(self_menu, _):
                app.new_call()

            def _toggle_overlay(self_menu, _):
                app.overlay.toggle()

            def _quit(self_menu, _):
                app.stop_listening()
                rumps.quit_application()

            def _process_queue(self_menu, _):
                app._process_main_queue()

        menu_app = CopilotMenuApp()
        print("[SalesCopilot] Ready. Click menubar icon to start.")
        menu_app.run()

    def start_listening(self):
        """Start audio capture + transcription."""
        if self._listening:
            return

        print("[SalesCopilot] Starting...")

        # Pipeline (receives audio, produces transcript)
        self.pipeline = TranscriptionPipeline(on_transcript=self._on_transcript)

        # Audio capture (feeds pipeline)
        self.capture = DualAudioCapture(on_audio=self.pipeline.feed_audio)

        # Start everything
        self.capture.start()
        self.pipeline.start()

        # Show overlay
        self.main_queue.put(("show", None))

        # Start trigger checker
        self._listening = True
        self._trigger_thread = threading.Thread(target=self._trigger_loop, daemon=True)
        self._trigger_thread.start()

        print("[SalesCopilot] Listening. Speak into your mic or join a call.")

    def stop_listening(self):
        """Stop audio capture + transcription."""
        if not self._listening:
            return

        self._listening = False

        if self.capture:
            self.capture.stop()
        if self.pipeline:
            self.pipeline.stop()

        self.main_queue.put(("hide", None))
        print("[SalesCopilot] Stopped.")

    def new_call(self):
        """Reset for a new call."""
        was_listening = self._listening
        if was_listening:
            self.stop_listening()

        # Clear overlay
        self.overlay.transcript_lines.clear()
        self.overlay.suggestions_text = ""
        self.overlay.alert_text = ""

        if was_listening:
            self.start_listening()

        print("[SalesCopilot] New call — transcript cleared.")

    def force_suggestions(self):
        """Force-trigger AI suggestions."""
        if not self.pipeline or not self.ai_engine:
            return

        transcript_text = self.pipeline.get_full_text(last_n=20)
        last_prospect = self.pipeline.get_last_prospect_text(last_n=5)

        if transcript_text.strip():
            self.overlay.clear_suggestions()
            self.ai_engine.force_suggest(transcript_text, last_prospect)

    # ─── Callbacks ───────────────────────────────────────────────────────

    def _on_transcript(self, speaker: str, text: str, timestamp: float):
        """Called when a new transcript line is produced."""
        self.main_queue.put(("transcript", (speaker, text)))

        # Console output
        label = "YOU" if speaker == "sabbo" else "THEM"
        print(f"  [{label}] {text}")

    def _on_stage_change(self, stage: str):
        """Called when the call stage changes."""
        from sales_copilot_corpus import NEPQ_STAGES
        info = NEPQ_STAGES.get(stage, {})
        self.main_queue.put(("stage", (
            info.get("name", stage),
            info.get("number", 0),
            info.get("tip", ""),
        )))

    def _on_suggestions(self, text: str):
        """Called when suggestions are fully generated."""
        # Already streamed via chunks, just log
        pass

    def _on_suggestion_chunk(self, chunk: str):
        """Called for each streaming chunk of suggestions."""
        self.main_queue.put(("suggest_chunk", chunk))

    def _on_objection(self, category: str):
        """Called when an objection is detected."""
        display = category.replace("_", " ").title()
        self.main_queue.put(("alert", f"OBJECTION: {display}"))

    # ─── Trigger Loop ────────────────────────────────────────────────────

    def _trigger_loop(self):
        """Background loop: check if we should fire AI suggestions."""
        while self._listening:
            try:
                if not self.pipeline or not self.ai_engine:
                    time.sleep(CHECK_TRIGGER_INTERVAL)
                    continue

                transcript_text = self.pipeline.get_full_text(last_n=20)
                last_prospect = self.pipeline.get_last_prospect_text(last_n=5)
                prospect_silence = self.pipeline.prospect_silence_seconds

                reason = self.ai_engine.should_trigger(
                    prospect_silence=prospect_silence,
                    last_prospect_text=last_prospect,
                    transcript_text=transcript_text,
                )

                if reason:
                    self.main_queue.put(("clear_suggest", None))
                    self.ai_engine.trigger_suggestions(
                        transcript_text=transcript_text,
                        last_prospect_text=last_prospect,
                        reason=reason,
                    )

            except Exception as e:
                print(f"[SalesCopilot] Trigger error: {e}")

            time.sleep(CHECK_TRIGGER_INTERVAL)

    # ─── Main Queue Processing ───────────────────────────────────────────

    def _process_main_queue(self):
        """Process pending UI actions. Called from main thread via rumps.Timer."""
        try:
            while True:
                action, data = self.main_queue.get_nowait()

                if action == "show":
                    self.overlay.show()
                elif action == "hide":
                    self.overlay.hide()
                elif action == "transcript":
                    speaker, text = data
                    self.overlay.add_transcript_line(speaker, text)
                elif action == "stage":
                    name, number, tip = data
                    self.overlay.update_stage(name, number, tip)
                elif action == "suggest_chunk":
                    self.overlay.append_suggestion_chunk(data)
                elif action == "clear_suggest":
                    self.overlay.clear_suggestions()
                elif action == "alert":
                    self.overlay.show_alert(data, duration=8.0)

        except queue_mod.Empty:
            pass


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if "--devices" in args:
        list_devices()
        return

    if "--test-ai" in args:
        from sales_copilot_ai import test_ai
        test_ai()
        return

    if "--test-corpus" in args:
        from sales_copilot_corpus import test_corpus
        test_corpus()
        return

    if "--test-audio" in args:
        from sales_copilot_audio import test_audio
        test_audio()
        return

    if "--test-pipeline" in args:
        from sales_copilot_pipeline import test_pipeline
        test_pipeline()
        return

    if "--test-overlay" in args:
        from sales_copilot_overlay import test_overlay
        test_overlay()
        return

    if "--test" in args:
        print("=== SalesCopilot Full Test Suite ===\n")
        print("Run individual tests:")
        print("  --test-audio     Test audio capture (mic + system)")
        print("  --test-pipeline  Test real-time transcription (30s)")
        print("  --test-corpus    Test sales corpus loading")
        print("  --test-ai        Test AI suggestion generation")
        print("  --test-overlay   Test overlay UI (15s)")
        print("  --devices        List audio devices")
        print()
        print("Or just run: python execution/sales_copilot.py")
        print("  → Menubar app starts, click to begin listening")
        return

    # Default: run the app
    app = SalesCopilotApp()
    app.run()


if __name__ == "__main__":
    main()
