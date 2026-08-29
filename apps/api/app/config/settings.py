"""
Central application configuration.

Every value here is overridable via environment variable (see .env.example
at the repo root). Nothing sensitive is hardcoded — secrets always come
from the environment so the same image can run in dev/staging/prod with
different .env files.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ---
    APP_NAME: str = "Pairza API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:pairza_dev_password@localhost:5432/pairza"
    )

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Auth / JWT ---
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- OAuth (Google) ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/auth/google/callback"

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # --- Session / game rules ---
    SESSION_DURATION_HOURS: int = 24
    SESSION_EXPIRING_WARNING_MINUTES: int = 60
    MATCH_COOLDOWN_DAYS: int = 21  # don't re-pair the same two strangers within this window
    MYSTERY_COOLDOWN_DAYS: int = 30  # don't re-serve the same mystery to a user within this window

    # --- Rate limiting ---
    RATE_LIMIT_MESSAGES_PER_MINUTE: int = 60
    RATE_LIMIT_AUTH_ATTEMPTS_PER_MINUTE: int = 10

    # --- Frontend URLs (for links in emails etc.) ---
    FRONTEND_URL: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
