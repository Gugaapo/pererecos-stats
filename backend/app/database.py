from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import WriteConcern
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None
    _timeout_ms: int = 5000

    async def connect(self):
        settings = get_settings()
        self._timeout_ms = settings.mongodb_timeout_ms

        # Connection options for security and performance
        self.client = AsyncIOMotorClient(
            settings.mongodb_url,
            serverSelectionTimeoutMS=self._timeout_ms,
            connectTimeoutMS=self._timeout_ms,
            socketTimeoutMS=self._timeout_ms,
            maxPoolSize=50,
            minPoolSize=5,
            retryWrites=True,
        )
        self.db = self.client[settings.mongodb_db_name]
        await self._create_indexes()
        logger.info("Database connected with timeout: %dms", self._timeout_ms)

    async def backfill_platform_field(self) -> int:
        """Set platform=twitch on legacy documents missing the field."""
        try:
            result = await self.db.chat_messages.update_many(
                {"platform": {"$exists": False}},
                {"$set": {"platform": "twitch"}},
            )
            if result.modified_count:
                logger.info("Backfilled platform field on %d messages", result.modified_count)
            return result.modified_count
        except Exception as exc:
            logger.warning("Platform backfill skipped or incomplete: %s", exc)
            return 0

    async def _create_indexes(self):
        messages = self.db.chat_messages
        await messages.create_index([("username", 1), ("timestamp", -1)])
        await messages.create_index([("timestamp", -1)])
        await messages.create_index([("username", 1), ("hour", 1)])
        # Indexes for user_id - preserves stats across username changes
        await messages.create_index([("user_id", 1), ("timestamp", -1)])
        await messages.create_index([("user_id", 1), ("hour", 1)])
        # Platform-scoped indexes for multi-platform stats
        await messages.create_index([("platform", 1), ("username", 1), ("timestamp", -1)])
        await messages.create_index([("platform", 1), ("user_id", 1), ("timestamp", -1)])
        await messages.create_index([("platform", 1), ("timestamp", -1)])
        # Speeds up reply-graph / get_top_replies tagged aggregation
        await messages.create_index([("reply_to_user_id", 1), ("timestamp", -1)])
        await messages.create_index([("reply_to_username", 1), ("timestamp", -1)])
        await messages.create_index(
            [("message_id", 1)],
            unique=True,
            sparse=True,
            name="message_id_unique_sparse",
        )
        await messages.create_index([("removed", 1), ("timestamp", -1)])
        await messages.create_index([("username", 1), ("is_bot", 1), ("timestamp", -1)])

        moderation = self.db.moderation_events
        await moderation.create_index([("event_at", -1)])
        await moderation.create_index([("platform", 1), ("target_user_id", 1), ("event_at", -1)])
        await moderation.create_index([("platform", 1), ("moderator_user_id", 1), ("event_at", -1)])
        await moderation.create_index([("platform", 1), ("action", 1), ("event_at", -1)])
        await moderation.create_index(
            [("platform", 1), ("target_user_id", 1), ("event_at", 1)],
            name="moderation_target_event_at",
        )

        folhinha_events = self.db.folhinha_events
        await folhinha_events.create_index([("dedupe_key", 1)], unique=True)
        await folhinha_events.create_index([("kind", 1), ("event_at", -1)])
        await folhinha_events.create_index([("platform", 1), ("kind", 1), ("event_at", -1)])
        await folhinha_events.create_index([("actor_username", 1), ("kind", 1), ("event_at", -1)])
        await folhinha_events.create_index([("target_username", 1), ("kind", 1), ("event_at", -1)])
        await folhinha_events.create_index([("cookies_balance", 1), ("event_at", -1)])
        await folhinha_events.create_index([("kind", 1), ("cookies_delta", 1), ("event_at", -1)])

        user_totals = self.db.user_totals
        await user_totals.create_index([("platform", 1), ("user_id", 1)], unique=True)
        await user_totals.create_index([("platform", 1), ("message_count", -1)])
        await user_totals.create_index([("message_count", -1)])
        await user_totals.create_index([("platform", 1), ("username", 1), ("message_count", -1)])
        await user_totals.create_index([("username", 1), ("message_count", -1)])
        await user_totals.create_index([("display_name", 1)])
        await user_totals.create_index([("known_usernames", 1)])

        platform_hourly = self.db.platform_hourly_stats
        await platform_hourly.create_index([("platform", 1)], unique=True)

        smoke_sessions = self.db.smoke_sessions
        await smoke_sessions.create_index(
            [("platform", 1), ("user_id", 1), ("date", 1)], unique=True
        )
        await smoke_sessions.create_index([("date", 1)])
        await smoke_sessions.create_index([("platform", 1), ("date", 1)])

        # Speeds up smoke-session backfill (hour=16 filter + timestamp minute check)
        await messages.create_index([("hour", 1), ("timestamp", 1)])

        user_daily = self.db.user_daily_stats
        await user_daily.create_index(
            [("platform", 1), ("user_id", 1), ("date", 1)], unique=True
        )
        await user_daily.create_index([("platform", 1), ("date", 1)])
        await user_daily.create_index([("date", 1)])

        emote_catalog = self.db.emote_catalog
        await emote_catalog.create_index([("emote_id", 1)], unique=True)
        await emote_catalog.create_index([("emote_name", 1)])
        await emote_catalog.create_index([("emote_name_lower", 1)])
        await emote_catalog.create_index([("creator_username", 1)])

        emote_daily = self.db.emote_daily_stats
        await emote_daily.create_index(
            [("date", 1), ("platform", 1), ("emote_id", 1), ("user_id", 1)],
            unique=True,
        )
        await emote_daily.create_index([("emote_id", 1), ("date", 1)])
        await emote_daily.create_index([("platform", 1), ("date", 1)])
        await emote_daily.create_index([("emote_name_lower", 1), ("date", 1)])
        await emote_daily.create_index([("user_id", 1), ("date", 1)])

        famosinhos = self.db.famosinhos_daily
        await famosinhos.create_index(
            [("date", 1), ("platform", 1), ("user_id", 1), ("source", 1)],
            unique=True,
        )
        await famosinhos.create_index([("platform", 1), ("date", 1)])
        await famosinhos.create_index([("date", 1)])

        folhinha = self.db.folhinha_daily
        await folhinha.create_index(
            [("date", 1), ("platform", 1), ("user_id", 1)],
            unique=True,
        )
        await folhinha.create_index([("platform", 1), ("date", 1)])
        await folhinha.create_index([("date", 1)])

        maria = self.db.maria_daily
        await maria.create_index(
            [("date", 1), ("platform", 1), ("user_id", 1)],
            unique=True,
        )
        await maria.create_index([("platform", 1), ("date", 1)])
        await maria.create_index([("date", 1)])

        escritor = self.db.escritor_roubado_daily
        await escritor.create_index(
            [("date", 1), ("platform", 1), ("user_id", 1)],
            unique=True,
        )
        await escritor.create_index([("platform", 1), ("date", 1)])
        await escritor.create_index([("date", 1)])

        logger.info("Database indexes created")

    async def disconnect(self):
        if self.client:
            self.client.close()
            logger.info("Database disconnected")

    @property
    def messages(self):
        return self.db.chat_messages

    @property
    def feedback(self):
        return self.db.feedback

    @property
    def user_totals(self):
        return self.db.user_totals

    @property
    def platform_hourly_stats(self):
        return self.db.platform_hourly_stats

    @property
    def smoke_sessions(self):
        return self.db.smoke_sessions

    @property
    def user_daily_stats(self):
        return self.db.user_daily_stats

    @property
    def emote_catalog(self):
        return self.db.emote_catalog

    @property
    def emote_daily_stats(self):
        return self.db.emote_daily_stats

    @property
    def famosinhos_daily(self):
        return self.db.famosinhos_daily

    @property
    def folhinha_daily(self):
        return self.db.folhinha_daily

    @property
    def maria_daily(self):
        return self.db.maria_daily

    @property
    def escritor_roubado_daily(self):
        return self.db.escritor_roubado_daily

    @property
    def moderation_events(self):
        return self.db.moderation_events

    @property
    def folhinha_events(self):
        return self.db.folhinha_events

    @property
    def timeout_ms(self) -> int:
        return self._timeout_ms


db = DatabaseManager()
