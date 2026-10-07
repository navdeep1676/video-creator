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

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/free"
    openrouter_catalog: str = "live"
    openrouter_site_url: str = "http://localhost:3000"
    openrouter_app_name: str = "Naratto"
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-3.5-flash"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-mini"
    # OpenAI-compatible local server. Ollama uses http://127.0.0.1:11434/v1.
    local_llm_base_url: str = "http://127.0.0.1:11434/v1"
    local_llm_model: str = ""
    local_llm_api_key: str = ""
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_timeout_s: float = 900
    comfyui_poll_s: float = 2
    image_workflow: str = "configs/workflows/qwen_image_2_1_t2i.json"
    image_workflow_map: str = "configs/workflows/qwen_image_2_1_t2i.map.json"
    image_model: str = "qwen_image_2.1_int8_convrot.safetensors"
    image_clip: str = "qwen3vl_8b_int8_convrot.safetensors"
    image_vae: str = "qwen_image_2.1_vae_bf16.safetensors"
    image_steps: int = 25
    image_cfg: float = 1.0
    image_max_side: int = 1024
    wan_budget_ratio: float = 0.25
    wan_clip_min_seconds: float = 5
    wan_clip_max_seconds: float = 10
    acestep_base_url: str = "http://127.0.0.1:8001"
    acestep_api_key: str = ""
    music_model: str = "acestep-v15-turbo"
    acestep_thinking: bool = False
    acestep_timeout_s: float = 900
    acestep_poll_s: float = 2

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

    # Wan2.1 Image-to-Video (https://github.com/Wan-Video/Wan2.1)
    wan_i2v_enabled: bool = True
    # auto | fal | replicate | diffusers | cli | mock
    # auto picks fal → replicate → CUDA diffusers → cli
    wan_i2v_backend: str = "auto"
    # Force FFmpeg zoom stand-in (NOT real AI). Leave false for real Wan via API/GPU.
    wan_i2v_mock: bool = False
    # fal.ai (recommended without local GPU): https://fal.ai/models/fal-ai/wan-i2v
    fal_key: str = ""
    fal_wan_i2v_endpoint: str = "fal-ai/wan-i2v"
    # Replicate alternative: https://replicate.com/wavespeedai/wan-2.1-i2v-480p
    replicate_api_token: str = ""
    replicate_wan_model: str = "wavespeedai/wan-2.1-i2v-480p"
    # Diffusers model ids (local CUDA only)
    wan_i2v_model_id: str = "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers"
    wan_i2v_resolution: str = "480p"  # 480p | 720p
    wan_i2v_num_frames: int = 81  # ~5s at 16 fps
    wan_i2v_guidance_scale: float = 5.0
    wan_i2v_num_inference_steps: int = 30
    wan_i2v_acceleration: str = "regular"  # fal: none | regular
    wan_i2v_prompt_expansion: bool = False
    wan_i2v_seed: int = 42
    wan_i2v_device: str = "auto"  # auto | cuda | cpu
    wan_i2v_offload: bool = True  # CPU offload / t5_cpu for lower VRAM
    wan_i2v_timeout_s: int = 3600
    wan_i2v_default_prompt: str = (
        "Subtle natural motion, gentle camera drift, cinematic lighting, high quality, smooth animation"
    )
    wan_i2v_negative_prompt: str = (
        "Bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, "
        "images, static, overall gray, worst quality, low quality, JPEG compression residue, ugly, "
        "incomplete, extra fingers, poorly drawn hands, poorly drawn faces, deformed, disfigured, "
        "misshapen limbs, fused fingers, still picture, messy background, three legs, many people "
        "in the background, walking backwards"
    )
    # CLI backend: path to cloned Wan2.1 repo generate.py and downloaded I2V checkpoint dir
    wan_i2v_cli_script: str = ""
    wan_i2v_ckpt_dir: str = ""
    wan_i2v_python: str = "python"

    # Wan2.1 Text-to-Video 1.3B. Local Diffusers or official generate.py. No ComfyUI.
    # https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B-Diffusers
    wan_t2v_enabled: bool = True
    # auto | diffusers | cli | mock
    wan_t2v_backend: str = "auto"
    wan_t2v_mock: bool = False
    wan_t2v_model_id: str = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
    wan_t2v_width: int = 832
    wan_t2v_height: int = 480
    wan_t2v_num_frames: int = 81  # 4n+1, ~5s at 16 fps
    wan_t2v_guidance_scale: float = 6.0  # official 1.3B recommendation
    wan_t2v_flow_shift: float = 8.0
    wan_t2v_num_inference_steps: int = 50
    wan_t2v_seed: int = 42
    wan_t2v_device: str = "auto"  # auto | cuda | cpu (ROCm PyTorch uses cuda)
    wan_t2v_offload: bool = True
    wan_t2v_timeout_s: int = 3600
    wan_t2v_default_prompt: str = (
        "Cinematic motion, natural movement, detailed scene, smooth animation"
    )
    wan_t2v_negative_prompt: str = (
        "Bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, "
        "images, static, overall gray, worst quality, low quality, JPEG compression residue, ugly, "
        "incomplete, extra fingers, poorly drawn hands, poorly drawn faces, deformed, disfigured, "
        "misshapen limbs, fused fingers, still picture, messy background, three legs, many people "
        "in the background, walking backwards"
    )
    # Official repo weights (not the Diffusers folder) and generate.py. Empty script falls back to WAN_I2V_CLI_SCRIPT.
    wan_t2v_ckpt_dir: str = ""
    wan_t2v_cli_script: str = ""
    wan_t2v_python: str = ""

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

    @property
    def use_mock_wan_i2v(self) -> bool:
        """True only when user explicitly opted into mock zoom (not real AI)."""
        if not self.wan_i2v_enabled:
            return True
        if self.wan_i2v_mock:
            return True
        if (self.wan_i2v_backend or "").strip().lower() == "mock":
            return True
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
