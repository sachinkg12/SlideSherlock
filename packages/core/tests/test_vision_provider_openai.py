"""
Unit tests for OpenAI Vision Provider (Day 1).
- base64 data URL is created
- cache hit skips API call
- invalid JSON triggers PARSE_FAIL
- cache key changes with prompt_version/mode
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vision_provider_openai import (
    VisionProviderError,
    _cache_key,
    _download_and_base64,
    _extract_json_from_response,
    _get_cached,
    _set_cached,
    OpenAIVisionProvider,
    PROMPT_VERSION,
)


def test_download_and_base64_creates_data_url():
    """MinIO bytes are encoded as base64 data URL."""
    minio = MagicMock()
    raw = b"\x89PNG\r\n\x1a\n"
    minio.get.return_value = raw
    bytes_out, data_url = _download_and_base64("jobs/j1/images/slide_001/img_00.png", minio)
    assert bytes_out == raw
    assert data_url.startswith("data:image/png;base64,")
    import base64
    decoded = base64.b64decode(data_url.split(",", 1)[1])
    assert decoded == raw


def test_cache_key_changes_with_mode_and_prompt_version():
    """Cache key differs when mode or prompt_version changes."""
    image_bytes = b"fake-image-bytes"
    model = "gpt-4o"
    lang = "en-US"
    key_caption = _cache_key(image_bytes, model, lang, PROMPT_VERSION, "caption")
    key_photo = _cache_key(image_bytes, model, lang, PROMPT_VERSION, "photo")
    key_diagram = _cache_key(image_bytes, model, lang, PROMPT_VERSION, "diagram")
    key_other_ver = _cache_key(image_bytes, model, lang, "v2", "photo")
    assert key_caption != key_photo
    assert key_photo != key_diagram
    assert key_photo != key_other_ver
    assert key_caption == _cache_key(image_bytes, model, lang, PROMPT_VERSION, "caption")


def test_extract_json_from_response_strips_markdown():
    """JSON is extracted from response even with markdown fence."""
    text = 'Here is the result:\n```json\n{"caption": "A cat", "confidence": 0.9}\n```'
    out = _extract_json_from_response(text)
    assert out == '{"caption": "A cat", "confidence": 0.9}'


def test_extract_json_from_response_no_json_raises_parse_fail():
    """When no JSON object is present, PARSE_FAIL is raised."""
    with pytest.raises(VisionProviderError) as exc_info:
        _extract_json_from_response("no json here")
    assert exc_info.value.reason_code == "PARSE_FAIL"


def test_invalid_json_triggers_parse_fail():
    """When OpenAI returns invalid JSON, caption() raises VisionProviderError with PARSE_FAIL."""
    minio = MagicMock()
    minio.get.return_value = b"\x89PNG"
    minio.exists.return_value = False
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        provider = OpenAIVisionProvider(
            cache_enabled=False,
        )
        with patch.object(provider, "_call_openai", return_value="this is not json at all"):
            with pytest.raises(VisionProviderError) as exc_info:
                provider.caption("jobs/j1/img.png", lang="en-US", minio_client=minio)
            assert exc_info.value.reason_code == "PARSE_FAIL"


def test_cache_hit_skips_api_call():
    """When cache has an entry, OpenAI is not called."""
    image_uri = "jobs/job-123/images/slide_001/img_00.png"
    image_bytes = b"\x89PNG\r\n"
    cache_payload = {"caption": "Cached caption", "confidence": 0.95, "scene_tags": []}
    cache_key = _cache_key(image_bytes, "gpt-4o", "en-US", PROMPT_VERSION, "caption")
    cache_path = f"jobs/job-123/cache/vision/{cache_key}.json"

    minio = MagicMock()
    def get(key):
        if key == image_uri:
            return image_bytes
        if key == cache_path:
            return json.dumps(cache_payload).encode("utf-8")
        raise FileNotFoundError(key)
    def exists(key):
        return key == cache_path
    minio.get.side_effect = get
    minio.exists.side_effect = exists

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        provider = OpenAIVisionProvider(
            cache_enabled=True,
            cache_prefix="jobs/{job_id}/cache/vision/",
        )
        api_called = []
        def track_call(*args, **kwargs):
            api_called.append(1)
            return json.dumps(cache_payload)
        with patch.object(provider, "_call_openai", side_effect=track_call):
            result = provider.caption(image_uri, lang="en-US", minio_client=minio)
        assert len(api_called) == 0
        assert result["caption"] == "Cached caption"
        assert result["confidence"] == 0.95


def test_get_cached_and_set_cached_roundtrip():
    """_set_cached and _get_cached work with a mock MinIO."""
    minio = MagicMock()
    stored = {}
    def put(key, data, content_type=None):
        stored[key] = data
    def get(key):
        return stored[key]
    def exists(key):
        return key in stored
    minio.put = put
    minio.get = get
    minio.exists = exists
    job_id = "j1"
    prefix = "jobs/j1/cache/vision"
    key = "abc123"
    payload = {"caption": "test", "confidence": 0.8}
    _set_cached(minio, job_id, prefix, key, payload)
    assert _get_cached(minio, job_id, prefix, key) == payload
    # Different job_id with its own prefix -> different path -> cache miss
    assert _get_cached(minio, "other", "jobs/other/cache/vision", key) is None
