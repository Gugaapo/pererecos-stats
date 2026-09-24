"""Subathon timer endpoints.

These are /subathon/*, not /stats/*, so they are platform-agnostic by design
and must not take a platform query param.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, Request, Response

from app.config import get_settings
from app.rate_limit import limiter
from app.models.schemas.subathon import (
    SubathonDiagnosticsResponse,
    SubathonOverviewResponse,
    SubathonTimerResponse,
)
from app.services.subathon_marathon import handle_webhook_event
from app.services.subathon_service import get_timer
from app.services.subathon_insights_service import (
    build_chat_sync_cached,
    build_insights_cached,
)
from app.services.subathon_stats import (
    contributions,
    daily_series,
    diagnostics,
    hourly_profile,
    overview,
    recent_increases,
    rules_snapshot,
)
from app.services.timer_attribution import attribution_stats, twitch_event_counters
from app.services.subathon_webhook import SignatureError, verify
from .stats_common import PLATFORM_PATTERN, add_api_version_headers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["subathon"])


@router.get("/subathon/timer", response_model=SubathonTimerResponse)
@limiter.limit("60/minute")
async def subathon_timer(request: Request, response: Response):
    add_api_version_headers(response)
    return SubathonTimerResponse(**(await get_timer()))


@router.get("/subathon/insights", response_model=None)
async def subathon_insights(request: Request, response: Response):
    """Timer-tab insight cards. Platform-agnostic — use plain fetch, not apiUrl()."""
    add_api_version_headers(response)
    return await build_insights_cached()


@router.get("/subathon/chat-sync", response_model=None)
async def subathon_chat_sync(
    request: Request,
    response: Response,
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    """Panic + reactive-emote analytics. Platform-agnostic default; optional filter."""
    add_api_version_headers(response)
    return await build_chat_sync_cached(platform)


@router.get("/subathon/overview", response_model=SubathonOverviewResponse)
@limiter.limit("60/minute")
async def subathon_overview(request: Request, response: Response):
    add_api_version_headers(response)
    return SubathonOverviewResponse(**(await overview()))


@router.get("/subathon/daily")
@limiter.limit("60/minute")
async def subathon_daily(
    request: Request,
    response: Response,
    days: int = Query(30, ge=1, le=400),
):
    add_api_version_headers(response)
    return await daily_series(days)


@router.get("/subathon/hourly")
@limiter.limit("60/minute")
async def subathon_hourly(request: Request, response: Response):
    add_api_version_headers(response)
    return await hourly_profile()


@router.get("/subathon/increases")
@limiter.limit("60/minute")
async def subathon_increases(
    request: Request,
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    add_api_version_headers(response)
    return await recent_increases(limit, offset)


@router.get("/subathon/contributions")
@limiter.limit("60/minute")
async def subathon_contributions(request: Request, response: Response):
    add_api_version_headers(response)
    return await contributions()


@router.get("/subathon/rules")
@limiter.limit("60/minute")
async def subathon_rules(request: Request, response: Response):
    add_api_version_headers(response)
    return await rules_snapshot()


@router.get("/subathon/twitch-events")
@limiter.limit("60/minute")
async def subathon_twitch_events(
    request: Request,
    response: Response,
    hours: int = Query(24, ge=1, le=168),
):
    """SSE Twitch event counters (subs/gifts/bits) over the last N hours."""
    add_api_version_headers(response)
    return await twitch_event_counters(hours)


@router.get("/subathon/attribution-stats")
@limiter.limit("60/minute")
async def subathon_attribution_stats(
    request: Request,
    response: Response,
    hours: int = Query(24, ge=0, le=8760),
):
    """Timer seconds by origin (subs/bits/pix/other). hours=0 means since genesis."""
    add_api_version_headers(response)
    return await attribution_stats(hours=hours)


@router.get("/subathon/diagnostics", response_model=SubathonDiagnosticsResponse)
@limiter.limit("60/minute")
async def subathon_diagnostics(request: Request, response: Response):
    add_api_version_headers(response)
    return SubathonDiagnosticsResponse(**(await diagnostics()))


@router.post("/subathon/webhook/pixie", status_code=204)
async def pixie_webhook(request: Request, response: Response):
    """Receive transaction.confirmed. 204 accepted, 400 invalid signature.

    Deliberately NOT rate-limited by slowapi: Pixie verification and retries
    must not be throttled. Idempotent on webhook-id.
    """
    raw = await request.body()
    settings = get_settings()
    try:
        verify(
            secret=settings.pixie_webhook_secret,
            webhook_id=request.headers.get("webhook-id"),
            webhook_timestamp=request.headers.get("webhook-timestamp"),
            webhook_signature=request.headers.get("webhook-signature"),
            body=raw,
            tolerance_seconds=settings.pixie_webhook_tolerance_seconds,
        )
    except SignatureError as exc:
        logger.warning("Rejected Pixie webhook: %s", exc)
        return Response(status_code=400)

    webhook_id = request.headers["webhook-id"]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return Response(status_code=400)

    await handle_webhook_event(webhook_id, payload)
    return Response(status_code=204)
