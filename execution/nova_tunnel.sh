#!/bin/bash
# Nova API Tunnel — exposes Flask app (port 5050) via Cloudflare tunnel
# Updates NOVA_API_URL on Vercel when URL changes.

FLASK_PORT=5050
LOG="/tmp/nova-tunnel.log"
VERCEL_PROJECTS=("247profitsSAAS" "247growthSAAS")
ENV_VAR_NAME="NOVA_API_URL"
HEALTH_CHECK_INTERVAL=30
MAX_RETRIES=5
CURRENT_URL=""

log() { echo "[$(date)] $1" >> "$LOG"; }

wait_for_flask() {
    log "Waiting for Flask on port $FLASK_PORT..."
    for i in {1..30}; do
        if curl -sf http://127.0.0.1:$FLASK_PORT/api/health > /dev/null 2>&1; then
            log "Flask is healthy"
            return 0
        fi
        sleep 2
    done
    log "ERROR: Flask not healthy after 60s"
    return 1
}

start_tunnel() {
    local out="/tmp/nova-cf-tunnel-output.log"
    > "$out"
    cloudflared tunnel --url http://127.0.0.1:$FLASK_PORT 2>"$out" &
    CF_PID=$!
    local url=""
    for i in {1..30}; do
        url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$out" 2>/dev/null | head -1)
        if [ -n "$url" ]; then break; fi
        if ! kill -0 $CF_PID 2>/dev/null; then
            log "ERROR: cloudflared died during startup"
            return 1
        fi
        sleep 1
    done
    if [ -z "$url" ]; then
        log "ERROR: No tunnel URL"
        kill $CF_PID 2>/dev/null
        return 1
    fi
    log "Tunnel URL: $url (PID: $CF_PID)"
    if [ "$url" != "$CURRENT_URL" ]; then
        update_vercel "$url"
        CURRENT_URL="$url"
    fi
    return 0
}

update_vercel() {
    local url="$1"
    local VERCEL_DIRS=("/Users/sabbojb/Documents/saas-dashboard" "/Users/SabboOpenClawAI/Documents/fba-saas")
    for i in "${!VERCEL_PROJECTS[@]}"; do
        local project="${VERCEL_PROJECTS[$i]}"
        local dir="${VERCEL_DIRS[$i]}"
        cd "$dir" 2>/dev/null || continue
        printf '%s' "$url" | vercel env add "$ENV_VAR_NAME" production --force 2>>"$LOG" || true
        log "Updated $project $ENV_VAR_NAME=$url"
    done
}

cleanup() {
    log "Shutting down nova tunnel (PID: $CF_PID)"
    kill $CF_PID 2>/dev/null
    wait $CF_PID 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

log "Starting Nova API tunnel..."
wait_for_flask || exit 1

retry=0
while ! start_tunnel; do
    retry=$((retry + 1))
    [ $retry -ge $MAX_RETRIES ] && { log "FATAL: Failed after $MAX_RETRIES attempts"; exit 1; }
    sleep 10
done

log "Tunnel running — health check every ${HEALTH_CHECK_INTERVAL}s"
while true; do
    sleep $HEALTH_CHECK_INTERVAL
    if ! kill -0 $CF_PID 2>/dev/null; then
        log "Tunnel died — restarting..."
        retry=0
        while ! start_tunnel; do
            retry=$((retry + 1))
            [ $retry -ge $MAX_RETRIES ] && exit 1
            sleep 10
        done
    fi
done
