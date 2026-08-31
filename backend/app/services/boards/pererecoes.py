"""Meta-leaderboard: Pererecães (sums points across registered boards)."""

import asyncio

from app.models.schemas import (
    PererecoesBreakdown,
    PererecoesEntry,
    PererecoesResponse,
)
from app.services.common.cache import get_stats_cache, set_stats_cache, stats_cache_key
from app.services.boards.base import pererecoes_boards

PERERECOES_POINTS = [100, 80, 70, 60, 50, 40, 30, 15, 10, 5]


async def get_pererecoes_leaderboard(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> PererecoesResponse:
    """Meta-leaderboard: sums position points a user earns across all other boards."""
    # Ensure board modules are registered
    from app.services.boards import registry  # noqa: F401

    cache_key = stats_cache_key(
        "pererecoes", period=period, platform=platform, limit=limit,
        start_date=start_date, end_date=end_date,
    )
    cached = get_stats_cache(cache_key)
    if cached is not None:
        return cached

    boards = pererecoes_boards()
    coros = [
        b.fetch_top(
            period=period, platform=platform, limit=10,
            start_date=start_date, end_date=end_date,
        )
        for b in boards
    ]
    labels = [b.label for b in boards]
    results = await asyncio.gather(*coros, return_exceptions=True)

    scores: dict[str, dict] = {}
    for label, board in zip(labels, results):
        if isinstance(board, Exception) or not board:
            continue
        for idx, row in enumerate(board[:10]):
            if not row:
                continue
            username, display_name, plat = row[0], row[1], row[2]
            if not username:
                continue
            pts = PERERECOES_POINTS[idx]
            key = username.lower()
            rec = scores.get(key)
            if rec is None:
                rec = {
                    "username": key,
                    "display_name": display_name or username,
                    "platform": plat or "twitch",
                    "points": 0,
                    "best_single": 0,
                    "breakdown": [],
                }
                scores[key] = rec
            rec["points"] += pts
            rec["breakdown"].append(
                PererecoesBreakdown(board=label, position=idx + 1, points=pts)
            )
            # Keep display/platform from the board where they scored the most.
            if pts > rec["best_single"]:
                rec["best_single"] = pts
                rec["display_name"] = display_name or username
                rec["platform"] = plat or "twitch"

    ranked = sorted(scores.values(), key=lambda r: r["points"], reverse=True)[:limit]

    leaderboard = [
        PererecoesEntry(
            rank=i + 1,
            username=rec["username"],
            display_name=rec["display_name"],
            platform=rec["platform"],
            points=rec["points"],
            breakdown=sorted(rec["breakdown"], key=lambda b: b.points, reverse=True),
        )
        for i, rec in enumerate(ranked)
    ]
    response = PererecoesResponse(
        period=period, platform=platform, leaderboard=leaderboard,
    )
    set_stats_cache(cache_key, response)
    return response
