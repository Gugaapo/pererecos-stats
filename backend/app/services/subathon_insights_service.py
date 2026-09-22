"""Read-side aggregations for the Timer tab. Pure math lives in subathon_insights.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.database import db
from app.services.common.cache import get_stats_cache, set_stats_cache, stats_cache_key
from app.services.common.query import (
    BOT_FILTER, NOT_REMOVED, get_platform_filter, merge_queries,
)
from app.services.subathon_insights import (
    PACE_MIN_WINDOW_SECONDS, STALE_THRESHOLD_SECONDS, aware, best_worst_hours,
    brt_hour, cross_check_summary, day_balance, dry_spell, end_projection,
    feed_cross_check, feed_health, growth_streak, increase_histogram,
    live_vs_offline, milestones, pace_arrow, pace_minutes_per_hour, panic_rate_stats,
    ramp_buckets, reactive_emote_stats, records_update, single_increase_stats,
)
from app.services.subathon_math import BRT, parse_dt
from app.services.subathon_service import get_timer
import logging

logger = logging.getLogger(__name__)

INSIGHTS_CACHE_TTL_SECONDS = 60
CHAT_SYNC_CACHE_TTL_SECONDS = 300
PANIC_THRESHOLD_SECONDS = 1800
REACTIVE_WINDOW_SECONDS = 300
CHAT_SYNC_LOOKBACK_HOURS = 48


def _snapshot_remaining(doc: dict) -> int | None:
    """Measured remaining at observation time: ends_at - at (no projection)."""
    ends_at = aware(doc.get("ends_at"))
    at = aware(doc.get("at"))
    if ends_at is None or at is None:
        return None
    return max(0, int((ends_at - at).total_seconds()))


def _mongo_utc(dt: datetime | None) -> datetime | None:
    """Normalize to naive UTC for Mongo queries (Motor returns/stores naive UTC)."""
    dt = aware(dt)
    if dt is None:
        return None
    return dt.replace(tzinfo=None)


async def _recent_snapshots(hours: int = 24) -> list[dict]:
    since = _mongo_utc(datetime.now(timezone.utc) - timedelta(hours=hours))
    rows = []
    cursor = db.marathon_snapshots.find({"at": {"$gte": since}}).sort("at", 1)
    async for doc in cursor:
        doc["at"] = aware(doc.get("at"))
        doc["ends_at"] = aware(doc.get("ends_at"))
        doc["remaining_seconds"] = _snapshot_remaining(doc)
        rows.append(doc)
    return rows


async def build_insights() -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    snaps = await _recent_snapshots(24)
    timer = await get_timer()
    remaining = timer.get("remaining_seconds")

    increases = []
    async for doc in db.marathon_increases.find({}).sort("at", 1):
        doc["at"] = aware(doc.get("at"))  # Mongo hands back naive UTC
        increases.append(doc)
    grants = [int(d.get("granted_seconds") or 0) for d in increases if d.get("kind") == "grant"]

    # 1/2/3 — pace, balance, projection over the trailing hour
    window_seconds = 3600
    if snaps:
        first_at = snaps[0]["at"]
        window_seconds = max(1, min(3600, int((now - first_at).total_seconds())))
    hour_ago = now - timedelta(seconds=window_seconds)
    granted_window = sum(
        int(d.get("granted_seconds") or 0)
        for d in increases
        if d.get("kind") == "grant" and d.get("at") and d["at"] >= hour_ago
    )
    day_ago = now - timedelta(hours=24)
    granted_24h = sum(
        int(d.get("granted_seconds") or 0)
        for d in increases
        if d.get("kind") == "grant" and d.get("at") and d["at"] >= day_ago
    )
    pace = pace_minutes_per_hour(granted_window, window_seconds)
    baseline = pace_minutes_per_hour(granted_24h, 86400)

    midnight_brt = now.astimezone(BRT).replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_utc = midnight_brt.astimezone(timezone.utc)
    granted_today = sum(
        int(d.get("granted_seconds") or 0)
        for d in increases
        if d.get("kind") == "grant" and d.get("at") and d["at"] >= midnight_utc
    )
    todays_snaps = [s for s in snaps if s["at"] >= midnight_utc]
    if todays_snaps:
        elapsed_today = int((now - todays_snaps[0]["at"]).total_seconds())
    else:
        first_snap = await db.marathon_snapshots.find_one(sort=[("at", 1)])
        first_at = aware((first_snap or {}).get("at"))
        observed_start = max(midnight_utc, first_at) if first_at else midnight_utc
        elapsed_today = max(0, int((now - observed_start).total_seconds()))

    # 4 — rolling 24h ramp
    by_hours_ago: dict[int, int] = {}
    for doc in increases:
        at = doc.get("at")
        if doc.get("kind") != "grant" or at is None or at < day_ago:
            continue
        by_hours_ago[int((now - at).total_seconds() // 3600)] = (
            by_hours_ago.get(int((now - at).total_seconds() // 3600), 0)
            + int(doc.get("granted_seconds") or 0)
        )

    # 5 — milestones (event-sourced + bootstrap) and live hours above each threshold
    records = await db.marathon_records.find_one({"_id": "current"}) or {}
    crossings = [doc async for doc in db.marathon_milestones.find({})]
    # Fall back to the oldest snapshot in view so a bootstrapped milestone still shows a date
    # on the very first run, before marathon_records has been written.
    first_observed = aware(records.get("first_observed_at"))
    if first_observed is None and snaps:
        first_observed = snaps[0]["at"]
    milestone_rows = milestones(
        remaining,
        first_observed,
        crossings,
        max_remaining_seconds=records.get("max_remaining_seconds"),
    )
    # Accumulated O(1) per poll into marathon_records (see T8), so this is NOT capped to the
    # 24h snapshot window and survives the 90d snapshot TTL.
    above_168h = round((records.get("hours_above_7d_seconds") or 0) / 3600, 3)

    # 7 — live vs offline (uses the status persisted with each increase)
    live = live_vs_offline(increases)

    # 8 — dry spell / seca
    seca = dry_spell([d["at"] for d in increases if d.get("at")], now)

    # 9 — feed health + cross-check
    health_doc = await db.marathon_health.find_one({"_id": "current"}) or {}
    # A gap is only unhealthy when an expected heartbeat was missed, so the threshold is
    # heartbeat + poll interval (300 + 60 = 360s), not the 180s staleness budget used for
    # the "dados desatualizados" note.
    expected_max_gap = int(settings.timer_snapshot_heartbeat_seconds) + int(settings.timer_poll_seconds)
    health = feed_health(
        health_doc.get("polls_ok"), health_doc.get("polls_fail"),
        health_doc.get("max_gap_seconds"), expected_max_gap,
    )
    health["heartbeat_seconds"] = int(settings.timer_snapshot_heartbeat_seconds)
    deltas = [
        d for d in (s.get("cross_check_seconds") for s in snaps) if d is not None
    ]
    cross = cross_check_summary(deltas)

    # 10 — hour-of-day balance
    granted_by_hour: dict[int, int] = {}
    for doc in increases:
        at = doc.get("at")
        if doc.get("kind") == "grant" and at is not None:
            h = brt_hour(at)
            granted_by_hour[h] = granted_by_hour.get(h, 0) + int(doc.get("granted_seconds") or 0)
    elapsed_by_hour: dict[int, int] = {}
    for prev, cur in zip(snaps, snaps[1:]):
        gap = min(300, max(0, int((cur["at"] - prev["at"]).total_seconds())))
        h = brt_hour(prev["at"])
        elapsed_by_hour[h] = elapsed_by_hour.get(h, 0) + gap

    out = {
        "generated_at": now,
        "since": first_observed,
        "pace": {
            "window_seconds": window_seconds,
            "granted_seconds_60m": granted_window,
            "minutes_per_hour": pace,
            "baseline_minutes_per_hour": baseline,
            "arrow": pace_arrow(pace, baseline),
        },
        "balance": {"date": now.astimezone(BRT).strftime("%Y-%m-%d"),
                    **day_balance(granted_today, elapsed_today)},
        "projection": end_projection(remaining, granted_window, window_seconds, now),
        "ramp_24h": ramp_buckets(by_hours_ago),
        "milestones": milestone_rows,
        "milestone_hours_above": {"168h": above_168h},
        "records": {
            "max_remaining_seconds": records.get("max_remaining_seconds"),
            "max_remaining_at": records.get("max_remaining_at"),
            "min_remaining_seconds": records.get("min_remaining_seconds"),
            "min_remaining_at": records.get("min_remaining_at"),
            "first_observed_at": records.get("first_observed_at"),
            "observations_seen": int(records.get("observations_seen") or 0),
        },
        "growth_streak": growth_streak(snaps),
        "distribution": {
            **single_increase_stats(grants),
            "buckets": increase_histogram(grants),
        },
        "dry_spell": seca,
        "hours": best_worst_hours(granted_by_hour, elapsed_by_hour),
        "feed_health": health,
        "cross_check": cross,
        "live": live,
    }
    return out


async def build_insights_cached() -> dict:
    key = stats_cache_key("subathon_insights")
    cached = get_stats_cache(key, INSIGHTS_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached
    out = await build_insights()
    set_stats_cache(key, out)
    return out


_emote_catalog_cache: tuple[float, dict[str, dict[str, str]]] | None = None


async def _emote_catalog_by_lower() -> dict[str, dict[str, str]]:
    """emote_name_lower -> {name, emote_id}, cached 300s."""
    global _emote_catalog_cache
    import time
    now = time.time()
    if _emote_catalog_cache and now - _emote_catalog_cache[0] < 300:
        return _emote_catalog_cache[1]
    mapping: dict[str, dict[str, str]] = {}
    cursor = db.emote_catalog.find(
        {}, {"emote_name_lower": 1, "emote_name": 1, "emote_id": 1}
    )
    async for doc in cursor:
        lower = (doc.get("emote_name_lower") or (doc.get("emote_name") or "").lower()).strip()
        if not lower:
            continue
        eid = str(doc.get("emote_id") or "").strip()
        mapping[lower] = {
            "name": doc.get("emote_name") or lower,
            "emote_id": eid,
        }
    _emote_catalog_cache = (now, mapping)
    return mapping


async def _count_emote_tokens(
    start: datetime, end: datetime, platform: str, name_set: set[str]
) -> dict[str, int]:
    """Count lowercase emote-name tokens in chat over [start, end)."""
    from collections import Counter
    counts: Counter[str] = Counter()
    if not name_set or start >= end:
        return {}
    query = merge_queries(
        BOT_FILTER,
        NOT_REMOVED,
        get_platform_filter(platform),
        {"timestamp": {"$gte": _mongo_utc(start), "$lt": _mongo_utc(end)}},
    )
    cursor = db.messages.find(query, {"message": 1})
    async for doc in cursor:
        text = doc.get("message") or ""
        for word in text.split():
            key = word.lower()
            if key in name_set:
                counts[key] += 1
    return dict(counts)


async def _reactive_emotes(platform: str, snaps: list[dict]) -> list[dict]:
    if len(snaps) < 2:
        return []
    window_start = snaps[0]["at"]
    window_end = snaps[-1]["at"]
    covered = max(0, int((window_end - window_start).total_seconds()))
    if covered <= 0:
        return []

    start_q = _mongo_utc(window_start)
    # Inclusive end so a grant on the last snapshot tick is not dropped.
    end_q = _mongo_utc(window_end + timedelta(seconds=1))
    grants: list[datetime] = []
    cursor = db.marathon_increases.find(
        {"kind": "grant", "at": {"$gte": start_q, "$lt": end_q}},
        sort=[("at", 1)],
    )
    async for doc in cursor:
        at = aware(doc.get("at"))
        if at is not None:
            grants.append(at)

    if not grants:
        logger.debug(
            "reactive_emotes: no grants in window %s .. %s (snaps=%s)",
            start_q, end_q, len(snaps),
        )
        return []

    catalog = await _emote_catalog_by_lower()
    if not catalog:
        logger.warning("reactive_emotes: emote_catalog empty")
        return []
    name_set = set(catalog.keys())
    after_counts: dict[str, int] = {}
    after_seconds = 0
    # Cap work: only the most recent grants drive the reactive ranking.
    recent_grants = grants[-12:]
    logger.debug(
        "reactive_emotes: grants=%s using=%s catalog=%s",
        len(grants), len(recent_grants), len(catalog),
    )
    for at in recent_grants:
        end = at + timedelta(seconds=REACTIVE_WINDOW_SECONDS)
        after_seconds += REACTIVE_WINDOW_SECONDS
        part = await _count_emote_tokens(at, end, platform, name_set)
        for k, v in part.items():
            after_counts[k] = after_counts.get(k, 0) + v

    if not after_counts:
        return []

    # Baseline over a shorter trailing window (last 2h of the snap span) for speed.
    baseline_start = max(window_start, window_end - timedelta(hours=2))
    full_counts = await _count_emote_tokens(baseline_start, window_end, platform, name_set)
    baseline_counts: dict[str, int] = {
        k: max(0, v - after_counts.get(k, 0)) for k, v in full_counts.items()
    }
    baseline_seconds = max(
        0, int((window_end - baseline_start).total_seconds()) - after_seconds
    )
    if baseline_seconds <= 0:
        baseline_seconds = max(1, after_seconds)

    after_named = {catalog[k]["name"]: v for k, v in after_counts.items() if k in catalog}
    base_named = {catalog[k]["name"]: v for k, v in baseline_counts.items() if k in catalog}
    for k, v in after_counts.items():
        if k not in catalog:
            after_named[k] = v
    for k, v in baseline_counts.items():
        if k not in catalog:
            base_named[k] = v

    rows = reactive_emote_stats(
        after_named, after_seconds, base_named, baseline_seconds
    )
    by_lower = {info["name"].lower(): info for info in catalog.values()}
    for row in rows:
        info = by_lower.get(str(row.get("emote_name") or "").lower()) or {}
        row["emote_id"] = info.get("emote_id") or None
    return rows


async def build_chat_sync(platform: str = "all") -> dict:
    now = datetime.now(timezone.utc)
    snaps = await _recent_snapshots(CHAT_SYNC_LOOKBACK_HOURS)
    panic_windows = []
    for prev, cur in zip(snaps, snaps[1:]):
        remaining = prev.get("remaining_seconds")
        if remaining is None or remaining >= PANIC_THRESHOLD_SECONDS:
            continue
        seconds = min(60, max(0, int((cur["at"] - prev["at"]).total_seconds())))
        panic_windows.append({
            "at": prev["at"], "seconds": seconds,
            "remaining_seconds": remaining, "msgs": 0,
        })

    async def _count_msgs(start: datetime, end: datetime) -> int:
        return await db.messages.count_documents(merge_queries(
            BOT_FILTER, NOT_REMOVED, get_platform_filter(platform),
            {"timestamp": {"$gte": start, "$lt": end}},
        ))

    for win in panic_windows:
        win["msgs"] = await _count_msgs(win["at"], win["at"] + timedelta(seconds=win["seconds"]))
    covered_seconds = int((snaps[-1]["at"] - snaps[0]["at"]).total_seconds()) if len(snaps) > 1 else 0
    covered_msgs = await _count_msgs(snaps[0]["at"], snaps[-1]["at"]) if len(snaps) > 1 else 0
    panic = panic_rate_stats(panic_windows, covered_seconds, covered_msgs)
    panic["threshold_seconds"] = PANIC_THRESHOLD_SECONDS

    reactive = await _reactive_emotes(platform, snaps)
    return {"generated_at": now, "lookback_hours": CHAT_SYNC_LOOKBACK_HOURS,
            "panic": panic, "reactive_emotes": reactive}


async def build_chat_sync_cached(platform: str = "all") -> dict:
    key = stats_cache_key("subathon_chat_sync", platform=platform)
    cached = get_stats_cache(key, CHAT_SYNC_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached
    out = await build_chat_sync(platform)
    set_stats_cache(key, out)
    return out
