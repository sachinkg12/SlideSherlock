"""
Unit tests for composer.py — concat_audio, _wrap_text_to_width, _compose_with_crossfade,
_xfade_single_pass, compose_video, and supporting helpers.
"""
from __future__ import annotations

import os
import sys
import subprocess
from typing import List
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# _wrap_text_to_width
# ---------------------------------------------------------------------------


def test_wrap_text_empty_returns_empty():
    from composer import _wrap_text_to_width

    draw = MagicMock()
    font = MagicMock()
    result = _wrap_text_to_width("", font, 200, draw)
    assert result == []


def test_wrap_text_single_short_word():
    from composer import _wrap_text_to_width

    draw = MagicMock()
    draw.textbbox.return_value = (0, 0, 50, 20)  # fits in 200px
    font = MagicMock()
    result = _wrap_text_to_width("Hello", font, 200, draw)
    assert result == ["Hello"]


def test_wrap_text_wraps_on_overflow():
    from composer import _wrap_text_to_width

    draw = MagicMock()
    font = MagicMock()
    # Make every 2-word combination overflow (w > 100)
    def textbbox_side(origin, text, font):
        word_count = len(text.split())
        return (0, 0, word_count * 60, 20)  # 60px per word

    draw.textbbox.side_effect = textbbox_side
    result = _wrap_text_to_width("one two three four", font, 100, draw)
    # Each word is 60px, max_width is 100 => each word on its own line
    assert len(result) >= 2
    assert all(len(line.split()) <= 2 for line in result)


def test_wrap_text_no_wrap_when_fits():
    from composer import _wrap_text_to_width

    draw = MagicMock()
    draw.textbbox.return_value = (0, 0, 80, 20)  # always fits in 200px
    font = MagicMock()
    result = _wrap_text_to_width("short text", font, 200, draw)
    assert result == ["short text"]


# ---------------------------------------------------------------------------
# concat_audio
# ---------------------------------------------------------------------------


def test_concat_audio_raises_with_no_files():
    from composer import concat_audio

    with pytest.raises(ValueError, match="No audio files"):
        concat_audio([], "/tmp/out.wav")


def test_concat_audio_calls_ffmpeg(tmp_path):
    from composer import concat_audio

    audio1 = tmp_path / "slide_0.wav"
    audio1.write_bytes(b"RIFF" + b"\x00" * 40)
    out = str(tmp_path / "combined.wav")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        concat_audio([str(audio1)], out)

    # ffmpeg concat should have been called
    calls = mock_run.call_args_list
    assert any("ffmpeg" in str(c) for c in calls)


def test_concat_audio_with_intro_silence_calls_ffmpeg(tmp_path):
    """Intro silence triggers extra ffmpeg call for anullsrc."""
    from composer import concat_audio

    audio1 = tmp_path / "slide_0.wav"
    audio1.write_bytes(b"RIFF" + b"\x00" * 40)
    out = str(tmp_path / "out.wav")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        concat_audio([str(audio1)], out, intro_silence_sec=1.0)

    # Should see at least 2 ffmpeg calls: one for silence, one for concat
    assert mock_run.call_count >= 2


def test_concat_audio_with_outro_silence_calls_ffmpeg(tmp_path):
    from composer import concat_audio

    audio1 = tmp_path / "slide_0.wav"
    audio1.write_bytes(b"RIFF" + b"\x00" * 40)
    out = str(tmp_path / "out.wav")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        concat_audio([str(audio1)], out, outro_silence_sec=1.5)

    assert mock_run.call_count >= 2


# ---------------------------------------------------------------------------
# _get_video_duration
# ---------------------------------------------------------------------------


def test_get_video_duration_returns_float():
    from composer import _get_video_duration

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="12.345\n")
        dur = _get_video_duration("/fake/video.mp4")
    assert abs(dur - 12.345) < 0.001


def test_get_video_duration_handles_error():
    from composer import _get_video_duration

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired("ffprobe", 5)
        dur = _get_video_duration("/fake/video.mp4")
    assert dur == 0.0


# ---------------------------------------------------------------------------
# _xfade_single_pass
# ---------------------------------------------------------------------------


def test_xfade_single_pass_builds_filter_complex():
    from composer import _xfade_single_pass

    with patch("subprocess.run") as mock_run, \
         patch("composer.get_video_encoder", return_value="libx264"), \
         patch("composer.get_video_encoder_args", return_value=[]):
        mock_run.return_value = MagicMock(returncode=0)
        _xfade_single_pass(["/a.mp4", "/b.mp4"], [3.0, 3.0], 300, "/out.mp4")

    cmd = mock_run.call_args.args[0]
    assert "ffmpeg" in cmd
    assert "-filter_complex" in cmd


def test_xfade_single_pass_clamps_fade_to_min_duration():
    """fade_sec must not exceed 40% of shortest duration."""
    from composer import _xfade_single_pass

    captured_cmd = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run), \
         patch("composer.get_video_encoder", return_value="libx264"), \
         patch("composer.get_video_encoder_args", return_value=[]):
        _xfade_single_pass(["/a.mp4", "/b.mp4"], [1.0, 1.0], 5000, "/out.mp4")

    fc_idx = captured_cmd.index("-filter_complex")
    filter_str = captured_cmd[fc_idx + 1]
    # duration= should be at most 0.4
    import re
    m = re.search(r"duration=([\d.]+)", filter_str)
    assert m, "No duration= found in filter_complex"
    assert float(m.group(1)) <= 0.4 + 1e-9


# ---------------------------------------------------------------------------
# _compose_with_crossfade
# ---------------------------------------------------------------------------


def test_compose_with_crossfade_single_video_copies(tmp_path):
    """A single video is just copied to output."""
    from composer import _compose_with_crossfade

    src = tmp_path / "only.mp4"
    src.write_bytes(b"\x00" * 8)
    out = str(tmp_path / "out.mp4")

    with patch("shutil.copy") as mock_copy:
        _compose_with_crossfade([str(src)], [3.0], 300, out)
        mock_copy.assert_called_once_with(str(src), out)


def test_compose_with_crossfade_empty_raises():
    from composer import _compose_with_crossfade

    with pytest.raises(ValueError, match="Need at least one video"):
        _compose_with_crossfade([], [], 300, "/out.mp4")


def test_compose_with_crossfade_large_deck_uses_chunks():
    """With chunk_size=2 and 4 videos, xfade is called twice (once per chunk)."""
    from composer import _compose_with_crossfade

    videos = [f"/slide_{i}.mp4" for i in range(4)]
    durations = [3.0] * 4

    with patch.dict(os.environ, {"CROSSFADE_CHUNK_SIZE": "2"}), \
         patch("composer._xfade_single_pass") as mock_xfade, \
         patch("subprocess.run") as mock_run:
        mock_xfade.return_value = "/tmp/chunk.mp4"
        mock_run.return_value = MagicMock(returncode=0)
        _compose_with_crossfade(videos, durations, 300, "/out.mp4")

    assert mock_xfade.call_count == 2  # 2 chunks of 2


# ---------------------------------------------------------------------------
# compose_video
# ---------------------------------------------------------------------------


def test_compose_video_raises_on_empty_slides():
    from composer import compose_video

    with pytest.raises(ValueError, match="No slide videos"):
        compose_video([], 10.0, "/out.mp4")


def test_compose_video_no_audio_uses_anullsrc():
    """Without audio, compose_video adds a silent audio stream."""
    from composer import compose_video

    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run), \
         patch("composer._get_video_duration", return_value=3.0):
        compose_video(["/slide_0.mp4"], 3.0, "/out.mp4")

    all_cmds = " ".join(str(c) for c in captured)
    assert "anullsrc" in all_cmds


def test_compose_video_with_audio_muxes_streams(tmp_path):
    """With audio_path provided, compose_video muxes video and audio."""
    from composer import compose_video

    audio = tmp_path / "narration.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 40)

    captured = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run), \
         patch("composer._get_video_duration", return_value=3.0), \
         patch("os.path.exists", return_value=True):
        compose_video(
            ["/slide_0.mp4"],
            3.0,
            str(tmp_path / "out.mp4"),
            audio_path=str(audio),
        )

    all_cmds = " ".join(str(c) for sublist in captured for c in sublist)
    # Should see -map to mux video and audio streams
    assert "-map" in all_cmds


def test_compose_video_returns_output_path(tmp_path):
    from composer import compose_video

    out = str(tmp_path / "final.mp4")

    with patch("subprocess.run") as mock_run, \
         patch("composer._get_video_duration", return_value=3.0):
        mock_run.return_value = MagicMock(returncode=0)
        result = compose_video(["/slide_0.mp4"], 3.0, out)

    assert result == out


def test_compose_video_crossfade_enabled_calls_compose_crossfade():
    from composer import compose_video, TRANSITION_CROSSFADE

    config = MagicMock()
    config.transition = TRANSITION_CROSSFADE
    config.transition_ms = 300
    config.intro_enabled = False
    config.outro_enabled = False
    config.audio_fade_ms = 0
    config.subtitles_burn_in = False

    with patch("composer._compose_with_crossfade") as mock_cf, \
         patch("subprocess.run") as mock_run, \
         patch("composer._get_video_duration", return_value=3.0), \
         patch("os.path.exists", return_value=False):
        mock_cf.return_value = "/tmp/concat.mp4"
        mock_run.return_value = MagicMock(returncode=0)
        compose_video(
            ["/slide_0.mp4", "/slide_1.mp4"],
            6.0,
            "/out.mp4",
            video_config=config,
            per_slide_durations=[3.0, 3.0],
        )

    mock_cf.assert_called_once()


def test_compose_video_intro_card_rendered_when_enabled():
    from composer import compose_video, TRANSITION_CUT

    config = MagicMock()
    config.transition = TRANSITION_CUT
    config.intro_enabled = True
    config.outro_enabled = False
    config.intro_title = "My Deck"
    config.intro_subtitle = "Subtitle"
    config.intro_duration = 2.0
    config.audio_fade_ms = 0
    config.subtitles_burn_in = False

    with patch("composer._render_card_mp4") as mock_card, \
         patch("subprocess.run") as mock_run, \
         patch("composer._get_video_duration", return_value=3.0), \
         patch("os.path.exists", return_value=False), \
         patch("os.unlink"):
        mock_card.return_value = "/tmp/intro.mp4"
        mock_run.return_value = MagicMock(returncode=0)
        compose_video(
            ["/slide_0.mp4"],
            3.0,
            "/out.mp4",
            video_config=config,
            per_slide_durations=[3.0],
        )

    mock_card.assert_called_once()
    # First arg should be intro_title
    assert mock_card.call_args.args[0] == "My Deck"
