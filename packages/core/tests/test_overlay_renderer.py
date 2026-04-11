"""
Unit tests for overlay_renderer.py — _draw_highlight, _draw_trace, _wrap_text_to_lines,
render_overlay_frames, render_overlay_mp4, render_slide_overlay,
render_slide_with_overlay_mp4, and draw_notes_on_image.
"""
from __future__ import annotations

import io
import os
import sys
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# _wrap_text_to_lines
# ---------------------------------------------------------------------------


def test_wrap_text_to_lines_empty():
    from overlay_renderer import _wrap_text_to_lines

    draw = MagicMock()
    font = MagicMock()
    result = _wrap_text_to_lines("", draw, font, 200, 4)
    assert result == []


def test_wrap_text_to_lines_single_word_fits():
    from overlay_renderer import _wrap_text_to_lines

    draw = MagicMock()
    draw.textbbox.return_value = (0, 0, 40, 16)  # fits in 200px
    font = MagicMock()
    result = _wrap_text_to_lines("Hello", draw, font, 200, 4)
    assert result == ["Hello"]


def test_wrap_text_to_lines_respects_max_lines():
    from overlay_renderer import _wrap_text_to_lines

    draw = MagicMock()
    font = MagicMock()
    call_count = [0]

    def textbbox(origin, text, font):
        call_count[0] += 1
        # Every two-word combination overflows
        return (0, 0, len(text.split()) * 80, 16)

    draw.textbbox.side_effect = textbbox

    # 8 words that will each be on their own line
    result = _wrap_text_to_lines("a b c d e f g h", draw, font, 100, 3)
    assert len(result) <= 3


def test_wrap_text_to_lines_wraps_correctly():
    from overlay_renderer import _wrap_text_to_lines

    draw = MagicMock()
    font = MagicMock()

    def textbbox(origin, text, font):
        w = len(text.split()) * 60
        return (0, 0, w, 16)

    draw.textbbox.side_effect = textbbox

    # Two words each 60px, max_width=100 => they won't fit together (120 > 100)
    result = _wrap_text_to_lines("word1 word2", draw, font, 100, 4)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# _draw_highlight
# ---------------------------------------------------------------------------


def test_draw_highlight_skips_zero_size():
    """A bbox with w=0 or h=0 should not draw anything."""
    from overlay_renderer import _draw_highlight

    PIL = pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    original = img.tobytes()
    _draw_highlight(img, {"x": 10, "y": 10, "w": 0, "h": 0})
    assert img.tobytes() == original  # unchanged


def test_draw_highlight_draws_rectangle():
    """A valid bbox results in a modified image."""
    from overlay_renderer import _draw_highlight

    PIL = pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    original = img.tobytes()
    _draw_highlight(img, {"x": 10, "y": 10, "w": 50, "h": 50})
    assert img.tobytes() != original


# ---------------------------------------------------------------------------
# _draw_trace
# ---------------------------------------------------------------------------


def test_draw_trace_skips_single_point():
    from overlay_renderer import _draw_trace

    PIL = pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    original = img.tobytes()
    _draw_trace(img, [{"x": 10, "y": 10}])
    assert img.tobytes() == original


def test_draw_trace_draws_line():
    from overlay_renderer import _draw_trace

    PIL = pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    original = img.tobytes()
    _draw_trace(img, [{"x": 10, "y": 10}, {"x": 180, "y": 180}])
    assert img.tobytes() != original


# ---------------------------------------------------------------------------
# render_overlay_frames
# ---------------------------------------------------------------------------


def test_render_overlay_frames_count():
    PIL = pytest.importorskip("PIL")
    from overlay_renderer import render_overlay_frames

    frames = render_overlay_frames(100, 100, [], duration_seconds=1.0, fps=15)
    assert len(frames) == 15


def test_render_overlay_frames_returns_png_bytes():
    PIL = pytest.importorskip("PIL")
    from overlay_renderer import render_overlay_frames

    frames = render_overlay_frames(100, 100, [], duration_seconds=0.1, fps=10)
    assert len(frames) == 1
    assert frames[0][:4] == b"\x89PNG"


def test_render_overlay_frames_applies_highlight_action():
    """A HIGHLIGHT action within its time window should modify the frame."""
    PIL = pytest.importorskip("PIL")
    from overlay_renderer import render_overlay_frames

    actions = [{"type": "HIGHLIGHT", "t_start": 0.0, "t_end": 1.0, "bbox": {"x": 10, "y": 10, "w": 50, "h": 50}}]
    frames_with = render_overlay_frames(200, 200, actions, duration_seconds=0.1, fps=10)
    frames_empty = render_overlay_frames(200, 200, [], duration_seconds=0.1, fps=10)
    # Frame with highlight should differ from fully transparent frame
    assert frames_with[0] != frames_empty[0]


def test_render_overlay_frames_zoom_treated_as_highlight():
    """ZOOM action at t=0 should produce the same effect as HIGHLIGHT."""
    PIL = pytest.importorskip("PIL")
    from overlay_renderer import render_overlay_frames

    bbox = {"x": 20, "y": 20, "w": 60, "h": 60}
    highlight_frames = render_overlay_frames(
        200, 200,
        [{"type": "HIGHLIGHT", "t_start": 0.0, "t_end": 1.0, "bbox": bbox}],
        duration_seconds=0.1, fps=10,
    )
    zoom_frames = render_overlay_frames(
        200, 200,
        [{"type": "ZOOM", "t_start": 0.0, "t_end": 1.0, "bbox": bbox}],
        duration_seconds=0.1, fps=10,
    )
    assert highlight_frames[0] == zoom_frames[0]


def test_render_overlay_frames_inactive_action_not_applied():
    """Action outside its time window should produce a transparent frame."""
    PIL = pytest.importorskip("PIL")
    from overlay_renderer import render_overlay_frames

    actions = [{"type": "HIGHLIGHT", "t_start": 5.0, "t_end": 10.0, "bbox": {"x": 0, "y": 0, "w": 50, "h": 50}}]
    frames = render_overlay_frames(100, 100, actions, duration_seconds=0.1, fps=10)
    empty_frames = render_overlay_frames(100, 100, [], duration_seconds=0.1, fps=10)
    assert frames[0] == empty_frames[0]


# ---------------------------------------------------------------------------
# render_slide_with_overlay_mp4 — fast path (no actions)
# ---------------------------------------------------------------------------


def test_render_slide_with_overlay_mp4_fast_path_calls_ffmpeg(tmp_path):
    """Fast path (no actions) should call ffmpeg -loop 1 instead of imageio."""
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    from overlay_renderer import render_slide_with_overlay_mp4

    img = Image.new("RGB", (100, 100), (128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    slide_bytes = buf.getvalue()

    out = str(tmp_path / "slide.mp4")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        render_slide_with_overlay_mp4(slide_bytes, [], 2.0, out)

    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert any("-loop" in cmd for cmd in cmds), "Fast path should use -loop 1"


def test_render_slide_with_overlay_mp4_returns_output_path(tmp_path):
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    from overlay_renderer import render_slide_with_overlay_mp4

    img = Image.new("RGB", (100, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    out = str(tmp_path / "slide.mp4")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = render_slide_with_overlay_mp4(buf.getvalue(), [], 2.0, out)

    assert result == out


def test_render_slide_with_overlay_mp4_slow_path_fallback(tmp_path):
    """When ffmpeg fast path fails (SubprocessError), falls through to imageio slow path."""
    PIL = pytest.importorskip("PIL")
    imageio = pytest.importorskip("imageio")
    numpy = pytest.importorskip("numpy")

    import subprocess
    from PIL import Image
    from overlay_renderer import render_slide_with_overlay_mp4

    img = Image.new("RGB", (100, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    out = str(tmp_path / "slide_slow.mp4")
    # A slide WITH actions forces the slow path even without ffmpeg failure;
    # we also make ffmpeg fail so the fast path would not succeed anyway.
    actions = [{"type": "HIGHLIGHT", "t_start": 0.0, "t_end": 2.0, "bbox": {"x": 0, "y": 0, "w": 50, "h": 50}}]

    fake_writer = MagicMock()
    fake_writer.append_data = MagicMock()
    fake_writer.close = MagicMock()

    with patch("subprocess.run", side_effect=subprocess.SubprocessError("exit 187")), \
         patch("imageio.get_writer", return_value=fake_writer):
        # Should not raise even though ffmpeg fails (slow path via imageio)
        try:
            render_slide_with_overlay_mp4(buf.getvalue(), actions, 0.1, out)
        except RuntimeError as e:
            if "imageio" in str(e).lower() or "numpy" in str(e).lower():
                pytest.skip("imageio/numpy not installed")
            raise
