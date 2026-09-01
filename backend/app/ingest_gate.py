"""Gate chat/moderation ingest until the subathon collection start."""

from datetime import datetime, timezone, timedelta

# 2026-09-01 00:00:00 BRT (UTC-3)
BRT = timezone(timedelta(hours=-3))
COLLECTION_START = datetime(2026, 9, 1, 0, 0, 0, tzinfo=BRT)


def ingest_enabled(now: datetime | None = None) -> bool:
    """Return True once collection may persist messages/events."""
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now >= COLLECTION_START
