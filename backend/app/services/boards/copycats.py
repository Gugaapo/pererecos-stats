"""Copycat boards: Maria vai com as outras + Escritor roubado."""

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
            collection,
            period,
            platform,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
        return [
            (r["username"], r["display_name"], r.get("platform", "twitch"))
            for r in rows
        ]

    return fetch_top


MARIA_BOARD = register_board(
    BoardSpec(
        id="maria-vai-com-as-outras",
        label="Maria vai com as outras",
        fetch_top=_named_fetcher("maria_daily"),
        rankings_fields=("maria_vai_com_as_outras_rank", "maria_vai_com_as_outras_count"),
        include_in_pererecoes=True,
        meta={"collection": "maria_daily"},
    )
)

ESCRITOR_BOARD = register_board(
    BoardSpec(
        id="escritor-roubado",
        label="Escritor roubado",
        fetch_top=_named_fetcher("escritor_roubado_daily"),
        rankings_fields=("escritor_roubado_rank", "escritor_roubado_count"),
        include_in_pererecoes=True,
        meta={"collection": "escritor_roubado_daily"},
    )
)
