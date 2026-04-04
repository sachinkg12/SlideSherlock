"""Tests for translation module."""
from __future__ import annotations


def test_derive_narration_from_script():
    from translation import derive_narration_from_script

    script = {
        "segments": [
            {"slide_index": 1, "text": "Intro.", "claim_id": "c1"},
            {"slide_index": 1, "text": "More.", "claim_id": "c2"},
            {"slide_index": 2, "text": "Slide two.", "claim_id": "c3"},
        ],
    }
    entries = derive_narration_from_script(script, 3)
    assert len(entries) == 3
    assert entries[0]["narration_text"] == "Intro. More."
    assert entries[0]["slide_index"] == 1
    assert entries[1]["narration_text"] == "Slide two."
    assert entries[1]["slide_index"] == 2
    assert entries[2]["narration_text"] == ""
    assert entries[2]["slide_index"] == 3


def test_translate_script_segments_same_lang():
    from translation import translate_script_segments
    from translator_provider import StubTranslatorProvider

    script = {
        "segments": [{"claim_id": "c1", "slide_index": 1, "text": "Hello", "entity_ids": ["n1"]}]
    }
    translated, report, ok = translate_script_segments(
        script, StubTranslatorProvider(), "en-US", "en-US"
    )
    assert ok
    assert translated["segments"][0]["text"] == "Hello"
    assert translated["segments"][0]["entity_ids"] == ["n1"]


def test_translate_script_segments_stub_fallback():
    from translation import translate_script_segments
    from translator_provider import StubTranslatorProvider

    script = {
        "segments": [{"claim_id": "c1", "slide_index": 1, "text": "Hello", "entity_ids": ["n1"]}]
    }
    translated, report, ok = translate_script_segments(
        script, StubTranslatorProvider(), "en-US", "hi-IN"
    )
    assert not ok
    assert translated["segments"][0]["text"] == "Hello"
    assert report[0]["fallback"] == "en"


def test_build_translation_report():
    from translation import build_translation_report

    report = build_translation_report(
        "job1",
        "l2",
        "hi-IN",
        [{"success": True}, {"success": False}],
        [{"success": True}],
        True,
        False,
    )
    assert report["variant_id"] == "l2"
    assert report["script_translated"] == 1
    assert report["script_total"] == 2
    assert report["notes_translated"] == 1
    assert report["degraded"] is False
