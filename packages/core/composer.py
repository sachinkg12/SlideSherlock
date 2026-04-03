"""
Composer (Fig3 step 18).
Combine slide PNG + overlay + audio via FFmpeg; output final.mp4.
Supports: crossfade transitions, intro/outro cards, per-slide audio fades,
subtitles burn-in, optional BGM. Degrades gracefully when features disabled.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any, List, Optional, Tuple

# Optional imports for video_config
try:
    from video_config import VideoConfig, TRANSITION_CUT, TRANSITION_CROSSFADE
except ImportError:
    VideoConfig = None  # type: ignore
    TRANSITION_CUT = "cut"
    TRANSITION_CROSSFADE = "crossfade"

try:
    from audio_processor import apply_audio_fade, _get_duration_seconds
except ImportError:
    apply_audio_fade = None  # type: ignore
    _get_duration_seconds = None  # type: ignore


def concat_audio(
    per_slide_audio_paths: List[str],
    output_audio_path: str,
    sample_rate: int = 48000,
    fade_ms: int = 0,
    intro_silence_sec: float = 0,
    outro_silence_sec: float = 0,
) -> str:
    """
    Concat per-slide audio files into one WAV. If fade_ms > 0, apply fade-in/out per slide.
    intro_silence_sec/outro_silence_sec: prepend/append silence for intro/outro cards.
    """
    if not per_slide_audio_paths and intro_silence_sec <= 0 and outro_silence_sec <= 0:
        raise ValueError("No audio files to concat")
    paths_to_concat = per_slide_audio_paths
    temp_faded: List[str] = []
    if fade_ms > 0 and apply_audio_fade:
        for i, p in enumerate(per_slide_audio_paths):
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                apply_audio_fade(p, tmp, fade_ms=fade_ms, sample_rate=sample_rate)
                temp_faded.append(tmp)
            except Exception:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
                temp_faded = []
                break
        if temp_faded and len(temp_faded) == len(per_slide_audio_paths):
            paths_to_concat = temp_faded
    parts: List[str] = []
    extra_temps: List[str] = []
    if intro_silence_sec > 0:
        fd, sil_in = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono",
             "-t", str(intro_silence_sec), "-ar", str(sample_rate), "-ac", "1", sil_in],
            check=True, capture_output=True, timeout=30,
        )
        parts.append(sil_in)
        extra_temps.append(sil_in)
    for p in paths_to_concat:
        parts.append(p)
    if outro_silence_sec > 0:
        fd, sil_out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=mono",
             "-t", str(outro_silence_sec), "-ar", str(sample_rate), "-ac", "1", sil_out],
            check=True, capture_output=True, timeout=30,
        )
        parts.append(sil_out)
        extra_temps.append(sil_out)
    if not parts:
        parts = paths_to_concat
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for p in parts:
                f.write(f"file '{os.path.abspath(p)}'\n")
            list_path = f.name
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", list_path,
                    "-ar", str(sample_rate),
                    "-ac", "1",
                    output_audio_path,
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
            return output_audio_path
        finally:
            if os.path.exists(list_path):
                os.unlink(list_path)
    finally:
        for t in temp_faded:
            try:
                if os.path.exists(t):
                    os.unlink(t)
            except Exception:
                pass
        for t in extra_temps:
            try:
                if os.path.exists(t):
                    os.unlink(t)
            except Exception:
                pass


def _get_video_duration(path: str) -> float:
    """Get duration of video file in seconds."""
    if _get_duration_seconds:
        return _get_duration_seconds(path) or 0.0
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        pass
    return 0.0


def _render_card_mp4(
    title: str,
    subtitle: str,
    duration_sec: float,
    width: int,
    height: int,
    output_path: str,
) -> str:
    """Render a title card (intro/outro) as MP4."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("PIL required for intro/outro cards")
    img = Image.new("RGB", (width, height), (30, 30, 40))
    draw = ImageDraw.Draw(img)
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 72)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
    except Exception:
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        except Exception:
            font_large = ImageFont.load_default()
            font_small = font_large
    y = height // 2 - 60
    if title:
        bbox = draw.textbbox((0, 0), title, font=font_large)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw) // 2, y), title, fill=(255, 255, 255), font=font_large)
        y += 80
    if subtitle:
        bbox = draw.textbbox((0, 0), subtitle, font=font_small)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw) // 2, y), subtitle, fill=(180, 180, 190), font=font_small)
    card_png = output_path.replace(".mp4", "_card.png")
    img.save(card_png)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", card_png,
                "-t", str(duration_sec), "-pix_fmt", "yuv420p",
                "-vf", f"scale={width}:{height}",
                output_path,
            ],
            check=True, capture_output=True, timeout=60,
        )
    finally:
        if os.path.exists(card_png):
            try:
                os.unlink(card_png)
            except Exception:
                pass
    return output_path


def _compose_with_crossfade(
    video_paths: List[str],
    durations: List[float],
    transition_ms: int,
    output_path: str,
) -> str:
    """Compose videos with xfade transitions. Requires filter_complex."""
    if len(video_paths) < 2:
        if len(video_paths) == 1:
            import shutil
            shutil.copy(video_paths[0], output_path)
            return output_path
        raise ValueError("Need at least one video")
    fade_sec = transition_ms / 1000.0
    fade_sec = min(fade_sec, min(durations) * 0.4)
    inputs: List[str] = []
    for p in video_paths:
        inputs.extend(["-i", p])
    # Build xfade chain: [0:v][1:v]xfade[v01]; [v01][2:v]xfade[v02]; ...
    filters: List[str] = []
    cum_dur = durations[0]
    for i in range(1, len(video_paths)):
        offset = max(0, cum_dur - fade_sec)
        out_label = "vout" if i == len(video_paths) - 1 else f"v{i:02d}"
        in_a = "[0:v]" if i == 1 else f"[v{i-1:02d}]"
        in_b = f"[{i}:v]"
        filters.append(f"{in_a}{in_b}xfade=transition=fade:duration={fade_sec:.3f}:offset={offset:.3f}[{out_label}]")
        cum_dur = cum_dur + durations[i] - fade_sec
    filter_str = ";".join(filters)
    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_str, "-map", "[vout]", "-c:v", "libx264", "-pix_fmt", "yuv420p", output_path]
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    return output_path


def compose_video(
    per_slide_mp4_paths: List[str],
    total_duration_seconds: float,
    output_path: str,
    audio_path: Optional[str] = None,
    per_slide_audio_paths: Optional[List[str]] = None,
    audio_sample_rate: int = 48000,
    video_config: Optional[Any] = None,
    srt_path: Optional[str] = None,
    per_slide_durations: Optional[List[float]] = None,
    deck_title: str = "",
    deck_subtitle: str = "",
) -> str:
    """
    Concat per-slide MP4s and add audio. Returns output_path.
    When video_config provided, applies: crossfade, intro/outro, audio fades, subtitle burn-in, BGM.
    Degrades gracefully when config is None or features disabled.
    """
    if not per_slide_mp4_paths:
        raise ValueError("No slide videos to concat")
    config = video_config
    use_crossfade = config and getattr(config, "transition", "") == TRANSITION_CROSSFADE and len(per_slide_mp4_paths) >= 2
    use_intro = config and getattr(config, "intro_enabled", False)
    use_outro = config and getattr(config, "outro_enabled", False)
    fade_ms = getattr(config, "audio_fade_ms", 0) if config else 0
    use_subs_burn = config and getattr(config, "subtitles_burn_in", False) and srt_path and os.path.exists(srt_path)
    use_bgm = config and getattr(config, "bgm_enabled", False) and getattr(config, "bgm_path", None)
    # Get dimensions from first slide
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0",
             per_slide_mp4_paths[0]],
            capture_output=True, text=True, timeout=5,
        )
        wh = (r.stdout or "").strip().split(",")
        width = int(wh[0]) if len(wh) >= 1 and wh[0].isdigit() else 1280
        height = int(wh[1]) if len(wh) >= 2 and wh[1].isdigit() else 720
    except Exception:
        width, height = 1280, 720
    video_paths = list(per_slide_mp4_paths)
    durations = list(per_slide_durations) if per_slide_durations else []
    if not durations:
        for p in video_paths:
            durations.append(_get_video_duration(p) if hasattr(subprocess, "run") else 2.0)
    intro_path: Optional[str] = None
    outro_path: Optional[str] = None
    if use_intro and config:
        fd, intro_path = tempfile.mkstemp(suffix="_intro.mp4")
        os.close(fd)
        _render_card_mp4(
            getattr(config, "intro_title", deck_title or "Presentation"),
            getattr(config, "intro_subtitle", deck_subtitle),
            getattr(config, "intro_duration", 2.0),
            width, height, intro_path,
        )
        video_paths.insert(0, intro_path)
        durations.insert(0, getattr(config, "intro_duration", 2.0))
    if use_outro and config:
        fd, outro_path = tempfile.mkstemp(suffix="_outro.mp4")
        os.close(fd)
        _render_card_mp4(
            getattr(config, "outro_text", "Thanks for watching"),
            "",
            getattr(config, "outro_duration", 2.0),
            width, height, outro_path,
        )
        video_paths.append(outro_path)
        durations.append(getattr(config, "outro_duration", 2.0))
    concat_path: Optional[str] = None
    sub_path_temp: Optional[str] = None
    try:
        if use_crossfade and config:
            trans_ms = getattr(config, "transition_ms", 300)
            fd, concat_path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            try:
                _compose_with_crossfade(video_paths, durations, trans_ms, concat_path)
            except Exception:
                use_crossfade = False
                if concat_path and os.path.exists(concat_path):
                    try:
                        os.unlink(concat_path)
                    except Exception:
                        pass
                concat_path = None
        if not use_crossfade:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                for p in video_paths:
                    f.write(f"file '{os.path.abspath(p)}'\n")
                list_path = f.name
            concat_path = tempfile.mktemp(suffix=".mp4")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", concat_path],
                    check=True, capture_output=True, timeout=300,
                )
            finally:
                if os.path.exists(list_path):
                    os.unlink(list_path)
        final_audio_path = audio_path
        intro_silence = getattr(config, "intro_duration", 0.0) if (use_intro and config) else 0.0
        outro_silence = getattr(config, "outro_duration", 0.0) if (use_outro and config) else 0.0
        if per_slide_audio_paths and not final_audio_path:
            fd, concat_audio_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                concat_audio(
                    per_slide_audio_paths,
                    concat_audio_path,
                    sample_rate=audio_sample_rate,
                    fade_ms=fade_ms,
                    intro_silence_sec=intro_silence,
                    outro_silence_sec=outro_silence,
                )
                final_audio_path = concat_audio_path
            except Exception:
                concat_audio(
                    per_slide_audio_paths,
                    concat_audio_path,
                    sample_rate=audio_sample_rate,
                    fade_ms=0,
                    intro_silence_sec=intro_silence,
                    outro_silence_sec=outro_silence,
                )
                final_audio_path = concat_audio_path
        else:
            concat_audio_path = None
        video_input = concat_path
        if use_subs_burn and srt_path and video_input:
            # Copy SRT to temp; use file:// for subtitles filter to avoid path escaping
            fd_srt, srt_temp = tempfile.mkstemp(suffix=".srt")
            os.close(fd_srt)
            sub_path_temp = tempfile.mktemp(suffix="_subs.mp4")
            try:
                with open(srt_path, "r", encoding="utf-8") as f:
                    with open(srt_temp, "w", encoding="utf-8") as out:
                        out.write(f.read())
                srt_uri = "file://" + os.path.abspath(srt_temp).replace("\\", "/")
                subprocess.run(
                    ["ffmpeg", "-y", "-i", video_input, "-vf", f"subtitles={srt_uri}", "-c:a", "copy", sub_path_temp],
                    check=True, capture_output=True, timeout=300,
                )
                video_input = sub_path_temp
            except Exception:
                sub_path_temp = None
            finally:
                if os.path.exists(srt_temp):
                    try:
                        os.unlink(srt_temp)
                    except Exception:
                        pass
        total_video_dur = sum(durations) if durations else total_duration_seconds
        if final_audio_path and os.path.exists(final_audio_path):
            audio_dur = _get_video_duration(final_audio_path) if hasattr(subprocess, "run") else 0.0
            video_dur = _get_video_duration(video_input) if hasattr(subprocess, "run") else total_video_dur
            if video_dur <= 0:
                video_dur = total_video_dur
            if audio_dur <= 0:
                audio_dur = total_video_dur
            if video_dur < audio_dur - 0.5:
                fd_pad, padded_audio = tempfile.mkstemp(suffix="_padded.wav")
                os.close(fd_pad)
                try:
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-i", final_audio_path,
                            "-af", f"apad=whole_dur={video_dur}",
                            "-ar", str(audio_sample_rate), "-ac", "1",
                            padded_audio,
                        ],
                        check=True, capture_output=True, timeout=60,
                    )
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", video_input, "-i", padded_audio,
                         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                         "-shortest", output_path],
                        check=True, capture_output=True, timeout=300,
                    )
                finally:
                    if os.path.exists(padded_audio):
                        try:
                            os.unlink(padded_audio)
                        except Exception:
                            pass
            else:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", video_input, "-i", final_audio_path,
                     "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                     "-shortest", output_path],
                    check=True, capture_output=True, timeout=300,
                )
        else:
            total_dur = sum(durations) if durations else total_duration_seconds
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i",
                    f"anullsrc=channel_layout=stereo:sample_rate={audio_sample_rate}:duration={total_dur}",
                    "-i", video_input,
                    "-c:v", "copy", "-c:a", "aac", "-shortest",
                    "-map", "1:v", "-map", "0:a",
                    output_path,
                ],
                check=True, capture_output=True, timeout=300,
            )
        if final_audio_path and final_audio_path != audio_path and os.path.exists(final_audio_path):
            try:
                os.unlink(final_audio_path)
            except Exception:
                pass
        return output_path
    finally:
        if intro_path and os.path.exists(intro_path):
            try:
                os.unlink(intro_path)
            except Exception:
                pass
        if outro_path and os.path.exists(outro_path):
            try:
                os.unlink(outro_path)
            except Exception:
                pass
        if concat_path and os.path.exists(concat_path):
            try:
                os.unlink(concat_path)
            except Exception:
                pass
        if sub_path_temp and os.path.exists(sub_path_temp):
            try:
                os.unlink(sub_path_temp)
            except Exception:
                pass
