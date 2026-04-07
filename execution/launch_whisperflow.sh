#!/bin/bash
# WhisperFlow launcher — opens via Terminal.app for Input Monitoring permissions,
# then runs in background and closes the Terminal window.
#
# Usage:
#   open -a Terminal /path/to/launch_whisperflow.sh
#
# Auto-start at login (run once):
#   python3 execution/whisper_flow.py --install
#
# The script auto-detects the project root relative to its own location.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT" || exit 1

# Kill any existing instance
pkill -f "python.*whisper_flow.py" 2>/dev/null
sleep 0.3

export PYTHONUNBUFFERED=1

# Use .venv if it exists, otherwise system python
if [ -f ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
else
    PYTHON="python3"
fi

# Ensure tmp dir exists
mkdir -p .tmp/whisper

# Launch WhisperFlow in background, detached from this terminal
nohup "$PYTHON" execution/whisper_flow.py >> .tmp/whisper/whisper_flow.log 2>&1 &
disown

# Wait for process to start, then close this Terminal window
sleep 2
osascript -e 'tell application "Terminal" to close front window' 2>/dev/null &
exit 0
