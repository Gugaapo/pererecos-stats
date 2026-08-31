"""User-related stats endpoints"""

from fastapi import APIRouter, HTTPException, Query, Request, Path
from app.rate_limit import limiter
from app.models.schemas import (
    UserStats, UserSearchResult, UserComparisonResponse,
    UserCoreResponse, UserActivityResponse, UserRankingsOnlyResponse,
    UserSocialResponse, UserEmotesResponse, UserRecentResponse,
    UserSmokeOnlyResponse, UsernameHistoryResponse,
    UserFolhinhaOnlyResponse, UserFolhinhaStats,
)
from app.services.stats_service import (
    get_user_stats, search_users, get_user_comparison,
    get_user_core, get_user_activity, get_user_rankings_section,
    get_user_social, get_user_emotes_section, get_user_recent, get_user_smoke_section,
    get_username_history, resolve_username,
)
from app.services.folhinha.user_stats import get_user_folhinha_stats
from .stats_common import USERNAME_PATTERN, PLATFORM_PATTERN, PERIOD_PATTERN, DATE_PATTERN

router = APIRouter(prefix="/api/v1", tags=["stats"])


@router.get("/stats/user/{username}", response_model=UserStats)
@limiter.limit("30/minute")
async def user_stats(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    """Deprecated monolithic endpoint — prefer /core + section endpoints."""
    stats = await get_user_stats(username, period, platform, start_date, end_date)
    if not stats:
        raise HTTPException(
            status_code=404,
            detail="User not found, ambiguous across platforms, or no messages in period",
        )
    return stats


@router.get("/stats/user/{username}/core", response_model=UserCoreResponse)
@limiter.limit("60/minute")
async def user_core(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    """Fast core stats for progressive loading (name, totals, hourly chart)."""
    stats = await get_user_core(username, period, platform, start_date, end_date)
    if not stats:
        raise HTTPException(
            status_code=404,
            detail="User not found, ambiguous across platforms, or no messages in period",
        )
    return stats


@router.get("/stats/user/{username}/activity", response_model=UserActivityResponse)
@limiter.limit("30/minute")
async def user_activity(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    stats = await get_user_activity(username, period, platform, start_date, end_date)
    if not stats:
        raise HTTPException(status_code=404, detail="User not found or no messages in period")
    return stats


@router.get("/stats/user/{username}/rankings", response_model=UserRankingsOnlyResponse)
@limiter.limit("30/minute")
async def user_rankings(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    stats = await get_user_rankings_section(username, period, platform, start_date, end_date)
    if not stats:
        raise HTTPException(status_code=404, detail="User not found")
    return stats


@router.get("/stats/user/{username}/social", response_model=UserSocialResponse)
@limiter.limit("20/minute")
async def user_social(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    stats = await get_user_social(username, period, platform, start_date, end_date)
    if not stats:
        raise HTTPException(status_code=404, detail="User not found")
    return stats


@router.get("/stats/user/{username}/emotes", response_model=UserEmotesResponse)
@limiter.limit("30/minute")
async def user_emotes(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    stats = await get_user_emotes_section(username, period, platform, start_date, end_date)
    if not stats:
        raise HTTPException(status_code=404, detail="User not found")
    return stats


@router.get("/stats/user/{username}/recent", response_model=UserRecentResponse)
@limiter.limit("60/minute")
async def user_recent(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    stats = await get_user_recent(username, platform)
    if not stats:
        raise HTTPException(status_code=404, detail="User not found")
    return stats


@router.get("/stats/user/{username}/smoke", response_model=UserSmokeOnlyResponse)
@limiter.limit("30/minute")
async def user_smoke(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    stats = await get_user_smoke_section(username, platform)
    if not stats:
        raise HTTPException(status_code=404, detail="User not found")
    return stats


@router.get("/stats/user/{username}/folhinha", response_model=UserFolhinhaOnlyResponse)
@limiter.limit("30/minute")
async def user_folhinha(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
):
    """Per-user Folhinha interactions (bonk, abraco, roleta, cookies)."""
    raw = await get_user_folhinha_stats(
        username,
        period=period,
        platform=platform,
        start_date=start_date,
        end_date=end_date,
    )
    if raw is None:
        return UserFolhinhaOnlyResponse(folhinha_stats=None)
    return UserFolhinhaOnlyResponse(folhinha_stats=UserFolhinhaStats(**raw))


@router.get("/stats/user/{username}/username-history", response_model=UsernameHistoryResponse)
@limiter.limit("30/minute")
async def username_history(
    request: Request,
    username: str = Path(..., pattern=USERNAME_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    """Get all past usernames for a user"""
    result = await get_username_history(username, platform)
    if not result:
        raise HTTPException(status_code=404, detail="User not found or no user ID tracked")
    return result


@router.get("/stats/search", response_model=list[UserSearchResult])
@limiter.limit("60/minute")
async def user_search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=25),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    """Search users by username prefix"""
    return await search_users(q, limit=10, platform=platform)


@router.get("/stats/compare/{user1}/{user2}", response_model=UserComparisonResponse)
@limiter.limit("20/minute")
async def compare_users(
    request: Request,
    user1: str = Path(..., pattern=USERNAME_PATTERN),
    user2: str = Path(..., pattern=USERNAME_PATTERN),
    period: str = Query("all", pattern=PERIOD_PATTERN),
    start_date: str | None = Query(None, pattern=DATE_PATTERN),
    end_date: str | None = Query(None, pattern=DATE_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    """Side-by-side comparison between two users"""
    resolved1 = await resolve_username(user1, platform)
    resolved2 = await resolve_username(user2, platform)
    if not resolved1:
        raise HTTPException(
            status_code=404,
            detail=f"Usuário '{user1}' não encontrado (use o login, não o display name)",
        )
    if not resolved2:
        raise HTTPException(
            status_code=404,
            detail=f"Usuário '{user2}' não encontrado (use o login, não o display name)",
        )

    stats1, stats2 = await get_user_comparison(
        resolved1, resolved2, period, platform, start_date, end_date
    )
    if not stats1:
        raise HTTPException(
            status_code=404,
            detail=f"Usuário '{resolved1}' sem mensagens no período selecionado",
        )
    if not stats2:
        raise HTTPException(
            status_code=404,
            detail=f"Usuário '{resolved2}' sem mensagens no período selecionado",
        )
    return UserComparisonResponse(user1=stats1, user2=stats2)
