"""Gate chat/moderation ingest until the real subathon live starts.

Calendar date is still 2026-09-01, but yesterday's stream ran past midnight BRT
and must not count. Ingest latches on the first Twitch stream whose started_at
is on/after SUBATHON_MIN_STREAM_START, then stays on across restreams.

Detection: EventSub stream.online (instant) + Helix /streams poll (fallback).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BRT = timezone(timedelta(hours=-3))
# Date filters / export floor (not the ingest switch).
COLLECTION_START = datetime(2026, 9, 1, 0, 0, 0, tzinfo=BRT)
HELIX = "https://api.twitch.tv/helix"
HELIX_POLL_SECS = 5

_ingest_latched = False
_latch_loaded = False


def _parse_aware(value: str, fallback: datetime) -> datetime:
    raw = (value or "").strip()
    if not raw:
        return fallback
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Invalid datetime %r, using fallback", raw)
        return fallback
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BRT)
    return dt


def min_stream_started_at() -> datetime:
    settings = get_settings()
    fallback = datetime(2026, 9, 1, 6, 0, 0, tzinfo=BRT)
    return _parse_aware(settings.subathon_min_stream_start, fallback)


def ingest_enabled(now: datetime | None = None) -> bool:
    """Return True once a qualifying subathon stream has been seen."""
    del now  # kept for call-site compatibility
    return _ingest_latched


def _bearer(token: str) -> str:
    t = (token or "").strip()
    if t.lower().startswith("oauth:"):
        t = t[6:]
    return t


async def load_ingest_latch() -> None:
    global _ingest_latched, _latch_loaded
    if _latch_loaded:
        return
    from app.database import db

    try:
        doc = await db.db.subathon_state.find_one({"_id": "ingest_gate"})
        if doc and doc.get("latched"):
            _ingest_latched = True
            logger.info("Subathon ingest already latched (persisted)")
    except Exception:
        logger.exception("Failed to load ingest latch from Mongo")
    _latch_loaded = True


async def _persist_latch(started_at: datetime) -> None:
    from app.database import db

    try:
        await db.db.subathon_state.update_one(
            {"_id": "ingest_gate"},
            {
                "$set": {
                    "latched": True,
                    "latched_at": datetime.now(timezone.utc),
                    "stream_started_at": started_at,
                }
            },
            upsert=True,
        )
    except Exception:
        logger.exception("Failed to persist ingest latch")


def _latch(started_at: datetime) -> None:
    global _ingest_latched
    if _ingest_latched:
        return
    _ingest_latched = True
    logger.info(
        "Subathon ingest latched on (stream started_at=%s, min=%s)",
        started_at.isoformat(),
        min_stream_started_at().isoformat(),
    )


async def try_latch_stream(started_at: datetime, *, source: str = "unknown") -> bool:
    """Latch ingest if this stream started after the overnight cutoff."""
    await load_ingest_latch()
    if _ingest_latched:
        return True
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    cutoff = min_stream_started_at()
    if started_at < cutoff:
        logger.info(
            "Ignoring stream from %s (started_at=%s before cutoff=%s)",
            source,
            started_at.isoformat(),
            cutoff.isoformat(),
        )
        return False
    _latch(started_at)
    await _persist_latch(started_at)
    logger.info("Subathon ingest enabled via %s", source)
    return True


async def _helix_stream_started_at() -> datetime | None:
    settings = get_settings()
    if not settings.twitch_oauth_token or not settings.twitch_client_id:
        return None
    channel = (settings.twitch_channel or "").lstrip("#").lower()
    headers = {
        "Authorization": f"Bearer {_bearer(settings.twitch_oauth_token)}",
        "Client-Id": settings.twitch_client_id,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{HELIX}/streams",
                headers=headers,
                params={"user_login": channel},
            )
        if resp.status_code != 200:
            logger.warning("Helix streams check failed (%s)", resp.status_code)
            return None
        rows = resp.json().get("data") or []
        if not rows:
            return None
        raw = rows[0].get("started_at")
        if not raw:
            return None
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        logger.exception("Helix streams check error")
        return None


async def watch_qualifying_stream(stop: asyncio.Event) -> None:
    """Poll Twitch until a live stream started after the leftover overnight one."""
    await load_ingest_latch()
    if _ingest_latched:
        return

    cutoff = min_stream_started_at()
    logger.info(
        "Waiting for subathon live (EventSub stream.online + Helix every %ss; cutoff %s)",
        HELIX_POLL_SECS,
        cutoff.isoformat(),
    )

    while not stop.is_set():
        started = await _helix_stream_started_at()
        if started is not None:
            if await try_latch_stream(started, source="helix"):
                return
        try:
            await asyncio.wait_for(stop.wait(), timeout=HELIX_POLL_SECS)
        except asyncio.TimeoutError:
            pass
