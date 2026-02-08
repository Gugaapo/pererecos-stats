#!/bin/bash
# Bot monitor script for pererecos-stats
# Detects when the Twitch bot has silently disconnected (even if the
# process is still running) by checking the age of the last stored message.
# Run hourly via cron:
#   0 * * * * /home/clawdbot/twitch-stats/scripts/bot-monitor.sh

LOG_FILE="/home/clawdbot/twitch-stats/logs/bot-monitor.log"
LOCK_FILE="/tmp/pererecos-stats-monitor.lock"
HEALTH_URL="http://127.0.0.1:8000/api/v1/health"
SERVICE_NAME="pererecos-stats"
DB_NAME="twitch_stats"
# Restart if no messages stored in this many seconds (2 hours)
MESSAGE_THRESHOLD_SECS=7200
# Minimum seconds between restarts to avoid restart loops
RESTART_COOLDOWN_SECS=3600
COOLDOWN_FILE="/tmp/pererecos-stats-last-restart"
# Max log size in bytes before rotation (500KB)
MAX_LOG_SIZE=512000

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# --- Lock to prevent overlapping runs with health-check.sh ---
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    exit 0
fi

# --- Log rotation ---
if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt "$MAX_LOG_SIZE" ]; then
    mv "$LOG_FILE" "${LOG_FILE}.old"
    log "Log rotated"
fi

needs_restart=false
reason=""

# --- Check 1: Is the API responding at all? ---
health_response=$(curl -sf --max-time 5 "$HEALTH_URL" 2>/dev/null)

if [ -z "$health_response" ]; then
    needs_restart=true
    reason="API not responding"
    log "ALERT: API not responding"
fi

# --- Check 2: Health endpoint bot_connected status ---
if [ "$needs_restart" = false ]; then
    bot_connected=$(echo "$health_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bot_connected', False))" 2>/dev/null)

    if [ "$bot_connected" = "False" ]; then
        needs_restart=true
        reason="bot_connected=false in health endpoint"
        log "ALERT: Bot disconnected detected via health endpoint"
    fi
fi

# --- Check 3: Last message age in MongoDB (catches silent disconnections) ---
if [ "$needs_restart" = false ]; then
    last_msg_epoch=$(mongosh --quiet --eval "
        const msg = db.getSiblingDB('${DB_NAME}').chat_messages.find().sort({timestamp: -1}).limit(1).toArray();
        if (msg.length > 0) { print(Math.floor(msg[0].timestamp.getTime() / 1000)); }
        else { print(0); }
    " 2>/dev/null)

    if [ -n "$last_msg_epoch" ] && [ "$last_msg_epoch" -gt 0 ] 2>/dev/null; then
        now_epoch=$(date +%s)
        age_secs=$(( now_epoch - last_msg_epoch ))
        age_hours=$(( age_secs / 3600 ))

        if [ "$age_secs" -ge "$MESSAGE_THRESHOLD_SECS" ]; then
            needs_restart=true
            reason="no messages in ${age_hours}h (threshold: $((MESSAGE_THRESHOLD_SECS / 3600))h)"
            log "ALERT: Last message was ${age_hours}h ago"
        fi
    else
        log "WARNING: Could not query MongoDB for last message time"
    fi
fi

# --- Restart if needed ---
if [ "$needs_restart" = true ]; then
    # Check cooldown to avoid restart loops
    if [ -f "$COOLDOWN_FILE" ]; then
        last_restart=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)
        now_epoch=$(date +%s)
        elapsed=$(( now_epoch - last_restart ))
        if [ "$elapsed" -lt "$RESTART_COOLDOWN_SECS" ]; then
            remaining=$(( (RESTART_COOLDOWN_SECS - elapsed) / 60 ))
            log "SKIPPED restart (cooldown: ${remaining}min remaining) — reason was: $reason"
            exit 0
        fi
    fi

    log "Initiating restart — reason: $reason"

    # Save pre-restart diagnostics
    log "--- Pre-restart diagnostics ---"
    journalctl -u "$SERVICE_NAME" -n 50 --no-pager >> "$LOG_FILE" 2>&1
    log "--- End diagnostics ---"

    sudo systemctl restart "$SERVICE_NAME"
    date +%s > "$COOLDOWN_FILE"
    log "Restart command issued"

    # Wait and verify recovery
    sleep 10
    health_after=$(curl -sf --max-time 5 "$HEALTH_URL" 2>/dev/null)

    if [ -n "$health_after" ]; then
        bot_after=$(echo "$health_after" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bot_connected', False))" 2>/dev/null)
        if [ "$bot_after" = "True" ]; then
            log "Recovery successful — bot_connected=true"
        else
            log "ERROR: Recovery partial — bot_connected=$bot_after"
        fi
    else
        log "ERROR: API not responding after restart"
    fi
else
    log "OK: All checks passed"
fi
