"""
Doctor: dependency checks for SlideSherlock pipeline.
Checks: LibreOffice, FFmpeg, Poppler, Tesseract (optional).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _find_libreoffice() -> Tuple[bool, str]:
    """Check LibreOffice (required for PPTX -> PDF)."""
    paths = [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice.bin",
        "libreoffice",
        "soffice",
    ]
    for p in paths:
        if os.path.isfile(p):
            try:
                out = subprocess.run(
                    [p, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                version = (
                    (out.stdout or out.stderr or "").strip()[:80]
                    if out.returncode == 0
                    else "found"
                )
                return True, version or p
            except Exception:
                return True, p
        if shutil.which(p):
            try:
                out = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
                version = (
                    (out.stdout or out.stderr or "").strip()[:80]
                    if out.returncode == 0
                    else "found"
                )
                return True, version or p
            except Exception:
                return True, p
    return False, "not found"


def _check_ffmpeg() -> Tuple[bool, str]:
    """Check FFmpeg (required for video composition)."""
    cmd = shutil.which("ffmpeg")
    if not cmd:
        return False, "not found"
    try:
        out = subprocess.run(
            [cmd, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_line = (
            (out.stdout or "").split("\n")[0].strip()[:80] if out.returncode == 0 else "found"
        )
        return True, first_line or "found"
    except Exception:
        return True, cmd


def _check_poppler() -> Tuple[bool, str]:
    """Check Poppler (pdftoppm, required for PDF -> PNG)."""
    cmd = shutil.which("pdftoppm")
    if not cmd:
        return False, "not found (install poppler or poppler-utils)"
    try:
        out = subprocess.run(
            [cmd, "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_line = (
            (out.stderr or out.stdout or "").split("\n")[0].strip()[:80]
            if out.returncode == 0
            else "found"
        )
        return True, first_line or "found"
    except Exception:
        return True, cmd


def _check_tesseract() -> Tuple[bool, str]:
    """Check Tesseract (optional, for vision/OCR)."""
    cmd = shutil.which("tesseract")
    if not cmd:
        return False, "not found (optional; needed for VISION_ENABLED=1)"
    try:
        out = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        first_line = (
            (out.stdout or out.stderr or "").split("\n")[0].strip()[:80]
            if out.returncode == 0
            else "found"
        )
        return True, first_line or "found"
    except Exception:
        return True, cmd


def run_doctor() -> Dict[str, Any]:
    """
    Run all dependency checks. Returns dict suitable for diagnostics.json.
    """
    libreoffice_ok, libreoffice_msg = _find_libreoffice()
    ffmpeg_ok, ffmpeg_msg = _check_ffmpeg()
    poppler_ok, poppler_msg = _check_poppler()
    tesseract_ok, tesseract_msg = _check_tesseract()

    all_required = libreoffice_ok and ffmpeg_ok and poppler_ok

    result = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "all_required_ok": all_required,
        "checks": {
            "libreoffice": {"ok": libreoffice_ok, "required": True, "message": libreoffice_msg},
            "ffmpeg": {"ok": ffmpeg_ok, "required": True, "message": ffmpeg_msg},
            "poppler": {"ok": poppler_ok, "required": True, "message": poppler_msg},
            "tesseract": {"ok": tesseract_ok, "required": False, "message": tesseract_msg},
        },
        "summary": {
            "required": 3,
            "required_ok": sum(1 for v in [libreoffice_ok, ffmpeg_ok, poppler_ok] if v),
            "optional_ok": 1 if tesseract_ok else 0,
        },
    }
    return result


def print_doctor_report(report: Dict[str, Any]) -> None:
    """Print human-readable doctor report to stdout."""
    checks = report.get("checks", {})
    print("SlideSherlock Doctor - dependency checks")
    print("")
    for name, info in checks.items():
        ok = info.get("ok", False)
        req = info.get("required", True)
        msg = info.get("message", "")
        status = "✅" if ok else "❌"
        req_tag = "required" if req else "optional"
        print(f"  {status} {name} ({req_tag}): {msg}")
    print("")
    if report.get("all_required_ok"):
        print("  All required dependencies OK.")
    else:
        print("  ⚠️  Some required dependencies missing. Install them to run the pipeline.")
        print("     LibreOffice: brew install --cask libreoffice | apt install libreoffice")
        print("     FFmpeg:      brew install ffmpeg | apt install ffmpeg")
        print("     Poppler:     brew install poppler | apt install poppler-utils")
