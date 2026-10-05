import json
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.services.openrouter_llm import OpenRouterLLMProvider, ProviderUnavailable
from app.services.story_planner import HORROR_BEATS, auto_scene_count, plan_story, video_seconds

NARRATION = "lantern flickers beside the gate"
MOTION = "the child walks to the door"


class ScriptedProvider:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete_json(self, *, system, user, schema, schema_name):
        self.calls.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _project(**overrides):
    values = {
        "content_type": "horror",
        "topic": "a lantern that follows a child home",
        "language": "en",
        "visual_style": "Dark Horror",
        "duration_seconds": 140,
        "scene_count": "auto",
        "music_mode": "background",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _scene(index, beat, narration=NARRATION, video_prompt=""):
    return {
        "beat": beat,
        "narration": narration,
        "dialogue": "",
        "character_names": ["Mira"],
        "location_name": "Lane",
        "image_prompt": "A quiet lane at night, cinematic lighting",
        "video_prompt": video_prompt,
        "camera_motion": "zoom_in",
        "transition": "crossfade",
        "sfx": [],
        "continues_from_index": None if index == 0 else index - 1,
    }


def horror_payload(count=10):
    beats = ["hook", "setup", "tension", "escalation", "reveal", "climax", "ending"]
    extras = ["tension", "escalation", "climax", "reveal", "setup"]
    while len(beats) < count:
        beats.append(extras[len(beats) % len(extras)])
    scenes = []
    for index, beat in enumerate(beats[:count]):
        motion = MOTION if index in {1, 2} else ""
        scenes.append(_scene(index, beat, video_prompt=motion))
    return {
        "title": "The lantern followed her",
        "hook": "The light knew her name.",
        "story": "An original night walk home.",
        "lyrics": None,
        "characters": [
            {
                "name": "Mira",
                "age": "9",
                "appearance": "short black hair, brown eyes",
                "clothing": "yellow raincoat",
                "personality": "curious",
                "visual_style": "cinematic",
            }
        ],
        "locations": [
            {"name": "Lane", "description": "narrow wet lane", "lighting": "one lantern", "mood": "uneasy"}
        ],
        "music_prompt": "low strings, slow tempo, uneasy",
        "sfx_notes": "distant footsteps",
        "scenes": scenes,
    }


def kids_payload(count=4, lyrics="Verse:\nPaper boats sail on Tuesday puddles\nChorus:\nWe made this song today"):
    scenes = [
        _scene(index, "verse", narration=f"count the puddles number {index} with Mira today")
        for index in range(count)
    ]
    return {
        "title": "Tuesday puddles",
        "hook": "A new song about counting puddles.",
        "story": "Mira counts puddles on the way to school.",
        "lyrics": lyrics,
        "kids_format": "number",
        "characters": [
            {
                "name": "Mira",
                "age": "6",
                "appearance": "round face, green scarf",
                "clothing": "red boots",
                "personality": "cheerful",
                "visual_style": "flat color cartoon",
            }
        ],
        "locations": [
            {"name": "Lane", "description": "sunny street", "lighting": "morning", "mood": "playful"}
        ],
        "music_prompt": "ukulele, bright tempo, playful",
        "sfx_notes": "",
        "scenes": scenes,
    }


def _settings():
    return Settings(wan_budget_ratio=0.25, wan_clip_min_seconds=5, wan_clip_max_seconds=10)


def test_each_scene_gets_its_own_music_prompt():
    provider = ScriptedProvider([horror_payload()])
    plan = plan_story(_project(), provider, _settings())
    assert plan.music_prompt == "low strings, slow tempo, uneasy"
    for scene in plan.scenes:
        assert scene.music_prompt.strip()
        assert "low strings, slow tempo, uneasy" in scene.music_prompt
        assert scene.beat in scene.music_prompt
        assert scene.narration in scene.music_prompt


def test_horror_plan_has_beats_and_chain():
    provider = ScriptedProvider([horror_payload()])
    plan = plan_story(_project(), provider, _settings())
    first_seen = []
    for scene in plan.scenes:
        if scene.beat not in first_seen:
            first_seen.append(scene.beat)
    assert first_seen == list(HORROR_BEATS)
    for index, scene in enumerate(plan.scenes):
        expected = None if index == 0 else index - 1
        assert scene.continues_from_index == expected
    assert len(provider.calls) == 1


def test_kids_plan_has_original_lyrics_and_retries_empty():
    provider = ScriptedProvider([kids_payload(lyrics="  "), kids_payload()])
    plan = plan_story(_project(content_type="kids", duration_seconds=30), provider, _settings())
    assert "Paper boats sail on Tuesday puddles" in plan.lyrics
    assert "Chorus:" in plan.lyrics
    assert len(provider.calls) == 2
    assert "Kids lyrics are empty" in provider.calls[1]


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (5, 4),
        (30, 4),
        (31, 6),
        (60, 6),
        (61, 10),
        (140, 10),
        (141, 12),
        (180, 12),
        (181, 24),
        (300, 24),
        (301, 60),
        (600, 60),
        (601, 150),
        (750, 150),
        (2000, 250),
    ],
)
def test_scene_count_table(duration, expected):
    assert auto_scene_count(duration) == expected


def test_scene_count_resample_matches_table():
    provider = ScriptedProvider([kids_payload(count=2)])
    plan = plan_story(_project(content_type="kids", duration_seconds=30), provider, _settings())
    assert len(plan.scenes) == auto_scene_count(30)
    assert plan.scenes[0].continues_from_index is None
    assert plan.scenes[-1].continues_from_index == len(plan.scenes) - 2
    assert abs(plan.scenes[-1].end_time - 30) < 0.05


def test_video_budget_for_140_seconds():
    provider = ScriptedProvider([horror_payload()])
    plan = plan_story(_project(duration_seconds=140), provider, _settings())
    assert len(plan.scenes) == 10
    spent = video_seconds(plan.scenes)
    assert 20 <= spent <= 40
    assert [scene.generation_mode for scene in plan.scenes].count("video") == 2
    assert plan.scenes[1].generation_mode == "video"
    assert plan.scenes[2].generation_mode == "video"


def test_invalid_json_retries_once():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        calls.append(body)
        content = "this is not json" if len(calls) == 1 else '{"title": "ok"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    settings = _settings()
    settings.openrouter_api_key = "test-key"
    settings.openrouter_model = "openrouter/free"
    provider = OpenRouterLLMProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    parsed = provider.complete_json(
        system="sys",
        user="write a story",
        schema={"type": "object"},
        schema_name="story_plan",
    )
    assert parsed == {"title": "ok"}
    assert len(calls) == 2
    assert calls[0]["model"] == "openrouter/free"
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert "invalid" in calls[1]["messages"][1]["content"].lower()


def test_invalid_json_stops_after_one_retry():
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "nope"}}]})

    settings = _settings()
    settings.openrouter_api_key = "test-key"
    provider = OpenRouterLLMProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError):
        provider.complete_json(system="sys", user="write", schema={}, schema_name="story_plan")
    assert calls["n"] == 2


def test_missing_api_key_does_not_call_openrouter():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("chat should not be called without a key")

    settings = _settings()
    settings.openrouter_api_key = ""
    provider = OpenRouterLLMProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderUnavailable):
        provider.complete_json(system="sys", user="write", schema={}, schema_name="story_plan")
