"""Tests for evidence_health.py."""
from __future__ import annotations

import json

from packages.core import evidence_health


def _ev(slide_index, kind, content="x", confidence=None, evidence_id=None):
    item = {
        "kind": kind,
        "content": content,
        "source_ref": {"slide_index": slide_index},
        "evidence_id": evidence_id or f"{kind}-{slide_index}",
    }
    if confidence is not None:
        item["confidence"] = confidence
    return item


def test_no_slides_is_high_risk():
    eh = evidence_health.evaluate(
        evidence_index={"evidence_items": []},
    )
    assert eh["risk_level"] == "high"
    assert eh["slides_total"] == 0


def test_text_only_deck_is_low_risk():
    items = [_ev(i, "TEXT_SPAN", content="bullet text") for i in range(1, 11)]
    eh = evidence_health.evaluate(
        evidence_index={"evidence_items": items},
    )
    assert eh["slides_total"] == 10
    assert eh["slides_with_text"] == 10
    assert eh["slides_with_no_evidence"] == 0
    assert eh["risk_level"] == "low"
    assert eh["risk_reasons"] == []


def test_no_evidence_on_30pct_of_slides_promotes_to_high():
    items = [_ev(i, "TEXT_SPAN") for i in range(1, 7)]  # 6 slides have evidence
    # Simulate slides 7..10 with no evidence by passing slide_metrics
    eh = evidence_health.evaluate(
        evidence_index={"evidence_items": items},
        slide_metrics={"slide_count": 10},
    )
    # 4/10 = 40% with no evidence, > 30% threshold
    assert eh["slides_with_no_evidence"] == 4
    assert eh["risk_level"] == "high"
    assert any("slides_with_no_evidence" in r for r in eh["risk_reasons"])


def test_image_heavy_deck_with_low_conf_vision_is_at_least_medium():
    items = []
    for i in range(1, 11):
        items.append(_ev(i, "IMAGE_CAPTION", confidence=0.4))
        items.append(_ev(i, "IMAGE_OBJECTS", confidence=0.3))
    eh = evidence_health.evaluate(
        evidence_index={"evidence_items": items},
        slide_metrics={"slide_count": 10},
    )
    assert eh["slides_with_text"] == 0
    assert eh["slides_with_low_confidence_vision"] == 10
    assert eh["risk_level"] == "high"  # low_conf > 30% promotes to high


def test_chart_like_table_like_detection_raises_to_at_least_medium():
    items = [
        _ev(1, "TEXT_SPAN", content="Quarterly revenue chart shows growth."),
        _ev(2, "TEXT_SPAN", content="See the table below."),
        _ev(3, "TEXT_SPAN", content="Plain bullet."),
    ]
    eh = evidence_health.evaluate(
        evidence_index={"evidence_items": items},
        slide_metrics={"slide_count": 3},
    )
    assert eh["chart_like_evidence_count"] >= 1
    assert eh["table_like_evidence_count"] >= 1
    assert eh["risk_level"] in {"medium", "high"}


def test_evidence_by_kind_count_is_correct():
    items = [_ev(1, "TEXT_SPAN"), _ev(1, "TEXT_SPAN"), _ev(2, "SHAPE_LABEL")]
    eh = evidence_health.evaluate(
        evidence_index={"evidence_items": items},
    )
    assert eh["evidence_by_kind"] == {"SHAPE_LABEL": 1, "TEXT_SPAN": 2}


def test_write_evidence_health_writes_file(tmp_path):
    out = tmp_path / "eh.json"
    evidence_health.write_evidence_health(
        out,
        evidence_index={"evidence_items": [_ev(1, "TEXT_SPAN")]},
    )
    data = json.loads(out.read_text())
    assert data["schema_version"] == "1.0"
    assert data["risk_level"] in {"low", "medium", "high"}
