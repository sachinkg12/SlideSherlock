"""
Video encoder selection — picks the best H.264 encoder for the host.

On Apple Silicon macOS with VideoToolbox available, returns
``h264_videotoolbox`` (hardware-accelerated, ~5-10× faster than libx264 for
the SlideSherlock workload, ~40% larger files at comparable visual quality —
acceptable for batch research data and end-user demos).

Everywhere else (Linux CI, Intel macs, Windows) falls back to ``libx264``,
which is ffmpeg's universally available software H.264 encoder.

Override with ``SLIDESHERLOCK_VIDEO_ENCODER=libx264`` (or any other
ffmpeg-known encoder name) if you need to force a specific encoder — for
example to keep batch outputs bit-comparable across different hosts.

Usage::

    from video_encoder import get_video_encoder, get_video_encoder_args
    cmd = ["ffmpeg", "-y", ..., "-c:v", get_video_encoder(),
           *get_video_encoder_args(), "-pix_fmt", "yuv420p", out_path]
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache
from typing import List, Tuple


# Public API ----------------------------------------------------------------


def get_video_encoder() -> str:
    """Return the ffmpeg `-c:v` value to use for H.264 encoding."""
    return _resolve()[0]


def get_video_encoder_args() -> List[str]:
    """Return extra ffmpeg args (after `-c:v ENCODER`) for the chosen encoder.

    For libx264 this is ``[]`` (preset/crf can be set by callers if they want).
    For h264_videotoolbox this is the quality flag, since VT uses ``-q:v``
    instead of ``-crf`` and does not accept ``-preset``.
    """
    return list(_resolve()[1])


def encoder_supports_preset() -> bool:
    """True if the active encoder accepts `-preset` (libx264 yes, VT no)."""
    return get_video_encoder() == "libx264"


# Internals -----------------------------------------------------------------


def _resolve() -> Tuple[str, List[str]]:
    override = (os.environ.get("SLIDESHERLOCK_VIDEO_ENCODER") or "").strip()
    if override:
        return override, _args_for(override)
    if _videotoolbox_available():
        return "h264_videotoolbox", _args_for("h264_videotoolbox")
    return "libx264", _args_for("libx264")


def _args_for(encoder: str) -> List[str]:
    if encoder == "h264_videotoolbox":
        # -q:v on VideoToolbox is 1 (best) … 100 (worst). 60 is roughly the
        # equivalent of libx264 -crf 23 visually, with the encoder's own
        # rate control kicking in.
        return ["-q:v", "60"]
    # libx264 / others — let callers add their own preset/crf if they want.
    return []


@lru_cache(maxsize=1)
def _videotoolbox_available() -> bool:
    """True iff host is macOS arm64 AND ffmpeg has the h264_videotoolbox encoder."""
    if platform.system() != "Darwin":
        return False
    if platform.machine() not in ("arm64", "aarch64"):
        # VideoToolbox also exists on Intel macs but the speedup is smaller
        # and the codepath is less tested. Be conservative.
        return False
    if shutil.which("ffmpeg") is None:
        return False
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return False
    return "h264_videotoolbox" in out
