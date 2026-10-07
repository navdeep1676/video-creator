# Providers

Call only the endpoints below. If a live server disagrees, trust `GET /object_info` or that server's own docs over this file, and update the workflow map. Do not invent a replacement route.

## OpenRouter

`POST {OPENROUTER_BASE_URL}/chat/completions`

Headers: `Authorization: Bearer {OPENROUTER_API_KEY}`, `Content-Type: application/json`, optional `HTTP-Referer: {OPENROUTER_SITE_URL}`, `X-Title: {OPENROUTER_APP_NAME}`.

Body:

```json
{
  "model": "openrouter/free",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "temperature": 0.7,
  "response_format": {
    "type": "json_schema",
    "json_schema": {"name": "story_plan", "strict": true, "schema": {}}
  }
}
```

Read `choices[0].message.content`. Parse JSON. Validate with Pydantic. On invalid JSON or schema mismatch, resend once with the error appended. If the HTTP status is 404 or the body says the model is unknown, `GET {OPENROUTER_BASE_URL}/models`, run the free-text filter below, and fail with those ids. Do not silently switch models.

If `response_format` is rejected (400), retry that call with `{"type": "json_object"}` and the schema printed in the system message.

OpenRouter is remote, so it is not a local GPU stage. Do not start ComfyUI or ACE-Step during a story call.

## Gemini

Story model ids that match `gemini-[A-Za-z0-9._-]+` use `GeminiLLMProvider` instead of OpenRouter.

`POST {GEMINI_BASE_URL}/models/{model}:generateContent`

Header: `x-goog-api-key: {GEMINI_API_KEY}`.

Body: `systemInstruction.parts[0].text`, one user `contents` entry, and `generationConfig` with `temperature` 0.7, `maxOutputTokens` 32768, `responseMimeType` `application/json`, and `responseJsonSchema` set to the story schema. If that schema is rejected with HTTP 400, retry the same call without `responseJsonSchema` and print the schema in the system text.

Read text from `candidates[0].content.parts`, skipping parts with `thought: true`. Parse JSON. On invalid JSON, resend once with the error appended. Do not silently switch models.

Missing `GEMINI_API_KEY` raises `ProviderUnavailable` before the HTTP call. `GET /api/v1/models` still lists the Gemini text models. `GEMINI_MODEL` defaults to `gemini-3.5-flash`. A custom id in that variable is added to the catalog when it matches the Gemini id pattern.

Gemini is remote, so it is not a local GPU stage.

## OpenAI

Story model ids that match `gpt-…`, `o` plus a digit (`o3`, `o4-mini`), or `chatgpt-…` use `OpenAILLMProvider`.

`POST {OPENAI_BASE_URL}/chat/completions`

Header: `Authorization: Bearer {OPENAI_API_KEY}`.

Body matches the OpenRouter chat body: `model`, system and user messages, `temperature` 0.7, and `response_format` `json_schema`. If HTTP 400 mentions the schema or `temperature`, retry once without the rejected field. Schema fallback uses `{"type": "json_object"}` and prints the schema in the system message.

Read `choices[0].message.content`. A `refusal` is an invalid reply and retries once. Parse JSON. On invalid JSON, resend once with the error appended. Do not silently switch models.

Missing `OPENAI_API_KEY` raises `ProviderUnavailable` before the HTTP call. `GET /api/v1/models` still lists the OpenAI text models. `OPENAI_MODEL` defaults to `gpt-5.4-mini`. A custom id in that variable is added to the catalog when it matches the OpenAI id pattern.

OpenAI is remote, so it is not a local GPU stage.

## Local model

Story model ids that start with `local/` use `LocalLLMProvider`. The id `local/qwen2.5:7b` calls the model `qwen2.5:7b`.

`POST {LOCAL_LLM_BASE_URL}/chat/completions`

Default base is `http://127.0.0.1:11434/v1` (Ollama). LM Studio is `http://127.0.0.1:1234/v1`. No API key. When `LOCAL_LLM_API_KEY` is set, send `Authorization: Bearer`.

Body matches the OpenAI chat body. On HTTP 400 for `response_format` or `temperature`, retry once without the rejected field. Ollama (`11434` in the base URL) also gets `keep_alive: 0` so the model leaves VRAM before ComfyUI, Wan, or ACE-Step.

`GET {LOCAL_LLM_BASE_URL}/models` fills the Local group. A stopped server leaves the group empty and does not fail the rest of `GET /api/v1/models`. `LOCAL_LLM_MODEL` is listed even when the server is down.

A connection error raises `ProviderUnavailable` and names the base URL. Do not download a model from this app.

Missing `OPENROUTER_API_KEY` raises `ProviderUnavailable` on chat calls. Listing models does not need a key. Tests inject a fake that returns fixture JSON.

### Free text catalog

`GET {OPENROUTER_BASE_URL}/models` is the source of selectable LLM ids. `is_free_text_model` in `backend/app/providers/openrouter_catalog.py` is the only filter. A model is included only when all of these hold:

- `pricing.prompt` and `pricing.completion` both parse as the number 0. `-1` means variable router pricing and is not free.
- `architecture.output_modalities` is exactly text. Drop models that also output audio, image, or video.
- `expiration_date` is empty, or it is today or later.

Keep `openrouter/free` when it passes. It is the free-model router, not a single checkpoint.

`GET /api/models` applies this filter to the live catalog. If that request fails, serve `configs/openrouter_free_text_models.json`. `scripts/refresh_openrouter_free_models.py` rewrites that file with the same filter. Do not keep a second hand-written id list.

`OPENROUTER_MODEL` defaults to `openrouter/free`. A project `llm_model` must be an id from the catalog being served. Chat completions still send that exact id.

## ComfyUI

Base: `COMFYUI_BASE_URL` (default `http://127.0.0.1:8188`).

| Call | Use |
| --- | --- |
| `GET /system_stats` | Devices, `vram_total`, `vram_free` |
| `GET /object_info` | Confirm node class types exist before the first real run |
| `GET /models/{folder}` | List checkpoints when `IMAGE_MODEL` must be written into the graph |
| `POST /upload/image` | Multipart field `image`; optional `type=input`, `overwrite=true`. Response `name`, `subfolder`, `type` |
| `POST /prompt` | Body `{"prompt": <api graph>, "client_id": "<uuid>"}`. Response `prompt_id`, `number`, or `error` + `node_errors` |
| `GET /history/{prompt_id}` | Outputs after completion |
| `GET /view?filename&subfolder&type` | Download bytes |
| `GET /queue` | `queue_running`, `queue_pending` |
| `POST /interrupt` | Stop the running graph |
| `POST /free` | Body `{"unload_models": true, "free_memory": true}` |
| `WS /ws?clientId=` | `execution_start`, `executing`, `progress`, `execution_error`, `execution_success` |

Poll `GET /history/{prompt_id}` when the socket drops. History outputs are keyed by node id. Read whichever of `images`, `gifs`, `videos`, `audio` is present. Download each file with `GET /view`.

API graph shape (one node):

```json
{"3": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20, "cfg": 7, "model": ["4", 0]}}}
```

Export the graph from ComfyUI (API format), save it under `configs/workflows/`, and ship a map file:

```json
{
  "checkpoint": "4.inputs.ckpt_name",
  "positive": "6.inputs.text",
  "negative": "7.inputs.text",
  "seed": "3.inputs.seed",
  "width": "5.inputs.width",
  "height": "5.inputs.height",
  "reference_image": "10.inputs.image"
}
```

Keys absent from a graph are skipped. `reference_image` is the uploaded filename. Set `checkpoint` only when `IMAGE_MODEL` is non-empty.

Client methods: `submit`, `wait`, `download`, `unload`. Retries belong to the job queue, not an inner infinite loop. One ComfyUI attempt may retry a dropped connection twice.

`POST /free` after the image stage and after the Wan stage, before the next GPU model loads.

## Wan

`ComfyUIWanVideoProvider` uses `VIDEO_WORKFLOW` (image-to-video). Same client as images.

- Input image is the scene image, uploaded first.
- `length` / frames come from the map. Frame count = `clip_seconds * fps`, clipped to `WAN_CLIP_MIN_SECONDS`..`WAN_CLIP_MAX_SECONDS`. Default range is 5–10 seconds. Do not ask Wan for the whole video.
- Model name field is set from `VIDEO_MODEL` only when the map has `model`.
- Only scenes with `generation_mode=video` call this provider.

If `/object_info` has no Wan node classes named in the workflow, fail that job with "Wan workflow nodes are not installed" and leave image scenes runnable.

## ACE-Step 1.5

Official local server (`python -m acestep.api_server`), default port **8001**. Confirm against the installed `docs/en/API.md` before changing paths. The current contract:

1. `POST /release_task` JSON. Read `data.task_id`. Wrapper is `{data, code, error, timestamp}`.
2. `POST /query_result` with `{"task_id_list": ["..."]}`. `data[].status`: `0` running, `1` succeeded, `2` failed. `result` is a JSON **string**; parse it. Audio URL is `file`.
3. `GET /v1/audio?path=` to download. Request `audio_format=wav` when the installed server accepts it; otherwise download the given file and transcode with FFmpeg to `music/background.wav`.

Fields to send: `prompt` (style), `lyrics` (empty for instrumental horror beds), `audio_duration` (project duration, clamped to the server range 10–600), `model` from `MUSIC_MODEL`, `thinking` false on 16GB unless a settings flag says otherwise, `batch_size` 1, `vocal_language` from the project language (`hi` → `zh` is wrong; send `hi` only if `/` docs list it, else `en` and keep Hindi lyrics in the `lyrics` field).

Do not call `/create_random_sample`. That returns canned examples.

`GET /health` for readiness. Optional `Authorization: Bearer {ACESTEP_API_KEY}` when set.

AMD: the default LM backend `vllm` is CUDA-oriented. Document `ACESTEP_LM_BACKEND=pt` and `ACESTEP_OFFLOAD_TO_CPU=true` for the RX 9060 XT. Do not start vLLM in this app.

Unload ComfyUI (`POST /free`) before the first ACE-Step request of a project.

## TTS

`TTSProvider.synthesize(text, language, voice, output_path) -> duration_seconds`.

`CommandTTSProvider` formats `TTS_COMMAND` and runs it. Non-zero exit fails that scene's voice job only. Duration comes from `ffprobe`.

No network TTS. Hindi, English, Hinglish, and male / female / child are voice ids in settings (`TTS_VOICE_MALE`, `TTS_VOICE_FEMALE`, `TTS_VOICE_CHILD`), passed through `{voice}`.

## GPU stages

Run in this order for a full generate. Do not overlap them.

1. LLM planning through a local model, OpenRouter, Gemini, or OpenAI. A local model uses the GPU; `keep_alive: 0` unloads Ollama before the next stage.
2. ComfyUI character references, then scene images. Then `POST /free`.
3. ComfyUI Wan for `video` scenes only. Then `POST /free`.
4. ACE-Step. One track per project.
5. TTS (CPU unless the configured command uses the GPU; still do not overlap it with step 2–4).
6. FFmpeg assemble (CPU).

## VRAM probe

`GpuMonitor.snapshot()`:

- Prefer `GET {COMFYUI_BASE_URL}/system_stats`. `vram_used = vram_total - vram_free` per device. Utilization and temperature stay null here.
- If `rocm-smi` is on `PATH`, parse `--showmeminfo vram --showuse --showtemp --json` for used bytes, utilization percent, and edge temperature.
- If neither works, return null metrics and `available: false`. Do not fail the app.
- Never shell out to `nvidia-smi`.

Expose the snapshot on `GET /api/gpu`.

## FFmpeg

`VideoRenderer` builds argument lists. Tests assert the lists; they do not require a display.

Image scene (one still → clip matching `duration`):

- Scale to cover the delivery frame, crop, then `zoompan` for `zoom_in`, `zoom_out`, `pan_left`, `pan_right`.
- `camera_shake`: small random `crop` expression.
- `fade` / `flash` / `blur` / `vignette` as `fade`, `eq`+`fade` color flash, `gblur`, `vignette`.
- Transitions between clips: `xfade` for `crossfade` and `fade`; `concat` for `hard_cut`.
- `fps` from the project. `setpts` for speed.

Audio mix, one filtergraph:

- Narration at gain 1.0.
- Music at 0.20, ducked to that level while narration is audible (`sidechaincompress` with narration as sidechain). When `music_mode=none`, omit music.
- Each SFX at its cue gain (default 0.5, allowed 0.3–0.7) delayed to the scene start (`adelay`).
- `amix` with `normalize=0`, then loudnorm only if the user enabled it. Narration must remain intelligible; do not normalize so hard that ducking is undone.

`ffprobe` checks the final file: video stream, audio stream, width, height, avg_frame_rate, duration within 0.5s of the narration timeline.
