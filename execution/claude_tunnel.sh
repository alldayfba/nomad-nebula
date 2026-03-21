#!/bin/bash
# Claude CLI Proxy Tunnel — starts cloudflared tunnel + updates Vercel env vars
# Runs as launchd service. Self-heals: health check loop restarts tunnel on failure.
# Hardened for lid-closed operation — survives brief Wi-Fi blips.

PROXY_PORT=5055
LOG="/tmp/claude-tunnel.log"
VERCEL_PROJECTS=("247profitsSAAS" "247growthSAAS")
ENV_VAR_NAME="CLAUDE_PROXY_URL"
HEALTH_CHECK_INTERVAL=30  # seconds between health checks
MAX_TUNNEL_RETRIES=5
CURRENT_TUNNEL_URL=""

log() {
    echo "[$(date)] $1" >> "$LOG"
}

wait_for_proxy() {
    log "Waiting for proxy health..."
    for i in {1..30}; do
        if curl -sf http://127.0.0.1:$PROXY_PORT/health > /dev/null 2>&1; then
            log "Proxy is healthy"
            return 0
        fi
        sleep 2
    done
    log "ERROR: Proxy not healthy after 60s"
    return 1
}

start_tunnel() {
    local tunnel_log="/tmp/cf-tunnel-output.log"
    > "$tunnel_log"  # Clear previous output

    cloudflared tunnel --url http://127.0.0.1:$PROXY_PORT 2>"$tunnel_log" &
    CF_PID=$!

    # Wait for tunnel URL to appear
    local url=""
    for i in {1..30}; do
        url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$tunnel_log" 2>/dev/null | head -1)
        if [ -n "$url" ]; then
            break
        fi
        # Check if cloudflared died
        if ! kill -0 $CF_PID 2>/dev/null; then
            log "ERROR: cloudflared process died during startup"
            return 1
        fi
        sleep 1
    done

    if [ -z "$url" ]; then
        log "ERROR: Failed to get tunnel URL"
        kill $CF_PID 2>/dev/null
        return 1
    fi

    log "Tunnel URL: $url (PID: $CF_PID)"

    # Only update Vercel if URL changed
    if [ "$url" != "$CURRENT_TUNNEL_URL" ]; then
        update_vercel "$url"
        CURRENT_TUNNEL_URL="$url"
    else
        log "Tunnel URL unchanged, skipping Vercel update"
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

check_tunnel_health() {
    # 1. Check if cloudflared process is alive
    if ! kill -0 $CF_PID 2>/dev/null; then
        log "ALERT: cloudflared process (PID $CF_PID) died"
        return 1
    fi

    # 2. Check if proxy is still reachable
    if ! curl -sf http://127.0.0.1:$PROXY_PORT/health > /dev/null 2>&1; then
        log "WARNING: proxy health check failed (may recover)"
        # Don't restart tunnel for proxy issues — proxy has its own launchd
        return 0
    fi

    # 3. Check if tunnel URL is reachable (if we have one)
    if [ -n "$CURRENT_TUNNEL_URL" ]; then
        if ! curl -sf --max-time 10 "$CURRENT_TUNNEL_URL/health" > /dev/null 2>&1; then
            log "WARNING: tunnel URL unreachable — will retry"
            # Give it one more chance (Wi-Fi blip)
            sleep 5
            if ! curl -sf --max-time 10 "$CURRENT_TUNNEL_URL/health" > /dev/null 2>&1; then
                log "ALERT: tunnel URL still unreachable after retry"
                return 1
            fi
        fi
    fi

    return 0
}

cleanup() {
    log "Shutting down tunnel (PID: $CF_PID)"
    kill $CF_PID 2>/dev/null
    wait $CF_PID 2>/dev/null
    exit 0
}

trap cleanup SIGTERM SIGINT

# ── Main ──────────────────────────────────────────────────────────────────────

log "Starting Claude tunnel (hardened)..."

# Wait for proxy
if ! wait_for_proxy; then
    log "Exiting — proxy not available"
    exit 1
fi

# Start initial tunnel
retry_count=0
while ! start_tunnel; do
    retry_count=$((retry_count + 1))
    if [ $retry_count -ge $MAX_TUNNEL_RETRIES ]; then
        log "ERROR: Failed to start tunnel after $MAX_TUNNEL_RETRIES attempts"
        exit 1
    fi
    log "Retrying tunnel start ($retry_count/$MAX_TUNNEL_RETRIES)..."
    sleep 10
done

log "Tunnel running — entering health check loop (every ${HEALTH_CHECK_INTERVAL}s)"

# Health check loop — monitors tunnel and auto-restarts on failure
while true; do
    sleep $HEALTH_CHECK_INTERVAL

    if ! check_tunnel_health; then
        log "Tunnel unhealthy — killing and restarting..."
        kill $CF_PID 2>/dev/null
        wait $CF_PID 2>/dev/null
        sleep 3

        # Wait for proxy (may have also restarted)
        if ! wait_for_proxy; then
            log "Proxy not available — waiting 30s before retry"
            sleep 30
            continue
        fi

        retry_count=0
        while ! start_tunnel; do
            retry_count=$((retry_count + 1))
            if [ $retry_count -ge $MAX_TUNNEL_RETRIES ]; then
                log "ERROR: Failed to restart tunnel after $MAX_TUNNEL_RETRIES attempts — exiting for launchd restart"
                exit 1
            fi
            log "Retrying tunnel restart ($retry_count/$MAX_TUNNEL_RETRIES)..."
            sleep 10
        done

        log "Tunnel restarted successfully"
    fi
done
