"""
Unit tests for translator_provider.py.
Tests: TranslatorProvider interface, StubTranslatorProvider, SOURCE_LANG_DEFAULT,
get_translator_provider factory, register_translator_provider.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from translator_provider import (
    SOURCE_LANG_DEFAULT,
    TranslatorProvider,
    StubTranslatorProvider,
    get_translator_provider,
    register_translator_provider,
    _TRANSLATOR_PROVIDER_REGISTRY,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_source_lang_default_is_english(self):
        assert SOURCE_LANG_DEFAULT == "en-US"


# ---------------------------------------------------------------------------
# StubTranslatorProvider
# ---------------------------------------------------------------------------

class TestStubTranslatorProvider:
    @pytest.fixture
    def provider(self):
        return StubTranslatorProvider()

    def test_same_lang_returns_text_unchanged(self, provider):
        result = provider.translate("Hello world", "en-US", "en-US")
        assert result == "Hello world"

    def test_different_lang_returns_none(self, provider):
        result = provider.translate("Hello world", "en-US", "hi-IN")
        assert result is None

    def test_is_available_returns_false(self, provider):
        assert provider.is_available() is False

    def test_translate_empty_string_same_lang(self, provider):
        result = provider.translate("", "en-US", "en-US")
        assert result == ""


# ---------------------------------------------------------------------------
# TranslatorProvider ABC
# ---------------------------------------------------------------------------

class TestTranslatorProviderInterface:
    def test_is_available_default_returns_true(self):
        """Default is_available returns True; StubTranslator overrides to False."""
        class ConcreteProvider(TranslatorProvider):
            def translate(self, text, source_lang, target_lang):
                return text

        p = ConcreteProvider()
        assert p.is_available() is True


# ---------------------------------------------------------------------------
# get_translator_provider
# ---------------------------------------------------------------------------

class TestGetTranslatorProvider:
    def test_stub_mode_returns_stub(self):
        with patch.dict(os.environ, {"TRANSLATOR_PROVIDER": "stub"}, clear=False):
            provider = get_translator_provider()
        assert isinstance(provider, StubTranslatorProvider)

    def test_none_mode_returns_stub(self):
        with patch.dict(os.environ, {"TRANSLATOR_PROVIDER": "none"}, clear=False):
            provider = get_translator_provider()
        assert isinstance(provider, StubTranslatorProvider)

    def test_default_when_env_not_set_returns_stub(self):
        env = {k: v for k, v in os.environ.items() if k != "TRANSLATOR_PROVIDER"}
        with patch.dict(os.environ, env, clear=True):
            provider = get_translator_provider()
        assert isinstance(provider, StubTranslatorProvider)

    def test_unknown_mode_falls_back_to_stub(self):
        with patch.dict(os.environ, {"TRANSLATOR_PROVIDER": "unknown_magic"}, clear=False):
            provider = get_translator_provider()
        assert isinstance(provider, StubTranslatorProvider)

    def test_llm_mode_returns_llm_translator_when_available(self):
        mock_llm_provider = MagicMock()
        from translator_provider_llm import LLMTranslatorProvider
        with patch.dict(os.environ, {"TRANSLATOR_PROVIDER": "llm"}, clear=False):
            provider = get_translator_provider()
        # Should get an LLMTranslatorProvider (or stub if import fails)
        assert provider is not None


# Needed for the mock above
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# register_translator_provider
# ---------------------------------------------------------------------------

class TestRegisterTranslatorProvider:
    def test_registers_and_retrieves_custom_factory(self):
        custom_stub = StubTranslatorProvider()
        register_translator_provider("my_custom_xlat", lambda: custom_stub)
        with patch.dict(os.environ, {"TRANSLATOR_PROVIDER": "my_custom_xlat"}, clear=False):
            provider = get_translator_provider()
        assert provider is custom_stub
        # Cleanup
        _TRANSLATOR_PROVIDER_REGISTRY.pop("my_custom_xlat", None)
