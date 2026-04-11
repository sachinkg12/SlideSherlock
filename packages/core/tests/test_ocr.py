"""
Tests for ocr.py: _ocr_id, run_ocr_tesseract, run_ocr_easyocr, run_ocr.
All external OCR backends are mocked.
"""
from __future__ import annotations

import os
import sys
import hashlib
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ocr as ocr_module
from ocr import _ocr_id, run_ocr, run_ocr_tesseract, run_ocr_easyocr


# ---------------------------------------------------------------------------
# _ocr_id
# ---------------------------------------------------------------------------

def test_ocr_id_is_deterministic():
    bbox = {"left": 10, "top": 20, "width": 50, "height": 30}
    id1 = _ocr_id(1, 0, bbox, "hello")
    id2 = _ocr_id(1, 0, bbox, "hello")
    assert id1 == id2


def test_ocr_id_differs_by_text():
    bbox = {"left": 0, "top": 0, "width": 10, "height": 10}
    assert _ocr_id(1, 0, bbox, "foo") != _ocr_id(1, 0, bbox, "bar")


def test_ocr_id_is_hex_string():
    bbox = {"left": 0, "top": 0, "width": 0, "height": 0}
    result = _ocr_id(2, 3, bbox, "text")
    assert len(result) == 64
    int(result, 16)  # must be valid hex


# ---------------------------------------------------------------------------
# run_ocr_tesseract – mocked pytesseract
# ---------------------------------------------------------------------------

def _make_tesseract_data(texts, confs, lefts, tops, widths, heights):
    return {
        "text": texts,
        "conf": confs,
        "left": lefts,
        "top": tops,
        "width": widths,
        "height": heights,
    }


def test_run_ocr_tesseract_returns_spans():
    data = _make_tesseract_data(
        ["Hello", "World", ""],
        [90, 80, -1],
        [0, 100, 0],
        [0, 0, 0],
        [50, 60, 0],
        [20, 20, 0],
    )
    fake_output = MagicMock()

    with patch.object(ocr_module, "PYTESSERACT_AVAILABLE", True), \
         patch.object(ocr_module, "pytesseract") as mock_tess, \
         patch.object(ocr_module, "Output", fake_output):
        mock_tess.image_to_data.return_value = data
        spans = run_ocr_tesseract(MagicMock(), slide_index=1)

    assert len(spans) == 2
    texts = [s["text"] for s in spans]
    assert "Hello" in texts
    assert "World" in texts


def test_run_ocr_tesseract_normalises_confidence():
    data = _make_tesseract_data(["Hi"], [75], [5], [5], [30], [15])
    fake_output = MagicMock()

    with patch.object(ocr_module, "PYTESSERACT_AVAILABLE", True), \
         patch.object(ocr_module, "pytesseract") as mock_tess, \
         patch.object(ocr_module, "Output", fake_output):
        mock_tess.image_to_data.return_value = data
        spans = run_ocr_tesseract(MagicMock(), slide_index=0)

    assert spans[0]["conf"] == pytest.approx(0.75)


def test_run_ocr_tesseract_unavailable_returns_empty():
    with patch.object(ocr_module, "PYTESSERACT_AVAILABLE", False):
        result = run_ocr_tesseract(MagicMock(), slide_index=0)
    assert result == []


def test_run_ocr_tesseract_skips_negative_conf_text():
    # text with conf="-1" (string) should still produce a span with conf=0
    data = _make_tesseract_data(["Ghost"], ["-1"], [0], [0], [10], [10])
    fake_output = MagicMock()

    with patch.object(ocr_module, "PYTESSERACT_AVAILABLE", True), \
         patch.object(ocr_module, "pytesseract") as mock_tess, \
         patch.object(ocr_module, "Output", fake_output):
        mock_tess.image_to_data.return_value = data
        spans = run_ocr_tesseract(MagicMock(), slide_index=0)

    assert len(spans) == 1
    assert spans[0]["conf"] == 0.0


# ---------------------------------------------------------------------------
# run_ocr_easyocr – mocked easyocr
# ---------------------------------------------------------------------------

def test_run_ocr_easyocr_returns_spans():
    box_pts = [[10, 10], [60, 10], [60, 30], [10, 30]]
    fake_results = [(box_pts, "EasyText", 0.88)]

    fake_reader = MagicMock()
    fake_reader.readtext.return_value = fake_results

    fake_np = MagicMock()
    fake_np.array.return_value = [[0]]

    with patch.object(ocr_module, "EASYOCR_AVAILABLE", True), \
         patch.object(ocr_module, "easyocr") as mock_easy, \
         patch.dict("sys.modules", {"numpy": fake_np}):
        mock_easy.Reader.return_value = fake_reader
        img = MagicMock()
        img.mode = "RGB"
        img.size = (200, 100)
        spans = run_ocr_easyocr(img, slide_index=2)

    assert len(spans) == 1
    assert spans[0]["text"] == "EasyText"
    assert spans[0]["conf"] == pytest.approx(0.88)


def test_run_ocr_easyocr_unavailable_returns_empty():
    with patch.object(ocr_module, "EASYOCR_AVAILABLE", False):
        result = run_ocr_easyocr(MagicMock(), slide_index=0)
    assert result == []


# ---------------------------------------------------------------------------
# run_ocr – dispatcher
# ---------------------------------------------------------------------------

def test_run_ocr_routes_to_tesseract_by_default():
    with patch("ocr.run_ocr_tesseract", return_value=[{"ocr_id": "x"}]) as mock_tess, \
         patch("ocr.run_ocr_easyocr", return_value=[]) as mock_easy:
        result = run_ocr(MagicMock(), slide_index=0)
    mock_tess.assert_called_once()
    mock_easy.assert_not_called()
    assert result == [{"ocr_id": "x"}]


def test_run_ocr_routes_to_easyocr_when_specified():
    with patch("ocr.run_ocr_tesseract", return_value=[]) as mock_tess, \
         patch("ocr.run_ocr_easyocr", return_value=[{"ocr_id": "y"}]) as mock_easy:
        result = run_ocr(MagicMock(), slide_index=0, backend="easyocr")
    mock_easy.assert_called_once()
    mock_tess.assert_not_called()
    assert result == [{"ocr_id": "y"}]
