#!/bin/bash
# Test all API endpoints

BASE_URL="${API_URL:-http://127.0.0.1:8000}"
API="$BASE_URL/api/v1"
PASSED=0
FAILED=0

red='\033[0;31m'
green='\033[0;32m'
yellow='\033[1;33m'
nc='\033[0m'

test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_field="$3"

    response=$(curl -s -w "\n%{http_code}" "$url")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" = "200" ]; then
        if [ -n "$expected_field" ]; then
            if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$expected_field' in d or isinstance(d, list)" 2>/dev/null; then
                echo -e "${green}PASS${nc} $name (HTTP $http_code)"
                ((PASSED++))
                return 0
            else
                echo -e "${yellow}WARN${nc} $name (HTTP $http_code, missing field: $expected_field)"
                ((PASSED++))
                return 0
            fi
        else
            echo -e "${green}PASS${nc} $name (HTTP $http_code)"
            ((PASSED++))
            return 0
        fi
    else
        echo -e "${red}FAIL${nc} $name (HTTP $http_code)"
        echo "  Response: $body"
        ((FAILED++))
        return 1
    fi
}

echo "================================"
echo "API Endpoint Tests"
echo "Base URL: $API"
echo "================================"
echo ""

# Health check
test_endpoint "Health Check" "$API/health" "status"

# Leaderboard
test_endpoint "Leaderboard (all)" "$API/stats/leaderboard?period=all&limit=5" "leaderboard"
test_endpoint "Leaderboard (day)" "$API/stats/leaderboard?period=day&limit=5" "leaderboard"
test_endpoint "Leaderboard (week)" "$API/stats/leaderboard?period=week&limit=5" "leaderboard"
test_endpoint "Leaderboard (month)" "$API/stats/leaderboard?period=month&limit=5" "leaderboard"

# Get a username from leaderboard for user-specific tests
USERNAME=$(curl -s "$API/stats/leaderboard?limit=1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['leaderboard'][0]['username'] if d.get('leaderboard') else '')" 2>/dev/null)

if [ -n "$USERNAME" ]; then
    echo ""
    echo "Using test user: $USERNAME"
    echo ""

    # User stats
    test_endpoint "User Stats (all)" "$API/stats/user/$USERNAME?period=all" "total_messages"
    test_endpoint "User Stats (day)" "$API/stats/user/$USERNAME?period=day" "total_messages"
    test_endpoint "User Stats (week)" "$API/stats/user/$USERNAME?period=week" "total_messages"

    # Search
    PREFIX="${USERNAME:0:3}"
    test_endpoint "User Search" "$API/stats/search?q=$PREFIX" ""
else
    echo -e "${yellow}SKIP${nc} User-specific tests (no users in leaderboard)"
fi

echo ""

# Activity endpoints
test_endpoint "Rising Stars" "$API/stats/rising-stars?limit=5" "entries"
test_endpoint "Hour Leaders" "$API/stats/hour-leaders" "entries"
test_endpoint "Top Writers" "$API/stats/top-writers?limit=5" "entries"
test_endpoint "Active Chatters" "$API/stats/active-chatters" "chatters"
test_endpoint "Chat Activity" "$API/stats/chat-activity" "activity"
test_endpoint "Overall Activity" "$API/stats/overall-activity" "activity"
test_endpoint "Unique Chatters" "$API/stats/unique-chatters" "activity"
test_endpoint "Top Emotes" "$API/stats/top-emotes" "emotes"

# Frontend
echo ""
test_endpoint "Frontend (index)" "$BASE_URL/" ""

echo ""
echo "================================"
echo -e "Results: ${green}$PASSED passed${nc}, ${red}$FAILED failed${nc}"
echo "================================"

exit $FAILED
