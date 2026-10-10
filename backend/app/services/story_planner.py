"""Turn a topic into an original story and a timed scene plan."""

from __future__ import annotations

import json
import re
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
LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi written in Devanagari",
    "hinglish": "Hinglish, Hindi in Devanagari mixed with English words",
}
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")

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


def import_plan(
    raw: dict,
    *,
    content_type: str,
    duration_seconds: int,
    settings: Settings,
    visual_style: str = "",
    music_mode: str = "background",
) -> StoryPlan:
    """Validate a pasted story object and fit it to the project length.

    Scene count stays as pasted. Timing, picture style, and music mode follow the project.
    """
    if not isinstance(raw, dict):
        raise PlanError("Story JSON must be an object")
    if "properties" in raw and "scenes" not in raw:
        raise PlanError("Paste a story object with scenes, not the JSON schema")
    try:
        plan = StoryPlan.model_validate(raw)
    except ValidationError as exc:
        raise PlanError(_validation_message(exc)) from exc
    for index, scene in enumerate(plan.scenes):
        scene.continues_from_index = None if index == 0 else index - 1
    _reject_bad_plan(plan, content_type)
    plan.scenes = prepare_scenes(
        plan.scenes,
        duration=duration_seconds,
        target=len(plan.scenes),
        content_type=content_type,
        settings=settings,
    )
    apply_generation_settings(plan, visual_style=visual_style, music_mode=music_mode, content_type=content_type)
    return plan


def _validation_message(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(item) for item in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
    return "; ".join(parts) or "Story JSON does not match the schema"


def plan_story(project: Any, provider: LLMProvider, settings: Settings) -> StoryPlan:
    schema = StoryPlan.model_json_schema()
    user = _user_prompt(project)
    last_error = "invalid plan"
    for attempt in range(2):
        raw = provider.complete_json(system=SYSTEM_PROMPT, user=user, schema=schema, schema_name="story_plan")
        try:
            plan = StoryPlan.model_validate(raw)
            _reject_bad_plan(plan, project.content_type)
            mismatch = _settings_problem(plan, project)
            if mismatch:
                raise PlanError(mismatch)
            plan.scenes = prepare_scenes(
                plan.scenes,
                duration=project.duration_seconds,
                target=target_scene_count(project.duration_seconds, project.scene_count),
                content_type=project.content_type,
                settings=settings,
            )
            apply_generation_settings(
                plan,
                visual_style=str(getattr(project, "visual_style", "") or ""),
                music_mode=str(getattr(project, "music_mode", "background") or "background"),
                content_type=project.content_type,
            )
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


def language_label(language: str) -> str:
    return LANGUAGE_NAMES.get(language, language)


def narration_word_bounds(duration_seconds: int, language: str) -> tuple[int, int]:
    """Spoken-word range that fills the selected length at a natural pace."""
    rate = 2.0 if language in {"hi", "hinglish"} else 2.3
    target = max(20, int(round(max(1, duration_seconds) * rate)))
    low = max(12, int(round(target * 0.6)))
    high = max(low + 1, int(round(target * 1.5)))
    return low, high


def _user_prompt(project: Any) -> str:
    count = target_scene_count(project.duration_seconds, project.scene_count)
    language = str(getattr(project, "language", "en") or "en")
    content_type = str(getattr(project, "content_type", "horror") or "horror")
    visual_style = str(getattr(project, "visual_style", "") or "").strip() or "Cinematic"
    music_mode = str(getattr(project, "music_mode", "background") or "background")
    duration = int(project.duration_seconds)
    low, high = narration_word_bounds(duration, language)
    return "\n".join(
        [
            "Follow every setting below. The story, the pictures, and the music must match them.",
            f"Type: {content_type}.",
            _type_instruction(content_type),
            f"Topic: {project.topic}",
            f"Language: {language_label(language)}.",
            _language_instruction(language),
            f"Visual style: {visual_style}.",
            f'Every image_prompt and every character visual_style must include "{visual_style}".',
            "Image prompts and video prompts stay in English.",
            f"Length: {duration} seconds.",
            (
                f"Write between {low} and {high} words of spoken narration across all scenes "
                f"so the story fills {duration} seconds."
            ),
            f"Scene count: {count}. Return exactly {count} scenes.",
            f"Music: {music_mode}.",
            _music_instruction(music_mode, language, content_type),
            "Write an original story. Do not copy an existing video or song.",
            "Each scene continues the previous scene.",
        ]
    )


def _type_instruction(content_type: str) -> str:
    if content_type == "kids":
        return (
            "This is a kids story. Include original lyrics with verse and chorus labels. kids_format is one of: "
            + ", ".join(KIDS_FORMATS)
            + "."
        )
    return "This is a horror story. Include every horror beat in order: " + ", ".join(HORROR_BEATS) + "."


def _language_instruction(language: str) -> str:
    if language == "hi":
        return (
            "Write the title, hook, story, narration, dialogue, and any lyrics in Hindi using Devanagari. "
            "Do not write those fields in English."
        )
    if language == "hinglish":
        return (
            "Write the title, hook, story, narration, dialogue, and any lyrics in Hinglish: "
            "Hindi in Devanagari mixed with English words."
        )
    return "Write the title, hook, story, narration, and dialogue in English only."


def _music_instruction(music_mode: str, language: str, content_type: str) -> str:
    if music_mode == "none":
        return "Set music_prompt to an empty string and set every scene music_prompt to an empty string."
    if music_mode == "full_song" or content_type == "kids":
        return (
            "Include original lyrics in "
            f"{language_label(language)} with verse and chorus labels. "
            "music_prompt and each scene music_prompt describe instruments, tempo, mood, and sung vocals. "
            "Do not name an existing song."
        )
    return (
        "music_prompt and each scene music_prompt describe an instrumental background score only: "
        "instruments, tempo, and mood. Say that it is instrumental with no vocals. "
        "Do not name an existing song."
    )


def _settings_problem(plan: StoryPlan, project: Any) -> str | None:
    language = str(getattr(project, "language", "en") or "en")
    music_mode = str(getattr(project, "music_mode", "background") or "background")
    language_problem = _language_problem(plan, language)
    if language_problem:
        return language_problem
    length_problem = _length_problem(plan, int(project.duration_seconds), language)
    if length_problem:
        return length_problem
    if music_mode == "full_song" and not (plan.lyrics or "").strip():
        return (
            "Full song needs original lyrics with verse and chorus labels in "
            f"{language_label(language)}."
        )
    return None


def _language_problem(plan: StoryPlan, language: str) -> str | None:
    devanagari, latin = _script_counts(_spoken_blob(plan))
    if language == "hi" and (devanagari < 40 or (latin > 12 and latin > devanagari / 3)):
        return "Write the title, hook, story, narration, dialogue, and lyrics in Hindi using Devanagari."
    if language == "hinglish" and (devanagari < 20 or latin < 4):
        return "Write Hinglish: Hindi in Devanagari mixed with English words."
    if language == "en" and devanagari > 30 and devanagari > latin * 2:
        return "Write the title, hook, story, narration, and dialogue in English."
    return None


def _length_problem(plan: StoryPlan, duration_seconds: int, language: str) -> str | None:
    low, high = narration_word_bounds(duration_seconds, language)
    count = _spoken_words(plan)
    if low <= count <= high:
        return None
    return (
        f"Spoken narration is {count} words. Write between {low} and {high} words "
        f"so the story fills {duration_seconds} seconds."
    )


def _spoken_blob(plan: StoryPlan) -> str:
    parts = [plan.title, plan.hook, plan.story, plan.lyrics or ""]
    for scene in plan.scenes:
        parts.append(scene.narration)
        parts.append(scene.dialogue)
    return "\n".join(parts)


def _script_counts(text: str) -> tuple[int, int]:
    return len(_DEVANAGARI.findall(text)), len(_LATIN_WORD.findall(text))


def _spoken_words(plan: StoryPlan) -> int:
    total = 0
    for scene in plan.scenes:
        narration = scene.narration.strip()
        dialogue = scene.dialogue.strip()
        total += len(narration.split())
        if dialogue and dialogue not in narration:
            total += len(dialogue.split())
    return total


def apply_generation_settings(
    plan: StoryPlan,
    *,
    visual_style: str,
    music_mode: str,
    content_type: str,
) -> None:
    _apply_visual_style(plan, visual_style)
    if music_mode == "none":
        plan.music_prompt = ""
        for scene in plan.scenes:
            scene.music_prompt = ""
        return
    _shape_music(plan, music_mode, content_type)
    ensure_scene_music(plan.scenes, plan.music_prompt, content_type)


def _apply_visual_style(plan: StoryPlan, visual_style: str) -> None:
    style = visual_style.strip()
    if not style:
        return
    needle = style.lower()
    for character in plan.characters:
        current = (character.visual_style or "").strip()
        if needle not in current.lower():
            character.visual_style = f"{style}, {current}".strip(", ")
    for scene in plan.scenes:
        prompt = scene.image_prompt.strip()
        if needle not in prompt.lower():
            scene.image_prompt = f"{style} style. {prompt}".strip()


def _shape_music(plan: StoryPlan, music_mode: str, content_type: str) -> None:
    plan.music_prompt = _score_line(plan.music_prompt, music_mode, content_type)
    for scene in plan.scenes:
        if scene.music_prompt.strip():
            scene.music_prompt = _score_line(scene.music_prompt, music_mode, content_type)


def _score_line(text: str, music_mode: str, content_type: str) -> str:
    score = text.strip()
    if not score:
        score = _default_score(content_type)
    lowered = score.lower()
    sung = music_mode == "full_song" or content_type == "kids"
    if sung:
        if "vocal" not in lowered and "sing" not in lowered:
            return f"{score}, sung vocals"
        return score
    if "instrumental" not in lowered and "no vocal" not in lowered:
        return f"{score}, instrumental, no vocals"
    return score


def _default_score(content_type: str) -> str:
    if content_type == "kids":
        return "gentle original children's music, acoustic guitar, soft tempo"
    return "dark ambient score, low drones, dissonant strings"


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
