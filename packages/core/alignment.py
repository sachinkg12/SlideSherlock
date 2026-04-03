"""
Timing/alignment (Fig3 step 15).
If TTS available: align; else estimate durations per sentence/word.
Output: timing/alignment.json with t_start, t_end per segment.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

# Words per minute for duration estimate when TTS not available
DEFAULT_WPM = 150
MIN_SEGMENT_DURATION = 1.0
MAX_SEGMENT_DURATION = 15.0


def estimate_duration_seconds(text: str, wpm: float = DEFAULT_WPM) -> float:
    """Estimate duration in seconds from word count."""
    words = (text or "").split()
    n = len(words)
    if n == 0:
        return MIN_SEGMENT_DURATION
    sec = (n / wpm) * 60.0
    return max(MIN_SEGMENT_DURATION, min(MAX_SEGMENT_DURATION, sec))


def build_alignment(
    job_id: str,
    verified_script: Dict[str, Any],
    segment_timestamps: Optional[List[Dict[str, Any]]] = None,
    per_slide_durations: Optional[Dict[int, float]] = None,
    wpm: float = DEFAULT_WPM,
) -> Dict[str, Any]:
    """
    Build timing/alignment.json.
    If segment_timestamps: use t_start/t_end per segment.
    Elif per_slide_durations: distribute each slide's duration among its segments by word count.
    Else: estimate duration per segment from word count, cumulative.
    """
    segments = verified_script.get("segments", [])
    entries: List[Dict[str, Any]] = []
    t_current = 0.0

    if per_slide_durations:
        from collections import defaultdict
        by_slide: Dict[int, List[tuple]] = defaultdict(list)
        for i, seg in enumerate(segments):
            si = seg.get("slide_index", 0)
            wc = len((seg.get("text") or "").split())
            by_slide[si].append((i, seg, wc))
        slide_starts: Dict[int, float] = {}
        t = 0.0
        for si in sorted(by_slide.keys()):
            slide_starts[si] = t
            t += per_slide_durations.get(si, 2.0)
        segment_entries: List[tuple] = []
        for si in sorted(by_slide.keys()):
            slide_dur = per_slide_durations.get(si, 2.0)
            items = by_slide[si]
            total_words = sum(wc for _, _, wc in items) or 1
            t_start = slide_starts[si]
            for i, seg, wc in items:
                duration = slide_dur * (wc / total_words) if total_words else slide_dur / len(items)
                duration = max(MIN_SEGMENT_DURATION, min(duration, slide_dur))
                t_end = t_start + duration
                segment_entries.append((i, {
                    "claim_id": seg.get("claim_id", ""),
                    "slide_index": si,
                    "segment_index": i,
                    "t_start": round(t_start, 3),
                    "t_end": round(t_end, 3),
                    "duration": round(duration, 3),
                }))
                t_start = t_end
        entries = [e for _, e in sorted(segment_entries, key=lambda x: x[0])]
        t_current = sum(per_slide_durations.values()) if per_slide_durations else t_current
    else:
        for i, seg in enumerate(segments):
            claim_id = seg.get("claim_id", "")
            slide_index = seg.get("slide_index", 0)
            text = seg.get("text", "")

            if segment_timestamps and i < len(segment_timestamps):
                ts = segment_timestamps[i]
                t_start = float(ts.get("t_start", t_current))
                t_end = float(ts.get("t_end", t_start + estimate_duration_seconds(text, wpm)))
            else:
                t_start = t_current
                duration = estimate_duration_seconds(text, wpm)
                t_end = t_start + duration

            entries.append({
                "claim_id": claim_id,
                "slide_index": slide_index,
                "segment_index": i,
                "t_start": round(t_start, 3),
                "t_end": round(t_end, 3),
                "duration": round(t_end - t_start, 3),
            })
            t_current = t_end

    if per_slide_durations and not entries:
        t_current = sum(per_slide_durations.values())

    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "segments": entries,
        "total_duration_seconds": round(t_current, 3),
        "source": "tts" if segment_timestamps else ("per_slide_audio" if per_slide_durations else "estimated"),
        "wpm": wpm if not (segment_timestamps or per_slide_durations) else None,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
