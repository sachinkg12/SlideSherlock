"""Unit tests for stages/script.py (ScriptStage)."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch, call
import pytest

from pipeline import PipelineContext, StageResult


def _make_ctx(tmp_path=None):
    ctx = PipelineContext(
        job_id="job-script-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config={},
        temp_dir=str(tmp_path) if tmp_path else "/tmp",
    )
    ctx.llm_provider = MagicMock()
    ctx.unified_graphs = [{"slide_index": 1, "nodes": [], "edges": []}]
    ctx.unified_by_slide = {1: {"slide_index": 1, "nodes": [], "edges": []}}
    ctx.slide_count = 1
    ctx.variant = {"id": "en", "lang": "en-US", "voice_id": "default_en"}
    ctx.script_prefix = "jobs/job-script-test/script/en/"
    return ctx


def test_script_stage_name():
    from stages.script import ScriptStage
    assert ScriptStage.name == "script"


def test_script_skips_when_no_llm_provider():
    """Stage skips when llm_provider is None."""
    from stages.script import ScriptStage

    ctx = _make_ctx()
    ctx.llm_provider = None

    with patch("stages.script.build_explain_plan", MagicMock()), \
         patch("stages.script.generate_script", MagicMock()), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(), "models": MagicMock()}):
        stage = ScriptStage()
        result = stage.run(ctx)

    assert result.status == "skipped"
    assert "missing dependencies" in str(result.metrics.get("reason", ""))


def test_script_skips_when_no_unified_graphs():
    """Stage skips when unified_graphs is empty."""
    from stages.script import ScriptStage

    ctx = _make_ctx()
    ctx.unified_graphs = []

    with patch("stages.script.build_explain_plan", MagicMock()), \
         patch("stages.script.generate_script", MagicMock()), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(), "models": MagicMock()}):
        stage = ScriptStage()
        result = stage.run(ctx)

    assert result.status == "skipped"
    assert "no unified graphs" in str(result.metrics.get("reason", ""))


def test_script_skips_when_deps_missing():
    """Stage returns skipped if build_explain_plan or generate_script is None."""
    from stages.script import ScriptStage

    ctx = _make_ctx()

    with patch("stages.script.build_explain_plan", None), \
         patch("stages.script.generate_script", None), \
         patch.dict("sys.modules", {"apps.api.models": MagicMock(), "models": MagicMock()}):
        stage = ScriptStage()
        result = stage.run(ctx)

    assert result.status == "skipped"


def test_script_runs_and_writes_artifacts():
    """Happy path: script and explain_plan are written to minio."""
    from stages.script import ScriptStage

    ctx = _make_ctx()
    mock_evidence = {"evidence_items": [], "sources": []}
    ctx.minio_client.get.side_effect = lambda key: (
        json.dumps(mock_evidence).encode() if "evidence" in key else
        json.dumps({"notes": "", "slide_text": ""}).encode()
    )

    mock_plan = {"plan_id": "p1", "steps": []}
    mock_draft = {"segments": [{"slide_index": 1, "text": "Intro.", "claim_id": "c1", "evidence_ids": [], "entity_ids": []}]}

    mock_artifact_cls = MagicMock()
    mock_models = MagicMock(Artifact=mock_artifact_cls, EntityLink=MagicMock(), EvidenceItem=MagicMock())
    # db.query returns empty
    ctx.db_session.query.return_value.join.return_value.filter.return_value = []

    with patch("stages.script.build_explain_plan", return_value=mock_plan), \
         patch("stages.script.generate_script", return_value=mock_draft), \
         patch("stages.script.retrieve_chunk_ids", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = ScriptStage()
        result = stage.run(ctx)

    assert result.status == "ok"
    assert ctx.verified_script == mock_draft
    put_keys = [c.args[0] for c in ctx.minio_client.put.call_args_list]
    assert any("explain_plan.json" in k for k in put_keys)
    assert any("script.json" in k for k in put_keys)


def test_script_stores_script_for_downstream():
    """After run, ctx.script_for_downstream is set."""
    from stages.script import ScriptStage

    ctx = _make_ctx()
    ctx.minio_client.get.return_value = json.dumps({"evidence_items": [], "sources": []}).encode()
    ctx.db_session.query.return_value.join.return_value.filter.return_value = []

    mock_draft = {"segments": []}

    mock_artifact_cls = MagicMock()
    mock_models = MagicMock(Artifact=mock_artifact_cls, EntityLink=MagicMock(), EvidenceItem=MagicMock())

    with patch("stages.script.build_explain_plan", return_value={}), \
         patch("stages.script.generate_script", return_value=mock_draft), \
         patch("stages.script.retrieve_chunk_ids", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = ScriptStage()
        result = stage.run(ctx)

    assert ctx.script_for_downstream == mock_draft


def test_script_loads_evidence_index_fallback():
    """If evidence index can't be loaded, script still runs with empty index."""
    from stages.script import ScriptStage

    ctx = _make_ctx()
    # Make minio.get raise for evidence, succeed for slide data
    def side_effect(key):
        if "evidence" in key:
            raise Exception("not found")
        return json.dumps({"notes": "", "slide_text": ""}).encode()

    ctx.minio_client.get.side_effect = side_effect
    ctx.db_session.query.return_value.join.return_value.filter.return_value = []

    mock_draft = {"segments": []}
    mock_models = MagicMock(Artifact=MagicMock(), EntityLink=MagicMock(), EvidenceItem=MagicMock())

    with patch("stages.script.build_explain_plan", return_value={}), \
         patch("stages.script.generate_script", return_value=mock_draft), \
         patch("stages.script.retrieve_chunk_ids", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = ScriptStage()
        result = stage.run(ctx)

    assert result.status == "ok"
    assert ctx.evidence_index == {"evidence_items": [], "sources": []}


def test_script_artifacts_written_list():
    """result.artifacts_written contains both plan and script paths."""
    from stages.script import ScriptStage

    ctx = _make_ctx()
    ctx.minio_client.get.return_value = json.dumps({"evidence_items": [], "sources": []}).encode()
    ctx.db_session.query.return_value.join.return_value.filter.return_value = []

    mock_models = MagicMock(Artifact=MagicMock(), EntityLink=MagicMock(), EvidenceItem=MagicMock())

    with patch("stages.script.build_explain_plan", return_value={}), \
         patch("stages.script.generate_script", return_value={"segments": []}), \
         patch("stages.script.retrieve_chunk_ids", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = ScriptStage()
        result = stage.run(ctx)

    assert len(result.artifacts_written) == 2
    assert any("explain_plan.json" in p for p in result.artifacts_written)
    assert any("script.json" in p for p in result.artifacts_written)
