from fastapi import APIRouter, HTTPException, Query, Request, Path, Header, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Annotated
from app.models.schemas import (
    UserStats, LeaderboardResponse, HealthResponse,
    RisingStarsResponse, HourLeadersResponse, WritersResponse,
    ActiveChattersResponse, UserComparisonResponse, UserSearchResult,
    ChatActivityResponse, OverallActivityResponse, TopEmotesResponse,
    UniqueChattersResponse
)
from app.services.stats_service import (
    get_user_stats, get_leaderboard, get_rising_stars, get_hour_leaders,
    get_top_writers, get_active_chatters, get_user_comparison, search_users,
    get_chat_activity_today, get_overall_hourly_activity, get_chat_top_emotes,
    get_unique_chatters_by_hour
)
from app.database import db
from app.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["stats"])
limiter = Limiter(key_func=get_remote_address)

# Twitch username: 4-25 chars, alphanumeric and underscore, cannot start with underscore
TWITCH_USERNAME_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_]{3,24}$"

# API Version
API_VERSION = "1.0.0"


def add_api_version_headers(response: Response) -> None:
    """Add API versioning headers to response"""
    response.headers["X-API-Version"] = API_VERSION
    response.headers["X-API-Deprecation"] = "false"


@router.get("/stats/user/{username}", response_model=UserStats)
@limiter.limit("30/minute")
async def user_stats(
    request: Request,
    username: str = Path(..., pattern=TWITCH_USERNAME_PATTERN),
    period: str = Query("all", pattern="^(day|week|month|all)$")
):
    stats = await get_user_stats(username, period)
    if not stats:
        raise HTTPException(status_code=404, detail="User not found or no messages in period")
    return stats


@router.get("/stats/leaderboard", response_model=LeaderboardResponse)
@limiter.limit("60/minute")
async def leaderboard(
    request: Request,
    period: str = Query("all", pattern="^(day|week|month|all)$"),
    limit: int = Query(10, ge=1, le=100)
):
    return await get_leaderboard(period, limit)


@router.get("/health", response_model=HealthResponse)
@limiter.limit("120/minute")
async def health_check(
    request: Request,
    response: Response,
    x_health_token: Annotated[str | None, Header()] = None
):
    """
    Health check endpoint. Optionally protected by HEALTH_CHECK_TOKEN env var.
    If token is set, requires X-Health-Token header to access detailed info.
    """
    settings = get_settings()
    add_api_version_headers(response)

    # If health check token is configured, validate it
    if settings.health_check_token:
        if x_health_token != settings.health_check_token:
            # Return minimal info for unauthorized requests
            return HealthResponse(
                status="ok",
                bot_connected=True,
                database_connected=True
            )

    try:
        await db.client.admin.command("ping")
        db_connected = True
    except Exception:
        db_connected = False

    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        bot_connected=True,
        database_connected=db_connected
    )


@router.get("/stats/rising-stars", response_model=RisingStarsResponse)
@limiter.limit("30/minute")
async def rising_stars(request: Request, limit: int = Query(10, ge=1, le=50)):
    """Users with biggest message increase (last 7 days vs previous 7 days)"""
    entries = await get_rising_stars(limit)
    return RisingStarsResponse(entries=entries)


@router.get("/stats/hour-leaders", response_model=HourLeadersResponse)
@limiter.limit("30/minute")
async def hour_leaders(request: Request):
    """Who dominates each hour (24 mini-leaderboards)"""
    entries = await get_hour_leaders()
    return HourLeadersResponse(entries=entries)


@router.get("/stats/top-writers", response_model=WritersResponse)
@limiter.limit("30/minute")
async def top_writers(request: Request, limit: int = Query(10, ge=1, le=50)):
    """Users with longest average message length (min 10 messages)"""
    entries = await get_top_writers(limit)
    return WritersResponse(entries=entries)


@router.get("/stats/active-chatters", response_model=ActiveChattersResponse)
@limiter.limit("60/minute")
async def active_chatters(request: Request):
    """Users who sent at least 1 message in the last 5 minutes"""
    chatters, total_users = await get_active_chatters(min_messages=1, minutes=5)
    return ActiveChattersResponse(count=len(chatters), chatters=chatters, total_users=total_users)


@router.get("/stats/chat-activity", response_model=ChatActivityResponse)
@limiter.limit("60/minute")
async def chat_activity(request: Request):
    """Chat activity by hour for today"""
    activity, total, peak_hour, peak_count = await get_chat_activity_today()
    return ChatActivityResponse(
        activity=activity,
        total_today=total,
        peak_hour=peak_hour,
        peak_count=peak_count
    )


@router.get("/stats/overall-activity", response_model=OverallActivityResponse)
@limiter.limit("30/minute")
async def overall_activity(request: Request):
    """Overall chat activity by hour (all time)"""
    activity, total, peak_hour, peak_count = await get_overall_hourly_activity()
    return OverallActivityResponse(
        activity=activity,
        total_messages=total,
        peak_hour=peak_hour,
        peak_count=peak_count
    )


@router.get("/stats/unique-chatters", response_model=UniqueChattersResponse)
@limiter.limit("60/minute")
async def unique_chatters(request: Request):
    """Unique chatters per hour for the last 24 hours"""
    activity, total, peak_hour, peak_count = await get_unique_chatters_by_hour()
    return UniqueChattersResponse(
        activity=activity,
        total_unique=total,
        peak_hour=peak_hour,
        peak_count=peak_count
    )


@router.get("/stats/search", response_model=list[UserSearchResult])
@limiter.limit("60/minute")
async def user_search(request: Request, q: str = Query(..., min_length=2, max_length=25)):
    """Search users by username prefix"""
    return await search_users(q, limit=10)


@router.get("/stats/top-emotes", response_model=TopEmotesResponse)
@limiter.limit("30/minute")
async def top_emotes(request: Request):
    """Top 10 most used emotes in the last 30 days"""
    emotes, total = await get_chat_top_emotes(limit=10)
    return TopEmotesResponse(emotes=emotes, total_emote_uses=total)


@router.get("/stats/compare/{user1}/{user2}", response_model=UserComparisonResponse)
@limiter.limit("20/minute")
async def compare_users(
    request: Request,
    user1: str = Path(..., pattern=TWITCH_USERNAME_PATTERN),
    user2: str = Path(..., pattern=TWITCH_USERNAME_PATTERN),
    period: str = Query("all", pattern="^(day|week|month|all)$")
):
    """Side-by-side comparison between two users"""
    stats1, stats2 = await get_user_comparison(user1, user2, period)
    if not stats1:
        raise HTTPException(status_code=404, detail=f"User '{user1}' not found or no messages in period")
    if not stats2:
        raise HTTPException(status_code=404, detail=f"User '{user2}' not found or no messages in period")
    return UserComparisonResponse(user1=stats1, user2=stats2)
