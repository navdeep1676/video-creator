# Pipeline

## Planning prompt

One OpenRouter call returns a single JSON object validated by Pydantic. The system message says: write an original story; do not quote or closely paraphrase copyrighted plots or song lyrics; kids songs must be new words and a new music prompt; every scene continues the previous scene; Hindi and Hinglish narration is in that language; image prompts stay in English.

Horror beats, in order: `hook`, `setup`, `tension`, `escalation`, `reveal`, `climax`, `ending`. Every beat is at least one scene. The last scene's `continues_from` is the previous scene id.

Kids `format` is one of `nursery_rhyme`, `educational`, `animal`, `moral`, `alphabet`, `number`, `original_song`. Include `lyrics` with original verse/chorus labels. `music_prompt` describes style only (instruments, tempo, mood), not a known song title.

JSON fields:

- `title`, `hook`, `story`, `lyrics` (kids, else null)
- `characters[]`: `name`, `age`, `appearance`, `clothing`, `personality`, `visual_style`
- `locations[]`: `name`, `description`, `lighting`, `mood`
- `music_prompt`, `sfx_notes`
- `scenes[]`: `beat`, `narration`, `dialogue`, `character_names`, `location_name`, `image_prompt`, `video_prompt`, `camera_motion`, `transition`, `sfx[]`, `continues_from_index`

Reject the plan if any scene's `continues_from_index` is not the previous index (scene 0 uses null), if a horror beat is missing, or if kids `lyrics` is empty.

Persist `story/story.json` and `story/narration.txt` (narration lines joined).

## Scene count and mode

`auto` count from duration:

| Duration | Scenes |
| --- | --- |
| ≤ 30s | 4 |
| ≤ 60s | 6 |
| ≤ 140s | 10 |
| ≤ 180s | 12 |
| ≤ 300s | 24 |
| ≤ 600s | 60 |
| else | clamp(round(duration / 5), 150, 250) |

If the model returns a different count, resample by splitting the longest narrations or merging the shortest until the count matches. Do not drop the first or last beat.

`generation_mode=video` budget is `WAN_BUDGET_RATIO` of total duration (default 0.25), and each such clip is at most `WAN_CLIP_MAX_SECONDS`. Prefer scenes whose `video_prompt` or `sfx` names a motion: shadow, door, turn, approach, jump scare, walk, dance, wave, jump, animal move, character interaction. Remaining scenes are `image`. A 140s film is about 100–120s of stills with FFmpeg motion and 20–40s of Wan, not 140 Wan clips.

Initial `start_time` / `end_time` split the duration across scenes in proportion to narration word count (minimum 2s). These times are provisional until TTS returns.

## Character bible

Create characters and locations before scene images. For each character, build one reference prompt from appearance, clothing, and visual style, plus a fixed seed stored on the row. Generate `reference.png` once. Later scene prompts append the character's appearance text and the workflow receives `reference_image`.

Reuse the reference when the asset row exists and the appearance hash is unchanged. Kids characters use the same path (example shape: a named object with stable colors and features).

## Timeline

Narration is the clock. After each scene wav exists, set `duration` from `ffprobe`, `start_time` to the running sum, and `end_time` to `start_time + duration`. Image clips and Wan clips are trimmed or padded (freeze the last frame, or `setpts`) to that duration. Do not use a fixed 5s-per-image step unless `scene_count` was manual and the project flag `fixed_timing` is true.

Gaps and overlaps are failures: scene i `end_time` must equal scene i+1 `start_time` within 0.05s. The sum of durations must match the final narration track within 0.5s.

## SFX

`configs/sfx_map.json` maps a cue key to a filename relative to `SFX_DIR` (default `ai-video/assets/sfx`).

Default keys: `door_open`, `footsteps`, `knock`, `heartbeat`, `whisper`, `bird`, `boing`, `laugh`.

The planner emits those keys, not free-form filenames. Unknown keys are kept on the scene and logged. Missing files are skipped unless the cue is in `required_sfx`.

## Quality gate

`validate_project` returns a list of strings. Render only when the list is empty.

1. Every scene has `image.png`.
2. Every `video` scene has `video.mp4`.
3. Every scene has `narration.wav` (skipped when narration text is empty and `music_mode=full_song`).
4. `final_mix.wav` exists when any audio source exists.
5. No timeline gaps or overlaps.
6. Sum of scene durations equals the mix duration within 0.5s when the mix exists.
7. Delivery width, height, and fps match the project (checked on the planned render spec before encode, and on the file after).
8. Character ids on each scene exist on the project.
9. After encode, `ffprobe` shows a video stream and the file size is > 0. Audio stream is required when a mix exists.

Write errors onto the render row. Leave the project out of `COMPLETED`.

## Full auto order

`POST /api/generate` enqueues: story → characters and locations → references → scene images → Wan → TTS → music (unless `none`) → sfx placement → timeline fit → quality gate → final render.

Cancel checks between stages. A cancelled project stops claiming new jobs and writes `CANCELLED`.
