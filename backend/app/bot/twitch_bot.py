from twitchio.ext import commands
from datetime import datetime, timezone, timedelta
import bleach

# Brasília timezone (UTC-3)
BRT = timezone(timedelta(hours=-3))
import httpx
import logging
from app.config import get_settings
from app.database import db

logger = logging.getLogger(__name__)

# Allowed tags/attributes for message sanitization (strip all HTML)
ALLOWED_TAGS: list[str] = []
ALLOWED_ATTRIBUTES: dict[str, list[str]] = {}


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
        """Refresh the OAuth token using the refresh token"""
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
                if response.status_code == 200:
                    data = response.json()
                    # Note: In production, you'd want to persist the new tokens
                    logger.info("Successfully refreshed OAuth token")
                    return True
                else:
                    logger.error(f"Failed to refresh token: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Error refreshing OAuth token: {e}")
            return False

    async def event_message(self, message):
        if message.echo:
            return

        now = datetime.now(timezone.utc)
        now_brt = now.astimezone(BRT)

        # Sanitize user inputs
        sanitized_message = sanitize_message(message.content)
        sanitized_display_name = bleach.clean(
            message.author.display_name or message.author.name,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True
        )[:25]  # Twitch display names max 25 chars

        doc = {
            "user_id": str(message.author.id),  # Twitch user ID (permanent)
            "username": message.author.name.lower(),
            "display_name": sanitized_display_name,
            "message": sanitized_message,
            "channel": message.channel.name,
            "timestamp": now,
            "hour": now_brt.hour  # Store hour in Brasília timezone (UTC-3)
        }

        try:
            await db.messages.insert_one(doc)
        except Exception as e:
            logger.error(f"Error saving message: {e}")

        await self.handle_commands(message)

    @commands.command(name="stats")
    async def stats_command(self, ctx):
        await ctx.send(f"@{ctx.author.name} Veja suas estatisticas em tossemideia.cloud/pererecos-stats")
