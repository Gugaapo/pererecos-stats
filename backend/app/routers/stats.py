"""
Stats router aggregator — includes all sub-routers.

This module maintains backward compatibility by providing a single
`router` export that aggregates all stats endpoints from:
  - stats_users.py (user profiles, search, compare)
  - stats_leaderboards.py (leaderboards, activity, smoke-time)
  - stats_emotes.py (emote stats and positions)
  - stats_misc.py (health, feedback, export)
"""

from fastapi import APIRouter
from . import stats_users, stats_leaderboards, stats_emotes, stats_misc

# Create main router
router = APIRouter()

# Include all sub-routers
router.include_router(stats_users.router, tags=["stats"])
router.include_router(stats_leaderboards.router, tags=["stats"])
router.include_router(stats_emotes.router, tags=["stats"])
router.include_router(stats_misc.router, tags=["stats"])
