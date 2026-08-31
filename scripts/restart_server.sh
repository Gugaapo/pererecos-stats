#!/bin/bash
# Local-dev restart: pkill + background uvicorn.
# Do not use on production — that unit is systemd (pererecos-stats.service).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../backend" && pwd)"
UVICORN="$BACKEND_DIR/venv/bin/uvicorn"

echo "Stopping existing server..."
pkill -f "uvicorn app.main:app" 2>/dev/null
sleep 1

echo "Starting server..."
cd "$BACKEND_DIR"
"$UVICORN" app.main:app --host 127.0.0.1 --port 8000 &

sleep 2

# Verify it started
if pgrep -f "uvicorn app.main:app" > /dev/null; then
    echo "Server started successfully!"
    echo "Access at: http://127.0.0.1:8000"
else
    echo "Failed to start server!"
    exit 1
fi
