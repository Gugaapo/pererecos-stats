"""Message-based boards: top messages, rising stars, top writers."""

from app.services.boards.base import BoardSpec, register_board


async def fetch_messages_top(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[str, str, str]]:
    from app.services.stats_service import get_leaderboard

    resp = await get_leaderboard(period, limit, platform, start_date, end_date)
    return [(e.username, e.display_name, e.platform) for e in resp.leaderboard]


async def fetch_rising_top(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[str, str, str]]:
    from app.services.stats_service import get_rising_stars

    entries = await get_rising_stars(
        limit=limit, platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )
    return [(e.username, e.display_name, e.platform) for e in entries]


async def fetch_writers_top(
    period: str = "all",
    platform: str = "all",
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[tuple[str, str, str]]:
    from app.services.stats_service import get_top_writers

    entries = await get_top_writers(
        limit=limit, platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )
    return [(e.username, e.display_name, e.platform) for e in entries]


MESSAGES_BOARD = register_board(
    BoardSpec(
        id="messages",
        label="Top Mensagens",
        fetch_top=fetch_messages_top,
        rankings_fields=("top_rank",),
        include_in_pererecoes=True,
    )
)

RISING_BOARD = register_board(
    BoardSpec(
        id="rising",
        label="Top Girinos",
        fetch_top=fetch_rising_top,
        rankings_fields=("rising_rank", "rising_count", "rising_growth"),
        include_in_pererecoes=True,
    )
)

WRITERS_BOARD = register_board(
    BoardSpec(
        id="writers",
        label="Top Textoes",
        fetch_top=fetch_writers_top,
        rankings_fields=("writers_rank", "writers_score", "writers_avg_length"),
        include_in_pererecoes=True,
    )
)
