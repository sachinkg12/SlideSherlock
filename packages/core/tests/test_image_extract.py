"""
Unit tests for embedded image extraction from PPTX.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from image_extract import (
    _stable_image_id,
    _ext_from_content_type,
    extract_images_from_pptx,
)


def test_stable_image_id():
    """image_id is stable for same job, slide, ppt_shape_id."""
    a = _stable_image_id("job1", 1, "42")
    b = _stable_image_id("job1", 1, "42")
    assert a == b
    c = _stable_image_id("job1", 1, "43")
    assert a != c
    d = _stable_image_id("job2", 1, "42")
    assert a != d


def test_ext_from_content_type():
    assert _ext_from_content_type("image/png") == "png"
    assert _ext_from_content_type("image/jpeg") == "jpg"
    assert _ext_from_content_type("image/gif") == "gif"
    assert _ext_from_content_type("image/unknown") == "png"


def test_extract_images_empty_without_pptx():
    """Without python-pptx or invalid path, returns empty index."""
    mock_mc = MagicMock()
    result = extract_images_from_pptx("", "job1", mock_mc)
    assert result["job_id"] == "job1"
    assert result["images"] == []
    assert "schema_version" in result
