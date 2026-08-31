from pydantic import BaseModel


class EmoteUsage(BaseModel):
    emote_name: str
    emote_id: str
    count: int


class TopEmotesResponse(BaseModel):
    emotes: list[EmoteUsage]
    total_emote_uses: int


class EmotePositionData(BaseModel):
    comeco: int
    meio: int
    fim: int
    comeco_pct: float
    meio_pct: float
    fim_pct: float
    total: int


class EmotePositionResponse(BaseModel):
    positions: EmotePositionData


class EmotePositionUserEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    message_count: int
    position_count: int  # emotes in this position
    label: str  # "esquerdista", "centrão", "direitista"


class EmotePositionUsersResponse(BaseModel):
    esquerdistas: list[EmotePositionUserEntry]
    centrao: list[EmotePositionUserEntry]
    direitistas: list[EmotePositionUserEntry]


class EmoteSearchResult(BaseModel):
    emote_name: str
    emote_id: str
    creator_username: str | None = None
    creator_display_name: str | None = None
    source: str = "channel"
    animated: bool = False


class EmoteLeastUsedEntry(BaseModel):
    emote_name: str
    emote_id: str
    count: int
    creator_username: str | None = None
    creator_display_name: str | None = None
    source: str = "channel"


class EmoteLeastUsedResponse(BaseModel):
    unused: list[EmoteLeastUsedEntry] = []
    unused_count: int = 0
    least_used: list[EmoteLeastUsedEntry] = []


class EmoteRankingResponse(BaseModel):
    emotes: list[EmoteLeastUsedEntry]
    total_emotes: int
    total_uses: int


class EmoteCreatorEntry(BaseModel):
    rank: int = 0
    username: str
    display_name: str
    emote_count: int
    sample_emotes: list[str] = []


class EmoteCreatorsResponse(BaseModel):
    creators: list[EmoteCreatorEntry]


class EmoteDiversidadeEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    unique_emotes: int


class EmoteDiversidadeResponse(BaseModel):
    period: str
    platform: str = "all"
    leaderboard: list[EmoteDiversidadeEntry]


class EmoteContributor(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    count: int


class EmotePeriodCounts(BaseModel):
    day: int = 0
    week: int = 0
    month: int = 0
    all: int = 0


class EmoteDetailResponse(BaseModel):
    emote_name: str
    emote_id: str
    creator_username: str | None = None
    creator_display_name: str | None = None
    source: str = "channel"
    animated: bool = False
    usage: EmotePeriodCounts
    top_contributors: list[EmoteContributor] = []


class EmoteWeatherEntry(BaseModel):
    emote_name: str
    emote_id: str
    count_now: int
    count_prev: int
    delta: int
    delta_pct: float | None = None


class EmoteWeatherResponse(BaseModel):
    period: str
    platform: str = "all"
    window_now: str  # "YYYY-MM-DD" or "YYYY-MM-DD..YYYY-MM-DD"
    window_prev: str
    rising: list[EmoteWeatherEntry]
    falling: list[EmoteWeatherEntry]
