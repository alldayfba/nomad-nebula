# WhisperFlow — SOP

## Purpose
Local voice-to-text dictation tool for macOS. Replaces paid WisprFlow ($15/mo) with a free, local Whisper-based alternative. Records from mic, transcribes with faster-whisper, cleans up filler words, pastes into the active text field.

## How It Works
1. Runs as a macOS menubar app (mic icon in menu bar)
2. Tap **Right Option (⌥)** to start recording — overlay appears with waveform
3. Speak into your mic — menubar shows 🔴 REC
4. Tap **Right Option (⌥)** again to stop
5. Audio transcribed locally by faster-whisper (~5s for 30s of speech)
6. Filler words removed, text cleaned up
7. Transcription pasted into whatever text field has focus
8. Original clipboard restored automatically

## Controls

| Action | Trigger |
|---|---|
| Start/stop recording | Single tap Right Option (⌥) |
| Locked mode (hands-free) | Double-tap Right Option within 600ms |
| Pause/resume recording | Long-press Right Option (>1 second) |
| Stop recording (mouse) | Click stop button on overlay pill |
| Toggle recording (mouse alt) | Hold middle mouse button 2+ seconds |

### Gesture Details
- **Single tap**: Press and release Right Option within 400ms with no other keys pressed. Toggles recording on/off.
- **Double-tap**: Two taps within 600ms. Enters locked mode — recording continues until the next single tap. Overlay shows 🔒 LOCKED.
- **Long-press**: Hold Right Option for 1+ second. Pauses recording (keeps accumulated audio). Tap again to resume. Overlay shows yellow PAUSED.
- **Stop button**: Click the red square icon on the right side of the overlay to stop recording.

## Menubar Indicators

| Icon | State |
|---|---|
| 🎤 | Idle — ready to record |
| 🔴 REC | Recording — mic is active |
| ⏸️ PAUSED | Paused — mic stopped, audio saved, tap to resume |
| ⏳ | Transcribing — processing audio |
| ✍️ | Typing — pasting text |

## Quick Start

```bash
cd ~/Documents/nomad-nebula
source .venv/bin/activate
python execution/whisper_flow.py
```

## Auto-Start (launchd)

```bash
# Load (starts on login)
launchctl load ~/Library/LaunchAgents/com.sabbo.whisper-flow.plist

# Unload
launchctl unload ~/Library/LaunchAgents/com.sabbo.whisper-flow.plist

# Check status
launchctl list | grep whisper

# View logs
tail -f .tmp/whisper/whisper_flow.log
```

## Testing

```bash
# Test mic capture (records 3s, shows levels)
python execution/whisper_flow.py --test-mic

# Test paste mechanism (pastes test text in 3s)
python execution/whisper_flow.py --test-paste

# Test transcription + cleanup on a test recording
python execution/whisper_flow.py --test-transcribe

# Test filler word cleanup
python execution/whisper_flow.py --test-cleanup "So um basically I was like thinking about uh the thing"
```

## macOS Permissions Required

All three must be granted in **System Settings > Privacy & Security**:

1. **Accessibility** — for CGEventTap hotkey capture and Cmd+V simulation
   - Add Terminal.app (or your IDE) to the Accessibility list
2. **Input Monitoring** — for global keyboard event monitoring
   - Add Terminal.app (or your IDE) to the Input Monitoring list
3. **Microphone** — to record audio
   - Add Terminal.app (or your IDE) to the Microphone list

If CGEventTap fails to create, you'll see a clear error message with instructions.

**Tip:** If permissions were previously granted but hotkeys don't work, toggle the permission OFF then ON in System Settings, then restart the app.

## Configuration (.env)

```
WHISPER_MODEL=base                   # tiny, base, small, medium, large
WHISPER_COMPUTE_TYPE=int8            # int8, float16, float32
WHISPER_MOUSE_HOLD_SECONDS=2.0       # seconds to hold middle mouse
WHISPER_CLEANUP_MODE=regex           # regex (free), api (Claude Haiku ~$0.001/call), none
WHISPER_HOTKEY_TAP_TIMEOUT=0.4       # max seconds for a tap
WHISPER_DOUBLE_TAP_WINDOW=0.6        # max seconds between double-taps
WHISPER_PAUSE_HOLD_THRESHOLD=1.0     # min seconds hold for pause
WHISPER_RESTORE_CLIPBOARD=true       # save/restore clipboard around paste
WHISPER_VAD_FILTER=true              # Silero VAD (filters silence before transcription)
```

### Model Sizes

| Model | Size | Speed (M4 Max) | Accuracy |
|---|---|---|---|
| tiny | 39M / ~75MB | ~10x realtime | Basic |
| base | 74M / ~150MB | ~6x realtime | Good (default) |
| small | 244M / ~500MB | ~3x realtime | Better |
| medium | 769M / ~1.5GB | ~1.5x realtime | Best for dictation |

First run downloads the model to `~/.cache/huggingface/`. Subsequent runs load from cache.

### Cleanup Modes

| Mode | Speed | Quality | Cost |
|---|---|---|---|
| `none` | Instant | Raw Whisper output | Free |
| `regex` | Instant | Removes common fillers (um, uh, etc.) | Free |
| `api` | +1-2s | Full grammar/punctuation polish via Claude Haiku | ~$0.001/call |

## Architecture

Single file: `execution/whisper_flow.py` (~970 lines)

- **State machine**: IDLE → RECORDING ⇄ PAUSED → TRANSCRIBING → TYPING → IDLE
- **Audio**: sounddevice (16kHz mono float32) → WAV file
- **Transcription**: faster-whisper (CTranslate2 on CPU) with Silero VAD
- **Cleanup**: Regex filler removal + optional Claude Haiku polish
- **Paste**: pbcopy → CGEvent Cmd+V (Quartz) + clipboard save/restore
- **UI**: rumps menubar app + NSPanel overlay with animated waveform + stop button
- **Hotkey**: CGEventTap via PyObjC (replaced pynput for reliability on Apple Silicon)
- **Mouse**: pynput mouse listener (middle button hold)

## Key Design Decisions

1. **CGEventTap over pynput for keyboard**: pynput's keyboard listener was unreliable on Apple Silicon — events never arrived even with Accessibility permission. CGEventTap gives direct control and clear error reporting.
2. **Right Option over Fn key**: The Fn/Globe key is completely intercepted by macOS on Apple Silicon before any public API can see it. Right Option is rarely used and provides the same single-key gesture.
3. **Clipboard save/restore**: The paste mechanism temporarily uses the clipboard, so the user's copied content is saved before and restored 0.5s after paste.
4. **Module-level ObjC classes**: NSView subclasses must be defined at module level to prevent PyObjC garbage collection crashes (SIGTRAP exit 133).

## Troubleshooting

| Problem | Fix |
|---|---|
| "CGEventTap creation failed" | Grant Accessibility + Input Monitoring to Terminal/IDE. Toggle OFF→ON if already listed. |
| "Input/output error" on launch | Grant Microphone permission to Terminal/IDE |
| Hotkey doesn't work | Check all 3 permissions. Restart app after permission changes. |
| Model download fails | Check internet; model caches in ~/.cache/huggingface/ |
| Low audio / no transcription | Run `--test-mic` to check levels; check mic in System Settings > Sound |
| Paste doesn't work | Run `--test-paste`; ensure Accessibility permission is granted |
| App crashes with SIGTRAP 133 | Don't define ObjC classes inside methods (see Key Design Decisions #4) |

## Self-Anneal Notes

- If transcription accuracy is poor, upgrade model to `small` in .env
- If recording latency is noticeable, `tiny` model is fastest
- If filler word removal is too aggressive, switch `WHISPER_CLEANUP_MODE=none`
- For highest quality output, use `WHISPER_CLEANUP_MODE=api` (requires ANTHROPIC_API_KEY)
- CGEventTap can be disabled by macOS if callback takes too long — the code auto-re-enables it
