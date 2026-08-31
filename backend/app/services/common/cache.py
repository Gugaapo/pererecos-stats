"""Shared in-memory cache for expensive stats endpoints."""

from datetime import datetime, timezone

HEAVY_STATS_CACHE_TTL_SECONDS = 300
_expensive_stats_cache: dict[str, tuple[object, datetime]] = {}

# Leaderboard rank cache (active chatters)
_rank_cache: dict[str, tuple[dict[str, int], int, datetime]] = {}
RANK_CACHE_TTL_SECONDS = 60


def stats_cache_key(name: str, **params) -> str:
    parts = [name] + [f"{k}={params[k]}" for k in sorted(params.keys())]
    return "|".join(parts)


def get_stats_cache(key: str, ttl: int = HEAVY_STATS_CACHE_TTL_SECONDS):
    entry = _expensive_stats_cache.get(key)
    if not entry:
        return None
    value, ts = entry
    if (datetime.now(timezone.utc) - ts).total_seconds() > ttl:
        _expensive_stats_cache.pop(key, None)
        return None
    return value


def set_stats_cache(key: str, value) -> None:
    _expensive_stats_cache[key] = (value, datetime.now(timezone.utc))


def invalidate_stats_cache() -> None:
    _expensive_stats_cache.clear()
    _rank_cache.clear()


# Backwards-compatible aliases used across the codebase
_stats_cache_key = stats_cache_key
_get_stats_cache = get_stats_cache
_set_stats_cache = set_stats_cache


def invalidate_rank_cache() -> None:
    invalidate_stats_cache()
