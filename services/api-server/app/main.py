"""sigtrades api-server：认证/会员/内部契约/SaaS 配置。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings, validate_production_secrets
from app.routers import (
    admin,
    agent_connect,
    auth,
    config,
    internal,
    public,
    resend_inbound_webhook,
    schwab_oauth,
    stripe_webhook,
    subscriptions,
    users,
)
from app.services.membership_scheduler import membership_scheduler_loop
from app.services.seed import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api-server")


class AcceptLanguageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.language = (request.headers.get("accept-language") or "zh").split(",")[0].strip()[:8]
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    validate_production_secrets(settings)
    await init_db()
    sched = asyncio.create_task(membership_scheduler_loop())

    from app.services.realtime.redis_bus import redis_event_bus

    logger.info("api-server ready (SEED_DEMO=%s)", settings.SEED_DEMO)
    yield
    sched.cancel()
    await redis_event_bus.close()


app = FastAPI(title="sigtrades api-server", lifespan=lifespan)
app.add_middleware(AcceptLanguageMiddleware)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(agent_connect.router)
app.include_router(public.router)
app.include_router(users.router)
app.include_router(schwab_oauth.router)
app.include_router(config.router)
app.include_router(subscriptions.router)
app.include_router(admin.router)
app.include_router(internal.router)
app.include_router(stripe_webhook.router)
app.include_router(resend_inbound_webhook.router)

_releases = Path(settings.AGENT_RELEASES_DIR)
if _releases.is_dir():
    app.mount("/releases", StaticFiles(directory=str(_releases)), name="agent-releases")
    logger.info("agent releases: %s -> /releases/", _releases)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-server"}
