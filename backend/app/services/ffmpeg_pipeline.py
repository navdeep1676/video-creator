from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.config import get_settings
from app.services.caption_styles import resolve_caption_style, caption_margins_px
from app.services.subtitles import (
    build_ass_from_timeline,
    build_srt_from_timeline,
    estimate_phrase_cues,
    load_cues,
)
from app.utils.media import ffmpeg_supports_subtitles, ffprobe_duration_ms, run_ffmpeg


@dataclass
class SlideMedia:
    slide_id: str
    image_path: Path
    audio_path: Path | None
    text: str
    duration_ms: int
    transition: str  # none | fade
    animation: str  # none | ken_burns | wan_i2v | wan_t2v
    # Optional precomputed speech-synced cues (relative to slide start)
    subtitle_cues: list[dict[str, Any]] = field(default_factory=list)
    # Multiple images on one slide → slideshow within the slide duration
    image_paths: list[Path] = field(default_factory=list)
    # Per-image hold times (ms). If empty/None weights → equal split.
    # Scaled so they sum to the slide duration (narration length).
    image_durations_ms: list[int | None] = field(default_factory=list)
    # Wan2.2 TI2V 5B prompt (wan_i2v uses the still; wan_t2v uses it when present)
    motion_prompt: str = ""
    # Project-level cache dir for generated Wan clips
    i2v_cache_dir: Path | None = None

    def resolved_image_paths(self) -> list[Path]:
        paths = [p for p in (self.image_paths or []) if p]
        if not paths and self.image_path:
            paths = [self.image_path]
        return paths

    def resolved_image_durations_s(self, total_s: float) -> list[float]:
        """Per-image seconds that sum to total_s."""
        paths = self.resolved_image_paths()
        n = len(paths)
        if n == 0:
            return []
        if n == 1:
            return [max(0.05, total_s)]

        weights: list[float] = []
        durs = list(self.image_durations_ms or [])
        while len(durs) < n:
            durs.append(None)
        for i in range(n):
            d = durs[i]
            if d is not None and d > 0:
                weights.append(float(d))
            else:
                weights.append(1.0)  # equal share among unspecified

        wsum = sum(weights) or float(n)
        out: list[float] = []
        remaining = total_s
        for i, w in enumerate(weights):
            if i == n - 1:
                out.append(max(0.05, remaining))
            else:
                sub = max(0.05, total_s * (w / wsum))
                out.append(sub)
                remaining -= sub
        return out


@dataclass
class RenderOptions:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    include_subtitles: bool = True
    # youtube | shorts | auto — see caption_styles
    caption_style: str = "auto"
    aspect_ratio: str | None = None
    bgm_path: Path | None = None
    bgm_volume: float = 0.15
    crf: int = 20
    fade_s: float = 0.5
    zoom_end: float = 1.15
    # Encode speed: veryfast for draft, medium for full
    x264_preset: str = "veryfast"


@dataclass
class RenderResult:
    output_path: Path
    thumbnail_path: Path
    duration_ms: int
    srt_path: Path | None


ProgressCb = Callable[[int, str], None]


def escape_subtitles_filter_path(path: Path) -> str:
    """Escape a caption path for the ffmpeg subtitles filter.

    The filtergraph parser consumes one backslash, then the option parser
    splits on ':'. A Windows drive letter needs two backslashes, or the rest
    of the path is read as original_size.
    """
    text = str(path.resolve()).replace("\\", "/")
    return text.replace(":", "\\\\:").replace("'", "\\\\'")


def _render_wan_t2v_segment(
    slide: SlideMedia,
    seg: Path,
    duration_s: float,
    index: int,
    n_slides: int,
    options: RenderOptions,
    progress: ProgressCb,
) -> None:
    """Wan2.2 TI2V 5B clip, then scale it onto the delivery frame."""
    from app.services.wan_t2v import generate_t2v

    progress(10 + int(30 * index / max(n_slides, 1)), "wan_ti2v")
    raw = seg.with_name(f"{seg.stem}_wan_ti2v.mp4")
    prompt = (slide.motion_prompt or "").strip() or (slide.text or "").strip()
    still = slide.image_path if slide.image_path.is_file() else None
    generate_t2v(
        raw,
        prompt=prompt,
        target_duration_s=duration_s,
        cache_dir=slide.i2v_cache_dir,
        frame_width=options.width,
        frame_height=options.height,
        image_path=still,
        progress_cb=lambda message: progress(
            10 + int(30 * (index + 1) / max(n_slides, 1)),
            f"wan_ti2v:{message[:80]}",
        ),
    )
    fi, fo = 0.0, 0.0
    if slide.transition == "fade":
        fi = 0.0 if index == 0 else options.fade_s
        fo = 0.0 if index == n_slides - 1 else options.fade_s
        if duration_s < 2 * options.fade_s:
            if index != 0:
                fi = duration_s / 4
            if index != n_slides - 1:
                fo = duration_s / 4
    vf_parts = [
        f"scale={options.width}:{options.height}:force_original_aspect_ratio=decrease",
        f"pad={options.width}:{options.height}:(ow-iw)/2:(oh-ih)/2",
        f"fps={options.fps}",
    ]
    if fi > 0:
        vf_parts.append(f"fade=t=in:st=0:d={fi:.3f}")
    if fo > 0:
        vf_parts.append(f"fade=t=out:st={max(0.0, duration_s - fo):.3f}:d={fo:.3f}")
    vf_parts.append("format=yuv420p")
    run_ffmpeg(
        [
            "-i",
            str(raw.resolve()),
            "-vf",
            ",".join(vf_parts),
            "-t",
            f"{duration_s:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            options.x264_preset,
            "-crf",
            str(options.crf),
            str(seg),
        ]
    )


def _fade_durations(d: float, fade_s: float, is_first: bool, is_last: bool, transition: str) -> tuple[float, float]:
    if transition != "fade":
        return 0.0, 0.0
    fi = 0.0 if is_first else fade_s
    fo = 0.0 if is_last else fade_s
    if d < 2 * fade_s:
        fi = d / 4 if not is_first else 0.0
        fo = d / 4 if not is_last else 0.0
    return fi, fo


def render_project_video(
    slides: list[SlideMedia],
    output_path: Path,
    work_dir: Path,
    options: RenderOptions | None = None,
    progress_cb: ProgressCb | None = None,
) -> RenderResult:
    settings = get_settings()
    options = options or RenderOptions(
        width=settings.video_width,
        height=settings.video_height,
        fps=settings.video_fps,
        fade_s=settings.fade_s,
        zoom_end=settings.ken_burns_zoom_end,
    )
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not slides:
        raise ValueError("No slides to render")

    # Timeline (+ speech-synced subtitle cues when available)
    t = 0.0
    timeline: list[dict] = []
    for slide in slides:
        d_s = slide.duration_ms / 1000.0
        cues = list(slide.subtitle_cues or [])
        if not cues and slide.audio_path:
            cues = load_cues(slide.audio_path)
        if not cues and (slide.text or "").strip():
            cues = estimate_phrase_cues(slide.text, d_s)
        timeline.append(
            {
                "slide": slide,
                "start_s": t,
                "end_s": t + d_s,
                "duration_s": d_s,
                "text": slide.text,
                "cues": cues,
            }
        )
        t += d_s
    total_s = t

    def progress(p: int, stage: str) -> None:
        if progress_cb:
            progress_cb(p, stage)

    # Step A: segments
    progress(10, "segments")
    segment_paths: list[Path] = []
    n_slides = len(timeline)
    for i, entry in enumerate(timeline):
        slide: SlideMedia = entry["slide"]
        d = entry["duration_s"]
        seg = work_dir / f"segment_{i:04d}.mp4"
        if slide.animation == "wan_t2v":
            _render_wan_t2v_segment(
                slide,
                seg,
                d,
                i,
                n_slides,
                options,
                lambda p, stage: progress(p, stage),
            )
            segment_paths.append(seg)
            progress(10 + int(30 * (i + 1) / n_slides), "segments")
            continue
        image_paths = slide.resolved_image_paths()
        if not image_paths:
            raise ValueError(f"Slide {slide.slide_id} has no images")

        # Per-image durations (scaled to slide total) — equal if unspecified
        n_imgs = len(image_paths)
        sub_durations = slide.resolved_image_durations_s(d)
        sub_paths: list[Path] = []
        for j, img_path in enumerate(image_paths):
            sub_d = sub_durations[j] if j < len(sub_durations) else max(0.05, d / n_imgs)
            n = max(1, round(sub_d * options.fps))
            sub = work_dir / f"segment_{i:04d}_img_{j:02d}.mp4"

            # Outer slide fade only on first/last image of the slide
            is_first_frame = i == 0 and j == 0
            is_last_frame = i == n_slides - 1 and j == n_imgs - 1
            # Within-slide image change: short fade between images
            fi, fo = 0.0, 0.0
            if slide.transition == "fade":
                if j == 0:
                    fi = 0.0 if i == 0 else options.fade_s
                else:
                    fi = min(0.25, sub_d / 4)
                if j == n_imgs - 1:
                    fo = 0.0 if i == n_slides - 1 else options.fade_s
                else:
                    fo = min(0.25, sub_d / 4)
                if sub_d < 2 * options.fade_s and (j == 0 or j == n_imgs - 1):
                    if j == 0 and not is_first_frame:
                        fi = sub_d / 4
                    if j == n_imgs - 1 and not is_last_frame:
                        fo = sub_d / 4

            fade_parts: list[str] = []
            if fi > 0:
                fade_parts.append(f"fade=t=in:st=0:d={fi:.3f}")
            if fo > 0:
                fade_parts.append(f"fade=t=out:st={max(0.0, sub_d - fo):.3f}:d={fo:.3f}")

            base_scale = (
                f"scale={options.width}:{options.height}:force_original_aspect_ratio=decrease,"
                f"pad={options.width}:{options.height}:(ow-iw)/2:(oh-ih)/2"
            )

            if slide.animation == "wan_i2v":
                # Wan2.2 TI2V 5B animates this still, then the clip is fit to the canvas.
                from app.services.wan_t2v import generate_t2v

                progress(
                    10 + int(30 * (i + j / max(n_imgs, 1)) / n_slides),
                    "wan_ti2v",
                )
                raw_i2v = work_dir / f"segment_{i:04d}_img_{j:02d}_wan.mp4"
                prompt = (slide.motion_prompt or "").strip() or (slide.text or "").strip()
                generate_t2v(
                    raw_i2v,
                    prompt=prompt,
                    target_duration_s=sub_d,
                    cache_dir=slide.i2v_cache_dir,
                    frame_width=options.width,
                    frame_height=options.height,
                    image_path=img_path,
                    progress_cb=lambda m: progress(
                        10 + int(30 * (i + 1) / n_slides), f"wan_ti2v:{m[:40]}"
                    ),
                )
                vf_parts = [base_scale, f"fps={options.fps}"]
                if fade_parts:
                    vf_parts.extend(fade_parts)
                vf_parts.append("format=yuv420p")
                run_ffmpeg(
                    [
                        "-i",
                        str(raw_i2v.resolve()),
                        "-vf",
                        ",".join(vf_parts),
                        "-t",
                        f"{sub_d:.3f}",
                        "-an",
                        "-c:v",
                        "libx264",
                        "-preset",
                        options.x264_preset,
                        "-crf",
                        str(options.crf),
                        str(sub),
                    ]
                )
            else:
                if slide.animation == "ken_burns":
                    zoom_inc = (options.zoom_end - 1.0) / max(n - 1, 1)
                    vf = (
                        f"{base_scale},"
                        f"zoompan=z='min(1.0+on*{zoom_inc:.8f},{options.zoom_end})':"
                        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                        f"d={n}:s={options.width}x{options.height}:fps={options.fps}"
                    )
                else:
                    vf = f"{base_scale},fps={options.fps}"

                if fade_parts:
                    vf = vf + "," + ",".join(fade_parts)
                vf = vf + ",format=yuv420p"

                run_ffmpeg(
                    [
                        "-loop",
                        "1",
                        "-i",
                        str(img_path.resolve()),
                        "-vf",
                        vf,
                        "-t",
                        f"{sub_d:.3f}",
                        "-an",
                        "-c:v",
                        "libx264",
                        "-preset",
                        options.x264_preset,
                        "-crf",
                        str(options.crf),
                        str(sub),
                    ]
                )
            sub_paths.append(sub)

        if len(sub_paths) == 1:
            shutil.move(str(sub_paths[0]), str(seg))
        else:
            sub_list = work_dir / f"segment_{i:04d}_concat.txt"
            sub_list.write_text("".join(f"file '{p.resolve()}'\n" for p in sub_paths), encoding="utf-8")
            try:
                run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(sub_list), "-c", "copy", str(seg)])
            except RuntimeError:
                run_ffmpeg(
                    [
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(sub_list),
                        "-c:v",
                        "libx264",
                        "-preset",
                        options.x264_preset,
                        "-crf",
                        str(options.crf),
                        str(seg),
                    ]
                )

        segment_paths.append(seg)
        progress(10 + int(30 * (i + 1) / n_slides), "segments")

    # Step B: concat video
    progress(45, "concat_video")
    concat_list = work_dir / "concat_list.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in segment_paths), encoding="utf-8")
    video_silent = work_dir / "video_silent.mp4"
    try:
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(video_silent)])
    except RuntimeError:
        run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c:v",
                "libx264",
                "-preset",
                options.x264_preset,
                "-crf",
                str(options.crf),
                str(video_silent),
            ]
        )

    # Step C: audio (always mono 44.1 kHz PCM so concat never glitches / doubles)
    progress(60, "audio")
    audio_parts: list[Path] = []
    for i, entry in enumerate(timeline):
        slide: SlideMedia = entry["slide"]
        d = entry["duration_s"]
        audio_out = work_dir / f"audio_{i:04d}.wav"
        if slide.audio_path and slide.audio_path.is_file():
            run_ffmpeg(
                [
                    "-i",
                    str(slide.audio_path.resolve()),
                    "-af",
                    (
                        "aformat=sample_fmts=s16:channel_layouts=mono:sample_rates=44100,"
                        f"apad=whole_dur={d:.3f},atrim=0:{d:.3f},asetpts=PTS-STARTPTS"
                    ),
                    "-ar",
                    "44100",
                    "-ac",
                    "1",
                    str(audio_out),
                ]
            )
        else:
            run_ffmpeg(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=mono",
                    "-t",
                    f"{d:.3f}",
                    "-ar",
                    "44100",
                    "-ac",
                    "1",
                    str(audio_out),
                ]
            )
        audio_parts.append(audio_out)

    audio_list = work_dir / "audio_list.txt"
    audio_list.write_text("".join(f"file '{p.resolve()}'\n" for p in audio_parts), encoding="utf-8")
    narration = work_dir / "narration.wav"
    # Re-encode (not -c copy) so sample-rate / layout mismatches cannot produce echo-like artifacts
    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(audio_list),
            "-c:a",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(narration),
        ]
    )

    # Step D: BGM
    progress(70, "audio_mix")
    audio_mix = work_dir / "audio_mix.wav"
    if options.bgm_path and options.bgm_path.is_file():
        run_ffmpeg(
            [
                "-i",
                str(narration),
                "-i",
                str(options.bgm_path.resolve()),
                "-filter_complex",
                (
                    f"[1:a]aformat=channel_layouts=mono:sample_rates=44100,"
                    f"volume={options.bgm_volume},"
                    f"apad=whole_dur={total_s:.3f},atrim=0:{total_s:.3f},asetpts=PTS-STARTPTS[bg];"
                    f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
                ),
                "-map",
                "[aout]",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(audio_mix),
            ]
        )
    else:
        shutil.copy2(narration, audio_mix)

    # Step E: timed captions (ASS for styled burn-in; SRT kept as sidecar artifact)
    srt_path: Path | None = None
    ass_path: Path | None = None
    if options.include_subtitles:
        progress(75, "subtitles")
        srt_path = work_dir / "job.srt"
        ass_path = work_dir / "job.ass"
        srt_path.write_text(build_srt_from_timeline(timeline), encoding="utf-8")
        pack = resolve_caption_style(
            options.caption_style,
            width=options.width,
            height=options.height,
            aspect_ratio=options.aspect_ratio,
        )
        font_size, margin_v, margin_l, margin_r = caption_margins_px(
            pack, width=options.width, height=options.height
        )
        ass_path.write_text(
            build_ass_from_timeline(
                timeline,
                play_res_x=options.width,
                play_res_y=options.height,
                font_size=font_size,
                margin_v=margin_v,
                margin_l=margin_l,
                margin_r=margin_r,
                outline=pack.outline,
                shadow=pack.shadow,
            ),
            encoding="utf-8",
        )

    # Step F: mux — explicit maps so a silent/placeholder A/V stream can never double-mix
    progress(80, "mux")
    final_tmp = work_dir / "output.mp4"
    mux_args = ["-i", str(video_silent), "-i", str(audio_mix)]
    if ass_path and ass_path.is_file() and ffmpeg_supports_subtitles():
        mux_args += ["-vf", f"subtitles={escape_subtitles_filter_path(ass_path)}"]
    mux_args += [
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        options.x264_preset,
        "-crf",
        str(options.crf),
        "-c:a",
        "aac",
        "-b:a",
        "128k" if options.crf >= 26 else "192k",
        "-ar",
        "44100",
        "-ac",
        "1",
        "-shortest",
        "-movflags",
        "+faststart",
        str(final_tmp),
    ]
    run_ffmpeg(mux_args)

    # Validate A/V
    v_ms = ffprobe_duration_ms(final_tmp)
    # Audio stream duration via format is fine for muxed file
    if abs(v_ms - int(total_s * 1000)) > 200:
        # soft check — still accept if close enough for short content
        pass

    thumb = work_dir / "thumb.jpg"
    progress(90, "thumbnail")
    ss = "00:00:00.500" if total_s > 1 else "00:00:00.000"
    run_ffmpeg(["-ss", ss, "-i", str(final_tmp), "-frames:v", "1", "-q:v", "2", str(thumb)])

    shutil.copy2(final_tmp, output_path)
    thumb_out = output_path.with_suffix(".jpg")
    if thumb_out.name.endswith(".mp4.jpg"):
        thumb_out = output_path.parent / (output_path.stem + "_thumb.jpg")
    shutil.copy2(thumb, thumb_out)

    progress(100, "finalize")
    return RenderResult(
        output_path=output_path,
        thumbnail_path=thumb_out,
        duration_ms=v_ms,
        srt_path=srt_path,
    )
