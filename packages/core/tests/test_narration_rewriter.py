"""
Unit tests for narration_rewriter.py — rewrite_narration_for_delivery.
All LLM backend calls are mocked.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entries(n: int = 2) -> List[Dict[str, Any]]:
    return [
        {"slide_index": i + 1, "narration_text": f"Slide {i + 1} narration.", "source_used": "template"}
        for i in range(n)
    ]


def _make_slides_notes(n: int = 2):
    return [("Notes for slide.", "Text on slide.") for _ in range(n)]


# ---------------------------------------------------------------------------
# rewrite_narration_for_delivery
# ---------------------------------------------------------------------------


def _llm_backend_patches(call_chat_return=None, call_chat_side_effect=None, llm_backend_error_cls=None):
    """
    narration_rewriter.py imports call_chat, LLMBackendError, get_narrate_config
    from llm_backend / llm_config inside the function body. Patch the source modules.
    """
    fake_error = llm_backend_error_cls or type("LLMBackendError", (Exception,), {})
    fake_call_chat = MagicMock(return_value=call_chat_return, side_effect=call_chat_side_effect)
    return fake_call_chat, fake_error


def test_rewrite_returns_same_count():
    from narration_rewriter import rewrite_narration_for_delivery

    entries = _make_entries(3)
    slides = _make_slides_notes(3)
    fake_call_chat, fake_err = _llm_backend_patches(call_chat_return="Rewritten text here for you.")

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=fake_call_chat, LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "test-key"))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key="test-key")

    assert len(result) == len(entries)


def test_rewrite_updates_narration_text():
    from narration_rewriter import rewrite_narration_for_delivery

    entries = _make_entries(1)
    slides = _make_slides_notes(1)
    fake_call_chat, fake_err = _llm_backend_patches(call_chat_return="Polished presenter text.")

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=fake_call_chat, LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "test-key"))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key="test-key")

    assert result[0]["narration_text"] == "Polished presenter text."
    assert result[0]["source_used"] == "ai_rewrite"


def test_rewrite_keeps_original_on_llm_error():
    """When LLMBackendError is raised, original entry is preserved."""
    from narration_rewriter import rewrite_narration_for_delivery

    entries = _make_entries(1)
    slides = _make_slides_notes(1)
    fake_err = type("LLMBackendError", (Exception,), {})
    fake_call_chat = MagicMock(side_effect=fake_err("API timeout"))

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=fake_call_chat, LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "test-key"))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key="test-key")

    assert result[0]["narration_text"] == entries[0]["narration_text"]
    assert result[0].get("source_used") != "ai_rewrite"


def test_rewrite_keeps_original_on_generic_exception():
    from narration_rewriter import rewrite_narration_for_delivery

    entries = _make_entries(2)
    slides = _make_slides_notes(2)

    call_count = [0]

    def flaky_call_chat(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("unexpected error")
        return "Second slide rewritten fine."

    fake_err = type("LLMBackendError", (Exception,), {})

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=flaky_call_chat, LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "test-key"))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key="test-key")

    assert result[0]["narration_text"] == entries[0]["narration_text"]
    assert result[1]["narration_text"] == "Second slide rewritten fine."


def test_rewrite_skips_when_no_api_key():
    """When API key missing and base_url requires one, entries are returned unchanged."""
    from narration_rewriter import rewrite_narration_for_delivery

    entries = _make_entries(2)
    slides = _make_slides_notes(2)
    fake_err = type("LLMBackendError", (Exception,), {})

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=MagicMock(), LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", None))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key=None)

    assert result == entries


def test_rewrite_skips_entry_with_no_text():
    """Entry with empty narration_text and no slide context: preserved as-is."""
    from narration_rewriter import rewrite_narration_for_delivery

    entries = [{"slide_index": 1, "narration_text": "", "source_used": "template"}]
    slides = [("", "")]
    mock_call = MagicMock(return_value="Should not be called.")
    fake_err = type("LLMBackendError", (Exception,), {})

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=mock_call, LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "test-key"))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key="test-key")

    mock_call.assert_not_called()
    assert result[0]["narration_text"] == ""


def test_rewrite_word_count_added():
    from narration_rewriter import rewrite_narration_for_delivery

    entries = _make_entries(1)
    slides = _make_slides_notes(1)
    rewritten_text = "This is a four word sentence with eight words total."
    fake_err = type("LLMBackendError", (Exception,), {})

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=MagicMock(return_value=rewritten_text), LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "test-key"))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key="test-key")

    assert result[0]["word_count"] == len(rewritten_text.split())


def test_rewrite_too_short_response_falls_back_to_original():
    """LLM response shorter than 10 chars: keep original."""
    from narration_rewriter import rewrite_narration_for_delivery

    entries = _make_entries(1)
    slides = _make_slides_notes(1)
    fake_err = type("LLMBackendError", (Exception,), {})

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=MagicMock(return_value="OK"), LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "test-key"))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key="test-key")

    assert result[0]["narration_text"] == entries[0]["narration_text"]


def test_rewrite_uses_slide_notes_as_context():
    """Slide notes appear in the user_prompt passed to call_chat."""
    from narration_rewriter import rewrite_narration_for_delivery

    entries = _make_entries(1)
    slides = [("Important speaker notes.", "Slide visible text.")]
    captured_messages = []
    fake_err = type("LLMBackendError", (Exception,), {})

    def capture_call(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return "Rewritten content that is long enough."

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=capture_call, LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "key"))),
    }):
        rewrite_narration_for_delivery(entries, slides, api_key="key")

    user_msg = next(m["content"] for m in captured_messages if m["role"] == "user")
    assert "Important speaker notes." in user_msg


def test_rewrite_non_openai_base_url_no_key_check():
    """A non-openai.com base_url should not require a key."""
    from narration_rewriter import rewrite_narration_for_delivery

    entries = _make_entries(1)
    slides = _make_slides_notes(1)
    fake_err = type("LLMBackendError", (Exception,), {})

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=MagicMock(return_value="Local LLM rewrite text here."), LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("http://localhost:11434/v1", "llama3", None))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key=None)

    assert result[0]["narration_text"] == "Local LLM rewrite text here."


def test_rewrite_out_of_range_slide_index_safe():
    """slide_index beyond slides list length should not raise IndexError."""
    from narration_rewriter import rewrite_narration_for_delivery

    entries = [{"slide_index": 99, "narration_text": "Slide 99 narration.", "source_used": "template"}]
    slides = _make_slides_notes(2)
    fake_err = type("LLMBackendError", (Exception,), {})

    with patch.dict("sys.modules", {
        "llm_backend": MagicMock(call_chat=MagicMock(return_value="Safe rewrite for slide 99."), LLMBackendError=fake_err),
        "llm_config": MagicMock(get_narrate_config=MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "key"))),
    }):
        result = rewrite_narration_for_delivery(entries, slides, api_key="key")

    assert len(result) == 1
