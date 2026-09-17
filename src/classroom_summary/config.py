from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_token: str
    database_url: str
    redis_url: str
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str
    ai_model: str
    timezone: str = "Asia/Bangkok"
    stream_maxlen: int = Field(default=100_000, gt=0)
    process_message_cap: int = Field(default=2_000, gt=0)
    ondemand_cache_ttl_seconds: int = Field(default=240, ge=180, le=300)
    ondemand_rate_limit_seconds: int = Field(default=30, gt=0)
    cron_lock_ttl_seconds: int = Field(default=1_800, gt=0)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
