#!/bin/bash
# Restart the uvicorn server

BACKEND_DIR="/home/clawdbot/twitch-stats/backend"

echo "Stopping existing server..."
pkill -f "uvicorn app.main:app" 2>/dev/null
sleep 1

echo "Starting server..."
cd "$BACKEND_DIR"
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 &

sleep 2

# Verify it started
if pgrep -f "uvicorn app.main:app" > /dev/null; then
    echo "Server started successfully!"
    echo "Access at: http://127.0.0.1:8000"
else
    echo "Failed to start server!"
    exit 1
fi
