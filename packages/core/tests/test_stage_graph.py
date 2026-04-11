"""Unit tests for stages/graph.py (GraphStage)."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from pipeline import PipelineContext, StageResult


def _make_ctx():
    ctx = PipelineContext(
        job_id="job-graph-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config={},
        temp_dir="/tmp",
    )
    ctx.slide_count = 2
    ctx.slide_metadata = [
        {"width": 1280, "height": 720},
        {"width": 1280, "height": 720},
    ]
    ctx.slides_pil = [MagicMock(), MagicMock()]
    ctx.slides_data = [
        {"slide_index": 1, "slide_text": "Slide 1"},
        {"slide_index": 2, "slide_text": "Slide 2"},
    ]
    return ctx


def _native_graph(slide_index: int):
    return {"slide_index": slide_index, "nodes": [], "edges": [], "clusters": []}


def test_graph_stage_name():
    from stages.graph import GraphStage
    assert GraphStage.name == "graph"


def test_graph_skips_when_no_slides():
    """Returns skipped when slide_count is 0."""
    from stages.graph import GraphStage

    ctx = _make_ctx()
    ctx.slide_count = 0

    stage = GraphStage()
    result = stage.run(ctx)

    assert result.status == "skipped"
    assert "no slides" in str(result.metrics.get("reason", ""))


def test_graph_loads_and_merges_native_graphs():
    """merge_graphs is called for each slide that has a native graph."""
    from stages.graph import GraphStage

    ctx = _make_ctx()

    g_native_1 = _native_graph(1)
    g_native_2 = _native_graph(2)
    g_unified_1 = {"slide_index": 1, "nodes": [], "edges": []}
    g_unified_2 = {"slide_index": 2, "nodes": [], "edges": []}

    def minio_get(key):
        if "slide_001" in key and "native" in key:
            return json.dumps(g_native_1).encode()
        if "slide_002" in key and "native" in key:
            return json.dumps(g_native_2).encode()
        if "slide_001" in key and "unified" in key:
            return json.dumps(g_unified_1).encode()
        if "slide_002" in key and "unified" in key:
            return json.dumps(g_unified_2).encode()
        raise Exception(f"Unexpected key: {key}")

    ctx.minio_client.get.side_effect = minio_get
    ctx.minio_client.put.return_value = None

    mock_merge = MagicMock(return_value=({"slide_index": 1, "nodes": [], "edges": []}, {}))

    with patch("stages.graph.merge_graphs", mock_merge), \
         patch("stages.graph.build_vision_graph_slide", None), \
         patch("stages.graph.run_image_understand", None):
        stage = GraphStage()
        result = stage.run(ctx)

    assert mock_merge.call_count == 2
    assert result.status == "ok"
    assert result.metrics["unified_graph_count"] == 2


def test_graph_sets_unified_graphs_on_ctx():
    """ctx.unified_graphs and ctx.unified_by_slide are set after run."""
    from stages.graph import GraphStage

    ctx = _make_ctx()
    ctx.slide_count = 1
    ctx.slide_metadata = [{"width": 1280, "height": 720}]

    g_native = _native_graph(1)
    g_unified = {"slide_index": 1, "nodes": [], "edges": []}

    def minio_get(key):
        if "native" in key:
            return json.dumps(g_native).encode()
        if "unified" in key:
            return json.dumps(g_unified).encode()
        raise Exception(key)

    ctx.minio_client.get.side_effect = minio_get
    ctx.minio_client.put.return_value = None

    with patch("stages.graph.merge_graphs", return_value=(g_unified, {})), \
         patch("stages.graph.build_vision_graph_slide", None), \
         patch("stages.graph.run_image_understand", None):
        stage = GraphStage()
        result = stage.run(ctx)

    assert len(ctx.unified_graphs) == 1
    assert 1 in ctx.unified_by_slide


def test_graph_handles_missing_native_gracefully():
    """If native graph load fails for a slide, that slide is skipped."""
    from stages.graph import GraphStage

    ctx = _make_ctx()
    ctx.slide_count = 1
    ctx.slide_metadata = [{"width": 1280, "height": 720}]

    ctx.minio_client.get.side_effect = Exception("not found")

    with patch("stages.graph.merge_graphs", MagicMock()) as mock_merge, \
         patch("stages.graph.build_vision_graph_slide", None), \
         patch("stages.graph.run_image_understand", None):
        stage = GraphStage()
        result = stage.run(ctx)

    mock_merge.assert_not_called()
    assert result.status == "ok"
    assert len(ctx.unified_graphs) == 0


def test_graph_writes_flags_json():
    """flags.json is written after merge."""
    from stages.graph import GraphStage

    ctx = _make_ctx()
    ctx.slide_count = 1
    ctx.slide_metadata = [{"width": 1280, "height": 720}]

    g_native = _native_graph(1)
    g_unified = {"slide_index": 1, "nodes": [], "edges": []}

    def minio_get(key):
        if "native" in key:
            return json.dumps(g_native).encode()
        if "unified" in key:
            return json.dumps(g_unified).encode()
        raise Exception(key)

    ctx.minio_client.get.side_effect = minio_get
    ctx.minio_client.put.return_value = None

    with patch("stages.graph.merge_graphs", return_value=(g_unified, {"flag": "ok"})), \
         patch("stages.graph.build_vision_graph_slide", None), \
         patch("stages.graph.run_image_understand", None):
        stage = GraphStage()
        stage.run(ctx)

    put_keys = [c.args[0] for c in ctx.minio_client.put.call_args_list]
    assert any("flags.json" in k for k in put_keys)


def test_graph_skips_when_merge_graphs_unavailable():
    """If merge_graphs is None, unified_graphs stays empty but result is ok."""
    from stages.graph import GraphStage

    ctx = _make_ctx()

    with patch("stages.graph.merge_graphs", None), \
         patch("stages.graph.build_vision_graph_slide", None), \
         patch("stages.graph.run_image_understand", None):
        stage = GraphStage()
        result = stage.run(ctx)

    assert ctx.unified_graphs == []
    assert result.status == "ok"


def test_graph_vision_enabled_calls_vision_graph(monkeypatch):
    """With VISION_ENABLED=1, build_vision_graph_slide is attempted per slide."""
    from stages.graph import GraphStage

    monkeypatch.setenv("VISION_ENABLED", "1")

    ctx = _make_ctx()
    ctx.slide_count = 1
    ctx.slide_metadata = [{"width": 1280, "height": 720}]

    g_native = _native_graph(1)
    g_unified = {"slide_index": 1, "nodes": [], "edges": []}

    def minio_get(key):
        if "native" in key:
            return json.dumps(g_native).encode()
        if "unified" in key:
            return json.dumps(g_unified).encode()
        raise Exception(key)

    ctx.minio_client.get.side_effect = minio_get
    ctx.minio_client.put.return_value = None

    mock_vision = MagicMock(return_value={"nodes": [], "edges": [], "text_spans": []})

    with patch("stages.graph.merge_graphs", return_value=(g_unified, {})), \
         patch("stages.graph.build_vision_graph_slide", mock_vision), \
         patch("stages.graph.run_image_understand", None):
        stage = GraphStage()
        stage.run(ctx)

    mock_vision.assert_called_once()
