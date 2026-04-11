"""
Unit tests for tts_provider.py.
Tests: TTSProvider interface, LocalTTSProvider, VOICE_LANG_MAP,
TTS_SAMPLE_RATE, get_tts_provider factory, register_tts_provider.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tts_provider import (
    TTS_SAMPLE_RATE,
    TTSProvider,
    LocalTTSProvider,
    VOICE_LANG_MAP,
    get_tts_provider,
    register_tts_provider,
    _TTS_PROVIDER_REGISTRY,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_tts_sample_rate_is_48000(self):
        assert TTS_SAMPLE_RATE == 48000

    def test_voice_lang_map_has_english(self):
        assert "en" in VOICE_LANG_MAP
        assert "en-US" in VOICE_LANG_MAP

    def test_voice_lang_map_has_hindi(self):
        assert "hi" in VOICE_LANG_MAP


# ---------------------------------------------------------------------------
# LocalTTSProvider initialization
# ---------------------------------------------------------------------------

class TestLocalTTSProviderInit:
    def test_defaults(self):
        p = LocalTTSProvider()
        assert p.voice_id == "default"
        assert p.lang == "en-US"
        assert p.sample_rate == TTS_SAMPLE_RATE

    def test_custom_voice_and_lang(self):
        p = LocalTTSProvider(voice_id="Samantha", lang="hi-IN")
        assert p.voice_id == "Samantha"
        assert p.lang == "hi-IN"

    def test_engine_starts_as_none(self):
        p = LocalTTSProvider()
        assert p._engine is None


# ---------------------------------------------------------------------------
# LocalTTSProvider.synthesize: empty text -> silence
# ---------------------------------------------------------------------------

class TestLocalTTSProviderSynthesizeEmptyText:
    def test_empty_text_writes_silence_and_returns_half_second(self, tmp_path):
        p = LocalTTSProvider()
        out = str(tmp_path / "out.wav")
        with patch.object(p, "_write_silence") as mock_silence:
            duration = p.synthesize("", out)
        mock_silence.assert_called_once_with(out, 0.5, TTS_SAMPLE_RATE)
        assert duration == 0.5

    def test_whitespace_only_is_treated_as_empty(self, tmp_path):
        p = LocalTTSProvider()
        out = str(tmp_path / "out.wav")
        with patch.object(p, "_write_silence") as mock_silence:
            duration = p.synthesize("   ", out)
        mock_silence.assert_called_once()
        assert duration == 0.5


# ---------------------------------------------------------------------------
# LocalTTSProvider.synthesize: pyttsx3 path
# ---------------------------------------------------------------------------

class TestLocalTTSProviderPyttsx3Path:
    def test_uses_engine_when_pyttsx3_available(self, tmp_path):
        p = LocalTTSProvider()
        out = str(tmp_path / "out.wav")
        mock_engine = MagicMock()
        p._engine = mock_engine
        with patch.object(p, "_get_duration_seconds", return_value=3.5):
            duration = p.synthesize("Hello world", out)
        mock_engine.save_to_file.assert_called_once_with("Hello world", out)
        mock_engine.runAndWait.assert_called_once()
        assert duration == 3.5
        # Engine is reset to None after use
        assert p._engine is None

    def test_fallback_duration_when_ffprobe_returns_none(self, tmp_path):
        p = LocalTTSProvider()
        out = str(tmp_path / "out.wav")
        mock_engine = MagicMock()
        p._engine = mock_engine
        with patch.object(p, "_get_duration_seconds", return_value=None):
            duration = p.synthesize("text", out)
        assert duration == 2.0

    def test_falls_back_to_say_when_no_engine(self, tmp_path):
        p = LocalTTSProvider()
        out = str(tmp_path / "out.wav")
        # _get_engine returns None -> falls through to _synthesize_say
        with patch.object(p, "_get_engine", return_value=None):
            with patch.object(p, "_synthesize_say", return_value=2.5) as mock_say:
                duration = p.synthesize("Hello", out)
        mock_say.assert_called_once_with(out, "Hello", TTS_SAMPLE_RATE)
        assert duration == 2.5


# ---------------------------------------------------------------------------
# LocalTTSProvider._get_duration_seconds
# ---------------------------------------------------------------------------

class TestGetDurationSeconds:
    def test_returns_duration_when_ffprobe_succeeds(self, tmp_path):
        p = LocalTTSProvider()
        fake_path = str(tmp_path / "audio.wav")
        with patch("tts_provider.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "4.25\n"
            mock_run.return_value = mock_result
            dur = p._get_duration_seconds(fake_path)
        assert dur == pytest.approx(4.25)

    def test_returns_none_when_ffprobe_fails(self, tmp_path):
        p = LocalTTSProvider()
        fake_path = str(tmp_path / "audio.wav")
        with patch("tts_provider.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_run.return_value = mock_result
            dur = p._get_duration_seconds(fake_path)
        assert dur is None

    def test_returns_none_on_exception(self, tmp_path):
        p = LocalTTSProvider()
        with patch("tts_provider.subprocess.run", side_effect=Exception("no ffprobe")):
            dur = p._get_duration_seconds(str(tmp_path / "audio.wav"))
        assert dur is None


# ---------------------------------------------------------------------------
# get_tts_provider factory
# ---------------------------------------------------------------------------

class TestGetTTSProvider:
    def test_local_returns_local_provider(self):
        provider = get_tts_provider("local")
        assert isinstance(provider, LocalTTSProvider)

    def test_unknown_provider_falls_back_to_local(self):
        provider = get_tts_provider("nonexistent_provider")
        assert isinstance(provider, LocalTTSProvider)

    def test_openai_falls_back_to_local_when_not_installed(self):
        with patch.dict(_TTS_PROVIDER_REGISTRY, {"openai": lambda v, l: LocalTTSProvider()}, clear=False):
            provider = get_tts_provider("openai", voice_id="alloy")
        assert isinstance(provider, LocalTTSProvider)

    def test_passes_voice_id_and_lang_to_factory(self):
        provider = get_tts_provider("local", voice_id="Samantha", lang="hi-IN")
        assert provider.voice_id == "Samantha"
        assert provider.lang == "hi-IN"


# ---------------------------------------------------------------------------
# register_tts_provider
# ---------------------------------------------------------------------------

class TestRegisterTTSProvider:
    def test_registers_custom_provider(self):
        mock_provider = MagicMock(spec=TTSProvider)
        register_tts_provider("test_custom", lambda v, l: mock_provider)
        provider = get_tts_provider("test_custom")
        assert provider is mock_provider
        # Cleanup
        _TTS_PROVIDER_REGISTRY.pop("test_custom", None)
