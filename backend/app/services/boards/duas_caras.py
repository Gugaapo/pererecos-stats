"""Duas Caras — who changed login the most (distinct known_usernames)."""

from app.database import db
from app.models.schemas import DuasCarasEntry, DuasCarasResponse
from app.services.common.cache import get_stats_cache, set_stats_cache, stats_cache_key
from app.services.common.query import IGNORED_BOTS, VALID_PLATFORMS
from app.services.boards.base import BoardSpec, register_board


async def get_duas_caras_leaderboard(
    platform: str = "all",
    limit: int = 10,
) -> DuasCarasResponse:
    """Rank users by distinct logins ever seen (known_usernames). All-time only."""
    cache_key = stats_cache_key("duas_caras", platform=platform, limit=limit)
    cached = get_stats_cache(cache_key)
    if cached is not None:
        return cached

    match: dict = {
        "known_usernames.1": {"$exists": True},
        "user_id": {"$exists": True, "$nin": [None, ""]},
        "username": {"$nin": list(IGNORED_BOTS)},
    }
    if platform in VALID_PLATFORMS:
        match["platform"] = platform

    pipeline = [
        {"$match": match},
        {
            "$addFields": {
                "name_count": {"$size": {"$ifNull": ["$known_usernames", []]}},
                "_legacy": {"$eq": ["$user_id", "$username"]},
            }
        },
        {"$match": {"_legacy": False, "name_count": {"$gte": 2}}},
        {"$sort": {"name_count": -1, "message_count": -1, "username": 1}},
        {"$limit": limit},
        {
            "$project": {
                "username": 1,
                "display_name": 1,
                "platform": 1,
                "name_count": 1,
                "known_usernames": 1,
            }
        },
    ]

    rows = await db.user_totals.aggregate(pipeline).to_list(limit)
    leaderboard = [
        DuasCarasEntry(
            rank=i + 1,
            username=row["username"],
            display_name=row.get("display_name") or row["username"],
            platform=row.get("platform", "twitch"),
            name_count=int(row.get("name_count", 0)),
            known_usernames=list(row.get("known_usernames") or []),
        )
        for i, row in enumerate(rows)
    ]
    result = DuasCarasResponse(platform=platform, leaderboard=leaderboard)
    set_stats_cache(cache_key, result)
    return result


async def _duas_caras_rank_for_user(
    username: str,
    user_id: str | None,
    platform: str,
) -> tuple[int | None, int | None]:
    """Return (rank, name_count) for a user. Rank only if on the board (top 200)."""
    plat_filter = platform if platform in VALID_PLATFORMS else "all"
    resp = await get_duas_caras_leaderboard(platform=plat_filter, limit=200)
    for entry in resp.leaderboard:
        if entry.username == username and entry.platform == platform:
            return entry.rank, entry.name_count
        if entry.username == username and plat_filter == "all":
            return entry.rank, entry.name_count

    # Eligible but outside top-N: still expose count for Seus Rankings / Comparar
    query: dict = {"username": username}
    if user_id and user_id != username:
        query = {"platform": platform, "user_id": str(user_id)} if platform in VALID_PLATFORMS else {
            "user_id": str(user_id)
        }
    elif platform in VALID_PLATFORMS:
        query["platform"] = platform

    doc = await db.user_totals.find_one(
        query,
        {"known_usernames": 1, "username": 1, "user_id": 1},
    )
    if not doc and user_id:
        doc = await db.user_totals.find_one(
            {"user_id": str(user_id)},
            {"known_usernames": 1, "username": 1, "user_id": 1},
        )
    if not doc:
        return None, None
    if str(doc.get("user_id") or "") == str(doc.get("username") or ""):
        return None, None
    names = doc.get("known_usernames") or []
    count = len(names)
    if count < 2:
        return None, None
    return None, count


async def rank_duas_caras_user(
    username: str,
    user_id: str | None = None,
    platform: str = "twitch",
    period: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[int | None, int | None]:
    """BoardSpec-compatible rank_user wrapper."""
    return await _duas_caras_rank_for_user(username, user_id, platform)


async def fetch_duas_caras_top(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[str, str, str]]:
    resp = await get_duas_caras_leaderboard(platform=platform, limit=limit)
    return [(e.username, e.display_name, e.platform) for e in resp.leaderboard]


DUAS_CARAS_BOARD = register_board(
    BoardSpec(
        id="duas_caras",
        label="Duas Caras",
        fetch_top=fetch_duas_caras_top,
        rank_user=rank_duas_caras_user,
        rankings_fields=("duas_caras_rank", "duas_caras_count"),
        include_in_pererecoes=True,
    )
)
