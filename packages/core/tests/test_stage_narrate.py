"""Unit tests for stages/narrate.py (NarrateStage)."""
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
        job_id="job-narrate-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config={"ai_narration": True},
        temp_dir="/tmp",
    )
    ctx.variant = {"id": "en", "lang": "en-US"}
    ctx.script_prefix = "jobs/job-narrate-test/script/en/"
    ctx.slide_count = 2
    ctx.verified_script = {
        "segments": [
            {"slide_index": 1, "text": "Intro text.", "claim_id": "c1", "evidence_ids": [], "entity_ids": []},
            {"slide_index": 2, "text": "Main content.", "claim_id": "c2", "evidence_ids": [], "entity_ids": []},
        ]
    }
    ctx.evidence_index = {"evidence_items": [], "sources": []}
    ctx.unified_by_slide = {1: {"nodes": []}, 2: {"nodes": []}}
    ctx.slides_notes_and_text = [("Note 1", "Text 1"), ("Note 2", "Text 2")]
    ctx.narration_entries_override = None
    return ctx


def _mock_llm_config(base_url="https://api.openai.com/v1", model="gpt-4o", api_key="test-key"):
    return MagicMock(return_value=(base_url, model, api_key))


def test_narrate_stage_name():
    from stages.narrate import NarrateStage
    assert NarrateStage.name == "narrate"


def test_narrate_skips_when_ai_narration_false():
    """Returns skipped when ctx.config['ai_narration'] is False."""
    from stages.narrate import NarrateStage

    ctx = _make_ctx()
    ctx.config["ai_narration"] = False

    mock_llm_config_mod = MagicMock()
    mock_llm_config_mod.get_narrate_config = MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "key"))

    with patch.dict("sys.modules", {"llm_config": mock_llm_config_mod}):
        stage = NarrateStage()
        result = stage.run(ctx)

    assert result.status == "skipped"
    assert "AI narration not enabled" in str(result.metrics.get("reason", ""))


def test_narrate_skips_when_no_verified_script():
    """Returns skipped when verified_script is None."""
    from stages.narrate import NarrateStage

    ctx = _make_ctx()
    ctx.verified_script = None

    mock_llm_config_mod = MagicMock()
    mock_llm_config_mod.get_narrate_config = MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "key"))

    with patch.dict("sys.modules", {"llm_config": mock_llm_config_mod}):
        stage = NarrateStage()
        result = stage.run(ctx)

    assert result.status == "skipped"
    assert "no verified script" in str(result.metrics.get("reason", ""))


def test_narrate_skips_when_no_api_key_for_remote():
    """Returns skipped when a remote provider URL is used but no api_key."""
    from stages.narrate import NarrateStage

    ctx = _make_ctx()

    mock_llm_config_mod = MagicMock()
    mock_llm_config_mod.get_narrate_config = MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", ""))

    with patch.dict("sys.modules", {"llm_config": mock_llm_config_mod}):
        stage = NarrateStage()
        result = stage.run(ctx)

    assert result.status == "skipped"
    assert "no API key" in str(result.metrics.get("reason", ""))


def test_narrate_runs_and_sets_override():
    """Happy path: LLM rewrites each slide and ctx.narration_entries_override is set."""
    from stages.narrate import NarrateStage

    ctx = _make_ctx()

    mock_llm_config_mod = MagicMock()
    mock_llm_config_mod.get_narrate_config = MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "sk-test"))

    mock_llm_backend_mod = MagicMock()
    mock_llm_backend_mod.call_chat = MagicMock(return_value="Rewritten narration for slide.")
    mock_llm_backend_mod.LLMBackendError = Exception

    ctx.minio_client.put.return_value = None

    with patch.dict("sys.modules", {"llm_config": mock_llm_config_mod, "llm_backend": mock_llm_backend_mod}):
        stage = NarrateStage()
        result = stage.run(ctx)

    assert result.status == "ok"
    assert ctx.narration_entries_override is not None
    assert len(ctx.narration_entries_override) == ctx.slide_count


def test_narrate_fallback_on_llm_failure():
    """If LLM call fails for a slide, template narration is used as fallback."""
    from stages.narrate import NarrateStage

    ctx = _make_ctx()

    mock_llm_config_mod = MagicMock()
    mock_llm_config_mod.get_narrate_config = MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "sk-test"))

    mock_llm_backend_mod = MagicMock()
    mock_llm_backend_mod.LLMBackendError = Exception
    # Raise on every call
    mock_llm_backend_mod.call_chat = MagicMock(side_effect=Exception("LLM error"))

    ctx.minio_client.put.return_value = None

    with patch.dict("sys.modules", {"llm_config": mock_llm_config_mod, "llm_backend": mock_llm_backend_mod}):
        stage = NarrateStage()
        result = stage.run(ctx)

    assert result.status == "ok"
    # All slides fell back
    sources = [e["source_used"] for e in ctx.narration_entries_override]
    assert all(s == "template_fallback" for s in sources)


def test_narrate_metrics_reflect_rewrite_count():
    """Metrics contain slides_rewritten and slides_total."""
    from stages.narrate import NarrateStage

    ctx = _make_ctx()

    mock_llm_config_mod = MagicMock()
    mock_llm_config_mod.get_narrate_config = MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "sk-test"))

    mock_llm_backend_mod = MagicMock()
    mock_llm_backend_mod.LLMBackendError = Exception
    mock_llm_backend_mod.call_chat = MagicMock(return_value="A well-formed narration sentence here.")

    ctx.minio_client.put.return_value = None

    with patch.dict("sys.modules", {"llm_config": mock_llm_config_mod, "llm_backend": mock_llm_backend_mod}):
        stage = NarrateStage()
        result = stage.run(ctx)

    assert "slides_rewritten" in result.metrics
    assert "slides_total" in result.metrics
    assert result.metrics["slides_total"] == 2


def test_narrate_saves_ai_narration_json():
    """ai_narration.json is written to minio after run."""
    from stages.narrate import NarrateStage

    ctx = _make_ctx()

    mock_llm_config_mod = MagicMock()
    mock_llm_config_mod.get_narrate_config = MagicMock(return_value=("https://api.openai.com/v1", "gpt-4o", "sk-test"))

    mock_llm_backend_mod = MagicMock()
    mock_llm_backend_mod.LLMBackendError = Exception
    mock_llm_backend_mod.call_chat = MagicMock(return_value="Narration for slide goes here.")

    ctx.minio_client.put.return_value = None

    with patch.dict("sys.modules", {"llm_config": mock_llm_config_mod, "llm_backend": mock_llm_backend_mod}):
        stage = NarrateStage()
        stage.run(ctx)

    put_keys = [c.args[0] for c in ctx.minio_client.put.call_args_list]
    assert any("ai_narration.json" in k for k in put_keys)


def test_narrate_local_provider_no_key_allowed():
    """Local providers (non-https://api.) should pass even without api_key."""
    from stages.narrate import NarrateStage

    ctx = _make_ctx()

    mock_llm_config_mod = MagicMock()
    # Local ollama endpoint, no key required
    mock_llm_config_mod.get_narrate_config = MagicMock(return_value=("http://localhost:11434/v1", "llama3", ""))

    mock_llm_backend_mod = MagicMock()
    mock_llm_backend_mod.LLMBackendError = Exception
    mock_llm_backend_mod.call_chat = MagicMock(return_value="Local LLM narration text here.")

    ctx.minio_client.put.return_value = None

    with patch.dict("sys.modules", {"llm_config": mock_llm_config_mod, "llm_backend": mock_llm_backend_mod}):
        stage = NarrateStage()
        result = stage.run(ctx)

    # Should not skip due to missing key
    assert result.status == "ok"
