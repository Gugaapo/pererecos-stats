from pydantic import BaseModel
from datetime import datetime


class HourlyActivity(BaseModel):
    hour: int
    count: int


class RecentMessage(BaseModel):
    message: str
    timestamp: datetime


class RivalInfo(BaseModel):
    username: str
    display_name: str
    similarity_score: float  # 0-100%


class ReplyTarget(BaseModel):
    username: str
    display_name: str
    reply_count: int


class ActiveChatter(BaseModel):
    username: str
    display_name: str
    message_count: int


class UserSearchResult(BaseModel):
    username: str
    display_name: str
    total_messages: int


class UserRankings(BaseModel):
    top_rank: int | None = None  # Position in top chatters
    top_rank_change: int | None = None  # +/- vs last week (positive = improved)
    rising_rank: int | None = None  # Position in rising stars
    writers_rank: int | None = None  # Position in top writers
    hours_dominated: list[int] = []  # Hours where user is #1


class FavoriteHour(BaseModel):
    hour: int
    count: int
    percentage: float


class EmoteUsage(BaseModel):
    emote_name: str
    emote_id: str
    count: int


class UserStats(BaseModel):
    username: str
    display_name: str
    period: str
    total_messages: int
    hourly_activity: list[HourlyActivity]
    recent_messages: list[RecentMessage] = []
    first_message_date: datetime | None = None
    last_message_date: datetime | None = None
    percentile: float = 0.0  # 0-100
    peak_hours: list[int] = []  # e.g., [16, 17, 18]
    favorite_hour: FavoriteHour | None = None
    rival: RivalInfo | None = None
    top_replies: list[ReplyTarget] = []
    rankings: UserRankings | None = None
    top_emotes: list[EmoteUsage] = []


class RisingStarEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    current_count: int
    previous_count: int
    growth_percent: float


class HourLeaderEntry(BaseModel):
    hour: int
    username: str
    display_name: str
    message_count: int


class WriterEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    avg_length: float
    message_count: int


class RisingStarsResponse(BaseModel):
    entries: list[RisingStarEntry]


class HourLeadersResponse(BaseModel):
    entries: list[HourLeaderEntry]


class WritersResponse(BaseModel):
    entries: list[WriterEntry]


class ActiveChattersResponse(BaseModel):
    count: int
    chatters: list[ActiveChatter]


class ChatActivityPoint(BaseModel):
    hour: int
    count: int


class ChatActivityResponse(BaseModel):
    activity: list[ChatActivityPoint]
    total_today: int
    peak_hour: int
    peak_count: int


class OverallActivityResponse(BaseModel):
    activity: list[ChatActivityPoint]
    total_messages: int
    peak_hour: int
    peak_count: int


class TopEmotesResponse(BaseModel):
    emotes: list[EmoteUsage]
    total_emote_uses: int


class UserComparisonResponse(BaseModel):
    user1: UserStats
    user2: UserStats


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    message_count: int


class LeaderboardResponse(BaseModel):
    period: str
    total_users: int
    total_messages: int
    leaderboard: list[LeaderboardEntry]


class HealthResponse(BaseModel):
    status: str
    bot_connected: bool
    database_connected: bool
