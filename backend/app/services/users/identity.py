"""User identity resolution helpers."""

import re

from app.database import db
from app.services.common.query import VALID_PLATFORMS, get_platform_filter, merge_queries


async def resolve_user_identity(username: str, platform: str = "all") -> tuple[str | None, str | None]:
    """
    Resolve user_id and platform for a username.
    Returns (None, None) if user not found or ambiguous when platform is 'all'.
    """
    username_lower = username.lower()

    if platform in VALID_PLATFORMS:
        doc = await db.messages.find_one(
            merge_queries(
                {"username": username_lower},
                get_platform_filter(platform),
                {"user_id": {"$exists": True}},
            ),
            sort=[("timestamp", -1)],
        )
        if doc:
            return doc.get("user_id"), platform
        exists = await db.messages.find_one(
            merge_queries({"username": username_lower}, get_platform_filter(platform)),
            sort=[("timestamp", -1)],
        )
        if exists:
            return exists.get("user_id"), platform
        return None, None

    platforms = await db.messages.distinct("platform", {"username": username_lower})
    legacy_exists = await db.messages.count_documents(
        {"username": username_lower, "platform": {"$exists": False}},
        limit=1,
    )
    if legacy_exists and "twitch" not in platforms:
        platforms.append("twitch")
    if len(platforms) != 1:
        return None, None

    resolved_platform = platforms[0] if platforms[0] in VALID_PLATFORMS else "twitch"
    doc = await db.messages.find_one(
        merge_queries(
            {"username": username_lower},
            get_platform_filter(resolved_platform),
            {"user_id": {"$exists": True}},
        ),
        sort=[("timestamp", -1)],
    )
    if doc:
        return doc.get("user_id"), resolved_platform

    exists = await db.messages.find_one(
        merge_queries({"username": username_lower}, get_platform_filter(resolved_platform)),
        sort=[("timestamp", -1)],
    )
    if exists:
        return exists.get("user_id"), resolved_platform
    return None, None


async def resolve_user_id(username: str, platform: str = "all") -> str | None:
    user_id, _ = await resolve_user_identity(username, platform)
    return user_id


async def resolve_username(raw: str, platform: str = "all") -> str | None:
    """
    Resolve a Twitch/Kick login from raw input (login or unique display_name).
    Returns lowercase username, or None if not found / ambiguous.
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    login = raw.lower()
    _, plat = await resolve_user_identity(login, platform)
    if plat is not None:
        return login

    if platform == "all":
        exists = await db.user_totals.find_one(
            {"username": login},
            projection={"_id": 1},
        )
        if exists:
            return login
    else:
        exists = await db.user_totals.find_one(
            {"platform": platform, "username": login},
            projection={"_id": 1},
        )
        if exists:
            return login

    escaped = re.escape(raw)
    match: dict = {"display_name": {"$regex": f"^{escaped}$", "$options": "i"}}
    if platform in VALID_PLATFORMS:
        match["platform"] = platform
    rows = await db.user_totals.aggregate([
        {"$match": match},
        {"$group": {"_id": "$username"}},
        {"$limit": 2},
    ]).to_list(2)
    if len(rows) == 1 and rows[0].get("_id"):
        return str(rows[0]["_id"]).lower()
    return None


def get_user_query(username: str, user_id: str | None, platform: str | None = None) -> dict:
    """
    Build a query that matches messages by user_id (if available) OR username.
    This ensures we get all messages even if the user changed their username.
    """
    if user_id:
        base = {
            "$or": [
                {"user_id": user_id},
                {"username": username.lower(), "user_id": {"$exists": False}},
            ]
        }
    else:
        base = {"username": username.lower()}

    if platform:
        return merge_queries(base, get_platform_filter(platform))
    return base
