"""
Unit tests for doctor dependency checks.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from doctor import run_doctor, print_doctor_report


def test_run_doctor_returns_dict():
    """run_doctor returns dict with checks and summary."""
    report = run_doctor()
    assert isinstance(report, dict)
    assert "schema_version" in report
    assert "all_required_ok" in report
    assert "checks" in report
    assert "summary" in report
    for key in ("libreoffice", "ffmpeg", "poppler", "tesseract"):
        assert key in report["checks"]
        assert "ok" in report["checks"][key]
        assert "required" in report["checks"][key]
        assert "message" in report["checks"][key]


def test_print_doctor_report_no_error():
    """print_doctor_report runs without raising."""
    report = run_doctor()
    print_doctor_report(report)  # should not raise
