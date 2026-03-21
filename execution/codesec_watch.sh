#!/bin/bash
# codesec_watch.sh — Auto-trigger CodeSec scan on file changes
# Uses fswatch to monitor directories and run scan when files change.
#
# Usage:
#   ./execution/codesec_watch.sh          # Run in foreground
#   ./execution/codesec_watch.sh &         # Run in background
#
# Requires: fswatch (brew install fswatch)

set -euo pipefail

PROJECT_ROOT="${NOMAD_NEBULA_ROOT:-/Users/Shared/antigravity/projects/nomad-nebula}"
SHARED_ROOT="/Users/Shared/antigravity"
LOG_FILE="$PROJECT_ROOT/.tmp/codesec/watch.log"
LOCK_FILE="$PROJECT_ROOT/.tmp/codesec/scan.lock"
COOLDOWN=120  # 2 minutes between scans (heavier than Training Officer's 60s)

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Check for fswatch
if ! command -v fswatch &> /dev/null; then
    echo "[codesec-watch] ERROR: fswatch not installed. Run: brew install fswatch"
    exit 1
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

run_scan() {
    # Prevent concurrent scans
    if [ -f "$LOCK_FILE" ]; then
        log "Scan already running, skipping."
        return
    fi

    touch "$LOCK_FILE"
    log "File change detected. Running CodeSec scan..."

    cd "$PROJECT_ROOT"
    if [ -d ".venv" ]; then
        source .venv/bin/activate 2>/dev/null || true
    fi

    python3 execution/codesec_scan.py >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?

    rm -f "$LOCK_FILE"

    if [ $EXIT_CODE -eq 0 ]; then
        log "CodeSec scan completed successfully."
    else
        log "CodeSec scan failed with exit code $EXIT_CODE"
    fi
}

log "Starting CodeSec file watcher..."
log "Monitoring: $PROJECT_ROOT/{directives,execution,SabboOS,bots,clients}"
log "Monitoring: $SHARED_ROOT/{memory,proposals}"
log "Cooldown: ${COOLDOWN}s between scans"

LAST_SCAN=0

# Watch directories for changes
fswatch -0 \
    --exclude '\.tmp' \
    --exclude '\.git' \
    --exclude '__pycache__' \
    --exclude '\.pyc$' \
    --include '\.md$' \
    --include '\.py$' \
    --include '\.yaml$' \
    --include '\.yml$' \
    --include '\.json$' \
    --include '\.sh$' \
    --include '\.env$' \
    "$PROJECT_ROOT/directives" \
    "$PROJECT_ROOT/execution" \
    "$PROJECT_ROOT/SabboOS" \
    "$PROJECT_ROOT/bots" \
    "$PROJECT_ROOT/clients" \
    "$PROJECT_ROOT" \
    "$SHARED_ROOT/memory" \
    "$SHARED_ROOT/proposals" \
    2>/dev/null | while read -d "" event; do

    NOW=$(date +%s)
    ELAPSED=$((NOW - LAST_SCAN))

    if [ $ELAPSED -ge $COOLDOWN ]; then
        LAST_SCAN=$NOW
        run_scan
    else
        log "Cooldown active (${ELAPSED}s/${COOLDOWN}s). Skipping."
    fi
done
