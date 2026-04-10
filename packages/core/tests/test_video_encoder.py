"""Tests for the video_encoder helper."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import video_encoder  # noqa: E402


def _clear_cache():
    video_encoder._videotoolbox_available.cache_clear()


def test_override_libx264(monkeypatch):
    monkeypatch.setenv("SLIDESHERLOCK_VIDEO_ENCODER", "libx264")
    _clear_cache()
    assert video_encoder.get_video_encoder() == "libx264"
    assert video_encoder.get_video_encoder_args() == []
    assert video_encoder.encoder_supports_preset() is True


def test_override_videotoolbox(monkeypatch):
    monkeypatch.setenv("SLIDESHERLOCK_VIDEO_ENCODER", "h264_videotoolbox")
    _clear_cache()
    assert video_encoder.get_video_encoder() == "h264_videotoolbox"
    assert "-q:v" in video_encoder.get_video_encoder_args()
    assert video_encoder.encoder_supports_preset() is False


def test_override_arbitrary_encoder(monkeypatch):
    """Allow forcing any ffmpeg-known encoder name via env."""
    monkeypatch.setenv("SLIDESHERLOCK_VIDEO_ENCODER", "h264_nvenc")
    _clear_cache()
    assert video_encoder.get_video_encoder() == "h264_nvenc"
    # Unknown encoder → no extra args; caller can supply their own.
    assert video_encoder.get_video_encoder_args() == []


def test_default_picks_something(monkeypatch):
    """With no override, return either libx264 or h264_videotoolbox depending on host."""
    monkeypatch.delenv("SLIDESHERLOCK_VIDEO_ENCODER", raising=False)
    _clear_cache()
    enc = video_encoder.get_video_encoder()
    assert enc in ("libx264", "h264_videotoolbox")


def test_videotoolbox_args_format(monkeypatch):
    monkeypatch.setenv("SLIDESHERLOCK_VIDEO_ENCODER", "h264_videotoolbox")
    _clear_cache()
    args = video_encoder.get_video_encoder_args()
    # Should be a list of strings, no None / non-string values
    assert all(isinstance(a, str) for a in args)
    # -q:v must be paired with a value
    assert len(args) % 2 == 0
