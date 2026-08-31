"""Emote catalog sync, daily usage aggregates, and emote stats APIs."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import logging

import httpx
from pymongo import UpdateOne

from app.config import get_settings
from app.database import db
from app.models.schemas import (
    EmoteContributor,
    EmoteCreatorEntry,
    EmoteCreatorsResponse,
    EmoteDetailResponse,
    EmoteDiversidadeEntry,
    EmoteDiversidadeResponse,
    EmoteLeastUsedEntry,
    EmoteLeastUsedResponse,
    EmotePeriodCounts,
    EmoteRankingResponse,
    EmoteSearchResult,
    EmoteUsage,
    EmoteWeatherEntry,
    EmoteWeatherResponse,
)

logger = logging.getLogger(__name__)

BRT = timezone(timedelta(hours=-3))
HTTP_TIMEOUT = 15.0
IGNORED_BOTS = frozenset({"streamadsbot", "folhinhabot", "fossabot"})

_name_to_id_cache: dict[str, str] | None = None
_name_cache_time: datetime | None = None
NAME_CACHE_TTL = 300


def _brt_date_str(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(BRT).strftime("%Y-%m-%d")


def _period_date_strs(
    period: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[str] | None:
    """Return BRT date strings to include, or None for all-time."""
    from app.services.stats_aggregates import resolve_period_dates
    from datetime import datetime as _dt

    date_range = resolve_period_dates(period, start_date, end_date)
    if not date_range:
        return None
    start = _dt.strptime(date_range[0], "%Y-%m-%d").date()
    end = _dt.strptime(date_range[1], "%Y-%m-%d").date()
    days = (end - start).days
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days + 1)]


def _platform_match(platform: str) -> dict:
    if platform == "twitch":
        return {"platform": "twitch"}
    if platform == "kick":
        return {"platform": "kick"}
    return {}


def _extract_catalog_entry(emote: dict, source: str) -> dict | None:
    emote_id = emote.get("id")
    name = emote.get("name")
    if not emote_id or not name:
        return None
    data = emote.get("data") or {}
    owner = data.get("owner") or {}
    return {
        "emote_id": str(emote_id),
        "emote_name": name,
        "emote_name_lower": name.lower(),
        "creator_7tv_id": owner.get("id"),
        "creator_username": (owner.get("username") or "").lower() or None,
        "creator_display_name": owner.get("display_name") or owner.get("username"),
        "source": source,
        "animated": bool(data.get("animated")),
        "updated_at": datetime.now(timezone.utc),
    }


async def sync_emote_catalog() -> int:
    """Refresh channel + global 7TV emotes into emote_catalog."""
    settings = get_settings()
    entries: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(f"https://7tv.io/v3/emote-sets/{settings.seventv_emote_set_id}")
            if resp.status_code == 200:
                for emote in resp.json().get("emotes", []):
                    entry = _extract_catalog_entry(emote, "channel")
                    if entry:
                        entries.append(entry)

            global_resp = await client.get("https://7tv.io/v3/emote-sets/global")
            if global_resp.status_code == 200:
                for emote in global_resp.json().get("emotes", []):
                    entry = _extract_catalog_entry(emote, "global")
                    if entry:
                        entries.append(entry)
    except Exception as exc:
        logger.error("Failed to sync emote catalog: %s", exc)
        return 0

    if not entries:
        return 0

    # Prefer channel entry when the same id appears in both
    by_id: dict[str, dict] = {}
    for entry in entries:
        existing = by_id.get(entry["emote_id"])
        if not existing or (existing["source"] == "global" and entry["source"] == "channel"):
            by_id[entry["emote_id"]] = entry

    ops = [
        UpdateOne(
            {"emote_id": e["emote_id"]},
            {"$set": e},
            upsert=True,
        )
        for e in by_id.values()
    ]
    if ops:
        await db.emote_catalog.bulk_write(ops, ordered=False)

    global _name_to_id_cache, _name_cache_time
    _name_to_id_cache = {e["emote_name"]: e["emote_id"] for e in by_id.values()}
    _name_cache_time = datetime.now(timezone.utc)

    logger.info("Synced emote_catalog: %d emotes", len(by_id))
    return len(by_id)


async def get_emote_name_map() -> dict[str, str]:
    """Name -> id map from catalog (fallback to live 7TV if catalog empty)."""
    global _name_to_id_cache, _name_cache_time
    now = datetime.now(timezone.utc)
    if (
        _name_to_id_cache is not None
        and _name_cache_time is not None
        and (now - _name_cache_time).total_seconds() < NAME_CACHE_TTL
    ):
        return _name_to_id_cache

    docs = await db.emote_catalog.find(
        {}, {"emote_name": 1, "emote_id": 1, "source": 1}
    ).to_list(None)
    if docs:
        # Prefer channel IDs when the same name exists in both sets
        by_name: dict[str, dict] = {}
        for d in docs:
            name = d.get("emote_name")
            if not name:
                continue
            existing = by_name.get(name)
            if not existing or (
                existing.get("source") == "global" and d.get("source") == "channel"
            ):
                by_name[name] = d
        _name_to_id_cache = {n: d["emote_id"] for n, d in by_name.items()}
        _name_cache_time = now
        return _name_to_id_cache

    await sync_emote_catalog()
    return _name_to_id_cache or {}


def count_emotes_in_text(message: str, name_map: dict[str, str]) -> Counter[str]:
    """Return Counter of emote_id -> occurrences in message text."""
    counts: Counter[str] = Counter()
    if not message or not name_map:
        return counts
    for word in message.split():
        emote_id = name_map.get(word)
        if emote_id:
            counts[emote_id] += 1
    return counts


async def record_emote_usage(doc: dict, name_map: dict[str, str] | None = None) -> None:
    """Increment emote_daily_stats for emotes found in a message."""
    username = (doc.get("username") or "").lower()
    if username in IGNORED_BOTS:
        return

    message = doc.get("message") or ""
    if not message:
        return

    if name_map is None:
        name_map = await get_emote_name_map()
    counts = count_emotes_in_text(message, name_map)
    if not counts:
        return

    # Reverse map for name lookup
    id_to_name = {eid: name for name, eid in name_map.items()}
    ts = doc["timestamp"]
    if getattr(ts, "tzinfo", None) is None:
        ts = ts.replace(tzinfo=timezone.utc)
    date_str = _brt_date_str(ts)
    platform = doc.get("platform", "twitch")
    user_id = str(doc.get("user_id") or username)
    display_name = doc.get("display_name", username)

    ops = []
    for emote_id, count in counts.items():
        emote_name = id_to_name.get(emote_id, emote_id)
        ops.append(
            UpdateOne(
                {
                    "date": date_str,
                    "platform": platform,
                    "emote_id": emote_id,
                    "user_id": user_id,
                },
                {
                    "$inc": {"count": count},
                    "$set": {
                        "username": username,
                        "display_name": display_name,
                        "emote_name": emote_name,
                        "emote_name_lower": emote_name.lower(),
                    },
                    "$setOnInsert": {
                        "date": date_str,
                        "platform": platform,
                        "emote_id": emote_id,
                        "user_id": user_id,
                    },
                },
                upsert=True,
            )
        )
    if ops:
        await db.emote_daily_stats.bulk_write(ops, ordered=False)


async def backfill_emote_daily_stats() -> int:
    """Scan chat_messages and rebuild emote_daily_stats if empty."""
    existing = await db.emote_daily_stats.estimated_document_count()
    if existing > 1000:
        logger.info("emote_daily_stats already populated (%d), skipping", existing)
        return existing

    name_map = await get_emote_name_map()
    if not name_map:
        await sync_emote_catalog()
        name_map = await get_emote_name_map()
    if not name_map:
        logger.warning("No emote map available for backfill")
        return 0

    id_to_name = {eid: name for name, eid in name_map.items()}
    logger.info("Starting emote_daily_stats backfill (%d emote names)...", len(name_map))

    # Aggregate in memory by key to reduce DB writes
    buckets: dict[tuple, dict] = {}
    cursor = db.messages.find(
        {"username": {"$nin": list(IGNORED_BOTS)}},
        {
            "message": 1,
            "username": 1,
            "display_name": 1,
            "user_id": 1,
            "platform": 1,
            "timestamp": 1,
        },
    ).batch_size(2000)

    processed = 0
    async for doc in cursor:
        processed += 1
        message = doc.get("message") or ""
        counts = count_emotes_in_text(message, name_map)
        if not counts:
            continue
        username = (doc.get("username") or "").lower()
        platform = doc.get("platform") or "twitch"
        user_id = str(doc.get("user_id") or username)
        display_name = doc.get("display_name") or username
        ts = doc.get("timestamp")
        if ts is None:
            continue
        date_str = _brt_date_str(ts)

        for emote_id, count in counts.items():
            key = (date_str, platform, emote_id, user_id)
            if key not in buckets:
                emote_name = id_to_name.get(emote_id, emote_id)
                buckets[key] = {
                    "date": date_str,
                    "platform": platform,
                    "emote_id": emote_id,
                    "user_id": user_id,
                    "username": username,
                    "display_name": display_name,
                    "emote_name": emote_name,
                    "emote_name_lower": emote_name.lower(),
                    "count": 0,
                }
            buckets[key]["count"] += count
            buckets[key]["username"] = username
            buckets[key]["display_name"] = display_name

        if processed % 50000 == 0:
            logger.info("emote backfill scanned %d messages, %d buckets", processed, len(buckets))

    ops = []
    written = 0
    for doc in buckets.values():
        ops.append(
            UpdateOne(
                {
                    "date": doc["date"],
                    "platform": doc["platform"],
                    "emote_id": doc["emote_id"],
                    "user_id": doc["user_id"],
                },
                {"$set": doc},
                upsert=True,
            )
        )
        if len(ops) >= 500:
            await db.emote_daily_stats.bulk_write(ops, ordered=False)
            written += len(ops)
            ops.clear()
    if ops:
        await db.emote_daily_stats.bulk_write(ops, ordered=False)
        written += len(ops)

    logger.info(
        "emote_daily_stats backfill complete: scanned %d msgs, wrote %d rows",
        processed,
        written,
    )
    return written


async def get_top_emotes_from_aggregates(
    limit: int = 10,
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[EmoteUsage], int] | None:
    from app.services.stats_aggregates import resolve_period_dates

    date_range = resolve_period_dates(period, start_date, end_date)
    match: dict = {}
    if date_range:
        match["date"] = {"$gte": date_range[0], "$lte": date_range[1]}
    match.update(_platform_match(platform))

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {"$toLower": "$emote_name"},
                "count": {"$sum": "$count"},
                "emote_name": {"$last": "$emote_name"},
                "emote_id": {"$last": "$emote_id"},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    rows = await db.emote_daily_stats.aggregate(pipeline).to_list(limit)
    if not rows:
        return None

    # Prefer channel catalog IDs when available for display
    name_keys = [r["_id"] for r in rows if r.get("_id")]
    catalog_docs = await db.emote_catalog.find(
        {"emote_name_lower": {"$in": name_keys}},
        {"emote_id": 1, "emote_name_lower": 1, "source": 1},
    ).to_list(None)
    preferred_id: dict[str, str] = {}
    for d in catalog_docs:
        key = d.get("emote_name_lower") or ""
        if not key:
            continue
        if key not in preferred_id or d.get("source") == "channel":
            preferred_id[key] = d["emote_id"]

    emotes = [
        EmoteUsage(
            emote_name=r["emote_name"],
            emote_id=preferred_id.get(r["_id"], r["emote_id"]),
            count=int(r["count"]),
        )
        for r in rows
    ]
    total = sum(e.count for e in emotes)
    return emotes, total


async def search_emotes(q: str, limit: int = 10) -> list[EmoteSearchResult]:
    q_lower = q.lower().strip()
    if len(q_lower) < 1:
        return []
    cursor = (
        db.emote_catalog.find({"emote_name_lower": {"$regex": f"^{q_lower}"}})
        .sort("emote_name", 1)
        .limit(limit)
    )
    docs = await cursor.to_list(limit)
    return [
        EmoteSearchResult(
            emote_name=d["emote_name"],
            emote_id=d["emote_id"],
            creator_username=d.get("creator_username"),
            creator_display_name=d.get("creator_display_name"),
            source=d.get("source", "channel"),
            animated=bool(d.get("animated")),
        )
        for d in docs
    ]


async def _catalog_usage_entries(
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[EmoteLeastUsedEntry]:
    """Name-deduped catalog entries with period usage counts.

    Channel and global 7TV copies often share a name but have different IDs.
    Usage is tracked under whichever ID the name map resolved to, so we
    aggregate counts by emote_name_lower and dedupe the catalog by name
    (preferring the channel entry).
    """
    from app.services.stats_aggregates import resolve_period_dates

    date_range = resolve_period_dates(period, start_date, end_date)
    match = {**_platform_match(platform)}
    if date_range:
        match["date"] = {"$gte": date_range[0], "$lte": date_range[1]}

    usage_pipeline = [
        {"$match": match} if match else {"$match": {}},
        {
            "$group": {
                "_id": {"$toLower": "$emote_name"},
                "count": {"$sum": "$count"},
            }
        },
    ]
    usage_rows = await db.emote_daily_stats.aggregate(usage_pipeline).to_list(None)
    usage_by_name = {
        (r["_id"] or "").lower(): int(r["count"])
        for r in usage_rows
        if r.get("_id")
    }

    catalog = await db.emote_catalog.find({}).to_list(None)
    by_name: dict[str, dict] = {}
    for doc in catalog:
        key = (doc.get("emote_name_lower") or doc.get("emote_name") or "").lower()
        if not key:
            continue
        existing = by_name.get(key)
        if not existing:
            by_name[key] = doc
            continue
        if existing.get("source") == "global" and doc.get("source") == "channel":
            by_name[key] = doc

    entries: list[EmoteLeastUsedEntry] = []
    for key, doc in by_name.items():
        entries.append(
            EmoteLeastUsedEntry(
                emote_name=doc["emote_name"],
                emote_id=doc["emote_id"],
                count=usage_by_name.get(key, 0),
                creator_username=doc.get("creator_username"),
                creator_display_name=doc.get("creator_display_name"),
                source=doc.get("source", "channel"),
            )
        )
    return entries


async def get_emote_ranking(
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> EmoteRankingResponse:
    """Full catalog ranked by usage descending (zeros at the bottom)."""
    entries = await _catalog_usage_entries(platform, period, start_date, end_date)
    entries.sort(key=lambda e: (-e.count, e.emote_name.lower()))
    total_uses = sum(e.count for e in entries)
    return EmoteRankingResponse(
        emotes=entries,
        total_emotes=len(entries),
        total_uses=total_uses,
    )


async def get_least_used_emotes(
    platform: str = "all",
    limit: int = 10,
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> EmoteLeastUsedResponse:
    """Split unused (0) from least-used among emotes with at least one use."""
    entries = await _catalog_usage_entries(platform, period, start_date, end_date)
    unused = sorted(
        [e for e in entries if e.count == 0],
        key=lambda e: e.emote_name.lower(),
    )
    least_used = sorted(
        [e for e in entries if e.count >= 1],
        key=lambda e: (e.count, e.emote_name.lower()),
    )[:limit]
    return EmoteLeastUsedResponse(
        unused=unused,
        unused_count=len(unused),
        least_used=least_used,
    )


async def get_emote_creators(
    platform: str = "all",
    limit: int = 10,
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> EmoteCreatorsResponse:
    # Creators who own catalog emotes AND have chatted (optionally in period)
    from app.services.stats_aggregates import resolve_period_dates

    pipeline = [
        {"$match": {"creator_username": {"$ne": None, "$exists": True}}},
        {
            "$group": {
                "_id": "$creator_username",
                "creator_display_name": {"$last": "$creator_display_name"},
                "emote_count": {"$sum": 1},
                "emote_names": {"$push": "$emote_name"},
            }
        },
        {"$sort": {"emote_count": -1}},
    ]
    rows = await db.emote_catalog.aggregate(pipeline).to_list(None)

    chat_usernames: set[str] = set()
    date_range = resolve_period_dates(period, start_date, end_date)
    if date_range:
        match = {"date": {"$gte": date_range[0], "$lte": date_range[1]}, **_platform_match(platform)}
        async for u in db.user_daily_stats.find(match, {"username": 1}):
            chat_usernames.add((u.get("username") or "").lower())
    else:
        ut_match = _platform_match(platform)
        async for u in db.user_totals.find(ut_match, {"username": 1}):
            chat_usernames.add((u.get("username") or "").lower())

    entries = []
    for row in rows:
        username = (row["_id"] or "").lower()
        if not username or username not in chat_usernames:
            continue
        entries.append(
            EmoteCreatorEntry(
                username=username,
                display_name=row.get("creator_display_name") or username,
                emote_count=int(row["emote_count"]),
                sample_emotes=(row.get("emote_names") or [])[:5],
            )
        )
        if len(entries) >= limit:
            break

    for i, e in enumerate(entries):
        e.rank = i + 1
    return EmoteCreatorsResponse(creators=entries)


async def get_diversidade(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> EmoteDiversidadeResponse:
    dates = _period_date_strs(period, start_date, end_date)
    match: dict = {}
    if dates is not None:
        match["date"] = {"$in": dates}
    match.update(_platform_match(platform))

    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {
            "$group": {
                "_id": {
                    "platform": "$platform",
                    "user_id": "$user_id",
                },
                "username": {"$last": "$username"},
                "display_name": {"$last": "$display_name"},
                "unique_emotes": {"$addToSet": "$emote_id"},
            }
        },
        {
            "$project": {
                "username": 1,
                "display_name": 1,
                "platform": "$_id.platform",
                "unique_count": {"$size": "$unique_emotes"},
            }
        },
        {"$sort": {"unique_count": -1}},
        {"$limit": limit},
    ]
    rows = await db.emote_daily_stats.aggregate(pipeline).to_list(limit)
    entries = [
        EmoteDiversidadeEntry(
            rank=i + 1,
            username=r["username"],
            display_name=r.get("display_name") or r["username"],
            platform=r.get("platform", "twitch"),
            unique_emotes=int(r["unique_count"]),
        )
        for i, r in enumerate(rows)
    ]
    return EmoteDiversidadeResponse(period=period, platform=platform, leaderboard=entries)


async def get_emote_detail(
    name: str,
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> EmoteDetailResponse | None:
    from app.services.stats_aggregates import resolve_period_dates

    name_lower = name.lower()
    # Prefer channel catalog entry when both channel + global exist
    catalog_docs = await db.emote_catalog.find({"emote_name_lower": name_lower}).to_list(10)
    catalog = None
    for doc in catalog_docs:
        if not catalog or (
            catalog.get("source") == "global" and doc.get("source") == "channel"
        ):
            catalog = doc
    if not catalog:
        usage = await db.emote_daily_stats.find_one({"emote_name_lower": name_lower})
        if not usage:
            return None
        catalog = {
            "emote_id": usage["emote_id"],
            "emote_name": usage["emote_name"],
            "creator_username": None,
            "creator_display_name": None,
            "source": "unknown",
            "animated": False,
        }

    emote_id = catalog["emote_id"]
    plat_match = _platform_match(platform)

    # Sum by name so channel/global ID splits still count as one emote
    async def _sum_for_dates(dates: list[str] | None) -> int:
        match: dict = {"emote_name_lower": name_lower, **plat_match}
        if dates is not None:
            match["date"] = {"$in": dates}
        pipeline = [{"$match": match}, {"$group": {"_id": None, "total": {"$sum": "$count"}}}]
        rows = await db.emote_daily_stats.aggregate(pipeline).to_list(1)
        return int(rows[0]["total"]) if rows else 0

    usage = EmotePeriodCounts(
        day=await _sum_for_dates(_period_date_strs("day")),
        week=await _sum_for_dates(_period_date_strs("week")),
        month=await _sum_for_dates(_period_date_strs("month")),
        all=await _sum_for_dates(None),
    )

    contrib_match = {"emote_name_lower": name_lower, **plat_match}
    date_range = resolve_period_dates(period, start_date, end_date)
    if date_range:
        contrib_match["date"] = {"$gte": date_range[0], "$lte": date_range[1]}
    contrib_pipeline = [
        {"$match": contrib_match},
        {
            "$group": {
                "_id": {"platform": "$platform", "user_id": "$user_id"},
                "username": {"$last": "$username"},
                "display_name": {"$last": "$display_name"},
                "count": {"$sum": "$count"},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    contrib_rows = await db.emote_daily_stats.aggregate(contrib_pipeline).to_list(20)
    contributors = [
        EmoteContributor(
            rank=i + 1,
            username=r["username"],
            display_name=r.get("display_name") or r["username"],
            platform=r["_id"].get("platform", "twitch"),
            count=int(r["count"]),
        )
        for i, r in enumerate(contrib_rows)
    ]

    return EmoteDetailResponse(
        emote_name=catalog["emote_name"],
        emote_id=emote_id,
        creator_username=catalog.get("creator_username"),
        creator_display_name=catalog.get("creator_display_name"),
        source=catalog.get("source", "channel"),
        animated=bool(catalog.get("animated")),
        usage=usage,
        top_contributors=contributors,
    )


def _format_window(start_ymd: str, end_ymd: str) -> str:
    if start_ymd == end_ymd:
        return start_ymd
    return f"{start_ymd}..{end_ymd}"


async def _emote_counts_by_name(
    start_ymd: str,
    end_ymd: str,
    platform: str,
) -> dict[str, dict]:
    """Aggregate emote_daily_stats by lowercased name for a date window."""
    match: dict = {
        "date": {"$gte": start_ymd, "$lte": end_ymd},
        **_platform_match(platform),
    }
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {"$toLower": "$emote_name"},
                "count": {"$sum": "$count"},
                "emote_name": {"$last": "$emote_name"},
                "emote_id": {"$last": "$emote_id"},
            }
        },
    ]
    rows = await db.emote_daily_stats.aggregate(pipeline).to_list(None)
    out: dict[str, dict] = {}
    for r in rows:
        key = (r.get("_id") or "").lower()
        if not key:
            continue
        out[key] = {
            "emote_name": r.get("emote_name") or key,
            "emote_id": str(r.get("emote_id") or ""),
            "count": int(r["count"]),
        }
    return out


async def get_emote_weather(
    platform: str = "all",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 10,
) -> EmoteWeatherResponse:
    """Rising/falling emotes: current window vs previous equal window.

    When no period window resolves (all-time), compares the last complete BRT
    day against the day before.
    """
    from app.services.stats_aggregates import (
        resolve_period_dates,
        previous_equal_window,
    )

    date_range = resolve_period_dates(period, start_date, end_date)
    if date_range:
        now_start, now_end = date_range
        prev_start, prev_end = previous_equal_window(now_start, now_end)
    else:
        today = datetime.now(BRT).date()
        yesterday = today - timedelta(days=1)
        day_before = today - timedelta(days=2)
        now_start = now_end = yesterday.isoformat()
        prev_start = prev_end = day_before.isoformat()

    now_counts = await _emote_counts_by_name(now_start, now_end, platform)
    prev_counts = await _emote_counts_by_name(prev_start, prev_end, platform)

    # Prefer catalog channel ID when available (name-dedupe)
    catalog = await db.emote_catalog.find({}).to_list(None)
    name_meta: dict[str, dict] = {}
    for doc in catalog:
        key = (doc.get("emote_name_lower") or doc.get("emote_name") or "").lower()
        if not key:
            continue
        existing = name_meta.get(key)
        if not existing:
            name_meta[key] = {
                "emote_id": doc["emote_id"],
                "emote_name": doc.get("emote_name") or key,
                "source": doc.get("source", "channel"),
            }
        elif existing.get("source") == "global" and doc.get("source") == "channel":
            name_meta[key] = {
                "emote_id": doc["emote_id"],
                "emote_name": doc.get("emote_name") or key,
                "source": "channel",
            }

    all_keys = set(now_counts) | set(prev_counts)
    entries: list[EmoteWeatherEntry] = []
    for key in all_keys:
        now = now_counts.get(key, {})
        prev = prev_counts.get(key, {})
        count_now = int(now.get("count", 0))
        count_prev = int(prev.get("count", 0))
        delta = count_now - count_prev
        if delta == 0:
            continue
        meta = name_meta.get(key, {})
        emote_name = (
            meta.get("emote_name")
            or now.get("emote_name")
            or prev.get("emote_name")
            or key
        )
        emote_id = (
            meta.get("emote_id")
            or now.get("emote_id")
            or prev.get("emote_id")
            or ""
        )
        if count_prev > 0:
            delta_pct = round((delta / count_prev) * 100.0, 1)
        elif count_now > 0:
            delta_pct = None  # new / previously unused
        else:
            delta_pct = None
        entries.append(
            EmoteWeatherEntry(
                emote_name=emote_name,
                emote_id=str(emote_id),
                count_now=count_now,
                count_prev=count_prev,
                delta=delta,
                delta_pct=delta_pct,
            )
        )

    rising = sorted(
        [e for e in entries if e.delta > 0],
        key=lambda e: (-e.delta, -e.count_now, e.emote_name.lower()),
    )[:limit]
    falling = sorted(
        [e for e in entries if e.delta < 0],
        key=lambda e: (e.delta, e.count_now, e.emote_name.lower()),
    )[:limit]

    return EmoteWeatherResponse(
        period=period,
        platform=platform,
        window_now=_format_window(now_start, now_end),
        window_prev=_format_window(prev_start, prev_end),
        rising=rising,
        falling=falling,
    )
