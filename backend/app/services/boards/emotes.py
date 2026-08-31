"""Emote-related Pererecães boards (diversidade, creators)."""

from app.services.boards.base import BoardSpec, register_board


async def fetch_diversidade_top(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[str, str, str]]:
    from app.services.emote_service import get_diversidade

    resp = await get_diversidade(
        platform=platform, limit=limit, period=period,
        start_date=start_date, end_date=end_date,
    )
    return [(e.username, e.display_name, e.platform) for e in resp.leaderboard]


async def fetch_creators_top(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[str, str, str]]:
    from app.services.emote_service import get_emote_creators

    resp = await get_emote_creators(
        platform=platform, limit=limit, period=period,
        start_date=start_date, end_date=end_date,
    )
    return [(e.username, e.display_name, "twitch") for e in resp.creators]


DIVERSIDADE_BOARD = register_board(
    BoardSpec(
        id="diversidade",
        label="Diversidade",
        fetch_top=fetch_diversidade_top,
        rankings_fields=("diversidade_rank", "diversidade_count"),
        include_in_pererecoes=True,
    )
)

CREATORS_BOARD = register_board(
    BoardSpec(
        id="creators",
        label="Criadores",
        fetch_top=fetch_creators_top,
        rankings_fields=("creators_rank", "creators_count"),
        include_in_pererecoes=True,
    )
)
