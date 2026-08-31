"""Named daily counter boards (famosinhos, folhinha)."""

from app.services.boards.base import BoardSpec, register_board


def _named_fetcher(collection: str):
    async def fetch_top(
        period: str = "all",
        platform: str = "all",
        limit: int = 10,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[tuple[str, str, str]]:
        from app.services.stats_aggregates import get_named_daily_leaderboard

        rows = await get_named_daily_leaderboard(
            collection, period, platform, limit=limit,
            start_date=start_date, end_date=end_date,
        )
        return [
            (r["username"], r["display_name"], r.get("platform", "twitch"))
            for r in rows
        ]

    return fetch_top


FAMOSINHOS_BOARD = register_board(
    BoardSpec(
        id="famosinhos",
        label="Famosinhos",
        fetch_top=_named_fetcher("famosinhos_daily"),
        rankings_fields=("famosinhos_rank", "famosinhos_count"),
        include_in_pererecoes=True,
        meta={"collection": "famosinhos_daily"},
    )
)

FOLHINHA_BOARD = register_board(
    BoardSpec(
        id="folhinha",
        label="Folhinha",
        fetch_top=_named_fetcher("folhinha_daily"),
        rankings_fields=("folhinha_rank", "folhinha_count"),
        include_in_pererecoes=True,
        meta={"collection": "folhinha_daily"},
    )
)
