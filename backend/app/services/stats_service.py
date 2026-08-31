from datetime import datetime, timedelta, timezone
import asyncio
import math
import re
from app.database import db
from app.config import get_settings
import httpx
from app.models.schemas import (
    UserStats, HourlyActivity, LeaderboardResponse, LeaderboardEntry, RecentMessage,
    RivalInfo, ReplyTarget, ActiveChatter, RisingStarEntry, HourLeaderEntry, WriterEntry,
    UserSearchResult, UserRankings, ChatActivityPoint, FavoriteHour, EmoteUsage,
    PastUsername, UsernameHistoryResponse, EmotePositionData, UserEmotePosition,
    EmotePositionUserEntry, UserCoreResponse, UserActivityResponse,
    UserRankingsOnlyResponse, UserSocialResponse, UserEmotesResponse,
    UserRecentResponse, UserSmokeOnlyResponse, RandomMessageItem,
    PererecoesEntry, PererecoesResponse, PererecoesBreakdown,
    DuasCarasEntry, DuasCarasResponse,
)

# Cache for 7TV emotes
_7tv_emotes_cache: dict[str, str] | None = None
_7tv_cache_time: datetime | None = None

from app.services.common.cache import (
    HEAVY_STATS_CACHE_TTL_SECONDS,
    RANK_CACHE_TTL_SECONDS,
    _rank_cache,
    _get_stats_cache,
    _set_stats_cache,
    _stats_cache_key,
    invalidate_rank_cache as _invalidate_rank_cache_common,
)
from app.services.common.query import (
    BOT_FILTER,
    IGNORED_BOTS,
    NOT_REMOVED,
    VALID_PLATFORMS,
    build_base_match,
    get_date_filter,
    get_platform_filter,
    merge_queries,
)

# Whether pre-aggregated counters are populated (avoids repeated count queries)
_aggregates_ready_cache: tuple[bool, datetime] | None = None
AGGREGATES_READY_TTL_SECONDS = 60

# HTTP client timeout (seconds)
HTTP_TIMEOUT = 10.0

# Database query limits
MAX_USERS_QUERY = 1000
MAX_MESSAGES_QUERY = 10000

RIBBITS_CONTEXT = 20


def invalidate_rank_cache() -> None:
    """Clear cached rank map + expensive stats after aggregate maintenance."""
    _invalidate_rank_cache_common()


USER_GROUP_FIELDS = {
    "_id": {
        "platform": "$_platform",
        "username": "$username",
    },
    "display_name": {"$last": "$display_name"},
    "count": {"$sum": 1},
}

ACTIVE_CHATTER_GROUP_FIELDS = {
    "_id": {
        "platform": "$_platform",
        "user_id": {"$ifNull": ["$user_id", "$username"]},
        "username": "$username",
    },
    "display_name": {"$last": "$display_name"},
    "count": {"$sum": 1},
}

NORMALIZE_PLATFORM_STAGE = {
    "$addFields": {"_platform": {"$ifNull": ["$platform", "twitch"]}}
}


def get_query_timeout() -> int:
    """Get MongoDB query timeout from settings"""
    settings = get_settings()
    return settings.mongodb_timeout_ms


async def aggregates_ready() -> bool:
    """True when user_totals has been backfilled or populated by live inserts."""
    global _aggregates_ready_cache
    now = datetime.now(timezone.utc)
    if _aggregates_ready_cache and (now - _aggregates_ready_cache[1]).total_seconds() < AGGREGATES_READY_TTL_SECONDS:
        return _aggregates_ready_cache[0]
    count = await db.user_totals.estimated_document_count()
    ready = count > 0
    _aggregates_ready_cache = (ready, now)
    return ready


async def aggregate_with_timeout(collection, pipeline, limit=None):
    """Execute aggregation with server-side timeout"""
    timeout_ms = get_query_timeout()
    cursor = collection.aggregate(
        pipeline,
        maxTimeMS=timeout_ms,
        allowDiskUse=True,
    )
    if limit:
        return await cursor.to_list(limit)
    return await cursor.to_list(None)


async def get_rank_map(platform: str = "all") -> tuple[dict[str, int], int]:
    """Cached leaderboard rank lookup for active chatters."""
    now = datetime.now(timezone.utc)
    cached = _rank_cache.get(platform)
    if cached and (now - cached[2]).total_seconds() < RANK_CACHE_TTL_SECONDS:
        return cached[0], cached[1]

    if await aggregates_ready():
        from app.services.stats_aggregates import get_rank_map_from_totals
        rank_map, total_users = await get_rank_map_from_totals(platform, MAX_USERS_QUERY)
    else:
        rank_pipeline = [
            {"$match": merge_queries(BOT_FILTER, get_platform_filter(platform))},
            NORMALIZE_PLATFORM_STAGE,
            {
                "$group": {
                    "_id": {
                        "platform": "$_platform",
                        "user_id": {"$ifNull": ["$user_id", "$username"]},
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": MAX_USERS_QUERY},
        ]
        all_users = await aggregate_with_timeout(db.messages, rank_pipeline, MAX_USERS_QUERY)
        rank_map = {
            f"{user['_id'].get('platform', 'twitch')}:{str(user['_id']['user_id'])}": i + 1
            for i, user in enumerate(all_users)
        }
        total_users = len(all_users)

    _rank_cache[platform] = (rank_map, total_users, now)
    return rank_map, total_users


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


from app.services.users.identity import (
    get_user_query,
    resolve_user_id,
    resolve_user_identity,
    resolve_username,
)


async def get_user_stats(
    username: str,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> UserStats | None:
    # Don't return stats for ignored bots
    if username.lower() in IGNORED_BOTS:
        return None

    user_id, user_platform = await resolve_user_identity(username, platform)
    if user_platform is None:
        return None

    user_query = get_user_query(username, user_id, user_platform)

    date_filter = get_date_filter(period, start_date, end_date)
    match_stage = merge_queries(user_query, date_filter) if date_filter else user_query

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
        merge_queries(user_query, NOT_REMOVED)
    ).sort("timestamp", -1).limit(10).to_list(10)

    recent_messages = [
        RecentMessage(
            message=doc["message"],
            timestamp=doc["timestamp"],
            platform=doc.get("platform", "twitch"),
        )
        for doc in recent_docs
    ]

    # Calculate new fields (pass user_id for consistent lookups)
    percentile = await get_user_percentile(
        username, period, user_id, user_platform, start_date=start_date, end_date=end_date
    )
    peak_hours = get_peak_hours(hourly_activity)
    rival = await get_rival(
        username, hourly_activity, period, user_id, user_platform,
        start_date=start_date, end_date=end_date,
    )
    top_replies = await get_top_replies(
        username, period, limit=5, user_id=user_id, platform=user_platform,
        start_date=start_date, end_date=end_date,
    )
    rankings = await get_user_rankings(
        username, period, user_id, user_platform,
        start_date=start_date, end_date=end_date,
    )
    top_emotes = await get_user_top_emotes(
        username, limit=10, user_id=user_id, platform=user_platform,
        period=period, start_date=start_date, end_date=end_date,
    )
    emote_position = await get_user_emote_position(
        username, user_id=user_id, platform=user_platform,
        period=period, start_date=start_date, end_date=end_date,
    )

    from app.services.smoke_service import get_user_smoke_stats
    smoke_stats = await get_user_smoke_stats(username, user_id=user_id, platform=user_platform)

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
        platform=user_platform,
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
        top_emotes=top_emotes,
        emote_position=emote_position,
        smoke_stats=smoke_stats,
    )


def _favorite_hour_from_activity(hourly_activity: list[HourlyActivity], total: int) -> FavoriteHour | None:
    if total <= 0:
        return None
    max_hour = max(hourly_activity, key=lambda h: h.count)
    if max_hour.count <= 0:
        return None
    return FavoriteHour(
        hour=max_hour.hour,
        count=max_hour.count,
        percentage=round((max_hour.count / total) * 100, 1),
    )


def _hourly_from_totals_doc(doc: dict) -> tuple[list[HourlyActivity], int]:
    nested = doc.get("hourly") or {}
    hours = []
    total = int(doc.get("message_count", 0))
    for h in range(24):
        count = int(nested.get(str(h), nested.get(h, 0)) or 0)
        hours.append(HourlyActivity(hour=h, count=count))
    if total == 0:
        total = sum(h.count for h in hours)
    return hours, total


async def _percentile_from_totals(
    username: str, user_id: str | None, platform: str, message_count: int
) -> float:
    if message_count <= 0:
        return 0.0
    from app.services.stats_aggregates import get_rank_map_from_totals
    rank_map, total_users = await get_rank_map_from_totals(platform, MAX_USERS_QUERY)
    if total_users <= 0:
        return 0.0
    key = f"{platform}:{str(user_id)}" if user_id else None
    rank = rank_map.get(key) if key else None
    if rank is None:
        # Fallback: count how many have fewer messages
        match = {"platform": platform} if platform in VALID_PLATFORMS else {}
        below = await db.user_totals.count_documents({
            **match,
            "message_count": {"$lt": message_count},
        })
        return round((below / max(total_users, 1)) * 100, 1)
    # rank 1 = top; percentile = % of users with fewer messages
    below = total_users - rank
    return round((below / total_users) * 100, 1)


async def get_user_core(
    username: str,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> UserCoreResponse | None:
    """Fast user core stats. Uses user_totals for period=all when available."""
    if username.lower() in IGNORED_BOTS:
        return None

    cache_key = _stats_cache_key(
        "user_core",
        username=username.lower(),
        period=period,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
    )
    cached = _get_stats_cache(cache_key, ttl=300)
    if cached is not None:
        return cached

    user_id, user_platform = await resolve_user_identity(username, platform)
    if user_platform is None:
        return None

    # Fast path: period=all from pre-aggregated user_totals (no custom dates)
    if period == "all" and not start_date and await aggregates_ready():
        query = {"platform": user_platform}
        if user_id:
            query["user_id"] = str(user_id)
        else:
            query["username"] = username.lower()

        doc = await db.user_totals.find_one(query)
        if not doc and user_id:
            doc = await db.user_totals.find_one({
                "platform": user_platform,
                "username": username.lower(),
            })

        if doc:
            hourly_activity, total = _hourly_from_totals_doc(doc)
            if total > 0:
                percentile = await _percentile_from_totals(
                    username, str(doc.get("user_id") or user_id or ""), user_platform, total
                )
                result = UserCoreResponse(
                    username=username.lower(),
                    display_name=doc.get("display_name") or username,
                    platform=user_platform,
                    period=period,
                    total_messages=total,
                    percentile=percentile,
                    first_message_date=doc.get("first_message"),
                    last_message_date=doc.get("last_message"),
                    favorite_hour=_favorite_hour_from_activity(hourly_activity, total),
                    hourly_activity=hourly_activity,
                    peak_hours=get_peak_hours(hourly_activity),
                )
                _set_stats_cache(cache_key, result)
                return result

    # Fast path: day/week/month/custom from user_daily_stats
    from app.services.stats_aggregates import (
        resolve_period_dates,
        daily_stats_ready,
        get_user_period_from_daily,
        get_percentile_from_daily,
    )
    date_range = resolve_period_dates(period, start_date, end_date)
    if date_range and await daily_stats_ready():
        daily = await get_user_period_from_daily(
            user_platform,
            str(user_id or username.lower()),
            username,
            period,
            start_date=start_date,
            end_date=end_date,
        )
        if daily:
            hourly_activity, total = _hourly_from_totals_doc(daily)
            if total > 0:
                percentile = await get_percentile_from_daily(
                    user_platform, total, period, start_date=start_date, end_date=end_date
                )
                result = UserCoreResponse(
                    username=username.lower(),
                    display_name=daily.get("display_name") or username,
                    platform=user_platform,
                    period=period,
                    total_messages=total,
                    percentile=percentile,
                    first_message_date=daily.get("first_message"),
                    last_message_date=daily.get("last_message"),
                    favorite_hour=_favorite_hour_from_activity(hourly_activity, total),
                    hourly_activity=hourly_activity,
                    peak_hours=get_peak_hours(hourly_activity),
                )
                _set_stats_cache(cache_key, result)
                return result

    # Fallback: light facet on chat_messages
    user_query = get_user_query(username, user_id, user_platform)
    date_filter = get_date_filter(period, start_date, end_date)
    match_stage = merge_queries(user_query, date_filter) if date_filter else user_query

    pipeline = [
        {"$match": match_stage},
        {"$facet": {
            "total": [{"$count": "count"}],
            "hourly": [
                {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ],
            "dates": [
                {"$group": {
                    "_id": None,
                    "first": {"$min": "$timestamp"},
                    "last": {"$max": "$timestamp"},
                    "display_name": {"$last": "$display_name"},
                }}
            ],
        }},
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
    percentile = await get_user_percentile(
        username, period, user_id, user_platform, start_date=start_date, end_date=end_date
    )

    core = UserCoreResponse(
        username=username.lower(),
        display_name=dates_info.get("display_name", username),
        platform=user_platform,
        period=period,
        total_messages=total,
        percentile=round(percentile, 1),
        first_message_date=dates_info.get("first"),
        last_message_date=dates_info.get("last"),
        favorite_hour=_favorite_hour_from_activity(hourly_activity, total),
        hourly_activity=hourly_activity,
        peak_hours=get_peak_hours(hourly_activity),
    )
    _set_stats_cache(cache_key, core)
    return core


async def get_user_activity(
    username: str,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> UserActivityResponse | None:
    cache_key = _stats_cache_key(
        "user_activity",
        username=username.lower(),
        period=period,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
    )
    cached = _get_stats_cache(cache_key, ttl=900)
    if cached is not None:
        return cached

    core = await get_user_core(username, period, platform, start_date=start_date, end_date=end_date)
    if not core:
        return None

    result = UserActivityResponse(
        hourly_activity=core.hourly_activity,
        peak_hours=core.peak_hours,
        favorite_hour=core.favorite_hour,
    )
    _set_stats_cache(cache_key, result)
    return result


async def get_user_rankings_section(
    username: str,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> UserRankingsOnlyResponse | None:
    if username.lower() in IGNORED_BOTS:
        return None

    cache_key = _stats_cache_key(
        "user_rankings",
        username=username.lower(),
        period=period,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
    )
    cached = _get_stats_cache(cache_key, ttl=1800)
    if cached is not None:
        return cached

    user_id, user_platform = await resolve_user_identity(username, platform)
    if user_platform is None:
        return None

    rankings = await get_user_rankings(
        username, period, user_id, user_platform, start_date=start_date, end_date=end_date
    )
    result = UserRankingsOnlyResponse(rankings=rankings)
    _set_stats_cache(cache_key, result)
    return result


async def get_user_social(
    username: str,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> UserSocialResponse | None:
    if username.lower() in IGNORED_BOTS:
        return None

    cache_key = _stats_cache_key(
        "user_social",
        username=username.lower(),
        period=period,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
    )
    cached = _get_stats_cache(cache_key, ttl=1800)
    if cached is not None:
        return cached

    user_id, user_platform = await resolve_user_identity(username, platform)
    if user_platform is None:
        return None

    # Need hourly pattern for rival — reuse core
    core = await get_user_core(username, period, platform, start_date=start_date, end_date=end_date)
    if not core:
        return None

    rival = await get_rival(
        username, core.hourly_activity, period, user_id, user_platform,
        start_date=start_date, end_date=end_date,
    )
    top_replies = await get_top_replies(
        username, period, limit=5, user_id=user_id, platform=user_platform,
        start_date=start_date, end_date=end_date,
    )
    result = UserSocialResponse(rival=rival, top_replies=top_replies)
    _set_stats_cache(cache_key, result)
    return result


async def get_user_emotes_section(
    username: str,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> UserEmotesResponse | None:
    if username.lower() in IGNORED_BOTS:
        return None

    cache_key = _stats_cache_key(
        "user_emotes",
        username=username.lower(),
        period=period,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
    )
    cached = _get_stats_cache(cache_key, ttl=900)
    if cached is not None:
        return cached

    user_id, user_platform = await resolve_user_identity(username, platform)
    if user_platform is None:
        return None

    top_emotes = await get_user_top_emotes(
        username, limit=10, user_id=user_id, platform=user_platform,
        period=period, start_date=start_date, end_date=end_date,
    )
    emote_position = await get_user_emote_position(
        username, user_id=user_id, platform=user_platform,
        period=period, start_date=start_date, end_date=end_date,
    )
    result = UserEmotesResponse(top_emotes=top_emotes, emote_position=emote_position)
    _set_stats_cache(cache_key, result)
    return result


async def get_user_recent(
    username: str, platform: str = "all"
) -> UserRecentResponse | None:
    if username.lower() in IGNORED_BOTS:
        return None

    cache_key = _stats_cache_key("user_recent", username=username.lower(), platform=platform)
    cached = _get_stats_cache(cache_key, ttl=120)
    if cached is not None:
        return cached

    user_id, user_platform = await resolve_user_identity(username, platform)
    if user_platform is None:
        return None

    user_query = get_user_query(username, user_id, user_platform)
    recent_docs = await db.messages.find(
        merge_queries(user_query, NOT_REMOVED)
    ).sort("timestamp", -1).limit(10).to_list(10)
    recent_messages = [
        RecentMessage(
            message=doc["message"],
            timestamp=doc["timestamp"],
            platform=doc.get("platform", "twitch"),
        )
        for doc in recent_docs
    ]
    result = UserRecentResponse(recent_messages=recent_messages)
    _set_stats_cache(cache_key, result)
    return result


async def get_user_smoke_section(
    username: str, platform: str = "all"
) -> UserSmokeOnlyResponse | None:
    if username.lower() in IGNORED_BOTS:
        return None

    cache_key = _stats_cache_key("user_smoke", username=username.lower(), platform=platform)
    cached = _get_stats_cache(cache_key, ttl=900)
    if cached is not None:
        return cached

    user_id, user_platform = await resolve_user_identity(username, platform)
    if user_platform is None:
        return None

    from app.services.smoke_service import get_user_smoke_stats
    smoke_stats = await get_user_smoke_stats(username, user_id=user_id, platform=user_platform)
    result = UserSmokeOnlyResponse(smoke_stats=smoke_stats)
    _set_stats_cache(cache_key, result)
    return result


async def get_leaderboard(
    period: str = "all",
    limit: int = 10,
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> LeaderboardResponse:
    from app.services.stats_aggregates import resolve_period_dates

    date_range = resolve_period_dates(period, start_date, end_date)
    if period == "all" and not date_range and await aggregates_ready():
        from app.services.stats_aggregates import get_leaderboard_from_totals
        entries, total_users, total_messages = await get_leaderboard_from_totals(platform, limit)
        leaderboard = [
            LeaderboardEntry(
                rank=i + 1,
                username=entry["username"],
                display_name=entry.get("display_name", entry["username"]),
                platform=entry.get("platform", "twitch"),
                message_count=entry["message_count"],
            )
            for i, entry in enumerate(entries)
        ]
        return LeaderboardResponse(
            period=period,
            platform=platform,
            total_users=total_users,
            total_messages=total_messages,
            leaderboard=leaderboard,
        )

    if date_range:
        start_ymd, end_ymd = date_range
        match: dict = {"date": {"$gte": start_ymd, "$lte": end_ymd}}
        if platform in ("twitch", "kick"):
            match["platform"] = platform
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {"platform": "$platform", "user_id": "$user_id"},
                    "username": {"$last": "$username"},
                    "display_name": {"$last": "$display_name"},
                    "count": {"$sum": "$message_count"},
                }
            },
            {"$sort": {"count": -1}},
            {
                "$facet": {
                    "leaderboard": [{"$limit": limit}],
                    "totals": [
                        {
                            "$group": {
                                "_id": None,
                                "total_users": {"$sum": 1},
                                "total_messages": {"$sum": "$count"},
                            }
                        }
                    ],
                }
            },
        ]
        results = await db.user_daily_stats.aggregate(pipeline).to_list(1)
        if results:
            result = results[0]
            entries = result.get("leaderboard", [])
            total_info = (result.get("totals") or [{}])[0]
            leaderboard = [
                LeaderboardEntry(
                    rank=i + 1,
                    username=e["username"],
                    display_name=e.get("display_name") or e["username"],
                    platform=e["_id"].get("platform", "twitch"),
                    message_count=int(e["count"]),
                )
                for i, e in enumerate(entries)
            ]
            return LeaderboardResponse(
                period=period,
                platform=platform,
                total_users=int(total_info.get("total_users", 0)),
                total_messages=int(total_info.get("total_messages", 0)),
                leaderboard=leaderboard,
            )

    match_stage = build_base_match(period, platform, start_date, end_date)

    pipeline = [
        {"$match": match_stage},
        NORMALIZE_PLATFORM_STAGE,
        {"$group": USER_GROUP_FIELDS},
        {"$sort": {"count": -1}},
        {"$facet": {
            "leaderboard": [{"$limit": limit}],
            "totals": [
                {"$group": {
                    "_id": None,
                    "total_users": {"$sum": 1},
                    "total_messages": {"$sum": "$count"},
                }}
            ],
        }},
    ]

    results = await aggregate_with_timeout(db.messages, pipeline, 1)
    if not results:
        return LeaderboardResponse(
            period=period,
            platform=platform,
            total_users=0,
            total_messages=0,
            leaderboard=[],
        )

    result = results[0]
    entries = result.get("leaderboard", [])
    total_info = result.get("totals", [{}])[0] if result.get("totals") else {}

    leaderboard = [
        LeaderboardEntry(
            rank=i + 1,
            username=entry["_id"]["username"],
            display_name=entry["display_name"],
            platform=entry["_id"].get("platform", "twitch"),
            message_count=entry["count"]
        )
        for i, entry in enumerate(entries)
    ]

    return LeaderboardResponse(
        period=period,
        platform=platform,
        total_users=total_info.get("total_users", 0),
        total_messages=total_info.get("total_messages", 0),
        leaderboard=leaderboard
    )


async def get_user_percentile(
    username: str,
    period: str,
    user_id: str | None = None,
    platform: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> float:
    """Calculate what % of users this user has more messages than"""
    match_stage = build_base_match(period, platform or "all", start_date, end_date)

    pipeline = [
        {"$match": match_stage},
        NORMALIZE_PLATFORM_STAGE,
        {"$group": USER_GROUP_FIELDS},
        {"$sort": {"count": -1}},
        {"$limit": MAX_USERS_QUERY}
    ]
    all_users = await aggregate_with_timeout(db.messages, pipeline, MAX_USERS_QUERY)

    if not all_users:
        return 0.0

    user_query = get_user_query(username, user_id, platform)
    date_filter = get_date_filter(period, start_date, end_date)
    user_match = merge_queries(user_query, date_filter) if date_filter else user_query

    user_count_result = await db.messages.count_documents(user_match)
    user_count = user_count_result if user_count_result else 0

    if user_count == 0:
        return 0.0

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


async def get_rival(
    username: str,
    hourly_pattern: list[HourlyActivity],
    period: str,
    user_id: str | None = None,
    platform: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> RivalInfo | None:
    """Find user with most similar hourly activity pattern using cosine similarity.

    period=all uses user_totals; day/week/month/custom use user_daily_stats when available.
    Falls back to a chat_messages aggregation only when aggregates are missing.
    """
    user_vector = [h.count for h in hourly_pattern]
    user_magnitude = math.sqrt(sum(x * x for x in user_vector))
    if user_magnitude == 0:
        return None

    username_lower = username.lower()
    plat = platform or "all"
    candidates: list[dict] = []

    # Fast path: all-time from user_totals (no custom dates)
    if period == "all" and not start_date and await aggregates_ready():
        from app.services.stats_aggregates import _totals_match
        match = _totals_match(plat if plat in VALID_PLATFORMS else "all")
        docs = await db.user_totals.find(match).sort("message_count", -1).limit(MAX_USERS_QUERY).to_list(MAX_USERS_QUERY)
        for doc in docs:
            nested = doc.get("hourly") or {}
            hours = [
                {"hour": h, "count": int(nested.get(str(h), nested.get(h, 0)) or 0)}
                for h in range(24)
            ]
            candidates.append({
                "_id": {
                    "username": doc["username"],
                    "platform": doc.get("platform", "twitch"),
                },
                "display_name": doc.get("display_name") or doc["username"],
                "hours": hours,
                "total": int(doc.get("message_count", 0)),
            })

    # Fast path: filtered periods from user_daily_stats
    else:
        from app.services.stats_aggregates import (
            daily_stats_ready,
            resolve_period_dates,
        )
        if await daily_stats_ready():
            date_range = resolve_period_dates(period, start_date, end_date)
            if date_range:
                range_start, range_end = date_range
                match: dict = {"date": {"$gte": range_start, "$lte": range_end}}
                if plat in VALID_PLATFORMS:
                    match["platform"] = plat
                pipeline = [
                    {"$match": match},
                    {
                        "$group": {
                            "_id": {"platform": "$platform", "user_id": "$user_id"},
                            "username": {"$last": "$username"},
                            "display_name": {"$last": "$display_name"},
                            "total": {"$sum": "$message_count"},
                            "hourlies": {"$push": "$hourly"},
                        }
                    },
                    {"$sort": {"total": -1}},
                    {"$limit": MAX_USERS_QUERY},
                ]
                rows = await db.user_daily_stats.aggregate(pipeline).to_list(MAX_USERS_QUERY)
                for row in rows:
                    hourly = {str(h): 0 for h in range(24)}
                    for nested in row.get("hourlies") or []:
                        if not isinstance(nested, dict):
                            continue
                        for h in range(24):
                            key = str(h)
                            hourly[key] += int(nested.get(key, nested.get(h, 0)) or 0)
                    candidates.append({
                        "_id": {
                            "username": row["username"],
                            "platform": row["_id"].get("platform", "twitch"),
                        },
                        "display_name": row.get("display_name") or row["username"],
                        "hours": [{"hour": h, "count": hourly[str(h)]} for h in range(24)],
                        "total": int(row["total"]),
                    })

    # Fallback: raw chat_messages aggregation
    if not candidates:
        match_stage = build_base_match(period, plat, start_date, end_date)
        pipeline = [
            {"$match": match_stage},
            {"$group": {
                "_id": {"username": "$username", "hour": "$hour", "platform": "$platform"},
                "display_name": {"$last": "$display_name"},
                "count": {"$sum": 1}
            }},
            {"$group": {
                "_id": {"username": "$_id.username", "platform": "$_id.platform"},
                "display_name": {"$last": "$display_name"},
                "hours": {"$push": {"hour": "$_id.hour", "count": "$count"}},
                "total": {"$sum": "$count"}
            }},
            {"$sort": {"total": -1}},
            {"$limit": MAX_USERS_QUERY}
        ]
        candidates = await db.messages.aggregate(pipeline).to_list(MAX_USERS_QUERY)

    if not candidates:
        return None

    best_rival = None
    best_similarity = -1

    for other_user in candidates:
        other_username = other_user["_id"]["username"]
        other_platform = other_user["_id"].get("platform", "twitch")
        if other_username == username_lower and (platform is None or other_platform == platform):
            continue

        other_hours = {h["hour"]: h["count"] for h in other_user["hours"]}
        other_vector = [other_hours.get(i, 0) for i in range(24)]
        other_magnitude = math.sqrt(sum(x * x for x in other_vector))

        if other_magnitude == 0:
            continue

        dot_product = sum(a * b for a, b in zip(user_vector, other_vector))
        similarity = (dot_product / (user_magnitude * other_magnitude)) * 100

        if similarity > best_similarity:
            best_similarity = similarity
            best_rival = RivalInfo(
                username=other_username,
                display_name=other_user["display_name"],
                platform=other_platform,
                similarity_score=round(similarity, 1)
            )

    return best_rival


# Sample size for reply detection — enough signal without N+1 scans
REPLY_SAMPLE_SIZE = 500
REPLY_WINDOW_SECONDS = 10
REPLY_OTHERS_LIMIT = 20000
REPLY_TAGGED_MIN = 3


def _aware_ts(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


async def _get_top_replies_from_tags(
    username: str,
    period: str,
    limit: int,
    user_id: str | None,
    platform: str | None,
    start_date: str | None,
    end_date: str | None,
) -> list[ReplyTarget]:
    """Aggregate who the user replied TO via stored reply_to_* fields."""
    user_query = get_user_query(username, user_id, platform)
    date_filter = get_date_filter(period, start_date, end_date)
    tagged_filter = {
        "$or": [
            {"reply_to_username": {"$exists": True, "$nin": [None, ""]}},
            {"reply_to_user_id": {"$exists": True, "$nin": [None, ""]}},
        ]
    }
    user_match = merge_queries(user_query, date_filter, tagged_filter)

    pipeline = [
        {"$match": user_match},
        {"$sort": {"timestamp": -1}},
        {"$limit": REPLY_SAMPLE_SIZE},
        {
            "$group": {
                "_id": {
                    "platform": {"$ifNull": ["$platform", "twitch"]},
                    "username": {
                        "$toLower": {
                            "$ifNull": ["$reply_to_username", "$reply_to_user_id"]
                        }
                    },
                },
                "display_name": {
                    "$last": {
                        "$ifNull": ["$reply_to_display_name", "$reply_to_username"]
                    }
                },
                "count": {"$sum": 1},
            }
        },
        {"$match": {"_id.username": {"$nin": [None, ""]}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    rows = await db.messages.aggregate(pipeline).to_list(limit)
    return [
        ReplyTarget(
            username=r["_id"]["username"],
            display_name=(r.get("display_name") or r["_id"]["username"]),
            platform=r["_id"].get("platform", "twitch"),
            reply_count=int(r["count"]),
        )
        for r in rows
        if r["_id"].get("username")
    ]


async def _get_top_replies_heuristic(
    username: str,
    period: str,
    limit: int,
    user_id: str | None,
    platform: str | None,
    start_date: str | None,
    end_date: str | None,
) -> list[ReplyTarget]:
    """Proximity heuristic: message within 10s after another user's message."""
    user_query = get_user_query(username, user_id, platform)
    date_filter = get_date_filter(period, start_date, end_date)
    user_match = merge_queries(user_query, date_filter) if date_filter else user_query

    user_messages = await db.messages.find(
        user_match,
        {"timestamp": 1, "platform": 1},
    ).sort("timestamp", -1).limit(REPLY_SAMPLE_SIZE).to_list(REPLY_SAMPLE_SIZE)

    if not user_messages:
        return []

    for msg in user_messages:
        msg["timestamp"] = _aware_ts(msg["timestamp"])

    min_ts = min(m["timestamp"] for m in user_messages) - timedelta(seconds=REPLY_WINDOW_SECONDS)
    max_ts = max(m["timestamp"] for m in user_messages)
    username_lower = username.lower()
    plat = platform or user_messages[0].get("platform", "twitch")

    others = await db.messages.find(
        merge_queries(
            BOT_FILTER,
            get_platform_filter(plat),
            {"username": {"$ne": username_lower}},
            {"timestamp": {"$gte": min_ts, "$lte": max_ts}},
        ),
        {"username": 1, "display_name": 1, "platform": 1, "timestamp": 1},
    ).sort("timestamp", 1).limit(REPLY_OTHERS_LIMIT).to_list(REPLY_OTHERS_LIMIT)

    for other in others:
        other["timestamp"] = _aware_ts(other["timestamp"])

    reply_counts: dict[str, dict] = {}
    user_sorted = sorted(user_messages, key=lambda m: m["timestamp"])
    j = 0
    n_others = len(others)

    for msg in user_sorted:
        msg_time = msg["timestamp"]
        window_start = msg_time - timedelta(seconds=REPLY_WINDOW_SECONDS)

        while j < n_others and others[j]["timestamp"] < window_start:
            j += 1

        k = j
        while k < n_others and others[k]["timestamp"] < msg_time:
            prev = others[k]
            other_username = prev["username"]
            msg_platform = prev.get("platform", "twitch")
            key = f"{msg_platform}:{other_username}"
            if key not in reply_counts:
                reply_counts[key] = {
                    "username": other_username,
                    "display_name": prev.get("display_name", other_username),
                    "platform": msg_platform,
                    "count": 0,
                }
            reply_counts[key]["count"] += 1
            k += 1

    sorted_replies = sorted(reply_counts.values(), key=lambda x: x["count"], reverse=True)[:limit]
    return [
        ReplyTarget(
            username=data["username"],
            display_name=data["display_name"],
            platform=data["platform"],
            reply_count=data["count"],
        )
        for data in sorted_replies
    ]


async def get_top_replies(
    username: str,
    period: str,
    limit: int = 5,
    user_id: str | None = None,
    platform: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[ReplyTarget]:
    """Find users this person replies to most.

    Prefers stored reply_to_* tags; falls back to the 10s proximity heuristic
    when fewer than REPLY_TAGGED_MIN tagged targets are available.
    """
    tagged = await _get_top_replies_from_tags(
        username, period, limit, user_id, platform, start_date, end_date,
    )
    if len(tagged) >= REPLY_TAGGED_MIN:
        return tagged

    return await _get_top_replies_heuristic(
        username, period, limit, user_id, platform, start_date, end_date,
    )


# Duas Caras lives in boards/duas_caras.py (registered via boards.registry)


async def get_duas_caras_leaderboard(platform: str = "all", limit: int = 10):
    from app.services.boards.duas_caras import get_duas_caras_leaderboard as _impl
    return await _impl(platform=platform, limit=limit)


async def _duas_caras_rank_for_user(username: str, user_id: str | None, platform: str):
    from app.services.boards.duas_caras import _duas_caras_rank_for_user as _impl
    return await _impl(username, user_id, platform)


async def get_rising_stars(
    limit: int = 10,
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[RisingStarEntry]:
    """Growth: selected range vs previous equal-length window (all => last 7 vs prev 7)."""
    from app.services.stats_aggregates import (
        resolve_period_dates,
        previous_equal_window,
    )

    cache_key = _stats_cache_key(
        "rising_stars", limit=limit, platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )
    cached = _get_stats_cache(cache_key)
    if cached is not None:
        return cached

    date_range = resolve_period_dates(period, start_date, end_date)
    if date_range:
        prev_ymd = previous_equal_window(*date_range)
        current_ymd = date_range
    else:
        today = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3))).date()
        current_ymd = ((today - timedelta(days=7)).isoformat(), today.isoformat())
        prev_ymd = previous_equal_window(*current_ymd)

    daily_match: dict = {
        "date": {"$gte": prev_ymd[0], "$lte": current_ymd[1]},
    }
    if platform in VALID_PLATFORMS:
        daily_match["platform"] = platform

    pipeline = [
        {"$match": daily_match},
        {"$facet": {
            "current": [
                {"$match": {"date": {"$gte": current_ymd[0], "$lte": current_ymd[1]}}},
                {"$group": {
                    "_id": {"platform": "$platform", "username": "$username"},
                    "display_name": {"$last": "$display_name"},
                    "count": {"$sum": "$message_count"}
                }}
            ],
            "previous": [
                {"$match": {"date": {"$gte": prev_ymd[0], "$lte": prev_ymd[1]}}},
                {"$group": {
                    "_id": {"platform": "$platform", "username": "$username"},
                    "count": {"$sum": "$message_count"}
                }}
            ]
        }}
    ]

    results = await db.user_daily_stats.aggregate(pipeline).to_list(1)
    if not results:
        return []

    result = results[0]

    def _rising_key(oid) -> tuple[str, str]:
        if isinstance(oid, dict):
            return (oid.get("platform") or "twitch", oid.get("username") or "")
        return ("twitch", str(oid))

    current_map = {_rising_key(u["_id"]): u for u in result["current"]}
    previous_map = {_rising_key(u["_id"]): u["count"] for u in result["previous"]}

    growth_data = []
    for user_key, data in current_map.items():
        current_count = data["count"]
        previous_count = previous_map.get(user_key, 0)

        if previous_count == 0:
            growth_percent = current_count * 10.0
        else:
            growth_percent = ((current_count - previous_count) / previous_count) * 100

        growth_data.append({
            "username": user_key[1],
            "platform": user_key[0],
            "display_name": data["display_name"],
            "current_count": current_count,
            "previous_count": previous_count,
            "growth_percent": growth_percent
        })

    growth_data.sort(key=lambda x: x["growth_percent"], reverse=True)
    top_growth = growth_data[:limit]

    result = [
        RisingStarEntry(
            rank=i + 1,
            username=entry["username"],
            display_name=entry["display_name"],
            platform=entry["platform"],
            current_count=entry["current_count"],
            previous_count=entry["previous_count"],
            growth_percent=round(entry["growth_percent"], 1)
        )
        for i, entry in enumerate(top_growth)
    ]
    _set_stats_cache(cache_key, result)
    return result


async def get_hour_leaders(
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[HourLeaderEntry]:
    """Top chatter for each of the 24 hours (optionally within a date range)."""
    from app.services.stats_aggregates import resolve_period_dates

    cache_key = _stats_cache_key(
        "hour_leaders", platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )
    cached = _get_stats_cache(cache_key)
    if cached is not None:
        return cached

    # Fast path: pre-aggregated user_daily_stats (~1s vs ~3s+ on raw messages)
    match: dict = {**BOT_FILTER}
    if platform in VALID_PLATFORMS:
        match["platform"] = platform
    date_range = resolve_period_dates(period, start_date, end_date)
    if date_range:
        match["date"] = {"$gte": date_range[0], "$lte": date_range[1]}

    pipeline = [
        {"$match": match},
        {
            "$project": {
                "platform": 1,
                "username": 1,
                "display_name": 1,
                "hourly": {"$objectToArray": {"$ifNull": ["$hourly", {}]}},
            }
        },
        {"$unwind": "$hourly"},
        {"$match": {"hourly.v": {"$gt": 0}}},
        {
            "$group": {
                "_id": {
                    "hour": "$hourly.k",
                    "platform": {"$ifNull": ["$platform", "twitch"]},
                    "username": "$username",
                },
                "display_name": {"$last": "$display_name"},
                "count": {"$sum": "$hourly.v"},
            }
        },
        {"$sort": {"count": -1}},
        {
            "$group": {
                "_id": "$_id.hour",
                "top_user": {"$first": "$_id.username"},
                "platform": {"$first": "$_id.platform"},
                "display_name": {"$first": "$display_name"},
                "count": {"$first": "$count"},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    results = await db.user_daily_stats.aggregate(pipeline, allowDiskUse=True).to_list(24)

    if not results:
        # Fallback to raw messages if daily aggregates are empty
        match_stage = build_base_match(period, platform, start_date, end_date)
        pipeline = [
            {"$match": match_stage},
            {"$group": {
                "_id": {"hour": "$hour", "platform": "$platform", "username": "$username"},
                "display_name": {"$last": "$display_name"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$group": {
                "_id": "$_id.hour",
                "top_user": {"$first": "$_id.username"},
                "platform": {"$first": "$_id.platform"},
                "display_name": {"$first": "$display_name"},
                "count": {"$first": "$count"}
            }},
            {"$sort": {"_id": 1}}
        ]
        results = await db.messages.aggregate(pipeline, allowDiskUse=True).to_list(24)

    result = []
    for entry in results:
        hour_raw = entry["_id"]
        try:
            hour = int(hour_raw)
        except (TypeError, ValueError):
            continue
        result.append(
            HourLeaderEntry(
                hour=hour,
                username=entry["top_user"],
                display_name=entry["display_name"],
                platform=entry.get("platform", "twitch"),
                message_count=int(entry["count"]),
            )
        )
    result.sort(key=lambda e: e.hour)
    _set_stats_cache(cache_key, result)
    return result


async def get_folhinha_commands_cached(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Cached wrapper around folhinha command token ranking."""
    from app.services.stats_aggregates import get_folhinha_commands

    cache_key = _stats_cache_key(
        "folhinha_commands",
        period=period,
        platform=platform,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )
    cached = _get_stats_cache(cache_key)
    if cached is not None:
        return cached
    rows = await get_folhinha_commands(
        period=period,
        platform=platform,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )
    _set_stats_cache(cache_key, rows)
    return rows


async def get_top_writers(
    limit: int = 10,
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[WriterEntry]:
    """Users with longest average message length / messages count ratio (min 20 messages)"""
    cache_key = _stats_cache_key(
        "top_writers", limit=limit, platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )
    cached = _get_stats_cache(cache_key)
    if cached is not None:
        return cached

    match_stage = build_base_match(period, platform, start_date, end_date)

    pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": {"platform": "$platform", "username": "$username"},
            "display_name": {"$last": "$display_name"},
            "avg_length": {"$avg": {"$strLenCP": "$message"}},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gte": 20}}},
        {"$addFields": {
            "score": {"$divide": ["$avg_length", "$count"]}
        }},
        {"$sort": {"score": -1}},
        {"$limit": limit}
    ]

    results = await db.messages.aggregate(pipeline).to_list(limit)

    result = [
        WriterEntry(
            rank=i + 1,
            username=entry["_id"]["username"],
            display_name=entry["display_name"],
            platform=entry["_id"].get("platform", "twitch"),
            avg_length=round(entry["avg_length"], 1),
            message_count=entry["count"],
            score=round(entry["score"], 4)
        )
        for i, entry in enumerate(results)
    ]
    _set_stats_cache(cache_key, result)
    return result


# Points / meta-board live in boards/pererecoes.py (driven by BoardSpec registry)
from app.services.boards.pererecoes import PERERECOES_POINTS  # noqa: F401


async def get_pererecoes_leaderboard(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
):
    from app.services.boards.pererecoes import get_pererecoes_leaderboard as _impl
    return await _impl(
        period=period, platform=platform, limit=limit,
        start_date=start_date, end_date=end_date,
    )


async def get_active_chatters(
    min_messages: int = 5, minutes: int = 5, platform: str = "all"
) -> tuple[list[ActiveChatter], int]:
    """Get users who sent more than min_messages in the last N minutes"""
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=minutes)

    pipeline = [
        {"$match": merge_queries(BOT_FILTER, get_platform_filter(platform), {"timestamp": {"$gte": since}})},
        NORMALIZE_PLATFORM_STAGE,
        {"$group": ACTIVE_CHATTER_GROUP_FIELDS},
        {"$match": {"count": {"$gte": min_messages}}},
        {"$sort": {"count": -1}},
        {"$limit": 100},
    ]

    results = await aggregate_with_timeout(db.messages, pipeline, 100)
    rank_map, total_users = await get_rank_map(platform)

    chatters = [
        ActiveChatter(
            username=entry["_id"]["username"],
            display_name=entry["display_name"],
            platform=entry["_id"].get("platform", "twitch"),
            message_count=entry["count"],
            rank=rank_map.get(
                f"{entry['_id'].get('platform', 'twitch')}:{str(entry['_id']['user_id'])}"
            ),
        )
        for entry in results
    ]
    return chatters, total_users


async def get_compare_snapshot(
    username: str,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> UserStats | None:
    """Lean profile snapshot for side-by-side comparison."""
    username_lower = username.lower().strip()
    if username_lower in IGNORED_BOTS:
        return None

    platforms = [platform] if platform in VALID_PLATFORMS else ["all", "twitch", "kick"]
    core = None
    for candidate_platform in platforms:
        core = await get_user_core(
            username_lower,
            period,
            candidate_platform,
            start_date,
            end_date,
        )
        if core is not None:
            break

    if core is None:
        return None

    user_id, _ = await resolve_user_identity(core.username, core.platform)
    rankings_task = get_user_rankings(
        core.username,
        period,
        user_id,
        core.platform,
        start_date=start_date,
        end_date=end_date,
    )
    top_emotes_task = get_user_top_emotes(
        core.username,
        limit=5,
        user_id=user_id,
        platform=core.platform,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    from app.services.smoke_service import get_user_smoke_stats
    smoke_task = get_user_smoke_stats(core.username, user_id=user_id, platform=core.platform)

    rankings, top_emotes, smoke_stats = await asyncio.gather(
        rankings_task,
        top_emotes_task,
        smoke_task,
    )
    if rankings and smoke_stats:
        rankings.smoke_rank = rankings.smoke_rank or smoke_stats.rank
        rankings.smoke_count = rankings.smoke_count if rankings.smoke_count is not None else smoke_stats.count

    return UserStats(
        username=core.username,
        display_name=core.display_name,
        platform=core.platform,
        period=core.period,
        total_messages=core.total_messages,
        hourly_activity=[],
        recent_messages=[],
        first_message_date=core.first_message_date,
        last_message_date=core.last_message_date,
        percentile=core.percentile,
        peak_hours=core.peak_hours,
        favorite_hour=core.favorite_hour,
        rankings=rankings,
        top_emotes=top_emotes,
        smoke_stats=smoke_stats,
    )


async def _compare_core(
    username: str,
    period: str,
    platform: str,
    start_date: str | None,
    end_date: str | None,
):
    platforms = [platform] if platform in VALID_PLATFORMS else ["all", "twitch", "kick"]
    for candidate_platform in platforms:
        core = await get_user_core(
            username,
            period,
            candidate_platform,
            start_date,
            end_date,
        )
        if core is not None:
            return core
    return None


def _model_entry_matches(entry, username: str, platform: str) -> bool:
    return entry.username == username and entry.platform == platform


def _dict_entry_matches(entry: dict, username: str, platform: str) -> bool:
    return entry.get("username") == username and entry.get("platform", "twitch") == platform


def _rising_tuple(entries: list[RisingStarEntry], username: str, platform: str) -> tuple[int | None, int | None, float | None]:
    for entry in entries:
        if _model_entry_matches(entry, username, platform):
            return entry.rank, entry.current_count, entry.growth_percent
    return None, None, None


def _writers_tuple(entries: list[WriterEntry], username: str, platform: str) -> tuple[int | None, float | None, float | None]:
    for entry in entries:
        if _model_entry_matches(entry, username, platform):
            return entry.rank, entry.score, entry.avg_length
    return None, None, None


def _named_tuple(rows: list[dict], username: str, platform: str) -> tuple[int | None, int | None]:
    for row in rows:
        if _dict_entry_matches(row, username, platform):
            return row["rank"], int(row.get("count") or 0)
    return None, None


def _pererecoes_tuple(entries: list[PererecoesEntry], username: str, platform: str):
    for entry in entries:
        if entry.username == username and entry.platform == platform:
            return entry.rank, entry.points, entry.breakdown
    for entry in entries:
        if entry.username == username:
            return entry.rank, entry.points, entry.breakdown
    return None, None, []


async def _compare_rankings_for_cores(
    core1,
    user_id1: str | None,
    core2,
    user_id2: str | None,
    period: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[UserRankings, UserRankings]:
    from app.services.stats_aggregates import get_named_daily_leaderboard

    board_cache: dict[str, tuple] = {}

    async def boards_for(platform: str):
        if platform not in board_cache:
            base_boards = await asyncio.gather(
                get_rising_stars(limit=10, platform=platform, period=period, start_date=start_date, end_date=end_date),
                get_top_writers(limit=10, platform=platform, period=period, start_date=start_date, end_date=end_date),
                get_named_daily_leaderboard("famosinhos_daily", period, platform, limit=200, start_date=start_date, end_date=end_date),
                get_named_daily_leaderboard("folhinha_daily", period, platform, limit=200, start_date=start_date, end_date=end_date),
                get_named_daily_leaderboard("maria_daily", period, platform, limit=200, start_date=start_date, end_date=end_date),
                get_named_daily_leaderboard("escritor_roubado_daily", period, platform, limit=200, start_date=start_date, end_date=end_date),
            )
            pererecoes = _get_stats_cache(
                _stats_cache_key(
                    "pererecoes",
                    period=period,
                    platform=platform,
                    limit=100,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            if pererecoes is None:
                pererecoes = PererecoesResponse(period=period, platform=platform, leaderboard=[])
            board_cache[platform] = (*base_boards, pererecoes)
        return board_cache[platform]

    async def build(core, user_id: str | None) -> UserRankings:
        username = core.username
        platform = core.platform
        (
            top_rank,
            boards,
            diversidade_pair,
            creators_pair,
            duas_caras_pair,
        ) = await asyncio.gather(
            _rank_from_message_leaderboard(
                username, user_id, platform, period,
                start_date=start_date, end_date=end_date,
            ),
            boards_for(platform),
            _diversidade_rank_for_user(
                username, user_id, platform, period,
                start_date=start_date, end_date=end_date,
            ),
            _creators_rank_for_user(username),
            _duas_caras_rank_for_user(username, user_id, platform),
        )
        rising_entries, writer_entries, famosinhos_rows, folhinha_rows, maria_rows, escritor_rows, pererecoes_resp = boards
        rising_rank, rising_count, rising_growth = _rising_tuple(rising_entries, username, platform)
        writers_rank, writers_score, writers_avg_length = _writers_tuple(writer_entries, username, platform)
        famosinhos_rank, famosinhos_count = _named_tuple(famosinhos_rows, username, platform)
        folhinha_rank, folhinha_count = _named_tuple(folhinha_rows, username, platform)
        maria_rank, maria_count = _named_tuple(maria_rows, username, platform)
        escritor_rank, escritor_count = _named_tuple(escritor_rows, username, platform)
        diversidade_rank, diversidade_count = diversidade_pair
        creators_rank, creators_count = creators_pair
        duas_caras_rank, duas_caras_count = duas_caras_pair
        pererecoes_rank, pererecoes_points, pererecoes_breakdown = _pererecoes_tuple(
            pererecoes_resp.leaderboard, username, platform,
        )

        return UserRankings(
            top_rank=top_rank,
            rising_rank=rising_rank,
            rising_count=rising_count,
            rising_growth=rising_growth,
            writers_rank=writers_rank,
            writers_score=writers_score,
            writers_avg_length=writers_avg_length,
            hours_dominated=[],
            famosinhos_rank=famosinhos_rank,
            famosinhos_count=famosinhos_count,
            folhinha_rank=folhinha_rank,
            folhinha_count=folhinha_count,
            maria_vai_com_as_outras_rank=maria_rank,
            maria_vai_com_as_outras_count=maria_count,
            escritor_roubado_rank=escritor_rank,
            escritor_roubado_count=escritor_count,
            diversidade_rank=diversidade_rank,
            diversidade_count=diversidade_count,
            creators_rank=creators_rank,
            creators_count=creators_count,
            duas_caras_rank=duas_caras_rank,
            duas_caras_count=duas_caras_count,
            pererecoes_rank=pererecoes_rank,
            pererecoes_points=pererecoes_points,
            pererecoes_breakdown=pererecoes_breakdown or [],
        )

    await asyncio.gather(*(boards_for(p) for p in {core1.platform, core2.platform}))
    return await asyncio.gather(build(core1, user_id1), build(core2, user_id2))


def _compare_user_stats(core, rankings: UserRankings, top_emotes: list[EmoteUsage], smoke_stats) -> UserStats:
    if smoke_stats:
        rankings.smoke_rank = rankings.smoke_rank or smoke_stats.rank
        rankings.smoke_count = rankings.smoke_count if rankings.smoke_count is not None else smoke_stats.count
    return UserStats(
        username=core.username,
        display_name=core.display_name,
        platform=core.platform,
        period=core.period,
        total_messages=core.total_messages,
        hourly_activity=[],
        recent_messages=[],
        first_message_date=core.first_message_date,
        last_message_date=core.last_message_date,
        percentile=core.percentile,
        peak_hours=core.peak_hours,
        favorite_hour=core.favorite_hour,
        rankings=rankings,
        top_emotes=top_emotes,
        smoke_stats=smoke_stats,
    )


async def get_user_comparison(
    user1: str,
    user2: str,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[UserStats | None, UserStats | None]:
    """Get stats for two users for comparison"""
    resolved1 = await resolve_username(user1, platform) or user1.lower().strip()
    resolved2 = await resolve_username(user2, platform) or user2.lower().strip()
    core1, core2 = await asyncio.gather(
        _compare_core(resolved1, period, platform, start_date, end_date),
        _compare_core(resolved2, period, platform, start_date, end_date),
    )
    if core1 is None or core2 is None:
        return None, None

    user_id1, _ = await resolve_user_identity(core1.username, core1.platform)
    user_id2, _ = await resolve_user_identity(core2.username, core2.platform)

    from app.services.smoke_service import get_user_smoke_stats
    rankings_task = _compare_rankings_for_cores(
        core1, user_id1, core2, user_id2, period, start_date, end_date,
    )
    emotes1_task = get_user_top_emotes(
        core1.username, limit=5, user_id=user_id1, platform=core1.platform,
        period=period, start_date=start_date, end_date=end_date,
    )
    emotes2_task = get_user_top_emotes(
        core2.username, limit=5, user_id=user_id2, platform=core2.platform,
        period=period, start_date=start_date, end_date=end_date,
    )
    smoke1_task = get_user_smoke_stats(core1.username, user_id=user_id1, platform=core1.platform)
    smoke2_task = get_user_smoke_stats(core2.username, user_id=user_id2, platform=core2.platform)

    (rankings1, rankings2), emotes1, emotes2, smoke1, smoke2 = await asyncio.gather(
        rankings_task,
        emotes1_task,
        emotes2_task,
        smoke1_task,
        smoke2_task,
    )

    return (
        _compare_user_stats(core1, rankings1, emotes1, smoke1),
        _compare_user_stats(core2, rankings2, emotes2, smoke2),
    )


async def search_users(query: str, limit: int = 10, platform: str = "all") -> list[UserSearchResult]:
    """Search users by username or display_name prefix from pre-aggregated totals.

    Past usernames are matched via known_usernames but results always return the
    current login, deduped by platform user_id.
    """
    if not query or len(query) < 2:
        return []

    escaped_query = re.escape(query.lower())
    prefix = {"$regex": f"^{escaped_query}", "$options": "i"}
    match: dict = {
        "username": {"$nin": list(IGNORED_BOTS)},
        "$or": [
            {"username": prefix},
            {"display_name": {"$regex": f"^{re.escape(query)}", "$options": "i"}},
            {"known_usernames": prefix},
        ]
    }
    if platform in VALID_PLATFORMS:
        match["platform"] = platform

    # Over-fetch so we still fill `limit` after collapsing past/legacy rows.
    fetch_limit = max(limit * 5, 25)
    raw = await db.user_totals.find(
        match,
        {"username": 1, "display_name": 1, "platform": 1, "message_count": 1, "user_id": 1},
    ).sort("message_count", -1).limit(fetch_limit).to_list(fetch_limit)

    results: list[UserSearchResult] = []
    seen: set[str] = set()

    for entry in raw:
        plat = entry.get("platform", "twitch")
        uid = str(entry.get("user_id") or "")
        username = entry["username"]

        # Legacy rows used login as user_id; resolve to the permanent platform id.
        if not uid or uid == username:
            real_uid, resolved_plat = await resolve_user_identity(
                username, plat if platform == "all" else platform
            )
            if real_uid:
                uid = str(real_uid)
                plat = resolved_plat or plat

        if uid and uid != username:
            canon = await db.user_totals.find_one(
                {"platform": plat, "user_id": uid},
                {"username": 1, "display_name": 1, "platform": 1, "message_count": 1, "user_id": 1},
            )
            if canon:
                entry = canon
                username = canon["username"]
                plat = canon.get("platform", plat)

        if username.lower() in IGNORED_BOTS:
            continue

        key = f"{plat}:{uid or username}"
        if key in seen:
            continue
        seen.add(key)

        results.append(
            UserSearchResult(
                username=entry["username"],
                display_name=entry.get("display_name") or entry["username"],
                platform=entry.get("platform", "twitch"),
                total_messages=int(entry.get("message_count", 0)),
            )
        )
        if len(results) >= limit:
            break

    return results


async def get_user_rankings(
    username: str,
    period: str,
    user_id: str | None = None,
    platform: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> UserRankings:
    """Get user's position in various leaderboards using pre-aggregates (fast path)."""
    import asyncio

    username_lower = username.lower()
    user_platform = platform or "twitch"
    plat_filter = user_platform if user_platform in ("twitch", "kick") else "all"

    async def _rising():
        entries = await get_rising_stars(
            limit=10, platform=plat_filter, period=period,
            start_date=start_date, end_date=end_date,
        )
        for entry in entries:
            if entry.username == username_lower and entry.platform == user_platform:
                return entry.rank, entry.current_count, entry.growth_percent
        return None, None, None

    async def _writers():
        entries = await get_top_writers(
            limit=10, platform=plat_filter, period=period,
            start_date=start_date, end_date=end_date,
        )
        for entry in entries:
            if entry.username == username_lower and entry.platform == user_platform:
                return entry.rank, entry.score, entry.avg_length
        return None, None, None

    async def _hours():
        hour_leaders = await get_hour_leaders(
            platform=plat_filter, period=period,
            start_date=start_date, end_date=end_date,
        )
        return [
            entry.hour for entry in hour_leaders
            if entry.username == username_lower and entry.platform == user_platform
        ]

    async def _smoke():
        try:
            from app.services.smoke_service import get_user_smoke_stats
            smoke = await get_user_smoke_stats(username_lower, user_id=user_id, platform=user_platform)
            return (smoke.rank, smoke.count) if smoke else (None, None)
        except Exception:
            return None, None

    async def _pererecoes():
        try:
            resp = await get_pererecoes_leaderboard(
                period, plat_filter, limit=100,
                start_date=start_date, end_date=end_date,
            )
            for entry in resp.leaderboard:
                if entry.username == username_lower and entry.platform == user_platform:
                    return entry.rank, entry.points, entry.breakdown
                if entry.username == username_lower:
                    return entry.rank, entry.points, entry.breakdown
            return None, None, []
        except Exception:
            return None, None, []

    (
        top_rank,
        rising_tuple,
        writers_tuple,
        hours_dominated,
        famosinhos_tuple,
        folhinha_tuple,
        maria_tuple,
        escritor_tuple,
        diversidade_pair,
        smoke_tuple,
        creators_pair,
        pererecoes_tuple,
        duas_caras_pair,
    ) = await asyncio.gather(
        _rank_from_message_leaderboard(
            username_lower, user_id, user_platform, period,
            start_date=start_date, end_date=end_date,
        ),
        _rising(),
        _writers(),
        _hours(),
        _rank_in_named_daily(
            "famosinhos_daily", username_lower, user_id, user_platform, period,
            start_date=start_date, end_date=end_date,
        ),
        _rank_in_named_daily(
            "folhinha_daily", username_lower, user_id, user_platform, period,
            start_date=start_date, end_date=end_date,
        ),
        _rank_in_named_daily(
            "maria_daily", username_lower, user_id, user_platform, period,
            start_date=start_date, end_date=end_date,
        ),
        _rank_in_named_daily(
            "escritor_roubado_daily", username_lower, user_id, user_platform, period,
            start_date=start_date, end_date=end_date,
        ),
        _diversidade_rank_for_user(
            username_lower, user_id, user_platform, period,
            start_date=start_date, end_date=end_date,
        ),
        _smoke(),
        _creators_rank_for_user(username_lower),
        _pererecoes(),
        _duas_caras_rank_for_user(username_lower, user_id, user_platform),
    )

    rising_rank, rising_count, rising_growth = rising_tuple
    writers_rank, writers_score, writers_avg_length = writers_tuple
    famosinhos_rank, famosinhos_count = famosinhos_tuple
    folhinha_rank, folhinha_count = folhinha_tuple
    maria_vai_com_as_outras_rank, maria_vai_com_as_outras_count = maria_tuple
    escritor_roubado_rank, escritor_roubado_count = escritor_tuple
    diversidade_rank, diversidade_count = diversidade_pair
    smoke_rank, smoke_count = smoke_tuple
    creators_rank, creators_count = creators_pair
    pererecoes_rank, pererecoes_points, pererecoes_breakdown = pererecoes_tuple
    duas_caras_rank, duas_caras_count = duas_caras_pair

    return UserRankings(
        top_rank=top_rank,
        top_rank_change=None,
        rising_rank=rising_rank,
        rising_count=rising_count,
        rising_growth=rising_growth,
        writers_rank=writers_rank,
        writers_score=writers_score,
        writers_avg_length=writers_avg_length,
        hours_dominated=hours_dominated,
        famosinhos_rank=famosinhos_rank,
        famosinhos_count=famosinhos_count,
        folhinha_rank=folhinha_rank,
        folhinha_count=folhinha_count,
        maria_vai_com_as_outras_rank=maria_vai_com_as_outras_rank,
        maria_vai_com_as_outras_count=maria_vai_com_as_outras_count,
        escritor_roubado_rank=escritor_roubado_rank,
        escritor_roubado_count=escritor_roubado_count,
        diversidade_rank=diversidade_rank,
        diversidade_count=diversidade_count,
        smoke_rank=smoke_rank,
        smoke_count=smoke_count,
        creators_rank=creators_rank,
        creators_count=creators_count,
        duas_caras_rank=duas_caras_rank,
        duas_caras_count=duas_caras_count,
        pererecoes_rank=pererecoes_rank,
        pererecoes_points=pererecoes_points,
        pererecoes_breakdown=pererecoes_breakdown or [],
    )


async def _rank_from_message_leaderboard(
    username: str,
    user_id: str | None,
    platform: str,
    period: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> int | None:
    """Rank by message count from aggregates when possible."""
    try:
        if period == "all" and not start_date:
            from app.services.stats_aggregates import get_leaderboard_from_totals
            entries, _, _ = await get_leaderboard_from_totals(platform, 1000)
            for i, entry in enumerate(entries):
                if entry.get("platform", "twitch") != platform:
                    continue
                if user_id and str(entry.get("user_id")) == str(user_id):
                    return i + 1
                if entry.get("username") == username:
                    return i + 1
            return None

        from app.services.stats_aggregates import resolve_period_dates
        date_range = resolve_period_dates(period, start_date, end_date)
        if not date_range:
            return None
        start, end = date_range
        match = {"date": {"$gte": start, "$lte": end}, "platform": platform}
        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {"user_id": "$user_id", "username": "$username"},
                    "count": {"$sum": "$message_count"},
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": 1000},
        ]
        rows = await db.user_daily_stats.aggregate(pipeline).to_list(1000)
        for i, row in enumerate(rows):
            oid = row["_id"]
            if user_id and str(oid.get("user_id")) == str(user_id):
                return i + 1
            if oid.get("username") == username:
                return i + 1
    except Exception as exc:
        print(f"top rank aggregate failed: {exc}")
    return None


async def _rank_in_named_daily(
    collection_name: str,
    username: str,
    user_id: str | None,
    platform: str,
    period: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[int | None, int | None]:
    from app.services.stats_aggregates import get_named_daily_leaderboard
    rows = await get_named_daily_leaderboard(
        collection_name, period, platform, limit=200,
        start_date=start_date, end_date=end_date,
    )
    for row in rows:
        if row.get("platform") != platform:
            continue
        if row.get("username") == username:
            return row["rank"], int(row.get("count") or 0)
    return None, None


async def _diversidade_rank_for_user(
    username: str,
    user_id: str | None,
    platform: str,
    period: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[int | None, int | None]:
    from app.services.emote_service import _period_date_strs, _platform_match
    dates = _period_date_strs(period, start_date, end_date)
    match: dict = {**_platform_match(platform)}
    if dates is not None:
        match["date"] = {"$in": dates}

    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {
            "$group": {
                "_id": {"platform": "$platform", "user_id": "$user_id"},
                "username": {"$last": "$username"},
                "unique_emotes": {"$addToSet": "$emote_id"},
            }
        },
        {
            "$project": {
                "username": 1,
                "platform": "$_id.platform",
                "user_id": "$_id.user_id",
                "unique_count": {"$size": "$unique_emotes"},
            }
        },
        {"$sort": {"unique_count": -1}},
        {"$limit": 200},
    ]
    rows = await db.emote_daily_stats.aggregate(pipeline).to_list(200)
    for i, row in enumerate(rows):
        if row.get("platform") != platform:
            continue
        if user_id and str(row.get("user_id")) == str(user_id):
            return i + 1, int(row["unique_count"])
        if row.get("username") == username:
            return i + 1, int(row["unique_count"])
    return None, None


async def _creators_rank_for_user(username: str) -> tuple[int | None, int | None]:
    from app.services.emote_service import get_emote_creators
    data = await get_emote_creators(platform="all", limit=100)
    for entry in data.creators:
        if entry.username == username:
            return entry.rank, entry.emote_count
    return None, None


def _msg_item_from_doc(doc: dict) -> RandomMessageItem:
    ts = doc.get("timestamp") or datetime.now(timezone.utc)
    return RandomMessageItem(
        username=doc.get("username") or "unknown",
        display_name=doc.get("display_name") or doc.get("username") or "unknown",
        platform=doc.get("platform") or "twitch",
        message=doc.get("message") or "",
        timestamp=ts,
    )


async def get_random_message_with_context(platform: str = "all") -> dict | None:
    """Pick a random message and return up to ±20 neighbors on the same platform."""
    match = merge_queries(BOT_FILTER, NOT_REMOVED)
    if platform == "twitch":
        match = merge_queries(match, {"$or": [{"platform": "twitch"}, {"platform": {"$exists": False}}]})
    elif platform == "kick":
        match = merge_queries(match, {"platform": "kick"})

    rows = await db.messages.aggregate([
        {"$match": match},
        {"$sample": {"size": 1}},
    ]).to_list(1)
    if not rows:
        return None

    focus_doc = rows[0]
    focus = _msg_item_from_doc(focus_doc)
    ts = focus_doc.get("timestamp")
    if ts is None:
        return {"focus": focus, "before": [], "after": []}
    if getattr(ts, "tzinfo", None) is None:
        ts = ts.replace(tzinfo=timezone.utc)

    plat = focus_doc.get("platform") or "twitch"
    plat_match = (
        {"$or": [{"platform": "twitch"}, {"platform": {"$exists": False}}]}
        if plat == "twitch"
        else {"platform": plat}
    )
    ctx_base = merge_queries(BOT_FILTER, NOT_REMOVED, plat_match)

    before_docs = await db.messages.find(
        merge_queries(ctx_base, {"timestamp": {"$lt": ts}}),
    ).sort("timestamp", -1).limit(RIBBITS_CONTEXT).to_list(RIBBITS_CONTEXT)

    after_docs = await db.messages.find(
        merge_queries(ctx_base, {"timestamp": {"$gt": ts}}),
    ).sort("timestamp", 1).limit(RIBBITS_CONTEXT).to_list(RIBBITS_CONTEXT)

    # before: chronological (oldest → newest approaching focus)
    before_docs.reverse()

    return {
        "focus": focus,
        "before": [_msg_item_from_doc(d) for d in before_docs],
        "after": [_msg_item_from_doc(d) for d in after_docs],
    }


async def get_chat_activity_today(
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[ChatActivityPoint], int, int, int]:
    """Hour-of-day message counts inside the selected period (all messages if period=all)."""
    match = build_base_match(period, platform, start_date, end_date)

    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
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


async def get_overall_hourly_activity(
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[ChatActivityPoint], list[ChatActivityPoint], int, int, int, int, float, int]:
    """Hour-of-day totals (and daily averages) inside the selected period."""
    from app.services.stats_aggregates import resolve_period_dates

    date_range = resolve_period_dates(period, start_date, end_date)
    hours = [0] * 24
    total_messages = 0

    if date_range is None:
        # All-time: prefer precomputed totals
        if await aggregates_ready():
            from app.services.stats_aggregates import get_overall_hourly_from_totals
            hours, total_messages = await get_overall_hourly_from_totals(platform)
        else:
            pipeline = [
                {"$match": merge_queries(BOT_FILTER, get_platform_filter(platform))},
                {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
            results = await db.messages.aggregate(pipeline).to_list(24)
            for r in results:
                h = int(r["_id"])
                if 0 <= h < 24:
                    hours[h] = int(r["count"])
            total_messages = sum(hours)
        days = await _collection_day_count(platform)
    else:
        match = build_base_match(period, platform, start_date, end_date)
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
        results = await db.messages.aggregate(pipeline).to_list(24)
        for r in results:
            h = int(r["_id"])
            if 0 <= h < 24:
                hours[h] = int(r["count"])
        total_messages = sum(hours)
        start_d = datetime.strptime(date_range[0][:10], "%Y-%m-%d").date()
        end_d = datetime.strptime(date_range[1][:10], "%Y-%m-%d").date()
        days = (end_d - start_d).days + 1

    days = max(days, 1)

    activity = [ChatActivityPoint(hour=h, count=hours[h]) for h in range(24)]
    average_activity = [
        ChatActivityPoint(hour=h, count=int(round(hours[h] / days)))
        for h in range(24)
    ]

    peak_hour = 0
    peak_count = 0
    for point in activity:
        if point.count > peak_count:
            peak_count = point.count
            peak_hour = point.hour

    avg_peak_hour = 0
    avg_peak_count = 0.0
    for h in range(24):
        avg = hours[h] / days
        if avg > avg_peak_count:
            avg_peak_count = avg
            avg_peak_hour = h

    return (
        activity,
        average_activity,
        total_messages,
        peak_hour,
        peak_count,
        avg_peak_hour,
        round(avg_peak_count, 1),
        days,
    )


async def _collection_day_count(platform: str = "all") -> int:
    """Number of distinct BRT calendar days with chat activity."""
    match: dict = {}
    if platform in ("twitch", "kick"):
        match["platform"] = platform
    try:
        if match:
            days = await db.user_daily_stats.distinct("date", match)
        else:
            days = await db.user_daily_stats.distinct("date")
        if days:
            return len(days)
    except Exception:
        pass

    # Fallback: span from earliest message
    query = merge_queries(BOT_FILTER, get_platform_filter(platform))
    first = await db.messages.find_one(query, sort=[("timestamp", 1)], projection={"timestamp": 1})
    if not first or not first.get("timestamp"):
        return 1
    ts = first["timestamp"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(1, (datetime.now(timezone.utc) - ts).days + 1)


async def get_user_top_emotes(
    username: str,
    limit: int = 5,
    user_id: str | None = None,
    platform: str | None = None,
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[EmoteUsage]:
    """Get top emotes used by a specific user in the selected period."""
    try:
        from app.services.emote_service import _period_date_strs, _platform_match

        match: dict = {**_platform_match(platform or "all")}
        dates = _period_date_strs(period, start_date, end_date)
        if dates is not None:
            match["date"] = {"$in": dates}
        if user_id:
            match["user_id"] = str(user_id)
        else:
            match["username"] = username.lower()

        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {"$toLower": "$emote_name"},
                    "emote_name": {"$last": "$emote_name"},
                    "emote_id": {"$last": "$emote_id"},
                    "count": {"$sum": "$count"},
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": limit},
        ]
        rows = await db.emote_daily_stats.aggregate(pipeline).to_list(limit)
        if rows:
            return [
                EmoteUsage(
                    emote_name=row.get("emote_name") or row["_id"],
                    emote_id=row.get("emote_id") or row["_id"],
                    count=int(row.get("count", 0)),
                )
                for row in rows
            ]
    except Exception as exc:
        print(f"user top emotes aggregate failed: {exc}")

    user_query = get_user_query(username, user_id, platform)
    match_query = merge_queries(user_query, get_date_filter(period, start_date, end_date))

    messages = await db.messages.find(match_query).limit(MAX_MESSAGES_QUERY).to_list(MAX_MESSAGES_QUERY)

    message_texts = [msg["message"] for msg in messages]
    return await count_emotes_in_messages(message_texts, limit)


async def get_chat_top_emotes(
    limit: int = 5,
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[EmoteUsage], int]:
    """Get top emotes used in chat for the selected period."""
    cache_key = _stats_cache_key(
        "chat_top_emotes",
        limit=limit,
        platform=platform,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    cached = _get_stats_cache(cache_key)
    if cached is not None:
        return cached

    try:
        from app.services.emote_service import get_top_emotes_from_aggregates
        agg = await get_top_emotes_from_aggregates(
            limit=limit,
            platform=platform,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
        if agg is not None:
            _set_stats_cache(cache_key, agg)
            return agg
    except Exception as exc:
        print(f"top-emotes aggregate fallback: {exc}")

    messages = await db.messages.find(
        build_base_match(period, platform, start_date, end_date)
    ).sort("timestamp", -1).limit(MAX_MESSAGES_QUERY).to_list(MAX_MESSAGES_QUERY)

    message_texts = [msg["message"] for msg in messages]
    emotes = await count_emotes_in_messages(message_texts, limit)

    total = sum(e.count for e in emotes)
    result = (emotes, total)
    _set_stats_cache(cache_key, result)
    return result


async def get_unique_chatters_by_hour(
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[ChatActivityPoint], int, int, int]:
    """Distinct users per hour-of-day inside the selected period."""
    match = build_base_match(period, platform, start_date, end_date)

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"hour": "$hour", "platform": "$platform", "username": "$username"}
        }},
        {"$group": {
            "_id": "$_id.hour",
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}},
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


async def get_username_history(username: str, platform: str = "all") -> UsernameHistoryResponse | None:
    """
    Get all past usernames for a user by looking up their user_id
    and finding all distinct usernames associated with it.
    """
    user_id, resolved_platform = await resolve_user_identity(username, platform)

    if not user_id or not resolved_platform:
        return None

    pipeline = [
        {"$match": merge_queries({"user_id": user_id}, get_platform_filter(resolved_platform))},
        {"$group": {
            "_id": "$username",
            "display_name": {"$last": "$display_name"},
            "first_seen": {"$min": "$timestamp"},
            "last_seen": {"$max": "$timestamp"}
        }},
        {"$sort": {"last_seen": -1}}
    ]

    results = await db.messages.aggregate(pipeline).to_list(100)

    if not results:
        return None

    current_lower = username.lower()
    past_usernames = [
        PastUsername(
            username=entry["_id"],
            display_name=entry["display_name"] or entry["_id"],
            first_seen=entry["first_seen"],
            last_seen=entry["last_seen"]
        )
        for entry in results
        if entry["_id"] != current_lower
    ]

    return UsernameHistoryResponse(
        current_username=current_lower,
        user_id=user_id,
        past_usernames=past_usernames
    )


async def analyze_emote_positions(messages: list[str]) -> EmotePositionData | None:
    """Analyze where emotes appear in messages (beginning, middle, end)"""
    emotes = await get_7tv_emotes()
    if not emotes:
        return None

    comeco = 0
    meio = 0
    fim = 0

    for message in messages:
        words = message.split()
        total_words = len(words)
        if total_words == 0:
            continue

        for i, word in enumerate(words):
            if word in emotes:
                relative_pos = i / total_words  # 0.0 to ~1.0
                if relative_pos < 1/3:
                    comeco += 1
                elif relative_pos < 2/3:
                    meio += 1
                else:
                    fim += 1

    total = comeco + meio + fim
    if total == 0:
        return None

    return EmotePositionData(
        comeco=comeco,
        meio=meio,
        fim=fim,
        comeco_pct=round((comeco / total) * 100, 1),
        meio_pct=round((meio / total) * 100, 1),
        fim_pct=round((fim / total) * 100, 1),
        total=total
    )


async def get_chat_emote_positions(
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> EmotePositionData | None:
    """Get global emote position distribution for the selected period."""
    cache_key = _stats_cache_key(
        "chat_emote_positions",
        platform=platform,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    cached = _get_stats_cache(cache_key)
    if cached is not None:
        return cached

    messages = await db.messages.find(
        build_base_match(period, platform, start_date, end_date)
    ).sort("timestamp", -1).limit(MAX_MESSAGES_QUERY).to_list(MAX_MESSAGES_QUERY)

    message_texts = [msg["message"] for msg in messages]
    result = await analyze_emote_positions(message_texts)
    _set_stats_cache(cache_key, result)
    return result


async def get_user_emote_position(
    username: str,
    user_id: str | None = None,
    platform: str | None = None,
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> UserEmotePosition | None:
    """Get a user's emote position classification"""
    user_query = get_user_query(username, user_id, platform)
    match_query = merge_queries(user_query, get_date_filter(period, start_date, end_date))

    messages = await db.messages.find(match_query).limit(MAX_MESSAGES_QUERY).to_list(MAX_MESSAGES_QUERY)

    message_texts = [msg["message"] for msg in messages]
    positions = await analyze_emote_positions(message_texts)

    if not positions:
        return None

    meio_pct = positions.meio / positions.total
    if meio_pct >= 0.15:
        label = "centrão"
    elif positions.comeco >= positions.fim:
        label = "esquerdista"
    else:
        label = "direitista"

    return UserEmotePosition(
        label=label,
        positions=positions
    )


async def get_emote_position_users(
    limit: int = 100,
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, list[EmotePositionUserEntry]]:
    """Classify top users by their emote position preference for the selected period."""
    cache_key = _stats_cache_key(
        "emote_position_users",
        limit=limit,
        platform=platform,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    cached = _get_stats_cache(cache_key)
    if cached is not None:
        return cached

    emotes = await get_7tv_emotes()
    if not emotes:
        return {"esquerdistas": [], "centrao": [], "direitistas": []}

    pipeline = [
        {"$match": build_base_match(period, platform, start_date, end_date)},
        {"$group": {
            "_id": {"platform": "$platform", "username": "$username"},
            "display_name": {"$last": "$display_name"},
            "count": {"$sum": 1},
            "messages": {"$push": "$message"}
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]

    users = await db.messages.aggregate(pipeline).to_list(limit)

    esquerdistas = []
    centrao = []
    direitistas = []

    for user in users:
        user_messages = user["messages"][:500]

        comeco = 0
        meio = 0
        fim = 0

        for message in user_messages:
            words = message.split()
            total_words = len(words)
            if total_words == 0:
                continue
            for i, word in enumerate(words):
                if word in emotes:
                    relative_pos = i / total_words
                    if relative_pos < 1/3:
                        comeco += 1
                    elif relative_pos < 2/3:
                        meio += 1
                    else:
                        fim += 1

        total_emotes = comeco + meio + fim
        if total_emotes == 0:
            continue

        meio_pct = meio / total_emotes
        if meio_pct >= 0.15:
            label = "centrão"
            pos_count = meio
        elif comeco >= fim:
            label = "esquerdista"
            pos_count = comeco
        else:
            label = "direitista"
            pos_count = fim

        entry = EmotePositionUserEntry(
            rank=0,
            username=user["_id"]["username"],
            display_name=user["display_name"],
            platform=user["_id"].get("platform", "twitch"),
            message_count=user["count"],
            position_count=pos_count,
            label=label
        )

        if label == "esquerdista":
            esquerdistas.append(entry)
        elif label == "centrão":
            centrao.append(entry)
        else:
            direitistas.append(entry)

    for group in [esquerdistas, centrao, direitistas]:
        group.sort(key=lambda x: x.position_count, reverse=True)
        for i, entry in enumerate(group):
            entry.rank = i + 1

    result = {
        "esquerdistas": esquerdistas,
        "centrao": centrao,
        "direitistas": direitistas
    }
    _set_stats_cache(cache_key, result)
    return result
