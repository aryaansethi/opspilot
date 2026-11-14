"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_engine, get_sessionmaker
from app.documents.router import router as documents_router
from app.evaluations.router import router as evaluations_router
from app.integrations.router import router as integrations_router
from app.investigations.router import router as investigations_router
from app.mcp.registry import sync_all
from app.search.router import router as search_router
from app.workspaces.router import router as workspaces_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if get_settings().environment != "test":
        # Best effort: register tools from reachable MCP servers; unreachable ones are retried
        # via POST /tools/sync.
        async with get_sessionmaker()() as db:
            await sync_all(db)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level, json=s.environment == "production")
    app = FastAPI(title="OpsPilot AI", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Workspace-Id", "Last-Event-ID"],
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith(f"{s.api_prefix}/auth"):
            response.headers["Cache-Control"] = "no-store"  # tokens must not be cached
        return response

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz() -> JSONResponse:
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            return JSONResponse({"status": "unavailable", "database": "down"}, 503)
        return JSONResponse({"status": "ok", "database": "up"})

    api = APIRouter(prefix=s.api_prefix)
    api.include_router(auth_router)
    api.include_router(workspaces_router)
    api.include_router(documents_router)
    api.include_router(search_router)
    api.include_router(integrations_router)
    api.include_router(investigations_router)
    api.include_router(evaluations_router)
    app.include_router(api)
    return app


app = create_app()
