# WhisperFlow — SOP

## Purpose
Local voice-to-text dictation tool for macOS. Free, private, runs entirely on your machine. Records from mic, transcribes with faster-whisper, cleans up via Claude Haiku, pastes into the active text field.

## How It Works
1. Runs as a macOS menubar app (🎤 icon)
2. Tap **Left Option (⌥)** — recording starts instantly, overlay appears
3. Speak into your mic — menubar shows 🔴 REC
4. Tap **Left Option (⌥)** again — stops recording
5. Audio transcribed locally (~2-5s), then polished by Claude Haiku
6. Transcription pasted into whatever text field has focus
7. Original clipboard restored automatically

## Controls

| Action | Trigger |
|---|---|
| Start/stop recording | Tap Left Option (⌥) — instant |
| Locked mode (hands-free) | Double-tap Left Option within 600ms |
| Pause/resume recording | Long-press Left Option (>1 second) |
| Stop recording (mouse) | Click stop button on overlay pill |
| Toggle recording (mouse alt) | Hold middle mouse button 2+ seconds |

### Gesture Details
- **Single tap**: Instant toggle. No delay. Press and release Option → recording starts/stops immediately.
- **Double-tap**: Two taps within 600ms. First tap starts recording, second tap upgrades to locked mode — recording continues until you double-tap again.
- **Long-press**: Hold Option for 1+ second while recording. Pauses (keeps audio). Hold again to resume. Overlay shows ⏸️ PAUSED.

## Install & Auto-Start

```bash
# Install dependencies
pip install sounddevice numpy faster-whisper rumps pynput pyobjc-framework-Quartz

# One-time setup: install auto-start
python execution/whisper_flow.py --install

# Grant permissions (REQUIRED — do this once):
#   System Settings > Privacy & Security > Accessibility > Terminal ✓
#   System Settings > Privacy & Security > Input Monitoring > Terminal ✓
#   System Settings > Privacy & Security > Microphone > Terminal ✓

# Manual launch (if not using auto-start):
open -a Terminal execution/launch_whisperflow.sh
```

### What Happens at Login
1. **launchd** opens Terminal briefly → launches WhisperFlow → Terminal closes
2. **Watchdog** (every 30s) checks if WhisperFlow died → silently restarts if so
3. You never have to think about it — it's always running

### Files
| File | Purpose |
|---|---|
| `execution/whisper_flow.py` | Main app (~2200 lines) |
| `execution/launch_whisperflow.sh` | Terminal launcher (auto-closes) |
| `execution/whisperflow_watchdog.sh` | Silent restart if killed |
| `~/Library/LaunchAgents/com.sabbo.whisper-flow.plist` | Boot launcher |
| `~/Library/LaunchAgents/com.sabbo.whisper-flow-watchdog.plist` | 30s watchdog |
| `.tmp/whisper/whisper_flow.log` | Runtime log |
| `.tmp/whisper/dictionary.json` | Custom word corrections |
| `.tmp/whisper/history.db` | Transcription history |

## Uninstall

```bash
python execution/whisper_flow.py --uninstall
```

## Configuration (.env)

```
WHISPER_MODEL=small.en               # tiny.en, base.en, small.en, medium.en
WHISPER_COMPUTE_TYPE=int8            # int8 (fastest), float16, float32
WHISPER_CLEANUP_MODE=api             # api (best), regex (free), none
WHISPER_HOTKEY_TAP_TIMEOUT=0.4       # max seconds for a tap
WHISPER_DOUBLE_TAP_WINDOW=0.6        # max seconds between double-taps
WHISPER_PAUSE_HOLD_THRESHOLD=1.0     # min seconds hold for pause
WHISPER_RESTORE_CLIPBOARD=true       # save/restore clipboard around paste
WHISPER_VAD_FILTER=true              # Silero VAD (filters silence)
WHISPER_PREROLL_SECONDS=0.75         # Ring buffer pre-roll (captures first word)
```

### Model Sizes

| Model | Size | Speed | Accuracy | Use When |
|---|---|---|---|---|
| tiny.en | ~75MB | ~10x realtime | Basic | Quick notes, speed matters |
| base.en | ~150MB | ~6x realtime | Good | Default balance |
| **small.en** | ~500MB | ~3x realtime | **Great** | **Recommended** — best accuracy/speed |
| medium.en | ~1.5GB | ~1.5x realtime | Best | Long dictation, accuracy critical |

### Cleanup Modes

| Mode | Speed | Quality | Cost |
|---|---|---|---|
| `none` | Instant | Raw Whisper output | Free |
| `regex` | Instant | Removes fillers (um, uh) | Free |
| **`api`** | +1-2s | **Full polish** (punctuation, grammar, dedup) | **~$0.001/call** |

## Architecture

### Self-Healing Systems
- **HealthMonitor** (every 30s): Checks ring buffer, mic silence, model state, CGEventTap, dictionary integrity. Auto-fixes anything broken.
- **Watchdog** (every 30s via launchd): Restarts entire app if process dies.
- **Stream lifecycle lock**: Prevents race conditions between HealthMonitor and recording.
- **Auto mic switch**: Follows macOS system default input device. Unplug USB mic → switches to built-in within 30s.
- **Exponential backoff**: If mic keeps failing, backs off instead of spam-restarting.

### Thread Safety
| Thread | Purpose | Lock |
|---|---|---|
| Main (rumps) | UI, overlay, menu | — |
| Ring buffer | Always-on mic capture | `_stream_lock` (RLock) |
| CGEventTap | Keyboard listener | Own CFRunLoop |
| Transcription | Whisper + paste | `self.lock` |
| HealthMonitor | Self-healing checks | `_stream_lock` |

### Key Design Decisions
1. **CGEventTap for keyboard** — pynput unreliable on Apple Silicon. CGEventTap gives direct control.
2. **Left Option key** — Fn/Globe key is uninterceptable on Apple Silicon. Left Option rarely conflicts.
3. **Launch via Terminal.app** — macOS TCC requires the "responsible process" to have Input Monitoring. Terminal.app has it; Claude Code and most IDEs don't.
4. **Ring buffer (always-on mic)** — 0.75s pre-roll captures the first word. No mic-open delay.
5. **Module-level ObjC classes** — Nested NSView subclasses get garbage collected → SIGTRAP 133.

## macOS Permissions (CRITICAL)

All three must be granted to **Terminal.app** in System Settings > Privacy & Security:

| Permission | Why | What Breaks Without It |
|---|---|---|
| **Accessibility** | CGEventTap creation + Cmd+V paste | "CGEventTap creation failed" error |
| **Input Monitoring** | Key events dispatched to CGEventTap | Tap created but no events arrive (silent failure) |
| **Microphone** | Audio capture | All mics return silence (peak=0.000) |

**If hotkey stops working after an OS update:** Toggle Terminal OFF→ON in Input Monitoring, then restart WhisperFlow.

## Dictionary (Auto-Learning)

WhisperFlow learns your corrections. If you backspace over a misheard word and retype it, it learns after seeing the same correction 3 times.

```bash
# View dictionary
python execution/whisper_flow.py --dict list

# Add manual correction
python execution/whisper_flow.py --dict add "savo" "Sabbo"

# Reset corrupted dictionary
python execution/whisper_flow.py --dict reset
```

Protected words (80+) can never be auto-corrected (prevents garbage like "it"→"bro").

## Troubleshooting

| Problem | Fix |
|---|---|
| Tap Option, nothing happens | Check 🎤 icon in menubar. If missing, run `launch_whisperflow.sh`. If present, check Input Monitoring permission for Terminal. |
| "CGEventTap creation failed" | Grant Accessibility + Input Monitoring to Terminal.app. Toggle OFF→ON if already listed. |
| Recording but no audio | Run `--test-mic`. Check Microphone permission. Try unplugging/replugging USB mic. |
| Poor transcription quality | Upgrade to `WHISPER_MODEL=small.en` and `WHISPER_CLEANUP_MODE=api` in .env |
| Multiple 🎤 icons in menubar | Reboot clears ghost icons from crashed instances |
| Terminal windows keep opening | Check `whisperflow_watchdog.sh` — it should NOT open Terminal (only `launch_whisperflow.sh` does) |
| App crashes with SIGTRAP 133 | Don't define ObjC classes inside methods (module-level only) |

## Self-Anneal Notes

- Stream lifecycle lock (`_stream_lock`) protects ALL audio stream operations — never call `sd._terminate()` while a stream is active
- HealthMonitor must acquire `_stream_lock` with TOCTOU re-check before restarting streams
- The `_audio_callback` copies `indata` early (`indata.copy()`) to prevent use-after-free on stream restart
- Ring buffer restarts are allowed even during recording — the ring buffer IS the recording stream
- Dictionary PROTECTED_WORDS set prevents auto-learning garbage corrections
