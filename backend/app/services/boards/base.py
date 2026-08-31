"""BoardSpec contract for pluggable leaderboards."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# fetch_top(period, platform, limit, start_date, end_date) -> list of tuples
#   (username, display_name, platform) for Pererecães, or richer objects for HTTP
FetchTopFn = Callable[..., Awaitable[list]]

# rank_user(username, user_id, platform, period, start_date, end_date)
#   -> (rank|None, value|None) or (rank, value, extra...)
RankUserFn = Callable[..., Awaitable[tuple]]


@dataclass
class BoardSpec:
    id: str
    label: str
    fetch_top: FetchTopFn
    rank_user: RankUserFn | None = None
    rankings_fields: tuple[str, ...] = ()
    include_in_pererecoes: bool = True
    # Optional: convert fetch_top rows for Pererecães to (username, display_name, platform)
    as_pererecoes_row: Callable[[Any], tuple[str, str, str]] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


_REGISTRY: list[BoardSpec] = []


def register_board(spec: BoardSpec) -> BoardSpec:
    _REGISTRY.append(spec)
    return spec


def all_boards() -> list[BoardSpec]:
    return list(_REGISTRY)


def pererecoes_boards() -> list[BoardSpec]:
    return [b for b in _REGISTRY if b.include_in_pererecoes]


def get_board(board_id: str) -> BoardSpec | None:
    for b in _REGISTRY:
        if b.id == board_id:
            return b
    return None
