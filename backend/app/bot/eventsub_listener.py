"""Twitch EventSub WebSocket client for channel.ban (timeouts/bans with moderator)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
import websockets

from app.config import get_settings
from app.ingest_gate import ingest_enabled
from app.services.moderation_service import record_eventsub_ban

logger = logging.getLogger(__name__)

EVENTSUB_WS = "wss://eventsub.wss.twitch.tv/ws"
HELIX = "https://api.twitch.tv/helix"


def _bearer(token: str) -> str:
    t = (token or "").strip()
    if t.lower().startswith("oauth:"):
        t = t[6:]
    return t


async def _helix_headers(settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_bearer(settings.twitch_oauth_token)}",
        "Client-Id": settings.twitch_client_id,
    }


async def _resolve_user_ids(settings) -> tuple[str | None, str | None]:
    """Return (broadcaster_id, bot_user_id)."""
    if not settings.twitch_client_id or not settings.twitch_oauth_token:
        return None, None
    headers = await _helix_headers(settings)
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Bot identity from the user access token
        me = await client.get(f"{HELIX}/users", headers=headers)
        if me.status_code != 200:
            logger.warning("EventSub: cannot resolve bot user (%s)", me.status_code)
            return None, None
        me_data = (me.json().get("data") or [])
        bot_id = me_data[0]["id"] if me_data else None

        channel = (settings.twitch_channel or "").lstrip("#").lower()
        br = await client.get(f"{HELIX}/users", headers=headers, params={"login": channel})
        if br.status_code != 200:
            logger.warning("EventSub: cannot resolve broadcaster %s (%s)", channel, br.status_code)
            return None, bot_id
        br_data = (br.json().get("data") or [])
        broadcaster_id = br_data[0]["id"] if br_data else None
        return broadcaster_id, bot_id


async def _subscribe_channel_ban(settings, session_id: str, broadcaster_id: str) -> bool:
    headers = await _helix_headers(settings)
    headers["Content-Type"] = "application/json"
    body = {
        "type": "channel.ban",
        "version": "1",
        "condition": {"broadcaster_user_id": broadcaster_id},
        "transport": {"method": "websocket", "session_id": session_id},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{HELIX}/eventsub/subscriptions", headers=headers, json=body)
        if resp.status_code in (200, 202):
            logger.info("EventSub channel.ban subscribed for broadcaster %s", broadcaster_id)
            return True
        logger.warning(
            "EventSub channel.ban subscribe failed (%s): %s — "
            "token likely missing channel:moderate scope (moderator will stay empty on IRC-only events)",
            resp.status_code,
            resp.text[:300],
        )
        return False


async def run_eventsub_listener(stop_event: asyncio.Event | None = None) -> None:
    """Long-running EventSub websocket loop. Safe to run as a background task."""
    settings = get_settings()
    if not settings.twitch_oauth_token or not settings.twitch_client_id:
        logger.info("EventSub disabled: missing oauth token or client_id")
        return

    backoff = 2
    while True:
        if stop_event and stop_event.is_set():
            return
        try:
            await _session_loop(settings, stop_event)
            backoff = 2
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("EventSub websocket error: %s — reconnect in %ss", exc, backoff)
            try:
                await asyncio.wait_for(
                    (stop_event.wait() if stop_event else asyncio.sleep(backoff)),
                    timeout=backoff,
                )
                if stop_event and stop_event.is_set():
                    return
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 60)


async def _session_loop(settings, stop_event: asyncio.Event | None) -> None:
    broadcaster_id, _bot_id = await _resolve_user_ids(settings)
    if not broadcaster_id:
        logger.warning("EventSub: no broadcaster id — not connecting")
        await asyncio.sleep(30)
        return

    async with websockets.connect(EVENTSUB_WS, ping_interval=20, ping_timeout=20) as ws:
        logger.info("EventSub websocket connected")
        async for raw in ws:
            if stop_event and stop_event.is_set():
                return
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                continue

            meta = msg.get("metadata") or {}
            payload = msg.get("payload") or {}
            msg_type = meta.get("message_type")

            if msg_type == "session_welcome":
                session_id = (payload.get("session") or {}).get("id")
                if not session_id:
                    logger.error("EventSub welcome missing session id")
                    return
                await _subscribe_channel_ban(settings, session_id, broadcaster_id)
                continue

            if msg_type == "session_reconnect":
                # Library will drop; outer loop reconnects. Prefer reconnect URL if present.
                reconnect_url = (payload.get("session") or {}).get("reconnect_url")
                logger.info("EventSub reconnect requested: %s", reconnect_url)
                return

            if msg_type == "notification":
                sub = payload.get("subscription") or {}
                if sub.get("type") == "channel.ban":
                    if not ingest_enabled():
                        continue
                    event = payload.get("event") or {}
                    try:
                        await record_eventsub_ban(event)
                    except Exception as exc:
                        logger.error("Failed to record EventSub ban: %s", exc)
                continue

            if msg_type == "session_keepalive":
                continue

            if msg_type == "revocation":
                logger.warning("EventSub subscription revoked: %s", payload)
                return
