"""
Overlay renderer (Fig3 step 17, Fig7).
Produce overlays/slide_i_overlay.mp4 (or frames) from timeline actions.
Draws HIGHLIGHT (bbox), TRACE (path) on transparent overlay; encodes to MP4.
Optional: on-screen notes (narration text) with layout templates and styling.
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional

# Note: per-slide overlays use libx264 directly (not get_video_encoder())
# to ensure all slides have matching H.264 profiles for concat -c copy.
# The video_encoder module is only used by composer.py for xfade compose.

OVERLAY_FPS = 15
HIGHLIGHT_COLOR = (0, 255, 100, 180)
TRACE_COLOR = (255, 200, 0, 220)
LINE_WIDTH = 4


def _draw_highlight(
    img: Any,
    bbox: Dict[str, float],
    outline_width: int = 3,
) -> None:
    """Draw semi-transparent rectangle on PIL Image (RGBA)."""
    from PIL import ImageDraw

    x, y = int(bbox.get("x", 0)), int(bbox.get("y", 0))
    w, h = int(bbox.get("w", 0)), int(bbox.get("h", 0))
    if w <= 0 or h <= 0:
        return
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle(
        [x, y, x + w, y + h],
        outline=HIGHLIGHT_COLOR,
        width=outline_width,
        fill=(HIGHLIGHT_COLOR[0], HIGHLIGHT_COLOR[1], HIGHLIGHT_COLOR[2], 40),
    )


def _draw_trace(
    img: Any,
    path: List[Dict[str, float]],
    width: int = LINE_WIDTH,
) -> None:
    """Draw line along path on PIL Image (RGBA)."""
    from PIL import ImageDraw

    if len(path) < 2:
        return
    draw = ImageDraw.Draw(img, "RGBA")
    pts = [(int(p.get("x", 0)), int(p.get("y", 0))) for p in path]
    draw.line(pts, fill=TRACE_COLOR, width=width)


def _wrap_text_to_lines(
    text: str,
    draw: Any,
    font: Any,
    max_width_px: int,
    max_lines: int,
) -> List[str]:
    """Wrap text into lines that fit within max_width_px, up to max_lines."""
    text = (text or "").strip()
    if not text:
        return []
    words = re.split(r"\s+", text)
    lines: List[str] = []
    current: List[str] = []
    for w in words:
        current.append(w)
        line = " ".join(current)
        bbox = draw.textbbox((0, 0), line, font=font)
        w_px = bbox[2] - bbox[0]
        if w_px <= max_width_px:
            continue
        if len(current) > 1:
            current.pop()
            lines.append(" ".join(current))
            if len(lines) >= max_lines:
                return lines
            current = [w]
        else:
            lines.append(line)
            if len(lines) >= max_lines:
                return lines
            current = []
    if current:
        lines.append(" ".join(current))
    return lines[:max_lines]


def _get_notes_font(font_size: int, font_path: Optional[str] = None) -> Any:
    """Load font for notes. Prefer font_path if set, else default bitmap."""
    from PIL import ImageFont

    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            pass
    try:
        return ImageFont.load_default()
    except Exception:
        pass
    return ImageFont.load_default()


def draw_notes_on_image(
    img: Any,
    notes_text: str,
    width: int,
    height: int,
    config: Any,
    font_path: Optional[str] = None,
) -> None:
    """
    Draw on-screen notes on a PIL Image (RGBA) in-place.
    config: OnScreenNotesConfig (layout, font_size, color_rgb, background_rgba, padding_px, max_lines, max_width_ratio).
    """
    if not notes_text or not config or not getattr(config, "enabled", True):
        return
    from PIL import ImageDraw
    from notes_config import (
        LAYOUT_BOTTOM_STRIP,
        LAYOUT_LOWER_THIRD,
        LAYOUT_SIDE_RIGHT,
        LAYOUT_SIDE_LEFT,
    )

    layout = getattr(config, "layout", LAYOUT_BOTTOM_STRIP)
    font_size = getattr(config, "font_size", 28)
    color_rgb = getattr(config, "color_rgb", (255, 255, 255))
    background_rgba = getattr(config, "background_rgba", (0, 0, 0, 180))
    padding_px = getattr(config, "padding_px", 16)
    max_lines = getattr(config, "max_lines", 4)
    max_width_ratio = getattr(config, "max_width_ratio", 0.9)

    font = _get_notes_font(font_size, font_path)
    draw = ImageDraw.Draw(img, "RGBA")

    # Text area width in pixels (for wrapping)
    text_area_width = int(width * max_width_ratio) - 2 * padding_px
    text_area_width = max(80, text_area_width)
    lines = _wrap_text_to_lines(notes_text, draw, font, text_area_width, max_lines)
    if not lines:
        return

    # Line height from font
    line_height = int(font_size * 1.3)
    block_height = len(lines) * line_height + 2 * padding_px
    block_width = 0
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        block_width = max(block_width, bbox[2] - bbox[0])
    block_width = min(int(width * max_width_ratio), block_width + 2 * padding_px)
    block_width = max(block_width, 100)

    # Position by layout (x1, y1 = top-left of box)
    if layout in (LAYOUT_BOTTOM_STRIP, LAYOUT_LOWER_THIRD):
        # Bottom: leave small margin from bottom
        box_height = block_height
        x1 = (width - block_width) // 2
        y1 = height - box_height - max(20, height // 20)
        if layout == LAYOUT_LOWER_THIRD:
            y1 = height - int(height * 0.28)
            if y1 < height - box_height - 20:
                y1 = height - box_height - 20
    elif layout == LAYOUT_SIDE_RIGHT:
        x1 = width - block_width - max(20, width // 20)
        y1 = (height - block_height) // 2
    elif layout == LAYOUT_SIDE_LEFT:
        x1 = max(20, width // 20)
        y1 = (height - block_height) // 2
    else:
        x1 = (width - block_width) // 2
        y1 = height - block_height - max(20, height // 20)
    y1 = max(0, y1)
    x1 = max(0, min(x1, width - block_width))
    x2 = x1 + block_width
    y2 = y1 + block_height
    if y2 > height:
        y2 = height
        y1 = y2 - block_height

    draw.rectangle([x1, y1, x2, y2], fill=background_rgba, outline=(255, 255, 255, 100))
    text_color = (*color_rgb, 255)
    for i, ln in enumerate(lines):
        ty = y1 + padding_px + i * line_height
        draw.text((x1 + padding_px, ty), ln, fill=text_color, font=font)


def render_overlay_frames(
    width: int,
    height: int,
    actions: List[Dict[str, Any]],
    duration_seconds: float,
    fps: float = OVERLAY_FPS,
) -> List[bytes]:
    """
    Render overlay as list of PNG bytes per frame.
    actions: list with type, t_start, t_end, bbox or path (pixel coords).
    """
    from PIL import Image

    n_frames = max(1, int(duration_seconds * fps))
    frames: List[bytes] = []
    for i in range(n_frames):
        t = i / fps
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for act in actions:
            if act.get("t_start", 0) <= t <= act.get("t_end", 0):
                if act.get("type") == "HIGHLIGHT" and act.get("bbox"):
                    _draw_highlight(img, act["bbox"])
                elif act.get("type") == "TRACE" and act.get("path"):
                    _draw_trace(img, act["path"])
                elif act.get("type") == "ZOOM" and act.get("bbox"):
                    _draw_highlight(img, act["bbox"])
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        frames.append(buf.getvalue())
    return frames


def render_overlay_mp4(
    width: int,
    height: int,
    actions: List[Dict[str, Any]],
    duration_seconds: float,
    output_path: str,
    fps: float = OVERLAY_FPS,
) -> str:
    """
    Render overlay to MP4 file. Returns output_path.
    Uses imageio to encode frames (requires ffmpeg).
    """
    from PIL import Image

    try:
        import imageio
        import numpy as np
    except ImportError:
        raise RuntimeError(
            "imageio and numpy required for overlay MP4; pip install imageio imageio-ffmpeg numpy"
        )
    n_frames = max(1, int(duration_seconds * fps))
    # Use libx264 for per-slide overlays so all slides have matching H.264
    # profile for concat -c copy. VT is only used in crossfade compose step.
    writer = imageio.get_writer(
        output_path, fps=fps, codec="libx264", quality=8, pixelformat="yuv420p"
    )
    for i in range(n_frames):
        t = i / fps
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for act in actions:
            if act.get("t_start", 0) <= t <= act.get("t_end", 0):
                if act.get("type") == "HIGHLIGHT" and act.get("bbox"):
                    _draw_highlight(img, act["bbox"])
                elif act.get("type") == "TRACE" and act.get("path"):
                    _draw_trace(img, act["path"])
                elif act.get("type") == "ZOOM" and act.get("bbox"):
                    _draw_highlight(img, act["bbox"])
        arr = np.array(img)
        writer.append_data(arr)
    writer.close()
    return output_path


def render_slide_overlay(
    slide_image_bytes: bytes,
    timeline_actions: List[Dict[str, Any]],
    slide_duration_seconds: float,
    output_path: str,
    fps: float = OVERLAY_FPS,
) -> str:
    """
    Render overlay for one slide: same dimensions as slide PNG.
    timeline_actions: actions for this slide_index with bbox/path in pixels.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(slide_image_bytes))
    width, height = img.size
    return render_overlay_mp4(
        width, height, timeline_actions, slide_duration_seconds, output_path, fps=fps
    )


def render_slide_with_overlay_mp4(
    slide_image_bytes: bytes,
    timeline_actions: List[Dict[str, Any]],
    slide_duration_seconds: float,
    output_path: str,
    fps: float = OVERLAY_FPS,
    notes_text: Optional[str] = None,
    notes_config: Optional[Any] = None,
    notes_font_path: Optional[str] = None,
) -> str:
    """
    Composite slide PNG + overlay per frame and encode to MP4 (no alpha in output).
    If notes_config.enabled and notes_text is set, draws on-screen notes on each frame.
    Returns output_path. Used by composer for final concat.

    Fast path: when there are no timeline actions AND no on-screen notes,
    uses ffmpeg -loop 1 to create a static video from the slide PNG in
    ~0.5s instead of frame-by-frame rendering (18-45s per slide). This
    is the dominant speedup for large decks where most slides are static.
    """
    from PIL import Image

    draw_notes = (
        notes_config and getattr(notes_config, "enabled", False) and (notes_text or "").strip()
    )
    # Only count actions that have actual content (bbox/path) — empty actions are no-ops
    has_actions = any(
        act.get("type") in ("HIGHLIGHT", "TRACE", "ZOOM") and (act.get("bbox") or act.get("path"))
        for act in (timeline_actions or [])
    )

    if not has_actions:
        # Fast path for static slides: render one frame, repeat at 1fps.
        # A 30s slide = 30 frames instead of 450 (at 15fps). 15× faster,
        # works on all platforms (no ffmpeg -loop or lavfi tricks needed).
        try:
            import imageio
            import numpy as np
        except ImportError:
            raise RuntimeError("imageio and numpy required")
        base = Image.open(io.BytesIO(slide_image_bytes)).convert("RGBA")
        width, height = base.size
        frame = base.copy()
        if draw_notes:
            draw_notes_on_image(
                frame, (notes_text or "").strip(), width, height, notes_config, notes_font_path
            )
        arr = np.array(frame.convert("RGB"))
        # Use 1fps for static content — massively fewer frames to encode.
        # The final video is re-encoded during crossfade/concat anyway.
        static_fps = 1
        n_frames = max(1, int(slide_duration_seconds * static_fps))
        writer = imageio.get_writer(
            output_path, fps=static_fps, codec="libx264", quality=8, pixelformat="yuv420p"
        )
        for _ in range(n_frames):
            writer.append_data(arr)
        writer.close()
        return output_path

    # Slow path: frame-by-frame rendering for slides with overlays or notes
    try:
        import imageio
        import numpy as np
    except ImportError:
        raise RuntimeError("imageio and numpy required; pip install imageio imageio-ffmpeg numpy")
    base = Image.open(io.BytesIO(slide_image_bytes)).convert("RGBA")
    width, height = base.size
    n_frames = max(1, int(slide_duration_seconds * fps))
    # Use libx264 for per-slide overlays so all slides have matching H.264
    # profile for concat -c copy. VT is only used in crossfade compose step.
    writer = imageio.get_writer(
        output_path, fps=fps, codec="libx264", quality=8, pixelformat="yuv420p"
    )
    for i in range(n_frames):
        t = i / fps
        frame = base.copy()
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for act in timeline_actions:
            if act.get("t_start", 0) <= t <= act.get("t_end", 0):
                if act.get("type") == "HIGHLIGHT" and act.get("bbox"):
                    _draw_highlight(overlay, act["bbox"])
                elif act.get("type") == "TRACE" and act.get("path"):
                    _draw_trace(overlay, act["path"])
                elif act.get("type") == "ZOOM" and act.get("bbox"):
                    _draw_highlight(overlay, act["bbox"])
        frame = Image.alpha_composite(frame, overlay)
        if draw_notes:
            draw_notes_on_image(
                frame, (notes_text or "").strip(), width, height, notes_config, notes_font_path
            )
        arr = np.array(frame.convert("RGB"))
        writer.append_data(arr)
    writer.close()
    return output_path
