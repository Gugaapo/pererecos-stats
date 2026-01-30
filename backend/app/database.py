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

    async def _create_indexes(self):
        messages = self.db.chat_messages
        await messages.create_index([("username", 1), ("timestamp", -1)])
        await messages.create_index([("timestamp", -1)])
        await messages.create_index([("username", 1), ("hour", 1)])
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
    def timeout_ms(self) -> int:
        return self._timeout_ms


db = DatabaseManager()
