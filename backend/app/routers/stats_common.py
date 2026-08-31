"""Shared patterns, constants, and utilities for stats routers"""

from fastapi import Response

# Username: 2-25 chars, alphanumeric and underscore
USERNAME_PATTERN = r"^[a-zA-Z0-9_]{2,25}$"
PLATFORM_PATTERN = "^(all|twitch|kick)$"
PERIOD_PATTERN = "^(day|week|month|all|custom)$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
FAMOSINHOS_SOURCE_PATTERN = "^(all|reply|heuristic)$"

# API Version
API_VERSION = "1.0.0"


def add_api_version_headers(response: Response) -> None:
    """Add API versioning headers to response"""
    response.headers["X-API-Version"] = API_VERSION
    response.headers["X-API-Deprecation"] = "false"
