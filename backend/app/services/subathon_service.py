"""Subathon header timer.

Before SUBATHON_START: countdown to start (untilStart).
On/after start: remaining live hours (placeholder until real API exists).
Swap the remainingLive branch later for the real upstream.
"""

from datetime import datetime, timezone

from app.config import get_settings
from app.ingest_gate import COLLECTION_START, ingest_enabled


def get_timer() -> dict:
    settings = get_settings()
    now = datetime.now(timezone.utc)

    if not ingest_enabled():
        remaining = max(0, int((COLLECTION_START - now).total_seconds()))
        return {
            "mode": "untilStart",
            "remaining_seconds": remaining,
            "target_at": COLLECTION_START,
            "as_of": now,
            "placeholder": False,
        }

    # Placeholder remaining-live hours until real API is wired.
    remaining = max(0, int(settings.subathon_placeholder_seconds))
    return {
        "mode": "remainingLive",
        "remaining_seconds": remaining,
        "target_at": None,
        "as_of": now,
        "placeholder": True,
    }
