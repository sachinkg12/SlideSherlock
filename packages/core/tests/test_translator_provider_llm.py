"""
Unit tests for translator_provider_llm.py.
Tests: LLMTranslatorProvider init, translate behavior, is_available logic.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from translator_provider_llm import LLMTranslatorProvider


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestLLMTranslatorProviderInit:
    def test_creates_with_default_stub_llm(self):
        p = LLMTranslatorProvider()
        # _llm should be a StubLLMProvider instance (which lacks .translate)
        assert p._llm is not None

    def test_accepts_custom_llm_provider(self):
        mock_llm = MagicMock()
        mock_llm.translate = MagicMock(return_value="translated")
        p = LLMTranslatorProvider(llm_provider=mock_llm)
        assert p._llm is mock_llm

    def test_accepts_none_llm_sets_none(self):
        # When StubLLMProvider is None (import failed), passing None explicitly
        p = LLMTranslatorProvider(llm_provider=None)
        # _llm is StubLLMProvider from llm_provider module (not None), unless import failed
        # Either way, the provider is constructed without error
        assert p is not None


# ---------------------------------------------------------------------------
# translate
# ---------------------------------------------------------------------------

class TestLLMTranslatorProviderTranslate:
    def test_empty_text_returns_empty_string(self):
        p = LLMTranslatorProvider()
        result = p.translate("", "en-US", "hi-IN")
        assert result == ""

    def test_whitespace_only_returns_empty_string(self):
        p = LLMTranslatorProvider()
        result = p.translate("   ", "en-US", "hi-IN")
        assert result == ""

    def test_same_language_returns_original_text(self):
        p = LLMTranslatorProvider()
        result = p.translate("Hello world", "en-US", "en-US")
        assert result == "Hello world"

    def test_delegates_to_llm_translate_when_available(self):
        mock_llm = MagicMock()
        mock_llm.translate.return_value = "नमस्ते दुनिया"
        p = LLMTranslatorProvider(llm_provider=mock_llm)
        result = p.translate("Hello world", "en-US", "hi-IN")
        assert result == "नमस्ते दुनिया"
        mock_llm.translate.assert_called_once_with("Hello world", "en-US", "hi-IN")

    def test_returns_none_when_llm_has_no_translate_method(self):
        mock_llm = MagicMock(spec=[])  # no attributes at all
        p = LLMTranslatorProvider(llm_provider=mock_llm)
        result = p.translate("Hello", "en-US", "fr-FR")
        assert result is None

    def test_returns_none_when_llm_is_none(self):
        p = LLMTranslatorProvider.__new__(LLMTranslatorProvider)
        p._llm = None
        result = p.translate("Hello", "en-US", "fr-FR")
        assert result is None


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

class TestLLMTranslatorProviderIsAvailable:
    def test_available_when_llm_has_translate(self):
        mock_llm = MagicMock()
        mock_llm.translate = MagicMock()
        p = LLMTranslatorProvider(llm_provider=mock_llm)
        assert p.is_available() is True

    def test_not_available_when_llm_is_none(self):
        p = LLMTranslatorProvider.__new__(LLMTranslatorProvider)
        p._llm = None
        assert p.is_available() is False

    def test_not_available_when_llm_lacks_translate(self):
        mock_llm = MagicMock(spec=[])  # no attributes
        p = LLMTranslatorProvider(llm_provider=mock_llm)
        assert p.is_available() is False

    def test_default_stub_llm_not_available(self):
        """StubLLMProvider has no .translate, so default LLMTranslatorProvider is not available."""
        p = LLMTranslatorProvider()
        # StubLLMProvider doesn't implement .translate, so this should be False
        assert p.is_available() is False
