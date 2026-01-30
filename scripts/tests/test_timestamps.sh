#!/bin/bash
# Test that timestamps include timezone info for correct frontend parsing

BASE_URL="${API_URL:-http://127.0.0.1:8000}"
API="$BASE_URL/api/v1"

red='\033[0;31m'
green='\033[0;32m'
nc='\033[0m'

echo "================================"
echo "Timestamp Format Tests"
echo "================================"
echo ""

# Get a user from leaderboard
USERNAME=$(curl -s "$API/stats/leaderboard?limit=1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['leaderboard'][0]['username'] if d.get('leaderboard') else '')" 2>/dev/null)

if [ -z "$USERNAME" ]; then
    echo -e "${red}FAIL${nc} No users in leaderboard to test"
    exit 1
fi

echo "Testing user: $USERNAME"
echo ""

# Fetch user stats
RESPONSE=$(curl -s "$API/stats/user/$USERNAME")

# Test last_message_date has timezone
LAST_MSG=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('last_message_date', ''))" 2>/dev/null)
if [[ "$LAST_MSG" == *"+00:00"* ]] || [[ "$LAST_MSG" == *"Z"* ]]; then
    echo -e "${green}PASS${nc} last_message_date has timezone: $LAST_MSG"
else
    echo -e "${red}FAIL${nc} last_message_date missing timezone: $LAST_MSG"
fi

# Test first_message_date has timezone
FIRST_MSG=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('first_message_date', ''))" 2>/dev/null)
if [[ "$FIRST_MSG" == *"+00:00"* ]] || [[ "$FIRST_MSG" == *"Z"* ]]; then
    echo -e "${green}PASS${nc} first_message_date has timezone: $FIRST_MSG"
else
    echo -e "${red}FAIL${nc} first_message_date missing timezone: $FIRST_MSG"
fi

# Test recent_messages timestamps have timezone
RECENT_TS=$(echo "$RESPONSE" | python3 -c "import sys,json; msgs=json.load(sys.stdin).get('recent_messages',[]); print(msgs[0]['timestamp'] if msgs else '')" 2>/dev/null)
if [[ "$RECENT_TS" == *"+00:00"* ]] || [[ "$RECENT_TS" == *"Z"* ]]; then
    echo -e "${green}PASS${nc} recent_messages timestamp has timezone: $RECENT_TS"
else
    echo -e "${red}FAIL${nc} recent_messages timestamp missing timezone: $RECENT_TS"
fi

echo ""

# Test timezone conversion
echo "Timezone Conversion Test:"
echo "========================="

python3 << 'EOF'
from datetime import datetime, timezone

# Simulating what JavaScript does
test_timestamps = [
    "2026-01-30T18:56:20.159000+00:00",  # With timezone (correct)
    "2026-01-30T18:56:20.159000",         # Without timezone (problematic)
]

for ts in test_timestamps:
    # Parse like JavaScript would (with timezone = UTC, without = local)
    if '+' in ts or 'Z' in ts:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        print(f"  {ts}")
        print(f"    -> Parsed as UTC, will convert correctly to BRT")
    else:
        print(f"  {ts}")
        print(f"    -> No timezone! JavaScript treats as LOCAL time (wrong!)")
EOF

echo ""
echo "================================"
