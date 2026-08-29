import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.chat import schemas as _chat_schemas  # noqa: F401 — ensures module import errors surface at boot
from app.common.database import AsyncSessionLocal
from app.common.exceptions import PairzaError
from app.config.settings import get_settings
from app.matchmaking.router import router as matchmaking_router
from app.moderation.router import router as moderation_router
from app.mysteries.router import router as mysteries_router
from app.rewards.router import router as rewards_router
from app.sessions import service as sessions_service
from app.sessions.router import router as sessions_router
from app.users.router import router as users_router
from app.websockets.router import router as websockets_router

settings = get_settings()
logger = logging.getLogger("pairza")

SWEEP_INTERVAL_SECONDS = 30


async def _background_sweeper() -> None:
    """Runs for the lifetime of the process: makes session expiry and the
    'expiring soon' warning proactive instead of only lazy-on-access, so a
    WebSocket-connected client gets `session.expiring` / `session.expired`
    even if nobody happens to hit a REST endpoint at the right moment."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await sessions_service.sweep_expired_sessions(db)
            async with AsyncSessionLocal() as db:
                await sessions_service.sweep_expiring_warnings(
                    db, timedelta(minutes=settings.SESSION_EXPIRING_WARNING_MINUTES)
                )
        except Exception:  # noqa: BLE001 — a bad sweep must never kill the loop
            logger.exception("background sweep failed")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_background_sweeper())
    yield
    task.cancel()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PairzaError)
async def pairza_error_handler(request: Request, exc: PairzaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(matchmaking_router)
app.include_router(mysteries_router)
app.include_router(sessions_router)
app.include_router(rewards_router)
app.include_router(moderation_router)
app.include_router(admin_router)
app.include_router(websockets_router)
