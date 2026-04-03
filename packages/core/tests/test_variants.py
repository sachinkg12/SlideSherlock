"""
Unit tests for output variants.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from variants import build_output_variants


def test_build_output_variants_default():
    """Default: single en variant."""
    variants = build_output_variants(None)
    assert len(variants) == 1
    assert variants[0]["id"] == "en"
    assert variants[0]["lang"] == "en-US"
    assert variants[0]["voice_id"] == "default_en"
    assert variants[0]["notes_translate"] is False


def test_build_output_variants_with_requested_language():
    """With requested_language: en + l2."""
    variants = build_output_variants("hi-IN")
    assert len(variants) == 2
    assert variants[0]["id"] == "en"
    assert variants[1]["id"] == "l2"
    assert variants[1]["lang"] == "hi-IN"
    assert variants[1]["notes_translate"] is True
    assert "hi" in variants[1]["voice_id"]
