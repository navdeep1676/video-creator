# Frontend

Next.js App Router under `ai-video/frontend`. Talk to the API with `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8100`). No model SDKs in the browser.

## Routes

| Route | Shows |
| --- | --- |
| `/` | Public homepage: features, how it works, pipeline. Signed-in visitors still see it; studio links go to the dashboard. |
| `/login`, `/register` | Public auth screens. A signed-in visitor is sent to `/dashboard`. |
| `/dashboard` | Total, completed, running, failed; GPU snapshot; queue; recent videos |
| `/projects` | Table, link to new, status badges |
| `/projects/new` | Create form, then POST `/api/projects` and route to the project |
| `/projects/[id]` | Story summary, characters, scene strip, progress, GPU, timeline, audio, final video, stage buttons |
| `/projects/[id]/story` | Title, hook, body, lyrics, narration |
| `/projects/[id]/characters` | Bible and reference images |
| `/projects/[id]/scenes` | Scene editor |
| `/projects/[id]/timeline` | Blocks scaled by duration, mode, transition |
| `/projects/[id]/render` | Gate errors, preview, final player, download |
| `/settings` | Read-only effective config (no API key). Every free text model from `GET /api/models`, plus URLs, resolution, retries |

Create form fields are the create body in `architecture.md`. Duration is a preset list plus custom seconds. Scene count is Auto or a number. Submit label is Generate when the user also wants the pipeline started (call `POST /api/generate`); otherwise Create saves a draft.

## Project actions

Buttons call one endpoint each: Generate Story, Generate Characters, Generate Images, Generate Motion, Generate Music, Generate Voice, Render Video, Cancel, Retry (re-queue the failed job). Disable a button while its stage is the active status.

Poll `GET /api/projects/{id}/status` every 2s while the status is not `DRAFT`, `COMPLETED`, `FAILED`, or `CANCELLED`.

## Scene editor

Each scene: index, thumbnail (`image.png` via the API file route), narration, duration, image prompt, video prompt, generation mode, sfx keys, music cue, status.

Actions: Regenerate Image, Regenerate Video, save edited prompts (`PATCH`), Approve, Reject.

## Preview

Story text on the story page. Image and wan file URLs on the scene. Audio element for narration and mix. Timeline page lists scenes in order. Render page plays `final.mp4`.

Add `GET /api/projects/{id}/files/{path}` that serves only files inside that project's directory (reject `..`).

## Visual

Dark, dense dashboard. Horror and kids projects share the layout; the content-type badge is the only theme change. Use shadcn `card`, `button`, `input`, `select`, `badge`, `tabs`.
