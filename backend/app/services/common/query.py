"""Shared Mongo query helpers (platform, bots, merge)."""

from datetime import datetime, timedelta, timezone

IGNORED_BOTS: set[str] = {
    "streamadsbot",
    "folhinhabot",
    "fossabot",
}

BOT_FILTER = {"username": {"$nin": list(IGNORED_BOTS)}}
NOT_REMOVED = {"removed": {"$ne": True}}
VALID_PLATFORMS = frozenset({"twitch", "kick"})


def get_platform_filter(platform: str = "all") -> dict:
    if platform == "twitch":
        return {"$or": [{"platform": "twitch"}, {"platform": {"$exists": False}}]}
    if platform == "kick":
        return {"platform": "kick"}
    return {}


def merge_queries(*queries: dict) -> dict:
    parts = [q for q in queries if q]
    if not parts:
        return {}
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}


def get_date_filter(
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Mongo timestamp filter for a period or explicit BRT date range."""
    from app.services.common.period import resolve_period_dates, date_range_to_utc_bounds

    date_range = resolve_period_dates(period, start_date, end_date)
    if date_range:
        start_utc, end_utc = date_range_to_utc_bounds(date_range[0], date_range[1])
        return {"timestamp": {"$gte": start_utc, "$lt": end_utc}}

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


def build_base_match(
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    match = {**BOT_FILTER, **get_platform_filter(platform)}
    date_filter = get_date_filter(period, start_date, end_date)
    if date_filter:
        match.update(date_filter)
    return match
