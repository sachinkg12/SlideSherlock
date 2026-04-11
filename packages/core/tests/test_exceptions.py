"""Tests for the SlideSherlock exception hierarchy."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from exceptions import (
    SlidesherlockError,
    StorageError,
    IngestError,
    MediaProcessingError,
    LLMError,
    VisionError,
    ComposerError,
    PipelineConfigError,
)


def test_base_exception_is_exception():
    assert issubclass(SlidesherlockError, Exception)


def test_all_subclasses_inherit_from_base():
    for cls in [
        StorageError,
        IngestError,
        MediaProcessingError,
        LLMError,
        VisionError,
        ComposerError,
        PipelineConfigError,
    ]:
        assert issubclass(cls, SlidesherlockError), f"{cls.__name__} must inherit SlidesherlockError"


def test_storage_error_fields():
    err = StorageError("upload failed", path="/data/file.bin", operation="put")
    assert err.path == "/data/file.bin"
    assert err.operation == "put"
    assert "upload failed" in str(err)


def test_ingest_error_fields():
    err = IngestError("bad pptx", input_path="/tmp/test.pptx")
    assert err.input_path == "/tmp/test.pptx"


def test_media_processing_error_fields():
    err = MediaProcessingError(
        "ffmpeg crashed", subprocess_cmd="ffmpeg -i ...", returncode=1, stderr="error"
    )
    assert err.returncode == 1
    assert err.subprocess_cmd == "ffmpeg -i ..."
    assert err.stderr == "error"


def test_llm_error_fields():
    err = LLMError("rate limited", status_code=429, model="gpt-4", provider="openai")
    assert err.status_code == 429
    assert err.model == "gpt-4"
    assert err.provider == "openai"


def test_vision_error_fields():
    err = VisionError("empty image", reason_code="EMPTY_IMAGE", image_uri="s3://bucket/img.png")
    assert err.reason_code == "EMPTY_IMAGE"
    assert err.image_uri == "s3://bucket/img.png"


def test_composer_error_fields():
    err = ComposerError("crossfade failed", phase="crossfade")
    assert err.phase == "crossfade"


def test_pipeline_config_error():
    err = PipelineConfigError("missing input path")
    assert isinstance(err, SlidesherlockError)
    assert "missing input path" in str(err)


def test_catch_base_catches_subclass():
    try:
        raise StorageError("test", path="/x", operation="get")
    except SlidesherlockError as e:
        assert isinstance(e, StorageError)


def test_llm_backend_error_inherits_llm_error():
    from llm_backend import LLMBackendError

    assert issubclass(LLMBackendError, LLMError)
    assert issubclass(LLMBackendError, SlidesherlockError)
