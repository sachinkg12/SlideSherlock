"""Unit tests for video production config."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from video_config import VideoConfig, TRANSITION_CUT, TRANSITION_CROSSFADE


def test_default_transition_crossfade():
    """Default transition is crossfade."""
    with patch.dict(os.environ, {}, clear=True):
        for k in list(os.environ.keys()):
            if k.startswith("VIDEO_") or k.startswith("SUBTITLES_") or k.startswith("AUDIO_BGM"):
                del os.environ[k]
        c = VideoConfig.from_env()
    assert c.transition == TRANSITION_CROSSFADE
    assert c.transition_ms == 300


def test_transition_cut():
    """VIDEO_TRANSITION=cut is accepted."""
    with patch.dict(os.environ, {"VIDEO_TRANSITION": "cut"}, clear=False):
        c = VideoConfig.from_env()
    assert c.transition == TRANSITION_CUT


def test_intro_outro_disabled_by_default():
    """Intro and outro disabled by default."""
    with patch.dict(os.environ, {}, clear=True):
        c = VideoConfig.from_env()
    assert c.intro_enabled is False
    assert c.outro_enabled is False


def test_intro_enabled():
    """VIDEO_INTRO_ENABLED=1 enables intro."""
    with patch.dict(os.environ, {"VIDEO_INTRO_ENABLED": "1", "VIDEO_INTRO_TITLE": "My Deck"}, clear=False):
        c = VideoConfig.from_env()
    assert c.intro_enabled is True
    assert c.intro_title == "My Deck"
