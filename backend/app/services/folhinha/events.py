"""Persist structured Folhinha interaction events (bonk / abraco / roulette / cookies)."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.database import db
from app.services.folhinha.parsers import (
    parse_folhinha_reply,
    parse_user_command,
)

logger = logging.getLogger(__name__)

LOOKBACK = timedelta(seconds=20)
FOLHINHA_LOGIN = "folhinhabot"


def _dedupe_key(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


async def _upsert_event(doc: dict) -> str | None:
    key = doc.get("dedupe_key")
    if not key:
        return None
    existing = await db.folhinha_events.find_one({"dedupe_key": key})
    if existing:
        updates: dict[str, Any] = {}
        if doc.get("percentage") is not None and existing.get("percentage") is None:
            updates["percentage"] = doc["percentage"]
        if doc.get("target_username") and not existing.get("target_username"):
            updates["target_username"] = doc["target_username"]
            updates["target_user_id"] = doc.get("target_user_id")
        if doc.get("actor_username") and not existing.get("actor_username"):
            updates["actor_username"] = doc["actor_username"]
            updates["actor_user_id"] = doc.get("actor_user_id")
        if doc.get("raw_reply") and not existing.get("raw_reply"):
            updates["raw_reply"] = doc["raw_reply"]
        for field in ("cookies_balance", "cookies_delta", "cookies_wagered"):
            if doc.get(field) is not None and existing.get(field) is None:
                updates[field] = doc[field]
        if updates:
            sources = list({*(existing.get("sources") or []), *(doc.get("sources") or [])})
            updates["sources"] = sources
            await db.folhinha_events.update_one({"_id": existing["_id"]}, {"$set": updates})
        return str(existing["_id"])

    result = await db.folhinha_events.insert_one(doc)
    return str(result.inserted_id)


def _base_doc(
    *,
    kind: str,
    platform: str,
    event_at: datetime,
    actor_username: str | None,
    actor_user_id: str | None,
    target_username: str | None,
    target_user_id: str | None,
    percentage: float | None,
    command: str | None,
    sources: list[str],
    raw_message: str | None = None,
    raw_reply: str | None = None,
    message_id: str | None = None,
    dedupe_key: str,
    meta: dict | None = None,
    cookies_balance: int | None = None,
    cookies_delta: int | None = None,
    cookies_wagered: int | None = None,
) -> dict:
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=timezone.utc)
    return {
        "kind": kind,
        "platform": platform or "twitch",
        "event_at": event_at,
        "recorded_at": datetime.now(timezone.utc),
        "actor_username": actor_username,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "target_username": target_username,
        "target_user_id": str(target_user_id) if target_user_id else None,
        "percentage": percentage,
        "cookies_balance": cookies_balance,
        "cookies_delta": cookies_delta,
        "cookies_wagered": cookies_wagered,
        "command": command,
        "sources": sources,
        "raw_message": (raw_message or None) and raw_message[:500],
        "raw_reply": (raw_reply or None) and raw_reply[:500],
        "message_id": message_id,
        "dedupe_key": dedupe_key,
        "meta": meta or {},
    }


async def _find_recent_user_cmd(
    *,
    platform: str,
    username: str | None,
    pattern: str,
    around: datetime,
) -> dict | None:
    if not username:
        return None
    since = around - LOOKBACK
    until = around + timedelta(seconds=2)
    rows = await (
        db.messages.find(
            {
                "platform": platform,
                "username": username.lower(),
                "timestamp": {"$gte": since, "$lte": until},
                "message": {"$regex": pattern, "$options": "i"},
            }
        )
        .sort("timestamp", -1)
        .limit(1)
        .to_list(1)
    )
    return rows[0] if rows else None


async def record_from_user_message(doc: dict) -> str | None:
    """Ingest chatter Folhinha commands into folhinha_events."""
    username = (doc.get("username") or "").lower()
    if username == FOLHINHA_LOGIN or doc.get("is_bot"):
        return None

    parsed = parse_user_command(doc.get("message") or "", username=username)
    if not parsed or not parsed.actor_username:
        return None

    # Slot outcomes come from Folhinha replies (need delta); ignore bare user cmd
    if parsed.kind == "cookie_slot":
        return None

    if parsed.kind == "bonk" and not parsed.target_username:
        return None
    if parsed.kind == "abraco" and not parsed.target_username:
        return None

    ts = doc.get("timestamp") or datetime.now(timezone.utc)
    if parsed.kind == "cookie_cd":
        key = _dedupe_key(
            "cookie_cd",
            doc.get("platform", "twitch"),
            parsed.actor_username,
            doc.get("message_id") or f"{int(ts.timestamp())}",
        )
    else:
        bucket = int(ts.timestamp() // 5)
        key = _dedupe_key(
            parsed.kind,
            doc.get("platform", "twitch"),
            parsed.actor_username,
            parsed.target_username,
            bucket,
        )

    event = _base_doc(
        kind=parsed.kind,
        platform=doc.get("platform") or "twitch",
        event_at=ts,
        actor_username=parsed.actor_username,
        actor_user_id=doc.get("user_id"),
        target_username=parsed.target_username,
        target_user_id=None,
        percentage=None,
        command=parsed.command,
        sources=["user_command"],
        raw_message=doc.get("message"),
        message_id=doc.get("message_id"),
        dedupe_key=key,
    )
    return await _upsert_event(event)


async def record_from_folhinha_message(doc: dict) -> str | None:
    """Ingest FolhinhaBot replies into folhinha_events."""
    parsed = parse_folhinha_reply(doc.get("message") or "")
    if not parsed:
        return None

    ts = doc.get("timestamp") or datetime.now(timezone.utc)
    platform = doc.get("platform") or "twitch"
    mid = doc.get("message_id") or f"{int(ts.timestamp())}"

    if parsed.kind == "roulette_survive" and parsed.actor_username:
        key = _dedupe_key("roulette_survive", platform, parsed.actor_username, int(ts.timestamp() // 3))
        event = _base_doc(
            kind="roulette_survive",
            platform=platform,
            event_at=ts,
            actor_username=parsed.actor_username,
            actor_user_id=None,
            target_username=None,
            target_user_id=None,
            percentage=None,
            command=parsed.command or "?rr",
            sources=["folhinha_reply"],
            raw_reply=doc.get("message"),
            message_id=doc.get("message_id"),
            dedupe_key=key,
        )
        return await _upsert_event(event)

    if parsed.kind == "roulette_death":
        since = ts - LOOKBACK
        cmd = await (
            db.messages.find(
                {
                    "platform": platform,
                    "timestamp": {"$gte": since, "$lte": ts},
                    "message": {"$regex": r"^\s*\?(rr|roleta)\b", "$options": "i"},
                    "username": {"$ne": FOLHINHA_LOGIN},
                }
            )
            .sort("timestamp", -1)
            .limit(1)
            .to_list(1)
        )
        actor = None
        actor_id = None
        if cmd:
            actor = (cmd[0].get("username") or "").lower() or None
            actor_id = cmd[0].get("user_id")
        if not actor:
            return None
        key = _dedupe_key("roulette_death", platform, actor, int(ts.timestamp() // 3))
        event = _base_doc(
            kind="roulette_death",
            platform=platform,
            event_at=ts,
            actor_username=actor,
            actor_user_id=actor_id,
            target_username=None,
            target_user_id=None,
            percentage=None,
            command="?rr",
            sources=["folhinha_reply", "bang"],
            raw_reply=doc.get("message"),
            message_id=doc.get("message_id"),
            dedupe_key=key,
        )
        return await _upsert_event(event)

    if parsed.kind == "cookie_claim" and parsed.actor_username:
        key = _dedupe_key("cookie_claim", platform, parsed.actor_username, mid)
        event = _base_doc(
            kind="cookie_claim",
            platform=platform,
            event_at=ts,
            actor_username=parsed.actor_username,
            actor_user_id=None,
            target_username=None,
            target_user_id=None,
            percentage=None,
            command="?cd",
            sources=["folhinha_reply"],
            raw_reply=doc.get("message"),
            message_id=doc.get("message_id"),
            dedupe_key=key,
            cookies_balance=parsed.cookies_balance,
        )
        return await _upsert_event(event)

    if parsed.kind == "cookie_balance" and parsed.actor_username:
        key = _dedupe_key("cookie_balance", platform, parsed.actor_username, mid)
        event = _base_doc(
            kind="cookie_balance",
            platform=platform,
            event_at=ts,
            actor_username=parsed.actor_username,
            actor_user_id=None,
            target_username=None,
            target_user_id=None,
            percentage=None,
            command=parsed.command,
            sources=["folhinha_reply"],
            raw_reply=doc.get("message"),
            message_id=doc.get("message_id"),
            dedupe_key=key,
            cookies_balance=parsed.cookies_balance,
        )
        return await _upsert_event(event)

    if parsed.kind == "cookie_slot" and parsed.actor_username:
        key = _dedupe_key("cookie_slot", platform, parsed.actor_username, mid)
        event = _base_doc(
            kind="cookie_slot",
            platform=platform,
            event_at=ts,
            actor_username=parsed.actor_username,
            actor_user_id=None,
            target_username=None,
            target_user_id=None,
            percentage=None,
            command="?cookie slot",
            sources=["folhinha_reply"],
            raw_reply=doc.get("message"),
            message_id=doc.get("message_id"),
            dedupe_key=key,
            cookies_balance=parsed.cookies_balance,
            cookies_delta=parsed.cookies_delta,
            cookies_wagered=parsed.cookies_wagered,
        )
        return await _upsert_event(event)

    if parsed.kind == "bonk" and parsed.actor_username:
        target = parsed.target_username
        if not target:
            recent = await _find_recent_user_cmd(
                platform=platform,
                username=parsed.actor_username,
                pattern=r"^\s*\?bonk\b",
                around=ts,
            )
            if recent:
                cmd_parsed = parse_user_command(
                    recent.get("message") or "", username=parsed.actor_username
                )
                if cmd_parsed:
                    target = cmd_parsed.target_username

        bucket = int(ts.timestamp() // 5)
        key = _dedupe_key("bonk", platform, parsed.actor_username, target, bucket)
        event = _base_doc(
            kind="bonk",
            platform=platform,
            event_at=ts,
            actor_username=parsed.actor_username,
            actor_user_id=None,
            target_username=target,
            target_user_id=None,
            percentage=parsed.percentage,
            command="?bonk",
            sources=["folhinha_reply"],
            raw_reply=doc.get("message"),
            message_id=doc.get("message_id"),
            dedupe_key=key,
        )
        return await _upsert_event(event)

    return None


async def record_roulette_death_from_moderation(
    *,
    target_username: str | None,
    target_user_id: str | None,
    event_at: datetime,
    platform: str = "twitch",
    command: str | None = None,
) -> str | None:
    """When CLEARCHAT is attributed to Folhinha roulette, record a death event."""
    actor = (target_username or "").lower() or None
    if not actor:
        return None
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=timezone.utc)
    key = _dedupe_key("roulette_death", platform, actor, int(event_at.timestamp() // 3))
    event = _base_doc(
        kind="roulette_death",
        platform=platform,
        event_at=event_at,
        actor_username=actor,
        actor_user_id=target_user_id,
        target_username=None,
        target_user_id=None,
        percentage=None,
        command=command or "?rr",
        sources=["moderation"],
        dedupe_key=key,
    )
    return await _upsert_event(event)


async def process_message_doc(doc: dict) -> None:
    """Route a stored chat message into Folhinha event ingest."""
    try:
        username = (doc.get("username") or "").lower()
        if username == FOLHINHA_LOGIN or doc.get("is_bot"):
            await record_from_folhinha_message(doc)
        else:
            await record_from_user_message(doc)
    except Exception as exc:
        logger.error("Folhinha event ingest failed: %s", exc)
