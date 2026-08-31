"""SmokeTime / Tragadores board."""

from app.services.boards.base import BoardSpec, register_board


async def fetch_smoke_top(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[str, str, str]]:
    from app.services.smoke_service import get_smoke_time_stats

    resp = await get_smoke_time_stats(
        platform,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
    return [
        (e.username, e.display_name, e.platform)
        for e in (resp.leaderboard or [])[:limit]
    ]


SMOKE_BOARD = register_board(
    BoardSpec(
        id="smoke",
        label="Tragadores",
        fetch_top=fetch_smoke_top,
        rankings_fields=("smoke_rank", "smoke_count"),
        include_in_pererecoes=True,
    )
)
