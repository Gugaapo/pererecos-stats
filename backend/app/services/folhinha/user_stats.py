"""Per-user Folhinha interaction stats from folhinha_events."""

from __future__ import annotations

from typing import Any

from app.database import db
from app.services.common.cache import get_stats_cache, set_stats_cache, stats_cache_key
from app.services.common.period import resolve_period_dates, date_range_to_utc_bounds
from app.services.common.query import get_platform_filter, IGNORED_BOTS

TOP_N = 5


def _period_match(period: str, start_date: str | None, end_date: str | None) -> dict:
    rng = resolve_period_dates(period, start_date, end_date)
    if not rng:
        return {}
    start_utc, end_utc = date_range_to_utc_bounds(rng[0], rng[1])
    return {"event_at": {"$gte": start_utc, "$lt": end_utc}}


async def _count(
    *,
    kind: str,
    field: str,
    username: str,
    period: str,
    platform: str,
    start_date: str | None,
    end_date: str | None,
    extra: dict | None = None,
) -> int:
    match: dict[str, Any] = {
        "kind": kind,
        field: username,
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
        **(extra or {}),
    }
    return await db.folhinha_events.count_documents(match)


async def _sum_delta(
    *,
    username: str,
    positive: bool,
    period: str,
    platform: str,
    start_date: str | None,
    end_date: str | None,
) -> int:
    match: dict[str, Any] = {
        "kind": "cookie_slot",
        "actor_username": username,
        "cookies_delta": {"$gt": 0} if positive else {"$lt": 0},
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
    }
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "total": {"$sum": "$cookies_delta" if positive else {"$abs": "$cookies_delta"}},
        }},
    ]
    rows = await db.folhinha_events.aggregate(pipeline).to_list(1)
    return int(rows[0]["total"]) if rows else 0


async def _avg_bonk_pct(
    username: str,
    period: str,
    platform: str,
    start_date: str | None,
    end_date: str | None,
) -> float | None:
    match: dict[str, Any] = {
        "kind": "bonk",
        "actor_username": username,
        "percentage": {"$ne": None},
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
    }
    pipeline = [
        {"$match": match},
        {"$group": {"_id": None, "avg": {"$avg": "$percentage"}, "n": {"$sum": 1}}},
    ]
    rows = await db.folhinha_events.aggregate(pipeline).to_list(1)
    if not rows or not rows[0].get("n"):
        return None
    return round(float(rows[0]["avg"]), 1)


async def _latest_cookies(
    username: str,
    period: str,
    platform: str,
    start_date: str | None,
    end_date: str | None,
) -> int | None:
    match: dict[str, Any] = {
        "actor_username": username,
        "cookies_balance": {"$ne": None},
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
    }
    row = await (
        db.folhinha_events.find(match)
        .sort("event_at", -1)
        .limit(1)
        .to_list(1)
    )
    if not row:
        return None
    return int(row[0]["cookies_balance"])


async def _top_partners(
    *,
    kind: str,
    self_field: str,
    partner_field: str,
    username: str,
    period: str,
    platform: str,
    start_date: str | None,
    end_date: str | None,
    limit: int = TOP_N,
    with_avg_pct: bool = False,
) -> list[dict]:
    match: dict[str, Any] = {
        "kind": kind,
        self_field: username,
        partner_field: {"$nin": [None, "", username, *list(IGNORED_BOTS)]},
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
    }
    group: dict[str, Any] = {
        "_id": f"${partner_field}",
        "count": {"$sum": 1},
        "platform": {"$last": "$platform"},
    }
    if with_avg_pct:
        group["avg_pct"] = {"$avg": "$percentage"}
        group["pct_n"] = {
            "$sum": {"$cond": [{"$ne": ["$percentage", None]}, 1, 0]},
        }

    pipeline = [
        {"$match": match},
        {"$group": group},
        {"$sort": {"count": -1, "_id": 1}},
        {"$limit": limit},
    ]
    rows = await db.folhinha_events.aggregate(pipeline).to_list(limit)
    out = []
    for r in rows:
        uname = r["_id"]
        entry = {
            "username": uname,
            "display_name": uname,
            "platform": r.get("platform") or "twitch",
            "count": int(r["count"]),
            "avg_percentage": None,
        }
        if with_avg_pct and r.get("pct_n"):
            entry["avg_percentage"] = round(float(r["avg_pct"]), 1)
        out.append(entry)
    return out


async def get_user_folhinha_stats(
    username: str,
    *,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict | None:
    """Build Folhinha profile stats for a login (lowercase)."""
    uname = (username or "").lower().strip()
    if not uname or uname in IGNORED_BOTS:
        return None

    cache_key = stats_cache_key(
        "user_folhinha",
        username=uname,
        period=period,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
    )
    hit = get_stats_cache(cache_key, ttl=120)
    if hit is not None:
        return hit

    kw = dict(period=period, platform=platform, start_date=start_date, end_date=end_date)

    bonks_given = await _count(kind="bonk", field="actor_username", username=uname, **kw)
    bonks_received = await _count(kind="bonk", field="target_username", username=uname, **kw)
    abracos_given = await _count(kind="abraco", field="actor_username", username=uname, **kw)
    abracos_received = await _count(kind="abraco", field="target_username", username=uname, **kw)
    survives = await _count(kind="roulette_survive", field="actor_username", username=uname, **kw)
    deaths = await _count(kind="roulette_death", field="actor_username", username=uname, **kw)

    stats = {
        "bonks_given": bonks_given,
        "bonks_received": bonks_received,
        "avg_bonk_pct": await _avg_bonk_pct(uname, **kw),
        "abracos_given": abracos_given,
        "abracos_received": abracos_received,
        "roulette_survives": survives,
        "roulette_deaths": deaths,
        "cookies_balance": await _latest_cookies(uname, **kw),
        "slot_won": await _sum_delta(username=uname, positive=True, **kw),
        "slot_lost": await _sum_delta(username=uname, positive=False, **kw),
        "top_bonk_targets": await _top_partners(
            kind="bonk",
            self_field="actor_username",
            partner_field="target_username",
            username=uname,
            with_avg_pct=True,
            **kw,
        ),
        "top_bonk_from": await _top_partners(
            kind="bonk",
            self_field="target_username",
            partner_field="actor_username",
            username=uname,
            with_avg_pct=True,
            **kw,
        ),
        "top_abraco_targets": await _top_partners(
            kind="abraco",
            self_field="actor_username",
            partner_field="target_username",
            username=uname,
            **kw,
        ),
        "top_abraco_from": await _top_partners(
            kind="abraco",
            self_field="target_username",
            partner_field="actor_username",
            username=uname,
            **kw,
        ),
    }

    has_any = any([
        bonks_given, bonks_received, abracos_given, abracos_received,
        survives, deaths, stats["cookies_balance"] is not None,
        stats["slot_won"], stats["slot_lost"],
    ])
    if not has_any:
        set_stats_cache(cache_key, None)
        return None

    set_stats_cache(cache_key, stats)
    return stats
