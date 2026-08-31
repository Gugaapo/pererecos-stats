"""Emote-related stats endpoints"""

from fastapi import APIRouter, HTTPException, Query, Request, Path
from app.rate_limit import limiter
from app.models.schemas import (
    TopEmotesResponse, EmoteSearchResult, EmoteLeastUsedResponse,
    EmoteCreatorsResponse, EmoteDiversidadeResponse, EmoteDetailResponse,
    EmoteRankingResponse, EmoteWeatherResponse,
    EmotePositionResponse, EmotePositionData, EmotePositionUsersResponse,
)
from app.services.stats_service import (
    get_chat_top_emotes, get_chat_emote_positions, get_emote_position_users,
)
from app.services.emote_service import (
    search_emotes, get_least_used_emotes, get_emote_creators,
    get_diversidade, get_emote_detail, get_emote_ranking, get_emote_weather,
)
from .stats_common import PLATFORM_PATTERN, PERIOD_PATTERN, DATE_PATTERN

router = APIRouter(prefix="/api/v1", tags=["stats"])


@router.get("/stats/top-emotes", response_model=TopEmotesResponse)
@limiter.limit("30/minute")
async def top_emotes(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Top 10 most used emotes in the selected period"""
    emotes, total = await get_chat_top_emotes(
        limit=10, platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )
    return TopEmotesResponse(emotes=emotes, total_emote_uses=total)


@router.get("/stats/emotes/search", response_model=list[EmoteSearchResult])
@limiter.limit("60/minute")
async def emotes_search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=50),
):
    """Autocomplete emotes from channel + global catalog"""
    return await search_emotes(q, limit=10)


@router.get("/stats/emotes/ranking", response_model=EmoteRankingResponse)
@limiter.limit("30/minute")
async def emotes_ranking(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Full catalog ranked by usage in the selected period"""
    return await get_emote_ranking(
        platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )


@router.get("/stats/emotes/weather", response_model=EmoteWeatherResponse)
@limiter.limit("30/minute")
async def emotes_weather(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Rising/falling emotes vs previous equal window (or last complete BRT day)."""
    return await get_emote_weather(
        platform=platform, period=period,
        start_date=start_date, end_date=end_date,
        limit=limit,
    )


@router.get("/stats/emotes/least-used", response_model=EmoteLeastUsedResponse)
@limiter.limit("30/minute")
async def emotes_least_used(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    return await get_least_used_emotes(
        platform=platform, limit=10, period=period,
        start_date=start_date, end_date=end_date,
    )


@router.get("/stats/emotes/creators", response_model=EmoteCreatorsResponse)
@limiter.limit("30/minute")
async def emotes_creators(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    return await get_emote_creators(
        platform=platform, limit=limit, period=period,
        start_date=start_date, end_date=end_date,
    )


@router.get("/stats/emotes/diversidade", response_model=EmoteDiversidadeResponse)
@limiter.limit("30/minute")
async def emotes_diversidade(
    request: Request,
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    limit: int = Query(10, ge=1, le=50),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    return await get_diversidade(
        period=period, platform=platform, limit=limit,
        start_date=start_date, end_date=end_date,
    )


@router.get("/stats/emote/{emote_name}", response_model=EmoteDetailResponse)
@limiter.limit("30/minute")
async def emote_detail(
    request: Request,
    emote_name: str = Path(..., min_length=1, max_length=80),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    detail = await get_emote_detail(
        emote_name, platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )
    if not detail:
        raise HTTPException(status_code=404, detail="Emote not found")
    return detail


@router.get("/stats/emote-positions", response_model=EmotePositionResponse)
@limiter.limit("30/minute")
async def emote_positions(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Global emote position distribution (começo/meio/fim) for the selected period"""
    positions = await get_chat_emote_positions(
        platform, period, start_date, end_date
    )
    if not positions:
        return EmotePositionResponse(positions=EmotePositionData(
            comeco=0, meio=0, fim=0,
            comeco_pct=0, meio_pct=0, fim_pct=0,
            total=0
        ))
    return EmotePositionResponse(positions=positions)


@router.get("/stats/emote-position-users", response_model=EmotePositionUsersResponse)
@limiter.limit("10/minute")
async def emote_position_users(
    request: Request,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Top users classified by emote position (esquerdista/centrão/direitista)"""
    result = await get_emote_position_users(
        limit=100, platform=platform, period=period,
        start_date=start_date, end_date=end_date,
    )
    return EmotePositionUsersResponse(**result)
