"""Pre-aggregated counters updated on each message insert for fast reads."""

from datetime import datetime, timezone, timedelta
import logging
import re

from pymongo import ReplaceOne, UpdateOne

from app.database import db

logger = logging.getLogger(__name__)

IGNORED_BOTS = frozenset({"streamadsbot", "folhinhabot", "fossabot"})
BOT_FILTER = {"username": {"$nin": list(IGNORED_BOTS)}}
NORMALIZE_PLATFORM_STAGE = {
    "$addFields": {"_platform": {"$ifNull": ["$platform", "twitch"]}}
}

BRT = timezone(timedelta(hours=-3))
SMOKE_EMOTE = "SmokeTime"
SMOKE_HOUR_BRT = 16
SMOKE_MINUTE_BRT = 20
SMOKE_MESSAGE_REGEX = re.compile(rf"(^|\s){re.escape(SMOKE_EMOTE)}(\s|$)")
BRT_TZ_OFFSET = "-03:00"

# Re-export period helpers from common (single source of truth)
from app.services.common.period import (  # noqa: E402
    resolve_period_dates,
    period_date_range_brt,
    date_range_to_utc_bounds,
    previous_equal_window,
)


def _is_smoke_time_message(doc: dict) -> bool:
    """True if message is SmokeTime at exactly 16:20 BRT."""
    if int(doc.get("hour", -1)) != SMOKE_HOUR_BRT:
        return False
    message = doc.get("message") or ""
    if SMOKE_EMOTE not in message.split():
        return False
    ts = doc.get("timestamp")
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_brt = ts.astimezone(BRT)
    return ts_brt.hour == SMOKE_HOUR_BRT and ts_brt.minute == SMOKE_MINUTE_BRT


async def record_smoke_session(doc: dict) -> None:
    """Upsert one smoke session per (platform, user_id, date) if message qualifies."""
    username = (doc.get("username") or "").lower()
    if username in IGNORED_BOTS:
        return
    if not _is_smoke_time_message(doc):
        return

    ts = doc["timestamp"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_brt = ts.astimezone(BRT)
    date_str = ts_brt.strftime("%Y-%m-%d")
    platform = doc.get("platform", "twitch")
    user_id = str(doc.get("user_id") or username)

    await db.smoke_sessions.update_one(
        {"platform": platform, "user_id": user_id, "date": date_str},
        {
            "$setOnInsert": {
                "platform": platform,
                "user_id": user_id,
                "date": date_str,
                "first_ts": ts,
            },
            "$set": {
                "username": username,
                "display_name": doc.get("display_name", username),
            },
        },
        upsert=True,
    )


async def record_message(doc: dict) -> None:
    """Increment pre-aggregated stats when a new chat message is stored."""
    username = doc.get("username", "").lower()
    if username in IGNORED_BOTS:
        return

    platform = doc.get("platform", "twitch")
    user_id = str(doc["user_id"])
    hour = int(doc["hour"])

    await db.user_totals.update_one(
        {"platform": platform, "user_id": user_id},
        {
            "$inc": {"message_count": 1, f"hourly.{hour}": 1},
            "$set": {
                "username": username,
                "display_name": doc.get("display_name", username),
                "last_message": doc["timestamp"],
            },
            "$addToSet": {"known_usernames": username},
            "$setOnInsert": {"first_message": doc["timestamp"]},
        },
        upsert=True,
    )

    await db.platform_hourly_stats.update_one(
        {"platform": platform},
        {
            "$inc": {"total_messages": 1, f"hourly.{hour}": 1},
            "$set": {"updated_at": doc["timestamp"]},
        },
        upsert=True,
    )

    for handler in INGEST_HANDLERS:
        try:
            await handler(doc)
        except Exception as exc:
            logger.warning("Ingest handler %s failed: %s", getattr(handler, "__name__", handler), exc)


async def record_daily_stats(doc: dict) -> None:
    """Increment per-user daily counters (BRT date) for period-filtered queries."""
    username = (doc.get("username") or "").lower()
    if username in IGNORED_BOTS:
        return

    ts = doc["timestamp"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_brt = ts.astimezone(BRT)
    date_str = ts_brt.strftime("%Y-%m-%d")
    platform = doc.get("platform", "twitch")
    user_id = str(doc.get("user_id") or username)
    hour = int(doc["hour"])

    await db.user_daily_stats.update_one(
        {"platform": platform, "user_id": user_id, "date": date_str},
        {
            "$inc": {"message_count": 1, f"hourly.{hour}": 1},
            "$set": {
                "username": username,
                "display_name": doc.get("display_name", username),
                "last_message": ts,
            },
            "$min": {"first_message": ts},
            "$setOnInsert": {
                "platform": platform,
                "user_id": user_id,
                "date": date_str,
            },
        },
        upsert=True,
    )


def _totals_match(platform: str) -> dict:
    if platform == "twitch":
        return {"platform": "twitch"}
    if platform == "kick":
        return {"platform": "kick"}
    return {}


async def get_leaderboard_from_totals(platform: str, limit: int) -> tuple[list[dict], int, int]:
    """Fast all-time leaderboard from pre-aggregated user totals."""
    match = _totals_match(platform)
    entries = await db.user_totals.find(match).sort("message_count", -1).limit(limit).to_list(limit)
    total_users = await db.user_totals.count_documents(match)

    if platform == "all":
        totals = await db.platform_hourly_stats.aggregate([
            {"$group": {"_id": None, "total_messages": {"$sum": "$total_messages"}}},
        ]).to_list(1)
        total_messages = totals[0]["total_messages"] if totals else 0
    else:
        doc = await db.platform_hourly_stats.find_one({"platform": platform})
        total_messages = doc.get("total_messages", 0) if doc else 0

    return entries, total_users, total_messages


async def get_rank_map_from_totals(platform: str, limit: int = 1000) -> tuple[dict[str, int], int]:
    """Fast rank lookup from pre-aggregated user totals."""
    match = _totals_match(platform)
    users = await db.user_totals.find(match).sort("message_count", -1).limit(limit).to_list(limit)
    rank_map = {
        f"{user.get('platform', 'twitch')}:{str(user['user_id'])}": i + 1
        for i, user in enumerate(users)
    }
    total_users = await db.user_totals.count_documents(match)
    return rank_map, total_users


async def get_overall_hourly_from_totals(platform: str) -> tuple[list[int], int]:
    """Fast all-time hourly activity from pre-aggregated platform stats."""
    hours = [0] * 24
    total_messages = 0

    if platform == "all":
        docs = await db.platform_hourly_stats.find({}).to_list(10)
    else:
        doc = await db.platform_hourly_stats.find_one({"platform": platform})
        docs = [doc] if doc else []

    for doc in docs:
        if not doc:
            continue
        total_messages += int(doc.get("total_messages", 0))
        nested = doc.get("hourly", {})
        if isinstance(nested, dict):
            for h in range(24):
                hours[h] += int(nested.get(str(h), nested.get(h, 0)) or 0)

    return hours, total_messages


async def backfill_aggregates() -> None:
    """Build user_totals and platform_hourly_stats from raw messages (background)."""
    user_count = await db.user_totals.estimated_document_count()
    hourly_count = await db.platform_hourly_stats.estimated_document_count()
    if user_count > 10000 and hourly_count > 0:
        logger.info(
            "Aggregates already populated (%d users, %d platforms), skipping backfill",
            user_count,
            hourly_count,
        )
        return

    logger.info("Starting aggregate backfill from chat_messages...")

    user_pipeline = [
        {"$match": BOT_FILTER},
        NORMALIZE_PLATFORM_STAGE,
        {
            "$group": {
                "_id": {
                    "platform": "$_platform",
                    "user_id": {"$ifNull": ["$user_id", "$username"]},
                },
                "username": {"$last": "$username"},
                "display_name": {"$last": "$display_name"},
                "message_count": {"$sum": 1},
                "first_message": {"$min": "$timestamp"},
                "last_message": {"$max": "$timestamp"},
            }
        },
    ]

    batch: list[dict] = []
    async for row in db.messages.aggregate(user_pipeline, allowDiskUse=True):
        batch.append({
            "platform": row["_id"].get("platform", "twitch"),
            "user_id": str(row["_id"]["user_id"]),
            "username": row["username"],
            "display_name": row["display_name"],
            "message_count": row["message_count"],
            "first_message": row["first_message"],
            "last_message": row["last_message"],
        })
        if len(batch) >= 500:
            await _upsert_user_totals_batch(batch)
            batch.clear()

    if batch:
        await _upsert_user_totals_batch(batch)

    hourly_pipeline = [
        {"$match": BOT_FILTER},
        NORMALIZE_PLATFORM_STAGE,
        {
            "$group": {
                "_id": {"platform": "$_platform", "hour": "$hour"},
                "count": {"$sum": 1},
            }
        },
    ]

    platform_data: dict[str, dict] = {}
    async for row in db.messages.aggregate(hourly_pipeline, allowDiskUse=True):
        plat = row["_id"].get("platform", "twitch")
        hour = int(row["_id"]["hour"])
        if plat not in platform_data:
            platform_data[plat] = {"hourly": {str(h): 0 for h in range(24)}, "total_messages": 0}
        platform_data[plat]["hourly"][str(hour)] += row["count"]
        platform_data[plat]["total_messages"] += row["count"]

    now = datetime.now(timezone.utc)
    for plat, data in platform_data.items():
        await db.platform_hourly_stats.update_one(
            {"platform": plat},
            {"$set": {**data, "updated_at": now}},
            upsert=True,
        )

    logger.info(
        "Aggregate backfill complete: %d users, %d platforms",
        await db.user_totals.estimated_document_count(),
        len(platform_data),
    )

    await merge_legacy_user_totals()
    await backfill_known_usernames()


async def merge_legacy_user_totals() -> int:
    """Merge user_totals rows where legacy messages used username as user_id.

    Only merges within the same platform — Twitch and Kick identities stay separate.
    Also drops rename orphans: legacy rows for an old login whose messages now
    live under a different current username for the same platform user_id.
    """
    merged = 0
    all_docs = await db.user_totals.find(
        {},
        {
            "platform": 1,
            "username": 1,
            "user_id": 1,
            "message_count": 1,
            "hourly": 1,
            "first_message": 1,
            "last_message": 1,
        },
    ).to_list(None)

    legacy_by_key: dict[tuple[str, str], dict] = {}
    real_by_key: dict[tuple[str, str], dict] = {}
    real_by_uid: dict[tuple[str, str], dict] = {}
    for doc in all_docs:
        key = (doc["platform"], doc["username"])
        if doc["user_id"] == doc["username"]:
            legacy_by_key[key] = doc
        else:
            existing = real_by_key.get(key)
            if not existing or doc["message_count"] > existing["message_count"]:
                real_by_key[key] = doc
            uid_key = (doc["platform"], str(doc["user_id"]))
            existing_uid = real_by_uid.get(uid_key)
            if not existing_uid or doc["message_count"] > existing_uid["message_count"]:
                real_by_uid[uid_key] = doc

    for key, legacy in legacy_by_key.items():
        real = real_by_key.get(key)
        if not real:
            # Rename orphan: old login keyed as user_id, while the live row uses
            # the permanent platform id under the current username.
            plat, username = key
            msg = await db.messages.find_one(
                {
                    "username": username,
                    "user_id": {"$exists": True, "$nin": [None, "", username]},
                    **({"platform": plat} if plat else {}),
                },
                sort=[("timestamp", -1)],
            )
            if not msg:
                continue
            canon = real_by_uid.get((plat, str(msg["user_id"])))
            if not canon or canon.get("username") == username:
                continue
            await db.user_totals.delete_one({"_id": legacy["_id"]})
            merged += 1
            continue

        inc_fields: dict = {"message_count": legacy.get("message_count", 0)}
        legacy_hourly = legacy.get("hourly") or {}
        for hour, count in legacy_hourly.items():
            inc_fields[f"hourly.{hour}"] = count

        first_message = legacy.get("first_message")
        last_message = legacy.get("last_message")
        set_fields: dict = {}
        if first_message and (not real.get("first_message") or first_message < real["first_message"]):
            set_fields["first_message"] = first_message
        if last_message and (not real.get("last_message") or last_message > real["last_message"]):
            set_fields["last_message"] = last_message

        update: dict = {"$inc": inc_fields}
        if set_fields:
            update["$set"] = set_fields

        await db.user_totals.update_one({"_id": real["_id"]}, update)
        await db.user_totals.delete_one({"_id": legacy["_id"]})
        merged += 1

    if merged:
        logger.info("Merged %d legacy duplicate user_totals entries", merged)
    return merged


async def backfill_known_usernames() -> int:
    """Populate user_totals.known_usernames from chat history (past + current logins)."""
    pipeline = [
        {"$match": {"user_id": {"$exists": True, "$nin": [None, ""]}}},
        {
            "$group": {
                "_id": {
                    "platform": {"$ifNull": ["$platform", "twitch"]},
                    "user_id": "$user_id",
                },
                "names": {"$addToSet": "$username"},
            }
        },
    ]
    updated = 0
    async for row in db.messages.aggregate(pipeline, allowDiskUse=True):
        plat = row["_id"]["platform"]
        uid = str(row["_id"]["user_id"])
        names = [n for n in row.get("names") or [] if n]
        if not names:
            continue
        # Skip legacy keys that are still username==user_id orphans without a real row
        if uid in names and len(names) == 1:
            # May still be a real user whose id equals login (rare); update if row exists
            pass
        result = await db.user_totals.update_one(
            {"platform": plat, "user_id": uid},
            {"$addToSet": {"known_usernames": {"$each": names}}},
        )
        if result.modified_count or result.matched_count:
            updated += 1
    if updated:
        logger.info("Backfilled known_usernames on %d user_totals docs", updated)
    return updated


async def _upsert_user_totals_batch(batch: list[dict]) -> None:
    ops = [
        ReplaceOne(
            {"platform": doc["platform"], "user_id": doc["user_id"]},
            doc,
            upsert=True,
        )
        for doc in batch
    ]
    await db.user_totals.bulk_write(ops, ordered=False)


async def _upsert_smoke_sessions_batch(batch: list[dict]) -> None:
    ops = [
        ReplaceOne(
            {
                "platform": doc["platform"],
                "user_id": doc["user_id"],
                "date": doc["date"],
            },
            doc,
            upsert=True,
        )
        for doc in batch
    ]
    await db.smoke_sessions.bulk_write(ops, ordered=False)


async def backfill_smoke_sessions() -> None:
    """Build smoke_sessions from historical chat_messages at 16:20 BRT with SmokeTime."""
    existing = await db.smoke_sessions.estimated_document_count()
    if existing > 0:
        logger.info(
            "smoke_sessions already populated (%d docs), skipping backfill",
            existing,
        )
        return

    logger.info("Starting smoke_sessions backfill from chat_messages...")

    pipeline = [
        {
            "$match": {
                **BOT_FILTER,
                "hour": SMOKE_HOUR_BRT,
                "message": {"$regex": SMOKE_MESSAGE_REGEX.pattern},
            }
        },
        {
            "$match": {
                "$expr": {
                    "$eq": [
                        {"$minute": {"date": "$timestamp", "timezone": BRT_TZ_OFFSET}},
                        SMOKE_MINUTE_BRT,
                    ]
                }
            }
        },
        NORMALIZE_PLATFORM_STAGE,
        {
            "$group": {
                "_id": {
                    "platform": "$_platform",
                    "user_id": {"$ifNull": ["$user_id", "$username"]},
                    "date": {
                        "$dateToString": {
                            "date": "$timestamp",
                            "timezone": BRT_TZ_OFFSET,
                            "format": "%Y-%m-%d",
                        }
                    },
                },
                "username": {"$last": "$username"},
                "display_name": {"$last": "$display_name"},
                "first_ts": {"$min": "$timestamp"},
            }
        },
    ]

    batch: list[dict] = []
    total = 0
    async for row in db.messages.aggregate(pipeline, allowDiskUse=True):
        batch.append({
            "platform": row["_id"].get("platform", "twitch"),
            "user_id": str(row["_id"]["user_id"]),
            "date": row["_id"]["date"],
            "username": row["username"],
            "display_name": row.get("display_name") or row["username"],
            "first_ts": row["first_ts"],
        })
        if len(batch) >= 500:
            await _upsert_smoke_sessions_batch(batch)
            total += len(batch)
            batch.clear()

    if batch:
        await _upsert_smoke_sessions_batch(batch)
        total += len(batch)

    logger.info("smoke_sessions backfill complete: %d sessions", total)


async def _upsert_user_daily_batch(batch: list[dict]) -> None:
    ops = [
        ReplaceOne(
            {
                "platform": doc["platform"],
                "user_id": doc["user_id"],
                "date": doc["date"],
            },
            doc,
            upsert=True,
        )
        for doc in batch
    ]
    await db.user_daily_stats.bulk_write(ops, ordered=False)


async def backfill_user_daily_stats() -> None:
    """Build user_daily_stats from chat_messages (BRT calendar days)."""
    existing = await db.user_daily_stats.estimated_document_count()
    if existing > 1000:
        logger.info(
            "user_daily_stats already populated (%d docs), skipping backfill",
            existing,
        )
        return

    logger.info("Starting user_daily_stats backfill from chat_messages...")

    pipeline = [
        {"$match": BOT_FILTER},
        NORMALIZE_PLATFORM_STAGE,
        {
            "$group": {
                "_id": {
                    "platform": "$_platform",
                    "user_id": {"$ifNull": ["$user_id", "$username"]},
                    "date": {
                        "$dateToString": {
                            "date": "$timestamp",
                            "timezone": BRT_TZ_OFFSET,
                            "format": "%Y-%m-%d",
                        }
                    },
                    "hour": "$hour",
                },
                "username": {"$last": "$username"},
                "display_name": {"$last": "$display_name"},
                "count": {"$sum": 1},
                "first_message": {"$min": "$timestamp"},
                "last_message": {"$max": "$timestamp"},
            }
        },
        {
            "$group": {
                "_id": {
                    "platform": "$_id.platform",
                    "user_id": "$_id.user_id",
                    "date": "$_id.date",
                },
                "username": {"$last": "$username"},
                "display_name": {"$last": "$display_name"},
                "message_count": {"$sum": "$count"},
                "first_message": {"$min": "$first_message"},
                "last_message": {"$max": "$last_message"},
                "hours": {"$push": {"hour": "$_id.hour", "count": "$count"}},
            }
        },
    ]

    batch: list[dict] = []
    total = 0
    async for row in db.messages.aggregate(pipeline, allowDiskUse=True):
        hourly = {str(h): 0 for h in range(24)}
        for entry in row.get("hours") or []:
            hourly[str(int(entry["hour"]))] = int(entry["count"])

        batch.append({
            "platform": row["_id"].get("platform", "twitch"),
            "user_id": str(row["_id"]["user_id"]),
            "date": row["_id"]["date"],
            "username": row["username"],
            "display_name": row.get("display_name") or row["username"],
            "message_count": row["message_count"],
            "hourly": hourly,
            "first_message": row["first_message"],
            "last_message": row["last_message"],
        })
        if len(batch) >= 500:
            await _upsert_user_daily_batch(batch)
            total += len(batch)
            batch.clear()

    if batch:
        await _upsert_user_daily_batch(batch)
        total += len(batch)

    logger.info("user_daily_stats backfill complete: %d day-rows", total)


# Period helpers live in common.period; re-exported above.


async def get_user_period_from_daily(
    platform: str,
    user_id: str,
    username: str,
    period: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict | None:
    """Sum user_daily_stats for a period. Returns dict with totals/hourly/dates or None."""
    date_range = resolve_period_dates(period, start_date, end_date)
    if not date_range:
        return None

    start_date, end_date = date_range
    match: dict = {
        "platform": platform,
        "date": {"$gte": start_date, "$lte": end_date},
    }
    if user_id:
        match["user_id"] = str(user_id)
    else:
        match["username"] = username.lower()

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": None,
                "message_count": {"$sum": "$message_count"},
                "first_message": {"$min": "$first_message"},
                "last_message": {"$max": "$last_message"},
                "display_name": {"$last": "$display_name"},
                "username": {"$last": "$username"},
                "hourlies": {"$push": "$hourly"},
            }
        },
    ]
    rows = await db.user_daily_stats.aggregate(pipeline).to_list(1)
    if not rows or rows[0].get("message_count", 0) <= 0:
        return None

    row = rows[0]
    hourly = {str(h): 0 for h in range(24)}
    for nested in row.get("hourlies") or []:
        if not isinstance(nested, dict):
            continue
        for h in range(24):
            key = str(h)
            hourly[key] += int(nested.get(key, nested.get(h, 0)) or 0)

    return {
        "message_count": int(row["message_count"]),
        "hourly": hourly,
        "first_message": row.get("first_message"),
        "last_message": row.get("last_message"),
        "display_name": row.get("display_name") or username,
        "username": row.get("username") or username,
    }


async def get_percentile_from_daily(
    platform: str,
    user_message_count: int,
    period: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> float:
    """Percentile among users with messages in the same date range (from daily stats)."""
    if user_message_count <= 0:
        return 0.0

    date_range = resolve_period_dates(period, start_date, end_date)
    if not date_range:
        return 0.0

    start_date, end_date = date_range
    match = {"date": {"$gte": start_date, "$lte": end_date}}
    if platform in ("twitch", "kick"):
        match["platform"] = platform

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": {"platform": "$platform", "user_id": "$user_id"},
                "count": {"$sum": "$message_count"},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 1000},
    ]
    users = await db.user_daily_stats.aggregate(pipeline).to_list(1000)
    if not users:
        return 0.0

    below = sum(1 for u in users if u["count"] < user_message_count)
    return round((below / len(users)) * 100, 1)


async def daily_stats_ready() -> bool:
    count = await db.user_daily_stats.estimated_document_count()
    return count > 0


REPLY_WINDOW_SECONDS = 10


def _doc_date_str(doc: dict) -> str:
    ts = doc["timestamp"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(BRT).strftime("%Y-%m-%d")


async def record_folhinha(doc: dict) -> None:
    """Count messages that start with '?' (Folhinha bot commands)."""
    username = (doc.get("username") or "").lower()
    if username in IGNORED_BOTS:
        return
    message = (doc.get("message") or "").strip()
    if not message.startswith("?"):
        return

    date_str = _doc_date_str(doc)
    platform = doc.get("platform", "twitch")
    user_id = str(doc.get("user_id") or username)

    await db.folhinha_daily.update_one(
        {"date": date_str, "platform": platform, "user_id": user_id},
        {
            "$inc": {"count": 1},
            "$set": {
                "username": username,
                "display_name": doc.get("display_name", username),
            },
            "$setOnInsert": {
                "date": date_str,
                "platform": platform,
                "user_id": user_id,
            },
        },
        upsert=True,
    )


async def _inc_famosinhos(
    *,
    date_str: str,
    platform: str,
    user_id: str,
    username: str,
    display_name: str,
    source: str,
    amount: int = 1,
) -> None:
    if amount <= 0:
        return
    await db.famosinhos_daily.update_one(
        {"date": date_str, "platform": platform, "user_id": user_id, "source": source},
        {
            "$inc": {"count": amount},
            "$set": {
                "username": username,
                "display_name": display_name,
            },
            "$setOnInsert": {
                "date": date_str,
                "platform": platform,
                "user_id": user_id,
                "source": source,
            },
        },
        upsert=True,
    )


async def record_famosinhos(doc: dict) -> None:
    """Increment Famosinhos for real reply-parent, else 10s heuristic targets."""
    username = (doc.get("username") or "").lower()
    if username in IGNORED_BOTS:
        return

    ts = doc["timestamp"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    date_str = ts.astimezone(BRT).strftime("%Y-%m-%d")
    platform = doc.get("platform", "twitch")

    reply_uid = doc.get("reply_to_user_id")
    reply_user = (doc.get("reply_to_username") or "").lower()
    if reply_uid or reply_user:
        target_id = str(reply_uid or reply_user)
        target_name = reply_user or target_id
        target_display = doc.get("reply_to_display_name") or target_name
        await _inc_famosinhos(
            date_str=date_str,
            platform=platform,
            user_id=target_id,
            username=target_name,
            display_name=target_display,
            source="reply",
        )
        return

    # Live heuristic: anyone who spoke in the prior 10s on same platform
    window_start = ts - timedelta(seconds=REPLY_WINDOW_SECONDS)
    others = await db.messages.find(
        {
            **BOT_FILTER,
            "platform": platform,
            "timestamp": {"$gte": window_start, "$lt": ts},
            "username": {"$ne": username},
        },
        {"user_id": 1, "username": 1, "display_name": 1},
    ).limit(50).to_list(50)

    seen: set[str] = set()
    for other in others:
        oid = str(other.get("user_id") or other.get("username"))
        if oid in seen:
            continue
        seen.add(oid)
        oname = (other.get("username") or "").lower()
        if oname in IGNORED_BOTS:
            continue
        await _inc_famosinhos(
            date_str=date_str,
            platform=platform,
            user_id=oid,
            username=oname,
            display_name=other.get("display_name") or oname,
            source="heuristic",
        )


async def _record_emote_usage_safe(doc: dict) -> None:
    from app.services.emote_service import record_emote_usage
    await record_emote_usage(doc)


COPYCAT_LOOKBACK = 10
COPYCAT_LOOKBACK_FETCH = 50
_COPY_WS_RE = re.compile(r"\s+")


def normalize_copy_text(message: str | None) -> str:
    """Trim, lowercase, collapse whitespace for copy matching."""
    if not message:
        return ""
    return _COPY_WS_RE.sub(" ", message.strip().lower())


async def _inc_simple_daily(
    collection,
    *,
    date_str: str,
    platform: str,
    user_id: str,
    username: str,
    display_name: str,
    amount: int = 1,
) -> None:
    if amount <= 0:
        return
    await collection.update_one(
        {"date": date_str, "platform": platform, "user_id": user_id},
        {
            "$inc": {"count": amount},
            "$set": {
                "username": username,
                "display_name": display_name,
            },
            "$setOnInsert": {
                "date": date_str,
                "platform": platform,
                "user_id": user_id,
            },
        },
        upsert=True,
    )


def _find_copy_source(
    norm: str,
    author_username: str,
    candidates: list[dict],
) -> dict | None:
    """Return most recent prior msg (among others) whose normalized text matches."""
    taken = 0
    for other in candidates:
        oname = (other.get("username") or "").lower()
        if not oname or oname == author_username or oname in IGNORED_BOTS:
            continue
        taken += 1
        if normalize_copy_text(other.get("message")) == norm:
            return other
        if taken >= COPYCAT_LOOKBACK:
            break
    return None


async def record_copycats(doc: dict) -> None:
    """Maria (copier) + Escritor roubado (copied author) from 10-message lookback."""
    username = (doc.get("username") or "").lower()
    if username in IGNORED_BOTS:
        return

    norm = normalize_copy_text(doc.get("message"))
    if not norm:
        return

    ts = doc["timestamp"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    date_str = ts.astimezone(BRT).strftime("%Y-%m-%d")
    platform = doc.get("platform") or "twitch"
    user_id = str(doc.get("user_id") or username)
    display_name = doc.get("display_name") or username

    others = await db.messages.find(
        {
            **BOT_FILTER,
            "platform": platform,
            "timestamp": {"$lt": ts},
        },
        {"user_id": 1, "username": 1, "display_name": 1, "message": 1},
    ).sort("timestamp", -1).limit(COPYCAT_LOOKBACK_FETCH).to_list(COPYCAT_LOOKBACK_FETCH)

    source = _find_copy_source(norm, username, others)
    if not source:
        return

    await _inc_simple_daily(
        db.maria_daily,
        date_str=date_str,
        platform=platform,
        user_id=user_id,
        username=username,
        display_name=display_name,
    )

    src_name = (source.get("username") or "").lower()
    if src_name and src_name not in IGNORED_BOTS:
        src_id = str(source.get("user_id") or src_name)
        await _inc_simple_daily(
            db.escritor_roubado_daily,
            date_str=date_str,
            platform=platform,
            user_id=src_id,
            username=src_name,
            display_name=source.get("display_name") or src_name,
        )


# Plugin list: new daily-counter boards append a record_* here (+ indexes + backfill).
INGEST_HANDLERS = [
    record_daily_stats,
    record_smoke_session,
    record_folhinha,
    record_famosinhos,
    record_copycats,
    _record_emote_usage_safe,
]


async def backfill_folhinha() -> int:
    existing = await db.folhinha_daily.estimated_document_count()
    if existing > 100:
        logger.info("folhinha_daily already populated (%d), skipping", existing)
        return existing

    logger.info("Starting folhinha_daily backfill...")
    pipeline = [
        {
            "$match": {
                **BOT_FILTER,
                "message": {"$regex": r"^\s*\?"},
            }
        },
        NORMALIZE_PLATFORM_STAGE,
        {
            "$group": {
                "_id": {
                    "platform": "$_platform",
                    "user_id": {"$ifNull": ["$user_id", "$username"]},
                    "date": {
                        "$dateToString": {
                            "date": "$timestamp",
                            "timezone": BRT_TZ_OFFSET,
                            "format": "%Y-%m-%d",
                        }
                    },
                },
                "username": {"$last": "$username"},
                "display_name": {"$last": "$display_name"},
                "count": {"$sum": 1},
            }
        },
    ]

    ops: list[UpdateOne] = []
    total = 0
    from pymongo import UpdateOne as UO

    async for row in db.messages.aggregate(pipeline, allowDiskUse=True):
        doc = {
            "date": row["_id"]["date"],
            "platform": row["_id"].get("platform", "twitch"),
            "user_id": str(row["_id"]["user_id"]),
            "username": row["username"],
            "display_name": row.get("display_name") or row["username"],
            "count": int(row["count"]),
        }
        ops.append(
            UO(
                {
                    "date": doc["date"],
                    "platform": doc["platform"],
                    "user_id": doc["user_id"],
                },
                {"$set": doc},
                upsert=True,
            )
        )
        if len(ops) >= 500:
            await db.folhinha_daily.bulk_write(ops, ordered=False)
            total += len(ops)
            ops.clear()
    if ops:
        await db.folhinha_daily.bulk_write(ops, ordered=False)
        total += len(ops)

    logger.info("folhinha_daily backfill complete: %d rows", total)
    return total


async def backfill_famosinhos_heuristic() -> int:
    """Build heuristic Famosinhos from chronological proximity (skip if already populated)."""
    existing = await db.famosinhos_daily.count_documents({"source": "heuristic"})
    if existing > 100:
        logger.info("famosinhos heuristic already populated (%d), skipping", existing)
        return existing

    logger.info("Starting famosinhos heuristic backfill...")
    from collections import defaultdict, deque

    # Per-platform sliding window of (ts, user_id, username, display_name)
    windows: dict[str, deque] = defaultdict(deque)
    buckets: dict[tuple, dict] = {}

    cursor = db.messages.find(
        BOT_FILTER,
        {
            "timestamp": 1,
            "platform": 1,
            "user_id": 1,
            "username": 1,
            "display_name": 1,
            "reply_to_user_id": 1,
            "reply_to_username": 1,
        },
    ).sort("timestamp", 1).batch_size(2000)

    processed = 0
    async for doc in cursor:
        processed += 1
        # Skip messages that already have real reply tags (live path handles those)
        if doc.get("reply_to_user_id") or doc.get("reply_to_username"):
            continue

        ts = doc.get("timestamp")
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        platform = doc.get("platform") or "twitch"
        username = (doc.get("username") or "").lower()
        window = windows[platform]
        cutoff = ts - timedelta(seconds=REPLY_WINDOW_SECONDS)

        while window and window[0][0] < cutoff:
            window.popleft()

        seen: set[str] = set()
        date_str = ts.astimezone(BRT).strftime("%Y-%m-%d")
        for ots, oid, oname, odisplay in window:
            if oid in seen or oname == username:
                continue
            seen.add(oid)
            key = (date_str, platform, oid, "heuristic")
            if key not in buckets:
                buckets[key] = {
                    "date": date_str,
                    "platform": platform,
                    "user_id": oid,
                    "source": "heuristic",
                    "username": oname,
                    "display_name": odisplay,
                    "count": 0,
                }
            buckets[key]["count"] += 1
            buckets[key]["username"] = oname
            buckets[key]["display_name"] = odisplay

        uid = str(doc.get("user_id") or username)
        window.append((ts, uid, username, doc.get("display_name") or username))

        if processed % 100000 == 0:
            logger.info(
                "famosinhos backfill scanned %d msgs, %d buckets",
                processed,
                len(buckets),
            )

    from pymongo import UpdateOne as UO

    ops: list = []
    written = 0
    for doc in buckets.values():
        ops.append(
            UO(
                {
                    "date": doc["date"],
                    "platform": doc["platform"],
                    "user_id": doc["user_id"],
                    "source": doc["source"],
                },
                {"$set": doc},
                upsert=True,
            )
        )
        if len(ops) >= 500:
            await db.famosinhos_daily.bulk_write(ops, ordered=False)
            written += len(ops)
            ops.clear()
    if ops:
        await db.famosinhos_daily.bulk_write(ops, ordered=False)
        written += len(ops)

    logger.info(
        "famosinhos heuristic backfill complete: scanned %d, wrote %d",
        processed,
        written,
    )
    return written


async def backfill_copycats() -> int:
    """Build Maria / Escritor roubado daily counters from chronological copy lookback."""
    existing = await db.maria_daily.estimated_document_count()
    if existing > 100:
        logger.info("maria_daily already populated (%d), skipping copycats backfill", existing)
        return existing

    logger.info("Starting Maria / Escritor roubado backfill...")
    from collections import defaultdict, deque

    # Per-platform recent messages: (norm, user_id, username, display_name)
    windows: dict[str, deque] = defaultdict(deque)
    maria_buckets: dict[tuple, dict] = {}
    escritor_buckets: dict[tuple, dict] = {}
    window_cap = COPYCAT_LOOKBACK_FETCH * 2

    cursor = db.messages.find(
        BOT_FILTER,
        {
            "timestamp": 1,
            "platform": 1,
            "user_id": 1,
            "username": 1,
            "display_name": 1,
            "message": 1,
        },
    ).sort("timestamp", 1).batch_size(2000)

    processed = 0
    hits = 0
    async for doc in cursor:
        processed += 1
        ts = doc.get("timestamp")
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        platform = doc.get("platform") or "twitch"
        username = (doc.get("username") or "").lower()
        if username in IGNORED_BOTS:
            continue
        uid = str(doc.get("user_id") or username)
        display = doc.get("display_name") or username
        norm = normalize_copy_text(doc.get("message"))
        window = windows[platform]

        if norm:
            taken = 0
            matched = None
            for onorm, oid, oname, odisplay in reversed(window):
                if oname == username or oname in IGNORED_BOTS:
                    continue
                taken += 1
                if onorm == norm:
                    matched = (oid, oname, odisplay)
                    break
                if taken >= COPYCAT_LOOKBACK:
                    break

            if matched:
                hits += 1
                date_str = ts.astimezone(BRT).strftime("%Y-%m-%d")
                mkey = (date_str, platform, uid)
                if mkey not in maria_buckets:
                    maria_buckets[mkey] = {
                        "date": date_str,
                        "platform": platform,
                        "user_id": uid,
                        "username": username,
                        "display_name": display,
                        "count": 0,
                    }
                maria_buckets[mkey]["count"] += 1
                maria_buckets[mkey]["username"] = username
                maria_buckets[mkey]["display_name"] = display

                oid, oname, odisplay = matched
                ekey = (date_str, platform, oid)
                if ekey not in escritor_buckets:
                    escritor_buckets[ekey] = {
                        "date": date_str,
                        "platform": platform,
                        "user_id": oid,
                        "username": oname,
                        "display_name": odisplay,
                        "count": 0,
                    }
                escritor_buckets[ekey]["count"] += 1
                escritor_buckets[ekey]["username"] = oname
                escritor_buckets[ekey]["display_name"] = odisplay

        window.append((norm, uid, username, display))
        while len(window) > window_cap:
            window.popleft()

        if processed % 100000 == 0:
            logger.info(
                "copycats backfill scanned %d msgs, %d hits, maria=%d escritor=%d",
                processed,
                hits,
                len(maria_buckets),
                len(escritor_buckets),
            )

    from pymongo import UpdateOne as UO

    async def _flush(coll, buckets: dict) -> int:
        ops: list = []
        written = 0
        for row in buckets.values():
            ops.append(
                UO(
                    {
                        "date": row["date"],
                        "platform": row["platform"],
                        "user_id": row["user_id"],
                    },
                    {"$set": row},
                    upsert=True,
                )
            )
            if len(ops) >= 500:
                await coll.bulk_write(ops, ordered=False)
                written += len(ops)
                ops.clear()
        if ops:
            await coll.bulk_write(ops, ordered=False)
            written += len(ops)
        return written

    written_m = await _flush(db.maria_daily, maria_buckets)
    written_e = await _flush(db.escritor_roubado_daily, escritor_buckets)
    logger.info(
        "copycats backfill complete: scanned %d, hits %d, wrote maria=%d escritor=%d",
        processed,
        hits,
        written_m,
        written_e,
    )
    return written_m + written_e


async def get_named_daily_leaderboard(
    collection_name: str,
    period: str,
    platform: str,
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
    source: str | None = None,
) -> list[dict]:
    """Generic top-N from famosinhos_daily or folhinha_daily.

    Optional ``source`` filters famosinhos rows by ``reply`` / ``heuristic``
    (ignored for collections without a source field).
    """
    coll = getattr(db, collection_name)
    date_range = resolve_period_dates(period, start_date, end_date)
    match: dict = {}
    if date_range:
        start, end = date_range
        match["date"] = {"$gte": start, "$lte": end}
    if platform in ("twitch", "kick"):
        match["platform"] = platform
    if source in ("reply", "heuristic"):
        match["source"] = source

    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {
            "$group": {
                "_id": {"platform": "$platform", "user_id": "$user_id"},
                "username": {"$last": "$username"},
                "display_name": {"$last": "$display_name"},
                "count": {"$sum": "$count"},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    rows = await coll.aggregate(pipeline).to_list(limit)
    return [
        {
            "rank": i + 1,
            "username": r["username"],
            "display_name": r.get("display_name") or r["username"],
            "platform": r["_id"].get("platform", "twitch"),
            "count": int(r["count"]),
        }
        for i, r in enumerate(rows)
    ]


FOLHINHA_COMMANDS_SCAN_LIMIT = 50000


async def get_folhinha_commands(
    period: str = "all",
    platform: str = "all",
    limit: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Rank Folhinha ?comando tokens from chat messages in the period."""
    from collections import Counter

    date_range = resolve_period_dates(period, start_date, end_date)
    match: dict = {
        **BOT_FILTER,
        "message": {"$regex": r"^\s*\?"},
    }
    if date_range:
        start_utc, end_utc = date_range_to_utc_bounds(date_range[0], date_range[1])
        match["timestamp"] = {"$gte": start_utc, "$lt": end_utc}
    if platform in ("twitch", "kick"):
        match["platform"] = platform

    cursor = (
        db.messages.find(match, {"message": 1})
        .sort("timestamp", -1)
        .limit(FOLHINHA_COMMANDS_SCAN_LIMIT)
    )
    counts: Counter[str] = Counter()
    async for doc in cursor:
        raw = (doc.get("message") or "").strip()
        if not raw.startswith("?"):
            continue
        token = raw[1:].split(None, 1)[0] if len(raw) > 1 else ""
        command = token.lower().strip("?!.,:;")
        if command:
            counts[command] += 1

    top = counts.most_common(limit)
    return [
        {"rank": i + 1, "command": cmd, "count": count}
        for i, (cmd, count) in enumerate(top)
    ]
