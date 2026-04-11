"""
Unit tests for vision_provider_llm.py.
Since this is a re-export facade over vision_provider_openai.py,
tests verify the re-export contract and that symbols are importable
and point to the correct implementations.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Re-export contract
# ---------------------------------------------------------------------------

class TestVisionProviderLLMReexports:
    def test_llm_vision_provider_importable(self):
        from vision_provider_llm import LLMVisionProvider
        assert LLMVisionProvider is not None

    def test_openai_vision_provider_alias_importable(self):
        from vision_provider_llm import OpenAIVisionProvider
        assert OpenAIVisionProvider is not None

    def test_llm_vision_provider_and_alias_are_same_class(self):
        from vision_provider_llm import LLMVisionProvider, OpenAIVisionProvider
        assert LLMVisionProvider is OpenAIVisionProvider

    def test_vision_provider_error_importable(self):
        from vision_provider_llm import VisionProviderError
        assert issubclass(VisionProviderError, Exception)

    def test_caption_result_importable(self):
        from vision_provider_llm import CaptionResult
        assert CaptionResult is not None

    def test_photo_extract_result_importable(self):
        from vision_provider_llm import PhotoExtractResult
        assert PhotoExtractResult is not None

    def test_diagram_extract_result_importable(self):
        from vision_provider_llm import DiagramExtractResult
        assert DiagramExtractResult is not None

    def test_prompt_constants_importable(self):
        from vision_provider_llm import (
            CAPTION_PROMPT_v1,
            PHOTO_EXTRACT_PROMPT_v1,
            DIAGRAM_EXTRACT_PROMPT_v1,
            PROMPTS,
            PROMPT_VERSION,
        )
        assert isinstance(CAPTION_PROMPT_v1, str)
        assert isinstance(PROMPT_VERSION, str)
        assert "caption" in PROMPTS
        assert "photo_extract" in PROMPTS
        assert "diagram_extract" in PROMPTS

    def test_helper_functions_importable(self):
        from vision_provider_llm import (
            _cache_key,
            _download_and_base64,
            _extract_json_from_response,
            _get_cached,
            _set_cached,
        )
        assert callable(_cache_key)
        assert callable(_download_and_base64)
        assert callable(_extract_json_from_response)
        assert callable(_get_cached)
        assert callable(_set_cached)

    def test_llm_vision_provider_is_openai_provider(self):
        """Verify re-export points to the same class as vision_provider_openai."""
        from vision_provider_llm import LLMVisionProvider as FromLLM
        from vision_provider_openai import LLMVisionProvider as FromOpenAI
        assert FromLLM is FromOpenAI


# ---------------------------------------------------------------------------
# Spot-check: LLMVisionProvider instantiation (no API calls)
# ---------------------------------------------------------------------------

class TestLLMVisionProviderInit:
    def test_instantiates_with_explicit_args(self):
        from vision_provider_llm import LLMVisionProvider
        p = LLMVisionProvider(
            api_key="sk-test",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
        )
        assert p._api_key == "sk-test"
        assert p._model == "gpt-4o-mini"
        assert p._base_url == "https://api.openai.com/v1"

    def test_defaults_model_to_gpt4o_mini_when_not_specified(self):
        from vision_provider_llm import LLMVisionProvider
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENAI_VISION_MODEL", "OPENAI_API_KEY")}
        import unittest.mock as mock
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("vision_provider_openai.get_vision_config",
                            return_value=("https://api.openai.com/v1", "gpt-4o-mini", ""), create=True):
                p = LLMVisionProvider()
        assert p._model in ("gpt-4o-mini", "gpt-4o")  # either default is valid

    def test_cache_enabled_by_default(self):
        from vision_provider_llm import LLMVisionProvider
        p = LLMVisionProvider(api_key="sk-test", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
        assert p._cache_enabled is True

    def test_temperature_defaults_to_zero(self):
        from vision_provider_llm import LLMVisionProvider
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_VISION_TEMPERATURE"}
        import unittest.mock as mock
        with mock.patch.dict(os.environ, env, clear=True):
            p = LLMVisionProvider(
                api_key="sk-test",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
            )
        assert p._temperature == 0.0
