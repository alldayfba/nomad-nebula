#!/usr/bin/env python3
"""
SalesCopilot — Overlay UI

Transparent, always-on-top NSPanel overlay showing:
  - Stage indicator (top bar)
  - Live transcript (scrolling, speaker-labeled)
  - AI suggestions (numbered cards with tonality tags)
  - Objection alert banner

Built on WhisperFlow's proven NSPanel + PyObjC pattern.
All ObjC classes at module level (never nested — avoids SIGTRAP).

Usage:
  python execution/sales_copilot_overlay.py --test
"""

from __future__ import annotations

import sys
import time
import threading
from collections import deque
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── Module-level ObjC class (MUST be at module level, never nested) ────────

_overlay_ref = None  # Global reference for ObjC callbacks


def _create_copilot_view_class():
    """Create the CopilotView NSView subclass at module level."""
    from AppKit import NSView

    class CopilotView(NSView):
        def drawRect_(self, rect):
            if _overlay_ref is not None:
                _overlay_ref._draw(rect)

        def mouseDown_(self, event):
            if _overlay_ref is not None:
                loc = self.convertPoint_fromView_(event.locationInWindow(), None)
                _overlay_ref._handle_click(loc.x, loc.y)

        def acceptsFirstResponder(self):
            return False

    return CopilotView


_CopilotViewClass = None


def _get_copilot_view_class():
    global _CopilotViewClass
    if _CopilotViewClass is None:
        _CopilotViewClass = _create_copilot_view_class()
    return _CopilotViewClass


# ─── Overlay ─────────────────────────────────────────────────────────────────

class CopilotOverlay:
    """Transparent floating panel with live transcript, suggestions, and stage indicator."""

    WIDTH = 420
    HEIGHT = 600
    MARGIN = 12
    HEADER_HEIGHT = 40
    TRANSCRIPT_HEIGHT = 200
    ALERT_HEIGHT = 30

    def __init__(self):
        self.panel = None
        self.view = None
        self._lock = threading.Lock()

        # State
        self.stage_name = "Connecting"
        self.stage_number = 1
        self.stage_tip = "Build rapport. Get micro-commitment."
        self.elapsed = "0:00"

        self.transcript_lines: deque = deque(maxlen=15)
        self.suggestions_text = ""
        self.alert_text = ""
        self.alert_until = 0.0

        self._visible = False
        self._start_time = time.time()

    def create_panel(self):
        """Create the NSPanel. MUST run on main thread."""
        from AppKit import (
            NSPanel, NSColor, NSScreen,
            NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
        )
        from Foundation import NSMakeRect

        screen = NSScreen.mainScreen()
        sf = screen.frame()
        x = sf.size.width - self.WIDTH - 20  # 20px from right edge
        y = sf.size.height - self.HEIGHT - 80  # 80px from top

        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, self.WIDTH, self.HEIGHT),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(101)
        panel.setCollectionBehavior_(
            1 << 0 |  # canJoinAllSpaces
            1 << 4 |  # fullScreenAuxiliary
            1 << 7    # stationary
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setAlphaValue_(0.92)
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)  # Click-through by default
        panel.setFloatingPanel_(True)
        panel.setWorksWhenModal_(True)
        panel.setHidesOnDeactivate_(False)

        global _overlay_ref
        _overlay_ref = self

        CopilotView = _get_copilot_view_class()
        view = CopilotView.alloc().initWithFrame_(NSMakeRect(0, 0, self.WIDTH, self.HEIGHT))
        panel.setContentView_(view)

        self.panel = panel
        self.view = view

    def show(self):
        """Show the overlay."""
        if self.panel:
            self.panel.orderFront_(None)
            self._visible = True
            self._start_time = time.time()

    def hide(self):
        """Hide the overlay."""
        if self.panel:
            self.panel.orderOut_(None)
            self._visible = False

    def toggle(self):
        """Toggle visibility."""
        if self._visible:
            self.hide()
        else:
            self.show()

    def set_interactive(self, interactive: bool):
        """Toggle click-through mode."""
        if self.panel:
            self.panel.setIgnoresMouseEvents_(not interactive)

    def update_stage(self, name: str, number: int, tip: str):
        """Update the stage indicator."""
        with self._lock:
            self.stage_name = name
            self.stage_number = number
            self.stage_tip = tip
        self._redraw()

    def add_transcript_line(self, speaker: str, text: str):
        """Add a line to the scrolling transcript."""
        label = "YOU" if speaker == "sabbo" else "THEM"
        with self._lock:
            self.transcript_lines.append((label, text))
        self._redraw()

    def set_suggestions(self, text: str):
        """Set the suggestions text (replaces previous)."""
        with self._lock:
            self.suggestions_text = text
        self._redraw()

    def append_suggestion_chunk(self, chunk: str):
        """Append streaming chunk to suggestions."""
        with self._lock:
            self.suggestions_text += chunk
        self._redraw()

    def clear_suggestions(self):
        """Clear the suggestions area."""
        with self._lock:
            self.suggestions_text = ""
        self._redraw()

    def show_alert(self, text: str, duration: float = 5.0):
        """Show an alert banner for N seconds."""
        with self._lock:
            self.alert_text = text
            self.alert_until = time.time() + duration
        self._redraw()

    def update_elapsed(self):
        """Update the elapsed time display."""
        elapsed = int(time.time() - self._start_time)
        minutes = elapsed // 60
        seconds = elapsed % 60
        self.elapsed = f"{minutes}:{seconds:02d}"

    def _redraw(self):
        """Schedule a redraw on the main thread."""
        if self.view:
            try:
                self.view.setNeedsDisplay_(True)
            except Exception:
                pass

    def _handle_click(self, x: float, y: float):
        """Handle click events (for future interactive mode)."""
        pass

    def _draw(self, rect):
        """Draw the overlay content. Called from CopilotView.drawRect_."""
        from AppKit import NSColor, NSBezierPath, NSFont, NSAttributedString
        from AppKit import NSFontAttributeName, NSForegroundColorAttributeName
        from AppKit import NSParagraphStyleAttributeName, NSMutableParagraphStyle
        from Foundation import NSMakeRect, NSDictionary

        w = self.WIDTH
        h = self.HEIGHT
        m = self.MARGIN

        # ── Background: dark rounded rectangle ──
        bg_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.06, 0.06, 0.10, 0.93)
        bg_color.setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(0, 0, w, h), 12, 12
        ).fill()

        # ── Helper: draw text ──
        def draw_text(text, x, y, size=12, r=1.0, g=1.0, b=1.0, alpha=1.0, bold=False, max_width=None):
            if not text:
                return 0
            font_name = "Menlo-Bold" if bold else "Menlo"
            font = NSFont.fontWithName_size_(font_name, size)
            if font is None:
                font = NSFont.systemFontOfSize_(size)

            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, alpha)

            para = NSMutableParagraphStyle.alloc().init()
            para.setLineBreakMode_(0)  # wrap by word

            attrs = NSDictionary.dictionaryWithObjects_forKeys_(
                [font, color, para],
                [NSFontAttributeName, NSForegroundColorAttributeName, NSParagraphStyleAttributeName],
            )
            ns_str = NSAttributedString.alloc().initWithString_attributes_(str(text), attrs)

            draw_w = max_width or (w - x - m)
            draw_rect = NSMakeRect(x, y, draw_w, 400)
            ns_str.drawInRect_(draw_rect)

            # Approximate line count for height calculation
            char_per_line = max(1, int(draw_w / (size * 0.6)))
            lines = max(1, len(text) // char_per_line + 1)
            return int(lines * (size + 4))

        # ── Coordinate system: draw from top down ──
        # NSView coords are bottom-up, so we start from h and work down
        y_cursor = h - m

        # ── Header: Stage + Elapsed ──
        y_cursor -= 16
        draw_text(
            f"STAGE {self.stage_number}/9: {self.stage_name.upper()}",
            m, y_cursor, size=11, r=0.4, g=0.8, b=1.0, bold=True,
        )

        self.update_elapsed()
        draw_text(
            self.elapsed,
            w - 60, y_cursor, size=11, r=0.6, g=0.6, b=0.6,
        )

        # Coaching tip
        y_cursor -= 16
        draw_text(
            self.stage_tip[:80],
            m, y_cursor, size=9, r=0.5, g=0.5, b=0.5, alpha=0.8,
        )

        # Divider
        y_cursor -= 10
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.2, 0.3, 0.5).setFill()
        NSBezierPath.fillRect_(NSMakeRect(m, y_cursor, w - 2 * m, 1))

        # ── Transcript Section ──
        y_cursor -= 14
        draw_text(
            "TRANSCRIPT",
            m, y_cursor, size=9, r=0.4, g=0.4, b=0.5, bold=True,
        )
        y_cursor -= 4

        with self._lock:
            lines = list(self.transcript_lines)

        for label, text in lines[-8:]:  # Show last 8 lines
            y_cursor -= 14
            if y_cursor < self.ALERT_HEIGHT + 200:
                break

            if label == "YOU":
                lr, lg, lb = 0.3, 0.8, 0.4  # Green for Sabbo
            else:
                lr, lg, lb = 0.9, 0.6, 0.2  # Orange for prospect

            draw_text(f"[{label}]", m, y_cursor, size=9, r=lr, g=lg, b=lb, bold=True)

            # Truncate long text
            display_text = text[:100] + "..." if len(text) > 100 else text
            y_cursor -= 12
            draw_text(display_text, m + 4, y_cursor, size=9, r=0.8, g=0.8, b=0.8)

        # Divider
        y_cursor -= 10
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.2, 0.3, 0.5).setFill()
        NSBezierPath.fillRect_(NSMakeRect(m, y_cursor, w - 2 * m, 1))

        # ── Suggestions Section ──
        y_cursor -= 14
        draw_text(
            "SUGGESTIONS",
            m, y_cursor, size=9, r=0.4, g=0.4, b=0.5, bold=True,
        )
        y_cursor -= 4

        with self._lock:
            suggestions = self.suggestions_text

        if suggestions:
            # Draw suggestions text with word wrapping
            suggestion_lines = suggestions.split('\n')
            for line in suggestion_lines:
                if not line.strip():
                    y_cursor -= 6
                    continue
                if y_cursor < self.ALERT_HEIGHT + 20:
                    break

                # Color-code: numbered suggestions in white, frameworks in cyan, tones in yellow
                y_cursor -= 14
                if line.strip().startswith(('1.', '2.', '3.')):
                    draw_text(line.strip(), m + 4, y_cursor, size=10, r=0.95, g=0.95, b=0.95)
                elif '[' in line and ']' in line:
                    draw_text(line.strip(), m + 8, y_cursor, size=9, r=1.0, g=0.9, b=0.4)
                else:
                    draw_text(line.strip(), m + 8, y_cursor, size=9, r=0.7, g=0.7, b=0.75)
        else:
            y_cursor -= 14
            draw_text(
                "Listening... suggestions appear when prospect speaks.",
                m + 4, y_cursor, size=9, r=0.4, g=0.4, b=0.4, alpha=0.6,
            )

        # ── Alert Banner (bottom) ──
        with self._lock:
            alert = self.alert_text if time.time() < self.alert_until else ""

        if alert:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.8, 0.3, 0.1, 0.9).setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(m, 4, w - 2 * m, self.ALERT_HEIGHT), 6, 6
            ).fill()
            draw_text(
                f"⚠ {alert}",
                m + 8, 10, size=10, r=1.0, g=1.0, b=1.0, bold=True,
            )


# ─── Test Mode ───────────────────────────────────────────────────────────────

def test_overlay():
    """Test the overlay with sample data."""
    print("\n=== SalesCopilot Overlay Test ===")
    print("The overlay will appear on screen for 15 seconds.\n")

    import rumps

    overlay = CopilotOverlay()

    class TestApp(rumps.App):
        def __init__(self):
            super().__init__("SC Test", quit_button=None)
            overlay.create_panel()
            overlay.show()

            # Populate with sample data
            overlay.update_stage("Problem Awareness", 3, "Ask: 'How's that going honestly?'")

            overlay.add_transcript_line("sabbo", "Hey, what made you reach out today?")
            overlay.add_transcript_line("prospect", "I've been trying to start Amazon FBA for 6 months but I'm stuck.")
            overlay.add_transcript_line("sabbo", "Got it. What have you tried so far?")
            overlay.add_transcript_line("prospect", "I bought a course last year but it was just pre-recorded videos. I spent $2K and never made a sale. I've been burned before honestly.")

            overlay.set_suggestions(
                "1. [Concerned] \"That's frustrating — spending $2K and getting nothing back. What do you think was the main reason it didn't work out?\" (NEPQ Stage 3 - Gap ID)\n\n"
                "2. [Curious] \"Walk me through what happened. You bought the course, then what? Where did it break down?\" (Pre-Frame: Revealing Question setup)\n\n"
                "3. [Challenging] \"So you've been wanting this for 6 months and you're still in the same spot. What's that costing you?\" (Consequence Framing)"
            )

            overlay.show_alert("OBJECTION: Been burned before (trust issue)", duration=10)

            # Auto-quit after 15 seconds
            rumps.Timer(lambda _: rumps.quit_application(), 15).start()

    app = TestApp()
    app.run()


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_overlay()
    else:
        print("Usage: python execution/sales_copilot_overlay.py --test")
