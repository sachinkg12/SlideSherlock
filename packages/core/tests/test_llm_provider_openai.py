"""
Unit tests for llm_provider_openai.py.
Tests: OpenAILLMProvider initialization, _chat dispatch, generate_segment,
generate_narration, fallback behavior.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def provider_with_key():
    """Provider initialized with explicit API key."""
    from llm_provider_openai import OpenAILLMProvider
    return OpenAILLMProvider(model="gpt-4o", api_key="sk-test-key")


@pytest.fixture
def minimal_graph():
    return {"nodes": [], "edges": [], "clusters": []}


@pytest.fixture
def rich_graph():
    return {
        "nodes": [
            {"node_id": "n1", "label_text": "API Gateway"},
            {"node_id": "n2", "label_text": "Auth Service"},
        ],
        "edges": [
            {"edge_id": "e1", "src_node_id": "n1", "dst_node_id": "n2"}
        ],
        "clusters": [],
    }


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestOpenAILLMProviderInit:
    def test_stores_model_and_key(self, provider_with_key):
        assert provider_with_key._model == "gpt-4o"
        assert provider_with_key._api_key == "sk-test-key"

    def test_reads_api_key_from_env_when_not_provided(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-from-env"}, clear=False):
            from llm_provider_openai import OpenAILLMProvider
            p = OpenAILLMProvider()
        assert p._api_key == "sk-from-env"

    def test_default_model_is_gpt4o(self):
        from llm_provider_openai import OpenAILLMProvider
        p = OpenAILLMProvider(api_key="sk-x")
        assert p._model == "gpt-4o"


# ---------------------------------------------------------------------------
# _chat method
# ---------------------------------------------------------------------------

class TestChatMethod:
    def test_raises_runtime_error_without_api_key(self):
        from llm_provider_openai import OpenAILLMProvider
        p = OpenAILLMProvider(model="gpt-4o", api_key="")
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY not set"):
                p._chat([{"role": "user", "content": "hi"}])

    def test_delegates_to_call_chat(self, provider_with_key):
        # call_chat is imported lazily inside _chat from llm_backend, so patch there
        with patch("llm_backend.call_chat", return_value="mocked output") as mock_call:
            result = provider_with_key._chat([{"role": "user", "content": "hello"}])
        assert result == "mocked output"
        mock_call.assert_called_once()
        kwargs = mock_call.call_args.kwargs
        assert kwargs["base_url"] == "https://api.openai.com/v1"
        assert kwargs["model"] == "gpt-4o"
        assert kwargs["api_key"] == "sk-test-key"


# ---------------------------------------------------------------------------
# generate_segment
# ---------------------------------------------------------------------------

class TestGenerateSegment:
    def test_returns_llm_output_on_success(self, provider_with_key, minimal_graph):
        section = {"section_type": "intro", "slide_index": 1}
        with patch.object(provider_with_key, "_chat", return_value="Natural narration text."):
            result = provider_with_key.generate_segment(section, minimal_graph, [], [])
        assert result == "Natural narration text."

    def test_falls_back_to_notes_when_llm_fails(self, provider_with_key, minimal_graph):
        section = {"section_type": "intro", "slide_index": 1}
        bundle = {"notes": "Fallback speaker notes.", "slide_text": ""}
        with patch.object(provider_with_key, "_chat", side_effect=RuntimeError("API down")):
            result = provider_with_key.generate_segment(
                section, minimal_graph, [], [], context_bundle=bundle
            )
        assert result == "Fallback speaker notes."

    def test_falls_back_to_slide_text_when_no_notes(self, provider_with_key, minimal_graph):
        section = {"section_type": "intro", "slide_index": 2}
        bundle = {"notes": "", "slide_text": "Architecture overview"}
        with patch.object(provider_with_key, "_chat", side_effect=RuntimeError("API down")):
            result = provider_with_key.generate_segment(
                section, minimal_graph, [], [], context_bundle=bundle
            )
        assert "Architecture overview" in result

    def test_final_fallback_is_slide_number(self, provider_with_key, minimal_graph):
        section = {"section_type": "intro", "slide_index": 5}
        with patch.object(provider_with_key, "_chat", side_effect=RuntimeError("API down")):
            result = provider_with_key.generate_segment(section, minimal_graph, [], [])
        assert "5" in result

    def test_builds_context_from_bundle_slide_text(self, provider_with_key, minimal_graph):
        section = {"section_type": "nodes", "slide_index": 0}
        bundle = {
            "slide_text": "Microservices diagram",
            "notes": "",
            "graph_summary": "",
            "image_evidence_items": [],
        }
        captured_messages = []
        def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return "result"
        with patch.object(provider_with_key, "_chat", side_effect=capture_chat):
            provider_with_key.generate_segment(section, minimal_graph, [], [], context_bundle=bundle)
        user_msg = next(m for m in captured_messages if m["role"] == "user")
        assert "Microservices" in user_msg["content"]

    def test_graph_nodes_included_in_context(self, provider_with_key, rich_graph):
        section = {"section_type": "nodes", "slide_index": 0}
        captured_messages = []
        def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return "result"
        with patch.object(provider_with_key, "_chat", side_effect=capture_chat):
            provider_with_key.generate_segment(section, rich_graph, [], [])
        all_text = " ".join(m["content"] for m in captured_messages if isinstance(m["content"], str))
        assert "API Gateway" in all_text

    def test_summary_section_uses_closing_prompt(self, provider_with_key, minimal_graph):
        section = {"section_type": "summary", "slide_index": 3}
        captured_messages = []
        def capture_chat(messages, **kwargs):
            captured_messages.extend(messages)
            return "result"
        with patch.object(provider_with_key, "_chat", side_effect=capture_chat):
            provider_with_key.generate_segment(section, minimal_graph, [], [])
        user_msg = next(m for m in captured_messages if m["role"] == "user")
        assert "closing" in user_msg["content"].lower() or "slide 3" in user_msg["content"]


# ---------------------------------------------------------------------------
# generate_narration
# ---------------------------------------------------------------------------

class TestGenerateNarration:
    def test_returns_tuple_on_success(self, provider_with_key):
        blueprint = {
            "slide_index": 1,
            "slide_type": "content",
            "template_narration": "Slide about services",
            "llm_context": {
                "nodes": [{"node_id": "n1", "label_text": "Service A"}],
                "edges": [],
                "evidence_ids": ["e1"],
                "notes": "Some notes",
                "slide_text": "Service architecture",
            },
        }
        with patch.object(provider_with_key, "_chat", return_value="Narration generated."):
            result = provider_with_key.generate_narration(blueprint)
        assert result is not None
        narration, entity_ids, evidence_ids = result
        assert narration == "Narration generated."
        assert "n1" in entity_ids
        assert "e1" in evidence_ids

    def test_returns_none_when_llm_fails(self, provider_with_key):
        blueprint = {
            "slide_index": 0,
            "slide_type": "content",
            "llm_context": {},
        }
        with patch.object(provider_with_key, "_chat", side_effect=RuntimeError("down")):
            result = provider_with_key.generate_narration(blueprint)
        assert result is None

    def test_returns_none_when_chat_returns_empty(self, provider_with_key):
        blueprint = {
            "slide_index": 0,
            "slide_type": "content",
            "llm_context": {},
        }
        with patch.object(provider_with_key, "_chat", return_value=""):
            result = provider_with_key.generate_narration(blueprint)
        assert result is None
