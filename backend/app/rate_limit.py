"""Shared SlowAPI rate limiter (single instance for app + routers)."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def client_ip(request: Request) -> str:
    """Prefer Cloudflare / proxy real IP over the nginx loopback address."""
    cf = (request.headers.get("CF-Connecting-IP") or "").strip()
    if cf:
        return cf
    real = (request.headers.get("X-Real-IP") or "").strip()
    if real:
        return real
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)
