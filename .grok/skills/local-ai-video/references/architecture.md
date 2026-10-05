# Architecture

Platform root: `ai-video/`. Python 3.11+. Frontend: Next.js, TypeScript, Tailwind, shadcn/ui.

```
ai-video/
  backend/app/
    main.py
    config.py
    api/
    db/models.py
    providers/          # interfaces + implementations
    pipelines/          # story, scenes, orchestrator
    services/           # renderer, timeline, sfx, qc, gpu, storage
    workers/queue.py
  frontend/             # Next.js app (app router)
  configs/workflows/    # ComfyUI API-format JSON + node maps
  configs/openrouter_free_text_models.json
  configs/sfx_map.json
  tests/
  scripts/
  docker/
  projects/             # runtime; gitkeep only
  outputs/              # runtime; gitkeep only
  requirements.txt
  package.json          # frontend
  .env.example
  README.md
```

Checkpoint weights are not in git. Model filenames are env values.

## Providers

Interfaces in `backend/app/providers/base.py`. Implementations receive settings; pipelines depend on the interfaces.

| Interface | Implementation | Role |
| --- | --- | --- |
| `LLMProvider` | `OpenRouterLLMProvider` | Story, bible, prompts, lyrics |
| `ImageProvider` | `ComfyUIImageProvider` | Text-to-image and reference image |
| `VideoProvider` | `ComfyUIWanVideoProvider` | Short image-to-video clips |
| `MusicProvider` | `AceStepMusicProvider` | Local ACE-Step 1.5 |
| `TTSProvider` | `CommandTTSProvider` | Local CLI TTS, swappable |

Add a new model by adding a provider. Do not branch on model names inside pipelines.

`CommandTTSProvider` runs `TTS_COMMAND` with `{text}`, `{language}`, `{voice}`, `{output}` placeholders. Default command is empty. Tests use `FakeTTSProvider`, which writes a silent wav of the requested duration via the stdlib `wave` module.

## Environment

`ai-video/.env.example`:

```
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openrouter/free
OPENROUTER_CATALOG=live
OPENROUTER_SITE_URL=http://localhost:3000
OPENROUTER_APP_NAME=local-ai-video

COMFYUI_BASE_URL=http://127.0.0.1:8188
IMAGE_WORKFLOW=configs/workflows/image_api.json
IMAGE_WORKFLOW_MAP=configs/workflows/image_map.json
VIDEO_WORKFLOW=configs/workflows/wan_i2v_api.json
VIDEO_WORKFLOW_MAP=configs/workflows/wan_i2v_map.json
IMAGE_MODEL=
VIDEO_MODEL=wan2.1-1.3b
IMAGE_GEN_WIDTH=576
IMAGE_GEN_HEIGHT=1024

ACESTEP_BASE_URL=http://127.0.0.1:8001
ACESTEP_API_KEY=
MUSIC_MODEL=acestep-v15-turbo

TTS_COMMAND=
FFMPEG_PATH=ffmpeg
FFPROBE_PATH=ffprobe

OUTPUT_DIR=./outputs
PROJECT_DIR=./projects
DATABASE_URL=sqlite:///./ai-video.db
API_HOST=127.0.0.1
API_PORT=8100

DEFAULT_FPS=30
DEFAULT_WIDTH=1080
DEFAULT_HEIGHT=1920
WAN_CLIP_MIN_SECONDS=5
WAN_CLIP_MAX_SECONDS=10
WAN_BUDGET_RATIO=0.25
MAX_RETRIES=3
```

`IMAGE_MODEL` empty means "use the checkpoint already named in the workflow file".

## Project record

Create accepts: `content_type` (`horror` | `kids`), `topic`, `duration_seconds` or a preset, `aspect_ratio` (`9:16` | `16:9` | `1:1`), `resolution` (`720p` | `1080p`), `language` (`hi` | `en` | `hinglish`), `visual_style`, `voice` (`male` | `female` | `child` | `custom`), `custom_voice_id`, `music_mode` (`none` | `background` | `full_song`), `scene_count` (`auto` or an integer), `rights_confirmed` (bool, default false), `llm_model` (optional free-text id; default `OPENROUTER_MODEL`).

Duration presets: 30, 60, 120, 140, 180, 300, 600, 1200, plus custom seconds.

Delivery size from aspect ratio and resolution (scale at render time; generate smaller):

| Aspect | 720p | 1080p |
| --- | --- | --- |
| 9:16 | 720x1280 | 1080x1920 |
| 16:9 | 1280x720 | 1920x1080 |
| 1:1 | 720x720 | 1080x1080 |

Generation size stays at `IMAGE_GEN_WIDTH` x `IMAGE_GEN_HEIGHT` fitted to the aspect ratio (short side = min of those, long side proportional, both divisible by 8).

## Project folder

```
projects/{project_id}/
  story/story.json
  story/narration.txt
  story/youtube.json
  characters/{character_id}/reference.png
  characters/{character_id}/metadata.json
  scenes/{scene_id}/prompt.json
  scenes/{scene_id}/image.png
  scenes/{scene_id}/video.mp4
  scenes/{scene_id}/narration.wav
  scenes/{scene_id}/sfx/
  music/background.wav
  audio/narration.wav
  audio/final_mix.wav
  render/preview.mp4
  render/final.mp4
```

`project_id` is a uuid. Display names may be `project_001` style only in docs.

`youtube.json` includes `ai_assisted: true`, title, description, language, and a line that the video was made with AI tools.

## Tables

SQLAlchemy 2.0, SQLite. Foreign keys on.

- `projects` — creation fields, `status`, `error`, timestamps
- `stories` — project_id unique, title, hook, body, lyrics (nullable), full JSON
- `characters` — project_id, name, age, appearance, clothing, personality, style, seed, reference_path
- `locations` — project_id, name, description, lighting, mood
- `scenes` — project_id, index, start_time, end_time, duration, narration, dialogue, character_ids JSON, location_id, image_prompt, video_prompt, camera_motion, transition, sfx JSON, music_cue, generation_mode (`image` | `video`), status, approved
- `assets` — owner type/id, kind, path, sha256, seed, prompt
- `generation_jobs` — project_id, scene_id nullable, stage, status, attempts, run_after, error, payload JSON
- `audio_tracks` — project_id, scene_id nullable, kind (`narration` | `music` | `sfx` | `mix`), path, duration, gain
- `video_clips` — scene_id, path, duration, source (`ffmpeg` | `wan`)
- `renders` — project_id, kind (`preview` | `final`), path, width, height, fps, duration, status, errors JSON

## Project status

`DRAFT`, `PLANNING`, `GENERATING_CHARACTERS`, `GENERATING_IMAGES`, `GENERATING_VIDEO`, `GENERATING_MUSIC`, `GENERATING_TTS`, `ASSEMBLING`, `RENDERING`, `COMPLETED`, `FAILED`, `CANCELLED`

Scene status: `PENDING`, `GENERATING`, `READY`, `APPROVED`, `FAILED`

Job status: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`

## HTTP

Prefix `/api`. CORS for the Next.js origin.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/health` | Process up, db writable, ffmpeg found |
| GET | `/api/models` | Free OpenRouter text models. The filter is in `providers.md`. |
| GET | `/api/gpu` | VRAM total, used, utilization, temperature; nulls when unknown |
| GET | `/api/dashboard` | Counts, queue, recent renders, gpu |
| POST | `/api/projects` | Create `DRAFT` |
| GET | `/api/projects` | List |
| GET | `/api/projects/{id}` | Project + story + counts |
| GET | `/api/projects/{id}/status` | Status, stage, job |
| GET | `/api/projects/{id}/scenes` | Scenes |
| POST | `/api/projects/{id}/generate` | Enqueue full pipeline |
| POST | `/api/generate` | Create + enqueue. Body is the create fields. Returns project id immediately, not the mp4 |
| POST | `/api/projects/{id}/stages/{stage}` | Enqueue one stage: `story`, `characters`, `images`, `motion`, `music`, `voice`, `render` |
| POST | `/api/projects/{id}/render` | Enqueue render |
| POST | `/api/projects/{id}/cancel` | Cancel queued and running jobs |
| GET | `/api/projects/{id}/download` | File response for `render/final.mp4` or 404 |
| POST | `/api/scenes/{id}/regenerate` | Body `{ "target": "image" \| "video" \| "voice" \| "prompt" }` |
| POST | `/api/scenes/{id}/approve` | Mark `APPROVED` |
| POST | `/api/scenes/{id}/reject` | Back to `PENDING` |
| PATCH | `/api/scenes/{id}` | Edit prompts, narration, mode, sfx, camera, transition |

`POST /api/generate` does not block until the mp4 exists. The response includes `project_id`, `status_url`, and `download_url`. The worker fills the file.

## Queue

One worker loop in-process (asyncio task started on FastAPI lifespan). Claim with `UPDATE ... WHERE status='QUEUED' AND run_after <= now` in a transaction.

On startup, jobs left `RUNNING` go back to `QUEUED` with the error `interrupted`. Completed scene files are reused. Do not regenerate a character reference or an image whose asset sha256 matches the same prompt, seed, model, and reference image.

Backoff: `run_after = now + 2**attempts` seconds, attempts capped at `MAX_RETRIES`. Then the job and, if scene-scoped, the scene become `FAILED`. The project becomes `FAILED` only when a non-scene job exhausts retries or the user cancels. Sibling scenes continue.

## Logs

One JSON object per line: `project_id`, `job_id`, `scene_id`, `stage`, `event` (`started` | `completed` | `failed`), `duration_ms`, `status`, `error`.

Human line in the message field: `[IMAGE] scene_021 completed in 24.3s`.
