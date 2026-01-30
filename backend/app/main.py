from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
import logging
from pathlib import Path

from app.config import get_settings
from app.database import db
from app.bot.twitch_bot import TwitchBot
from app.routers.stats import router as stats_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


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

    if settings.twitch_oauth_token:
        bot = TwitchBot()
        bot_task = asyncio.create_task(bot.start())
        app.state.bot = bot
        print("Twitch bot started")
    else:
        print("Warning: No Twitch OAuth token configured, bot disabled")

    yield

    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass

    await db.disconnect()
    print("Shutdown complete")


settings = get_settings()
app = FastAPI(
    title="Pererecos Stats API",
    description="Twitch chat statistics for omeiaum channel",
    version="1.0.0",
    lifespan=lifespan,
    root_path=settings.api_root_path,
    docs_url="/api/docs" if settings.api_root_path == "" else None,
    redoc_url="/api/redoc" if settings.api_root_path == "" else None,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security logging middleware (must be first to catch all responses)
if settings.log_security_events:
    app.add_middleware(SecurityLoggingMiddleware)

# Request size limit middleware
app.add_middleware(RequestSizeLimitMiddleware, max_size=settings.max_request_size)

# Security headers middleware
if settings.enable_security_headers:
    app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware
cors_origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
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
