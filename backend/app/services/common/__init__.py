"""Shared service utilities."""

from app.services.common.cache import (
    HEAVY_STATS_CACHE_TTL_SECONDS,
    RANK_CACHE_TTL_SECONDS,
    _rank_cache,
    get_stats_cache,
    invalidate_rank_cache,
    invalidate_stats_cache,
    set_stats_cache,
    stats_cache_key,
    _get_stats_cache,
    _set_stats_cache,
    _stats_cache_key,
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
from app.services.common.period import (
    BRT,
    date_range_to_utc_bounds,
    period_date_range_brt,
    previous_equal_window,
    resolve_period_dates,
)

__all__ = [
    "HEAVY_STATS_CACHE_TTL_SECONDS",
    "RANK_CACHE_TTL_SECONDS",
    "_rank_cache",
    "get_stats_cache",
    "invalidate_rank_cache",
    "invalidate_stats_cache",
    "set_stats_cache",
    "stats_cache_key",
    "_get_stats_cache",
    "_set_stats_cache",
    "_stats_cache_key",
    "BOT_FILTER",
    "IGNORED_BOTS",
    "NOT_REMOVED",
    "VALID_PLATFORMS",
    "build_base_match",
    "get_date_filter",
    "get_platform_filter",
    "merge_queries",
    "BRT",
    "date_range_to_utc_bounds",
    "period_date_range_brt",
    "previous_equal_window",
    "resolve_period_dates",
]
