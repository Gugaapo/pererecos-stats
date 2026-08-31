"""Import all board modules so BoardSpec registrations run once."""

from app.services.boards import messages as messages  # noqa: F401
from app.services.boards import named_daily as named_daily  # noqa: F401
from app.services.boards import emotes as emotes  # noqa: F401
from app.services.boards import smoke as smoke  # noqa: F401
from app.services.boards import duas_caras as duas_caras  # noqa: F401
from app.services.boards import copycats as copycats  # noqa: F401
from app.services.boards.base import (
    BoardSpec,
    all_boards,
    get_board,
    pererecoes_boards,
    register_board,
)
from app.services.boards.duas_caras import get_duas_caras_leaderboard
from app.services.boards.pererecoes import get_pererecoes_leaderboard

__all__ = [
    "BoardSpec",
    "all_boards",
    "get_board",
    "pererecoes_boards",
    "register_board",
    "get_duas_caras_leaderboard",
    "get_pererecoes_leaderboard",
]
