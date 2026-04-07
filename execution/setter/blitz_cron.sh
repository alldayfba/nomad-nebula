#!/bin/bash
# Follower Blitz Cron — runs cold outbound DMs on a loop
# Designed to run via launchd every 3 hours
# Each run sends up to 400 DMs, auto-skips already contacted

cd /Users/Shared/antigravity/projects/nomad-nebula
source .venv/bin/activate

LOG_DIR=".tmp/setter"
LOG_FILE="$LOG_DIR/blitz-cron.log"
PAUSE_FILE="$LOG_DIR/PAUSED"

# Check kill switch
if [ -f "$PAUSE_FILE" ]; then
    echo "$(date) PAUSED — $PAUSE_FILE exists, skipping run" >> "$LOG_FILE"
    exit 0
fi

# Check Chrome is running
if ! curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
    echo "$(date) ERROR — Chrome not running on port 9222" >> "$LOG_FILE"
    exit 1
fi

echo "$(date) Starting blitz run (limit 400)..." >> "$LOG_FILE"

python -m execution.setter.follower_blitz \
    --mode cold \
    --limit 400 \
    --fast \
    --no-night-mode \
    >> "$LOG_FILE" 2>&1

echo "$(date) Blitz run complete" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"
