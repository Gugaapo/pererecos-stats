"""Leaderboard and activity stats endpoints"""

from fastapi import APIRouter, HTTPException, Query, Request
from app.rate_limit import limiter
from app.models.schemas import (
    LeaderboardResponse, RisingStarsResponse, HourLeadersResponse, WritersResponse,
    ActiveChattersResponse, ChatActivityResponse, OverallActivityResponse,
    UniqueChattersResponse, NamedLeaderboardResponse, NamedLeaderboardEntry,
    PererecoesResponse, DuasCarasResponse, RandomMessageResponse,
    FolhinhaCommandsResponse, FolhinhaCommandEntry, SmokeTimeResponse,
    FolhinhaTabResponse, FolhinhaTabEntry, FolhinhaTabAllResponse,
)
from app.models.schemas.leaderboards import FolhinhaOverview
from app.services.stats_service import (
    get_leaderboard, get_rising_stars, get_hour_leaders,
    get_top_writers, get_active_chatters,
    get_chat_activity_today, get_overall_hourly_activity,
    get_unique_chatters_by_hour,
    get_pererecoes_leaderboard, get_duas_caras_leaderboard,
    get_folhinha_commands_cached, get_random_message_with_context,
)
from app.services.stats_aggregates import get_named_daily_leaderboard
from app.services.smoke_service import get_smoke_time_stats
from .stats_common import PLATFORM_PATTERN, PERIOD_PATTERN, DATE_PATTERN, FAMOSINHOS_SOURCE_PATTERN

router = APIRouter(prefix="/api/v1", tags=["stats"])


@router.get("/stats/leaderboard", response_model=LeaderboardResponse)
@limiter.limit("60/minute")
async def leaderboard(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=100),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    return await get_leaderboard(period, limit, platform, start_date, end_date)


@router.get("/stats/rising-stars", response_model=RisingStarsResponse)
@limiter.limit("30/minute")
async def rising_stars(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Users with biggest growth in selected range vs previous equal window."""
    entries = await get_rising_stars(limit, platform, period, start_date, end_date)
    return RisingStarsResponse(entries=entries)


@router.get("/stats/hour-leaders", response_model=HourLeadersResponse)
@limiter.limit("30/minute")
async def hour_leaders(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Who dominates each hour (24 mini-leaderboards)"""
    entries = await get_hour_leaders(platform, period, start_date, end_date)
    return HourLeadersResponse(entries=entries)


@router.get("/stats/top-writers", response_model=WritersResponse)
@limiter.limit("30/minute")
async def top_writers(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Users with longest average message length (min 20 messages)"""
    entries = await get_top_writers(limit, platform, period, start_date, end_date)
    return WritersResponse(entries=entries)


@router.get("/stats/active-chatters", response_model=ActiveChattersResponse)
@limiter.limit("60/minute")
async def active_chatters(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    """Users who sent at least 1 message in the last 5 minutes"""
    chatters, total_users = await get_active_chatters(min_messages=1, minutes=5, platform=platform)
    return ActiveChattersResponse(count=len(chatters), chatters=chatters, total_users=total_users)


@router.get("/stats/chat-activity", response_model=ChatActivityResponse)
@limiter.limit("60/minute")
async def chat_activity(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Chat activity by hour-of-day in the selected period"""
    activity, total, peak_hour, peak_count = await get_chat_activity_today(
        platform, period, start_date, end_date
    )
    return ChatActivityResponse(
        activity=activity,
        total_today=total,
        peak_hour=peak_hour,
        peak_count=peak_count
    )


@router.get("/stats/overall-activity", response_model=OverallActivityResponse)
@limiter.limit("30/minute")
async def overall_activity(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Totals and daily averages by hour-of-day (BRT) for the selected period."""
    (
        activity,
        average_activity,
        total,
        peak_hour,
        peak_count,
        avg_peak_hour,
        avg_peak_count,
        days,
    ) = await get_overall_hourly_activity(platform, period, start_date, end_date)
    return OverallActivityResponse(
        activity=activity,
        average_activity=average_activity,
        total_messages=total,
        peak_hour=peak_hour,
        peak_count=peak_count,
        avg_peak_hour=avg_peak_hour,
        avg_peak_count=avg_peak_count,
        days=days,
    )


@router.get("/stats/unique-chatters", response_model=UniqueChattersResponse)
@limiter.limit("60/minute")
async def unique_chatters(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Unique chatters per hour-of-day in the selected period"""
    activity, total, peak_hour, peak_count = await get_unique_chatters_by_hour(
        platform, period, start_date, end_date
    )
    return UniqueChattersResponse(
        activity=activity,
        total_unique=total,
        peak_hour=peak_hour,
        peak_count=peak_count
    )


@router.get("/stats/famosinhos", response_model=NamedLeaderboardResponse)
@limiter.limit("30/minute")
async def famosinhos(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    source: str = Query("all", pattern=FAMOSINHOS_SOURCE_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    rows = await get_named_daily_leaderboard(
        "famosinhos_daily", period, platform, limit=limit,
        start_date=start_date, end_date=end_date,
        source=source,
    )
    return NamedLeaderboardResponse(
        period=period,
        platform=platform,
        source=source,
        leaderboard=[NamedLeaderboardEntry(**r) for r in rows],
    )


@router.get("/stats/folhinha", response_model=NamedLeaderboardResponse)
@limiter.limit("30/minute")
async def folhinha(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    rows = await get_named_daily_leaderboard(
        "folhinha_daily", period, platform, limit=limit,
        start_date=start_date, end_date=end_date,
    )
    return NamedLeaderboardResponse(
        period=period,
        platform=platform,
        leaderboard=[NamedLeaderboardEntry(**r) for r in rows],
    )


@router.get("/stats/maria-vai-com-as-outras", response_model=NamedLeaderboardResponse)
@limiter.limit("30/minute")
async def maria_vai_com_as_outras(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    rows = await get_named_daily_leaderboard(
        "maria_daily", period, platform, limit=limit,
        start_date=start_date, end_date=end_date,
    )
    return NamedLeaderboardResponse(
        period=period,
        platform=platform,
        leaderboard=[NamedLeaderboardEntry(**r) for r in rows],
    )


@router.get("/stats/escritor-roubado", response_model=NamedLeaderboardResponse)
@limiter.limit("30/minute")
async def escritor_roubado(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    rows = await get_named_daily_leaderboard(
        "escritor_roubado_daily", period, platform, limit=limit,
        start_date=start_date, end_date=end_date,
    )
    return NamedLeaderboardResponse(
        period=period,
        platform=platform,
        leaderboard=[NamedLeaderboardEntry(**r) for r in rows],
    )


@router.get("/stats/folhinha/commands", response_model=FolhinhaCommandsResponse)
@limiter.limit("20/minute")
async def folhinha_commands(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Top Folhinha ?comando tokens in the selected period."""
    rows = await get_folhinha_commands_cached(
        period=period, platform=platform, limit=limit,
        start_date=start_date, end_date=end_date,
    )
    return FolhinhaCommandsResponse(
        period=period,
        platform=platform,
        commands=[FolhinhaCommandEntry(**r) for r in rows],
    )


FOLHINHA_TAB_BOARDS = (
    "bonkadores",
    "sacos-de-pancada",
    "mais-fortes",
    "mais-fracos",
    "mais-carinhos",
    "mais-fofos",
    "desvivedores",
    "sobreviventes",
    "cookie-cd",
    "mais-cookies",
    "slot-ganhos",
    "slot-perdas",
)
FOLHINHA_TAB_BOARD_SET = frozenset(FOLHINHA_TAB_BOARDS)


@router.get("/stats/folhinha/tab", response_model=FolhinhaTabAllResponse)
@limiter.limit("60/minute")
async def folhinha_tab_all(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """All Folhinha-tab leaderboards in one response (boards only — overview is separate)."""
    import asyncio
    from app.services.folhinha.leaderboards import get_folhinha_board

    async def _one(board_id: str):
        rows = await get_folhinha_board(
            board_id,
            period=period,
            platform=platform,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
        return board_id, [FolhinhaTabEntry(**r) for r in rows]

    board_results = await asyncio.gather(*[_one(bid) for bid in FOLHINHA_TAB_BOARDS])
    boards = {board_id: entries for board_id, entries in board_results}
    return FolhinhaTabAllResponse(
        period=period,
        platform=platform,
        boards=boards,
        overview=None,
    )


@router.get("/stats/folhinha/overview", response_model=FolhinhaOverview)
@limiter.limit("60/minute")
async def folhinha_overview(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Folhinha tab overview visuals — loaded after boards so the grid stays fast."""
    from app.services.folhinha.leaderboards import get_folhinha_overview

    overview_raw = await get_folhinha_overview(
        period=period,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
    )
    return FolhinhaOverview(**overview_raw)


@router.get("/stats/folhinha/boards/{board_id}", response_model=FolhinhaTabResponse)
@limiter.limit("120/minute")
async def folhinha_tab_board(
    request: Request,
    board_id: str,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Folhinha tab leaderboards (bonk / abraco / roleta). Prefer /stats/folhinha/tab."""
    if board_id not in FOLHINHA_TAB_BOARD_SET:
        raise HTTPException(status_code=404, detail=f"Unknown Folhinha board: {board_id}")
    from app.services.folhinha.leaderboards import get_folhinha_board

    rows = await get_folhinha_board(
        board_id,
        period=period,
        platform=platform,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )
    return FolhinhaTabResponse(
        board=board_id,
        period=period,
        platform=platform,
        leaderboard=[FolhinhaTabEntry(**r) for r in rows],
    )


@router.get("/stats/pererecoes", response_model=PererecoesResponse)
@limiter.limit("30/minute")
async def pererecoes(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Meta-leaderboard: points earned by top-10 positions across all other boards."""
    return await get_pererecoes_leaderboard(
        period, platform, limit=limit, start_date=start_date, end_date=end_date,
    )


@router.get("/stats/duas-caras", response_model=DuasCarasResponse)
@limiter.limit("30/minute")
async def duas_caras(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=50),
):
    """Who changed login the most (distinct usernames, all-time)."""
    return await get_duas_caras_leaderboard(platform=platform, limit=limit)


@router.get("/stats/random-message", response_model=RandomMessageResponse)
@limiter.limit("20/minute")
async def random_message(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    """Ribbits do passado: random message plus ±20 before/after for context."""
    data = await get_random_message_with_context(platform)
    if not data:
        raise HTTPException(status_code=404, detail="No messages found")
    focus = data["focus"]
    return RandomMessageResponse(
        focus=focus,
        before=data.get("before") or [],
        after=data.get("after") or [],
        username=focus.username,
        display_name=focus.display_name,
        platform=focus.platform,
        message=focus.message,
        timestamp=focus.timestamp,
    )


@router.get("/stats/smoke-time", response_model=SmokeTimeResponse)
@limiter.limit("30/minute")
async def smoke_time(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Maiores Tragadores: SmokeTime ritual at 16:20 BRT"""
    return await get_smoke_time_stats(platform, period, start_date, end_date)
