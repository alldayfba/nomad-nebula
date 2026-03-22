# SalesCopilot — Real-Time AI Sales Call Assistant
> Directive | Version 1.0 | 2026-03-21

## What It Does

Listens to live sales calls (Zoom, Google Meet, phone), transcribes both sides in real-time, detects objections and call stages, and displays AI-powered response suggestions in a transparent overlay on screen.

## Setup (One-Time)

### For Zoom Calls
No setup needed — ZoomAudioDevice is auto-detected.

### For Other Calls (Google Meet, Phone)
```bash
brew install blackhole-2ch
```
Then: System Settings → Sound → Create Multi-Output Device (speakers + BlackHole).

### Permissions
- System Settings → Privacy → Microphone → Terminal (or your IDE)
- System Settings → Privacy → Screen Recording (if using ScreenCaptureKit later)

## Usage

```bash
source .venv/bin/activate
python execution/sales_copilot.py
```

Menubar icon appears → click "Start Listening" → join your call.

### Hotkeys
| Key | Action |
|---|---|
| Cmd+Shift+S | Toggle overlay visibility |
| Cmd+Shift+R | Force request suggestions |
| Cmd+Shift+N | New call (reset transcript) |

### Testing Individual Components
```bash
python execution/sales_copilot.py --devices        # List audio devices
python execution/sales_copilot.py --test-audio      # Test mic + system audio
python execution/sales_copilot.py --test-pipeline   # Test transcription (30s)
python execution/sales_copilot.py --test-corpus     # Test corpus loading
python execution/sales_copilot.py --test-ai         # Test AI suggestions
python execution/sales_copilot.py --test-overlay    # Test overlay UI (15s)
```

## Architecture

```
sales_copilot.py          ← Main app (menubar, orchestrator)
sales_copilot_audio.py    ← Dual audio capture (mic + system)
sales_copilot_pipeline.py ← Ring buffer + faster-whisper transcription
sales_copilot_corpus.py   ← Sales training corpus loader (tiered prompts)
sales_copilot_ai.py       ← Claude API (stage detection + suggestions)
sales_copilot_overlay.py  ← NSPanel overlay UI
```

## How It Works

1. **Audio:** Captures mic (Sabbo) + system audio (prospect) as separate streams
2. **Transcription:** 4-second chunks with 1-second overlap → faster-whisper → dedup → speaker-labeled transcript
3. **Detection:** Checks for objection keywords, question marks, prospect silence, stage transitions
4. **AI:** Sends transcript + NEPQ stage + relevant battle card to Claude Sonnet → streams 2-3 suggestions
5. **Display:** Transparent overlay shows: stage indicator, scrolling transcript, suggestion cards, objection alerts

## Configuration (.env)

```
COPILOT_WHISPER_MODEL=small        # Whisper model (tiny/base/small/medium)
COPILOT_COMPUTE_TYPE=int8          # Compute type (int8/float16)
COPILOT_CHUNK_SECONDS=4.0          # Audio chunk size
COPILOT_PROCESS_INTERVAL=2.5       # Transcription cycle interval
COPILOT_SILENCE_TRIGGER=3.0        # Seconds of prospect silence before triggering
COPILOT_MIN_SUGGEST_INTERVAL=8.0   # Min seconds between suggestion requests
COPILOT_OFFER=amazon               # Offer mode (amazon/agency)
COPILOT_MIC_DEVICE=                # Override mic device name
COPILOT_SYSTEM_DEVICE=             # Override system audio device name
```

## Training Corpus

Powered by 42+ files of sales training:
- NEPQ 9-stage framework (Jeremy Miner)
- Pre-Frame Psychology (Johnny Mau)
- 28 Rules of Closing + 7 All-Purpose Closes (Alex Hormozi)
- 5 Tones (JP Egan)
- 21 Agency OS battle cards
- Amazon OS battle cards
- Full closer and setter scripts

## Troubleshooting

| Issue | Fix |
|---|---|
| No system audio | Check `--devices` output. Install BlackHole or verify ZoomAudioDevice exists. |
| Transcription too slow | Lower model: `COPILOT_WHISPER_MODEL=base` or `tiny` |
| Suggestions too frequent | Increase `COPILOT_MIN_SUGGEST_INTERVAL` |
| Overlay blocks content | Move Zoom window to the left; overlay is on the right edge |
| No suggestions appearing | Check ANTHROPIC_API_KEY in .env. Run `--test-ai` to verify. |
