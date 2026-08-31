"""SmokeTime (16:20 BRT) ritual stats from the smoke_sessions collection."""

from datetime import datetime, timedelta, date, timezone
from collections import defaultdict

from app.database import db
from app.services.stats_aggregates import BRT, _totals_match
from app.services.stats_service import (
    _stats_cache_key,
    _get_stats_cache,
    _set_stats_cache,
    HEAVY_STATS_CACHE_TTL_SECONDS,
)
from app.models.schemas import (
    SmokeTimeResponse,
    SmokeLeaderboardEntry,
    SmokeDayPoint,
    SmokeBestDay,
    SmokeToday,
    SmokeFirstToday,
    SmokeStreakEntry,
    UserSmokeStats,
)

LEADERBOARD_LIMIT = 10
LONGEST_STREAKS_LIMIT = 10


def _today_brt() -> date:
    return datetime.now(BRT).date()


def _parse_date(date_str: str) -> date:
    return date.fromisoformat(date_str)


def _current_streak(dates: list[date], today: date) -> int:
    """Consecutive days ending at today (or yesterday if today not yet participated)."""
    if not dates:
        return 0

    date_set = set(dates)
    # Streak is active only if the user participated today or yesterday
    if today not in date_set and (today - timedelta(days=1)) not in date_set:
        return 0

    cursor = today if today in date_set else today - timedelta(days=1)
    streak = 0
    while cursor in date_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _longest_streak(dates: list[date]) -> int:
    if not dates:
        return 0
    sorted_dates = sorted(set(dates))
    best = 1
    current = 1
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
            current += 1
            if current > best:
                best = current
        else:
            current = 1
    return best


async def get_smoke_time_stats(
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> SmokeTimeResponse:
    from app.services.stats_aggregates import resolve_period_dates

    cache_key = _stats_cache_key(
        "smoke_time", platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )
    cached = _get_stats_cache(cache_key, ttl=HEAVY_STATS_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached

    match = _totals_match(platform)
    date_range = resolve_period_dates(period, start_date, end_date)
    if date_range:
        match = {**match, "date": {"$gte": date_range[0], "$lte": date_range[1]}}
    cursor = db.smoke_sessions.find(
        match,
        {
            "platform": 1,
            "user_id": 1,
            "username": 1,
            "display_name": 1,
            "date": 1,
            "first_ts": 1,
        },
    )
    docs = await cursor.to_list(None)

    today = _today_brt()
    today_str = today.isoformat()

    # Group sessions by user and by day
    by_user: dict[tuple[str, str], dict] = {}
    by_day: dict[str, set[tuple[str, str]]] = defaultdict(set)
    first_today: SmokeFirstToday | None = None
    first_today_ts: datetime | None = None

    for doc in docs:
        plat = doc.get("platform", "twitch")
        user_id = str(doc["user_id"])
        key = (plat, user_id)
        date_str = doc["date"]

        if key not in by_user:
            by_user[key] = {
                "platform": plat,
                "user_id": user_id,
                "username": doc["username"],
                "display_name": doc.get("display_name") or doc["username"],
                "dates": [],
            }
        else:
            # Keep latest username/display_name
            by_user[key]["username"] = doc["username"]
            by_user[key]["display_name"] = doc.get("display_name") or doc["username"]

        by_user[key]["dates"].append(_parse_date(date_str))
        by_day[date_str].add(key)

        if date_str == today_str and doc.get("first_ts") is not None:
            ts = doc["first_ts"]
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if first_today_ts is None or ts < first_today_ts:
                    first_today_ts = ts
                    first_today = SmokeFirstToday(
                        username=doc["username"],
                        display_name=doc.get("display_name") or doc["username"],
                        platform=plat,
                        first_ts=ts,
                    )

    total_sessions = len(docs)
    total_unique = len(by_user)
    first_session = min(by_day.keys()) if by_day else None

    # Best day
    best_day = None
    if by_day:
        best_date = max(by_day.keys(), key=lambda d: len(by_day[d]))
        best_day = SmokeBestDay(
            date=best_date,
            participants=len(by_day[best_date]),
        )

    # Last 5 days (today .. today-4), always 5 entries
    last_5_days: list[SmokeDayPoint] = []
    for i in range(5):
        d = today - timedelta(days=i)
        d_str = d.isoformat()
        last_5_days.append(
            SmokeDayPoint(date=d_str, participants=len(by_day.get(d_str, set())))
        )

    last_30_days: list[SmokeDayPoint] = []
    for i in range(30):
        d = today - timedelta(days=i)
        d_str = d.isoformat()
        last_30_days.append(
            SmokeDayPoint(date=d_str, participants=len(by_day.get(d_str, set())))
        )

    today_count = len(by_day.get(today_str, set()))

    # Always resolve first tragador of today BRT (independent of period window)
    if first_today is None:
        today_match = {**_totals_match(platform), "date": today_str}
        today_docs = await db.smoke_sessions.find(
            today_match,
            {"username": 1, "display_name": 1, "platform": 1, "first_ts": 1},
        ).to_list(None)
        for doc in today_docs:
            ts = doc.get("first_ts")
            if not isinstance(ts, datetime):
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if first_today_ts is None or ts < first_today_ts:
                first_today_ts = ts
                first_today = SmokeFirstToday(
                    username=doc["username"],
                    display_name=doc.get("display_name") or doc["username"],
                    platform=doc.get("platform", "twitch"),
                    first_ts=ts,
                )
        today_count = len(today_docs) if today_docs else today_count

    # Leaderboard: top 10 by session count
    ranked = sorted(
        by_user.values(),
        key=lambda u: len(u["dates"]),
        reverse=True,
    )

    leaderboard = [
        SmokeLeaderboardEntry(
            username=u["username"],
            display_name=u["display_name"],
            platform=u["platform"],
            count=len(u["dates"]),
            streak_current=_current_streak(u["dates"], today),
        )
        for u in ranked[:LEADERBOARD_LIMIT]
    ]

    # Longest streaks (all-time)
    streak_ranked = sorted(
        (
            {
                **u,
                "streak": _longest_streak(u["dates"]),
            }
            for u in by_user.values()
        ),
        key=lambda u: u["streak"],
        reverse=True,
    )
    longest_streaks = [
        SmokeStreakEntry(
            username=u["username"],
            display_name=u["display_name"],
            platform=u["platform"],
            streak=u["streak"],
        )
        for u in streak_ranked[:LONGEST_STREAKS_LIMIT]
        if u["streak"] > 0
    ]

    result = SmokeTimeResponse(
        leaderboard=leaderboard,
        best_day=best_day,
        last_5_days=last_5_days,
        last_30_days=last_30_days,
        today=SmokeToday(participants=today_count),
        total_sessions=total_sessions,
        total_unique_participants=total_unique,
        longest_streaks=longest_streaks,
        first_session=first_session,
        first_today=first_today,
    )
    _set_stats_cache(cache_key, result)
    return result


async def get_user_smoke_stats(
    username: str,
    user_id: str | None = None,
    platform: str | None = None,
) -> UserSmokeStats | None:
    """Per-user SmokeTime stats from smoke_sessions. Returns None if user never participated."""
    username_lower = username.lower()
    plat = platform or "twitch"

    if user_id:
        user_match = {
            "platform": plat,
            "$or": [
                {"user_id": str(user_id)},
                {"username": username_lower, "user_id": {"$exists": False}},
            ],
        }
    else:
        user_match = {"platform": plat, "username": username_lower}

    user_docs = await db.smoke_sessions.find(
        user_match,
        {"date": 1, "username": 1},
    ).to_list(None)

    if not user_docs:
        return None

    dates = sorted({_parse_date(d["date"]) for d in user_docs})
    today = _today_brt()
    count = len(dates)
    streak_current = _current_streak(dates, today)
    streak_longest = _longest_streak(dates)
    first_session = dates[0].isoformat()
    last_session = dates[-1].isoformat()

    # Rank: 1 + number of users on same platform with more sessions
    pipeline = [
        {"$match": {"platform": plat}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": count}}},
        {"$count": "ahead"},
    ]
    ahead = await db.smoke_sessions.aggregate(pipeline).to_list(1)
    rank = (ahead[0]["ahead"] + 1) if ahead else 1

    return UserSmokeStats(
        count=count,
        streak_current=streak_current,
        streak_longest=streak_longest,
        rank=rank,
        first_session=first_session,
        last_session=last_session,
    )
