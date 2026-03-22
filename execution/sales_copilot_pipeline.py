#!/usr/bin/env python3
"""
SalesCopilot — Real-Time Transcription Pipeline

Ring buffer + chunked faster-whisper transcription with speaker labels.
Processes dual audio streams (mic=Sabbo, system=Prospect) into a live transcript.

Usage:
  python execution/sales_copilot_pipeline.py --test
"""

from __future__ import annotations

import os
import sys
import re
import time
import wave
import threading
import tempfile
from pathlib import Path
from collections import deque

import numpy as np

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

WHISPER_MODEL = os.getenv("COPILOT_WHISPER_MODEL", "small")
WHISPER_COMPUTE_TYPE = os.getenv("COPILOT_COMPUTE_TYPE", "int8")

CHUNK_SECONDS = float(os.getenv("COPILOT_CHUNK_SECONDS", "4.0"))
OVERLAP_SECONDS = float(os.getenv("COPILOT_OVERLAP_SECONDS", "1.0"))
PROCESS_INTERVAL = float(os.getenv("COPILOT_PROCESS_INTERVAL", "2.5"))
SILENCE_RMS_THRESHOLD = float(os.getenv("COPILOT_SILENCE_THRESHOLD", "0.005"))
MIN_TRANSCRIPT_WORDS = 2  # Ignore chunks with fewer words

TMP_DIR = PROJECT_ROOT / ".tmp" / "copilot"
TMP_DIR.mkdir(parents=True, exist_ok=True)


# ─── Filler Cleanup ─────────────────────────────────────────────────────────

FILLER_PATTERNS = [
    re.compile(r'\b(um+|uh+m?|er+m?|ah+|eh+|hm+|hmm+)\b', re.IGNORECASE),
    re.compile(r'\b(you know,?\s*|I mean,?\s*|like,?\s+(?=you know|basically|literally))', re.IGNORECASE),
    re.compile(r'\s*\.\.\.\s*'),
]


def clean_transcript(text: str) -> str:
    """Remove filler words, fix punctuation, capitalize."""
    for pattern in FILLER_PATTERNS:
        text = pattern.sub(' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+([,.\?!;:])', r'\1', text)
    text = re.sub(r'(^|[.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
    return text.strip()


# ─── Ring Buffer ─────────────────────────────────────────────────────────────

class RingBuffer:
    """Fixed-duration audio ring buffer with overlap extraction."""

    def __init__(self, seconds: float, sample_rate: int = SAMPLE_RATE):
        self.max_samples = int(seconds * sample_rate)
        self.buffer = np.zeros((self.max_samples, 1), dtype=np.float32)
        self.write_pos = 0
        self.total_written = 0
        self._lock = threading.Lock()

    def append(self, data: np.ndarray):
        """Append audio data to the ring buffer."""
        with self._lock:
            n = len(data)
            if data.ndim == 1:
                data = data.reshape(-1, 1)

            if n >= self.max_samples:
                self.buffer[:] = data[-self.max_samples:]
                self.write_pos = 0
                self.total_written += n
                return

            end = self.write_pos + n
            if end <= self.max_samples:
                self.buffer[self.write_pos:end] = data
            else:
                first = self.max_samples - self.write_pos
                self.buffer[self.write_pos:] = data[:first]
                self.buffer[:n - first] = data[first:]

            self.write_pos = end % self.max_samples
            self.total_written += n

    def get_window(self, seconds: float = None) -> np.ndarray:
        """Get the most recent N seconds of audio."""
        with self._lock:
            if seconds is None:
                n = min(self.total_written, self.max_samples)
            else:
                n = min(int(seconds * SAMPLE_RATE), self.max_samples, self.total_written)

            if n == 0:
                return np.zeros((0, 1), dtype=np.float32)

            start = (self.write_pos - n) % self.max_samples
            if start < self.write_pos:
                return self.buffer[start:self.write_pos].copy()
            else:
                return np.concatenate([
                    self.buffer[start:],
                    self.buffer[:self.write_pos]
                ]).copy()

    def has_speech(self, seconds: float = None) -> bool:
        """Check if the buffer has speech above the silence threshold."""
        audio = self.get_window(seconds)
        if len(audio) == 0:
            return False
        rms = float(np.sqrt(np.mean(audio ** 2)))
        return rms > SILENCE_RMS_THRESHOLD


# ─── Transcription Pipeline ─────────────────────────────────────────────────

class TranscriptionPipeline:
    """Processes dual audio streams into a diarized, real-time transcript."""

    def __init__(self, on_transcript=None):
        """
        Args:
            on_transcript: callback(speaker: str, text: str, timestamp: float)
                speaker is "sabbo" or "prospect"
        """
        self.on_transcript = on_transcript or (lambda s, t, ts: None)
        self.model = None
        self._model_lock = threading.Lock()

        # Ring buffers for each stream
        self.mic_buffer = RingBuffer(seconds=CHUNK_SECONDS + OVERLAP_SECONDS)
        self.sys_buffer = RingBuffer(seconds=CHUNK_SECONDS + OVERLAP_SECONDS)

        # Dedup: last few words from each stream to avoid overlap repeats
        self._last_mic_words = []
        self._last_sys_words = []

        # Full transcript log
        self.transcript: list[dict] = []  # [{speaker, text, timestamp}, ...]
        self._transcript_lock = threading.Lock()

        # Processing thread
        self._running = False
        self._thread = None

        # Counters
        self._chunks_processed = 0
        self._last_mic_speech = 0.0
        self._last_sys_speech = 0.0

    def load_model(self):
        """Load the faster-whisper model (lazy, thread-safe)."""
        with self._model_lock:
            if self.model is not None:
                return
            print(f"[SalesCopilot] Loading Whisper model '{WHISPER_MODEL}' ({WHISPER_COMPUTE_TYPE})...")
            from faster_whisper import WhisperModel
            self.model = WhisperModel(WHISPER_MODEL, compute_type=WHISPER_COMPUTE_TYPE)
            print("[SalesCopilot] Whisper model loaded.")

    def feed_audio(self, label: str, data: np.ndarray):
        """Feed audio from the audio capture module."""
        if label == "mic":
            self.mic_buffer.append(data)
        elif label == "system":
            self.sys_buffer.append(data)

    def start(self):
        """Start the background transcription loop."""
        if self._running:
            return
        self.load_model()
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the transcription loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def get_transcript(self, last_n: int = 20) -> list[dict]:
        """Get the last N transcript entries."""
        with self._transcript_lock:
            return list(self.transcript[-last_n:])

    def get_last_prospect_text(self, last_n: int = 5) -> str:
        """Get the last N prospect utterances concatenated."""
        with self._transcript_lock:
            prospect_lines = [
                e["text"] for e in self.transcript
                if e["speaker"] == "prospect"
            ]
            return " ".join(prospect_lines[-last_n:])

    def get_full_text(self, last_n: int = 20) -> str:
        """Get formatted transcript text for AI context."""
        entries = self.get_transcript(last_n)
        lines = []
        for e in entries:
            label = "Sabbo" if e["speaker"] == "sabbo" else "Prospect"
            lines.append(f"[{label}] {e['text']}")
        return "\n".join(lines)

    def _process_loop(self):
        """Background loop: transcribe buffers every PROCESS_INTERVAL seconds."""
        while self._running:
            try:
                self._process_cycle()
            except Exception as e:
                print(f"[SalesCopilot] Pipeline error: {e}")
            time.sleep(PROCESS_INTERVAL)

    def _process_cycle(self):
        """One processing cycle: check both buffers, transcribe if speech present."""
        now = time.time()

        # Process mic audio (Sabbo)
        if self.mic_buffer.has_speech(CHUNK_SECONDS):
            audio = self.mic_buffer.get_window(CHUNK_SECONDS)
            text = self._transcribe(audio)
            text = self._dedup(text, self._last_mic_words)
            if text and len(text.split()) >= MIN_TRANSCRIPT_WORDS:
                self._last_mic_words = text.split()[-5:]
                self._emit("sabbo", text, now)
                self._last_mic_speech = now

        # Process system audio (Prospect)
        if self.sys_buffer.has_speech(CHUNK_SECONDS):
            audio = self.sys_buffer.get_window(CHUNK_SECONDS)
            text = self._transcribe(audio)
            text = self._dedup(text, self._last_sys_words)
            if text and len(text.split()) >= MIN_TRANSCRIPT_WORDS:
                self._last_sys_words = text.split()[-5:]
                self._emit("prospect", text, now)
                self._last_sys_speech = now

        self._chunks_processed += 1

    def _transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a numpy audio array using faster-whisper."""
        if self.model is None:
            return ""

        # Save to temp wav
        audio_flat = audio.flatten()
        audio_int16 = (audio_flat * 32767).astype(np.int16)

        tmp_path = TMP_DIR / f"chunk_{threading.current_thread().ident}.wav"
        with wave.open(str(tmp_path), "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())

        try:
            segments, _ = self.model.transcribe(
                str(tmp_path),
                beam_size=5,
                vad_filter=True,
            )
            raw = " ".join(seg.text for seg in segments).strip()
            return clean_transcript(raw)
        except Exception as e:
            print(f"[SalesCopilot] Transcription error: {e}")
            return ""
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

    def _dedup(self, text: str, last_words: list) -> str:
        """Remove overlapping words from the start of text that match last_words."""
        if not text or not last_words:
            return text

        words = text.split()
        if len(words) == 0:
            return text

        # Find longest prefix match with last_words suffix
        max_overlap = min(len(words), len(last_words))
        best_overlap = 0

        for overlap_len in range(1, max_overlap + 1):
            suffix = last_words[-overlap_len:]
            prefix = words[:overlap_len]
            if [w.lower() for w in suffix] == [w.lower() for w in prefix]:
                best_overlap = overlap_len

        if best_overlap > 0:
            words = words[best_overlap:]

        return " ".join(words)

    def _emit(self, speaker: str, text: str, timestamp: float):
        """Emit a transcript entry."""
        entry = {"speaker": speaker, "text": text, "timestamp": timestamp}
        with self._transcript_lock:
            self.transcript.append(entry)
        self.on_transcript(speaker, text, timestamp)

    @property
    def prospect_silence_seconds(self) -> float:
        """Seconds since the prospect last spoke."""
        if self._last_sys_speech == 0:
            return float("inf")
        return time.time() - self._last_sys_speech

    @property
    def sabbo_silence_seconds(self) -> float:
        """Seconds since Sabbo last spoke."""
        if self._last_mic_speech == 0:
            return float("inf")
        return time.time() - self._last_mic_speech


# ─── Test Mode ───────────────────────────────────────────────────────────────

def test_pipeline():
    """Test the transcription pipeline with mic audio for 30 seconds."""
    print("\n=== SalesCopilot Pipeline Test ===")
    print("Speak into your mic for 30 seconds. Transcript will appear below.\n")

    from sales_copilot_audio import DualAudioCapture

    def on_transcript(speaker, text, timestamp):
        label = "YOU" if speaker == "sabbo" else "THEM"
        print(f"  [{label}] {text}")

    pipeline = TranscriptionPipeline(on_transcript=on_transcript)

    capture = DualAudioCapture(on_audio=pipeline.feed_audio)
    capture.start()
    pipeline.start()

    try:
        for _ in range(60):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    pipeline.stop()
    capture.stop()
    print(f"\nProcessed {pipeline._chunks_processed} cycles, {len(pipeline.transcript)} entries.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_pipeline()
    else:
        print("Usage: python execution/sales_copilot_pipeline.py --test")
