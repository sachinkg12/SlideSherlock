"""
Audio processing: normalize loudness (-16 LUFS), trim long silences, resample to 48kHz.
Uses FFmpeg for stability.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Optional

# Target LUFS (broadcast-ish)
DEFAULT_LUFS_TARGET = -16.0
DEFAULT_SAMPLE_RATE = 48000
# Silence threshold: trim silence longer than this (seconds) at start/end
SILENCE_DURATION_THRESHOLD = 0.5
# FFmpeg silenceremove: noise floor in dB
SILENCE_NOISE = "-40dB"


def process_audio(
    input_path: str,
    output_path: str,
    loudness_normalize: bool = True,
    lufs_target: float = DEFAULT_LUFS_TARGET,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    trim_silence: bool = True,
) -> float:
    """
    Normalize loudness, optional trim long silences, resample to sample_rate.
    Returns duration in seconds of output file.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)
    filters = []
    if trim_silence:
        filters.append(f"silenceremove=start_periods=1:start_duration={SILENCE_DURATION_THRESHOLD}:start_threshold={SILENCE_NOISE}")
    filters.append(f"aresample={sample_rate}")
    if loudness_normalize:
        filters.append(f"loudnorm=I={lufs_target}:LRA=11:TP=-1.5")
    filter_str = ",".join(filters)
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-af", filter_str, "-ar", str(sample_rate), "-ac", "1", output_path],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return _get_duration_seconds(output_path) or 0.0


def apply_audio_fade(
    input_path: str,
    output_path: str,
    fade_ms: int = 100,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> float:
    """
    Apply fade-in and fade-out to audio (avoids clicks at transitions).
    fade_ms: duration of fade at start and end, in milliseconds.
    Returns duration in seconds of output.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)
    dur = _get_duration_seconds(input_path) or 0.0
    fade_sec = max(0.001, min(0.5, fade_ms / 1000.0))
    st_out = max(0, dur - fade_sec)
    af = f"afade=t=in:st=0:d={fade_sec},afade=t=out:st={st_out:.3f}:d={fade_sec},aresample={sample_rate}"
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-af", af, "-ar", str(sample_rate), "-ac", "1", output_path],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return _get_duration_seconds(output_path) or dur


def _get_duration_seconds(path: str) -> Optional[float]:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def process_audio_simple(
    input_path: str,
    output_path: str,
    loudness_normalize: bool = True,
    lufs_target: float = DEFAULT_LUFS_TARGET,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> float:
    """
    Simpler pipeline: resample + optional loudnorm (no silenceremove to avoid filter_complex).
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)
    if loudness_normalize:
        af = f"loudnorm=I={lufs_target}:LRA=11:TP=-1.5,aresample={sample_rate}"
    else:
        af = f"aresample={sample_rate}"
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-af", af, "-ar", str(sample_rate), "-ac", "1", output_path],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return _get_duration_seconds(output_path) or 0.0
