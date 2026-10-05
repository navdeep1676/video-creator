"""Turn a topic into an original story and a timed scene plan."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.services.openrouter_llm import LLMProvider

HORROR_BEATS = ("hook", "setup", "tension", "escalation", "reveal", "climax", "ending")
KIDS_FORMATS = ("nursery_rhyme", "educational", "animal", "moral", "alphabet", "number", "original_song")
MOTION_WORDS = (
    "shadow",
    "door",
    "turn",
    "approach",
    "jump scare",
    "jumpscare",
    "walk",
    "dance",
    "wave",
    "jump",
    "animal",
    "interact",
)
SFX_KEYS = ("door_open", "footsteps", "knock", "heartbeat", "whisper", "bird", "boing", "laugh")

SYSTEM_PROMPT = """You write original stories for short videos.
Do not quote or closely paraphrase copyrighted plots or song lyrics.
Kids songs must be new words and a new music prompt.
Every scene continues the previous scene.
Hindi and Hinglish narration is in that language.
Image prompts stay in English.
Return one JSON object matching the schema.
Horror beats, in order, are hook, setup, tension, escalation, reveal, climax, ending.
Kids format is one of nursery_rhyme, educational, animal, moral, alphabet, number, original_song.
Kids lyrics use original verse and chorus labels.
The music prompt describes instruments, tempo, and mood only. Do not name an existing song.
Every scene has its own music_prompt for the instruments, tempo, and mood of that scene.
Each scene continues the score from the previous scene.
Scene continues_from_index is null for the first scene and the previous index after that.
SFX values use only these keys: door_open, footsteps, knock, heartbeat, whisper, bird, boing, laugh.
"""


class PlanError(ValueError):
    pass


class CharacterDraft(BaseModel):
    name: str
    age: str = ""
    appearance: str = ""
    clothing: str = ""
    personality: str = ""
    visual_style: str = ""


class LocationDraft(BaseModel):
    name: str
    description: str = ""
    lighting: str = ""
    mood: str = ""


class SceneDraft(BaseModel):
    beat: str
    narration: str
    dialogue: str = ""
    character_names: list[str] = Field(default_factory=list)
    location_name: str = ""
    image_prompt: str
    video_prompt: str = ""
    camera_motion: str = "zoom_in"
    transition: str = "crossfade"
    sfx: list[str] = Field(default_factory=list)
    music_prompt: str = ""
    continues_from_index: int | None = None
    start_time: float = 0
    end_time: float = 0
    duration: float = 0
    generation_mode: str = "image"


class StoryPlan(BaseModel):
    title: str
    hook: str
    story: str
    lyrics: str | None = None
    kids_format: str | None = None
    characters: list[CharacterDraft]
    locations: list[LocationDraft]
    music_prompt: str = ""
    sfx_notes: str = ""
    scenes: list[SceneDraft]


def auto_scene_count(duration_seconds: int) -> int:
    if duration_seconds <= 30:
        return 4
    if duration_seconds <= 60:
        return 6
    if duration_seconds <= 140:
        return 10
    if duration_seconds <= 180:
        return 12
    if duration_seconds <= 300:
        return 24
    if duration_seconds <= 600:
        return 60
    return max(150, min(250, round(duration_seconds / 5)))


def target_scene_count(duration_seconds: int, scene_count: str) -> int:
    if scene_count == "auto":
        return auto_scene_count(duration_seconds)
    return int(scene_count)


def plan_story(project: Any, provider: LLMProvider, settings: Settings) -> StoryPlan:
    schema = StoryPlan.model_json_schema()
    user = _user_prompt(project)
    last_error = "invalid plan"
    for attempt in range(2):
        raw = provider.complete_json(system=SYSTEM_PROMPT, user=user, schema=schema, schema_name="story_plan")
        try:
            plan = StoryPlan.model_validate(raw)
            _reject_bad_plan(plan, project.content_type)
            plan.scenes = prepare_scenes(
                plan.scenes,
                duration=project.duration_seconds,
                target=target_scene_count(project.duration_seconds, project.scene_count),
                content_type=project.content_type,
                settings=settings,
            )
            ensure_scene_music(plan.scenes, plan.music_prompt, project.content_type)
            return plan
        except (ValidationError, PlanError) as exc:
            last_error = str(exc)
            user = _user_prompt(project) + f"\n\nThe previous reply failed validation: {last_error}. Return corrected JSON only."
            if attempt == 1:
                raise PlanError(last_error) from exc
    raise PlanError(last_error)


def prepare_scenes(
    scenes: list[SceneDraft],
    *,
    duration: int,
    target: int,
    content_type: str,
    settings: Settings,
) -> list[SceneDraft]:
    planned = [scene.model_copy(deep=True) for scene in scenes]
    if not planned:
        raise PlanError("The plan has no scenes")
    guard = 0
    while len(planned) != target and guard < target + len(scenes) + 5:
        guard += 1
        if len(planned) > target:
            merged = _merge_shortest(planned)
            if merged is planned:
                break
            planned = merged
        else:
            planned = _split_longest(planned)
    if len(planned) != target:
        raise PlanError(f"Could not fit the story into {target} scenes")
    _renumber(planned)
    if content_type == "horror" and target >= len(HORROR_BEATS):
        problem = _horror_beat_problem(planned)
        if problem:
            raise PlanError(problem)
    _allocate_time(planned, float(duration))
    _assign_generation_mode(planned, float(duration), settings)
    return planned


def video_seconds(scenes: list[SceneDraft]) -> float:
    return sum(scene.duration for scene in scenes if scene.generation_mode == "video")


def _user_prompt(project: Any) -> str:
    count = target_scene_count(project.duration_seconds, project.scene_count)
    return "\n".join(
        [
            f"Content type: {project.content_type}",
            f"Topic: {project.topic}",
            f"Language: {project.language}",
            f"Visual style: {project.visual_style}",
            f"Duration seconds: {project.duration_seconds}",
            f"Scene count: {count}",
            f"Music mode: {project.music_mode}",
            "Write an original story. Do not copy an existing video or song.",
            "Give every scene its own music_prompt. Describe instruments, tempo, and mood for that scene only.",
            f"Return exactly {count} scenes.",
            (
                "Include original lyrics with verse and chorus labels. kids_format is one of: "
                + ", ".join(KIDS_FORMATS)
                if project.content_type == "kids"
                else "Include every horror beat in order: " + ", ".join(HORROR_BEATS)
            ),
        ]
    )


def _reject_bad_plan(plan: StoryPlan, content_type: str) -> None:
    for index, scene in enumerate(plan.scenes):
        scene.beat = scene.beat.strip().lower()
        expected = None if index == 0 else index - 1
        if scene.continues_from_index != expected:
            raise PlanError(f"Scene {index} does not continue the previous scene")
        scene.sfx = _normalize_sfx(scene.sfx)
    if content_type == "horror":
        problem = _horror_beat_problem(plan.scenes)
        if problem:
            raise PlanError(problem)
    if content_type == "kids":
        if not (plan.lyrics or "").strip():
            raise PlanError("Kids lyrics are empty")
        if plan.kids_format and plan.kids_format not in KIDS_FORMATS:
            raise PlanError("Unknown kids format")


def _horror_beat_problem(scenes: list[SceneDraft]) -> str | None:
    present: list[str] = []
    for scene in scenes:
        if scene.beat not in present:
            present.append(scene.beat)
    missing = [beat for beat in HORROR_BEATS if beat not in present]
    if missing:
        return "Missing horror beats: " + ", ".join(missing)
    if present != list(HORROR_BEATS):
        return "Horror beats are out of order"
    return None


def _normalize_sfx(cues: list[str]) -> list[str]:
    normalized = []
    for cue in cues:
        key = cue.strip().lower().replace(" ", "_")
        if key in SFX_KEYS and key not in normalized:
            normalized.append(key)
        elif cue.strip() and cue.strip() not in normalized:
            normalized.append(cue.strip())
    return normalized


def _merge_shortest(scenes: list[SceneDraft]) -> list[SceneDraft]:
    counts: dict[str, int] = {}
    for scene in scenes:
        counts[scene.beat] = counts.get(scene.beat, 0) + 1
    candidates = [index for index in range(1, len(scenes) - 1) if counts[scenes[index].beat] > 1]
    if not candidates:
        candidates = list(range(1, len(scenes) - 1))
    if not candidates:
        return scenes
    index = min(candidates, key=lambda item: _words(scenes[item].narration))
    merged = scenes[index - 1].model_copy(deep=True)
    current = scenes[index]
    merged.narration = f"{merged.narration} {current.narration}".strip()
    merged.dialogue = " ".join(part for part in (merged.dialogue, current.dialogue) if part).strip()
    merged.sfx = _normalize_sfx(merged.sfx + current.sfx)
    merged.music_prompt = _join_music(merged.music_prompt, current.music_prompt)
    return scenes[: index - 1] + [merged] + scenes[index + 1 :]


def _split_longest(scenes: list[SceneDraft]) -> list[SceneDraft]:
    index = max(range(len(scenes)), key=lambda item: _words(scenes[item].narration))
    scene = scenes[index]
    words = scene.narration.split()
    if len(words) < 2:
        words = (scene.narration + " continues").split()
    midpoint = max(1, len(words) // 2)
    left = scene.model_copy(deep=True)
    right = scene.model_copy(deep=True)
    left.narration = " ".join(words[:midpoint])
    right.narration = " ".join(words[midpoint:])
    return scenes[:index] + [left, right] + scenes[index + 1 :]


def _renumber(scenes: list[SceneDraft]) -> None:
    for index, scene in enumerate(scenes):
        scene.continues_from_index = None if index == 0 else index - 1


def _allocate_time(scenes: list[SceneDraft], total: float) -> None:
    weights = [_words(scene.narration) for scene in scenes]
    weight_sum = float(sum(weights))
    durations = [total * weight / weight_sum for weight in weights]
    if len(scenes) * 2 <= total:
        for _ in range(len(scenes)):
            deficit = 0.0
            free = []
            for index, duration in enumerate(durations):
                if duration < 2:
                    deficit += 2 - duration
                    durations[index] = 2
                else:
                    free.append(index)
            if deficit <= 0 or not free:
                break
            free_sum = sum(durations[index] for index in free)
            if free_sum <= deficit:
                break
            for index in free:
                durations[index] -= deficit * durations[index] / free_sum
    durations[-1] += total - sum(durations)
    cursor = 0.0
    for scene, duration in zip(scenes, durations):
        scene.duration = round(duration, 3)
        scene.start_time = round(cursor, 3)
        cursor += duration
        scene.end_time = round(cursor, 3)
    scenes[-1].end_time = round(total, 3)


def _assign_generation_mode(scenes: list[SceneDraft], total: float, settings: Settings) -> None:
    # The whole scene counts toward the budget. A 140s film then keeps about
    # 20–40s of video scenes. The video stage caps each Wan clip later.
    budget = total * settings.wan_budget_ratio
    used = 0.0

    def rank(item: tuple[int, SceneDraft]) -> tuple[int, int, int]:
        index, scene = item
        text = f"{scene.video_prompt} {' '.join(scene.sfx)} {scene.narration}".lower()
        hits = sum(1 for word in MOTION_WORDS if word in text)
        beat_bonus = 2 if scene.beat in {"climax", "reveal", "ending"} else 0
        return (hits, beat_bonus, -index)

    for _index, scene in sorted(enumerate(scenes), key=rank, reverse=True):
        scene.generation_mode = "image"
        if used + scene.duration <= budget + 0.05 and (rank((_index, scene))[0] > 0 or rank((_index, scene))[1] > 0):
            scene.generation_mode = "video"
            used += scene.duration


def ensure_scene_music(scenes: list[SceneDraft], music_prompt: str, content_type: str) -> None:
    base = music_prompt.strip()
    for scene in scenes:
        if scene.music_prompt.strip():
            continue
        scene.music_prompt = _scene_music_line(scene, base, content_type)


def _scene_music_line(scene: SceneDraft, base: str, content_type: str) -> str:
    narration = " ".join(scene.narration.split())[:120]
    parts = [part for part in (base, f"{scene.beat}, {_beat_mood(scene.beat, content_type)}", scene.location_name.strip(), narration) if part]
    return ", ".join(parts)


def _beat_mood(beat: str, content_type: str) -> str:
    if content_type == "kids":
        moods = {
            "hook": "gentle opening",
            "verse": "soft and playful",
            "chorus": "brighter and singable",
            "ending": "calm and warm",
        }
        return moods.get(beat, "light and playful")
    moods = {
        "hook": "sparse and quiet",
        "setup": "slow and cautious",
        "tension": "uneasy and dissonant",
        "escalation": "tighter and louder",
        "reveal": "thin and exposed",
        "climax": "fast and heavy",
        "ending": "fading and unresolved",
    }
    return moods.get(beat, "matching this scene")


def _join_music(left: str, right: str) -> str:
    left = left.strip()
    right = right.strip()
    if not right or right == left:
        return left
    if not left:
        return right
    return f"{left}; {right}"


def _words(text: str) -> int:
    return max(1, len(text.split()))


def plan_to_json(plan: StoryPlan) -> str:
    return json.dumps(plan.model_dump(), indent=2)
