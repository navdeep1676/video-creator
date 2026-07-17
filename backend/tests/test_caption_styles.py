"""Caption style packs and margin math."""

from app.services.caption_styles import (
    caption_margins_px,
    resolve_caption_style,
)


def test_auto_picks_shorts_for_portrait():
    pack = resolve_caption_style("auto", width=1080, height=1920, aspect_ratio="9:16")
    assert pack.id == "shorts"
    assert pack.margin_v_ratio >= 0.18


def test_auto_picks_youtube_for_landscape():
    pack = resolve_caption_style("auto", width=1920, height=1080, aspect_ratio="16:9")
    assert pack.id == "youtube"


def test_shorts_has_larger_safe_margins_than_youtube():
    yt = resolve_caption_style("youtube", width=1080, height=1920)
    sh = resolve_caption_style("shorts", width=1080, height=1920)
    assert sh.margin_v_ratio > yt.margin_v_ratio
    assert sh.margin_h_ratio > yt.margin_h_ratio

    _, yt_v, yt_l, _ = caption_margins_px(yt, width=1080, height=1920)
    _, sh_v, sh_l, _ = caption_margins_px(sh, width=1080, height=1920)
    assert sh_v > yt_v
    assert sh_l > yt_l


def test_unknown_style_falls_back_to_auto():
    pack = resolve_caption_style("nope", width=1920, height=1080, aspect_ratio="16:9")
    assert pack.id == "youtube"
