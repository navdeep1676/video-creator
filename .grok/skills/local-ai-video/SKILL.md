---
name: local-ai-video
description: >
  Build and extend the local-first horror and kids-cartoon video platform
  (FastAPI, SQLite, Next.js, ComfyUI, Wan 2.1, ACE-Step) with OpenRouter, Gemini,
  or OpenAI for story text. Use when the user runs /local-ai-video, or asks to implement,
  continue, debug, or document the ai-video app, its story or scene planner,
  character bible, ComfyUI images, Wan clips, ACE-Step music, TTS, FFmpeg
  timeline, job queue, or dashboard.
---

# Local AI video platform

Build this platform inside the existing Naratto app: `backend/` and `frontend/`. Do not create a second app under `ai-video/`. Keep Naratto slide projects, auth, and the dashboard working. Story planning uses the same users, projects, and `/api/v1` routes.

Read `references/phases.md` and implement the next phase that is not done. Finish its tests before starting the next phase. If the user asked to build or continue the platform, keep going through later phases in this session until a phase fails or all phases are done. Do not write every phase in one untested dump.

Contracts live in the reference files. Do not restate them elsewhere.

- Product, data, HTTP, and folder layout: `references/architecture.md`
- Provider calls (OpenRouter, ComfyUI, Wan, ACE-Step, TTS, GPU): `references/providers.md`
- Story, scenes, timeline, audio, validation: `references/pipeline.md`
- UI routes and controls: `references/frontend.md`
- Phase gates: `references/phases.md`

## Rules that override the rest of the prompt

- LLM calls go through `LLMProvider`. `OpenRouterLLMProvider` handles OpenRouter ids. `GeminiLLMProvider` handles ids that start with `gemini-` and `GEMINI_API_KEY`. `OpenAILLMProvider` handles `gpt-`, `o`-series, and `chatgpt-` ids with `OPENAI_API_KEY`. `LocalLLMProvider` handles `local/` ids on an OpenAI-compatible server (`LOCAL_LLM_BASE_URL`). Do not add the Ollama Python package, a local Qwen process, or another vendor SDK.
- Image, video, music, and FFmpeg stay local. Do not send images, clips, or audio to a paid cloud generator.
- Do not assume NVIDIA or CUDA. Do not call `nvidia-smi`. Target AMD RX 9060 XT 16GB, 64GB RAM, ROCm/ComfyUI.
- Never load the image model, Wan, and ACE-Step at the same time. Run the GPU stages in `references/providers.md` and unload between them.
- Workflows are ComfyUI API-format JSON files under `backend/configs/workflows/`. Patch inputs through the mapping file. Do not invent node graphs or ComfyUI routes.
- Stories and kids lyrics must be original. Do not scrape YouTube or copy copyrighted lyrics. Use pasted lyrics only when the request sets `rights_confirmed: true`.
- Do not download copyrighted SFX or music. SFX paths are configurable and may be missing; a missing file is a warning, not a crash, unless the user marked that cue required.
- Secrets stay in the repo `.env`, never in git. Document new variables in `.env.example`.
- Paths must work on macOS, Linux, and Windows. No hardcoded drive letters.
- Generation is asynchronous. Jobs live in SQLite and resume after restart. A failed scene retries only that scene (`max_retries = 3`, exponential backoff).
- Tests use fakes for OpenRouter, ComfyUI, and ACE-Step. The 30-second end-to-end test must not call the GPU.
- Before a final render, run the quality checks in `references/pipeline.md`. On failure, do not write `final.mp4`; return the exact errors.

## While implementing

Match the surrounding Naratto style. Prefer real FastAPI, SQLAlchemy, and FFmpeg argument builders over stubs. A provider may raise `ProviderUnavailable` when its process is down; the job stores that error and stays retryable. Do not fake a successful image, clip, or song.

After each phase, run that phase's tests from `backend/`, fix failures, and update the repo `README.md` only for setup steps that phase introduced.
