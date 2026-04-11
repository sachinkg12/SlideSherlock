"""
LLM-backed VisionProvider for SlideSherlock.
Works with any OpenAI-compatible vision endpoint (OpenAI, Ollama, Together,
OpenRouter, DeepInfra, LocalAI, etc.) via llm_backend.call_chat_with_image.

- Downloads images from MinIO, sends as base64, returns structured results.
- Deterministic caching by (sha256(image), model, lang, prompt_version, mode).
- No secrets in code; reads provider config from llm_config.get_vision_config().
- Validated Pydantic output; PARSE_FAIL raised on invalid JSON (stage-level
  fallback handles it).

Backwards compat: the class name OpenAIVisionProvider is preserved.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Optional: inherit from VisionProvider for type consistency (avoid circular import at module load)
try:
    from vision_provider import VisionProvider as _VisionProvider
except ImportError:
    _VisionProvider = object

# -----------------------------------------------------------------------------
# Versioned prompts (embedded; prompt_version included in cache key)
# -----------------------------------------------------------------------------
PROMPT_VERSION = "v1"

CAPTION_PROMPT_v1 = """You are an image captioning assistant. Describe this image in one or two concise sentences.
Output ONLY valid JSON with no markdown, no code fence, no extra text.
Schema: {"caption": "<string>", "confidence": <0.0-1.0>, "scene_tags": [{"tag": "<string>", "conf": <0.0-1.0>}]}
Use the language code for the user's locale where natural (e.g. en for en-US)."""

PHOTO_EXTRACT_PROMPT_v1 = """You are an image analysis assistant. Extract structured facts from this photo.
Output ONLY valid JSON with no markdown, no code fence, no extra text.
Schema:
{
  "caption": "<short caption>",
  "objects": [{"label": "<string>", "conf": <0.0-1.0>}],
  "actions": [{"verb_phrase": "<string>", "conf": <0.0-1.0>}],
  "scene_tags": [{"tag": "<string>", "conf": <0.0-1.0>}],
  "global_confidence": <0.0-1.0>
}
List only what you clearly see. Use the language code for labels/caption where natural."""

DIAGRAM_EXTRACT_PROMPT_v1 = """You are a diagram analysis assistant. Extract structure from this diagram image.
Output ONLY valid JSON with no markdown, no code fence, no extra text.
Schema:
{
  "diagram_type": "SEQUENCE|FLOW|ARCH|UNKNOWN_DIAGRAM",
  "entities": [{"name": "<string>", "conf": <0.0-1.0>}],
  "interactions": [{"from": "<entity>", "to": "<entity>", "label": "<string>", "order": <int>, "conf": <0.0-1.0>}],
  "summary": "<one or two sentence summary>",
  "global_confidence": <0.0-1.0>
}
Do not invent entities or interactions; only list what is clearly visible. Use the given language for labels/summary."""


# Prompts are overridable via env vars (1-env-var customization per provider).
PROMPTS = {
    "caption": os.environ.get("VISION_CAPTION_PROMPT") or CAPTION_PROMPT_v1,
    "photo_extract": os.environ.get("VISION_PHOTO_PROMPT") or PHOTO_EXTRACT_PROMPT_v1,
    "diagram_extract": os.environ.get("VISION_DIAGRAM_PROMPT") or DIAGRAM_EXTRACT_PROMPT_v1,
}


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------
from exceptions import VisionError


class VisionProviderError(VisionError):
    """Raised when vision provider fails in a way callers should handle (e.g. fallback)."""

    def __init__(self, message: str, reason_code: str = "UNKNOWN"):
        self.reason_code = reason_code
        super().__init__(message)


# -----------------------------------------------------------------------------
# Pydantic output schemas
# -----------------------------------------------------------------------------
class SceneTagItem(BaseModel):
    tag: str = ""
    conf: float = Field(ge=0.0, le=1.0, default=0.0)


class CaptionResult(BaseModel):
    caption: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    scene_tags: Optional[List[SceneTagItem]] = None


class LabelConfItem(BaseModel):
    label: str = ""
    conf: float = Field(ge=0.0, le=1.0, default=0.0)


class VerbPhraseConfItem(BaseModel):
    verb_phrase: str = ""
    conf: float = Field(ge=0.0, le=1.0, default=0.0)


class PhotoExtractResult(BaseModel):
    caption: str = ""
    objects: List[LabelConfItem] = Field(default_factory=list)
    actions: List[VerbPhraseConfItem] = Field(default_factory=list)
    scene_tags: List[SceneTagItem] = Field(default_factory=list)
    global_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class DiagramEntityItem(BaseModel):
    name: str = ""
    conf: float = Field(ge=0.0, le=1.0, default=0.0)


class DiagramInteractionItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_entity: str = Field(alias="from", default="")
    to: str = ""
    label: str = ""
    order: int = 0
    conf: float = Field(ge=0.0, le=1.0, default=0.0)


class DiagramExtractResult(BaseModel):
    diagram_type: str = "UNKNOWN_DIAGRAM"
    entities: List[DiagramEntityItem] = Field(default_factory=list)
    interactions: List[DiagramInteractionItem] = Field(default_factory=list)
    summary: str = ""
    global_confidence: float = Field(ge=0.0, le=1.0, default=0.0)


# -----------------------------------------------------------------------------
# Helpers: MinIO + base64, cache key, cache get/set
# -----------------------------------------------------------------------------
def _job_id_from_uri(image_uri: str) -> Optional[str]:
    """Derive job_id from MinIO path jobs/{job_id}/..."""
    if not image_uri or not image_uri.startswith("jobs/"):
        return None
    parts = image_uri.split("/")
    if len(parts) >= 2:
        return parts[1]
    return None


def _download_and_base64(image_uri: str, minio_client: Any) -> tuple[bytes, str]:
    """
    Download image from MinIO and return (raw_bytes, data_url_string).
    data_url is e.g. data:image/png;base64,...
    """
    if not minio_client:
        raise VisionProviderError("MinIO client required to load image", "MISSING_CLIENT")
    try:
        raw = minio_client.get(image_uri)
    except Exception as e:
        raise VisionProviderError(f"Failed to download image: {e}", "DOWNLOAD_FAIL")
    if not raw:
        raise VisionProviderError("Empty image bytes", "EMPTY_IMAGE")
    b64 = base64.b64encode(raw).decode("ascii")
    # Infer media type from URI
    uri_lower = image_uri.lower()
    if uri_lower.endswith(".png"):
        mime = "image/png"
    elif uri_lower.endswith(".jpg") or uri_lower.endswith(".jpeg"):
        mime = "image/jpeg"
    elif uri_lower.endswith(".webp"):
        mime = "image/webp"
    elif uri_lower.endswith(".gif"):
        mime = "image/gif"
    else:
        mime = "image/png"
    data_url = f"data:{mime};base64,{b64}"
    return raw, data_url


def _cache_key(
    image_bytes: bytes,
    model: str,
    lang: str,
    prompt_version: str,
    mode: str,
) -> str:
    h = hashlib.sha256(image_bytes).hexdigest()
    payload = f"{h}|{model}|{lang}|{prompt_version}|{mode}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_cached(
    minio_client: Any,
    job_id: Optional[str],
    cache_prefix: str,
    key: str,
) -> Optional[Dict[str, Any]]:
    if not job_id or not minio_client or not cache_prefix:
        return None
    path = f"{cache_prefix.rstrip('/')}/{key}.json"
    try:
        if not getattr(minio_client, "exists", lambda p: False)(path):
            return None
        data = minio_client.get(path)
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def _set_cached(
    minio_client: Any,
    job_id: Optional[str],
    cache_prefix: str,
    key: str,
    payload: Dict[str, Any],
) -> None:
    if not job_id or not minio_client or not cache_prefix:
        return
    path = f"{cache_prefix.rstrip('/')}/{key}.json"
    try:
        minio_client.put(path, json.dumps(payload).encode("utf-8"), "application/json")
    except Exception:
        pass


def _extract_json_from_response(text: str) -> str:
    """Take first JSON object from model output (strip markdown if present)."""
    text = (text or "").strip()
    # Remove optional markdown code fence
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
    # Find first { ... }
    start = text.find("{")
    if start == -1:
        raise VisionProviderError("No JSON object in response", "PARSE_FAIL")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise VisionProviderError("Unclosed JSON in response", "PARSE_FAIL")


# -----------------------------------------------------------------------------
# LLMVisionProvider (backwards-compat alias: OpenAIVisionProvider)
# -----------------------------------------------------------------------------
class LLMVisionProvider(_VisionProvider):
    """
    Generic VisionProvider that uses any OpenAI-compatible vision endpoint
    (OpenAI, Ollama, Together, OpenRouter, DeepInfra, LocalAI, ...).

    - Reads image from MinIO, encodes as base64, calls the endpoint via
      llm_backend.call_chat_with_image.
    - Caches results in MinIO by (sha256(image), model, lang, prompt_version, mode).
      The model name is part of the cache key so different models don't collide.
    - Returns validated dicts; raises VisionProviderError on parse/validation failure.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout_seconds: Optional[int] = None,
        cache_enabled: Optional[bool] = None,
        cache_prefix: Optional[str] = None,
    ):
        # Resolve base_url/model/api_key: explicit args > llm_config > legacy env
        resolved_url = base_url
        resolved_model = model
        resolved_key = api_key
        if resolved_url is None or resolved_model is None or resolved_key is None:
            try:
                from llm_config import get_vision_config

                cfg_url, cfg_model, cfg_key = get_vision_config()
                if resolved_url is None:
                    resolved_url = cfg_url or "https://api.openai.com/v1"
                if resolved_model is None:
                    resolved_model = cfg_model
                if resolved_key is None:
                    resolved_key = cfg_key
            except Exception:
                pass
        if resolved_url is None:
            resolved_url = "https://api.openai.com/v1"
        if resolved_model is None:
            resolved_model = os.environ.get("OPENAI_VISION_MODEL", "").strip() or "gpt-4o-mini"
        if resolved_key is None:
            resolved_key = os.environ.get("OPENAI_API_KEY", "").strip() or None

        self._base_url = resolved_url
        self._api_key = (resolved_key or "").strip()
        self._model = (resolved_model or "gpt-4o-mini").strip()
        self._temperature = temperature
        if self._temperature is None:
            self._temperature = float(os.environ.get("OPENAI_VISION_TEMPERATURE", "0"))
        self._timeout = timeout_seconds
        if self._timeout is None:
            self._timeout = int(os.environ.get("OPENAI_VISION_TIMEOUT_SECONDS", "60"))
        self._cache_enabled = cache_enabled
        if self._cache_enabled is None:
            self._cache_enabled = os.environ.get("VISION_CACHE_ENABLED", "true").lower() in (
                "1",
                "true",
                "yes",
            )
        self._cache_prefix = cache_prefix
        if self._cache_prefix is None:
            self._cache_prefix = os.environ.get(
                "VISION_CACHE_PREFIX", "jobs/{job_id}/cache/vision/"
            ).strip()

    def _resolve_cache_prefix(self, job_id: Optional[str]) -> str:
        if not job_id or "{job_id}" not in self._cache_prefix:
            return ""
        return self._cache_prefix.replace("{job_id}", job_id)

    def _call_openai(self, prompt: str, data_url: str) -> str:
        """Vision chat call via llm_backend (OpenAI-compatible; works with any provider).

        Method name kept for backwards compat (test suite patches it).
        """
        from llm_backend import call_chat_with_image, LLMBackendError

        try:
            return call_chat_with_image(
                base_url=self._base_url,
                model=self._model,
                image_b64_data_url=data_url,
                prompt=prompt,
                api_key=self._api_key or None,
                max_tokens=1024,
                temperature=self._temperature,
                timeout=self._timeout,
                max_retries=3,
            )
        except LLMBackendError as e:
            raise VisionProviderError(str(e), "API_ERROR")

    def caption(
        self,
        image_uri: str,
        lang: str = "en-US",
        minio_client: Any = None,
    ) -> Dict[str, Any]:
        """
        Generate image caption. Returns {caption, confidence, scene_tags?, reason_code?}.
        On parse/API error, raises VisionProviderError(PARSE_FAIL or other).
        """
        raw_bytes, data_url = _download_and_base64(image_uri, minio_client)
        job_id = _job_id_from_uri(image_uri)
        cache_prefix = self._resolve_cache_prefix(job_id)
        key = _cache_key(raw_bytes, self._model, lang, PROMPT_VERSION, "caption")
        if self._cache_enabled and cache_prefix and minio_client:
            cached = _get_cached(minio_client, job_id, cache_prefix, key)
            if cached is not None:
                return cached
        prompt = PROMPTS["caption"] + f"\nLanguage/locale: {lang}"
        try:
            text = self._call_openai(prompt, data_url)
        except Exception as e:
            raise VisionProviderError(str(e), "API_ERROR")
        try:
            json_str = _extract_json_from_response(text)
            data = json.loads(json_str)
        except (json.JSONDecodeError, VisionProviderError) as e:
            raise VisionProviderError(
                f"Caption response parse failed: {e}",
                "PARSE_FAIL",
            )
        try:
            result = CaptionResult(**data)
        except Exception as e:
            raise VisionProviderError(f"Caption schema validation failed: {e}", "PARSE_FAIL")
        out = {
            "caption": result.caption,
            "confidence": result.confidence,
            "scene_tags": [{"tag": t.tag, "conf": t.conf} for t in (result.scene_tags or [])],
        }
        if self._cache_enabled and job_id and minio_client and cache_prefix:
            _set_cached(minio_client, job_id, cache_prefix, key, out)
        return out

    def extract(
        self,
        image_uri: str,
        lang: str = "en-US",
        minio_client: Any = None,
        mode: str = "photo",
    ) -> Dict[str, Any]:
        """
        Extract structured content. mode in {"photo","diagram","slide"}.
        Returns dict matching PhotoExtractResult or DiagramExtractResult; on error raises VisionProviderError.
        """
        if mode == "slide":
            mode = "photo"
        raw_bytes, data_url = _download_and_base64(image_uri, minio_client)
        job_id = _job_id_from_uri(image_uri)
        cache_prefix = self._resolve_cache_prefix(job_id)
        key = _cache_key(raw_bytes, self._model, lang, PROMPT_VERSION, mode)
        if self._cache_enabled and cache_prefix and minio_client and job_id:
            cached = _get_cached(minio_client, job_id, cache_prefix, key)
            if cached is not None:
                return cached
        if mode == "photo":
            prompt = PROMPTS["photo_extract"] + f"\nLanguage/locale: {lang}"
        else:
            prompt = PROMPTS["diagram_extract"] + f"\nLanguage/locale: {lang}"
        try:
            text = self._call_openai(prompt, data_url)
        except Exception as e:
            raise VisionProviderError(str(e), "API_ERROR")
        try:
            json_str = _extract_json_from_response(text)
            data = json.loads(json_str)
        except (json.JSONDecodeError, VisionProviderError) as e:
            raise VisionProviderError(f"Extract response parse failed: {e}", "PARSE_FAIL")
        try:
            if mode == "photo":
                result = PhotoExtractResult(**data)
                out = {
                    "caption": result.caption,
                    "objects": [{"label": o.label, "conf": o.conf} for o in result.objects],
                    "actions": [
                        {"verb_phrase": a.verb_phrase, "conf": a.conf} for a in result.actions
                    ],
                    "scene_tags": [{"tag": t.tag, "conf": t.conf} for t in result.scene_tags],
                    "global_confidence": result.global_confidence,
                }
            else:
                result = DiagramExtractResult(**data)
                interactions = []
                for i in result.interactions:
                    interactions.append(
                        {
                            "from": getattr(i, "from_entity", None) or getattr(i, "from", ""),
                            "to": i.to,
                            "label": i.label,
                            "order": i.order,
                            "conf": i.conf,
                        }
                    )
                out = {
                    "diagram_type": result.diagram_type,
                    "entities": [{"name": e.name, "conf": e.conf} for e in result.entities],
                    "interactions": interactions,
                    "summary": result.summary,
                    "global_confidence": result.global_confidence,
                }
        except Exception as e:
            raise VisionProviderError(f"Extract schema validation failed: {e}", "PARSE_FAIL")
        if self._cache_enabled and job_id and minio_client and cache_prefix:
            _set_cached(minio_client, job_id, cache_prefix, key, out)
        return out


# Backwards-compatible alias. Existing imports keep working.
OpenAIVisionProvider = LLMVisionProvider
