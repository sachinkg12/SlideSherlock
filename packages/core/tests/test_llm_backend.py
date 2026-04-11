"""
Unit tests for llm_backend.py.
Tests: call_chat, call_chat_with_image, health_check, retry logic, error handling.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch, call

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm_backend import LLMBackendError, call_chat, call_chat_with_image, health_check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, json_body=None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_body is not None:
        resp.json.return_value = json_body
    return resp


def _ok_response(content: str = "Hello world") -> MagicMock:
    return _make_response(
        200,
        json_body={"choices": [{"message": {"content": content}}]},
    )


# ---------------------------------------------------------------------------
# call_chat: success path
# ---------------------------------------------------------------------------

class TestCallChatSuccess:
    def test_returns_assistant_content(self):
        with patch("llm_backend.requests.post", return_value=_ok_response("Test output")) as mock_post:
            result = call_chat(
                base_url="https://api.openai.com/v1",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                api_key="sk-test",
            )
        assert result == "Test output"
        mock_post.assert_called_once()

    def test_strips_whitespace_from_content(self):
        with patch("llm_backend.requests.post", return_value=_ok_response("  padded  ")):
            result = call_chat("https://api.openai.com/v1", "gpt-4o", [])
        assert result == "padded"

    def test_sends_authorization_header_when_api_key_given(self):
        with patch("llm_backend.requests.post", return_value=_ok_response()) as mock_post:
            call_chat("https://api.openai.com/v1", "gpt-4o", [], api_key="sk-abc")
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer sk-abc"

    def test_no_auth_header_when_no_api_key(self):
        with patch("llm_backend.requests.post", return_value=_ok_response()) as mock_post:
            call_chat("https://localhost:11434/v1", "llama3", [])
        headers = mock_post.call_args.kwargs["headers"]
        assert "Authorization" not in headers

    def test_extra_headers_merged(self):
        with patch("llm_backend.requests.post", return_value=_ok_response()) as mock_post:
            call_chat(
                "https://api.openai.com/v1",
                "gpt-4o",
                [],
                extra_headers={"X-Custom": "value"},
            )
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["X-Custom"] == "value"

    def test_url_appends_chat_completions(self):
        with patch("llm_backend.requests.post", return_value=_ok_response()) as mock_post:
            call_chat("https://api.openai.com/v1/", "gpt-4o", [])
        url = mock_post.call_args.args[0]
        assert url == "https://api.openai.com/v1/chat/completions"

    def test_empty_content_returns_empty_string(self):
        resp = _make_response(200, json_body={"choices": [{"message": {"content": None}}]})
        with patch("llm_backend.requests.post", return_value=resp):
            result = call_chat("https://api.openai.com/v1", "gpt-4o", [])
        assert result == ""


# ---------------------------------------------------------------------------
# call_chat: error handling
# ---------------------------------------------------------------------------

class TestCallChatErrors:
    def test_raises_on_4xx_non_429(self):
        resp = _make_response(401, text="Unauthorized")
        with patch("llm_backend.requests.post", return_value=resp):
            with pytest.raises(LLMBackendError) as exc_info:
                call_chat("https://api.openai.com/v1", "gpt-4o", [], max_retries=1)
        assert exc_info.value.status_code == 401

    def test_raises_on_5xx_after_retries(self):
        resp = _make_response(500, text="Internal Server Error")
        with patch("llm_backend.requests.post", return_value=resp):
            with patch("llm_backend.time.sleep"):
                with pytest.raises(LLMBackendError) as exc_info:
                    call_chat("https://api.openai.com/v1", "gpt-4o", [], max_retries=2)
        assert exc_info.value.status_code == 500

    def test_retries_on_429_then_succeeds(self):
        rate_limit_resp = _make_response(429, text="Rate limited")
        ok_resp = _ok_response("Retry success")
        with patch("llm_backend.requests.post", side_effect=[rate_limit_resp, ok_resp]):
            with patch("llm_backend.time.sleep"):
                result = call_chat("https://api.openai.com/v1", "gpt-4o", [], max_retries=3)
        assert result == "Retry success"

    def test_raises_on_request_exception(self):
        with patch("llm_backend.requests.post", side_effect=requests.exceptions.ConnectionError("refused")):
            with patch("llm_backend.time.sleep"):
                with pytest.raises(LLMBackendError) as exc_info:
                    call_chat("https://api.openai.com/v1", "gpt-4o", [], max_retries=1)
        assert "Request failed" in str(exc_info.value)

    def test_llm_backend_error_stores_status_code(self):
        err = LLMBackendError("test error", status_code=503)
        assert err.status_code == 503
        assert "test error" in str(err)

    def test_llm_backend_error_no_status_code(self):
        err = LLMBackendError("connection refused")
        assert err.status_code is None


# ---------------------------------------------------------------------------
# call_chat_with_image
# ---------------------------------------------------------------------------

class TestCallChatWithImage:
    def test_builds_vision_message_and_calls_chat(self):
        with patch("llm_backend.requests.post", return_value=_ok_response("diagram described")) as mock_post:
            result = call_chat_with_image(
                base_url="https://api.openai.com/v1",
                model="gpt-4o",
                image_b64_data_url="data:image/png;base64,abc123",
                prompt="Describe this diagram.",
                api_key="sk-test",
            )
        assert result == "diagram described"
        payload = mock_post.call_args.kwargs["json"]
        messages = payload["messages"]
        user_msg = messages[-1]
        assert user_msg["role"] == "user"
        content = user_msg["content"]
        assert any(c["type"] == "text" and "Describe" in c["text"] for c in content)
        assert any(c["type"] == "image_url" for c in content)

    def test_includes_system_prompt_when_provided(self):
        with patch("llm_backend.requests.post", return_value=_ok_response()) as mock_post:
            call_chat_with_image(
                "https://api.openai.com/v1",
                "gpt-4o",
                "data:image/png;base64,abc",
                "prompt text",
                system_prompt="You are an expert.",
            )
        payload = mock_post.call_args.kwargs["json"]
        messages = payload["messages"]
        assert messages[0]["role"] == "system"
        assert "expert" in messages[0]["content"]

    def test_no_system_prompt_omits_system_message(self):
        with patch("llm_backend.requests.post", return_value=_ok_response()) as mock_post:
            call_chat_with_image(
                "https://api.openai.com/v1",
                "gpt-4o",
                "data:image/png;base64,abc",
                "prompt text",
            )
        payload = mock_post.call_args.kwargs["json"]
        messages = payload["messages"]
        assert all(m["role"] != "system" for m in messages)


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_returns_ok_on_200(self):
        resp = _make_response(200, json_body={"data": []})
        with patch("llm_backend.requests.get", return_value=resp):
            ok, msg = health_check("https://api.openai.com/v1", api_key="sk-test")
        assert ok is True
        assert msg == "OK"

    def test_returns_false_on_non_200(self):
        resp = _make_response(503, text="Service Unavailable")
        with patch("llm_backend.requests.get", return_value=resp):
            ok, msg = health_check("https://api.openai.com/v1")
        assert ok is False
        assert "503" in msg

    def test_returns_false_on_exception(self):
        with patch("llm_backend.requests.get", side_effect=Exception("timeout")):
            ok, msg = health_check("https://api.openai.com/v1")
        assert ok is False
        assert "timeout" in msg

    def test_health_check_url_appends_models(self):
        resp = _make_response(200, json_body={})
        with patch("llm_backend.requests.get", return_value=resp) as mock_get:
            health_check("https://api.openai.com/v1/")
        url = mock_get.call_args.args[0]
        assert url == "https://api.openai.com/v1/models"
