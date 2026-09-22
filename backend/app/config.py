from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache
import re


class Settings(BaseSettings):
    twitch_oauth_token: str = ""
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    twitch_refresh_token: str = ""
    twitch_channel: str = "omeiaum"
    kick_enabled: bool = False
    kick_channel: str = "meiaum"
    kick_chatroom_id: int = 0
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "twitch_stats"
    api_root_path: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    # 7TV Configuration
    seventv_emote_set_id: str = "01HR3ABJ800007QJQMTQH1J05C"

    # CORS Configuration (comma-separated origins; avoid "*" in production)
    cors_origins: str = "https://tossemideia.cloud"

    # Security Configuration
    health_check_token: str = ""  # Optional token for health endpoint protection
    mongodb_timeout_ms: int = 30000  # MongoDB operation timeout
    max_request_size: int = 1048576  # 1MB max request size
    enable_security_headers: bool = True

    # Logging
    log_security_events: bool = True

    # Subathon timer (BRT)
    subathon_start: str = "2026-09-06T15:00:00-03:00"
    subathon_placeholder_seconds: int = 259200
    # First live that counts for ingest latch (usually same as subathon_start).
    subathon_min_stream_start: str = "2026-09-06T15:00:00-03:00"

    # Public MeiaUm timer feed (vinnytasso) — primary ends_at/state source
    timer_feed_enabled: bool = True
    timer_feed_url: str = "https://meiaum.vinnytasso.com.br/api/v1/timer"
    timer_poll_seconds: int = 60
    timer_snapshot_heartbeat_seconds: int = 300
    timer_stale_seconds: int = 180

    # Pixie.gg — optional money webhooks + marathon fallback
    pixie_enabled: bool = True
    pixie_api_token: str = ""
    pixie_creator_id: str = ""
    pixie_webhook_secret: str = ""
    pixie_base_url: str = "https://ws.pixie.gg"
    pixie_poll_seconds: int = 60
    pixie_snapshot_heartbeat_seconds: int = 300
    pixie_timer_stale_seconds: int = 180
    pixie_webhook_tolerance_seconds: int = 300
    subathon_pause_credit_tolerance_seconds: int = 60

    @field_validator("mongodb_url")
    @classmethod
    def validate_mongodb_url(cls, v: str) -> str:
        """Validate MongoDB connection string format"""
        pattern = r"^mongodb(\+srv)?:\/\/"
        if not re.match(pattern, v):
            raise ValueError("Invalid MongoDB connection string format")
        return v

    @field_validator("pixie_creator_id")
    @classmethod
    def validate_pixie_creator_id(cls, v: str) -> str:
        if not v:
            return v
        if not re.match(r"^cr_[A-Za-z0-9_-]{22}$", v):
            raise ValueError("pixie_creator_id must match ^cr_[A-Za-z0-9_-]{22}$")
        return v

    @property
    def is_timer_configured(self) -> bool:
        return self.timer_feed_enabled and bool(self.timer_feed_url)

    @property
    def is_pixie_configured(self) -> bool:
        return (
            self.pixie_enabled
            and bool(self.pixie_api_token)
            and bool(self.pixie_creator_id)
        )

    @property
    def is_pixie_webhook_configured(self) -> bool:
        return bool(self.pixie_webhook_secret)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
