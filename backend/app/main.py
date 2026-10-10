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
            conn.exec_driver_sql(
                "ALTER TABLE slides ADD COLUMN IF NOT EXISTS image_keys JSONB DEFAULT '[]'::jsonb"
            )
            conn.exec_driver_sql(
                "ALTER TABLE slides ALTER COLUMN image_key DROP NOT NULL"
            )
            # Backfill multi-image list from legacy single image_key
            conn.exec_driver_sql(
                """
                UPDATE slides
                SET image_keys = jsonb_build_array(image_key)
                WHERE image_key IS NOT NULL
                  AND (image_keys IS NULL OR image_keys = '[]'::jsonb)
                """
            )
            conn.exec_driver_sql(
                "ALTER TABLE slides ADD COLUMN IF NOT EXISTS motion_prompt TEXT"
            )
            conn.exec_driver_sql(
                "ALTER TABLE story_jobs ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(255)"
            )
            conn.exec_driver_sql(
                "ALTER TABLE story_jobs ADD COLUMN IF NOT EXISTS progress INTEGER NOT NULL DEFAULT 0"
            )
            conn.exec_driver_sql(
                "ALTER TABLE story_jobs ADD COLUMN IF NOT EXISTS detail TEXT"
            )
            conn.exec_driver_sql(
                "ALTER TABLE story_jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ"
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
        from app.services.wan_i2v import wan_i2v_status
        from app.services.wan_t2v import wan_t2v_status

        return {
            "status": "ok",
            "mock_tts": settings.use_mock_tts,
            "deepgram_configured": bool(settings.deepgram_api_key),
            "tts": {
                "deepgram_aura2": bool(settings.deepgram_api_key),
                "edge_free": True,
            },
            "wan_i2v": wan_i2v_status(),
            "wan_t2v": wan_t2v_status(),
        }

    @app.get(f"{settings.api_prefix}/models")
    def list_models() -> dict:
        from app.services.openrouter_catalog import load_catalog

        from app.services.gemini_llm import gemini_catalog_rows
        from app.services.openai_llm import openai_catalog_rows

        catalog = load_catalog(settings)
        openrouter = [{**row, "provider": row.get("provider") or "openrouter"} for row in catalog.models]
        return {
            "source": catalog.source,
            "default_model": catalog.default_model,
            "default_model_is_free": catalog.default_model in catalog.ids(),
            "key_configured": bool(settings.openrouter_api_key),
            "gemini_key_configured": bool(settings.gemini_api_key),
            "openai_key_configured": bool(settings.openai_api_key),
            "models": openai_catalog_rows(settings) + gemini_catalog_rows(settings) + openrouter,
        }

    @app.get(f"{settings.api_prefix}/gpu")
    def gpu_status() -> dict:
        from app.services.gpu import snapshot

        return snapshot(settings)

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
