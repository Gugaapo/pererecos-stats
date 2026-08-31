#!/usr/bin/env python3
"""Backfill folhinha_events from existing chat_messages.

Usage (from backend/):
  ./venv/bin/python -m app.scripts.backfill_folhinha_events
  ./venv/bin/python -m app.scripts.backfill_folhinha_events --csv /path/to/export.csv
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.database import db
from app.services.folhinha.events import process_message_doc
from app.services.folhinha.import_csv import import_messages_csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill_folhinha_events")


async def backfill_from_messages(limit: int | None = None) -> int:
    await db.connect()
    query = {
        "$or": [
            {"username": "folhinhabot"},
            {"message": {"$regex": r"^\s*\?(bonk|abra[cç]o|rr|roleta|cd|cookie\s+slot|c\s+slot)\b", "$options": "i"}},
        ]
    }
    cursor = db.messages.find(query).sort("timestamp", 1)
    if limit:
        cursor = cursor.limit(limit)
    n = 0
    async for doc in cursor:
        await process_message_doc(doc)
        n += 1
        if n % 500 == 0:
            logger.info("Processed %d messages...", n)
    logger.info("Done. Processed %d messages.", n)
    await db.disconnect()
    return n


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="Import CSV first (export format), then extract events")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.csv:
        await db.connect()
        summary = await import_messages_csv(args.csv, extract_events=True, dry_run=args.dry_run)
        logger.info("CSV import: %s", summary)
        await db.disconnect()
        return

    await backfill_from_messages(limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
