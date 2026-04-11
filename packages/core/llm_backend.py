"""
Unified LLM HTTP backend. Works with any OpenAI-compatible endpoint:
OpenAI, Ollama, Groq, Together AI, OpenRouter, DeepInfra, LM Studio, vLLM, LocalAI.

Uses requests (fork-safe) — NOT the openai SDK which has httpx/asyncio
issues in RQ forked workers.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from exceptions import LLMError


class LLMBackendError(LLMError):
    """Raised when an LLM call fails after all retries."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code)


def call_chat(
    base_url: str,
    model: str,
    messages: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    max_tokens: int = 300,
    temperature: float = 0.7,
    timeout: int = 30,
    max_retries: int = 3,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    """
    OpenAI-compatible chat completion. Returns the assistant's text content.
    Retries with exponential backoff on 429 and 5xx errors.
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    url = base_url.rstrip("/") + "/chat/completions"
    last_error: Any = None

    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 429:
                wait = min(2 ** (attempt + 1), 30)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise LLMBackendError(
                    f"Server error {resp.status_code}: {resp.text[:200]}",
                    resp.status_code,
                )
            if resp.status_code != 200:
                raise LLMBackendError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}", resp.status_code
                )
            data = resp.json()
            content = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            return content
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            raise LLMBackendError(f"Request failed: {e}") from e

    raise LLMBackendError(f"Max retries exhausted. Last error: {last_error}")


def call_chat_with_image(
    base_url: str,
    model: str,
    image_b64_data_url: str,
    prompt: str,
    api_key: Optional[str] = None,
    system_prompt: Optional[str] = None,
    max_tokens: int = 500,
    temperature: float = 0.0,
    timeout: int = 60,
    max_retries: int = 3,
    extra_headers: Optional[Dict[str, str]] = None,
) -> str:
    """
    OpenAI-compatible vision chat. Sends an image + text prompt.
    Works with: OpenAI gpt-4o/gpt-4o-mini, Ollama llava/llama3.2-vision,
    Together AI Llama 3.2 Vision, OpenRouter Claude/Gemini Vision, etc.
    """
    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_b64_data_url}},
            ],
        }
    )
    return call_chat(
        base_url=base_url,
        model=model,
        messages=messages,
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        extra_headers=extra_headers,
    )


def health_check(
    base_url: str, api_key: Optional[str] = None, timeout: int = 5
) -> Tuple[bool, str]:
    """Quick health check by listing models. Returns (ok, message)."""
    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = base_url.rstrip("/") + "/models"
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return True, "OK"
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)[:80]
