from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    message_count: int


class LeaderboardResponse(BaseModel):
    period: str
    platform: str = "all"
    total_users: int
    total_messages: int
    leaderboard: list[LeaderboardEntry]


class RisingStarEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    current_count: int
    previous_count: int
    growth_percent: float


class RisingStarsResponse(BaseModel):
    entries: list[RisingStarEntry]


class HourLeaderEntry(BaseModel):
    hour: int
    username: str
    display_name: str
    platform: str = "twitch"
    message_count: int


class HourLeadersResponse(BaseModel):
    entries: list[HourLeaderEntry]


class WriterEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    avg_length: float
    message_count: int
    score: float


class WritersResponse(BaseModel):
    entries: list[WriterEntry]


class DuasCarasEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    name_count: int
    known_usernames: list[str] = []


class DuasCarasResponse(BaseModel):
    platform: str = "all"
    leaderboard: list[DuasCarasEntry]


class ActiveChatter(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    message_count: int
    rank: int | None = None  # Overall leaderboard position


class ActiveChattersResponse(BaseModel):
    count: int
    chatters: list[ActiveChatter]
    total_users: int  # Total users in leaderboard for percentage calculations


class ChatActivityPoint(BaseModel):
    hour: int
    count: int


class ChatActivityResponse(BaseModel):
    activity: list[ChatActivityPoint]
    total_today: int
    peak_hour: int
    peak_count: int


class OverallActivityResponse(BaseModel):
    activity: list[ChatActivityPoint]  # all-time totals per hour-of-day
    average_activity: list[ChatActivityPoint] = []  # mean msgs per day at that hour (rounded)
    total_messages: int
    peak_hour: int
    peak_count: int
    avg_peak_hour: int = 0
    avg_peak_count: float = 0.0
    days: int = 1


class UniqueChattersResponse(BaseModel):
    activity: list[ChatActivityPoint]
    total_unique: int
    peak_hour: int
    peak_count: int


class NamedLeaderboardEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    count: int


class NamedLeaderboardResponse(BaseModel):
    period: str
    platform: str = "all"
    leaderboard: list[NamedLeaderboardEntry]
    source: str = "all"


class PererecoesBreakdown(BaseModel):
    board: str  # human-readable board name
    position: int  # 1-10 position on that board
    points: int


class PererecoesEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    points: int
    breakdown: list[PererecoesBreakdown] = []


class PererecoesResponse(BaseModel):
    period: str
    platform: str = "all"
    leaderboard: list[PererecoesEntry]


class FolhinhaCommandEntry(BaseModel):
    rank: int
    command: str
    count: int


class FolhinhaCommandsResponse(BaseModel):
    period: str
    platform: str = "all"
    commands: list[FolhinhaCommandEntry]


class FolhinhaTabEntry(BaseModel):
    rank: int
    username: str
    display_name: str
    platform: str = "twitch"
    count: int = 0
    avg_percentage: float | None = None
    value: float | int = 0
    value_label: str = "vezes"


class FolhinhaTabResponse(BaseModel):
    board: str
    period: str
    platform: str = "all"
    leaderboard: list[FolhinhaTabEntry]


class FolhinhaOverviewTotals(BaseModel):
    bonks: int = 0
    abracos: int = 0
    slots: int = 0
    cookie_cd: int = 0
    roulette: int = 0
    roulette_survive: int = 0
    roulette_death: int = 0


class FolhinhaHistBucket(BaseModel):
    bucket: str
    label: str
    count: int = 0


class FolhinhaTopBonkPair(BaseModel):
    """Undirected duel: count = actor→target + target→actor."""
    actor_username: str
    actor_display_name: str
    target_username: str
    target_display_name: str
    count: int
    actor_count: int = 0  # bonks actor → target
    target_count: int = 0  # bonks target → actor
    platform: str = "twitch"


class FolhinhaSlotTotals(BaseModel):
    won: int = 0
    lost: int = 0


class FolhinhaCookieTopEntry(BaseModel):
    username: str
    display_name: str
    platform: str = "twitch"
    count: int = 0


class FolhinhaOverview(BaseModel):
    totals: FolhinhaOverviewTotals
    bonk_pct_histogram: list[FolhinhaHistBucket] = []
    top_bonk_pair: FolhinhaTopBonkPair | None = None
    slot_totals: FolhinhaSlotTotals = FolhinhaSlotTotals()
    cookie_top: list[FolhinhaCookieTopEntry] = []


class FolhinhaTabAllResponse(BaseModel):
    period: str
    platform: str = "all"
    boards: dict[str, list[FolhinhaTabEntry]]
    overview: FolhinhaOverview | None = None
