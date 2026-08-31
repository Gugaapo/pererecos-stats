"""Folhinha interaction package."""

from app.services.folhinha.events import process_message_doc
from app.services.folhinha.leaderboards import get_folhinha_board

__all__ = ["process_message_doc", "get_folhinha_board"]
