#!/usr/bin/env python3
"""
SalesCopilot — Dual Audio Capture Module

Captures two audio streams simultaneously:
  1. Microphone (what Sabbo says)
  2. System/Zoom audio (what the prospect says)

Supports:
  - ZoomAudioDevice (auto-detected when Zoom is running)
  - LoomAudioDevice (auto-detected when Loom is running)
  - BlackHole virtual driver (manual setup fallback)
  - Any input device by name or index

Usage:
  python execution/sales_copilot_audio.py --test
"""

from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd

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

# Device name preferences for system audio (tried in order)
SYSTEM_AUDIO_DEVICES = [
    "ZoomAudioDevice",
    "LoomAudioDevice",
    "BlackHole 2ch",
    "BlackHole",
]

# Environment overrides
MIC_DEVICE = os.getenv("COPILOT_MIC_DEVICE", None)  # None = system default
SYSTEM_DEVICE = os.getenv("COPILOT_SYSTEM_DEVICE", None)  # None = auto-detect


# ─── Device Discovery ────────────────────────────────────────────────────────

def find_device(name_pattern: str, kind: str = "input") -> dict | None:
    """Find an audio device by name pattern. Returns device info or None."""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if name_pattern.lower() in dev["name"].lower():
            ch_key = "max_input_channels" if kind == "input" else "max_output_channels"
            if dev[ch_key] > 0:
                return {"index": i, **dev}
    return None


def find_system_audio_device() -> dict | None:
    """Auto-detect the best system audio capture device."""
    if SYSTEM_DEVICE:
        dev = find_device(SYSTEM_DEVICE)
        if dev:
            return dev

    for name in SYSTEM_AUDIO_DEVICES:
        dev = find_device(name)
        if dev:
            return dev
    return None


def find_mic_device() -> dict | None:
    """Find the microphone device."""
    if MIC_DEVICE:
        return find_device(MIC_DEVICE)
    # Default input device
    dev_info = sd.query_devices(kind="input")
    idx = sd.default.device[0]
    return {"index": idx, **dev_info}


def list_devices():
    """Print all audio devices with input/output channel counts."""
    devices = sd.query_devices()
    print("Available audio devices:")
    for i, dev in enumerate(devices):
        inp = dev["max_input_channels"]
        out = dev["max_output_channels"]
        marker = ""
        for name in SYSTEM_AUDIO_DEVICES:
            if name.lower() in dev["name"].lower() and inp > 0:
                marker = " <-- SYSTEM AUDIO"
                break
        print(f"  {i}: {dev['name']} (in={inp}, out={out}){marker}")


# ─── Audio Stream ────────────────────────────────────────────────────────────

class AudioStream:
    """Captures audio from a single device, feeding chunks to a callback."""

    def __init__(self, device_info: dict, label: str, on_audio):
        """
        Args:
            device_info: dict with 'index', 'name', 'max_input_channels', etc.
            label: "mic" or "system" for logging
            on_audio: callback(label, np.ndarray) called with each audio chunk
        """
        self.device_info = device_info
        self.label = label
        self.on_audio = on_audio
        self.stream = None
        self._native_rate = None
        self.running = False
        self.rms = 0.0

    def start(self):
        """Open the audio stream and start capturing."""
        dev = self.device_info
        idx = dev["index"]
        native_rate = int(dev["default_samplerate"])
        max_ch = dev["max_input_channels"]

        # Try configs in order: target rate mono, native rate mono, native stereo
        configs = [
            (SAMPLE_RATE, 1),
            (native_rate, 1),
            (native_rate, min(max_ch, 2)),
        ]

        for rate, ch in configs:
            try:
                self.stream = sd.InputStream(
                    device=idx,
                    samplerate=rate,
                    channels=ch,
                    dtype=DTYPE,
                    callback=self._callback,
                )
                self._native_rate = rate
                self.stream.start()
                self.running = True
                print(f"[SalesCopilot] {self.label}: {dev['name']} @ {rate}Hz/{ch}ch")
                return
            except Exception as e:
                print(f"[SalesCopilot] {self.label}: {rate}Hz/{ch}ch failed: {e}")
                continue

        raise RuntimeError(f"Could not open {self.label} device: {dev['name']}")

    def stop(self):
        """Stop and close the audio stream."""
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _callback(self, indata, frames, time_info, status):
        """Audio callback — downsample to 16kHz mono, forward to pipeline."""
        if status:
            pass  # Suppress warnings during normal operation

        data = indata.copy()

        # Convert stereo to mono
        if data.shape[1] > 1:
            data = data.mean(axis=1, keepdims=True)

        # Downsample to 16kHz if captured at native rate
        if self._native_rate and self._native_rate != SAMPLE_RATE:
            ratio = int(round(self._native_rate / SAMPLE_RATE))
            if ratio > 1:
                data = data[::ratio]

        # Track RMS for amplitude display
        self.rms = float(np.sqrt(np.mean(data ** 2)))

        # Forward to pipeline
        self.on_audio(self.label, data)


# ─── Dual Audio Capture ─────────────────────────────────────────────────────

class DualAudioCapture:
    """Manages simultaneous mic + system audio capture."""

    def __init__(self, on_audio):
        """
        Args:
            on_audio: callback(label, np.ndarray) — label is "mic" or "system"
        """
        self.on_audio = on_audio
        self.mic_stream = None
        self.system_stream = None
        self.has_system_audio = False

    def start(self):
        """Start both audio streams."""
        # Mic
        mic_dev = find_mic_device()
        if mic_dev:
            self.mic_stream = AudioStream(mic_dev, "mic", self.on_audio)
            self.mic_stream.start()
        else:
            print("[SalesCopilot] WARNING: No microphone found!")

        # System audio
        sys_dev = find_system_audio_device()
        if sys_dev:
            self.system_stream = AudioStream(sys_dev, "system", self.on_audio)
            try:
                self.system_stream.start()
                self.has_system_audio = True
            except RuntimeError as e:
                print(f"[SalesCopilot] System audio unavailable: {e}")
                print("[SalesCopilot] Running mic-only mode (your voice only)")
                self.system_stream = None
        else:
            print("[SalesCopilot] No system audio device found.")
            print("[SalesCopilot] Install BlackHole (brew install blackhole-2ch) or use Zoom/Loom.")
            print("[SalesCopilot] Running mic-only mode.")

    def stop(self):
        """Stop all audio streams."""
        if self.mic_stream:
            self.mic_stream.stop()
        if self.system_stream:
            self.system_stream.stop()

    def get_rms(self) -> dict:
        """Get current RMS levels for both streams."""
        return {
            "mic": self.mic_stream.rms if self.mic_stream else 0.0,
            "system": self.system_stream.rms if self.system_stream else 0.0,
        }


# ─── Test Mode ───────────────────────────────────────────────────────────────

def test_audio():
    """Test audio capture from both streams for 10 seconds."""
    print("\n=== SalesCopilot Audio Test ===\n")
    list_devices()

    chunk_count = {"mic": 0, "system": 0}
    last_rms = {"mic": 0.0, "system": 0.0}

    def on_audio(label, data):
        chunk_count[label] += 1
        last_rms[label] = float(np.sqrt(np.mean(data ** 2)))

    capture = DualAudioCapture(on_audio)
    print("\nStarting capture... speak into your mic and play audio.")
    print("Press Ctrl+C to stop.\n")

    capture.start()

    try:
        for i in range(20):
            time.sleep(0.5)
            mic_bar = "█" * int(last_rms["mic"] * 500)
            sys_bar = "█" * int(last_rms["system"] * 500)
            print(f"  Mic [{chunk_count['mic']:4d}]: {mic_bar:40s} | System [{chunk_count['system']:4d}]: {sys_bar:40s}", end="\r")
    except KeyboardInterrupt:
        pass

    capture.stop()
    print(f"\n\nResults: mic={chunk_count['mic']} chunks, system={chunk_count['system']} chunks")
    print("Audio capture " + ("WORKING" if chunk_count["mic"] > 0 else "FAILED"))


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_audio()
    else:
        list_devices()
