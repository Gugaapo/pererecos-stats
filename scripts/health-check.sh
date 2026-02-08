#!/bin/bash
# Health check script for pererecos-stats
# Checks if the API is responding and restarts the service if not

LOG_FILE="/home/clawdbot/twitch-stats/logs/health-check.log"
LOCK_FILE="/tmp/pererecos-stats-monitor.lock"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Shared lock with bot-monitor.sh to prevent competing restarts
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    exit 0
fi

# Check if API responds within 5 seconds
if curl -sf --max-time 5 http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
    # API is healthy, no action needed
    exit 0
else
    log "Health check failed - API not responding"

    # Check if service is running
    if systemctl is-active --quiet pererecos-stats; then
        log "Service is running but not responding - restarting"
        sudo systemctl restart pererecos-stats
    else
        log "Service is not running - starting"
        sudo systemctl start pererecos-stats
    fi

    # Wait and verify (10s to allow bot to connect to Twitch)
    sleep 10
    if curl -sf --max-time 5 http://127.0.0.1:8000/api/v1/health > /dev/null 2>&1; then
        log "Service recovered successfully"
    else
        log "ERROR: Service failed to recover"
        exit 1
    fi
fi
