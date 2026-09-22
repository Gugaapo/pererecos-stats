"""Home / chat activity charts — peeled from stats_service."""

from datetime import datetime, timezone

from app.database import db
from app.models.schemas import ChatActivityPoint
from app.services.common.query import (
    BOT_FILTER,
    build_base_match,
    get_platform_filter,
    merge_queries,
)


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
        from app.services.stats_service import aggregates_ready
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
