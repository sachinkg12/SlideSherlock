"""
Provider interface for translation (narration, notes).
Faithful translation only - no new facts. Supports no-provider mode (degraded variant).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

SOURCE_LANG_DEFAULT = "en-US"


class TranslatorProvider(ABC):
    """Interface for translating text between languages."""

    @abstractmethod
    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[str]:
        """
        Faithful translation of text. Must not add new facts.
        source_lang, target_lang: BCP-47 (e.g. en-US, hi-IN).
        Returns translated text or None if translation failed/unavailable.
        """

    def is_available(self) -> bool:
        """Return True if this provider can translate."""
        return True


class StubTranslatorProvider(TranslatorProvider):
    """
    No-op: returns text as-is (identity). Use when no translator available.
    Pipeline marks variant as degraded when using this for target language.
    """

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[str]:
        if source_lang == target_lang:
            return text
        return None

    def is_available(self) -> bool:
        return False


def _make_stub_translator():
    return StubTranslatorProvider()


def _make_llm_translator():
    try:
        from translator_provider_llm import LLMTranslatorProvider

        return LLMTranslatorProvider()
    except ImportError:
        return StubTranslatorProvider()


# Registry: adding a new translator provider = one entry here.
_TRANSLATOR_PROVIDER_REGISTRY = {
    "stub": _make_stub_translator,
    "none": _make_stub_translator,
    "llm": _make_llm_translator,
}


def register_translator_provider(name: str, factory) -> None:
    """Register a new translator provider factory."""
    _TRANSLATOR_PROVIDER_REGISTRY[name] = factory


def get_translator_provider() -> Optional[TranslatorProvider]:
    """Factory: return configured translator or StubTranslatorProvider (no-op).

    Auto-selects 'llm' translator when OPENAI_API_KEY is set and no explicit
    TRANSLATOR_PROVIDER is configured — so multi-language works out of the box
    when the user has an API key.
    """
    import os

    mode = (os.environ.get("TRANSLATOR_PROVIDER") or "").strip().lower()
    if not mode:
        # Auto-detect: use LLM translator if OpenAI API key is available
        if os.environ.get("OPENAI_API_KEY", "").strip():
            mode = "llm"
        else:
            mode = "stub"
    factory = _TRANSLATOR_PROVIDER_REGISTRY.get(mode, _make_stub_translator)
    return factory()
