from pydantic import BaseModel, field_serializer
from datetime import datetime, timezone


class SmokeLeaderboardEntry(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    count: int
    streak_current: int = 0


class SmokeDayPoint(BaseModel):
    date: str  # YYYY-MM-DD
    participants: int


class SmokeBestDay(BaseModel):
    date: str
    participants: int


class SmokeToday(BaseModel):
    participants: int


class SmokeFirstToday(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    first_ts: datetime

    @field_serializer("first_ts")
    def serialize_first_ts(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class SmokeStreakEntry(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    streak: int


class SmokeTimeResponse(BaseModel):
    leaderboard: list[SmokeLeaderboardEntry]
    best_day: SmokeBestDay | None = None
    last_5_days: list[SmokeDayPoint]
    last_30_days: list[SmokeDayPoint] = []
    today: SmokeToday
    total_sessions: int
    total_unique_participants: int
    longest_streaks: list[SmokeStreakEntry] = []
    first_session: str | None = None  # YYYY-MM-DD
    first_today: SmokeFirstToday | None = None


class UserSmokeStats(BaseModel):
    count: int = 0
    streak_current: int = 0
    streak_longest: int = 0
    rank: int | None = None
    first_session: str | None = None  # YYYY-MM-DD
    last_session: str | None = None  # YYYY-MM-DD
