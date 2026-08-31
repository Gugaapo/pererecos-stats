"""Import chat CSV (same columns as export) and extract Folhinha events.

CSV columns: time, platform, user, message, removed
time format: BRT %Y-%m-%d %H:%M:%S
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import BinaryIO, TextIO

from app.database import db
from app.services.common.period import BRT
from app.services.folhinha.events import process_message_doc

logger = logging.getLogger(__name__)

FOLHINHA_LOGIN = "folhinhabot"
EXPECTED_HEADER = ["time", "platform", "user", "message", "removed"]


def _parse_brt_time(value: str) -> datetime:
    # Accept with/without fractional seconds
    raw = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=BRT).astimezone(
                __import__("datetime").timezone.utc
            )
        except ValueError:
            continue
    raise ValueError(f"Invalid time: {value!r}")


async def import_messages_csv(
    source: str | BinaryIO | TextIO,
    *,
    extract_events: bool = True,
    dry_run: bool = False,
) -> dict:
    """Insert rows into chat_messages and optionally build folhinha_events.

    Dedupes on (platform, username, timestamp, message).
    FolhinhaBot rows get is_bot=True (and are excluded from normal aggregates).
    """
    if isinstance(source, str):
        text = open(source, "r", encoding="utf-8-sig", newline="")
        close = True
    elif hasattr(source, "read"):
        raw = source.read()
        if isinstance(raw, bytes):
            text = io.StringIO(raw.decode("utf-8-sig"))
        else:
            text = io.StringIO(raw)
        close = False
    else:
        raise TypeError("source must be a path or file-like")

    inserted = 0
    skipped = 0
    events = 0
    errors: list[str] = []

    try:
        reader = csv.DictReader(text)
        if not reader.fieldnames:
            raise ValueError("CSV missing header")
        header = [h.strip().lower() for h in reader.fieldnames]
        for col in EXPECTED_HEADER:
            if col not in header:
                raise ValueError(f"CSV missing column {col!r} (got {reader.fieldnames})")

        for i, row in enumerate(reader, start=2):
            try:
                ts = _parse_brt_time(row.get("time") or row.get("Time") or "")
                platform = (row.get("platform") or "twitch").strip().lower() or "twitch"
                username = (row.get("user") or "").strip().lower()
                message = row.get("message") or ""
                removed_raw = (row.get("removed") or "false").strip().lower()
                removed = removed_raw in {"1", "true", "yes", "y"}
                if not username:
                    skipped += 1
                    continue

                doc = {
                    "platform": platform,
                    "user_id": None,
                    "username": username,
                    "display_name": username,
                    "message": message,
                    "channel": "omeiaum" if platform == "twitch" else "meiaum",
                    "timestamp": ts,
                    "hour": ts.astimezone(BRT).hour,
                    "removed": removed,
                    "import_source": "csv",
                }
                if username == FOLHINHA_LOGIN:
                    doc["is_bot"] = True
                    doc["bot_name"] = "folhinhabot"

                if dry_run:
                    inserted += 1
                    continue

                existing = await db.messages.find_one(
                    {
                        "platform": platform,
                        "username": username,
                        "timestamp": ts,
                        "message": message,
                    },
                    {"_id": 1},
                )
                if existing:
                    skipped += 1
                    msg_doc = {**doc, "_id": existing["_id"]}
                else:
                    result = await db.messages.insert_one(doc)
                    inserted += 1
                    msg_doc = {**doc, "_id": result.inserted_id}

                if extract_events:
                    await process_message_doc(msg_doc)
                    events += 1
            except Exception as exc:
                errors.append(f"line {i}: {exc}")
                if len(errors) >= 50:
                    errors.append("… truncated")
                    break
    finally:
        if close:
            text.close()

    summary = {
        "inserted": inserted,
        "skipped": skipped,
        "events_delta_estimate": events,
        "errors": errors,
        "dry_run": dry_run,
    }
    logger.info("CSV import done: %s", summary)
    return summary
