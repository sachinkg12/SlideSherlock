"""
On-screen notes config: layout template and styling.
Env: ON_SCREEN_NOTES_ENABLED, ON_SCREEN_NOTES_LAYOUT, ON_SCREEN_NOTES_FONT_SIZE, etc.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Tuple

# Layout identifiers
LAYOUT_OFF = "off"
LAYOUT_BOTTOM_STRIP = "bottom_strip"
LAYOUT_LOWER_THIRD = "lower_third"
LAYOUT_SIDE_RIGHT = "side_right"
LAYOUT_SIDE_LEFT = "side_left"

VALID_LAYOUTS = (
    LAYOUT_OFF,
    LAYOUT_BOTTOM_STRIP,
    LAYOUT_LOWER_THIRD,
    LAYOUT_SIDE_RIGHT,
    LAYOUT_SIDE_LEFT,
)

# Defaults
DEFAULT_FONT_SIZE = 28
DEFAULT_COLOR_HEX = "ffffff"
DEFAULT_BACKGROUND_RGBA = (0, 0, 0, 180)
DEFAULT_PADDING_PX = 16
DEFAULT_MAX_LINES = 4
DEFAULT_MAX_WIDTH_RATIO = 0.9  # fraction of frame width for text area


def _parse_color_hex(hex_str: str) -> Tuple[int, int, int]:
    """Parse #RRGGBB or RRGGBB to (r, g, b)."""
    s = (hex_str or "").strip().lstrip("#")
    if len(s) >= 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    return (255, 255, 255)


def _parse_rgba(rgba_str: str) -> Tuple[int, int, int, int]:
    """Parse 'r,g,b,a' to (r,g,b,a). Default semi-transparent black."""
    s = (rgba_str or "").strip()
    if not s:
        return DEFAULT_BACKGROUND_RGBA
    parts = [p.strip() for p in s.split(",")]
    if len(parts) >= 4:
        return (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    if len(parts) == 3:
        return (int(parts[0]), int(parts[1]), int(parts[2]), 180)
    return DEFAULT_BACKGROUND_RGBA


def resolve_notes_font_for_variant(variant_id: str, lang: str) -> str | None:
    """
    Resolve font path for on-screen notes per variant.
    Checks: NOTES_FONT_{VARIANT_ID}, NOTES_FONT_{LANG} (e.g. NOTES_FONT_HI_IN), ON_SCREEN_NOTES_FONT_PATH.
    Use a font that supports Latin + Devanagari (e.g. Noto Sans, Noto Sans Devanagari) for non-Latin scripts.
    """
    v = (variant_id or "").upper().replace("-", "_")
    lang_key = (lang or "en-US").upper().replace("-", "_")
    for key in (f"NOTES_FONT_{v}", f"NOTES_FONT_{lang_key}", "ON_SCREEN_NOTES_FONT_PATH"):
        p = os.environ.get(key)
        if p and os.path.isfile(p):
            return p
    return None


@dataclass
class OnScreenNotesConfig:
    """Configuration for rendering on-screen notes (narration text) on video frames."""

    enabled: bool
    layout: str  # off | bottom_strip | lower_third | side_right | side_left
    font_size: int
    color_hex: str  # e.g. "ffffff"
    color_rgb: Tuple[int, int, int]
    background_rgba: Tuple[int, int, int, int]
    padding_px: int
    max_lines: int
    max_width_ratio: float  # 0..1, fraction of frame width for text block
    font_file: str | None = None  # optional .ttf path for non-Latin scripts (e.g. Noto Sans)

    @classmethod
    def from_env(cls) -> "OnScreenNotesConfig":
        enabled = (os.environ.get("ON_SCREEN_NOTES_ENABLED", "0")).strip().lower() in (
            "1",
            "true",
            "yes",
        )
        layout = (os.environ.get("ON_SCREEN_NOTES_LAYOUT", LAYOUT_BOTTOM_STRIP)).strip().lower()
        if layout not in VALID_LAYOUTS:
            layout = LAYOUT_BOTTOM_STRIP
        if layout == LAYOUT_OFF:
            enabled = False
        font_size = int(os.environ.get("ON_SCREEN_NOTES_FONT_SIZE", str(DEFAULT_FONT_SIZE)))
        font_size = max(12, min(72, font_size))
        color_hex = (os.environ.get("ON_SCREEN_NOTES_COLOR", DEFAULT_COLOR_HEX)).strip().lstrip("#")
        if len(color_hex) < 6:
            color_hex = DEFAULT_COLOR_HEX
        color_rgb = _parse_color_hex(color_hex)
        bg_str = os.environ.get("ON_SCREEN_NOTES_BACKGROUND_RGBA", "")
        background_rgba = _parse_rgba(bg_str)
        padding_px = int(os.environ.get("ON_SCREEN_NOTES_PADDING", str(DEFAULT_PADDING_PX)))
        padding_px = max(4, min(64, padding_px))
        max_lines = int(os.environ.get("ON_SCREEN_NOTES_MAX_LINES", str(DEFAULT_MAX_LINES)))
        max_lines = max(1, min(10, max_lines))
        max_width_ratio = float(
            os.environ.get("ON_SCREEN_NOTES_MAX_WIDTH_RATIO", str(DEFAULT_MAX_WIDTH_RATIO))
        )
        max_width_ratio = max(0.2, min(1.0, max_width_ratio))
        font_file = os.environ.get("ON_SCREEN_NOTES_FONT_PATH")
        if font_file and not os.path.isfile(font_file):
            font_file = None
        return cls(
            enabled=enabled,
            layout=layout,
            font_size=font_size,
            color_hex=color_hex,
            color_rgb=color_rgb,
            background_rgba=background_rgba,
            padding_px=padding_px,
            max_lines=max_lines,
            max_width_ratio=max_width_ratio,
            font_file=font_file,
        )
