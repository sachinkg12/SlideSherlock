"""
Unit tests for llm_config.py: PROVIDERS registry, get_provider, get_narrate_config, get_vision_config.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm_config import (
    PROVIDERS,
    ProviderConfig,
    get_provider,
    get_narrate_config,
    get_vision_config,
    list_providers,
)


def test_providers_registry_contains_expected_entries():
    """Registry has core providers: openai, ollama, groq, together, openrouter."""
    for name in ("openai", "ollama", "groq", "together", "openrouter"):
        assert name in PROVIDERS


def test_list_providers_returns_all():
    """list_providers() returns the same dict as PROVIDERS."""
    assert list_providers() is PROVIDERS


def test_get_provider_openai():
    """get_provider('openai') returns the correct ProviderConfig."""
    p = get_provider("openai")
    assert isinstance(p, ProviderConfig)
    assert p.name == "openai"
    assert "openai.com" in p.base_url
    assert p.supports_vision is True
    assert p.api_key_env == "OPENAI_API_KEY"


def test_get_provider_case_insensitive():
    """get_provider is case-insensitive."""
    p = get_provider("OpenAI")
    assert p.name == "openai"


def test_get_provider_unknown_raises_key_error():
    """get_provider with unknown name raises KeyError."""
    with pytest.raises(KeyError, match="Unknown provider"):
        get_provider("nonexistent_provider")


def test_get_provider_groq_no_vision():
    """Groq provider does not support vision."""
    p = get_provider("groq")
    assert p.supports_vision is False
    assert p.default_vision_model is None


def test_get_provider_ollama_local_no_api_key():
    """Ollama has no api_key_env (local provider)."""
    p = get_provider("ollama")
    assert p.api_key_env is None


def test_get_narrate_config_defaults_to_openai():
    """Without env overrides, narrate config uses openai defaults."""
    clean = {
        "NARRATE_BASE_URL": "", "NARRATE_PROVIDER": "", "NARRATE_MODEL": "",
        "NARRATE_API_KEY": "", "OPENAI_API_KEY": "",
    }
    with patch.dict(os.environ, clean, clear=False):
        for k in clean:
            os.environ.pop(k, None)
        url, model, api_key = get_narrate_config()
    assert "openai.com" in url
    assert model == PROVIDERS["openai"].default_text_model


def test_get_narrate_config_custom_url_overrides_registry():
    """NARRATE_BASE_URL bypasses the provider registry."""
    env = {
        "NARRATE_BASE_URL": "https://my-proxy.example.com/v1",
        "NARRATE_MODEL": "custom-model",
        "NARRATE_API_KEY": "sk-custom",
    }
    with patch.dict(os.environ, env, clear=False):
        url, model, api_key = get_narrate_config()
    assert url == "https://my-proxy.example.com/v1"
    assert model == "custom-model"
    assert api_key == "sk-custom"


def test_get_narrate_config_provider_ollama():
    """NARRATE_PROVIDER=ollama resolves to ollama base_url."""
    with patch.dict(os.environ, {"NARRATE_PROVIDER": "ollama", "NARRATE_BASE_URL": ""}, clear=False):
        os.environ.pop("NARRATE_BASE_URL", None)
        url, model, api_key = get_narrate_config()
    assert "localhost:11434" in url
    assert api_key is None


def test_get_narrate_config_model_override():
    """NARRATE_MODEL overrides the provider default."""
    with patch.dict(
        os.environ,
        {"NARRATE_PROVIDER": "openai", "NARRATE_MODEL": "gpt-4o", "NARRATE_BASE_URL": ""},
        clear=False,
    ):
        os.environ.pop("NARRATE_BASE_URL", None)
        _, model, _ = get_narrate_config()
    assert model == "gpt-4o"


def test_get_vision_config_stub_provider():
    """VISION_PROVIDER=stub returns empty url and 'stub' model with no api key."""
    with patch.dict(os.environ, {"VISION_PROVIDER": "stub", "VISION_BASE_URL": ""}, clear=False):
        os.environ.pop("VISION_BASE_URL", None)
        url, model, api_key = get_vision_config()
    assert url == ""
    assert model == "stub"
    assert api_key is None


def test_get_vision_config_custom_url():
    """VISION_BASE_URL overrides provider registry for vision."""
    env = {
        "VISION_BASE_URL": "https://vision.example.com/v1",
        "VISION_MODEL": "vision-model-v2",
        "VISION_API_KEY": "vk-test",
    }
    with patch.dict(os.environ, env, clear=False):
        url, model, api_key = get_vision_config()
    assert url == "https://vision.example.com/v1"
    assert model == "vision-model-v2"
    assert api_key == "vk-test"


def test_get_vision_config_non_vision_provider_raises():
    """Using a provider that does not support vision raises ValueError."""
    with patch.dict(os.environ, {"VISION_PROVIDER": "groq", "VISION_BASE_URL": ""}, clear=False):
        os.environ.pop("VISION_BASE_URL", None)
        with pytest.raises(ValueError, match="does not support vision"):
            get_vision_config()


def test_provider_config_dataclass_fields():
    """ProviderConfig fields are all present and typed correctly."""
    p = get_provider("openrouter")
    assert isinstance(p.name, str)
    assert isinstance(p.base_url, str)
    assert isinstance(p.supports_vision, bool)
    assert p.default_text_model != ""
