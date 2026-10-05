from types import SimpleNamespace

from app.services.story_slides import (
    duration_ms,
    motion_prompt,
    narration_text,
    slide_animation,
    slide_transition,
    voice_for_story,
)


def test_narration_keeps_dialogue_when_it_is_new():
    assert narration_text("रात में चिराग जला।", "कौन है?") == "रात में चिराग जला।\nकौन है?"


def test_narration_skips_dialogue_already_in_the_line():
    assert narration_text("कौन है?", "कौन है?") == "कौन है?"


def test_duration_is_at_least_one_second():
    assert duration_ms(14) == 14000
    assert duration_ms(0.2) == 1000


def test_video_scene_uses_wan_and_keeps_the_motion_line():
    scene = SimpleNamespace(generation_mode="video", video_prompt="the lamp flares", image_prompt="a lamp")
    assert slide_animation("video") == "wan_i2v"
    assert motion_prompt(scene) == "the lamp flares"
    assert slide_transition("crossfade") == "fade"
    assert slide_transition("cut") == "none"


def test_image_scene_has_no_motion_prompt():
    scene = SimpleNamespace(generation_mode="image", video_prompt="", image_prompt="a lamp")
    assert slide_animation("image") == "ken_burns"
    assert motion_prompt(scene) is None


def test_hindi_story_uses_a_hindi_voice():
    project = SimpleNamespace(settings={"story": {"language": "hi", "voice": "female"}})
    assert voice_for_story(project) == "hi-swara"
