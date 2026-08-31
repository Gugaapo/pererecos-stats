"""Miscellaneous endpoints: health, feedback, export"""

from fastapi import APIRouter, Query, Request, Header, Response
from fastapi.responses import StreamingResponse
from slowapi.util import get_remote_address
from typing import Annotated
from datetime import datetime, timezone
from app.rate_limit import limiter
from app.models.schemas import HealthResponse, FeedbackRequest, FeedbackResponse
from app.services.export_service import validate_export_range, iter_messages_csv
from app.database import db
from app.config import get_settings
from .stats_common import PLATFORM_PATTERN, DATE_PATTERN, add_api_version_headers

router = APIRouter(prefix="/api/v1", tags=["stats"])


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

    # Determine real bot status from the bot task
    bot_task = getattr(request.app.state, "bot_task", None)
    if bot_task is None:
        bot_connected = False
    else:
        bot_connected = not bot_task.done()

    kick_task = getattr(request.app.state, "kick_task", None)
    if kick_task is None:
        kick_connected = False
    else:
        kick_connected = not kick_task.done()

    if settings.health_check_token:
        if x_health_token != settings.health_check_token:
            return HealthResponse(
                status="ok",
                bot_connected=bot_connected,
                kick_connected=kick_connected,
                database_connected=True
            )

    try:
        await db.client.admin.command("ping")
        db_connected = True
    except Exception:
        db_connected = False

    bots_ok = bot_connected or kick_connected or (
        not settings.twitch_oauth_token and not settings.kick_enabled
    )
    all_healthy = db_connected and bots_ok
    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        bot_connected=bot_connected,
        kick_connected=kick_connected,
        database_connected=db_connected
    )


@router.post("/feedback", response_model=FeedbackResponse)
@limiter.limit("5/minute")
async def submit_feedback(request: Request, feedback: FeedbackRequest):
    """Submit bug report or suggestion"""
    doc = {
        "type": feedback.type,
        "message": feedback.message,
        "timestamp": datetime.now(timezone.utc),
        "status": "pending",  # pending, reviewed, resolved
        "ip": get_remote_address(request)
    }

    result = await db.feedback.insert_one(doc)
    return FeedbackResponse(success=True, id=str(result.inserted_id))


@router.get("/export/messages")
@limiter.limit("5/hour")
async def export_messages(
    request: Request,
    start_date: str = Query(..., pattern=DATE_PATTERN),
    end_date: str = Query(..., pattern=DATE_PATTERN),
    platform: str = Query("all", pattern=PLATFORM_PATTERN),
):
    """Download raw chat messages as CSV (time, platform, user, message)."""
    start, end = validate_export_range(start_date, end_date)
    filename = f"pererecos-chat_{start}_{end}.csv"
    return StreamingResponse(
        iter_messages_csv(start, end, platform),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
