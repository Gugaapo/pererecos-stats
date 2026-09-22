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
from app.services.subathon_stats import (
    contributions,
    daily_series,
    diagnostics,
    hourly_profile,
    overview,
    recent_increases,
    rules_snapshot,
)
from app.services.subathon_webhook import SignatureError, verify
from .stats_common import add_api_version_headers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["subathon"])


@router.get("/subathon/timer", response_model=SubathonTimerResponse)
@limiter.limit("60/minute")
async def subathon_timer(request: Request, response: Response):
    add_api_version_headers(response)
    return SubathonTimerResponse(**(await get_timer()))


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
