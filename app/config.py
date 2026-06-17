"""
Application configuration via pydantic-settings.
All values are read from environment variables / .env file.
Never hardcode secrets — only defaults for non-sensitive dev config.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, env_settings, dotenv_settings

    # ── Database ────────────────────────────────────────────────────────────
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 3600

    # ── Redis ───────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_MAX_CONNECTIONS: int = 20

    # ── JWT / Auth ──────────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # ── File Upload ─────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 80
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/webp,image/avif,image/heic"
    THUMBNAIL_SIZE: str = "512,256"

    # ── CORS ────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173"

    # ── Application ─────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    APP_NAME: str = "Tour360API"
    API_VERSION: str = "v1"
    BASE_URL: str = "http://localhost:8000"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"   # "text" or "json"

    # ── Rate Limiting ───────────────────────────────────────────────────────
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REGISTER: str = "3/hour"
    RATE_LIMIT_UPLOAD: str = "20/hour"
    RATE_LIMIT_CACHE_CLEAR: str = "10/hour"

    # ── Cache ───────────────────────────────────────────────────────────────
    CACHE_TTL_TOUR_LIST: int = 86400      # 24 hours — tour list rarely changes
    CACHE_TTL_TOUR_DETAIL: int = 86400    # 24 hours — full tour + scenes + links
    CACHE_TTL_SCENE: int = 86400          # 24 hours — individual scene data
    CACHE_TTL_ADMIN: int = 300            # 5 minutes — admin views need fresher data
    CACHE_TTL_UPLOAD: int = 60            # 1 minute — upload status (short, polling)

    # ── Observability ───────────────────────────────────────────────────────
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # ── Derived / computed ──────────────────────────────────────────────────
    @property
    def allowed_image_types_list(self) -> List[str]:
        return [t.strip() for t in self.ALLOWED_IMAGE_TYPES.split(",")]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def thumbnail_size(self) -> tuple[int, int]:
        w, h = self.THUMBNAIL_SIZE.split(",")
        return (int(w), int(h))

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    # ── Production validators ───────────────────────────────────────────────

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_long(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    @model_validator(mode="after")
    def production_guard(self) -> "Settings":
        """Fail fast if production is misconfigured — don't run insecurely."""
        if self.ENVIRONMENT != "production":
            return self

        # SECRET_KEY must be strong in production
        if len(self.SECRET_KEY) < 64:
            raise ValueError(
                "SECRET_KEY must be at least 64 characters in production. "
                "Generate with: python -c \"import secrets; print(secrets.token_hex(64))\""
            )

        # CORS must not have wildcards or localhost in production
        for origin in self.cors_origins_list:
            if origin == "*":
                raise ValueError("CORS_ORIGINS cannot contain '*' in production")
            if "localhost" in origin or "127.0.0.1" in origin:
                raise ValueError(
                    f"CORS_ORIGINS contains '{origin}' — remove localhost origins in production"
                )

        # DEBUG must be off
        if self.DEBUG:
            raise ValueError("DEBUG must be false in production")

        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — call this everywhere."""
    return Settings()


# Trigger reload for .env change
settings = get_settings()
