"""Subathon timer endpoints."""

from fastapi import APIRouter, Request, Response

from app.rate_limit import limiter
from app.models.schemas.subathon import SubathonTimerResponse
from app.services.subathon_service import get_timer
from .stats_common import add_api_version_headers

router = APIRouter(prefix="/api/v1", tags=["subathon"])


@router.get("/subathon/timer", response_model=SubathonTimerResponse)
@limiter.limit("60/minute")
async def subathon_timer(request: Request, response: Response):
    add_api_version_headers(response)
    return SubathonTimerResponse(**get_timer())
