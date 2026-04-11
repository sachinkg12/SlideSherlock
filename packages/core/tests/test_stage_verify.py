"""Unit tests for stages/verify.py (VerifyStage)."""
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
        job_id="job-verify-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config={},
        temp_dir="/tmp",
    )
    ctx.variant = {"id": "en", "lang": "en-US"}
    ctx.script_prefix = "jobs/job-verify-test/script/en/"
    ctx.slide_count = 2
    ctx.evidence_index = {"evidence_items": [], "sources": []}
    ctx.unified_by_slide = {1: {"nodes": [], "edges": []}, 2: {"nodes": [], "edges": []}}
    ctx.verified_script = {
        "segments": [
            {"slide_index": 1, "text": "Intro.", "claim_id": "c1", "evidence_ids": ["e1"], "entity_ids": []},
        ]
    }
    return ctx


def test_verify_stage_name():
    from stages.verify import VerifyStage
    assert VerifyStage.name == "verify"


def test_verify_skips_when_no_verified_script():
    """Returns skipped when ctx.verified_script is None."""
    from stages.verify import VerifyStage

    ctx = _make_ctx()
    ctx.verified_script = None

    with patch.dict("sys.modules", {"apps.api.models": MagicMock(), "models": MagicMock()}):
        stage = VerifyStage()
        result = stage.run(ctx)

    assert result.status == "skipped"
    assert "no script to verify" in str(result.metrics.get("reason", ""))


def test_verify_returns_ok_when_deps_available():
    """Returns ok when verifier functions are available and succeed."""
    from stages.verify import VerifyStage

    ctx = _make_ctx()
    ctx.minio_client.get.side_effect = lambda key: (
        json.dumps({"plan": "explain"}).encode() if "explain_plan" in key else
        b""
    )
    ctx.minio_client.put.return_value = None

    verified_script = ctx.verified_script
    verify_report = [{"claim_id": "c1", "verdict": "PASS", "reasons": []}]
    coverage = {"pct_claims_with_evidence": 1.0, "total_claims": 1}

    mock_artifact_cls = MagicMock()
    mock_models = MagicMock(Artifact=mock_artifact_cls)

    with patch("stages.verify.run_rewrite_loop", return_value=(verified_script, verify_report, coverage)), \
         patch("stages.verify.build_verify_report_payload", return_value={"report": verify_report}), \
         patch("stages.verify.build_coverage_payload", return_value={"coverage": coverage}), \
         patch("stages.verify.write_slide_vision_debug_bundle", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = VerifyStage()
        result = stage.run(ctx)

    assert result.status == "ok"


def test_verify_sets_ctx_coverage_and_report():
    """ctx.coverage and ctx.verify_report are set after run."""
    from stages.verify import VerifyStage

    ctx = _make_ctx()
    ctx.minio_client.get.return_value = json.dumps({}).encode()
    ctx.minio_client.put.return_value = None

    verify_report = [{"claim_id": "c1", "verdict": "PASS", "reasons": []}]
    coverage = {"pct_claims_with_evidence": 0.9, "total_claims": 1}

    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.verify.run_rewrite_loop", return_value=(ctx.verified_script, verify_report, coverage)), \
         patch("stages.verify.build_verify_report_payload", return_value={}), \
         patch("stages.verify.build_coverage_payload", return_value={}), \
         patch("stages.verify.write_slide_vision_debug_bundle", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = VerifyStage()
        stage.run(ctx)

    assert ctx.coverage == coverage
    assert ctx.verify_report == verify_report


def test_verify_writes_artifacts_to_minio():
    """verify_report.json, coverage.json, and script.json are all uploaded."""
    from stages.verify import VerifyStage

    ctx = _make_ctx()
    ctx.minio_client.get.return_value = b"{}"
    ctx.minio_client.put.return_value = None

    verify_report = []
    coverage = {}

    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.verify.run_rewrite_loop", return_value=(ctx.verified_script, verify_report, coverage)), \
         patch("stages.verify.build_verify_report_payload", return_value={}), \
         patch("stages.verify.build_coverage_payload", return_value={}), \
         patch("stages.verify.write_slide_vision_debug_bundle", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = VerifyStage()
        result = stage.run(ctx)

    put_keys = [c.args[0] for c in ctx.minio_client.put.call_args_list]
    assert any("verify_report.json" in k for k in put_keys)
    assert any("coverage.json" in k for k in put_keys)
    assert any("script.json" in k for k in put_keys)


def test_verify_sets_script_for_downstream():
    """ctx.script_for_downstream is set to the verified script."""
    from stages.verify import VerifyStage

    ctx = _make_ctx()
    ctx.minio_client.get.return_value = b"{}"
    ctx.minio_client.put.return_value = None

    new_script = {"segments": [{"slide_index": 1, "text": "Rewritten.", "claim_id": "c1"}]}
    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.verify.run_rewrite_loop", return_value=(new_script, [], {})), \
         patch("stages.verify.build_verify_report_payload", return_value={}), \
         patch("stages.verify.build_coverage_payload", return_value={}), \
         patch("stages.verify.write_slide_vision_debug_bundle", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = VerifyStage()
        stage.run(ctx)

    assert ctx.script_for_downstream == new_script
    assert ctx.verified_script == new_script


def test_verify_runs_without_verifier_deps():
    """If run_rewrite_loop is None, verified_script is preserved unchanged."""
    from stages.verify import VerifyStage

    ctx = _make_ctx()
    original_script = ctx.verified_script
    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.verify.run_rewrite_loop", None), \
         patch("stages.verify.build_verify_report_payload", None), \
         patch("stages.verify.build_coverage_payload", None), \
         patch("stages.verify.write_slide_vision_debug_bundle", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = VerifyStage()
        result = stage.run(ctx)

    assert result.status == "ok"
    assert ctx.verified_script == original_script


def test_verify_artifacts_written_list():
    """result.artifacts_written contains three paths."""
    from stages.verify import VerifyStage

    ctx = _make_ctx()
    ctx.minio_client.get.return_value = b"{}"
    ctx.minio_client.put.return_value = None

    mock_models = MagicMock(Artifact=MagicMock())

    with patch("stages.verify.run_rewrite_loop", return_value=(ctx.verified_script, [], {})), \
         patch("stages.verify.build_verify_report_payload", return_value={}), \
         patch("stages.verify.build_coverage_payload", return_value={}), \
         patch("stages.verify.write_slide_vision_debug_bundle", None), \
         patch.dict("sys.modules", {"apps.api.models": mock_models, "models": mock_models}):
        stage = VerifyStage()
        result = stage.run(ctx)

    assert len(result.artifacts_written) == 3
