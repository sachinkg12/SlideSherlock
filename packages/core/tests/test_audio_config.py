"""
Unit tests for audio_config.py: AudioConfig.from_env(), constants, defaults.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from audio_config import (
    AudioConfig,
    AUDIO_MODE_USE_SUPPLIED,
    AUDIO_MODE_GENERATE,
    AUDIO_VOICE_LOCAL,
    AUDIO_VOICE_OPENAI,
    AUDIO_VOICE_ELEVENLABS,
    DEFAULT_LUFS_TARGET,
    DEFAULT_SAMPLE_RATE,
)


def test_defaults_when_no_env_set():
    """No env vars set -> generate mode, local voice, loudness normalize on."""
    keys = [
        "AUDIO_MODE", "AUDIO_VOICE_PROVIDER", "AUDIO_LOUDNESS_NORMALIZE",
        "AUDIO_LUFS_TARGET", "AUDIO_SAMPLE_RATE",
    ]
    env_patch = {k: "" for k in keys}
    with patch.dict(os.environ, env_patch, clear=False):
        for k in keys:
            os.environ.pop(k, None)
        cfg = AudioConfig.from_env()
    assert cfg.mode == AUDIO_MODE_GENERATE
    assert cfg.voice_provider == AUDIO_VOICE_LOCAL
    assert cfg.loudness_normalize is True
    assert cfg.lufs_target == DEFAULT_LUFS_TARGET
    assert cfg.sample_rate == DEFAULT_SAMPLE_RATE


def test_mode_use_supplied():
    """AUDIO_MODE=use_supplied is accepted."""
    with patch.dict(os.environ, {"AUDIO_MODE": "use_supplied"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.mode == AUDIO_MODE_USE_SUPPLIED


def test_mode_generate_explicit():
    """AUDIO_MODE=generate is accepted."""
    with patch.dict(os.environ, {"AUDIO_MODE": "generate"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.mode == AUDIO_MODE_GENERATE


def test_invalid_mode_falls_back_to_generate():
    """An unrecognized AUDIO_MODE falls back to generate."""
    with patch.dict(os.environ, {"AUDIO_MODE": "nonsense"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.mode == AUDIO_MODE_GENERATE


def test_voice_provider_openai():
    """AUDIO_VOICE_PROVIDER=openai is accepted."""
    with patch.dict(os.environ, {"AUDIO_VOICE_PROVIDER": "openai"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.voice_provider == AUDIO_VOICE_OPENAI


def test_voice_provider_elevenlabs():
    """AUDIO_VOICE_PROVIDER=elevenlabs is accepted."""
    with patch.dict(os.environ, {"AUDIO_VOICE_PROVIDER": "elevenlabs"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.voice_provider == AUDIO_VOICE_ELEVENLABS


def test_invalid_voice_provider_falls_back_to_local():
    """An unrecognized AUDIO_VOICE_PROVIDER falls back to local."""
    with patch.dict(os.environ, {"AUDIO_VOICE_PROVIDER": "mystery_tts"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.voice_provider == AUDIO_VOICE_LOCAL


def test_loudness_normalize_disabled_via_zero():
    """AUDIO_LOUDNESS_NORMALIZE=0 -> loudness_normalize False."""
    with patch.dict(os.environ, {"AUDIO_LOUDNESS_NORMALIZE": "0"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.loudness_normalize is False


def test_loudness_normalize_enabled_via_true():
    """AUDIO_LOUDNESS_NORMALIZE=true -> loudness_normalize True."""
    with patch.dict(os.environ, {"AUDIO_LOUDNESS_NORMALIZE": "true"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.loudness_normalize is True


def test_custom_lufs_target():
    """AUDIO_LUFS_TARGET=-23.0 is parsed correctly."""
    with patch.dict(os.environ, {"AUDIO_LUFS_TARGET": "-23.0"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.lufs_target == -23.0


def test_custom_sample_rate():
    """AUDIO_SAMPLE_RATE=44100 is parsed correctly."""
    with patch.dict(os.environ, {"AUDIO_SAMPLE_RATE": "44100"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.sample_rate == 44100


def test_mode_is_case_insensitive():
    """AUDIO_MODE accepts uppercase input."""
    with patch.dict(os.environ, {"AUDIO_MODE": "GENERATE"}, clear=False):
        cfg = AudioConfig.from_env()
    assert cfg.mode == AUDIO_MODE_GENERATE


def test_constants_have_expected_values():
    """Spot-check the exported constants."""
    assert DEFAULT_LUFS_TARGET == -16.0
    assert DEFAULT_SAMPLE_RATE == 48000
    assert AUDIO_MODE_USE_SUPPLIED == "use_supplied"
    assert AUDIO_MODE_GENERATE == "generate"
