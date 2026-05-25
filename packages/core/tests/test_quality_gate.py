"""Tests for the operational grounding gate."""
from __future__ import annotations

import json
import os

import pytest

from packages.core import quality_gate


def _coverage(passes, rewrites, removes, total):
    return {"pass": passes, "rewrite": rewrites, "remove": removes, "total_claims": total}


def _vr(items):
    return {"job_id": "j", "report": items}


def _nar(entries):
    return {"job_id": "j", "entries": entries}


def _entry(slide, text, source="ai_narrate"):
    return {"slide_index": slide, "narration_text": text, "source_used": source, "word_count": len(text.split())}


# ----- threshold config ----------------------------------------------------


def test_default_thresholds_load():
    t = quality_gate.load_thresholds()
    assert t["thresholds"]["block"]["missing_citation_count_gt"] == 0
    assert t["thresholds"]["block"]["proxy_flagged_rate_gt"] == 0.10
    assert t["thresholds"]["needs_review"]["fallback_rate_gt"] == 0.50


def test_custom_thresholds_load(tmp_path):
    custom = {
        "version": 99,
        "thresholds": {
            "needs_review": {
                "fallback_rate_gt": 0.99,
                "proxy_flagged_rate_gt": 0.99,
                "low_confidence_vision_claim_count_gt": 999,
                "chart_or_table_risk_count_gt": 999,
                "translation_warning_count_gt": 999,
            },
            "block": {
                "missing_citation_count_gt": 999,
                "invalid_evidence_id_count_gt": 999,
                "proxy_flagged_rate_gt": 0.99,
            },
        },
        "definitions": {
            "fabrication_keywords": [],
            "image_claim_keywords": [],
            "chart_like_keywords": [],
            "table_like_keywords": [],
            "low_confidence_vision_threshold": 0.6,
            "image_evidence_kinds": [],
        },
    }
    p = tmp_path / "custom.json"
    p.write_text(json.dumps(custom))
    t = quality_gate.load_thresholds(p)
    assert t["version"] == 99
    assert t["thresholds"]["block"]["proxy_flagged_rate_gt"] == 0.99


# ----- decision logic ------------------------------------------------------


def test_deliver_when_clean():
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}]),
        coverage=_coverage(passes=10, rewrites=0, removes=0, total=10),
        ai_narration=_nar([_entry(1, "This deck discusses regional climate effects.")]),
        evidence_index={"evidence_items": []},
    )
    assert qg["decision"] == "deliver"
    assert qg["reasons"] == []


def test_deliver_with_warnings_when_minor_rewrite_or_fallback():
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}] * 3),
        coverage=_coverage(passes=8, rewrites=2, removes=0, total=10),
        ai_narration=_nar([
            _entry(1, "Slide one summary.", source="ai_narrate"),
            _entry(2, "Slide two summary.", source="post_rewrite_fallback"),
            _entry(3, "Slide three summary.", source="ai_narrate"),
            _entry(4, "Slide four summary.", source="ai_narrate"),
        ]),
        evidence_index={"evidence_items": []},
    )
    assert qg["decision"] == "deliver_with_warnings"
    assert any("fallback" in r or "rewrite" in r for r in qg["reasons"])


def test_block_on_missing_citation():
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": ["NO_EVIDENCE_IDS"], "is_image_claim": False}]),
        coverage=_coverage(passes=0, rewrites=1, removes=0, total=1),
        ai_narration=_nar([_entry(1, "Slide one.", source="ai_narrate")]),
        evidence_index={"evidence_items": []},
    )
    assert qg["decision"] == "block"
    assert any("missing_citation" in r for r in qg["reasons"])


def test_block_on_invalid_evidence_id():
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": ["EVIDENCE_NOT_FOUND"], "is_image_claim": False}]),
        coverage=_coverage(passes=0, rewrites=1, removes=0, total=1),
        ai_narration=_nar([_entry(1, "Slide one.")]),
        evidence_index={"evidence_items": []},
    )
    assert qg["decision"] == "block"


def test_block_on_high_proxy_rate():
    # 2 of 10 = 20% > 10% block threshold
    entries = [_entry(i, "scenic vibrant landscape view.") for i in range(1, 3)]
    entries += [_entry(i, "Plain narration text.") for i in range(3, 11)]
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}]),
        coverage=_coverage(passes=10, rewrites=0, removes=0, total=10),
        ai_narration=_nar(entries),
        evidence_index={"evidence_items": []},
    )
    assert qg["decision"] == "block"
    assert any("proxy_flagged_rate" in r for r in qg["reasons"])


def test_needs_review_on_high_fallback_no_proxy():
    # 6/10 fallback, 0% proxy, no block triggers
    entries = [_entry(i, "Plain narration.", source="post_rewrite_fallback") for i in range(1, 7)]
    entries += [_entry(i, "Plain narration.") for i in range(7, 11)]
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}]),
        coverage=_coverage(passes=10, rewrites=0, removes=0, total=10),
        ai_narration=_nar(entries),
        evidence_index={"evidence_items": []},
    )
    assert qg["decision"] == "needs_review"
    assert any("fallback_rate" in r for r in qg["reasons"])


def test_needs_review_on_low_confidence_vision_claim():
    qg = quality_gate.evaluate(
        verify_report=_vr([{
            "reason_codes": [],
            "is_image_claim": True,
            "confidence_used": 0.4,
        }]),
        coverage=_coverage(passes=1, rewrites=0, removes=0, total=1),
        ai_narration=_nar([_entry(1, "Plain narration text.")]),
        evidence_index={"evidence_items": []},
    )
    assert qg["decision"] == "needs_review"
    assert any("low_confidence_vision" in r for r in qg["reasons"])


def test_chart_table_risk_triggers_review():
    # Narration mentions chart; evidence has no CHART/TABLE kinds
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}]),
        coverage=_coverage(passes=1, rewrites=0, removes=0, total=1),
        ai_narration=_nar([{
            "slide_index": 1,
            "narration_text": "The bar chart shows revenue.",
            "source_used": "ai_narrate",
            "word_count": 6,
        }]),
        evidence_index={"evidence_items": [{
            "kind": "TEXT_SPAN", "evidence_id": "e1",
            "source_ref": {"slide_index": 1},
        }]},
    )
    assert qg["decision"] == "needs_review"
    assert any("chart_or_table_risk" in r for r in qg["reasons"])


def test_translation_warning_triggers_review():
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}]),
        coverage=_coverage(passes=1, rewrites=0, removes=0, total=1),
        ai_narration=_nar([_entry(1, "Plain narration.")]),
        evidence_index={"evidence_items": []},
        translation_report=[{"slide_index": 1, "success": False, "fallback": "en"}],
    )
    assert qg["decision"] == "needs_review"
    assert any("translation_warning" in r for r in qg["reasons"])


def test_table_evidence_suppresses_table_risk():
    """Slide with native TABLE_CELL evidence should not flag table-like narration."""
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}]),
        coverage=_coverage(passes=1, rewrites=0, removes=0, total=1),
        ai_narration=_nar([{
            "slide_index": 1,
            "narration_text": "The table summarizes Q3 revenue by region.",
            "source_used": "ai_narrate",
            "word_count": 7,
        }]),
        evidence_index={"evidence_items": [
            {"kind": "TABLE_HEADER", "evidence_id": "h1", "source_ref": {"slide_index": 1}, "content": "Region"},
            {"kind": "TABLE_CELL",   "evidence_id": "c1", "source_ref": {"slide_index": 1}, "content": "West"},
        ]},
    )
    # No chart/table risk since the slide has TABLE_* evidence backing the narration.
    assert qg["chart_or_table_risk_count"] == 0
    assert qg["decision"] in {"deliver", "deliver_with_warnings"}


def test_chart_evidence_suppresses_chart_risk():
    """Slide with native CHART_* evidence should not flag chart-like narration."""
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}]),
        coverage=_coverage(passes=1, rewrites=0, removes=0, total=1),
        ai_narration=_nar([{
            "slide_index": 1,
            "narration_text": "The bar chart shows Win2k service packs increasing over time.",
            "source_used": "ai_narrate",
            "word_count": 9,
        }]),
        evidence_index={"evidence_items": [
            {"kind": "CHART_TITLE", "evidence_id": "t1", "source_ref": {"slide_index": 1}, "content": "Win2k Service Packs"},
            {"kind": "CHART_VALUE", "evidence_id": "v1", "source_ref": {"slide_index": 1}, "content": "SP1 = 71"},
        ]},
    )
    assert qg["chart_or_table_risk_count"] == 0
    assert qg["decision"] in {"deliver", "deliver_with_warnings"}


def test_chart_narration_still_flags_when_only_table_evidence():
    """Native TABLE evidence does NOT cover chart-shaped claims (charts still go through vision)."""
    qg = quality_gate.evaluate(
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}]),
        coverage=_coverage(passes=1, rewrites=0, removes=0, total=1),
        ai_narration=_nar([{
            "slide_index": 1,
            "narration_text": "The bar chart shows growth.",
            "source_used": "ai_narrate",
            "word_count": 5,
        }]),
        evidence_index={"evidence_items": [
            {"kind": "TABLE_CELL", "evidence_id": "c1", "source_ref": {"slide_index": 1}, "content": "x"},
        ]},
    )
    # Still risk: no CHART evidence kind exists yet.
    assert qg["chart_or_table_risk_count"] == 1


def test_write_quality_gate_writes_json(tmp_path):
    out = tmp_path / "qg.json"
    quality_gate.write_quality_gate(
        out,
        verify_report=_vr([{"reason_codes": [], "is_image_claim": False}]),
        coverage=_coverage(passes=1, rewrites=0, removes=0, total=1),
        ai_narration=_nar([_entry(1, "Plain narration.")]),
        evidence_index={"evidence_items": []},
    )
    data = json.loads(out.read_text())
    assert data["decision"] == "deliver"
    assert data["schema_version"] == "1.0"
