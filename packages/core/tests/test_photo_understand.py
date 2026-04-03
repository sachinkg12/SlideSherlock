"""
Unit tests for PHOTO understanding pipeline.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vision_provider import StubVisionProvider, REASON_VISION_UNAVAILABLE


def test_stub_vision_provider_caption():
    """Stub provider returns low-confidence caption."""
    p = StubVisionProvider()
    r = p.caption("uri", lang="en-US")
    assert "caption" in r
    assert "Image present" in r["caption"]
    assert r["confidence"] <= 0.2
    assert r.get("reason_code") == REASON_VISION_UNAVAILABLE


def test_stub_vision_provider_extract():
    """Stub provider returns empty objects/actions/tags."""
    p = StubVisionProvider()
    r = p.extract("uri", lang="en-US")
    assert r.get("objects") == []
    assert r.get("actions") == []
    assert r.get("scene_tags") == []
    assert r.get("global_confidence", 0) <= 0.2
