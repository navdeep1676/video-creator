from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.utils.exceptions import AppError


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    Path(settings.storage_root).mkdir(parents=True, exist_ok=True)
    # Auto-create tables for MVP (Alembic still provided for prod path)
    Base.metadata.create_all(bind=engine)
    # Lightweight additive migrations for existing DBs
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE narrations ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(255)"
            )
    except Exception:
        pass
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "mock_tts": settings.use_mock_tts,
            "deepgram_configured": bool(settings.deepgram_api_key),
            "tts": {
                "deepgram_aura2": bool(settings.deepgram_api_key),
                "edge_free": True,
            },
        }

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
