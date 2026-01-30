#!/bin/bash
# Test if server is running and responsive

BASE_URL="${API_URL:-http://127.0.0.1:8000}"

red='\033[0;31m'
green='\033[0;32m'
yellow='\033[1;33m'
nc='\033[0m'

echo "================================"
echo "Server Status Tests"
echo "================================"
echo ""

# Check if uvicorn process is running
PIDS=$(pgrep -f "uvicorn app.main:app" 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo -e "${green}PASS${nc} Uvicorn process running (PID: $PIDS)"
else
    echo -e "${red}FAIL${nc} Uvicorn process not running"
    echo ""
    echo "Start with:"
    echo "  cd /home/clawdbot/twitch-stats/backend"
    echo "  source venv/bin/activate"
    echo "  uvicorn app.main:app --host 127.0.0.1 --port 8000"
    exit 1
fi

# Check HTTP response
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/" 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${green}PASS${nc} HTTP response OK (code: $HTTP_CODE)"
else
    echo -e "${red}FAIL${nc} HTTP response failed (code: $HTTP_CODE)"
    exit 1
fi

# Check API health
HEALTH=$(curl -s "$BASE_URL/api/v1/health" 2>/dev/null)
BOT_STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bot_connected', False))" 2>/dev/null)
DB_STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('database_connected', False))" 2>/dev/null)

if [ "$DB_STATUS" = "True" ]; then
    echo -e "${green}PASS${nc} Database connected"
else
    echo -e "${red}FAIL${nc} Database not connected"
fi

if [ "$BOT_STATUS" = "True" ]; then
    echo -e "${green}PASS${nc} Twitch bot connected"
else
    echo -e "${yellow}WARN${nc} Twitch bot not connected (may be expected)"
fi

# Check response time
START=$(date +%s%N)
curl -s -o /dev/null "$BASE_URL/api/v1/stats/leaderboard?limit=1"
END=$(date +%s%N)
ELAPSED=$(( (END - START) / 1000000 ))

if [ "$ELAPSED" -lt 1000 ]; then
    echo -e "${green}PASS${nc} Response time OK (${ELAPSED}ms)"
elif [ "$ELAPSED" -lt 3000 ]; then
    echo -e "${yellow}WARN${nc} Response time slow (${ELAPSED}ms)"
else
    echo -e "${red}FAIL${nc} Response time too slow (${ELAPSED}ms)"
fi

echo ""
echo "================================"
