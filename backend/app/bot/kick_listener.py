import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta

import bleach
import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from app.bot.twitch_bot import sanitize_message
from app.config import get_settings
from app.database import db

logger = logging.getLogger(__name__)

BRT = timezone(timedelta(hours=-3))

PUSHER_APP_KEY = "32cbd69e4b950bf97679"
PUSHER_CLUSTER = "us2"
PUSHER_EVENT = r"App\Events\ChatMessageEvent"

KICK_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

ALLOWED_TAGS: list[str] = []
ALLOWED_ATTRIBUTES: dict[str, list[str]] = {}

KICK_SKIP_STORE_BOTS: set[str] = {
    "streamadsbot",
    "fossabot",
}


async def resolve_chatroom_id(channel: str, override_id: int = 0) -> int:
    if override_id:
        return override_id

    url = f"https://kick.com/api/v2/channels/{channel.lower()}"
    async with httpx.AsyncClient(timeout=15.0, headers=KICK_HEADERS) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        chatroom_id = data.get("chatroom", {}).get("id")
        if not chatroom_id:
            raise ValueError(f"No chatroom id found for Kick channel '{channel}'")
        return int(chatroom_id)


def _sanitize_display_name(name: str) -> str:
    cleaned = bleach.clean(name, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
    return cleaned[:25]


async def save_kick_message(payload: dict, channel: str) -> None:
    sender = payload.get("sender") or {}
    username = (sender.get("username") or sender.get("slug") or "").lower()
    if not username:
        return
    if username in KICK_SKIP_STORE_BOTS:
        return

    is_folhinha = username == "folhinhabot"

    content = payload.get("content") or ""
    if not content.strip():
        return

    user_id = str(sender.get("id") or sender.get("user_id") or username)
    display_name = _sanitize_display_name(sender.get("username") or username)

    now = datetime.now(timezone.utc)
    now_brt = now.astimezone(BRT)

    doc = {
        "platform": "kick",
        "user_id": user_id,
        "username": username,
        "display_name": display_name,
        "message": sanitize_message(content),
        "channel": channel.lower(),
        "timestamp": now,
        "hour": now_brt.hour,
        "removed": False,
    }
    if is_folhinha:
        doc["is_bot"] = True
        doc["bot_name"] = "folhinhabot"

    # Kick reply metadata when present
    metadata = payload.get("metadata") or {}
    reply = metadata.get("original_message") or metadata.get("reply_to") or {}
    if isinstance(reply, dict) and reply:
        reply_sender = reply.get("sender") or reply.get("user") or {}
        if isinstance(reply_sender, dict):
            r_uid = reply_sender.get("id") or reply_sender.get("user_id")
            r_name = (reply_sender.get("username") or reply_sender.get("slug") or "").lower()
            if r_uid or r_name:
                doc["reply_to_user_id"] = str(r_uid) if r_uid else None
                doc["reply_to_username"] = r_name or None
                if reply_sender.get("username"):
                    doc["reply_to_display_name"] = _sanitize_display_name(reply_sender["username"])

    try:
        await db.messages.insert_one(doc)
        if not is_folhinha:
            from app.services.stats_aggregates import record_message
            await record_message(doc)
        try:
            from app.services.folhinha.events import process_message_doc
            await process_message_doc(doc)
        except Exception as fh_exc:
            logger.error("Folhinha event ingest failed (Kick): %s", fh_exc)
    except Exception as exc:
        logger.error("Error saving Kick message: %s", exc)


async def run_kick_listener() -> None:
    settings = get_settings()
    channel = settings.kick_channel.lower()
    reconnect_delay = 5

    while True:
        try:
            chatroom_id = await resolve_chatroom_id(channel, settings.kick_chatroom_id)
            ws_url = (
                f"wss://ws-{PUSHER_CLUSTER}.pusher.com/app/{PUSHER_APP_KEY}"
                "?protocol=7&client=js&version=7.6.0&flash=false"
            )
            pusher_channel = f"chatrooms.{chatroom_id}.v2"

            logger.info("Connecting to Kick chatroom %s (%s)", channel, chatroom_id)
            print(f"Kick listener connected to #{channel} (chatroom {chatroom_id})")

            async with websockets.connect(ws_url, ping_interval=30, ping_timeout=20) as ws:
                subscribed = False
                async for raw in ws:
                    try:
                        envelope = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    event = envelope.get("event")
                    data_raw = envelope.get("data", "{}")

                    if event == "pusher:connection_established":
                        await ws.send(json.dumps({
                            "event": "pusher:subscribe",
                            "data": {"auth": "", "channel": pusher_channel},
                        }))
                        continue

                    if event == "pusher_internal:subscription_succeeded":
                        subscribed = True
                        logger.info("Subscribed to Kick channel %s", pusher_channel)
                        continue

                    if event == PUSHER_EVENT:
                        try:
                            payload = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
                        except (json.JSONDecodeError, TypeError):
                            continue
                        await save_kick_message(payload, channel)

                    if event == "pusher:error":
                        logger.error("Kick Pusher error: %s", data_raw)
                        if not subscribed:
                            raise ConnectionError(f"Pusher error: {data_raw}")

        except asyncio.CancelledError:
            logger.info("Kick listener cancelled")
            raise
        except Exception as exc:
            logger.error("Kick listener error: %s", exc, exc_info=True)
            print(f"Kick listener disconnected, retrying in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
