#!/bin/bash
# Run all tests

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

red='\033[0;31m'
green='\033[0;32m'
cyan='\033[0;36m'
nc='\033[0m'

TOTAL_FAILED=0

run_test() {
    local name="$1"
    local script="$2"

    echo ""
    echo -e "${cyan}>>> Running: $name${nc}"
    echo ""

    if [[ "$script" == *.py ]]; then
        # Use venv python for Python scripts
        /home/clawdbot/twitch-stats/backend/venv/bin/python3 "$script"
    else
        bash "$script"
    fi

    if [ $? -ne 0 ]; then
        ((TOTAL_FAILED++))
    fi
}

echo "========================================"
echo "  Twitch Stats - Full Test Suite"
echo "========================================"
echo ""
echo "Base URL: ${API_URL:-http://127.0.0.1:8000}"

# Run tests in order
run_test "Server Status" "./test_server.sh"
run_test "Database" "./test_db.py"
run_test "API Endpoints" "./test_api.sh"
run_test "Timestamps" "./test_timestamps.sh"

echo ""
echo "========================================"
if [ $TOTAL_FAILED -eq 0 ]; then
    echo -e "${green}All test suites passed!${nc}"
else
    echo -e "${red}$TOTAL_FAILED test suite(s) had failures${nc}"
fi
echo "========================================"

exit $TOTAL_FAILED
