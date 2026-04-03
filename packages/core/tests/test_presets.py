"""
Unit tests for quality presets.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from presets import (
    get_preset_env_vars,
    apply_preset,
    get_current_preset,
    PRESET_DRAFT,
    PRESET_STANDARD,
    PRESET_PRO,
)


def test_get_preset_env_vars_draft():
    """Draft preset: no vision, no bgm, cut transitions."""
    env = get_preset_env_vars(PRESET_DRAFT)
    assert env.get("VISION_ENABLED") == "0"
    assert env.get("AUDIO_BGM_ENABLED") == "0"
    assert env.get("VIDEO_TRANSITION") == "cut"
    assert env.get("ON_SCREEN_NOTES_ENABLED") == "0"
    assert env.get("SUBTITLES_ENABLED") == "0"


def test_get_preset_env_vars_standard():
    """Standard preset: notes overlay, crossfade, subtitles."""
    env = get_preset_env_vars(PRESET_STANDARD)
    assert env.get("ON_SCREEN_NOTES_ENABLED") == "1"
    assert env.get("VIDEO_TRANSITION") == "crossfade"
    assert env.get("SUBTITLES_ENABLED") == "1"
    assert env.get("AUDIO_LOUDNESS_NORMALIZE") == "1"


def test_get_preset_env_vars_pro():
    """Pro preset: vision, bgm ducking, loudness normalize."""
    env = get_preset_env_vars(PRESET_PRO)
    assert env.get("VISION_ENABLED") == "1"
    assert env.get("AUDIO_BGM_ENABLED") == "1"
    assert env.get("AUDIO_BGM_DUCKING") == "1"
    assert env.get("AUDIO_LOUDNESS_NORMALIZE") == "1"


def test_apply_preset_sets_env():
    """apply_preset sets os.environ."""
    with patch.dict(os.environ, {}, clear=False):
        apply_preset(PRESET_DRAFT)
        assert os.environ.get("VIDEO_TRANSITION") == "cut"
        assert os.environ.get("VISION_ENABLED") == "0"


def test_get_current_preset_from_env():
    """get_current_preset returns SLIDESHERLOCK_PRESET if valid."""
    with patch.dict(os.environ, {"SLIDESHERLOCK_PRESET": PRESET_STANDARD}, clear=False):
        assert get_current_preset() == PRESET_STANDARD
    with patch.dict(os.environ, {"SLIDESHERLOCK_PRESET": "invalid"}, clear=False):
        assert get_current_preset() is None
