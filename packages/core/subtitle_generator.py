"""
Generate SRT subtitles from narration_per_slide and per-slide durations.
"""
from __future__ import annotations


def _sec_to_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _escape_srt_text(text: str) -> str:
    """Escape text for SRT (newlines allowed within cue)."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def generate_srt(
    per_slide_texts: list[str],
    per_slide_durations: list[float],
    offset_seconds: float = 0.0,
) -> str:
    """
    Generate SRT content from per-slide narration texts and durations.
    per_slide_texts[i] = narration for slide i+1
    per_slide_durations[i] = duration in seconds for slide i+1
    offset_seconds = start offset (e.g. intro duration)
    """
    lines: list[str] = []
    t = offset_seconds
    for i, (text, dur) in enumerate(zip(per_slide_texts, per_slide_durations)):
        if not text.strip():
            t += dur
            continue
        start = t
        end = t + dur
        t = end
        idx = i + 1
        lines.append(str(idx))
        lines.append(f"{_sec_to_srt_timestamp(start)} --> {_sec_to_srt_timestamp(end)}")
        lines.append(_escape_srt_text(text))
        lines.append("")
    return "\n".join(lines).strip()


def generate_srt_from_narration_and_alignment(
    narration_slides: list[dict],
    per_slide_durations: dict[int, float],
    slide_count: int,
    offset_seconds: float = 0.0,
) -> str:
    """
    Build SRT from narration_per_slide.json slides and per_slide_durations.
    narration_slides: list of {slide_index, narration_text, ...}
    per_slide_durations: {slide_index: duration_seconds}
    """
    texts: list[str] = []
    durations: list[float] = []
    for i in range(slide_count):
        si = i + 1
        text = ""
        for s in narration_slides:
            if s.get("slide_index") == si:
                text = s.get("narration_text", "") or ""
                break
        texts.append(text)
        durations.append(per_slide_durations.get(si, 2.0))
    return generate_srt(texts, durations, offset_seconds)
