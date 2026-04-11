"""Unit tests for stages/translate.py (TranslateStage)."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from pipeline import PipelineContext, StageResult


def _make_ctx(variant_id="l2", lang="fr-FR", notes_translate=True):
    ctx = PipelineContext(
        job_id="job-translate-test",
        project_id="proj-1",
        minio_client=MagicMock(),
        db_session=MagicMock(),
        config={},
        temp_dir="/tmp",
    )
    ctx.variant = {"id": variant_id, "lang": lang, "notes_translate": notes_translate}
    ctx.script_prefix = f"jobs/job-translate-test/script/{variant_id}/"
    ctx.slide_count = 2
    ctx.evidence_index = {"evidence_items": [], "sources": []}
    ctx.unified_by_slide = {1: {}, 2: {}}
    ctx.verified_script = {
        "segments": [
            {"slide_index": 1, "text": "Intro.", "claim_id": "c1"},
            {"slide_index": 2, "text": "Detail.", "claim_id": "c2"},
        ]
    }
    ctx.narration_entries_override = None
    ctx.per_slide_notes_for_overlay = None
    ctx.translation_degraded = False
    return ctx


def test_translate_stage_name():
    from stages.translate import TranslateStage
    assert TranslateStage.name == "translate"


def test_translate_skips_for_en_variant():
    """Returns skipped when variant_id is 'en'."""
    from stages.translate import TranslateStage

    ctx = _make_ctx(variant_id="en", lang="en-US")

    stage = TranslateStage()
    result = stage.run(ctx)

    assert result.status == "skipped"
    assert "not l2 or english" in str(result.metrics.get("reason", ""))


def test_translate_skips_for_english_target_lang():
    """l2 variant with en-US target also skips when notes_translate is False."""
    from stages.translate import TranslateStage

    ctx = _make_ctx(variant_id="l2", lang="en-US", notes_translate=False)

    stage = TranslateStage()
    result = stage.run(ctx)

    assert result.status == "skipped"


def test_translate_skips_when_deps_missing():
    """Returns skipped and sets ctx.translation_degraded when deps are None."""
    from stages.translate import TranslateStage

    ctx = _make_ctx()

    with patch("stages.translate.get_translator_provider", None), \
         patch("stages.translate.translate_script_segments", None), \
         patch("stages.translate.translate_notes_per_slide", None), \
         patch("stages.translate.verify_translated_script", None), \
         patch("stages.translate.derive_narration_from_script", None), \
         patch("stages.translate.build_translation_report", None):
        stage = TranslateStage()
        result = stage.run(ctx)

    assert result.status == "skipped"
    assert ctx.translation_degraded is True
    assert "translation deps missing" in str(result.metrics.get("reason", ""))


def test_translate_happy_path_sets_script_for_downstream():
    """Successful translation sets ctx.script_for_downstream to translated script."""
    from stages.translate import TranslateStage

    ctx = _make_ctx()
    ctx.minio_client.get.return_value = json.dumps({"notes": "Speaker note", "slide_text": "Text"}).encode()
    ctx.minio_client.put.return_value = None

    translated_script = {"segments": [{"slide_index": 1, "text": "Intro traduit."}]}
    narration_derived = [{"slide_index": 1, "narration_text": "Intro traduit."}]

    mock_provider = MagicMock()

    with patch("stages.translate.get_translator_provider", return_value=mock_provider), \
         patch("stages.translate.translate_script_segments", return_value=(translated_script, {}, True)), \
         patch("stages.translate.verify_translated_script", return_value=(True, {})), \
         patch("stages.translate.translate_notes_per_slide", return_value=(["note fr", "note fr 2"], {})), \
         patch("stages.translate.derive_narration_from_script", return_value=narration_derived), \
         patch("stages.translate.build_translation_report", return_value={"report": "ok"}):
        stage = TranslateStage()
        result = stage.run(ctx)

    assert result.status == "ok"
    assert ctx.script_for_downstream == translated_script
    assert ctx.narration_entries_override == narration_derived


def test_translate_degraded_on_script_failure():
    """Sets ctx.translation_degraded when script translation fails verify."""
    from stages.translate import TranslateStage

    ctx = _make_ctx()
    ctx.minio_client.get.return_value = json.dumps({"notes": "", "slide_text": ""}).encode()
    ctx.minio_client.put.return_value = None

    mock_provider = MagicMock()
    bad_script = {"segments": [{"slide_index": 1, "text": "Bad translation."}]}

    with patch("stages.translate.get_translator_provider", return_value=mock_provider), \
         patch("stages.translate.translate_script_segments", return_value=(bad_script, {}, True)), \
         patch("stages.translate.verify_translated_script", return_value=(False, {"errors": ["mismatch"]})), \
         patch("stages.translate.translate_notes_per_slide", return_value=([], {})), \
         patch("stages.translate.derive_narration_from_script", return_value=[]), \
         patch("stages.translate.build_translation_report", return_value={}):
        stage = TranslateStage()
        stage.run(ctx)

    assert ctx.translation_degraded is True


def test_translate_writes_translation_report():
    """translation_report.json is uploaded to minio."""
    from stages.translate import TranslateStage

    ctx = _make_ctx()
    ctx.minio_client.get.return_value = json.dumps({"notes": "", "slide_text": ""}).encode()
    ctx.minio_client.put.return_value = None

    translated_script = {"segments": []}
    mock_provider = MagicMock()

    with patch("stages.translate.get_translator_provider", return_value=mock_provider), \
         patch("stages.translate.translate_script_segments", return_value=(translated_script, {}, True)), \
         patch("stages.translate.verify_translated_script", return_value=(True, {})), \
         patch("stages.translate.translate_notes_per_slide", return_value=(["fr note"], {})), \
         patch("stages.translate.derive_narration_from_script", return_value=[]), \
         patch("stages.translate.build_translation_report", return_value={"report": "done"}):
        stage = TranslateStage()
        stage.run(ctx)

    put_keys = [c.args[0] for c in ctx.minio_client.put.call_args_list]
    assert any("translation_report.json" in k for k in put_keys)


def test_translate_notes_uploaded_when_notes_translate_enabled():
    """notes_clean.json and notes_translated.json are uploaded when notes_translate=True."""
    from stages.translate import TranslateStage

    ctx = _make_ctx(notes_translate=True)
    ctx.minio_client.get.return_value = json.dumps({"notes": "Note", "slide_text": "Text"}).encode()
    ctx.minio_client.put.return_value = None

    translated_script = {"segments": []}
    mock_provider = MagicMock()

    with patch("stages.translate.get_translator_provider", return_value=mock_provider), \
         patch("stages.translate.translate_script_segments", return_value=(translated_script, {}, True)), \
         patch("stages.translate.verify_translated_script", return_value=(True, {})), \
         patch("stages.translate.translate_notes_per_slide", return_value=(["note en français", "note 2"], {})), \
         patch("stages.translate.derive_narration_from_script", return_value=[]), \
         patch("stages.translate.build_translation_report", return_value={}):
        stage = TranslateStage()
        stage.run(ctx)

    put_keys = [c.args[0] for c in ctx.minio_client.put.call_args_list]
    assert any("notes_clean.json" in k for k in put_keys)
    assert any("notes_translated.json" in k for k in put_keys)
