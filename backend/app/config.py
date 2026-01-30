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
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "twitch_stats"
    api_root_path: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    # 7TV Configuration
    seventv_emote_set_id: str = "01HR3ABJ800007QJQMTQH1J05C"

    # CORS Configuration
    cors_origins: str = "*"  # Comma-separated list of origins, or "*" for all

    # Security Configuration
    health_check_token: str = ""  # Optional token for health endpoint protection
    mongodb_timeout_ms: int = 5000  # MongoDB operation timeout
    max_request_size: int = 1048576  # 1MB max request size
    enable_security_headers: bool = True

    # Logging
    log_security_events: bool = True

    @field_validator("mongodb_url")
    @classmethod
    def validate_mongodb_url(cls, v: str) -> str:
        """Validate MongoDB connection string format"""
        pattern = r"^mongodb(\+srv)?:\/\/"
        if not re.match(pattern, v):
            raise ValueError("Invalid MongoDB connection string format")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
