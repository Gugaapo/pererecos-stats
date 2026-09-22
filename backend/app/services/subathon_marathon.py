"""Marathon state store: poll timer feed, derive increments, cache in Mongo.

All DB writes for the timer surface live here so routers stay thin.
Upstream is the public vinnytasso /timer feed by default (not request-path Pixie).
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.config import get_settings
from app.database import db
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
    m: Marathon, *, source: str, heartbeat: bool = False
) -> dict:
    settings = get_settings()
    prev_doc = await load_cached()
    prev = _doc_to_marathon(prev_doc) if prev_doc else None
    now = m.observed_at

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
        await db.marathon_increases.insert_one(
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
            }
        )

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
            if changed or need_heartbeat:
                await record_observation(
                    m, source="poll", heartbeat=need_heartbeat and not changed
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
                            **({"creator_id": creator} if creator else {}),
                        }
                    },
                    upsert=True,
                )
            error_backoff = poll_s
        except TimerFeedError as exc:
            logger.warning("Marathon poll failed: %s", exc)
            await db.marathon_state.update_one(
                {"_id": CURRENT_ID},
                {"$inc": {"error_count": 1}},
                upsert=True,
            )
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
