"""
Unit tests for evidence_index.py — _emu_to_float, _stable_evidence_id, _content_hash,
_flatten_shapes_and_connectors, and build_evidence_index.
"""
from __future__ import annotations

import hashlib
import os
import sys
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evidence_index import (
    _emu_to_float,
    _stable_evidence_id,
    _content_hash,
    _flatten_shapes_and_connectors,
)


# ---------------------------------------------------------------------------
# _emu_to_float
# ---------------------------------------------------------------------------


def test_emu_to_float_none():
    assert _emu_to_float(None) == 0.0


def test_emu_to_float_int():
    assert _emu_to_float(914400) == 914400.0


def test_emu_to_float_float():
    assert _emu_to_float(3.14) == pytest.approx(3.14)


def test_emu_to_float_emu_object():
    emu_obj = MagicMock()
    emu_obj.emu = 457200
    assert _emu_to_float(emu_obj) == 457200.0


def test_emu_to_float_string_returns_zero():
    # Non-numeric string without .emu attribute returns 0.0
    assert _emu_to_float("not_a_number") == 0.0


# ---------------------------------------------------------------------------
# _stable_evidence_id
# ---------------------------------------------------------------------------


def test_stable_evidence_id_deterministic():
    id1 = _stable_evidence_id("job-1", 0, "TEXT_SPAN", "notes")
    id2 = _stable_evidence_id("job-1", 0, "TEXT_SPAN", "notes")
    assert id1 == id2


def test_stable_evidence_id_different_inputs_different_ids():
    id1 = _stable_evidence_id("job-1", 0, "TEXT_SPAN", "notes")
    id2 = _stable_evidence_id("job-1", 0, "TEXT_SPAN", "slide_text")
    assert id1 != id2


def test_stable_evidence_id_different_slides_different_ids():
    id1 = _stable_evidence_id("job-1", 0, "TEXT_SPAN", "notes")
    id2 = _stable_evidence_id("job-1", 1, "TEXT_SPAN", "notes")
    assert id1 != id2


def test_stable_evidence_id_is_sha256_hex():
    eid = _stable_evidence_id("job-x", 2, "SHAPE_LABEL", "shape-42")
    # sha256 hex is 64 chars
    assert len(eid) == 64
    assert all(c in "0123456789abcdef" for c in eid)


# ---------------------------------------------------------------------------
# _content_hash
# ---------------------------------------------------------------------------


def test_content_hash_deterministic():
    h1 = _content_hash("hello world")
    h2 = _content_hash("hello world")
    assert h1 == h2


def test_content_hash_different_content_different_hash():
    assert _content_hash("foo") != _content_hash("bar")


def test_content_hash_matches_sha256():
    text = "some content"
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert _content_hash(text) == expected


# ---------------------------------------------------------------------------
# _flatten_shapes_and_connectors
# ---------------------------------------------------------------------------


def test_flatten_shapes_empty_payload():
    shapes, connectors = _flatten_shapes_and_connectors({})
    assert shapes == []
    assert connectors == []


def test_flatten_shapes_plain_shapes():
    payload = {
        "shapes": [
            {"ppt_shape_id": "s1", "text_runs": [{"text": "Hello"}]},
            {"ppt_shape_id": "s2", "text_runs": []},
        ]
    }
    shapes, connectors = _flatten_shapes_and_connectors(payload)
    assert len(shapes) == 2
    assert connectors == []


def test_flatten_shapes_connectors_separated():
    payload = {
        "connectors": [
            {"ppt_connector_id": "conn-1", "label": "flows to"},
        ],
        "shapes": [
            {"ppt_shape_id": "s1"},
        ],
    }
    shapes, connectors = _flatten_shapes_and_connectors(payload)
    assert len(shapes) == 1
    assert len(connectors) == 1
    assert connectors[0]["ppt_connector_id"] == "conn-1"


def test_flatten_shapes_group_children_expanded():
    payload = {
        "shapes": [
            {
                "type": "GROUP",
                "children": [
                    {"ppt_shape_id": "child-1"},
                    {"ppt_shape_id": "child-2"},
                ],
            }
        ]
    }
    shapes, connectors = _flatten_shapes_and_connectors(payload)
    assert len(shapes) == 2


def test_flatten_shapes_groups_key_expanded():
    payload = {
        "groups": [
            {
                "children": [
                    {"ppt_shape_id": "g-child-1"},
                ]
            }
        ]
    }
    shapes, connectors = _flatten_shapes_and_connectors(payload)
    assert len(shapes) == 1


def test_flatten_shapes_nested_connector_in_group():
    payload = {
        "shapes": [
            {
                "type": "GROUP",
                "children": [
                    {"ppt_connector_id": "inner-conn"},
                    {"ppt_shape_id": "inner-shape"},
                ],
            }
        ]
    }
    shapes, connectors = _flatten_shapes_and_connectors(payload)
    assert len(shapes) == 1
    assert len(connectors) == 1


# ---------------------------------------------------------------------------
# build_evidence_index (DB/minio fully mocked)
# ---------------------------------------------------------------------------


def _make_mock_db_and_models():
    """Return a mock db_session and patched models."""
    db = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()

    slide_cls = MagicMock(side_effect=lambda **kw: MagicMock(**kw))
    source_cls = MagicMock(side_effect=lambda **kw: MagicMock(**kw))
    ev_cls = MagicMock(side_effect=lambda **kw: MagicMock(**kw))
    ref_cls = MagicMock(side_effect=lambda **kw: MagicMock(**kw))
    artifact_cls = MagicMock(side_effect=lambda **kw: MagicMock(**kw))

    return db, slide_cls, source_cls, ev_cls, ref_cls, artifact_cls


def _run_build_index(job_id, slides_data, db=None, minio=None, models=None):
    """
    build_evidence_index imports from apps.api.models inside the function body.
    Patch sys.modules before calling so the local import resolves to our mocks.
    """
    from evidence_index import build_evidence_index

    db = db or MagicMock(flush=MagicMock(), add=MagicMock(), commit=MagicMock())
    minio = minio or MagicMock()

    if models is None:
        _, Slide, Source, EvidenceItem, SourceRef, Artifact = _make_mock_db_and_models()
        models = MagicMock(Slide=Slide, Source=Source, EvidenceItem=EvidenceItem, SourceRef=SourceRef, Artifact=Artifact)

    with patch.dict("sys.modules", {"apps.api.models": models}):
        return build_evidence_index(job_id, "proj-1", slides_data, db, minio), db, minio


def test_build_evidence_index_returns_schema_version():
    result, _, _ = _run_build_index(
        "job-1",
        [{"slide_index": 0, "notes": "hello", "slide_text": "world", "shapes": [], "connectors": [], "groups": []}],
    )
    assert result["schema_version"] == "1.0"
    assert result["job_id"] == "job-1"


def test_build_evidence_index_notes_creates_evidence_item():
    result, _, _ = _run_build_index(
        "job-2",
        [{"slide_index": 0, "notes": "These are speaker notes.", "slide_text": "", "shapes": [], "connectors": [], "groups": []}],
    )
    notes_items = [e for e in result["evidence_items"] if e["kind"] == "TEXT_SPAN" and e["content"] == "These are speaker notes."]
    assert len(notes_items) == 1


def test_build_evidence_index_slide_text_creates_evidence_item():
    result, _, _ = _run_build_index(
        "job-3",
        [{"slide_index": 0, "notes": "", "slide_text": "Slide body text here.", "shapes": [], "connectors": [], "groups": []}],
    )
    text_items = [e for e in result["evidence_items"] if e["content"] == "Slide body text here."]
    assert len(text_items) == 1


def test_build_evidence_index_minio_put_called():
    _, _, minio = _run_build_index(
        "job-4",
        [{"slide_index": 0, "notes": "", "slide_text": "", "shapes": [], "connectors": [], "groups": []}],
    )
    minio.put.assert_called_once()
    put_path = minio.put.call_args.args[0]
    assert "evidence/index.json" in put_path


def test_build_evidence_index_shape_labels():
    slides_data = [
        {
            "slide_index": 0,
            "notes": "",
            "slide_text": "",
            "shapes": [
                {
                    "ppt_shape_id": "shape-1",
                    "text_runs": [{"text": "Architecture"}],
                    "bbox": {"left": 0, "top": 0, "width": 914400, "height": 685800},
                }
            ],
            "connectors": [],
            "groups": [],
        }
    ]
    result, _, _ = _run_build_index("job-5", slides_data)
    shape_items = [e for e in result["evidence_items"] if e["kind"] == "SHAPE_LABEL"]
    assert len(shape_items) == 1
    assert shape_items[0]["content"] == "Architecture"


def test_build_evidence_index_stable_ids_across_calls():
    """Same inputs => same evidence_ids on second call."""
    slides_data = [{"slide_index": 0, "notes": "stable notes", "slide_text": "", "shapes": [], "connectors": [], "groups": []}]

    _, Slide, Source, EvidenceItem, SourceRef, Artifact = _make_mock_db_and_models()
    models = MagicMock(Slide=Slide, Source=Source, EvidenceItem=EvidenceItem, SourceRef=SourceRef, Artifact=Artifact)

    db1 = MagicMock(flush=MagicMock(), add=MagicMock(), commit=MagicMock())
    db2 = MagicMock(flush=MagicMock(), add=MagicMock(), commit=MagicMock())

    r1, _, _ = _run_build_index("job-stable", slides_data, db=db1, models=models)
    r2, _, _ = _run_build_index("job-stable", slides_data, db=db2, models=models)

    ids1 = {e["evidence_id"] for e in r1["evidence_items"]}
    ids2 = {e["evidence_id"] for e in r2["evidence_items"]}
    assert ids1 == ids2
