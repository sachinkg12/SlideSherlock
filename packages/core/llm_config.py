"""
LLM provider registry. Adding a new OpenAI-compatible provider = 1 line.

Providers are looked up by name. Each provider exposes:
- base_url: HTTP endpoint
- api_key_env: Name of env var holding the API key (None for local providers)
- default_text_model: Recommended text model
- default_vision_model: Recommended vision model (or None if no vision)
- supports_vision: Whether the provider can do image analysis

User can override:
- NARRATE_PROVIDER (default: openai)
- NARRATE_MODEL (default: provider's default_text_model)
- VISION_PROVIDER (default: stub — vision is opt-in)
- VISION_MODEL (default: provider's default_vision_model)

Custom endpoints:
- NARRATE_BASE_URL, NARRATE_API_KEY (override the registry)
- VISION_BASE_URL, VISION_API_KEY (override the registry)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: Optional[str]
    default_text_model: str
    default_vision_model: Optional[str]
    supports_vision: bool


# Registry: ADDING A NEW PROVIDER = ADD ONE ENTRY HERE.
PROVIDERS: Dict[str, ProviderConfig] = {
    "openai": ProviderConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_text_model="gpt-4o-mini",
        default_vision_model="gpt-4o-mini",
        supports_vision=True,
    ),
    "ollama": ProviderConfig(
        name="ollama",
        base_url="http://localhost:11434/v1",
        api_key_env=None,
        default_text_model="llama3.1:8b",
        default_vision_model="llava:7b",
        supports_vision=True,
    ),
    "groq": ProviderConfig(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        default_text_model="llama-3.1-70b-versatile",
        default_vision_model=None,
        supports_vision=False,
    ),
    "together": ProviderConfig(
        name="together",
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        default_text_model="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        default_vision_model="meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
        supports_vision=True,
    ),
    "openrouter": ProviderConfig(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        default_text_model="meta-llama/llama-3.1-8b-instruct",
        default_vision_model="anthropic/claude-3-haiku",
        supports_vision=True,
    ),
    "deepinfra": ProviderConfig(
        name="deepinfra",
        base_url="https://api.deepinfra.com/v1/openai",
        api_key_env="DEEPINFRA_API_KEY",
        default_text_model="meta-llama/Meta-Llama-3.1-8B-Instruct",
        default_vision_model="meta-llama/Llama-3.2-11B-Vision-Instruct",
        supports_vision=True,
    ),
    "anyscale": ProviderConfig(
        name="anyscale",
        base_url="https://api.endpoints.anyscale.com/v1",
        api_key_env="ANYSCALE_API_KEY",
        default_text_model="meta-llama/Llama-2-7b-chat-hf",
        default_vision_model=None,
        supports_vision=False,
    ),
    "lmstudio": ProviderConfig(
        name="lmstudio",
        base_url="http://localhost:1234/v1",
        api_key_env=None,
        default_text_model="local-model",
        default_vision_model=None,
        supports_vision=False,
    ),
    "vllm": ProviderConfig(
        name="vllm",
        base_url="http://localhost:8000/v1",
        api_key_env=None,
        default_text_model="meta-llama/Meta-Llama-3.1-8B-Instruct",
        default_vision_model=None,
        supports_vision=False,
    ),
    "localai": ProviderConfig(
        name="localai",
        base_url="http://localhost:8080/v1",
        api_key_env=None,
        default_text_model="llama3",
        default_vision_model="bakllava",
        supports_vision=True,
    ),
}


def list_providers() -> Dict[str, ProviderConfig]:
    """Return the provider registry."""
    return PROVIDERS


def get_provider(name: str) -> ProviderConfig:
    """Look up a provider by name. Raises KeyError if unknown."""
    name = (name or "").strip().lower()
    if name not in PROVIDERS:
        raise KeyError(f"Unknown provider: {name}. Known: {', '.join(sorted(PROVIDERS.keys()))}")
    return PROVIDERS[name]


def get_narrate_config() -> Tuple[str, str, Optional[str]]:
    """
    Returns (base_url, model, api_key) for narration LLM.

    Resolution order:
    1. NARRATE_BASE_URL + NARRATE_MODEL + NARRATE_API_KEY (custom override)
    2. NARRATE_PROVIDER from registry
    3. Default: openai
    """
    custom_url = os.environ.get("NARRATE_BASE_URL", "").strip()
    if custom_url:
        return (
            custom_url,
            os.environ.get("NARRATE_MODEL", "").strip() or "gpt-4o-mini",
            os.environ.get("NARRATE_API_KEY", "").strip() or None,
        )

    provider_name = os.environ.get("NARRATE_PROVIDER", "openai").strip().lower()
    provider = get_provider(provider_name)
    model = os.environ.get("NARRATE_MODEL", "").strip() or provider.default_text_model
    api_key: Optional[str] = None
    if provider.api_key_env:
        api_key = os.environ.get(provider.api_key_env, "").strip() or None
    return (provider.base_url, model, api_key)


def get_vision_config() -> Tuple[str, str, Optional[str]]:
    """Same as get_narrate_config but for vision."""
    custom_url = os.environ.get("VISION_BASE_URL", "").strip()
    if custom_url:
        return (
            custom_url,
            os.environ.get("VISION_MODEL", "").strip()
            or os.environ.get("OPENAI_VISION_MODEL", "").strip()
            or "gpt-4o-mini",
            os.environ.get("VISION_API_KEY", "").strip() or None,
        )

    provider_name = os.environ.get("VISION_PROVIDER", "openai").strip().lower()
    if provider_name == "stub":
        return ("", "stub", None)

    provider = get_provider(provider_name)
    if not provider.supports_vision:
        raise ValueError(f"Provider {provider_name} does not support vision")

    model = (
        os.environ.get("VISION_MODEL", "").strip()
        or os.environ.get("OPENAI_VISION_MODEL", "").strip()
        or provider.default_vision_model
        or "gpt-4o-mini"
    )
    api_key: Optional[str] = None
    if provider.api_key_env:
        api_key = os.environ.get(provider.api_key_env, "").strip() or None
    return (provider.base_url, model, api_key)
