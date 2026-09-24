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
    # A session's LENGTH is not configured here — it's derived from the
    # mystery's difficulty (see app/mysteries/difficulty.py). Old
    # SESSION_DURATION_HOURS / SESSION_EXPIRING_WARNING_MINUTES values left in
    # an existing .env are simply ignored.
    #
    # How often the background sweeper looks for sessions that just ran out of
    # time (or are about to). Sessions now last 5-30 minutes, so this needs to
    # be seconds, not the 30s it was when a session lasted a day.
    SESSION_SWEEP_INTERVAL_SECONDS: int = 5
    MATCH_COOLDOWN_DAYS: int = 21  # don't re-pair the same two strangers within this window
    MYSTERY_COOLDOWN_DAYS: int = 30  # don't re-serve the same mystery to a user within this window

    # --- Rate limiting ---
    RATE_LIMIT_MESSAGES_PER_MINUTE: int = 60
    RATE_LIMIT_AUTH_ATTEMPTS_PER_MINUTE: int = 10

    # --- Outbound email (app/common/email.py) — password reset / account recovery only ---
    # SMTP_HOST empty (the default) means "log the email instead of sending it": local dev and
    # this project's sandboxed build both work with zero setup. Set these for real delivery.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@pairza.app"
    SMTP_USE_TLS: bool = True
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Frontend URLs (for links in emails etc.) ---
    FRONTEND_URL: str = "http://localhost:3000"

    # --- Demo data credentials (scripts/seed_demo.py ONLY — never used at runtime, and
    # seed_demo.py itself refuses to run unless ENVIRONMENT=development) ---
    # These are intentionally predictable: they only ever populate a disposable local/demo
    # database. A REAL production admin account is never created from these defaults — see
    # scripts/create_admin.py, which reads ADMIN_EMAIL / ADMIN_PASSWORD from the environment
    # with no default at all.
    DEMO_USER_EMAIL: str = "demo@pairza.app"
    DEMO_USER_PASSWORD: str = "PairzaDemo123!"
    ADMIN_USER_EMAIL: str = "admin@pairza.app"
    ADMIN_USER_PASSWORD: str = "PairzaAdmin123!"
    SEED_USER_PASSWORD: str = "SeedPassword123!"

    # --- AI mystery generation (scripts/generate_mysteries.py) ---
    # Never used at request-serving time — only by the offline CLI script.
    # Leaving ANTHROPIC_API_KEY blank makes the script fail fast with a
    # clear message rather than a confusing HTTP error.
    ANTHROPIC_API_KEY: str = ""
    MYSTERY_GENERATOR_MODEL: str = "claude-sonnet-4-6"
    # If True, mysteries that pass every validation stage go straight to
    # PUBLISHED (playable immediately). If False, they stop at VALIDATED
    # and an admin must explicitly publish each one — see section 10 of
    # the spec for why a team might want either policy.
    MYSTERY_AUTO_PUBLISH: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
