"""Stream chat message exports as CSV."""

import csv
import io
from datetime import date, datetime, timezone

from fastapi import HTTPException

from app.database import db
from app.services.stats_aggregates import BOT_FILTER, BRT, date_range_to_utc_bounds
from app.services.stats_service import get_platform_filter, merge_queries

COLLECTION_START = date(2026, 9, 1)
CSV_BATCH_FLUSH = 256
MAX_EXPORT_DAYS = 365


def validate_export_range(start_date: str, end_date: str) -> tuple[str, str]:
    """Validate inclusive BRT date range for public export."""
    try:
        start = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
        end = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format (use YYYY-MM-DD)") from exc

    if start < COLLECTION_START:
        raise HTTPException(
            status_code=400,
            detail=f"start_date must be on or after {COLLECTION_START.isoformat()}",
        )

    today = datetime.now(BRT).date()
    if end > today:
        end = today
    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date")

    span_days = (end - start).days + 1
    if span_days > MAX_EXPORT_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Export range cannot exceed {MAX_EXPORT_DAYS} days (requested {span_days})",
        )

    return start.isoformat(), end.isoformat()


async def iter_messages_csv(
    start_date: str,
    end_date: str,
    platform: str = "all",
):
    """Async generator yielding UTF-8 CSV chunks (time, platform, user, message)."""
    start_utc, end_utc = date_range_to_utc_bounds(start_date, end_date)
    match = merge_queries(
        BOT_FILTER,
        get_platform_filter(platform),
        {"timestamp": {"$gte": start_utc, "$lt": end_utc}},
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["time", "platform", "user", "message", "removed"])
    yield "\ufeff".encode("utf-8") + buf.getvalue().encode("utf-8")
    buf.seek(0)
    buf.truncate(0)

    rows_in_buf = 0
    projection = {
        "timestamp": 1, "platform": 1, "username": 1, "message": 1, "removed": 1, "_id": 0,
    }
    cursor = db.messages.find(match, projection).sort("timestamp", 1).batch_size(2000)

    async for doc in cursor:
        ts = doc.get("timestamp")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts_str = ts.astimezone(BRT).strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_str = ""

        writer.writerow([
            ts_str,
            doc.get("platform") or "twitch",
            doc.get("username") or "",
            doc.get("message") or "",
            "true" if doc.get("removed") else "false",
        ])
        rows_in_buf += 1

        if rows_in_buf >= CSV_BATCH_FLUSH:
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)
            rows_in_buf = 0

    if rows_in_buf:
        yield buf.getvalue().encode("utf-8")
