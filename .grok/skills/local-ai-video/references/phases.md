# Phases

Mark a phase done only when its tests pass. Use pytest from `ai-video/` with `python -m pytest`.

## 1. Skeleton

FastAPI app, settings, SQLite models, create/list/get project, `/api/health`, `/api/dashboard` with zero-safe counts, `/api/gpu` returning the monitor shape. Next.js shell with `/dashboard`, `/projects`, `/projects/new`, `/settings` reading the API. README: create venv, install requirements, copy `.env.example`, run uvicorn on port 8100, run `npm run dev`.

Tests: health, create project, dashboard counts, free-text catalog filter, `GET /api/models` serves that catalog.

## 2. OpenRouter planning

`OpenRouterLLMProvider` plus story and scene planner. `POST /api/projects/{id}/stages/story` enqueues planning. Fake provider in tests.

Tests: horror plan has all beats and chained `continues_from_index`; kids plan has non-empty original lyrics; scene count follows the duration table; 140s video-mode budget is within 20–40s; invalid JSON retries once.

## 3. ComfyUI images

Client and `ComfyUIImageProvider`. Workflow map patch. Job writes `image.png`. Fake HTTP in tests, including `node_errors` and a history payload with `images`.

Tests: prompt body contains the patched seed and text; download uses `filename`, `subfolder`, `type`; failed history fails the scene job only.

## 4. Character consistency

Bible rows, one reference image per character, scene jobs send the reference filename, unchanged appearance skips regeneration.

Tests: second run does not submit a second reference prompt; scene graph contains the uploaded reference name.

## 5. Wan

`ComfyUIWanVideoProvider` for `video` scenes. Clip seconds clipped to 5–10. `POST /free` is requested between the image stage and Wan.

Tests: image scenes do not submit the video workflow; a 140s plan submits Wan only until the budget is spent.

## 6. FFmpeg timeline

`VideoRenderer` argument builder and timeline fit from wav durations.

Tests: zoom and pan appear in the filter; duration uses the probed narration length; gap detection fails the gate; no literal `5` second default when timing is not fixed.

## 7. TTS

`CommandTTSProvider` and `FakeTTSProvider`. Per-scene wav, then concat into `audio/narration.wav`.

Tests: one failed scene does not delete another scene's wav; concat list order matches scene index.

## 8. ACE-Step

`AceStepMusicProvider` against the `/release_task` contract. Skip when `music_mode=none`.

Tests: request includes lyrics and `audio_duration`; status `2` fails the music job; horror background sends an instrumental prompt and empty lyrics.

## 9. Mix and SFX

Map cues, `adelay`, sidechain duck of music under narration.

Tests: filtergraph contains narration, music, and one sfx delay; missing optional sfx does not fail the mix.

## 10. Orchestrator

Wire `POST /api/generate` and stage endpoints to the queue. Cancel. Restart requeues `RUNNING` jobs. Resume skips existing files.

Tests: job order is planning, images, video, tts, music, render; cancel stops later jobs; a second run does not regenerate an existing image asset.

## 11. Tests and UI finish

Remaining routes in `frontend.md`. Scene patch, approve, reject, regenerate. Download endpoint. 30s horror end-to-end with fakes writing a tiny valid mp4 through the real FFmpeg renderer when `ffmpeg` exists, otherwise the argument list plus a skipped encode marked in the test.

Tests: API status flow, retry backoff schedule, quality gate blocks render when an image is missing, duration math.

## 12. Performance

Cache key is prompt + seed + model + reference hash. Document AMD setup in the README: ROCm/ComfyUI, do not install CUDA builds, ACE-Step `ACESTEP_LM_BACKEND=pt` and CPU offload, `POST /free` between stages, generate below delivery resolution.

Tests: cache hit does not call the image provider; README lists the AMD steps.

## README outline

After the phases that introduce them, the README must cover: install, AMD/ROCm, OpenRouter key and model id, ComfyUI, exporting the API workflow, Wan 2.1 1.3B, ACE-Step on port 8001, FFmpeg, backend, frontend, a 30s dry run with fakes, a 2:20 real run, and a troubleshooting list (missing compose file is not this app; Naratto compose lives in the repo `docker/` folder; this app's compose is `ai-video/docker`).

Troubleshooting entries to include once those pieces exist: OpenRouter 401, unknown model id, ComfyUI connection refused, `node_errors`, missing Wan nodes, ACE-Step status 2, vLLM failing on AMD, ffmpeg not on PATH, quality-gate error list, jobs stuck `RUNNING` after a crash (restart requeues them).
