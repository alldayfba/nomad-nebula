#!/bin/bash
# WhisperFlow watchdog — restarts WhisperFlow if it dies.
# Called by launchd every 30 seconds. No Terminal windows opened.

if ! pgrep -f "python.*whisper_flow.py" > /dev/null 2>&1; then
    cd /Users/Shared/antigravity/projects/nomad-nebula
    export PYTHONUNBUFFERED=1
    mkdir -p .tmp/whisper

    if [ -f ".venv/bin/python3" ]; then
        PYTHON=".venv/bin/python3"
    else
        PYTHON="python3"
    fi

    nohup "$PYTHON" execution/whisper_flow.py >> .tmp/whisper/whisper_flow.log 2>&1 &
fi
