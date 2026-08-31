"""BRT period helpers shared by services and aggregates."""

from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))


def period_date_range_brt(period: str) -> tuple[str, str] | None:
    """Return (start_date, end_date) inclusive YYYY-MM-DD in BRT for day/week/month."""
    today = datetime.now(BRT).date()
    if period == "day":
        start = today - timedelta(days=1)
    elif period == "week":
        start = today - timedelta(days=7)
    elif period == "month":
        start = today - timedelta(days=30)
    elif period == "custom":
        return None
    else:
        return None
    return start.isoformat(), today.isoformat()


def resolve_period_dates(
    period: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[str, str] | None:
    """Inclusive BRT YYYY-MM-DD range, or None for all-time.

    Explicit start_date+end_date win over period presets.
    """
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
            end = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
        if start > end:
            start, end = end, start
        return start.isoformat(), end.isoformat()

    return period_date_range_brt(period)


def date_range_to_utc_bounds(start_ymd: str, end_ymd: str) -> tuple[datetime, datetime]:
    """Convert inclusive BRT calendar dates to UTC [start, end) datetimes."""
    start = datetime.strptime(start_ymd[:10], "%Y-%m-%d").replace(tzinfo=BRT)
    end_day = datetime.strptime(end_ymd[:10], "%Y-%m-%d").replace(tzinfo=BRT)
    end = end_day + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def previous_equal_window(start_ymd: str, end_ymd: str) -> tuple[str, str]:
    """Window of the same length immediately before start_ymd."""
    start = datetime.strptime(start_ymd[:10], "%Y-%m-%d").date()
    end = datetime.strptime(end_ymd[:10], "%Y-%m-%d").date()
    length = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)
    return prev_start.isoformat(), prev_end.isoformat()
