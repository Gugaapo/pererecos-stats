"""User profile section loaders — re-exported from stats_service for domain layout."""

# Implementations remain in stats_service for now; this module documents the domain
# boundary and provides a stable import path for routers/callers.

from app.services.stats_service import (  # noqa: F401
    get_user_activity,
    get_user_core,
    get_user_emotes_section,
    get_user_rankings,
    get_user_rankings_section,
    get_user_recent,
    get_user_smoke_section,
    get_user_social,
    get_user_stats,
    get_username_history,
)
