"""
Unit tests for audio_processor.py: process_audio, apply_audio_fade, process_audio_simple, _get_duration_seconds.
All ffmpeg/ffprobe calls are mocked — no real files or subprocesses are invoked.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import audio_processor
from audio_processor import (
    DEFAULT_LUFS_TARGET,
    DEFAULT_SAMPLE_RATE,
    SILENCE_DURATION_THRESHOLD,
    SILENCE_NOISE,
    apply_audio_fade,
    process_audio,
    process_audio_simple,
)


# --- Helpers ---

def _fake_duration_result(duration: float):
    """Return a mock subprocess result that reports a given duration."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = f"{duration}\n"
    return mock


# --- process_audio ---

def test_process_audio_raises_if_input_missing(tmp_path):
    """process_audio raises FileNotFoundError when input_path does not exist."""
    with pytest.raises(FileNotFoundError):
        process_audio(
            str(tmp_path / "nonexistent.wav"),
            str(tmp_path / "out.wav"),
        )


def test_process_audio_calls_ffmpeg(tmp_path):
    """process_audio calls ffmpeg with the right basic arguments."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "output.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(3.5)
        result = process_audio(str(input_file), str(output_file))

    assert mock_run.call_count >= 1
    cmd = mock_run.call_args_list[0][0][0]
    assert "ffmpeg" in cmd
    assert str(input_file) in cmd
    assert str(output_file) in cmd


def test_process_audio_returns_duration(tmp_path):
    """process_audio returns the duration reported by ffprobe."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "output.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(7.25)
        duration = process_audio(str(input_file), str(output_file))

    assert duration == pytest.approx(7.25, abs=0.01)


def test_process_audio_includes_loudnorm_when_enabled(tmp_path):
    """Loudness normalize enabled -> 'loudnorm' appears in the filter string."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "output.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(2.0)
        process_audio(str(input_file), str(output_file), loudness_normalize=True)

    cmd = " ".join(mock_run.call_args_list[0][0][0])
    assert "loudnorm" in cmd


def test_process_audio_excludes_loudnorm_when_disabled(tmp_path):
    """Loudness normalize disabled -> 'loudnorm' does not appear in args."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "output.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(2.0)
        process_audio(str(input_file), str(output_file), loudness_normalize=False)

    cmd = " ".join(mock_run.call_args_list[0][0][0])
    assert "loudnorm" not in cmd


def test_process_audio_includes_silenceremove_when_trim_enabled(tmp_path):
    """trim_silence=True -> 'silenceremove' appears in filter args."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "output.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(2.0)
        process_audio(str(input_file), str(output_file), trim_silence=True)

    cmd = " ".join(mock_run.call_args_list[0][0][0])
    assert "silenceremove" in cmd


def test_process_audio_excludes_silenceremove_when_disabled(tmp_path):
    """trim_silence=False -> 'silenceremove' does not appear."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "output.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(2.0)
        process_audio(str(input_file), str(output_file), trim_silence=False)

    cmd = " ".join(mock_run.call_args_list[0][0][0])
    assert "silenceremove" not in cmd


# --- apply_audio_fade ---

def test_apply_audio_fade_raises_if_input_missing(tmp_path):
    """apply_audio_fade raises FileNotFoundError when input does not exist."""
    with pytest.raises(FileNotFoundError):
        apply_audio_fade(
            str(tmp_path / "missing.wav"),
            str(tmp_path / "out.wav"),
        )


def test_apply_audio_fade_calls_ffmpeg_with_afade(tmp_path):
    """apply_audio_fade passes afade filter to ffmpeg."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "out.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(4.0)
        apply_audio_fade(str(input_file), str(output_file), fade_ms=100)

    # Two subprocess.run calls: ffprobe (via _get_duration_seconds) + ffmpeg
    all_cmds = [" ".join(call[0][0]) for call in mock_run.call_args_list]
    ffmpeg_cmds = [c for c in all_cmds if "ffmpeg" in c]
    assert len(ffmpeg_cmds) >= 1
    assert "afade" in ffmpeg_cmds[0]


def test_apply_audio_fade_returns_duration(tmp_path):
    """apply_audio_fade returns a float duration."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "out.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(5.0)
        duration = apply_audio_fade(str(input_file), str(output_file))

    assert isinstance(duration, float)


# --- process_audio_simple ---

def test_process_audio_simple_raises_if_input_missing(tmp_path):
    """process_audio_simple raises FileNotFoundError when input does not exist."""
    with pytest.raises(FileNotFoundError):
        process_audio_simple(
            str(tmp_path / "missing.wav"),
            str(tmp_path / "out.wav"),
        )


def test_process_audio_simple_no_silenceremove(tmp_path):
    """process_audio_simple never uses silenceremove."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "out.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(3.0)
        process_audio_simple(str(input_file), str(output_file))

    cmd = " ".join(mock_run.call_args_list[0][0][0])
    assert "silenceremove" not in cmd


def test_process_audio_simple_loudnorm_present_when_enabled(tmp_path):
    """process_audio_simple includes loudnorm when loudness_normalize=True."""
    input_file = tmp_path / "input.wav"
    input_file.write_bytes(b"\x00" * 16)
    output_file = tmp_path / "out.wav"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = _fake_duration_result(3.0)
        process_audio_simple(str(input_file), str(output_file), loudness_normalize=True)

    cmd = " ".join(mock_run.call_args_list[0][0][0])
    assert "loudnorm" in cmd


def test_constants_have_expected_values():
    """Spot-check module-level constants."""
    assert DEFAULT_LUFS_TARGET == -16.0
    assert DEFAULT_SAMPLE_RATE == 48000
    assert SILENCE_DURATION_THRESHOLD == 0.5
    assert SILENCE_NOISE == "-40dB"
