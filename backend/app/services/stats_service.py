from datetime import datetime, timedelta, timezone
import math
import re
from app.database import db
from app.config import get_settings
import httpx
from app.models.schemas import (
    UserStats, HourlyActivity, LeaderboardResponse, LeaderboardEntry, RecentMessage,
    RivalInfo, ReplyTarget, ActiveChatter, RisingStarEntry, HourLeaderEntry, WriterEntry,
    UserSearchResult, UserRankings, ChatActivityPoint, FavoriteHour, EmoteUsage
)

# Cache for 7TV emotes
_7tv_emotes_cache: dict[str, str] | None = None
_7tv_cache_time: datetime | None = None

# HTTP client timeout (seconds)
HTTP_TIMEOUT = 10.0

# Database query limits
MAX_USERS_QUERY = 1000
MAX_MESSAGES_QUERY = 10000


def get_query_timeout() -> int:
    """Get MongoDB query timeout from settings"""
    settings = get_settings()
    return settings.mongodb_timeout_ms


async def aggregate_with_timeout(collection, pipeline, limit=None):
    """Execute aggregation with timeout"""
    timeout_ms = get_query_timeout()
    cursor = collection.aggregate(pipeline)
    if limit:
        return await cursor.to_list(limit)
    return await cursor.to_list(None)


async def find_with_timeout(collection, query, sort=None, limit=None):
    """Execute find with timeout"""
    cursor = collection.find(query)
    if sort:
        cursor = cursor.sort(*sort) if isinstance(sort, tuple) else cursor.sort(sort)
    if limit:
        cursor = cursor.limit(limit)
        return await cursor.to_list(limit)
    return await cursor.to_list(None)


async def get_7tv_emotes() -> dict[str, str]:
    """Get 7TV emotes (name -> id), cached for 1 hour"""
    global _7tv_emotes_cache, _7tv_cache_time

    now = datetime.now(timezone.utc)
    if _7tv_emotes_cache is not None and _7tv_cache_time is not None:
        if (now - _7tv_cache_time).total_seconds() < 3600:
            return _7tv_emotes_cache

    settings = get_settings()
    emotes = {}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # Fetch channel emotes
            resp = await client.get(f"https://7tv.io/v3/emote-sets/{settings.seventv_emote_set_id}")
            if resp.status_code == 200:
                data = resp.json()
                for emote in data.get("emotes", []):
                    emotes[emote["name"]] = emote["id"]

            # Fetch global emotes
            global_resp = await client.get("https://7tv.io/v3/emote-sets/global")
            if global_resp.status_code == 200:
                global_data = global_resp.json()
                for emote in global_data.get("emotes", []):
                    emotes[emote["name"]] = emote["id"]

    except httpx.TimeoutException:
        print("Timeout fetching 7TV emotes")
    except Exception as e:
        print(f"Error fetching 7TV emotes: {e}")

    _7tv_emotes_cache = emotes
    _7tv_cache_time = now
    return emotes


async def count_emotes_in_messages(messages: list[str], limit: int = 5) -> list[EmoteUsage]:
    """Count emote usage in a list of messages"""
    emotes = await get_7tv_emotes()
    if not emotes:
        return []

    counts: dict[str, int] = {}

    for message in messages:
        words = message.split()
        for word in words:
            if word in emotes:
                counts[word] = counts.get(word, 0) + 1

    # Sort by count and take top N
    sorted_emotes = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]

    return [
        EmoteUsage(emote_name=name, emote_id=emotes[name], count=count)
        for name, count in sorted_emotes
    ]


def get_date_filter(period: str) -> dict:
    now = datetime.now(timezone.utc)

    if period == "day":
        start = now - timedelta(days=1)
    elif period == "week":
        start = now - timedelta(weeks=1)
    elif period == "month":
        start = now - timedelta(days=30)
    else:
        return {}

    return {"timestamp": {"$gte": start}}


async def get_user_stats(username: str, period: str = "all") -> UserStats | None:
    date_filter = get_date_filter(period)
    match_stage = {"username": username.lower()}
    if date_filter:
        match_stage.update(date_filter)

    pipeline = [
        {"$match": match_stage},
        {"$facet": {
            "total": [{"$count": "count"}],
            "hourly": [
                {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}}
            ],
            "dates": [
                {"$group": {
                    "_id": None,
                    "first": {"$min": "$timestamp"},
                    "last": {"$max": "$timestamp"},
                    "display_name": {"$last": "$display_name"}
                }}
            ]
        }}
    ]

    results = await db.messages.aggregate(pipeline).to_list(1)
    if not results:
        return None

    result = results[0]
    total = result["total"][0]["count"] if result["total"] else 0
    dates_info = result["dates"][0] if result["dates"] else {}

    if total == 0:
        return None

    hourly_map = {h["_id"]: h["count"] for h in result["hourly"]}
    hourly_activity = [
        HourlyActivity(hour=h, count=hourly_map.get(h, 0))
        for h in range(24)
    ]

    recent_docs = await db.messages.find(
        {"username": username.lower()}
    ).sort("timestamp", -1).limit(10).to_list(10)

    recent_messages = [
        RecentMessage(message=doc["message"], timestamp=doc["timestamp"])
        for doc in recent_docs
    ]

    # Calculate new fields
    percentile = await get_user_percentile(username, period)
    peak_hours = get_peak_hours(hourly_activity)
    rival = await get_rival(username, hourly_activity, period)
    top_replies = await get_top_replies(username, period, limit=5)
    rankings = await get_user_rankings(username, period)
    top_emotes = await get_user_top_emotes(username, limit=10)

    # Calculate favorite hour
    favorite_hour = None
    if total > 0:
        max_hour = max(hourly_activity, key=lambda h: h.count)
        if max_hour.count > 0:
            favorite_hour = FavoriteHour(
                hour=max_hour.hour,
                count=max_hour.count,
                percentage=round((max_hour.count / total) * 100, 1)
            )

    return UserStats(
        username=username.lower(),
        display_name=dates_info.get("display_name", username),
        period=period,
        total_messages=total,
        hourly_activity=hourly_activity,
        recent_messages=recent_messages,
        first_message_date=dates_info.get("first"),
        last_message_date=dates_info.get("last"),
        percentile=round(percentile, 1),
        peak_hours=peak_hours,
        favorite_hour=favorite_hour,
        rival=rival,
        top_replies=top_replies,
        rankings=rankings,
        top_emotes=top_emotes
    )


async def get_leaderboard(period: str = "all", limit: int = 10) -> LeaderboardResponse:
    date_filter = get_date_filter(period)
    match_stage = date_filter if date_filter else {}

    pipeline = [
        {"$match": match_stage} if match_stage else {"$match": {}},
        {"$group": {
            "_id": "$username",
            "display_name": {"$last": "$display_name"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit}
    ]

    results = await db.messages.aggregate(pipeline).to_list(limit)

    count_pipeline = [
        {"$match": match_stage} if match_stage else {"$match": {}},
        {"$group": {"_id": None, "total_messages": {"$sum": 1}, "users": {"$addToSet": "$username"}}},
        {"$project": {"total_messages": 1, "total_users": {"$size": "$users"}}}
    ]
    totals = await db.messages.aggregate(count_pipeline).to_list(1)
    total_info = totals[0] if totals else {"total_messages": 0, "total_users": 0}

    leaderboard = [
        LeaderboardEntry(
            rank=i + 1,
            username=entry["_id"],
            display_name=entry["display_name"],
            message_count=entry["count"]
        )
        for i, entry in enumerate(results)
    ]

    return LeaderboardResponse(
        period=period,
        total_users=total_info.get("total_users", 0),
        total_messages=total_info.get("total_messages", 0),
        leaderboard=leaderboard
    )


async def get_user_percentile(username: str, period: str) -> float:
    """Calculate what % of users this user has more messages than"""
    date_filter = get_date_filter(period)
    match_stage = date_filter if date_filter else {}

    # Get all users' message counts (limited for performance)
    pipeline = [
        {"$match": match_stage} if match_stage else {"$match": {}},
        {"$group": {"_id": "$username", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": MAX_USERS_QUERY}
    ]
    all_users = await db.messages.aggregate(pipeline).to_list(MAX_USERS_QUERY)

    if not all_users:
        return 0.0

    # Find this user's count
    user_count = 0
    for user in all_users:
        if user["_id"] == username.lower():
            user_count = user["count"]
            break

    if user_count == 0:
        return 0.0

    # Count users with fewer messages
    below_count = sum(1 for user in all_users if user["count"] < user_count)
    total_users = len(all_users)

    return (below_count / total_users) * 100 if total_users > 0 else 0.0


def get_peak_hours(hourly_activity: list[HourlyActivity]) -> list[int]:
    """Find top 3 consecutive hours with most activity"""
    if not hourly_activity:
        return []

    counts = [h.count for h in hourly_activity]

    # Find the best window of 3 consecutive hours
    best_sum = 0
    best_start = 0

    for start in range(24):
        # Handle wrap-around (23, 0, 1)
        window_sum = sum(counts[(start + i) % 24] for i in range(3))
        if window_sum > best_sum:
            best_sum = window_sum
            best_start = start

    if best_sum == 0:
        return []

    return [(best_start + i) % 24 for i in range(3)]


async def get_rival(username: str, hourly_pattern: list[HourlyActivity], period: str) -> RivalInfo | None:
    """Find user with most similar hourly activity pattern using cosine similarity"""
    date_filter = get_date_filter(period)
    match_stage = date_filter if date_filter else {}

    # Get hourly patterns for top users only (limited for performance)
    pipeline = [
        {"$match": match_stage} if match_stage else {"$match": {}},
        {"$group": {
            "_id": {"username": "$username", "hour": "$hour"},
            "display_name": {"$last": "$display_name"},
            "count": {"$sum": 1}
        }},
        {"$group": {
            "_id": "$_id.username",
            "display_name": {"$last": "$display_name"},
            "hours": {"$push": {"hour": "$_id.hour", "count": "$count"}},
            "total": {"$sum": "$count"}
        }},
        {"$sort": {"total": -1}},
        {"$limit": MAX_USERS_QUERY}
    ]

    all_users = await db.messages.aggregate(pipeline).to_list(MAX_USERS_QUERY)

    if not all_users:
        return None

    # Build user's pattern vector
    user_vector = [h.count for h in hourly_pattern]
    user_magnitude = math.sqrt(sum(x * x for x in user_vector))

    if user_magnitude == 0:
        return None

    best_rival = None
    best_similarity = -1

    for other_user in all_users:
        if other_user["_id"] == username.lower():
            continue

        # Build other user's pattern vector
        other_hours = {h["hour"]: h["count"] for h in other_user["hours"]}
        other_vector = [other_hours.get(i, 0) for i in range(24)]
        other_magnitude = math.sqrt(sum(x * x for x in other_vector))

        if other_magnitude == 0:
            continue

        # Cosine similarity
        dot_product = sum(a * b for a, b in zip(user_vector, other_vector))
        similarity = (dot_product / (user_magnitude * other_magnitude)) * 100

        if similarity > best_similarity:
            best_similarity = similarity
            best_rival = RivalInfo(
                username=other_user["_id"],
                display_name=other_user["display_name"],
                similarity_score=round(similarity, 1)
            )

    return best_rival


async def get_top_replies(username: str, period: str, limit: int = 5) -> list[ReplyTarget]:
    """Find users this person 'replies' to most (their message within 10s of the other's)"""
    date_filter = get_date_filter(period)

    # Get user's messages with timestamps
    user_match = {"username": username.lower()}
    if date_filter:
        user_match.update(date_filter)

    # Limit to recent messages for performance
    user_messages = await db.messages.find(user_match).sort("timestamp", -1).limit(MAX_MESSAGES_QUERY).to_list(MAX_MESSAGES_QUERY)

    if not user_messages:
        return []

    reply_counts: dict[str, dict] = {}

    for msg in user_messages:
        msg_time = msg["timestamp"]
        # Find messages from other users in the 10 seconds before this message
        window_start = msg_time - timedelta(seconds=10)

        previous_messages = await db.messages.find({
            "username": {"$ne": username.lower()},
            "timestamp": {"$gte": window_start, "$lt": msg_time}
        }).limit(50).to_list(50)

        for prev_msg in previous_messages:
            other_username = prev_msg["username"]
            if other_username not in reply_counts:
                reply_counts[other_username] = {
                    "display_name": prev_msg.get("display_name", other_username),
                    "count": 0
                }
            reply_counts[other_username]["count"] += 1

    # Sort by count and take top N
    sorted_replies = sorted(reply_counts.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]

    return [
        ReplyTarget(
            username=username,
            display_name=data["display_name"],
            reply_count=data["count"]
        )
        for username, data in sorted_replies
    ]


async def get_rising_stars(limit: int = 10) -> list[RisingStarEntry]:
    """Users with biggest growth: last 7 days vs previous 7 days"""
    now = datetime.now(timezone.utc)
    last_week = now - timedelta(days=7)
    prev_week = now - timedelta(days=14)

    pipeline = [
        {"$facet": {
            "current": [
                {"$match": {"timestamp": {"$gte": last_week}}},
                {"$group": {
                    "_id": "$username",
                    "display_name": {"$last": "$display_name"},
                    "count": {"$sum": 1}
                }}
            ],
            "previous": [
                {"$match": {"timestamp": {"$gte": prev_week, "$lt": last_week}}},
                {"$group": {
                    "_id": "$username",
                    "count": {"$sum": 1}
                }}
            ]
        }}
    ]

    results = await db.messages.aggregate(pipeline).to_list(1)
    if not results:
        return []

    result = results[0]
    current_map = {u["_id"]: u for u in result["current"]}
    previous_map = {u["_id"]: u["count"] for u in result["previous"]}

    growth_data = []
    for username, data in current_map.items():
        current_count = data["count"]
        previous_count = previous_map.get(username, 0)

        if previous_count == 0:
            # New user or no previous activity - use current count as growth %
            growth_percent = current_count * 10.0  # Boost new active users
        else:
            growth_percent = ((current_count - previous_count) / previous_count) * 100

        growth_data.append({
            "username": username,
            "display_name": data["display_name"],
            "current_count": current_count,
            "previous_count": previous_count,
            "growth_percent": growth_percent
        })

    # Sort by growth percentage (descending) and take top N
    growth_data.sort(key=lambda x: x["growth_percent"], reverse=True)
    top_growth = growth_data[:limit]

    return [
        RisingStarEntry(
            rank=i + 1,
            username=entry["username"],
            display_name=entry["display_name"],
            current_count=entry["current_count"],
            previous_count=entry["previous_count"],
            growth_percent=round(entry["growth_percent"], 1)
        )
        for i, entry in enumerate(top_growth)
    ]


async def get_hour_leaders() -> list[HourLeaderEntry]:
    """Top chatter for each of the 24 hours"""
    pipeline = [
        {"$group": {
            "_id": {"hour": "$hour", "username": "$username"},
            "display_name": {"$last": "$display_name"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$group": {
            "_id": "$_id.hour",
            "top_user": {"$first": "$_id.username"},
            "display_name": {"$first": "$display_name"},
            "count": {"$first": "$count"}
        }},
        {"$sort": {"_id": 1}}
    ]

    results = await db.messages.aggregate(pipeline).to_list(24)

    return [
        HourLeaderEntry(
            hour=entry["_id"],
            username=entry["top_user"],
            display_name=entry["display_name"],
            message_count=entry["count"]
        )
        for entry in results
    ]


async def get_top_writers(limit: int = 10) -> list[WriterEntry]:
    """Users with longest average message length (min 10 messages)"""
    pipeline = [
        {"$group": {
            "_id": "$username",
            "display_name": {"$last": "$display_name"},
            "avg_length": {"$avg": {"$strLenCP": "$message"}},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gte": 10}}},  # Minimum 10 messages
        {"$sort": {"avg_length": -1}},
        {"$limit": limit}
    ]

    results = await db.messages.aggregate(pipeline).to_list(limit)

    return [
        WriterEntry(
            rank=i + 1,
            username=entry["_id"],
            display_name=entry["display_name"],
            avg_length=round(entry["avg_length"], 1),
            message_count=entry["count"]
        )
        for i, entry in enumerate(results)
    ]


async def get_active_chatters(min_messages: int = 5, minutes: int = 5) -> tuple[list[ActiveChatter], int]:
    """Get users who sent more than min_messages in the last N minutes"""
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=minutes)

    pipeline = [
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {
            "_id": "$username",
            "display_name": {"$last": "$display_name"},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gte": min_messages}}},
        {"$sort": {"count": -1}}
    ]

    results = await db.messages.aggregate(pipeline).to_list(None)

    # Get overall leaderboard ranks for active chatters
    rank_pipeline = [
        {"$group": {"_id": "$username", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": MAX_USERS_QUERY}
    ]
    all_users = await db.messages.aggregate(rank_pipeline).to_list(MAX_USERS_QUERY)
    total_users = len(all_users)

    # Build rank lookup
    rank_map = {user["_id"]: i + 1 for i, user in enumerate(all_users)}

    chatters = [
        ActiveChatter(
            username=entry["_id"],
            display_name=entry["display_name"],
            message_count=entry["count"],
            rank=rank_map.get(entry["_id"])
        )
        for entry in results
    ]
    return chatters, total_users


async def get_user_comparison(user1: str, user2: str, period: str = "all") -> tuple[UserStats | None, UserStats | None]:
    """Get stats for two users for comparison"""
    stats1 = await get_user_stats(user1, period)
    stats2 = await get_user_stats(user2, period)
    return stats1, stats2


async def search_users(query: str, limit: int = 10) -> list[UserSearchResult]:
    """Search users by username prefix"""
    if not query or len(query) < 2:
        return []

    # Escape special regex characters and create case-insensitive prefix match
    escaped_query = re.escape(query.lower())

    pipeline = [
        {"$match": {"username": {"$regex": f"^{escaped_query}", "$options": "i"}}},
        {"$group": {
            "_id": "$username",
            "display_name": {"$last": "$display_name"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit}
    ]

    results = await db.messages.aggregate(pipeline).to_list(limit)

    return [
        UserSearchResult(
            username=entry["_id"],
            display_name=entry["display_name"],
            total_messages=entry["count"]
        )
        for entry in results
    ]


async def get_user_rankings(username: str, period: str) -> UserRankings:
    """Get user's position in various leaderboards"""
    date_filter = get_date_filter(period)
    match_stage = date_filter if date_filter else {}
    username_lower = username.lower()

    # Get top rank (position in message count leaderboard, limited)
    top_pipeline = [
        {"$match": match_stage} if match_stage else {"$match": {}},
        {"$group": {"_id": "$username", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": MAX_USERS_QUERY}
    ]
    all_users = await db.messages.aggregate(top_pipeline).to_list(MAX_USERS_QUERY)

    top_rank = None
    for i, user in enumerate(all_users):
        if user["_id"] == username_lower:
            top_rank = i + 1
            break

    # Get rank change vs last week
    top_rank_change = None
    if top_rank is not None:
        now = datetime.now(timezone.utc)
        last_week = now - timedelta(days=7)
        prev_week = now - timedelta(days=14)

        # Get rank from last week
        prev_pipeline = [
            {"$match": {"timestamp": {"$gte": prev_week, "$lt": last_week}}},
            {"$group": {"_id": "$username", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": MAX_USERS_QUERY}
        ]
        prev_users = await db.messages.aggregate(prev_pipeline).to_list(MAX_USERS_QUERY)

        prev_rank = None
        for i, user in enumerate(prev_users):
            if user["_id"] == username_lower:
                prev_rank = i + 1
                break

        if prev_rank is not None:
            top_rank_change = prev_rank - top_rank  # Positive = improved

    # Get rising stars rank
    rising_entries = await get_rising_stars(limit=100)
    rising_rank = None
    for entry in rising_entries:
        if entry.username == username_lower:
            rising_rank = entry.rank
            break

    # Get writers rank
    writers_pipeline = [
        {"$group": {
            "_id": "$username",
            "avg_length": {"$avg": {"$strLenCP": "$message"}},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gte": 10}}},
        {"$sort": {"avg_length": -1}},
        {"$limit": MAX_USERS_QUERY}
    ]
    writers = await db.messages.aggregate(writers_pipeline).to_list(MAX_USERS_QUERY)

    writers_rank = None
    for i, user in enumerate(writers):
        if user["_id"] == username_lower:
            writers_rank = i + 1
            break

    # Get hours dominated
    hour_leaders = await get_hour_leaders()
    hours_dominated = [entry.hour for entry in hour_leaders if entry.username == username_lower]

    return UserRankings(
        top_rank=top_rank,
        top_rank_change=top_rank_change,
        rising_rank=rising_rank,
        writers_rank=writers_rank,
        hours_dominated=hours_dominated
    )


async def get_chat_activity_today() -> tuple[list[ChatActivityPoint], int, int, int]:
    """Get chat activity for the last 24 hours"""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    pipeline = [
        {"$match": {"timestamp": {"$gte": last_24h}}},
        {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]

    results = await db.messages.aggregate(pipeline).to_list(24)

    hourly_map = {r["_id"]: r["count"] for r in results}
    activity = [
        ChatActivityPoint(hour=h, count=hourly_map.get(h, 0))
        for h in range(24)
    ]

    total_today = sum(a.count for a in activity)

    peak_hour = 0
    peak_count = 0
    for a in activity:
        if a.count > peak_count:
            peak_count = a.count
            peak_hour = a.hour

    return activity, total_today, peak_hour, peak_count


async def get_overall_hourly_activity() -> tuple[list[ChatActivityPoint], int, int, int]:
    """Get overall chat activity by hour (all time)"""
    pipeline = [
        {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]

    results = await db.messages.aggregate(pipeline).to_list(24)

    hourly_map = {r["_id"]: r["count"] for r in results}
    activity = [
        ChatActivityPoint(hour=h, count=hourly_map.get(h, 0))
        for h in range(24)
    ]

    total_messages = sum(a.count for a in activity)

    peak_hour = 0
    peak_count = 0
    for a in activity:
        if a.count > peak_count:
            peak_count = a.count
            peak_hour = a.hour

    return activity, total_messages, peak_hour, peak_count


async def get_user_top_emotes(username: str, limit: int = 5) -> list[EmoteUsage]:
    """Get top emotes used by a specific user in the last 30 days"""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    messages = await db.messages.find({
        "username": username.lower(),
        "timestamp": {"$gte": thirty_days_ago}
    }).limit(MAX_MESSAGES_QUERY).to_list(MAX_MESSAGES_QUERY)

    message_texts = [msg["message"] for msg in messages]
    return await count_emotes_in_messages(message_texts, limit)


async def get_chat_top_emotes(limit: int = 5) -> tuple[list[EmoteUsage], int]:
    """Get top emotes used in chat overall in the last 30 days"""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Sample messages for performance (get most recent ones)
    messages = await db.messages.find({
        "timestamp": {"$gte": thirty_days_ago}
    }).sort("timestamp", -1).limit(MAX_MESSAGES_QUERY).to_list(MAX_MESSAGES_QUERY)

    message_texts = [msg["message"] for msg in messages]
    emotes = await count_emotes_in_messages(message_texts, limit)

    total = sum(e.count for e in emotes)
    return emotes, total


async def get_unique_chatters_by_hour() -> tuple[list[ChatActivityPoint], int, int, int]:
    """Get unique chatters per hour for the last 24 hours"""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    pipeline = [
        {"$match": {"timestamp": {"$gte": last_24h}}},
        {"$group": {
            "_id": {"hour": "$hour", "username": "$username"}
        }},
        {"$group": {
            "_id": "$_id.hour",
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]

    results = await db.messages.aggregate(pipeline).to_list(24)

    hourly_map = {r["_id"]: r["count"] for r in results}
    activity = [
        ChatActivityPoint(hour=h, count=hourly_map.get(h, 0))
        for h in range(24)
    ]

    total_unique = sum(a.count for a in activity)

    peak_hour = 0
    peak_count = 0
    for a in activity:
        if a.count > peak_count:
            peak_count = a.count
            peak_hour = a.hour

    return activity, total_unique, peak_hour, peak_count
