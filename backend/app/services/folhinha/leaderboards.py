"""Folhinha tab leaderboards from folhinha_events."""

from __future__ import annotations

from typing import Any, Literal

from app.database import db
from app.services.common.cache import get_stats_cache, set_stats_cache, stats_cache_key
from app.services.common.period import resolve_period_dates, date_range_to_utc_bounds
from app.services.common.query import get_platform_filter, IGNORED_BOTS

BOT_ACTORS = list(IGNORED_BOTS)

BoardId = Literal[
    "bonkadores",
    "sacos-de-pancada",
    "mais-fortes",
    "mais-fracos",
    "mais-carinhos",
    "mais-fofos",
    "desvivedores",
    "sobreviventes",
    "cookie-cd",
    "mais-cookies",
    "slot-ganhos",
    "slot-perdas",
]

MIN_BONKS_FOR_AVG = 3


def _period_match(period: str, start_date: str | None, end_date: str | None) -> dict:
    rng = resolve_period_dates(period, start_date, end_date)
    if not rng:
        return {}
    start_utc, end_utc = date_range_to_utc_bounds(rng[0], rng[1])
    return {"event_at": {"$gte": start_utc, "$lt": end_utc}}


async def _count_leaderboard(
    *,
    kind: str,
    field: str,  # actor_username | target_username
    period: str,
    platform: str,
    limit: int,
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    match: dict[str, Any] = {
        "kind": kind,
        field: {"$nin": [None, "", *BOT_ACTORS]},
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
    }
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": f"${field}",
            "count": {"$sum": 1},
            "display_name": {"$last": f"${field}"},
            "platform": {"$last": "$platform"},
        }},
        {"$sort": {"count": -1, "_id": 1}},
        {"$limit": limit},
    ]
    rows = await db.folhinha_events.aggregate(pipeline).to_list(limit)
    out = []
    for i, r in enumerate(rows, start=1):
        uname = r["_id"]
        out.append({
            "rank": i,
            "username": uname,
            "display_name": r.get("display_name") or uname,
            "platform": r.get("platform") or "twitch",
            "count": int(r["count"]),
            "value": int(r["count"]),
            "value_label": "vezes",
        })
    return out


async def _avg_percentage_leaderboard(
    *,
    ascending: bool,
    period: str,
    platform: str,
    limit: int,
    start_date: str | None,
    end_date: str | None,
    min_bonks: int = MIN_BONKS_FOR_AVG,
) -> list[dict]:
    match: dict[str, Any] = {
        "kind": "bonk",
        "actor_username": {"$nin": [None, "", *BOT_ACTORS]},
        "percentage": {"$ne": None},
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
    }
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$actor_username",
            "avg_pct": {"$avg": "$percentage"},
            "count": {"$sum": 1},
            "platform": {"$last": "$platform"},
        }},
        {"$match": {"count": {"$gte": min_bonks}}},
        {"$sort": {"avg_pct": 1 if ascending else -1, "count": -1, "_id": 1}},
        {"$limit": limit},
    ]
    rows = await db.folhinha_events.aggregate(pipeline).to_list(limit)
    out = []
    for i, r in enumerate(rows, start=1):
        uname = r["_id"]
        avg = round(float(r["avg_pct"]), 1)
        out.append({
            "rank": i,
            "username": uname,
            "display_name": uname,
            "platform": r.get("platform") or "twitch",
            "count": int(r["count"]),
            "avg_percentage": avg,
            "value": avg,
            "value_label": "% médio",
        })
    return out


async def _cookie_balance_leaderboard(
    *,
    period: str,
    platform: str,
    limit: int,
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    """Latest known cookie balance per user (from claim / slot / status replies)."""
    match: dict[str, Any] = {
        "actor_username": {"$nin": [None, "", *BOT_ACTORS]},
        "cookies_balance": {"$ne": None},
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
    }
    pipeline = [
        {"$match": match},
        {"$sort": {"event_at": -1}},
        {"$group": {
            "_id": "$actor_username",
            "cookies": {"$first": "$cookies_balance"},
            "platform": {"$first": "$platform"},
            "as_of": {"$first": "$event_at"},
        }},
        {"$sort": {"cookies": -1, "_id": 1}},
        {"$limit": limit},
    ]
    rows = await db.folhinha_events.aggregate(pipeline).to_list(limit)
    out = []
    for i, r in enumerate(rows, start=1):
        uname = r["_id"]
        cookies = int(r["cookies"])
        out.append({
            "rank": i,
            "username": uname,
            "display_name": uname,
            "platform": r.get("platform") or "twitch",
            "count": cookies,
            "value": cookies,
            "value_label": "cookies",
        })
    return out


async def _slot_delta_leaderboard(
    *,
    mode: str,  # won | lost
    period: str,
    platform: str,
    limit: int,
    start_date: str | None,
    end_date: str | None,
) -> list[dict]:
    match: dict[str, Any] = {
        "kind": "cookie_slot",
        "actor_username": {"$nin": [None, "", *BOT_ACTORS]},
        "cookies_delta": {"$ne": None},
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
    }
    if mode == "won":
        match["cookies_delta"] = {"$gt": 0}
        sum_expr = {"$sum": "$cookies_delta"}
    else:
        match["cookies_delta"] = {"$lt": 0}
        sum_expr = {"$sum": {"$abs": "$cookies_delta"}}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$actor_username",
            "total": sum_expr,
            "count": {"$sum": 1},
            "platform": {"$last": "$platform"},
        }},
        {"$sort": {"total": -1, "count": -1, "_id": 1}},
        {"$limit": limit},
    ]
    rows = await db.folhinha_events.aggregate(pipeline).to_list(limit)
    out = []
    label = "cookies ganhos" if mode == "won" else "cookies perdidos"
    for i, r in enumerate(rows, start=1):
        uname = r["_id"]
        total = int(r["total"])
        out.append({
            "rank": i,
            "username": uname,
            "display_name": uname,
            "platform": r.get("platform") or "twitch",
            "count": total,
            "value": total,
            "value_label": label,
        })
    return out


BOARD_FETCHERS = {
    "bonkadores": lambda **kw: _count_leaderboard(kind="bonk", field="actor_username", **kw),
    "sacos-de-pancada": lambda **kw: _count_leaderboard(kind="bonk", field="target_username", **kw),
    "mais-fortes": lambda **kw: _avg_percentage_leaderboard(ascending=False, **kw),
    "mais-fracos": lambda **kw: _avg_percentage_leaderboard(ascending=True, **kw),
    "mais-carinhos": lambda **kw: _count_leaderboard(kind="abraco", field="actor_username", **kw),
    "mais-fofos": lambda **kw: _count_leaderboard(kind="abraco", field="target_username", **kw),
    "desvivedores": lambda **kw: _count_leaderboard(kind="roulette_death", field="actor_username", **kw),
    "sobreviventes": lambda **kw: _count_leaderboard(kind="roulette_survive", field="actor_username", **kw),
    "cookie-cd": lambda **kw: _count_leaderboard(kind="cookie_cd", field="actor_username", **kw),
    "mais-cookies": lambda **kw: _cookie_balance_leaderboard(**kw),
    "slot-ganhos": lambda **kw: _slot_delta_leaderboard(mode="won", **kw),
    "slot-perdas": lambda **kw: _slot_delta_leaderboard(mode="lost", **kw),
}


async def get_folhinha_board(
    board_id: str,
    *,
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    fetcher = BOARD_FETCHERS.get(board_id)
    if not fetcher:
        return []
    cache_key = stats_cache_key(
        "folhinha_tab",
        board=board_id,
        period=period,
        platform=platform,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )
    hit = get_stats_cache(cache_key, ttl=300)
    if hit is not None:
        return hit
    rows = await fetcher(
        period=period,
        platform=platform,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )
    set_stats_cache(cache_key, rows)
    return rows


BONK_PCT_BUCKETS = (
    (0, 20, "0–20%"),
    (21, 40, "21–40%"),
    (41, 60, "41–60%"),
    (61, 80, "61–80%"),
    (81, 100, "81–100%"),
)


async def get_folhinha_overview(
    *,
    period: str = "all",
    platform: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Aggregates for Folhinha tab overview (one payload with the board batch)."""
    import asyncio

    cache_key = stats_cache_key(
        "folhinha_overview_v2",
        period=period,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
    )
    hit = get_stats_cache(cache_key, ttl=300)
    if hit is not None:
        return hit

    base: dict[str, Any] = {
        **_period_match(period, start_date, end_date),
        **get_platform_filter(platform),
    }

    async def _kind_totals():
        rows = await db.folhinha_events.aggregate([
            {"$match": base},
            {"$group": {"_id": "$kind", "n": {"$sum": 1}}},
        ]).to_list(50)
        return {r["_id"]: int(r["n"]) for r in rows if r.get("_id")}

    async def _histogram():
        rows = await db.folhinha_events.aggregate([
            {"$match": {**base, "kind": "bonk", "percentage": {"$ne": None}}},
            {"$bucket": {
                "groupBy": "$percentage",
                "boundaries": [0, 21, 41, 61, 81, 101],
                "default": "other",
                "output": {"count": {"$sum": 1}},
            }},
        ]).to_list(10)
        return {r["_id"]: int(r["count"]) for r in rows}

    async def _top_pair():
        """Top undirected duo by mutual bonks (A→B + B→A)."""
        rows = await db.folhinha_events.aggregate([
            {"$match": {
                **base,
                "kind": "bonk",
                "actor_username": {"$nin": [None, "", *BOT_ACTORS]},
                "target_username": {"$nin": [None, "", *BOT_ACTORS]},
                "$expr": {"$ne": ["$actor_username", "$target_username"]},
            }},
            {"$addFields": {
                "pair_lo": {
                    "$cond": [
                        {"$lt": ["$actor_username", "$target_username"]},
                        "$actor_username",
                        "$target_username",
                    ]
                },
                "pair_hi": {
                    "$cond": [
                        {"$lt": ["$actor_username", "$target_username"]},
                        "$target_username",
                        "$actor_username",
                    ]
                },
            }},
            {"$group": {
                "_id": {"lo": "$pair_lo", "hi": "$pair_hi"},
                "total": {"$sum": 1},
                "lo_to_hi": {
                    "$sum": {"$cond": [{"$eq": ["$actor_username", "$pair_lo"]}, 1, 0]}
                },
                "hi_to_lo": {
                    "$sum": {"$cond": [{"$eq": ["$actor_username", "$pair_hi"]}, 1, 0]}
                },
                "platform": {"$last": "$platform"},
            }},
            {"$sort": {"total": -1}},
            {"$limit": 1},
        ]).to_list(1)
        if not rows:
            return None
        pr = rows[0]
        lo = pr["_id"]["lo"]
        hi = pr["_id"]["hi"]
        lo_to_hi = int(pr.get("lo_to_hi") or 0)
        hi_to_lo = int(pr.get("hi_to_lo") or 0)
        # Put the heavier attacker on the left for display
        if lo_to_hi >= hi_to_lo:
            actor, target = lo, hi
            actor_count, target_count = lo_to_hi, hi_to_lo
        else:
            actor, target = hi, lo
            actor_count, target_count = hi_to_lo, lo_to_hi
        return {
            "actor_username": actor,
            "actor_display_name": actor,
            "target_username": target,
            "target_display_name": target,
            "count": int(pr["total"]),
            "actor_count": actor_count,
            "target_count": target_count,
            "platform": pr.get("platform") or "twitch",
        }

    async def _slot_totals():
        rows = await db.folhinha_events.aggregate([
            {"$match": {
                **base,
                "kind": "cookie_slot",
                "cookies_delta": {"$ne": None},
            }},
            {"$group": {
                "_id": None,
                "won": {"$sum": {"$cond": [{"$gt": ["$cookies_delta", 0]}, "$cookies_delta", 0]}},
                "lost": {"$sum": {"$cond": [
                    {"$lt": ["$cookies_delta", 0]},
                    {"$abs": "$cookies_delta"},
                    0,
                ]}},
            }},
        ]).to_list(1)
        if not rows:
            return 0, 0
        return int(rows[0]["won"]), int(rows[0]["lost"])

    # Cookie top reuses the same board query (already cached when tab loads in parallel)
    by_kind, bucket_counts, top_bonk_pair, (slot_won, slot_lost), cookie_top = await asyncio.gather(
        _kind_totals(),
        _histogram(),
        _top_pair(),
        _slot_totals(),
        _cookie_balance_leaderboard(
            period=period,
            platform=platform,
            limit=5,
            start_date=start_date,
            end_date=end_date,
        ),
    )

    bonks = by_kind.get("bonk", 0)
    abracos = by_kind.get("abraco", 0)
    slots = by_kind.get("cookie_slot", 0)
    cookie_cd = by_kind.get("cookie_cd", 0)
    survive = by_kind.get("roulette_survive", 0)
    death = by_kind.get("roulette_death", 0)

    bonk_pct_histogram = []
    for lo, hi, label in BONK_PCT_BUCKETS:
        bonk_pct_histogram.append({
            "bucket": f"{lo}-{hi}",
            "label": label,
            "count": bucket_counts.get(lo, 0),
        })

    out = {
        "totals": {
            "bonks": bonks,
            "abracos": abracos,
            "slots": slots,
            "cookie_cd": cookie_cd,
            "roulette": survive + death,
            "roulette_survive": survive,
            "roulette_death": death,
        },
        "bonk_pct_histogram": bonk_pct_histogram,
        "top_bonk_pair": top_bonk_pair,
        "slot_totals": {"won": slot_won, "lost": slot_lost},
        "cookie_top": [
            {
                "username": r["username"],
                "display_name": r["display_name"],
                "platform": r.get("platform") or "twitch",
                "count": r["count"],
            }
            for r in cookie_top
        ],
    }
    set_stats_cache(cache_key, out)
    return out
