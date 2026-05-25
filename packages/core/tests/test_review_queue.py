"""Tests for review_queue.py."""
from __future__ import annotations

from packages.core import review_queue


def _vr(items):
    return {"job_id": "j", "report": items}


def _nar(entries):
    return {"job_id": "j", "entries": entries}


def _e(slide, text, source="ai_narrate"):
    return {"slide_index": slide, "narration_text": text, "source_used": source, "word_count": len(text.split())}


def test_missing_citation_item_is_created():
    items = review_queue.build(
        quality_gate={"fallback_rate": 0.0, "proxy_flagged_rate": 0.0, "job_id": "j", "deck_id": "d"},
        verify_report=_vr([{"slide_index": 1, "reason_codes": ["NO_EVIDENCE_IDS"], "pointers": {"evidence_ids": []}, "is_image_claim": False}]),
        evidence_index={"evidence_items": []},
        ai_narration=_nar([]),
        evidence_health={"risk_level": "low"},
    )
    assert any(i["risk_type"] == "missing_citation" and i["severity"] == "high" for i in items)
    assert any(i["suggested_action"] == "regenerate" for i in items if i["risk_type"] == "missing_citation")


def test_invalid_evidence_id_item_is_block_severity():
    items = review_queue.build(
        quality_gate={"fallback_rate": 0.0, "proxy_flagged_rate": 0.0},
        verify_report=_vr([{
            "slide_index": 2, "reason_codes": ["EVIDENCE_NOT_FOUND"],
            "pointers": {"evidence_ids": ["x"], "invalid_evidence_ids": ["x"]},
            "is_image_claim": False,
        }]),
        evidence_index={"evidence_items": []},
        ai_narration=_nar([]),
        evidence_health={"risk_level": "low"},
    )
    rec = next(i for i in items if i["risk_type"] == "invalid_evidence_id")
    assert rec["severity"] == "high"
    assert rec["suggested_action"] == "block"


def test_low_confidence_vision_item_is_medium():
    items = review_queue.build(
        quality_gate={"fallback_rate": 0.0, "proxy_flagged_rate": 0.0},
        verify_report=_vr([{
            "slide_index": 3, "reason_codes": [], "pointers": {},
            "is_image_claim": True, "confidence_used": 0.3,
        }]),
        evidence_index={"evidence_items": []},
        ai_narration=_nar([]),
        evidence_health={"risk_level": "low"},
    )
    rec = next(i for i in items if i["risk_type"] == "low_confidence_vision")
    assert rec["severity"] == "medium"
    assert rec["suggested_action"] == "edit"


def test_proxy_flag_picked_up_from_narration():
    items = review_queue.build(
        quality_gate={"fallback_rate": 0.0, "proxy_flagged_rate": 0.02},
        verify_report=_vr([]),
        evidence_index={"evidence_items": []},
        ai_narration=_nar([_e(1, "A vibrant scenic landscape backdrop.")]),
        evidence_health={"risk_level": "low"},
    )
    rec = next(i for i in items if i["risk_type"] == "proxy_flag")
    assert rec["slide_index"] == 1
    assert "vibrant" in rec["risk_reason"] or "scenic" in rec["risk_reason"] or "landscape" in rec["risk_reason"]


def test_high_fallback_deck_level_item_added_once():
    entries = [_e(i, "Plain.", source="post_rewrite_fallback") for i in range(1, 11)]
    items = review_queue.build(
        quality_gate={"fallback_rate": 0.9, "proxy_flagged_rate": 0.0},
        verify_report=_vr([]),
        evidence_index={"evidence_items": []},
        ai_narration=_nar(entries),
        evidence_health={"risk_level": "low"},
    )
    high_fallback_items = [i for i in items if i["risk_type"] == "high_fallback"]
    assert len(high_fallback_items) == 1
    assert high_fallback_items[0]["severity"] == "high"


def test_translation_warning_item_created():
    items = review_queue.build(
        quality_gate={"fallback_rate": 0.0, "proxy_flagged_rate": 0.0},
        verify_report=_vr([]),
        evidence_index={"evidence_items": []},
        ai_narration=_nar([]),
        evidence_health={"risk_level": "low"},
        translation_report=[{"slide_index": 2, "success": False, "fallback": "en"}],
    )
    rec = next(i for i in items if i["risk_type"] == "translation_warning")
    assert rec["slide_index"] == 2


def test_weak_evidence_coverage_from_evidence_health_high():
    items = review_queue.build(
        quality_gate={"fallback_rate": 0.0, "proxy_flagged_rate": 0.0},
        verify_report=_vr([]),
        evidence_index={"evidence_items": []},
        ai_narration=_nar([]),
        evidence_health={"risk_level": "high", "risk_reasons": ["no evidence"]},
    )
    rec = next(i for i in items if i["risk_type"] == "weak_evidence_coverage")
    assert rec["severity"] == "high"
    assert rec["suggested_action"] == "block"


def test_evidence_snippets_attached_to_items():
    items = review_queue.build(
        quality_gate={"fallback_rate": 0.0, "proxy_flagged_rate": 0.0},
        verify_report=_vr([{
            "slide_index": 5, "reason_codes": ["NO_EVIDENCE_IDS"],
            "pointers": {"evidence_ids": ["e1"]}, "is_image_claim": False,
        }]),
        evidence_index={"evidence_items": [{"evidence_id": "e1", "content": "hello world"}]},
        ai_narration=_nar([]),
        evidence_health={"risk_level": "low"},
    )
    rec = next(i for i in items if i["risk_type"] == "missing_citation")
    assert rec["evidence_snippets"][0]["evidence_id"] == "e1"
    assert "hello world" in rec["evidence_snippets"][0]["snippet"]
