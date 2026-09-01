from twitchio.ext import commands
from datetime import datetime, timezone, timedelta
from pathlib import Path
import bleach

# Brasília timezone (UTC-3)
BRT = timezone(timedelta(hours=-3))
import httpx
import logging
from app.config import get_settings
from app.database import db
from app.ingest_gate import ingest_enabled

logger = logging.getLogger(__name__)

# Allowed tags/attributes for message sanitization (strip all HTML)
ALLOWED_TAGS: list[str] = []
ALLOWED_ATTRIBUTES: dict[str, list[str]] = {}

# Bot accounts never stored in chat_messages
SKIP_STORE_BOTS: set[str] = {
    "streamadsbot",
    "fossabot",
}

# Still excluded from leaderboards / aggregates (see common.query.IGNORED_BOTS).
# FolhinhaBot is stored so we can read ?command replies, but not ranked.


def sanitize_message(content: str) -> str:
    """Sanitize message content to prevent XSS"""
    # Strip all HTML tags
    cleaned = bleach.clean(content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
    # Limit message length
    return cleaned[:500] if len(cleaned) > 500 else cleaned


class TwitchBot(commands.Bot):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            token=settings.twitch_oauth_token,
            prefix="!",
            initial_channels=[settings.twitch_channel]
        )
        self.target_channel = settings.twitch_channel
        self._settings = settings

    async def event_ready(self):
        logger.info(f"Bot connected as {self.nick} to #{self.target_channel}")
        print(f"Bot connected as {self.nick} to #{self.target_channel}")

    async def refresh_oauth_token(self) -> bool:
        """Refresh the OAuth token using the refresh token and persist to .env."""
        settings = self._settings
        if not settings.twitch_refresh_token or not settings.twitch_client_id or not settings.twitch_client_secret:
            logger.warning("Cannot refresh token: missing refresh_token, client_id, or client_secret")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": settings.twitch_refresh_token,
                        "client_id": settings.twitch_client_id,
                        "client_secret": settings.twitch_client_secret,
                    }
                )
                if response.status_code != 200:
                    logger.error(f"Failed to refresh token: {response.status_code}")
                    return False

                data = response.json()
                access = data.get("access_token") or ""
                new_refresh = data.get("refresh_token") or settings.twitch_refresh_token
                if not access:
                    logger.error("Refresh response missing access_token")
                    return False

                oauth_value = access if access.startswith("oauth:") else f"oauth:{access}"
                settings.twitch_oauth_token = oauth_value
                settings.twitch_refresh_token = new_refresh
                self._persist_twitch_tokens(oauth_value, new_refresh)
                logger.info("Successfully refreshed OAuth token")
                return True
        except Exception as e:
            logger.error(f"Error refreshing OAuth token: {e}")
            return False

    def _persist_twitch_tokens(self, oauth_token: str, refresh_token: str) -> None:
        """Write refreshed tokens back to the backend .env file if present."""
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if not env_path.exists():
            logger.warning("Cannot persist tokens: .env not found at %s", env_path)
            return
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
            updated = {"TWITCH_OAUTH_TOKEN": False, "TWITCH_REFRESH_TOKEN": False}
            out: list[str] = []
            for line in lines:
                if line.startswith("TWITCH_OAUTH_TOKEN="):
                    out.append(f"TWITCH_OAUTH_TOKEN={oauth_token}")
                    updated["TWITCH_OAUTH_TOKEN"] = True
                elif line.startswith("TWITCH_REFRESH_TOKEN="):
                    out.append(f"TWITCH_REFRESH_TOKEN={refresh_token}")
                    updated["TWITCH_REFRESH_TOKEN"] = True
                else:
                    out.append(line)
            if not updated["TWITCH_OAUTH_TOKEN"]:
                out.append(f"TWITCH_OAUTH_TOKEN={oauth_token}")
            if not updated["TWITCH_REFRESH_TOKEN"]:
                out.append(f"TWITCH_REFRESH_TOKEN={refresh_token}")
            env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to persist Twitch tokens: %s", exc)

    async def event_message(self, message):
        if message.echo:
            return

        # Ignore bot accounts we never want in the DB (FolhinhaBot is stored)
        if message.author.name.lower() in SKIP_STORE_BOTS:
            return

        if not ingest_enabled():
            return

        now = datetime.now(timezone.utc)
        now_brt = now.astimezone(BRT)
        username_lower = message.author.name.lower()
        is_folhinha = username_lower == "folhinhabot"

        # Sanitize user inputs
        sanitized_message = sanitize_message(message.content)
        sanitized_display_name = bleach.clean(
            message.author.display_name or message.author.name,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True
        )[:25]  # Twitch display names max 25 chars

        # Real Twitch reply-parent tags (when the user used the reply feature)
        tags = getattr(message, "tags", None) or {}
        msg_id = None
        try:
            msg_id = message.id
        except Exception:
            msg_id = tags.get("id")

        doc = {
            "platform": "twitch",
            "user_id": str(message.author.id),  # Twitch user ID (permanent)
            "username": username_lower,
            "display_name": sanitized_display_name,
            "message": sanitized_message,
            "channel": message.channel.name,
            "timestamp": now,
            "hour": now_brt.hour,  # Store hour in Brasília timezone (UTC-3)
            "removed": False,
        }
        if is_folhinha:
            doc["is_bot"] = True
            doc["bot_name"] = "folhinhabot"
        if msg_id:
            doc["message_id"] = str(msg_id)

        reply_uid = tags.get("reply-parent-user-id")
        reply_login = tags.get("reply-parent-user-login")
        reply_display = tags.get("reply-parent-display-name")
        if reply_uid or reply_login:
            doc["reply_to_user_id"] = str(reply_uid) if reply_uid else None
            doc["reply_to_username"] = (reply_login or "").lower() or None
            if reply_display:
                doc["reply_to_display_name"] = bleach.clean(
                    reply_display, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True
                )[:25]

        try:
            await db.messages.insert_one(doc)
            # FolhinhaBot stays in IGNORED_BOTS for aggregates — store only, no counters
            if not is_folhinha:
                from app.services.stats_aggregates import record_message
                await record_message(doc)
                try:
                    from app.services.folhinha.events import process_message_doc
                    await process_message_doc(doc)
                except Exception as fh_exc:
                    logger.error("Folhinha event ingest failed: %s", fh_exc)
            else:
                try:
                    from app.services.moderation_service import attribute_from_folhinha_bang
                    await attribute_from_folhinha_bang(doc)
                except Exception as bang_exc:
                    logger.error("Folhinha BANG attribution failed: %s", bang_exc)
                try:
                    from app.services.folhinha.events import process_message_doc
                    await process_message_doc(doc)
                except Exception as fh_exc:
                    logger.error("Folhinha event ingest failed: %s", fh_exc)
        except Exception as e:
            logger.error(f"Error saving message: {e}")

        # Subathon fork: do not answer chat commands (!stats) — original bot owns those.
        # if not is_folhinha:
        #     await self.handle_commands(message)

    async def event_raw_data(self, data: str):
        """Handle IRC CLEARMSG / CLEARCHAT to flag mod-removed messages."""
        if " CLEARMSG " not in data and " CLEARCHAT " not in data:
            return

        if not ingest_enabled():
            return

        try:
            tags: dict[str, str] = {}
            payload = data
            if data.startswith("@"):
                tag_part, _, payload = data[1:].partition(" ")
                for pair in tag_part.split(";"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        tags[k] = v

            now = datetime.now(timezone.utc)

            if " CLEARMSG " in payload:
                target_id = tags.get("target-msg-id")
                if not target_id:
                    return
                result = await db.messages.update_one(
                    {"message_id": target_id, "platform": "twitch"},
                    {"$set": {
                        "removed": True,
                        "removed_at": now,
                        "removed_reason": "clearmsg",
                    }},
                )
                if result.modified_count:
                    logger.info("Marked message %s as removed (CLEARMSG)", target_id)
                return

            if " CLEARCHAT " in payload:
                target_user_id = tags.get("target-user-id")
                # Full /clear (no user) — do not mass-mark historical messages
                if not target_user_id:
                    return

                ban_duration_raw = tags.get("ban-duration")
                ban_duration = None
                if ban_duration_raw is not None and ban_duration_raw != "":
                    try:
                        ban_duration = int(ban_duration_raw)
                    except ValueError:
                        ban_duration = None
                ban_reason = tags.get("ban-reason")
                if ban_reason:
                    ban_reason = ban_reason.replace("\\s", " ")

                # CLEARCHAT trailing param is the login: ":tmi.twitch.tv CLEARCHAT #chan :login"
                target_username = None
                if " :" in payload:
                    target_username = payload.rsplit(" :", 1)[-1].strip().lower() or None

                channel = None
                if " CLEARCHAT #" in payload:
                    try:
                        channel = payload.split(" CLEARCHAT #", 1)[1].split(" ", 1)[0].lower()
                    except IndexError:
                        channel = None

                try:
                    from app.services.moderation_service import record_clearchat_moderation
                    await record_clearchat_moderation(
                        target_user_id=str(target_user_id),
                        target_username=target_username,
                        ban_duration=ban_duration,
                        ban_reason=ban_reason,
                        room_id=tags.get("room-id"),
                        tmi_sent_ts=tags.get("tmi-sent-ts"),
                        channel=channel,
                    )
                except Exception as mod_exc:
                    logger.error("Failed to record CLEARCHAT moderation event: %s", mod_exc)

                # Timeout/ban clears that user's visible chat; limit to recent window
                since = now - timedelta(hours=24)
                result = await db.messages.update_many(
                    {
                        "platform": "twitch",
                        "user_id": str(target_user_id),
                        "removed": {"$ne": True},
                        "timestamp": {"$gte": since},
                    },
                    {"$set": {
                        "removed": True,
                        "removed_at": now,
                        "removed_reason": "clearchat",
                        "removed_action": "timeout" if ban_duration is not None else "ban",
                        "removed_duration_seconds": ban_duration,
                    }},
                )
                if result.modified_count:
                    logger.info(
                        "Marked %d messages removed for user_id=%s (CLEARCHAT %s)",
                        result.modified_count,
                        target_user_id,
                        "timeout" if ban_duration is not None else "ban",
                    )
        except Exception as e:
            logger.error("Error handling CLEARMSG/CLEARCHAT: %s", e)

    @commands.command(name="stats")
    async def stats_command(self, ctx):
        await ctx.send(f"@{ctx.author.name} Veja suas estatisticas em tossemideia.cloud/pererecos-stats")
