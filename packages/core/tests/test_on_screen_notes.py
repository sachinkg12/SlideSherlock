"""
Unit tests for on-screen notes drawing (overlay_renderer).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image


def test_draw_notes_on_image_empty_text_no_crash():
    """draw_notes_on_image with empty text does not crash."""
    from overlay_renderer import draw_notes_on_image
    from notes_config import OnScreenNotesConfig

    img = Image.new("RGBA", (320, 180), (0, 0, 0, 0))
    config = OnScreenNotesConfig(
        enabled=True,
        layout="bottom_strip",
        font_size=24,
        color_hex="ffffff",
        color_rgb=(255, 255, 255),
        background_rgba=(0, 0, 0, 180),
        padding_px=12,
        max_lines=3,
        max_width_ratio=0.9,
    )
    draw_notes_on_image(img, "", 320, 180, config)
    draw_notes_on_image(img, "   ", 320, 180, config)


def test_draw_notes_on_image_with_text():
    """draw_notes_on_image with text and enabled config draws without crashing."""
    from overlay_renderer import draw_notes_on_image
    from notes_config import OnScreenNotesConfig

    img = Image.new("RGBA", (640, 360), (255, 255, 255, 255))
    config = OnScreenNotesConfig(
        enabled=True,
        layout="bottom_strip",
        font_size=24,
        color_hex="ffffff",
        color_rgb=(255, 255, 255),
        background_rgba=(0, 0, 0, 200),
        padding_px=16,
        max_lines=4,
        max_width_ratio=0.9,
    )
    draw_notes_on_image(img, "This is a short note for the slide.", 640, 360, config)
    # Image should have been modified (some non-white pixels in lower area)
    pixels = list(img.getdata())
    dark_pixels = [p for p in pixels if p[3] > 0 and (p[0] < 250 or p[1] < 250 or p[2] < 250)]
    assert len(dark_pixels) > 0, "Expected some drawn pixels (background or text)"


def test_draw_notes_disabled_does_nothing():
    """When config.enabled is False, draw_notes_on_image does not modify image."""
    from overlay_renderer import draw_notes_on_image
    from notes_config import OnScreenNotesConfig

    img = Image.new("RGBA", (100, 100), (200, 200, 200, 255))
    config = OnScreenNotesConfig(
        enabled=False,
        layout="bottom_strip",
        font_size=24,
        color_hex="ffffff",
        color_rgb=(255, 255, 255),
        background_rgba=(0, 0, 0, 180),
        padding_px=16,
        max_lines=4,
        max_width_ratio=0.9,
    )
    before = img.tobytes()
    draw_notes_on_image(img, "Some text", 100, 100, config)
    assert img.tobytes() == before


def test_wrap_text_to_lines():
    """_wrap_text_to_lines returns at most max_lines."""
    from overlay_renderer import _wrap_text_to_lines
    from PIL import ImageDraw, ImageFont

    img = Image.new("RGBA", (400, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    lines = _wrap_text_to_lines("One two three four five six seven eight nine ten", draw, font, 200, 3)
    assert len(lines) <= 3
    assert len(lines) >= 1
