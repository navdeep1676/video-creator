from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Naratto"
    environment: str = "development"  # development | production
    api_prefix: str = "/api/v1"
    secret_key: str = "dev-secret-change-me-in-production-min-32-chars"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    media_token_ttl_seconds: int = 600

    database_url: str = "postgresql+psycopg://video:video@localhost:5432/video_creator"
    redis_url: str = "redis://localhost:6379/0"

    storage_root: str = "./data"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    deepgram_api_key: str = ""
    deepgram_base_url: str = "https://api.deepgram.com/v1/speak"
    tts_mock: bool = False  # force mock TTS even if key present

    max_image_bytes: int = 10 * 1024 * 1024
    max_video_upload_bytes: int = 200 * 1024 * 1024  # 200 MB for clipper source
    max_clipper_frames: int = 50
    max_slides_per_project: int = 50
    max_images_per_slide: int = 12
    max_video_duration_s: int = 20 * 60
    max_user_storage_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GB
    default_duration_ms: int = 5000
    fade_s: float = 0.5
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 30
    ken_burns_zoom_end: float = 1.15
    feature_bgm: bool = True
    default_voice: str = "edge-en-ava"

    celery_task_always_eager: bool = False
    render_hard_limit_s: int = 1800
    render_soft_limit_s: int = 1700
    visibility_timeout_s: int = 3600
    stuck_job_grace_s: int = 120
    keep_completed_jobs: int = 3

    cookie_secure: bool | None = None  # None = auto (False in development)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def use_secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment != "development"

    @property
    def use_mock_tts(self) -> bool:
        return self.tts_mock or not self.deepgram_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
