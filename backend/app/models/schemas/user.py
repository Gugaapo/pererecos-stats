from pydantic import BaseModel, Field, field_serializer
from datetime import datetime, timezone
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .leaderboards import PererecoesBreakdown
    from .smoke import UserSmokeStats


class RecentMessage(BaseModel):
    message: str
    timestamp: datetime
    platform: str = "twitch"

    @field_serializer('timestamp')
    def serialize_timestamp(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class HourlyActivity(BaseModel):
    hour: int
    count: int


class RivalInfo(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    similarity_score: float  # 0-100%


class ReplyTarget(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    reply_count: int


class FavoriteHour(BaseModel):
    hour: int
    count: int
    percentage: float


class UserRankings(BaseModel):
    top_rank: int | None = None  # Position in top chatters
    top_rank_change: int | None = None  # +/- vs last week (positive = improved)
    rising_rank: int | None = None  # Position in rising stars
    rising_count: int | None = None
    rising_growth: float | None = None
    writers_rank: int | None = None  # Position in top writers
    writers_score: float | None = None
    writers_avg_length: float | None = None
    hours_dominated: list[int] = []  # Hours where user is #1
    famosinhos_rank: int | None = None
    famosinhos_count: int | None = None
    folhinha_rank: int | None = None
    folhinha_count: int | None = None
    maria_vai_com_as_outras_rank: int | None = None
    maria_vai_com_as_outras_count: int | None = None
    escritor_roubado_rank: int | None = None
    escritor_roubado_count: int | None = None
    diversidade_rank: int | None = None
    diversidade_count: int | None = None
    smoke_rank: int | None = None
    smoke_count: int | None = None
    creators_rank: int | None = None
    creators_count: int | None = None
    duas_caras_rank: int | None = None
    duas_caras_count: int | None = None
    pererecoes_rank: int | None = None
    pererecoes_points: int | None = None
    pererecoes_breakdown: list["PererecoesBreakdown"] = []


class UserEmotePosition(BaseModel):
    label: str  # "esquerdista", "centrão", "direitista"
    positions: "EmotePositionData"


# Forward reference will be resolved via __init__.py imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .emotes import EmoteUsage, EmotePositionData
else:
    EmoteUsage = "EmoteUsage"
    EmotePositionData = "EmotePositionData"


class UserStats(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
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
    top_emotes: list["EmoteUsage"] = []
    emote_position: UserEmotePosition | None = None
    smoke_stats: "UserSmokeStats | None" = None

    @field_serializer('first_message_date', 'last_message_date')
    def serialize_dates(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class UserSearchResult(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    total_messages: int


class UserCoreResponse(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    period: str
    total_messages: int
    percentile: float = 0.0
    first_message_date: datetime | None = None
    last_message_date: datetime | None = None
    favorite_hour: FavoriteHour | None = None
    hourly_activity: list[HourlyActivity] = []
    peak_hours: list[int] = []

    @field_serializer('first_message_date', 'last_message_date')
    def serialize_dates(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class UserActivityResponse(BaseModel):
    hourly_activity: list[HourlyActivity] = []
    peak_hours: list[int] = []
    favorite_hour: FavoriteHour | None = None


class UserRankingsOnlyResponse(BaseModel):
    rankings: UserRankings | None = None


class UserSocialResponse(BaseModel):
    rival: RivalInfo | None = None
    top_replies: list[ReplyTarget] = []


class UserEmotesResponse(BaseModel):
    top_emotes: list["EmoteUsage"] = []
    emote_position: UserEmotePosition | None = None


class UserRecentResponse(BaseModel):
    recent_messages: list[RecentMessage] = []


class UserSmokeOnlyResponse(BaseModel):
    smoke_stats: "UserSmokeStats | None" = None


class FolhinhaPartner(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    count: int
    avg_percentage: float | None = None


class UserFolhinhaStats(BaseModel):
    bonks_given: int = 0
    bonks_received: int = 0
    avg_bonk_pct: float | None = None
    abracos_given: int = 0
    abracos_received: int = 0
    roulette_survives: int = 0
    roulette_deaths: int = 0
    cookies_balance: int | None = None
    slot_won: int = 0
    slot_lost: int = 0
    top_bonk_targets: list[FolhinhaPartner] = []
    top_bonk_from: list[FolhinhaPartner] = []
    top_abraco_targets: list[FolhinhaPartner] = []
    top_abraco_from: list[FolhinhaPartner] = []


class UserFolhinhaOnlyResponse(BaseModel):
    folhinha_stats: UserFolhinhaStats | None = None


class PastUsername(BaseModel):
    username: str
    display_name: str
    first_seen: datetime
    last_seen: datetime

    @field_serializer('first_seen', 'last_seen')
    def serialize_dates(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class UsernameHistoryResponse(BaseModel):
    current_username: str
    user_id: str | None = None
    past_usernames: list[PastUsername] = []


class FeedbackRequest(BaseModel):
    type: Literal["bug", "sugestao"]
    message: str = Field(..., min_length=10, max_length=2000)


class FeedbackResponse(BaseModel):
    success: bool
    id: str


class HealthResponse(BaseModel):
    status: str
    bot_connected: bool
    kick_connected: bool = False
    database_connected: bool


class UserComparisonResponse(BaseModel):
    user1: UserStats
    user2: UserStats


class RandomMessageItem(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    message: str
    timestamp: datetime

    @field_serializer('timestamp')
    def serialize_timestamp(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class RandomMessageResponse(BaseModel):
    focus: RandomMessageItem
    before: list[RandomMessageItem] = []
    after: list[RandomMessageItem] = []
    # Flattened focus fields for convenience
    username: str = ""
    display_name: str = ""
    platform: str = "twitch"
    message: str = ""
    timestamp: datetime | None = None

    @field_serializer('timestamp')
    def serialize_timestamp(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
