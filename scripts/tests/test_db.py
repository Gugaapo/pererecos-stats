#!/home/clawdbot/twitch-stats/backend/venv/bin/python3
"""Test database connection and basic queries."""

import asyncio
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, '/home/clawdbot/twitch-stats/backend')

GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

passed = 0
failed = 0


def test_pass(msg):
    global passed
    print(f"{GREEN}PASS{NC} {msg}")
    passed += 1


def test_fail(msg, error=None):
    global failed
    print(f"{RED}FAIL{NC} {msg}")
    if error:
        print(f"      Error: {error}")
    failed += 1


async def main():
    print("================================")
    print("Database Tests")
    print("================================")
    print("")

    # Test 1: Import config
    try:
        from app.config import get_settings
        settings = get_settings()
        test_pass(f"Config loaded (MongoDB: {settings.mongodb_url[:30]}...)")
    except Exception as e:
        test_fail("Config import", e)
        return 1

    # Test 2: Database connection
    try:
        from app.database import db
        await db.connect()
        test_pass("Database connected")
    except Exception as e:
        test_fail("Database connection", e)
        return 1

    # Test 3: Messages collection exists
    try:
        count = await db.messages.count_documents({})
        test_pass(f"Messages collection accessible ({count:,} documents)")
    except Exception as e:
        test_fail("Messages collection", e)

    # Test 4: Indexes exist
    try:
        indexes = await db.messages.index_information()
        expected = [
            'username_1_timestamp_-1',
            'timestamp_-1',
            'username_1_hour_1',
            'user_id_1_timestamp_-1',
            'user_id_1_hour_1'
        ]
        for idx in expected:
            if idx in indexes:
                test_pass(f"Index exists: {idx}")
            else:
                test_fail(f"Index missing: {idx}")
    except Exception as e:
        test_fail("Index check", e)

    # Test 5: Sample message structure
    try:
        sample = await db.messages.find_one()
        if sample:
            required_fields = ['username', 'message', 'timestamp', 'hour']
            for field in required_fields:
                if field in sample:
                    test_pass(f"Message has field: {field}")
                else:
                    test_fail(f"Message missing field: {field}")

            # Check for user_id (new field - may not exist in old messages)
            if 'user_id' in sample:
                test_pass(f"Message has user_id: {sample['user_id']}")
            else:
                print(f"{YELLOW}INFO{NC} Old message without user_id (expected for legacy data)")

            # Check timestamp is datetime
            if isinstance(sample.get('timestamp'), datetime):
                ts = sample['timestamp']
                tz_info = "with timezone" if ts.tzinfo else "naive (no timezone)"
                test_pass(f"Timestamp is datetime ({tz_info})")
            else:
                test_fail("Timestamp is not datetime type")
        else:
            print(f"{YELLOW}SKIP{NC} No messages in database")
    except Exception as e:
        test_fail("Sample message", e)

    # Test 6: Aggregation works
    try:
        pipeline = [
            {"$group": {"_id": "$username", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 1}
        ]
        result = await db.messages.aggregate(pipeline).to_list(1)
        if result:
            test_pass(f"Aggregation works (top user: {result[0]['_id']} with {result[0]['count']} msgs)")
        else:
            print(f"{YELLOW}SKIP{NC} No aggregation results")
    except Exception as e:
        test_fail("Aggregation", e)

    # Cleanup
    await db.disconnect()

    print("")
    print("================================")
    print(f"Results: {GREEN}{passed} passed{NC}, {RED}{failed} failed{NC}")
    print("================================")

    return failed


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
