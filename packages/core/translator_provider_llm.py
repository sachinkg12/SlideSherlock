"""
LLM-based translator provider. Use when TRANSLATOR_PROVIDER=llm.
Requires an LLM that can perform translation (e.g. OpenAI, Anthropic).
"""
from __future__ import annotations

from typing import Optional

try:
    from llm_provider import StubLLMProvider
except ImportError:
    StubLLMProvider = None  # type: ignore


class LLMTranslatorProvider:
    """
    Translator using LLM. Stub returns None (no translation).
    Replace with real LLM integration for actual translation.
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider or (StubLLMProvider() if StubLLMProvider else None)

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[str]:
        if not text or not (text or "").strip():
            return ""
        if source_lang == target_lang:
            return text
        if self._llm and hasattr(self._llm, "translate"):
            return self._llm.translate(text, source_lang, target_lang)
        return None

    def is_available(self) -> bool:
        return self._llm is not None and hasattr(self._llm, "translate")
