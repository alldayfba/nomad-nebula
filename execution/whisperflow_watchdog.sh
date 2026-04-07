#!/bin/bash
# WhisperFlow watchdog — checks if WhisperFlow is running, relaunches if not.
# Called by launchd every 30 seconds.

if ! pgrep -f "python.*whisper_flow.py" > /dev/null 2>&1; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    open -a Terminal "$SCRIPT_DIR/launch_whisperflow.sh"
fi
