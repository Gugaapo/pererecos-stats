from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, field_serializer


class SubathonTimerResponse(BaseModel):
    mode: Literal[
        "running", "paused", "locked", "ended", "unavailable", "untilStart"
    ]
    state: str | None = None
    direction: str | None = None
    remaining_seconds: int | None = None
    ends_at: datetime | None = None
    paused_at: datetime | None = None
    paused_total_seconds: int = 0
    locked: bool = False
    paused: bool = False
    target_at: datetime | None = None
    server_now: datetime
    fetched_at: datetime | None = None
    stale: bool = False
    placeholder: bool = False

    @field_serializer("ends_at", "paused_at", "target_at", "server_now", "fetched_at")
    def serialize_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class SubathonOverviewResponse(BaseModel):
    days_tracked: int = 0
    first_observation: datetime | None = None
    total_added_seconds: int = 0
    biggest_day: dict[str, Any] | None = None
    most_static_day: dict[str, Any] | None = None
    longest_active_streak: int = 0
    current_active_streak: int = 0
    longest_gap: dict[str, Any] | None = None
    paused_total_seconds: int = 0
    increase_count: int = 0
    avg_added_per_day_seconds: int = 0
    current_remaining_seconds: int | None = None


class SubathonDiagnosticsResponse(BaseModel):
    last_success_at: datetime | None = None
    error_count: int = 0
    stale: bool = False
    snapshots_24h: int = 0
    increases_24h: int = 0
    poll_granted_seconds_24h: int = 0
    webhook_granted_seconds_24h: int = 0
    agreement_ratio: float | None = None
    timer_feed_url: str = ""
    pixie_webhook_configured: bool = False
