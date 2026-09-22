"""User compare — domain module (implementation peeled toward users/)."""

from app.services.stats_service import (  # noqa: F401
    get_compare_snapshot,
    get_user_comparison,
)

__all__ = ["get_user_comparison", "get_compare_snapshot"]
