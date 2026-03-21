#!/bin/bash
# Kill all multi-agent Chrome instances (ports 9223-9227)

BASE_PORT=9223
KILLED=0

for i in $(seq 1 5); do
    PORT=$((BASE_PORT + i - 1))
    PID=$(lsof -ti :$PORT 2>/dev/null)
    if [ -n "$PID" ]; then
        echo "Killing Chrome agent $i on port $PORT (PID: $PID)"
        kill $PID 2>/dev/null
        KILLED=$((KILLED + 1))
    fi
done

# Clean up temp data dirs
for i in $(seq 1 5); do
    DATA_DIR="/tmp/chrome-agent-${i}"
    if [ -d "$DATA_DIR" ]; then
        rm -rf "$DATA_DIR"
    fi
done

echo "Killed $KILLED Chrome instance(s). Temp data cleaned."
