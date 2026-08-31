from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
import logging
from pathlib import Path

from app.config import get_settings
from app.database import db
from app.bot.twitch_bot import TwitchBot
from app.bot.kick_listener import run_kick_listener
from app.routers.stats import router as stats_router
from app.rate_limit import limiter
from app.services.stats_aggregates import (
    backfill_aggregates,
    merge_legacy_user_totals,
    backfill_known_usernames,
    backfill_smoke_sessions,
    backfill_user_daily_stats,
    backfill_folhinha,
    backfill_famosinhos_heuristic,
    backfill_copycats,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # CSP for API responses
        if request.url.path.startswith("/api/"):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent large payload attacks"""
    def __init__(self, app, max_size: int = 1048576):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        if request.headers.get("content-length"):
            content_length = int(request.headers["content-length"])
            if content_length > self.max_size:
                logger.warning(f"Request too large: {content_length} bytes from {request.client.host}")
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request entity too large"}
                )
        return await call_next(request)


class SecurityLoggingMiddleware(BaseHTTPMiddleware):
    """Log security-relevant events"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Log rate limit violations
        if response.status_code == 429:
            logger.warning(
                f"Rate limit exceeded: {request.client.host} - {request.method} {request.url.path}"
            )

        # Log validation errors (potential attacks)
        if response.status_code == 422:
            logger.warning(
                f"Validation error: {request.client.host} - {request.method} {request.url.path}"
            )

        # Log unauthorized access attempts
        if response.status_code in (401, 403):
            logger.warning(
                f"Unauthorized access: {request.client.host} - {request.method} {request.url.path}"
            )

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    print("Database connected")

    settings = get_settings()
    bot = None
    bot_task = None
    kick_task = None
    eventsub_task = None
    eventsub_stop = asyncio.Event()

    if settings.twitch_oauth_token:
        bot = TwitchBot()
        bot_task = asyncio.create_task(bot.start())
        app.state.bot = bot
        app.state.bot_task = bot_task

        def _bot_task_done(task: asyncio.Task):
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.error("Twitch bot task crashed", exc_info=exc)

        bot_task.add_done_callback(_bot_task_done)
        print("Twitch bot started")

        from app.bot.eventsub_listener import run_eventsub_listener
        eventsub_task = asyncio.create_task(run_eventsub_listener(eventsub_stop))
        app.state.eventsub_task = eventsub_task
        app.state.eventsub_stop = eventsub_stop

        def _eventsub_done(task: asyncio.Task):
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.error("EventSub listener crashed", exc_info=exc)

        eventsub_task.add_done_callback(_eventsub_done)
        print("EventSub channel.ban listener started")
    else:
        app.state.bot_task = None
        app.state.eventsub_task = None
        print("Warning: No Twitch OAuth token configured, bot disabled")

    if settings.kick_enabled:
        kick_task = asyncio.create_task(run_kick_listener())
        app.state.kick_task = kick_task

        def _kick_task_done(task: asyncio.Task):
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.error("Kick listener task crashed", exc_info=exc)

        kick_task.add_done_callback(_kick_task_done)
        print(f"Kick listener started for channel {settings.kick_channel}")
    else:
        app.state.kick_task = None
        print("Kick listener disabled (set KICK_ENABLED=true to enable)")

    async def _run_backfill():
        try:
            await backfill_aggregates()
            await merge_legacy_user_totals()
            await backfill_known_usernames()
            await backfill_smoke_sessions()
            await backfill_user_daily_stats()
            from app.services.emote_service import sync_emote_catalog, backfill_emote_daily_stats
            await sync_emote_catalog()
            await backfill_emote_daily_stats()
            await backfill_folhinha()
            await backfill_famosinhos_heuristic()
            await backfill_copycats()
            from app.services.stats_service import invalidate_rank_cache
            invalidate_rank_cache()
        except Exception as exc:
            logger.error("Aggregate backfill failed", exc_info=exc)

    backfill_task = asyncio.create_task(_run_backfill())
    app.state.backfill_task = backfill_task

    yield

    if backfill_task and not backfill_task.done():
        backfill_task.cancel()
        try:
            await backfill_task
        except asyncio.CancelledError:
            pass

    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Twitch bot cleanup error (non-fatal): %s", exc)

    if eventsub_task:
        eventsub_stop.set()
        eventsub_task.cancel()
        try:
            await eventsub_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("EventSub cleanup error (non-fatal): %s", exc)

    if kick_task:
        kick_task.cancel()
        try:
            await kick_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Kick listener cleanup error (non-fatal): %s", exc)

    await db.disconnect()
    print("Shutdown complete")


settings = get_settings()
app = FastAPI(
    title="Pererecos Stats API",
    description="Chat statistics for omeiaum (Twitch) and meiaum (Kick)",
    version="1.0.0",
    lifespan=lifespan,
    root_path=settings.api_root_path,
    docs_url="/api/docs" if settings.api_root_path == "" else None,
    redoc_url="/api/redoc" if settings.api_root_path == "" else None,
)

# Rate limiting (shared limiter + middleware so @limiter.limit decorators enforce)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security logging middleware (must be first to catch all responses)
if settings.log_security_events:
    app.add_middleware(SecurityLoggingMiddleware)

# Request size limit middleware
app.add_middleware(RequestSizeLimitMiddleware, max_size=settings.max_request_size)

# Security headers middleware
if settings.enable_security_headers:
    app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware — prefer explicit origins in production
cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if not cors_origins:
    cors_origins = ["https://tossemideia.cloud"]
allow_credentials = "*" not in cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if "*" not in cors_origins else ["*"],
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(stats_router)

logger.info("Application started with security features enabled")

frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(str(frontend_path / "index.html"))
