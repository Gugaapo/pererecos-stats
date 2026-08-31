"""Persist Twitch timeouts/bans (and related CLEARCHAT metadata)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import logging
import re
from typing import Any

from app.database import db

logger = logging.getLogger(__name__)

DEDUP_WINDOW = timedelta(seconds=8)
FOLHINHA_CMD_LOOKBACK = timedelta(seconds=15)
FOLHINHA_BANG_WINDOW = timedelta(seconds=12)

# ?rr / ?roleta right before a timeout
FOLHINHA_ROULETTE_CMD = re.compile(r"^\s*\?(rr|roleta)\b", re.IGNORECASE)
# Lose announcement from FolhinhaBot (timeout just happened / about to)
FOLHINHA_BANG = re.compile(r"^\s*BANG!", re.IGNORECASE)

FOLHINHA_LOGIN = "folhinhabot"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _folhinha_moderator_fields() -> dict[str, Any]:
    return {
        "moderator_user_id": None,
        "moderator_username": FOLHINHA_LOGIN,
        "moderator_display_name": "FolhinhaBot",
        "moderator_inferred": True,
        "moderator_inference": "folhinha_roulette",
    }


async def _find_recent_roulette_command(
    *,
    target_user_id: str | None,
    target_username: str | None,
    event_at: datetime,
) -> dict | None:
    """User sent ?rr / ?roleta shortly before the timeout."""
    since = event_at - FOLHINHA_CMD_LOOKBACK
    until = event_at + timedelta(seconds=2)
    identity: list[dict] = []
    if target_user_id:
        identity.append({"user_id": str(target_user_id)})
    if target_username:
        identity.append({"username": target_username.lower()})
    if not identity:
        return None

    cursor = (
        db.messages.find(
            {
                "platform": "twitch",
                "timestamp": {"$gte": since, "$lte": until},
                "$or": identity,
                "message": {"$regex": r"^\s*\?(rr|roleta)\b", "$options": "i"},
            }
        )
        .sort("timestamp", -1)
        .limit(1)
    )
    rows = await cursor.to_list(1)
    return rows[0] if rows else None


async def maybe_attribute_folhinha_roulette(
    event_id,
    *,
    target_user_id: str | None,
    target_username: str | None,
    event_at: datetime,
    existing: dict | None = None,
) -> bool:
    """If this timeout followed ?rr/?roleta, mark FolhinhaBot as moderator."""
    if existing and existing.get("moderator_username") and not existing.get("moderator_inferred"):
        return False  # real EventSub mod wins
    if existing and existing.get("moderator_username") == FOLHINHA_LOGIN:
        return False

    cmd = await _find_recent_roulette_command(
        target_user_id=target_user_id,
        target_username=target_username,
        event_at=event_at,
    )
    if not cmd:
        return False

    raw = (cmd.get("message") or "").strip().split()
    cmd_text = raw[0].lower() if raw else "?rr"
    updates = {
        **_folhinha_moderator_fields(),
        "folhinha_command": cmd_text[:32],
        "folhinha_command_at": cmd.get("timestamp"),
        "sources": list({
            *((existing or {}).get("sources") or []),
            "folhinha_roulette",
        }),
    }
    await db.moderation_events.update_one({"_id": event_id}, {"$set": updates})
    logger.info(
        "Attributed timeout of %s to FolhinhaBot via %s",
        target_username or target_user_id,
        cmd_text,
    )
    try:
        from app.services.folhinha.events import record_roulette_death_from_moderation
        await record_roulette_death_from_moderation(
            target_username=target_username,
            target_user_id=target_user_id,
            event_at=event_at,
            command=cmd_text,
        )
    except Exception as exc:
        logger.error("Folhinha roulette death event failed: %s", exc)
    return True


async def attribute_from_folhinha_bang(doc: dict) -> None:
    """When Folhinha posts BANG!, attach to a nearby unattributed timeout if possible."""
    text = doc.get("message") or ""
    if not FOLHINHA_BANG.search(text):
        return
    ts = doc.get("timestamp")
    if not ts:
        return
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    since = ts - FOLHINHA_BANG_WINDOW
    until = ts + timedelta(seconds=3)
    event = await (
        db.moderation_events.find(
            {
                "platform": "twitch",
                "action": "timeout",
                "event_at": {"$gte": since, "$lte": until},
                "$or": [
                    {"moderator_username": None},
                    {"moderator_username": {"$exists": False}},
                    {"moderator_inferred": True, "moderator_username": FOLHINHA_LOGIN},
                ],
            }
        )
        .sort("event_at", -1)
        .limit(1)
        .to_list(1)
    )
    event = event[0] if event else None
    if not event:
        return

    await maybe_attribute_folhinha_roulette(
        event["_id"],
        target_user_id=event.get("target_user_id"),
        target_username=event.get("target_username"),
        event_at=event.get("event_at") or ts,
        existing=event,
    )
    await db.moderation_events.update_one(
        {"_id": event["_id"]},
        {"$set": {
            "folhinha_bang_message": text[:300],
            "folhinha_bang_at": ts,
            "sources": list({*(event.get("sources") or []), "folhinha_bang"}),
        }},
    )


async def record_clearchat_moderation(
    *,
    target_user_id: str,
    target_username: str | None,
    ban_duration: int | None,
    ban_reason: str | None,
    room_id: str | None,
    tmi_sent_ts: str | None,
    channel: str | None,
) -> str | None:
    """Insert or enrich a moderation event from IRC CLEARCHAT.

    ban_duration: seconds for a timeout; None means permanent ban.
    Moderator is not on IRC — may be inferred from Folhinha ?rr/?roleta.
    """
    now = datetime.now(timezone.utc)
    event_at = now
    if tmi_sent_ts and tmi_sent_ts.isdigit():
        try:
            event_at = datetime.fromtimestamp(int(tmi_sent_ts) / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            event_at = now

    action = "timeout" if ban_duration is not None else "ban"
    duration_seconds = int(ban_duration) if ban_duration is not None else None

    existing = await db.moderation_events.find_one(
        {
            "platform": "twitch",
            "target_user_id": str(target_user_id),
            "event_at": {"$gte": event_at - DEDUP_WINDOW, "$lte": event_at + DEDUP_WINDOW},
        },
        sort=[("event_at", -1)],
    )
    if existing:
        updates: dict[str, Any] = {}
        if duration_seconds is not None and existing.get("duration_seconds") is None:
            updates["duration_seconds"] = duration_seconds
            updates["action"] = "timeout"
            updates["is_permanent"] = False
        if ban_reason and not existing.get("reason"):
            updates["reason"] = ban_reason[:500]
        if target_username and not existing.get("target_username"):
            updates["target_username"] = target_username.lower()
        if "irc_clearchat" not in (existing.get("sources") or []):
            updates["sources"] = list({*(existing.get("sources") or []), "irc_clearchat"})
        if updates:
            await db.moderation_events.update_one({"_id": existing["_id"]}, {"$set": updates})
            existing = {**existing, **updates}
        if action == "timeout" or existing.get("action") == "timeout":
            await maybe_attribute_folhinha_roulette(
                existing["_id"],
                target_user_id=str(target_user_id),
                target_username=target_username or existing.get("target_username"),
                event_at=event_at,
                existing=existing,
            )
        return str(existing["_id"])

    doc = {
        "platform": "twitch",
        "action": action,
        "is_permanent": duration_seconds is None,
        "duration_seconds": duration_seconds,
        "target_user_id": str(target_user_id),
        "target_username": (target_username or "").lower() or None,
        "moderator_user_id": None,
        "moderator_username": None,
        "moderator_display_name": None,
        "reason": (ban_reason or None) and ban_reason[:500],
        "channel": channel,
        "room_id": room_id,
        "event_at": event_at,
        "recorded_at": now,
        "sources": ["irc_clearchat"],
    }
    result = await db.moderation_events.insert_one(doc)
    if action == "timeout":
        await maybe_attribute_folhinha_roulette(
            result.inserted_id,
            target_user_id=str(target_user_id),
            target_username=target_username,
            event_at=event_at,
            existing=doc,
        )
    logger.info(
        "Moderation event %s target=%s duration=%s",
        action,
        target_user_id,
        duration_seconds,
    )
    return str(result.inserted_id)


async def record_eventsub_ban(event: dict) -> str | None:
    """Insert or enrich from EventSub channel.ban (has moderator + ends_at)."""
    target_user_id = str(event.get("user_id") or "")
    if not target_user_id:
        return None

    banned_at = _parse_iso(event.get("banned_at")) or datetime.now(timezone.utc)
    ends_at = _parse_iso(event.get("ends_at"))
    is_permanent = bool(event.get("is_permanent"))
    duration_seconds = None
    if not is_permanent and ends_at and banned_at:
        duration_seconds = max(0, int((ends_at - banned_at).total_seconds()))

    action = "ban" if is_permanent else "timeout"
    mod_id = event.get("moderator_user_id")
    mod_login = (event.get("moderator_user_login") or "").lower() or None
    mod_name = event.get("moderator_user_name")
    reason = event.get("reason") or None
    target_login = (event.get("user_login") or "").lower() or None

    existing = await db.moderation_events.find_one(
        {
            "platform": "twitch",
            "target_user_id": target_user_id,
            "event_at": {"$gte": banned_at - DEDUP_WINDOW, "$lte": banned_at + DEDUP_WINDOW},
        },
        sort=[("event_at", -1)],
    )
    if existing:
        updates = {
            "action": action,
            "is_permanent": is_permanent,
            "duration_seconds": duration_seconds if duration_seconds is not None else existing.get("duration_seconds"),
            "target_username": target_login or existing.get("target_username"),
            "moderator_user_id": str(mod_id) if mod_id else existing.get("moderator_user_id"),
            "moderator_username": mod_login or existing.get("moderator_username"),
            "moderator_display_name": mod_name or existing.get("moderator_display_name"),
            "moderator_inferred": False if mod_login else existing.get("moderator_inferred"),
            "reason": (reason[:500] if reason else existing.get("reason")),
            "ends_at": ends_at,
            "sources": list({*(existing.get("sources") or []), "eventsub_channel_ban"}),
            "eventsub_event": event,
        }
        await db.moderation_events.update_one({"_id": existing["_id"]}, {"$set": updates})
        return str(existing["_id"])

    doc = {
        "platform": "twitch",
        "action": action,
        "is_permanent": is_permanent,
        "duration_seconds": duration_seconds,
        "target_user_id": target_user_id,
        "target_username": target_login,
        "target_display_name": event.get("user_name"),
        "moderator_user_id": str(mod_id) if mod_id else None,
        "moderator_username": mod_login,
        "moderator_display_name": mod_name,
        "moderator_inferred": False,
        "reason": reason[:500] if reason else None,
        "channel": (event.get("broadcaster_user_login") or "").lower() or None,
        "room_id": str(event.get("broadcaster_user_id")) if event.get("broadcaster_user_id") else None,
        "event_at": banned_at,
        "ends_at": ends_at,
        "recorded_at": datetime.now(timezone.utc),
        "sources": ["eventsub_channel_ban"],
        "eventsub_event": event,
    }
    result = await db.moderation_events.insert_one(doc)
    logger.info(
        "EventSub %s target=%s by=%s duration=%s",
        action,
        target_login or target_user_id,
        mod_login,
        duration_seconds,
    )
    return str(result.inserted_id)
