"""Tests for production_summary.py."""
from __future__ import annotations

import json

from packages.core import production_summary


def _qg(decision="deliver", **extra):
    base = {
        "schema_version": "1.0",
        "job_id": "j", "deck_id": "d", "language": "en",
        "decision": decision, "reasons": extra.get("reasons", []),
        "total_slides": 10, "total_segments": 10,
        "pass_count": 8, "rewrite_count": 2, "remove_count": 0,
        "fallback_count": 1, "fallback_rate": 0.1,
        "proxy_flagged_slide_count": 0, "proxy_flagged_rate": 0.0,
        "translation_warning_count": 0,
    }
    base.update(extra)
    return base


def _eh(**extra):
    base = {
        "slides_total": 10,
        "slides_with_text": 9, "slides_with_images": 4,
        "slides_with_no_evidence": 0, "slides_with_low_confidence_vision": 0,
        "chart_like_evidence_count": 0, "table_like_evidence_count": 0,
        "risk_level": "low",
    }
    base.update(extra)
    return base


def test_summary_has_top_reasons_from_review_items():
    items = [
        {"risk_type": "missing_citation"},
        {"risk_type": "missing_citation"},
        {"risk_type": "proxy_flag"},
    ]
    s = production_summary.build(_qg(), _eh(), items)
    top = {r["risk_type"]: r["count"] for r in s["review"]["top_reasons"]}
    assert top["missing_citation"] == 2
    assert top["proxy_flag"] == 1


def test_next_action_mapping():
    assert production_summary.build(_qg("deliver"), _eh(), [])["recommended_next_action"] == "deliver"
    assert production_summary.build(_qg("deliver_with_warnings"), _eh(), [])["recommended_next_action"] == "deliver after spot check"
    assert production_summary.build(_qg("needs_review"), _eh(), [])["recommended_next_action"] == "review listed slides"
    assert production_summary.build(_qg("block", reasons=["x"]), _eh(), [])["recommended_next_action"] == "block and regenerate"


def test_html_is_self_contained_and_anonymous():
    import re
    html = production_summary.render_html(production_summary.build(_qg(), _eh(), []))
    # No external assets / network calls
    assert "<script src=" not in html
    assert "https://" not in html
    assert "http://" not in html
    # Pattern-based identity leak checks. These catch any future regression
    # without hardcoding specific identifiers in the test source itself.
    assert not re.search(r"[\w.\-]+@[\w.\-]+\.[a-z]{2,}", html), \
        "email-shaped string leaked into render"
    assert "mailto:" not in html, "mailto: link leaked into render"
    assert "github.com" not in html.lower(), "github URL leaked into render"


def test_write_production_summary_writes_both_files(tmp_path):
    jpath = tmp_path / "ps.json"
    hpath = tmp_path / "ps.html"
    production_summary.write_production_summary(
        jpath, hpath, _qg(), _eh(), [{"risk_type": "high_fallback"}],
    )
    data = json.loads(jpath.read_text())
    assert data["schema_version"] == "1.0"
    assert "production summary" in hpath.read_text().lower()


def test_summary_consumes_review_items_dict_or_list():
    items_as_dict = {"items": [{"risk_type": "missing_citation"}]}
    s1 = production_summary.build(_qg(), _eh(), items_as_dict)
    s2 = production_summary.build(_qg(), _eh(), items_as_dict["items"])
    assert s1["review"]["item_count"] == s2["review"]["item_count"] == 1
