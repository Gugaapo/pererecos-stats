"""Pluggable leaderboard boards (BoardSpec registry)."""

from app.services.boards.base import (
    BoardSpec,
    all_boards,
    get_board,
    pererecoes_boards,
    register_board,
)

__all__ = [
    "BoardSpec",
    "all_boards",
    "get_board",
    "pererecoes_boards",
    "register_board",
    "get_duas_caras_leaderboard",
    "get_pererecoes_leaderboard",
]


def __getattr__(name: str):
    if name == "get_duas_caras_leaderboard":
        from app.services.boards.duas_caras import get_duas_caras_leaderboard
        return get_duas_caras_leaderboard
    if name == "get_pererecoes_leaderboard":
        from app.services.boards.pererecoes import get_pererecoes_leaderboard
        return get_pererecoes_leaderboard
    raise AttributeError(name)
