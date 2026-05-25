"""Tests for the true-raw baseline configuration.

The script itself makes API calls and is not exercised in unit tests, but the
pure parts (payload builder, output schema) are tested here.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts" / "eval" / "run_true_raw_baseline.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("run_true_raw_baseline", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_script_exists():
    assert SCRIPT_PATH.exists(), f"missing script at {SCRIPT_PATH}"


def test_payload_builder_returns_well_formed_dict():
    mod = _load_module()
    p = mod.build_request_payload(
        slide_index=1, slide_total=5,
        title="Quarterly Update", body="Revenue up 12%",
        model="gpt-4o-mini-2024-07-18",
        temperature=0.7, max_tokens=300,
    )
    assert p["model"] == "gpt-4o-mini-2024-07-18"
    assert p["temperature"] == 0.7
    assert p["max_tokens"] == 300
    roles = [m["role"] for m in p["messages"]]
    assert roles == ["system", "user"]
    user_content = p["messages"][1]["content"]
    assert "Slide 1 of 5" in user_content
    assert "Quarterly Update" in user_content
    assert "Revenue up 12%" in user_content


def test_payload_builder_handles_empty_title_and_body():
    mod = _load_module()
    p = mod.build_request_payload(
        slide_index=2, slide_total=2, title="", body="",
        model="m", temperature=0.5, max_tokens=100,
    )
    user_content = p["messages"][1]["content"]
    # Placeholder strings appear; no exceptions raised
    assert "(no title)" in user_content
    assert "(no body text)" in user_content


def test_system_prompt_does_not_mention_evidence_or_verifier():
    """A0 baseline must not see anything about the grounding system."""
    mod = _load_module()
    sys_prompt = mod.PROMPT_SYSTEM.lower()
    for forbidden in ("evidence", "verifier", "ground", "citation", "fallback"):
        assert forbidden not in sys_prompt


def test_narrate_deck_dry_run_writes_schema(tmp_path, monkeypatch):
    """Dry-run path: no API key required, no network, output schema valid."""
    mod = _load_module()
    # Stub extract_slide_text so we don't need a real PPTX
    def fake_extract(p):
        return [
            {"slide_index": 1, "title": "Intro", "body": "Welcome."},
            {"slide_index": 2, "title": "End", "body": "Thanks."},
        ]
    monkeypatch.setattr(mod, "extract_slide_text", fake_extract)
    out = tmp_path / "deck" / "ai_narration.json"
    result = mod.narrate_deck(
        pptx_path=tmp_path / "irrelevant.pptx",
        out_path=out,
        model="gpt-4o-mini",
        temperature=0.7,
        max_tokens=300,
        dry_run=True,
        api_key=None,
    )
    assert result["condition"] == "A0_true_raw_gpt"
    assert result["slide_count"] == 2
    assert result["ai_rewritten"] is False
    assert all(e["source_used"] == "true_raw_gpt" for e in result["entries"])
    assert out.exists()


def test_narrate_deck_real_run_requires_api_key(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "extract_slide_text", lambda p: [
        {"slide_index": 1, "title": "x", "body": "x"},
    ])
    import pytest
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        mod.narrate_deck(
            pptx_path=tmp_path / "x.pptx",
            out_path=tmp_path / "out.json",
            model="m", temperature=0.7, max_tokens=300,
            dry_run=False, api_key=None,
        )
