"""
Unit tests for on-screen notes config (layout + styling from env).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notes_config import (
    OnScreenNotesConfig,
    resolve_notes_font_for_variant,
    LAYOUT_OFF,
    LAYOUT_BOTTOM_STRIP,
    LAYOUT_LOWER_THIRD,
    LAYOUT_SIDE_RIGHT,
    LAYOUT_SIDE_LEFT,
    VALID_LAYOUTS,
)


def test_default_disabled():
    """When ON_SCREEN_NOTES_ENABLED not set, enabled is False."""
    with patch.dict(os.environ, {}, clear=False):
        if "ON_SCREEN_NOTES_ENABLED" in os.environ:
            del os.environ["ON_SCREEN_NOTES_ENABLED"]
        c = OnScreenNotesConfig.from_env()
    assert c.enabled is False
    assert c.layout in VALID_LAYOUTS


def test_enabled_via_env():
    """ON_SCREEN_NOTES_ENABLED=1 -> enabled True."""
    with patch.dict(os.environ, {"ON_SCREEN_NOTES_ENABLED": "1"}, clear=False):
        c = OnScreenNotesConfig.from_env()
    assert c.enabled is True
    assert c.layout == LAYOUT_BOTTOM_STRIP


def test_layout_lower_third():
    """ON_SCREEN_NOTES_LAYOUT=lower_third is accepted."""
    with patch.dict(
        os.environ,
        {"ON_SCREEN_NOTES_ENABLED": "1", "ON_SCREEN_NOTES_LAYOUT": "lower_third"},
        clear=False,
    ):
        c = OnScreenNotesConfig.from_env()
    assert c.enabled is True
    assert c.layout == LAYOUT_LOWER_THIRD


def test_layout_off_disables():
    """ON_SCREEN_NOTES_LAYOUT=off forces enabled False."""
    with patch.dict(
        os.environ, {"ON_SCREEN_NOTES_ENABLED": "1", "ON_SCREEN_NOTES_LAYOUT": "off"}, clear=False
    ):
        c = OnScreenNotesConfig.from_env()
    assert c.enabled is False
    assert c.layout == LAYOUT_OFF


def test_font_size_bounds():
    """Font size clamped to 12–72."""
    with patch.dict(
        os.environ,
        {"ON_SCREEN_NOTES_ENABLED": "0", "ON_SCREEN_NOTES_FONT_SIZE": "100"},
        clear=False,
    ):
        c = OnScreenNotesConfig.from_env()
    assert c.font_size == 72
    with patch.dict(os.environ, {"ON_SCREEN_NOTES_FONT_SIZE": "8"}, clear=False):
        c2 = OnScreenNotesConfig.from_env()
    assert c2.font_size == 12


def test_color_and_background():
    """Color hex and background RGBA parsed."""
    with patch.dict(
        os.environ,
        {
            "ON_SCREEN_NOTES_ENABLED": "0",
            "ON_SCREEN_NOTES_COLOR": "ff0000",
            "ON_SCREEN_NOTES_BACKGROUND_RGBA": "0,0,0,200",
        },
        clear=False,
    ):
        c = OnScreenNotesConfig.from_env()
    assert c.color_rgb == (255, 0, 0)
    assert c.background_rgba == (0, 0, 0, 200)


def test_side_layouts():
    """side_right and side_left are valid."""
    with patch.dict(
        os.environ,
        {"ON_SCREEN_NOTES_ENABLED": "1", "ON_SCREEN_NOTES_LAYOUT": "side_right"},
        clear=False,
    ):
        c = OnScreenNotesConfig.from_env()
    assert c.layout == LAYOUT_SIDE_RIGHT
    with patch.dict(os.environ, {"ON_SCREEN_NOTES_LAYOUT": "side_left"}, clear=False):
        c2 = OnScreenNotesConfig.from_env()
    assert c2.layout == LAYOUT_SIDE_LEFT


def test_resolve_notes_font_for_variant():
    """Per-variant and per-lang font resolution."""
    with patch.dict(os.environ, {}, clear=False):
        for k in ("NOTES_FONT_L2", "NOTES_FONT_HI_IN", "ON_SCREEN_NOTES_FONT_PATH"):
            os.environ.pop(k, None)
    # No font set -> None
    assert resolve_notes_font_for_variant("l2", "hi-IN") is None
    with patch.dict(os.environ, {"ON_SCREEN_NOTES_FONT_PATH": "/nonexistent.ttf"}, clear=False):
        # Non-existent file -> None (we check os.path.isfile)
        assert resolve_notes_font_for_variant("en", "en-US") is None
