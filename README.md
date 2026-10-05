# Naratto

**Learning video studio** — convert slides + narration scripts into professional educational MP4 videos.

**Stack:** React + TypeScript + MUI · FastAPI · PostgreSQL · Redis · Celery · FFmpeg · Deepgram TTS

## Features (MVP)

- Email/password auth (JWT access + httpOnly refresh cookie)
- Projects & multi-image slide upload
- Per-slide narration, voice, speed, transition, Ken Burns animation
- **Wan2.1 Image-to-Video** slide animation (AI motion from stills; mock offline, GPU Diffusers/CLI for real inference)
- Async Deepgram TTS (mock mode without API key)
- Background FFmpeg render (fade + concat timeline, subtitles, optional BGM)
- Download MP4 + signed media URLs for preview
- Original horror and kids stories from OpenRouter (`POST /api/v1/projects/{id}/story`). Set `OPENROUTER_API_KEY` in `.env`. Free text models are listed at `/api/v1/models`.

## Quick start (Docker — live reload)

```bash
# From repo root
cp .env.example .env
# Optional: set DEEPGRAM_API_KEY and TTS_MOCK=false for real voices

./scripts/dev-docker.sh
# or:
cd docker
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

| Service  | URL |
|----------|-----|
| Frontend (Vite HMR) | http://localhost:3000 |
| API docs (uvicorn --reload) | http://localhost:8000/docs |
| Health   | http://localhost:8000/health |

**Hot reload**

| Area | Behavior |
|------|----------|
| **Backend API** | `uvicorn --reload` on `backend/app/**` bind mount |
| **Frontend** | Vite HMR; edit `frontend/src/**` and the browser updates |
| **Celery workers** | `watchfiles` restarts the worker when `.py` files change |

Production-style (no reload, baked images):

```bash
cd docker
docker compose -f docker-compose.yml up --build
```

1. Register an account  
2. Create a project  
3. Upload slide images  
4. Enter narration per slide → **Generate voice** (or **Generate all voices**)  
5. Open **Export video** → **Generate video** → download MP4  

Without `DEEPGRAM_API_KEY`, TTS runs in **mock mode** (sine tones sized to estimated speech length) so the full pipeline still works offline.

### Wan2.1 Image-to-Video (AI Motion)

[Wan2.1](https://github.com/Wan-Video/Wan2.1) animates slide stills into short motion clips during export when a slide’s **Animation** is set to **AI Motion (Wan2.1 I2V)**.

> **Important:** Without a cloud key or GPU, you only get a FFmpeg zoom (mock). That is **not** real Wan video.

| Mode | When | Requirements |
|------|------|----------------|
| **fal.ai** (recommended) | `FAL_KEY` set, `WAN_I2V_BACKEND=auto` | Key from [fal.ai/wan-i2v](https://fal.ai/models/fal-ai/wan-i2v) |
| **Replicate** | `REPLICATE_API_TOKEN` set | [wavespeedai/wan-2.1-i2v-480p](https://replicate.com/wavespeedai/wan-2.1-i2v-480p) |
| **Diffusers** | CUDA + `WAN_I2V_BACKEND=diffusers` | `pip install -r backend/requirements-wan.txt` |
| **Mock zoom** | `WAN_I2V_MOCK=true` | Offline stand-in only — looks like Ken Burns |

```bash
# Real Wan2.1 via fal.ai (works on Mac / Docker without a local GPU)
# 1. Create a key: https://fal.ai/dashboard/keys
# 2. Put it in repo-root .env:
FAL_KEY=your_fal_key_here
WAN_I2V_MOCK=false
WAN_I2V_BACKEND=auto
WAN_I2V_RESOLUTION=480p

# 3. Restart stack
./scripts/dev-docker.sh -d
```

Real generation takes **1–4+ minutes per image**. Clips are cached under `uploads/{project_id}/i2v_cache/`.

Status: `GET /health` → `wan_i2v`, or `GET /api/v1/video/wan-i2v/status`.

## Local development (without full compose)

### Prerequisites

- Python 3.12+, Node 20+, PostgreSQL 16, Redis, FFmpeg

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://video:video@localhost:5432/video_creator
export REDIS_URL=redis://localhost:6379/0
export STORAGE_ROOT=./data
export TTS_MOCK=true
export SECRET_KEY=dev-secret-change-me-in-production-min-32

uvicorn app.main:app --reload --port 8000
```

Workers (separate terminals):

```bash
celery -A app.workers.celery_app.celery_app worker -Q tts,default -c 2 -l info
celery -A app.workers.celery_app.celery_app worker -Q render -c 1 -l info
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://localhost:8000`.

## Architecture

See [docs/design.md](docs/design.md) for the full system design.

```text
React → FastAPI → PostgreSQL
              ↘ Redis/Celery → worker-tts (Deepgram)
                             → worker-render (FFmpeg) → MP4
```

## API overview

| Area | Endpoints |
|------|-----------|
| Auth | `POST /api/v1/auth/register`, `login`, `refresh`, `logout` |
| Projects | `POST/GET/PATCH/DELETE /api/v1/projects` |
| Slides | `POST/GET .../slides`, `PATCH/DELETE /slides/{id}`, reorder |
| TTS | `POST /tts/generate`, `generate-batch`, `GET /tts/voices` |
| Video | `POST /video/render`, `GET /video/status/{id}`, `download/{id}` |
| Files | `GET /files/{key}?exp=&sig=` (signed) |

## Configuration

| Env | Default | Notes |
|-----|---------|--------|
| `DATABASE_URL` | local Postgres | SQLAlchemy URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker |
| `STORAGE_ROOT` | `./data` | Local media root |
| `DEEPGRAM_API_KEY` | empty | Enables real TTS |
| `TTS_MOCK` | auto if no key | Force mock speech |
| `WAN_I2V_MOCK` | `true` | FFmpeg stand-in instead of real Wan2.1 |
| `WAN_I2V_BACKEND` | `mock` | `mock` \| `diffusers` \| `cli` |
| `WAN_I2V_MODEL_ID` | I2V-14B-480P Diffusers | Hugging Face model id |
| `SECRET_KEY` | dev string | JWT + media HMAC |
| `CORS_ORIGINS` | localhost Vite | Comma-separated |

## License

MIT (or your choice).
