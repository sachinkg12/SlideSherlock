"""
Canonical LLM-backed vision provider module.

The real implementation lives in vision_provider_openai.py for backwards
compatibility with existing imports and tests. This file re-exports the
same symbols under their new generic names.
"""
from __future__ import annotations

from vision_provider_openai import (  # noqa: F401
    LLMVisionProvider,
    OpenAIVisionProvider,  # backwards-compat alias
    VisionProviderError,
    CaptionResult,
    PhotoExtractResult,
    DiagramExtractResult,
    CAPTION_PROMPT_v1,
    PHOTO_EXTRACT_PROMPT_v1,
    DIAGRAM_EXTRACT_PROMPT_v1,
    PROMPTS,
    PROMPT_VERSION,
    _cache_key,
    _download_and_base64,
    _extract_json_from_response,
    _get_cached,
    _set_cached,
)
