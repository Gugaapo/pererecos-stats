"""Subathon header timer — served from Mongo cache.

The poller owns the steady-state upstream budget. If the cache is already stale,
get_timer() does one opportunistic refresh from the timer feed so the UI can
self-heal instead of sticking on "desatualizado".
"""

from datetime import datetime, timezone
import logging

from app.config import get_settings
from app.database import db
from app.ingest_gate import collection_start, ingest_enabled
from app.services.subathon_math import Marathon, parse_dt

logger = logging.getLogger(__name__)


def _cached_to_marathon(doc: dict) -> Marathon | None:
    if not doc:
        return None
    observed = parse_dt(doc.get("observed_at") or doc.get("fetched_at"))
    if observed is None:
        return None
    return Marathon(
        state=str(doc.get("state") or "unavailable"),
        direction=str(doc.get("direction") or "decrease"),
        locked=bool(doc.get("locked")),
        paused=bool(doc.get("paused")),
        ends_at=parse_dt(doc.get("ends_at")),
        paused_at=parse_dt(doc.get("paused_at")),
        observed_at=observed,
        rules=dict(doc.get("rules") or {}),
    )


async def _refresh_cache_from_feed() -> dict | None:
    """One-shot feed fetch when cache is stale. Best-effort; never raises."""
    try:
        from app.services.subathon_marathon import record_observation
        from app.services.timer_client import client as timer_client

        feed = await timer_client.get_timer()
        await record_observation(
            feed.marathon,
            source="request_refresh",
            heartbeat=False,
            status=feed.status,
            feed_seconds=feed.feed_seconds,
            feed_value=feed.feed_value,
        )
        creator = (feed.payload or {}).get("creator_id")
        if creator:
            await db.marathon_state.update_one(
                {"_id": "current"}, {"$set": {"creator_id": creator}}
            )
        return await db.marathon_state.find_one({"_id": "current"})
    except Exception as exc:
        logger.warning("Opportunistic timer refresh failed: %s", exc)
        return None


async def get_timer() -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    start = collection_start()

    # untilStart branch preserved byte-for-byte in behaviour (pre-subathon countdown).
    if not ingest_enabled():
        remaining = max(0, int((start - now).total_seconds()))
        return {
            "mode": "untilStart",
            "state": None,
            "direction": None,
            "remaining_seconds": remaining,
            "ends_at": None,
            "paused_at": None,
            "paused_total_seconds": 0,
            "locked": False,
            "paused": False,
            "target_at": start,
            "server_now": now,
            "fetched_at": None,
            "stale": False,
            "placeholder": False,
        }

    cached = await db.marathon_state.find_one({"_id": "current"})
    marathon = _cached_to_marathon(cached) if cached else None

    if settings.is_timer_configured and marathon is not None:
        last_success = parse_dt(cached.get("last_success_at")) if cached else None
        stale_s = int(settings.timer_stale_seconds)
        stale = bool(
            last_success is None
            or (now - last_success).total_seconds() > stale_s
        )
        if stale:
            refreshed = await _refresh_cache_from_feed()
            if refreshed:
                cached = refreshed
                marathon = _cached_to_marathon(cached) or marathon
                last_success = parse_dt(cached.get("last_success_at"))
                now = datetime.now(timezone.utc)
                stale = bool(
                    last_success is None
                    or (now - last_success).total_seconds() > stale_s
                )

        paused_total = 0
        async for p in db.marathon_pauses.find({}):
            paused_total += int(p.get("seconds") or 0)

        return {
            "mode": marathon.timer_mode(),
            "state": marathon.state,
            "direction": marathon.direction,
            "remaining_seconds": marathon.remaining_at(now),
            "ends_at": marathon.ends_at,
            "paused_at": marathon.paused_at,
            "paused_total_seconds": paused_total,
            "locked": marathon.locked,
            "paused": marathon.paused,
            "target_at": None,
            "server_now": now,
            "fetched_at": parse_dt(cached.get("fetched_at")) if cached else None,
            "stale": stale,
            "placeholder": False,
        }

    # No cache yet but feed configured — try once so first page load fills state.
    if settings.is_timer_configured and marathon is None:
        refreshed = await _refresh_cache_from_feed()
        if refreshed:
            return await get_timer()

    # Placeholder fallback when feed unconfigured or still empty.
    remaining = max(0, int(settings.subathon_placeholder_seconds))
    return {
        "mode": "unavailable",
        "state": None,
        "direction": None,
        "remaining_seconds": remaining,
        "ends_at": None,
        "paused_at": None,
        "paused_total_seconds": 0,
        "locked": False,
        "paused": False,
        "target_at": None,
        "server_now": now,
        "fetched_at": None,
        "stale": False,
        "placeholder": True,
    }
