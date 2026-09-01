from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, field_serializer


class SubathonTimerResponse(BaseModel):
    mode: Literal["untilStart", "remainingLive"]
    remaining_seconds: int
    target_at: datetime | None = None
    as_of: datetime
    placeholder: bool = False

    @field_serializer("target_at", "as_of")
    def serialize_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
