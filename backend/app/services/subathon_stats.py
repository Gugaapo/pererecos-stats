"""Aggregation helpers for /subathon/* stats. Platform-agnostic; no platform param."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import get_settings
from app.database import db
from app.services.subathon_math import humanize_seconds, parse_dt
from app.services.subathon_service import get_timer


async def daily_series(days: int) -> list[dict]:
    days = max(1, min(400, int(days)))
    cursor = db.marathon_daily.find({}).sort("date", -1).limit(days)
    rows = []
    async for doc in cursor:
        rows.append(
            {
                "date": doc.get("date"),
                "added_seconds": int(doc.get("added_seconds") or 0),
                "increase_count": int(doc.get("increase_count") or 0),
                "biggest_increase_seconds": int(doc.get("biggest_increase_seconds") or 0),
                "paused_seconds": int(doc.get("paused_seconds") or 0),
                "tracked_seconds": int(doc.get("tracked_seconds") or 0),
                "money_minor_units": int(doc.get("money_minor_units") or 0),
                "txn_count": int(doc.get("txn_count") or 0),
                "biggest_txn_minor_units": int(doc.get("biggest_txn_minor_units") or 0),
            }
        )
    rows.reverse()
    return rows


async def overview() -> dict:
    daily = await daily_series(400)
    days_tracked = len(daily)
    total_added = sum(d["added_seconds"] for d in daily)
    increase_count = sum(d["increase_count"] for d in daily)

    biggest_day = None
    most_static = None
    for d in daily:
        if biggest_day is None or d["added_seconds"] > biggest_day["added_seconds"]:
            biggest_day = {"date": d["date"], "added_seconds": d["added_seconds"]}
        if d["tracked_seconds"] >= int(86400 * 0.9):
            if most_static is None or d["added_seconds"] < most_static["added_seconds"]:
                most_static = {"date": d["date"], "added_seconds": d["added_seconds"]}

    # streaks: consecutive days with added_seconds > 0
    longest = current = 0
    run = 0
    for d in daily:
        if d["added_seconds"] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    current = 0
    for d in reversed(daily):
        if d["added_seconds"] > 0:
            current += 1
        else:
            break

    paused_total = 0
    async for p in db.marathon_pauses.find({}):
        paused_total += int(p.get("seconds") or 0)

    first_obs = None
    first_snap = await db.marathon_snapshots.find_one(sort=[("at", 1)])
    if first_snap and first_snap.get("at"):
        first_obs = first_snap["at"]

    longest_gap = None
    prev_at = None
    async for snap in db.marathon_snapshots.find({"heartbeat": {"$ne": True}}).sort(
        "at", 1
    ):
        at = snap.get("at")
        if isinstance(at, datetime) and prev_at is not None:
            gap = int((at - prev_at).total_seconds())
            if longest_gap is None or gap > longest_gap["seconds"]:
                longest_gap = {
                    "start_at": prev_at,
                    "end_at": at,
                    "seconds": gap,
                }
        if isinstance(at, datetime):
            prev_at = at

    timer = await get_timer()
    avg = int(total_added // days_tracked) if days_tracked else 0

    return {
        "days_tracked": days_tracked,
        "first_observation": first_obs,
        "total_added_seconds": total_added,
        "biggest_day": biggest_day,
        "most_static_day": most_static,
        "longest_active_streak": longest,
        "current_active_streak": current,
        "longest_gap": longest_gap,
        "paused_total_seconds": paused_total,
        "increase_count": increase_count,
        "avg_added_per_day_seconds": avg,
        "current_remaining_seconds": timer.get("remaining_seconds"),
    }


async def hourly_profile() -> list[dict]:
    pipeline = [
        {"$match": {"kind": "grant", "granted_seconds": {"$gt": 0}}},
        {
            "$group": {
                "_id": {
                    "$hour": {"date": "$at", "timezone": "America/Sao_Paulo"}
                },
                "added_seconds": {"$sum": "$granted_seconds"},
                "increase_count": {"$sum": 1},
            }
        },
    ]
    buckets = {h: {"hour": h, "added_seconds": 0, "increase_count": 0} for h in range(24)}
    async for row in db.marathon_increases.aggregate(pipeline):
        h = int(row["_id"])
        buckets[h] = {
            "hour": h,
            "added_seconds": int(row.get("added_seconds") or 0),
            "increase_count": int(row.get("increase_count") or 0),
        }
    return [buckets[h] for h in range(24)]


async def recent_increases(limit: int, offset: int) -> dict:
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    total = await db.marathon_increases.count_documents({})
    items = []
    cursor = (
        db.marathon_increases.find({})
        .sort("at", -1)
        .skip(offset)
        .limit(limit)
    )
    async for doc in cursor:
        items.append(
            {
                "at": doc.get("at"),
                "granted_seconds": int(doc.get("granted_seconds") or 0),
                "raw_delta_seconds": int(doc.get("raw_delta_seconds") or 0),
                "kind": doc.get("kind"),
                "source": doc.get("source"),
                "precision_seconds": int(doc.get("precision_seconds") or 0),
                "brt_date": doc.get("brt_date"),
            }
        )
    return {"total": total, "items": items}


async def contributions() -> dict:
    pipeline = [
        {
            "$group": {
                "_id": None,
                "money_minor_units": {"$sum": "$amount_minor_units"},
                "txn_count": {"$sum": 1},
                "biggest_txn": {"$max": "$amount_minor_units"},
                "granted_seconds_total": {"$sum": "$granted_seconds"},
                "first_txn_at": {"$min": "$confirmed_at"},
                "last_txn_at": {"$max": "$confirmed_at"},
            }
        }
    ]
    rows = await db.marathon_txn.aggregate(pipeline).to_list(1)
    if not rows:
        return {
            "money_minor_units": 0,
            "txn_count": 0,
            "biggest_txn": 0,
            "avg_txn_minor_units": 0,
            "first_txn_at": None,
            "last_txn_at": None,
            "granted_seconds_total": 0,
            "implied_brl_per_live_hour": None,
        }
    r = rows[0]
    count = int(r.get("txn_count") or 0)
    money = int(r.get("money_minor_units") or 0)
    granted = int(r.get("granted_seconds_total") or 0)
    avg = int(money // count) if count else 0
    implied = None
    if granted > 0:
        # minor units per live hour of granted time
        implied = int((money * 3600) // granted)
    return {
        "money_minor_units": money,
        "txn_count": count,
        "biggest_txn": int(r.get("biggest_txn") or 0),
        "avg_txn_minor_units": avg,
        "first_txn_at": r.get("first_txn_at"),
        "last_txn_at": r.get("last_txn_at"),
        "granted_seconds_total": granted,
        "implied_brl_per_live_hour": implied,
    }


async def rules_snapshot() -> dict:
    cached = await db.marathon_state.find_one({"_id": "current"})
    rules = (cached or {}).get("rules") or {}
    table = []
    tip = rules.get("tip") or {}
    if tip.get("each") and tip.get("seconds"):
        each = int(tip["each"])
        secs = int(tip["seconds"])
        table.append(
            {
                "label": f"R$ {each / 100:.2f}",
                "seconds": secs,
                "human": humanize_seconds(secs),
            }
        )
    twitch = rules.get("twitch") or {}
    for key, label in (
        ("prime_sub", "Twitch Prime"),
        ("tier_1_sub", "Twitch Tier 1"),
        ("tier_2_sub", "Twitch Tier 2"),
        ("tier_3_sub", "Twitch Tier 3"),
    ):
        item = twitch.get(key) or {}
        if item.get("seconds"):
            s = int(item["seconds"])
            table.append({"label": label, "seconds": s, "human": humanize_seconds(s)})
    bit = twitch.get("bit") or {}
    if bit.get("each") and bit.get("seconds"):
        table.append(
            {
                "label": f"{bit['each']} bits",
                "seconds": int(bit["seconds"]),
                "human": humanize_seconds(int(bit["seconds"])),
            }
        )
    return {"rules": rules, "conversion_table": table}


async def diagnostics() -> dict:
    settings = get_settings()
    cached = await db.marathon_state.find_one({"_id": "current"})
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    last_success = parse_dt((cached or {}).get("last_success_at"))
    stale = bool(
        last_success is None
        or (now - last_success).total_seconds() > settings.timer_stale_seconds
    )
    snapshots_24h = await db.marathon_snapshots.count_documents({"at": {"$gte": since}})
    increases_24h = await db.marathon_increases.count_documents({"at": {"$gte": since}})
    poll_rows = await db.marathon_increases.aggregate(
        [
            {"$match": {"at": {"$gte": since}, "kind": "grant", "source": "poll"}},
            {"$group": {"_id": None, "s": {"$sum": "$granted_seconds"}}},
        ]
    ).to_list(1)
    poll_granted = int(poll_rows[0]["s"]) if poll_rows else 0
    wh_rows = await db.marathon_txn.aggregate(
        [
            {"$match": {"confirmed_at": {"$gte": since}}},
            {"$group": {"_id": None, "s": {"$sum": "$granted_seconds"}}},
        ]
    ).to_list(1)
    webhook_granted = int(wh_rows[0]["s"]) if wh_rows else 0
    ratio = None
    if poll_granted > 0 and webhook_granted > 0:
        ratio = round(min(poll_granted, webhook_granted) / max(poll_granted, webhook_granted), 4)
    return {
        "last_success_at": last_success,
        "error_count": int((cached or {}).get("error_count") or 0),
        "stale": stale,
        "snapshots_24h": snapshots_24h,
        "increases_24h": increases_24h,
        "poll_granted_seconds_24h": poll_granted,
        "webhook_granted_seconds_24h": webhook_granted,
        "agreement_ratio": ratio,
        "timer_feed_url": settings.timer_feed_url,
        "pixie_webhook_configured": settings.is_pixie_webhook_configured,
    }
