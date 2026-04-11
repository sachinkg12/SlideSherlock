"""
Unit tests for vision_provider.py.
Tests: constants, ImageExtractionResult, StubVisionExtractor, StubVisionProvider,
VisionExtractor interface, VisionProvider interface, get_vision_extractor factory,
get_vision_provider factory.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vision_provider import (
    KIND_IMAGE_CAPTION,
    KIND_IMAGE_OBJECTS,
    KIND_IMAGE_ACTIONS,
    KIND_DIAGRAM_ENTITIES,
    KIND_DIAGRAM_INTERACTIONS,
    KIND_DIAGRAM_SUMMARY,
    REASON_LOW_CONFIDENCE,
    REASON_EXTRACTION_FAILED,
    REASON_NO_VISION_PROVIDER,
    REASON_SAFE_FALLBACK,
    CONFIDENCE_THRESHOLD,
    ImageExtractionResult,
    VisionExtractor,
    StubVisionExtractor,
    StubVisionProvider,
    get_vision_extractor,
    get_vision_provider,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_kind_constants_are_strings(self):
        assert isinstance(KIND_IMAGE_CAPTION, str)
        assert isinstance(KIND_DIAGRAM_SUMMARY, str)

    def test_confidence_threshold(self):
        assert CONFIDENCE_THRESHOLD == 0.7

    def test_reason_codes_defined(self):
        assert REASON_SAFE_FALLBACK == "SAFE_FALLBACK"
        assert REASON_NO_VISION_PROVIDER == "NO_VISION_PROVIDER"


# ---------------------------------------------------------------------------
# ImageExtractionResult dataclass
# ---------------------------------------------------------------------------

class TestImageExtractionResult:
    def test_required_fields(self):
        r = ImageExtractionResult(
            slide_index=1,
            content="test content",
            kind=KIND_IMAGE_CAPTION,
            confidence=0.8,
        )
        assert r.slide_index == 1
        assert r.content == "test content"
        assert r.kind == KIND_IMAGE_CAPTION
        assert r.confidence == 0.8

    def test_optional_fields_default_to_none(self):
        r = ImageExtractionResult(
            slide_index=0,
            content="",
            kind=KIND_DIAGRAM_SUMMARY,
            confidence=0.0,
        )
        assert r.reason_code is None
        assert r.image_bbox is None
        assert r.image_uri is None
        assert r.ppt_picture_shape_id is None
        assert r.slide_png_uri is None
        assert r.metadata is None

    def test_full_construction(self):
        r = ImageExtractionResult(
            slide_index=2,
            content="A flowchart",
            kind=KIND_DIAGRAM_SUMMARY,
            confidence=0.5,
            reason_code=REASON_SAFE_FALLBACK,
            image_bbox={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            image_uri="jobs/j1/img.png",
            ppt_picture_shape_id="shape_001",
            slide_png_uri="jobs/j1/slide.png",
            metadata={"source": "vision"},
        )
        assert r.reason_code == REASON_SAFE_FALLBACK
        assert r.image_bbox["w"] == 1.0
        assert r.metadata["source"] == "vision"


# ---------------------------------------------------------------------------
# StubVisionExtractor
# ---------------------------------------------------------------------------

class TestStubVisionExtractor:
    @pytest.fixture
    def extractor(self):
        return StubVisionExtractor()

    def test_extract_photo_returns_list_with_one_result(self, extractor):
        results = extractor.extract_photo(b"\x00\x01\x02", slide_index=0)
        assert len(results) == 1

    def test_extract_photo_result_is_image_caption_kind(self, extractor):
        results = extractor.extract_photo(b"\x00", slide_index=1)
        assert results[0].kind == KIND_IMAGE_CAPTION

    def test_extract_photo_confidence_below_threshold(self, extractor):
        results = extractor.extract_photo(b"\x00", slide_index=0)
        assert results[0].confidence < CONFIDENCE_THRESHOLD

    def test_extract_photo_reason_code_is_safe_fallback(self, extractor):
        results = extractor.extract_photo(b"\x00", slide_index=0)
        assert results[0].reason_code == REASON_SAFE_FALLBACK

    def test_extract_photo_preserves_slide_index(self, extractor):
        results = extractor.extract_photo(b"\x00", slide_index=7)
        assert results[0].slide_index == 7

    def test_extract_diagram_returns_list_with_one_result(self, extractor):
        results = extractor.extract_diagram(b"\x00", slide_index=0)
        assert len(results) == 1

    def test_extract_diagram_is_diagram_summary_kind(self, extractor):
        results = extractor.extract_diagram(b"\x00", slide_index=0)
        assert results[0].kind == KIND_DIAGRAM_SUMMARY

    def test_extract_diagram_with_vision_graph_includes_labels(self, extractor):
        vision_graph = {
            "nodes": [
                {"node_id": "n1", "label_text": "Router"},
                {"node_id": "n2", "label_text": "Switch"},
            ]
        }
        results = extractor.extract_diagram(b"\x00", slide_index=0, vision_graph=vision_graph)
        assert "Router" in results[0].content or "Switch" in results[0].content

    def test_extract_diagram_without_graph_has_generic_content(self, extractor):
        results = extractor.extract_diagram(b"\x00", slide_index=0, vision_graph=None)
        assert "diagram" in results[0].content.lower()

    def test_extract_diagram_metadata_includes_vision_nodes_used(self, extractor):
        vision_graph = {"nodes": [{"node_id": "n1", "label_text": "A"}]}
        results = extractor.extract_diagram(b"\x00", slide_index=0, vision_graph=vision_graph)
        assert results[0].metadata is not None
        assert "vision_nodes_used" in results[0].metadata


# ---------------------------------------------------------------------------
# StubVisionProvider
# ---------------------------------------------------------------------------

class TestStubVisionProvider:
    @pytest.fixture
    def provider(self):
        return StubVisionProvider()

    def test_caption_returns_dict(self, provider):
        result = provider.caption("jobs/j1/img.png")
        assert isinstance(result, dict)
        assert "caption" in result
        assert "confidence" in result

    def test_caption_has_low_confidence(self, provider):
        result = provider.caption("jobs/j1/img.png")
        assert result["confidence"] < CONFIDENCE_THRESHOLD

    def test_caption_reason_code_indicates_unavailable(self, provider):
        result = provider.caption("jobs/j1/img.png")
        assert result.get("reason_code") is not None

    def test_extract_returns_dict(self, provider):
        result = provider.extract("jobs/j1/img.png")
        assert isinstance(result, dict)

    def test_extract_has_empty_objects_and_actions(self, provider):
        result = provider.extract("jobs/j1/img.png")
        assert result["objects"] == []
        assert result["actions"] == []
        assert result["scene_tags"] == []

    def test_extract_has_low_global_confidence(self, provider):
        result = provider.extract("jobs/j1/img.png", mode="photo")
        assert result["global_confidence"] < CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# get_vision_extractor factory
# ---------------------------------------------------------------------------

class TestGetVisionExtractor:
    def test_stub_provider_env_returns_stub(self):
        with patch.dict(os.environ, {"VISION_EXTRACTOR_PROVIDER": "stub"}, clear=False):
            extractor = get_vision_extractor()
        assert isinstance(extractor, StubVisionExtractor)

    def test_default_when_env_not_set_returns_stub(self):
        env = {k: v for k, v in os.environ.items() if k != "VISION_EXTRACTOR_PROVIDER"}
        with patch.dict(os.environ, env, clear=True):
            extractor = get_vision_extractor()
        assert isinstance(extractor, StubVisionExtractor)

    def test_openai_without_api_key_falls_back_to_stub(self):
        env = {k: v for k, v in os.environ.items() if k not in ("VISION_EXTRACTOR_PROVIDER", "OPENAI_API_KEY")}
        env["VISION_EXTRACTOR_PROVIDER"] = "openai"
        with patch.dict(os.environ, env, clear=True):
            extractor = get_vision_extractor()
        assert isinstance(extractor, StubVisionExtractor)


# ---------------------------------------------------------------------------
# get_vision_provider factory
# ---------------------------------------------------------------------------

class TestGetVisionProvider:
    def test_stub_env_returns_stub(self):
        with patch.dict(os.environ, {"VISION_PROVIDER": "stub"}, clear=False):
            provider = get_vision_provider()
        assert isinstance(provider, StubVisionProvider)

    def test_unknown_provider_returns_stub(self):
        with patch.dict(os.environ, {"VISION_PROVIDER": "nonexistent_llm"}, clear=False):
            provider = get_vision_provider()
        assert isinstance(provider, StubVisionProvider)

    def test_factory_exception_falls_back_to_stub(self):
        from vision_provider import _VISION_PROVIDER_REGISTRY
        original = _VISION_PROVIDER_REGISTRY.get("openai")
        _VISION_PROVIDER_REGISTRY["openai"] = lambda: (_ for _ in ()).throw(RuntimeError("down"))
        with patch.dict(os.environ, {"VISION_PROVIDER": "openai"}, clear=False):
            provider = get_vision_provider()
        assert isinstance(provider, StubVisionProvider)
        if original is not None:
            _VISION_PROVIDER_REGISTRY["openai"] = original
