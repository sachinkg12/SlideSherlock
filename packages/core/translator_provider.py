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
        pass

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


def get_translator_provider() -> Optional[TranslatorProvider]:
    """Factory: return configured translator or StubTranslatorProvider (no-op)."""
    import os
    mode = (os.environ.get("TRANSLATOR_PROVIDER") or "stub").strip().lower()
    if mode == "stub" or mode == "none":
        return StubTranslatorProvider()
    if mode == "llm":
        try:
            from translator_provider_llm import LLMTranslatorProvider
            return LLMTranslatorProvider()
        except ImportError:
            return StubTranslatorProvider()
    return StubTranslatorProvider()
