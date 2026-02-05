#!/bin/bash
# Bot monitor script for pererecos-stats
# Detects when the Twitch bot task has crashed inside a running process
# and restarts the service. Run hourly via cron:
#   0 * * * * /home/clawdbot/twitch-stats/scripts/bot-monitor.sh

LOG_FILE="/home/clawdbot/twitch-stats/logs/bot-monitor.log"
HEALTH_URL="http://127.0.0.1:8000/api/v1/health"
SERVICE_NAME="pererecos-stats"
MESSAGE_THRESHOLD_HOURS=2

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

needs_restart=false
reason=""

# --- Check 1: Health endpoint bot_connected status ---
health_response=$(curl -sf --max-time 5 "$HEALTH_URL" 2>/dev/null)

if [ -z "$health_response" ]; then
    # API not responding at all — the existing health-check.sh handles this
    log "API not responding, skipping (handled by health-check.sh)"
    exit 0
fi

bot_connected=$(echo "$health_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bot_connected', 'unknown'))" 2>/dev/null)

if [ "$bot_connected" = "False" ]; then
    needs_restart=true
    reason="bot_connected=false in health endpoint"
    log "ALERT: Bot disconnected detected via health endpoint"
fi

# --- Check 2: Last message age in MongoDB (secondary check) ---
if [ "$needs_restart" = false ]; then
    last_msg_epoch=$(mongosh --quiet --eval "
        const msg = db.chat_messages.find().sort({timestamp: -1}).limit(1).toArray();
        if (msg.length > 0) { print(Math.floor(msg[0].timestamp.getTime() / 1000)); }
        else { print(0); }
    " pererecos_stats 2>/dev/null)

    if [ -n "$last_msg_epoch" ] && [ "$last_msg_epoch" -gt 0 ] 2>/dev/null; then
        now_epoch=$(date +%s)
        age_hours=$(( (now_epoch - last_msg_epoch) / 3600 ))

        if [ "$age_hours" -ge "$MESSAGE_THRESHOLD_HOURS" ]; then
            needs_restart=true
            reason="no messages in ${age_hours}h (threshold: ${MESSAGE_THRESHOLD_HOURS}h)"
            log "ALERT: No messages in ${age_hours} hours"
        fi
    fi
fi

# --- Restart if needed ---
if [ "$needs_restart" = true ]; then
    log "Initiating restart — reason: $reason"

    # Save pre-restart diagnostics
    log "--- Pre-restart diagnostics ---"
    journalctl -u "$SERVICE_NAME" -n 50 --no-pager >> "$LOG_FILE" 2>&1
    log "--- End diagnostics ---"

    sudo systemctl restart "$SERVICE_NAME"
    log "Restart command issued"

    # Wait and verify recovery
    sleep 10
    health_after=$(curl -sf --max-time 5 "$HEALTH_URL" 2>/dev/null)
    bot_after=$(echo "$health_after" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bot_connected', 'unknown'))" 2>/dev/null)

    if [ "$bot_after" = "True" ]; then
        log "Recovery successful — bot_connected=true"
    else
        log "ERROR: Recovery failed — bot_connected=$bot_after"
        exit 1
    fi
fi
