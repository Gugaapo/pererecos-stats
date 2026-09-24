"""Marathon state store: poll timer feed, derive increments, cache in Mongo.

All DB writes for the timer surface live here so routers stay thin.
Upstream is the public vinnytasso /timer feed by default (not request-path Pixie).
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.config import get_settings
from app.database import db
from app.services.subathon_insights import (
    HOURS_ABOVE_THRESHOLD_SECONDS,
    feed_cross_check,
    new_crossings,
    records_update,
)
from app.services.subathon_math import (
    Marathon,
    brt_date,
    derive_increment,
    granted_seconds_from_tip,
    parse_dt,
)
from app.services.timer_client import TimerFeedError, client as timer_client

logger = logging.getLogger(__name__)

CURRENT_ID = "current"


def _observation_remaining(m: Marathon) -> int | None:
    """Remaining at observation time (frozen while paused)."""
    if m.ends_at is None or m.observed_at is None:
        return None
    anchor = m.paused_at if (m.paused and m.paused_at) else m.observed_at
    ends = m.ends_at
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return max(0, int((ends - anchor).total_seconds()))


async def _bump_health(*, ok: bool, gap_seconds: int | None = None) -> None:
    """Per-BRT-day poller health counters (reset when the BRT day rolls)."""
    now = datetime.now(timezone.utc)
    day = brt_date(now)
    doc = await db.marathon_health.find_one({"_id": CURRENT_ID}) or {}
    polls_ok = int(doc.get("polls_ok") or 0)
    polls_fail = int(doc.get("polls_fail") or 0)
    max_gap = int(doc.get("max_gap_seconds") or 0)
    if doc.get("day") != day:
        polls_ok = 0
        polls_fail = 0
        max_gap = 0
    update: dict[str, Any] = {
        "day": day,
        "polls_ok": polls_ok,
        "polls_fail": polls_fail,
        "max_gap_seconds": max_gap,
    }
    if ok:
        last_gap = max(0, int(gap_seconds or 0))
        update["polls_ok"] = polls_ok + 1
        update["last_ok_at"] = now
        update["last_gap_seconds"] = last_gap
        update["max_gap_seconds"] = max(max_gap, last_gap)
    else:
        update["polls_fail"] = polls_fail + 1
        update["last_fail_at"] = now
    await db.marathon_health.update_one(
        {"_id": CURRENT_ID}, {"$set": update}, upsert=True
    )


def _doc_to_marathon(doc: dict[str, Any]) -> Marathon | None:
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


async def load_cached() -> dict | None:
    return await db.marathon_state.find_one({"_id": CURRENT_ID})


async def _recompute_daily(day: str) -> None:
    pipeline = [
        {"$match": {"brt_date": day}},
        {
            "$group": {
                "_id": None,
                "added_seconds": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$kind", "grant"]},
                            {"$max": ["$granted_seconds", 0]},
                            0,
                        ]
                    }
                },
                "increase_count": {
                    "$sum": {"$cond": [{"$eq": ["$kind", "grant"]}, 1, 0]}
                },
                "biggest_increase_seconds": {
                    "$max": {
                        "$cond": [
                            {"$eq": ["$kind", "grant"]},
                            "$granted_seconds",
                            0,
                        ]
                    }
                },
            }
        },
    ]
    rows = await db.marathon_increases.aggregate(pipeline).to_list(1)
    agg = rows[0] if rows else {}
    money = await db.marathon_txn.aggregate(
        [
            {"$match": {"brt_date": day}},
            {
                "$group": {
                    "_id": None,
                    "money_minor_units": {"$sum": "$amount_minor_units"},
                    "txn_count": {"$sum": 1},
                    "biggest_txn_minor_units": {"$max": "$amount_minor_units"},
                }
            },
        ]
    ).to_list(1)
    money_agg = money[0] if money else {}
    paused_seconds = 0
    async for p in db.marathon_pauses.find({}):
        start = p.get("start_at")
        if isinstance(start, datetime) and brt_date(start) == day:
            paused_seconds += int(p.get("seconds") or 0)

    await db.marathon_daily.update_one(
        {"date": day},
        {
            "$set": {
                "date": day,
                "added_seconds": int(agg.get("added_seconds") or 0),
                "increase_count": int(agg.get("increase_count") or 0),
                "biggest_increase_seconds": int(agg.get("biggest_increase_seconds") or 0),
                "paused_seconds": paused_seconds,
                "money_minor_units": int(money_agg.get("money_minor_units") or 0),
                "txn_count": int(money_agg.get("txn_count") or 0),
                "biggest_txn_minor_units": int(money_agg.get("biggest_txn_minor_units") or 0),
                "computed_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {"tracked_seconds": 0},
        },
        upsert=True,
    )


async def record_observation(
    m: Marathon,
    *,
    source: str,
    heartbeat: bool = False,
    status: str | None = None,
    feed_seconds: int | None = None,
    feed_value: str | None = None,
) -> dict:
    settings = get_settings()
    prev_doc = await load_cached()
    prev = _doc_to_marathon(prev_doc) if prev_doc else None
    now = m.observed_at
    prev_remaining = _observation_remaining(prev) if prev else None
    cur_remaining = _observation_remaining(m)
    cross = feed_cross_check(feed_seconds, m.ends_at, m.observed_at)

    decision = {
        "kind": "none",
        "granted_seconds": 0,
        "raw_delta_seconds": 0,
        "pause_seconds": 0,
        "pause_credit_seconds": 0,
    }
    precision_seconds = 0
    if prev is not None:
        precision_seconds = abs(int((m.observed_at - prev.observed_at).total_seconds()))
        decision = derive_increment(
            prev,
            m,
            pause_tolerance=settings.subathon_pause_credit_tolerance_seconds,
        )

    if decision["kind"] in ("grant", "pause_credit", "adjustment"):
        insert_result = await db.marathon_increases.insert_one(
            {
                "at": now,
                "granted_seconds": int(decision["granted_seconds"]),
                "raw_delta_seconds": int(decision["raw_delta_seconds"]),
                "ends_at_before": prev.ends_at if prev else None,
                "ends_at_after": m.ends_at,
                "kind": decision["kind"],
                "source": source,
                "precision_seconds": precision_seconds,
                "brt_date": brt_date(now),
                "status": status,
            }
        )
        if decision["kind"] == "grant" and int(decision["granted_seconds"]) > 0:
            try:
                from app.services import timer_attribution as attr

                await attr.attribute_increase(
                    increase_at=now if now.tzinfo else now.replace(tzinfo=timezone.utc),
                    granted_seconds=int(decision["granted_seconds"]),
                    precision_seconds=precision_seconds,
                    increase_id=insert_result.inserted_id,
                )
            except Exception:
                logger.exception("Increase attribution failed")

    # Pause intervals: open on paused rise, close on fall
    if prev is not None:
        if not prev.paused and m.paused:
            await db.marathon_pauses.insert_one(
                {
                    "start_at": m.paused_at or now,
                    "end_at": None,
                    "seconds": 0,
                    "open": True,
                }
            )
        elif prev.paused and not m.paused:
            open_pause = await db.marathon_pauses.find_one(
                {"open": True}, sort=[("start_at", -1)]
            )
            if open_pause:
                start = open_pause["start_at"]
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                seconds = max(0, int((now - start).total_seconds()))
                await db.marathon_pauses.update_one(
                    {"_id": open_pause["_id"]},
                    {"$set": {"end_at": now, "seconds": seconds, "open": False}},
                )

    day = brt_date(now)
    if decision["kind"] in ("grant", "pause_credit", "adjustment") or not prev_doc:
        await _recompute_daily(day)

    # Track tracked_seconds roughly as wall gap when running
    if prev is not None and not prev.paused and not m.paused:
        await db.marathon_daily.update_one(
            {"date": day},
            {"$inc": {"tracked_seconds": precision_seconds},
             "$set": {"ends_at_last": m.ends_at}},
            upsert=True,
        )

    # Records / milestones / hours-above accumulator (survive the 90d snapshot TTL)
    rec_doc = await db.marathon_records.find_one({"_id": CURRENT_ID}) or {}
    hours_above_7d = int(rec_doc.get("hours_above_7d_seconds") or 0)
    updated_rec = records_update(rec_doc, cur_remaining, now)
    updated_rec["hours_above_7d_seconds"] = hours_above_7d
    updated_rec["_id"] = CURRENT_ID
    await db.marathon_records.update_one(
        {"_id": CURRENT_ID}, {"$set": updated_rec}, upsert=True
    )
    if (
        prev_remaining is not None
        and prev_remaining >= HOURS_ABOVE_THRESHOLD_SECONDS
        and precision_seconds > 0
    ):
        await db.marathon_records.update_one(
            {"_id": CURRENT_ID},
            {"$inc": {"hours_above_7d_seconds": min(precision_seconds, 300)}},
            upsert=True,
        )

    for crossing in new_crossings(prev_remaining, cur_remaining):
        await db.marathon_milestones.update_one(
            {
                "threshold_seconds": crossing["threshold_seconds"],
                "direction": crossing["direction"],
            },
            {
                "$setOnInsert": {
                    "threshold_seconds": crossing["threshold_seconds"],
                    "direction": crossing["direction"],
                    "label": crossing["label"],
                    "at": now,
                    "remaining_at_event": crossing["remaining_at_event"],
                    "estimated": False,
                }
            },
            upsert=True,
        )

    await _bump_health(ok=True, gap_seconds=precision_seconds)

    changed = (
        prev is None
        or prev.ends_at != m.ends_at
        or prev.state != m.state
        or prev.paused != m.paused
        or prev.locked != m.locked
        or prev.direction != m.direction
        or decision["kind"] != "none"
    )

    state_doc = {
        "_id": CURRENT_ID,
        "state": m.state,
        "direction": m.direction,
        "locked": m.locked,
        "paused": m.paused,
        "ends_at": m.ends_at,
        "paused_at": m.paused_at,
        "rules": m.rules,
        "observed_at": m.observed_at,
        "fetched_at": datetime.now(timezone.utc),
        "last_success_at": datetime.now(timezone.utc),
        "error_count": 0,
        "creator_id": None,
        "status": status,
        "feed_seconds": feed_seconds,
        "cross_check_seconds": cross,
    }
    # Preserve rules from previous if new observation has empty rules
    if not m.rules and prev_doc and prev_doc.get("rules"):
        state_doc["rules"] = prev_doc["rules"]
    if prev_doc and prev_doc.get("creator_id"):
        state_doc["creator_id"] = prev_doc["creator_id"]

    await db.marathon_state.update_one(
        {"_id": CURRENT_ID}, {"$set": state_doc}, upsert=True
    )

    write_snapshot = changed or heartbeat
    if write_snapshot:
        await db.marathon_snapshots.insert_one(
            {
                "at": now,
                "ends_at": m.ends_at,
                "state": m.state,
                "paused": m.paused,
                "locked": m.locked,
                "source": source,
                "raw_delta_seconds": int(decision["raw_delta_seconds"]),
                "heartbeat": bool(heartbeat and not changed),
                "status": status,
                "feed_seconds": feed_seconds,
                "feed_value": feed_value,
                "cross_check_seconds": cross,
            }
        )

    logger.info(
        "marathon observation source=%s kind=%s raw_delta=%s pause=%s granted=%s changed=%s",
        source,
        decision["kind"],
        decision["raw_delta_seconds"],
        decision["pause_seconds"],
        decision["granted_seconds"],
        changed,
    )
    return {"changed": changed, "decision": decision, "state": state_doc}


async def poll_forever(stop: asyncio.Event) -> None:
    settings = get_settings()
    poll_s = max(5, int(settings.timer_poll_seconds))
    heartbeat_s = max(poll_s, int(settings.timer_snapshot_heartbeat_seconds))
    last_heartbeat: datetime | None = None
    last_snapshot_key: tuple | None = None
    error_backoff = poll_s

    logger.info("Marathon poller starting (timer feed every %ss)", poll_s)

    while not stop.is_set():
        try:
            feed = await timer_client.get_timer()
            m = feed.marathon
            # Stamp creator from feed payload when present
            creator = (feed.payload or {}).get("creator_id")
            key = (
                m.ends_at.isoformat() if m.ends_at else None,
                m.state,
                m.paused,
                m.locked,
                m.direction,
            )
            now = datetime.now(timezone.utc)
            need_heartbeat = (
                last_heartbeat is None
                or (now - last_heartbeat).total_seconds() >= heartbeat_s
            )
            changed = key != last_snapshot_key
            first_after_start = last_snapshot_key is None
            if changed or need_heartbeat:
                await record_observation(
                    m,
                    source="poll",
                    heartbeat=(need_heartbeat and not changed) or first_after_start,
                    status=feed.status,
                    feed_seconds=feed.feed_seconds,
                    feed_value=feed.feed_value,
                )
                if creator:
                    await db.marathon_state.update_one(
                        {"_id": CURRENT_ID}, {"$set": {"creator_id": creator}}
                    )
                last_snapshot_key = key
                if need_heartbeat:
                    last_heartbeat = now
                logger.info(
                    "Marathon poll ok mode=%s ends_at=%s remaining≈%s",
                    m.timer_mode(),
                    m.ends_at,
                    m.remaining_at(now),
                )
            else:
                # Still a successful upstream read — keep last_success_at fresh so the
                # public timer does not flip to stale between heartbeats.
                await db.marathon_state.update_one(
                    {"_id": CURRENT_ID},
                    {
                        "$set": {
                            "last_success_at": now,
                            "fetched_at": now,
                            "error_count": 0,
                            "status": feed.status,
                            "feed_seconds": feed.feed_seconds,
                            **({"creator_id": creator} if creator else {}),
                        }
                    },
                    upsert=True,
                )
                await _bump_health(ok=True, gap_seconds=0)
            error_backoff = poll_s
        except TimerFeedError as exc:
            logger.warning("Marathon poll failed: %s", exc)
            await db.marathon_state.update_one(
                {"_id": CURRENT_ID},
                {"$inc": {"error_count": 1}},
                upsert=True,
            )
            await _bump_health(ok=False)
            error_backoff = min(poll_s * 10, max(poll_s, (exc.retry_after or error_backoff) * 1.5))
            error_backoff = error_backoff * (0.8 + random.random() * 0.4)
        except Exception:
            logger.exception("Marathon poller unexpected error")
            error_backoff = min(poll_s * 10, error_backoff * 1.5)

        try:
            await asyncio.wait_for(stop.wait(), timeout=error_backoff if error_backoff != poll_s else poll_s)
            break
        except asyncio.TimeoutError:
            continue

    logger.info("Marathon poller stopped")


async def _apply_timer_updated_cache(payload: dict[str, Any]) -> None:
    """Refresh Agora display from SSE without touching poll-owned ends_at.

    Writing ends_at here used to erase poller deltas (SSE moved ends_at first,
    then poll saw raw_delta=0 and never inserted marathon_increases).
    """
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    if not current:
        return
    now = datetime.now(timezone.utc)
    ends_at = parse_dt(current.get("ends_at"))
    observed = parse_dt(payload.get("observed_at")) or now
    cached = await load_cached() or {}
    if ends_at is None:
        ends_at = parse_dt(cached.get("display_ends_at") or cached.get("ends_at"))
        if ends_at is None:
            raw = cached.get("display_ends_at") or cached.get("ends_at")
            if isinstance(raw, datetime):
                ends_at = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    update: dict[str, Any] = {
        "display_state": str(current.get("state") or cached.get("state") or "unavailable"),
        "display_direction": str(
            current.get("direction") or cached.get("direction") or "increase"
        ),
        "display_locked": (
            bool(current.get("locked")) if "locked" in current else bool(cached.get("locked"))
        ),
        "display_paused": (
            bool(current.get("paused")) if "paused" in current else bool(cached.get("paused"))
        ),
        "last_sse_at": now,
        "last_sse_observed_at": observed,
        "error_count": 0,
    }
    if ends_at is not None:
        update["display_ends_at"] = ends_at
    if current.get("seconds") is not None:
        update["display_feed_seconds"] = current.get("seconds")
    if current.get("value") is not None:
        update["display_feed_value"] = current.get("value")
    # Keep header "fresh" without claiming a poll success that advanced ends_at.
    update["fetched_at"] = now
    await db.marathon_state.update_one({"_id": CURRENT_ID}, {"$set": update}, upsert=True)

    # Recover grants when SSE saw an ends_at jump the poller never recorded.
    prev = payload.get("previous") if isinstance(payload.get("previous"), dict) else {}
    prev_ends = parse_dt(prev.get("ends_at"))
    if ends_at is not None and prev_ends is not None:
        raw = int((ends_at - prev_ends).total_seconds())
        if raw > 0:
            await _ensure_sse_grant(
                at=observed,
                granted_seconds=raw,
                ends_at_before=prev_ends,
                ends_at_after=ends_at,
            )


def _mongo_dt(dt: datetime) -> datetime:
    """Store/compare as naive UTC to match poller marathon_increases docs."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


async def _ensure_sse_grant(
    *,
    at: datetime,
    granted_seconds: int,
    ends_at_before: datetime,
    ends_at_after: datetime,
) -> bool:
    """Insert a grant from timer.updated if no nearby poll grant exists."""
    if granted_seconds <= 0:
        return False
    at_m = _mongo_dt(at)
    before_m = _mongo_dt(ends_at_before)
    after_m = _mongo_dt(ends_at_after)
    window = timedelta(seconds=max(90, get_settings().attribution_window_seconds))
    existing = await db.marathon_increases.find_one(
        {
            "kind": "grant",
            "granted_seconds": granted_seconds,
            "at": {"$gte": at_m - window, "$lte": at_m + window},
        }
    )
    if existing:
        return False
    # Also skip if any grant already covers this ends_at_after.
    by_ends = await db.marathon_increases.find_one(
        {"kind": "grant", "ends_at_after": after_m}
    )
    if by_ends:
        return False
    doc = {
        "at": at_m,
        "granted_seconds": int(granted_seconds),
        "raw_delta_seconds": int(granted_seconds),
        "ends_at_before": before_m,
        "ends_at_after": after_m,
        "kind": "grant",
        "source": "sse",
        "precision_seconds": 1,
        "brt_date": brt_date(at if at.tzinfo else at.replace(tzinfo=timezone.utc)),
        "status": None,
    }
    result = await db.marathon_increases.insert_one(doc)
    logger.info(
        "SSE recovered grant +%ss at %s (poll had missed ends_at jump)",
        granted_seconds,
        at_m.isoformat(),
    )
    try:
        from app.services import timer_attribution as attr

        await attr.attribute_increase(
            increase_at=at if at.tzinfo else at.replace(tzinfo=timezone.utc),
            granted_seconds=int(granted_seconds),
            precision_seconds=1,
            increase_id=result.inserted_id,
        )
    except Exception:
        logger.exception("SSE grant attribution failed")
    # Align poll-owned ends_at so the next poll does not double-count.
    await db.marathon_state.update_one(
        {"_id": CURRENT_ID},
        {
            "$set": {
                "ends_at": after_m,
                "observed_at": at_m,
                "last_success_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    return True


async def recover_missed_sse_grants(*, lookback_hours: float = 72.0) -> int:
    """Replay stored timer.updated jumps into marathon_increases when poll missed them."""
    since = datetime.now(timezone.utc) - timedelta(hours=max(0.1, lookback_hours))
    since_m = _mongo_dt(since)
    recovered = 0
    cursor = db.feed_events.find(
        {"type": "timer.updated", "at": {"$gte": since_m}}
    ).sort("at", 1)
    async for ev in cursor:
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
        prev = payload.get("previous") if isinstance(payload.get("previous"), dict) else {}
        ends_at = parse_dt(current.get("ends_at"))
        prev_ends = parse_dt(prev.get("ends_at"))
        if ends_at is None or prev_ends is None:
            continue
        raw = int((ends_at - prev_ends).total_seconds())
        if raw <= 0:
            continue
        observed = parse_dt(payload.get("observed_at")) or parse_dt(ev.get("at"))
        if observed is None:
            continue
        if await _ensure_sse_grant(
            at=observed,
            granted_seconds=raw,
            ends_at_before=prev_ends,
            ends_at_after=ends_at,
        ):
            recovered += 1
    if recovered:
        logger.info("Recovered %s missed SSE grants from feed_events", recovered)
    return recovered


async def handle_stream_event(
    event_type: str,
    payload: dict[str, Any] | None,
    sse_id: str | None,
) -> None:
    from app.services import timer_attribution as attr

    if event_type == "handshake":
        await db.marathon_state.update_one(
            {"_id": CURRENT_ID},
            {"$set": {"last_sse_handshake_at": datetime.now(timezone.utc), "sse_connected": True}},
            upsert=True,
        )
        return
    if event_type == "timer.updated" and isinstance(payload, dict):
        await _apply_timer_updated_cache(payload)
        await attr.store_feed_event(event_type, payload, sse_id=sse_id)
        return
    if event_type.startswith(("twitch.", "pixie.", "timer.")):
        await attr.store_feed_event(event_type, payload, sse_id=sse_id)
        return
    logger.debug("Ignoring SSE event type=%s", event_type)


async def stream_forever(stop: asyncio.Event) -> None:
    from app.services.timer_sse_client import stream_client

    await stream_client.run_forever(stop, handle_stream_event)


async def rebuild_daily(days: int = 400) -> int:
    cursor = db.marathon_increases.aggregate(
        [{"$group": {"_id": "$brt_date"}}, {"$sort": {"_id": 1}}, {"$limit": days}]
    )
    count = 0
    async for row in cursor:
        day = row["_id"]
        if day:
            await _recompute_daily(day)
            count += 1
    return count


async def handle_webhook_event(webhook_id: str, payload: dict) -> None:
    """Insert-first dedupe; money path only — poller owns time increments."""
    try:
        await db.pixie_webhook_events.insert_one(
            {
                "webhook_id": webhook_id,
                "event_id": payload.get("id"),
                "type": payload.get("type"),
                "received_at": datetime.now(timezone.utc),
                "body_raw": payload,
            }
        )
    except DuplicateKeyError:
        return

    if payload.get("type") != "transaction.confirmed":
        return

    data = (payload.get("data") or {}).get("transaction") or {}
    txn_id = data.get("id")
    if not txn_id:
        return

    amount = data.get("amount") or {}
    converted = data.get("converted_amount")
    if converted and converted.get("minor_units") is not None:
        minor = int(converted["minor_units"])
        currency = str(converted.get("currency") or amount.get("currency") or "BRL")
    else:
        minor = int(amount.get("minor_units") or 0)
        currency = str(amount.get("currency") or "BRL")

    confirmed_at = parse_dt(data.get("confirmed_at")) or datetime.now(timezone.utc)
    created_at = parse_dt(data.get("created_at"))
    cached = await load_cached()
    rules = (cached or {}).get("rules") or {}
    granted = granted_seconds_from_tip(minor, rules)
    day = brt_date(confirmed_at)

    try:
        await db.marathon_txn.insert_one(
            {
                "txn_id": txn_id,
                "amount_minor_units": minor,
                "currency": currency,
                "converted_minor_units": (
                    int(converted["minor_units"])
                    if converted and converted.get("minor_units") is not None
                    else None
                ),
                "created_at": created_at,
                "confirmed_at": confirmed_at,
                "granted_seconds": granted,
                "brt_date": day,
                "webhook_id": webhook_id,
            }
        )
    except DuplicateKeyError:
        return

    await _recompute_daily(day)
    logger.info(
        "Pixie txn accepted txn_id=%s minor=%s granted=%s day=%s",
        txn_id,
        minor,
        granted,
        day,
    )
