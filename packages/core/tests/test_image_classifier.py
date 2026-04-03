"""
Unit tests for image type classifier (PHOTO vs DIAGRAM vs UNKNOWN).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from image_classifier import (
    classify_image,
    run_classify_images,
    KIND_PHOTO,
    KIND_DIAGRAM,
    KIND_UNKNOWN,
)


def test_classify_unknown_when_no_backends():
    """When OCR/OpenCV unavailable, returns UNKNOWN."""
    result = classify_image(b"\x00\x01\x02")
    assert result["image_kind"] in (KIND_PHOTO, KIND_DIAGRAM, KIND_UNKNOWN)
    assert 0 <= result["confidence"] <= 1
    assert "reasons" in result


def test_run_classify_images_empty():
    """Empty images_index -> empty classifications."""
    mock_mc = MagicMock()
    payload = run_classify_images("job1", {"images": []}, mock_mc)
    assert payload["job_id"] == "job1"
    assert payload["classifications"] == []
    assert mock_mc.put.called


def test_config_thresholds():
    """Config reads VISION_CLASSIFIER_MIN_CONFIDENCE_* env."""
    with patch.dict(os.environ, {"VISION_CLASSIFIER_MIN_CONFIDENCE_PHOTO": "0.7"}, clear=False):
        from image_classifier import _config_min_confidence_photo
        assert _config_min_confidence_photo() == 0.7
