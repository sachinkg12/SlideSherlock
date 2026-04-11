"""
SlideSherlock exception hierarchy.

All domain-specific exceptions inherit from SlidesherlockError so callers
can catch a single base type for broad handling, or specific subclasses
for targeted recovery.
"""

from __future__ import annotations

from typing import Optional


class SlidesherlockError(Exception):
    """Base exception for all SlideSherlock domain errors."""

    def __init__(self, message: str, **kwargs):
        self.details = kwargs
        super().__init__(message)


class StorageError(SlidesherlockError):
    """Failure reading from or writing to object storage (MinIO/S3)."""

    def __init__(self, message: str, path: str = "", operation: str = ""):
        super().__init__(message, path=path, operation=operation)
        self.path = path
        self.operation = operation


class IngestError(SlidesherlockError):
    """Failure during file ingestion: PPTX download, parse, or conversion."""

    def __init__(self, message: str, input_path: str = ""):
        super().__init__(message, input_path=input_path)
        self.input_path = input_path


class MediaProcessingError(SlidesherlockError):
    """Failure in a media subprocess (ffmpeg, ffprobe, LibreOffice)."""

    def __init__(
        self,
        message: str,
        subprocess_cmd: str = "",
        returncode: Optional[int] = None,
        stderr: str = "",
    ):
        super().__init__(
            message,
            subprocess_cmd=subprocess_cmd,
            returncode=returncode,
            stderr=stderr,
        )
        self.subprocess_cmd = subprocess_cmd
        self.returncode = returncode
        self.stderr = stderr


class LLMError(SlidesherlockError):
    """Failure calling an LLM provider after retries."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        model: str = "",
        provider: str = "",
    ):
        super().__init__(
            message, status_code=status_code, model=model, provider=provider
        )
        self.status_code = status_code
        self.model = model
        self.provider = provider


class VisionError(SlidesherlockError):
    """Failure in the vision pipeline (image understanding, OCR, classification)."""

    def __init__(self, message: str, reason_code: str = "UNKNOWN", image_uri: str = ""):
        super().__init__(message, reason_code=reason_code, image_uri=image_uri)
        self.reason_code = reason_code
        self.image_uri = image_uri


class ComposerError(SlidesherlockError):
    """Failure during video/audio composition."""

    def __init__(self, message: str, phase: str = ""):
        super().__init__(message, phase=phase)
        self.phase = phase


class PipelineConfigError(SlidesherlockError):
    """Invalid or missing pipeline configuration (job input, presets, env vars)."""

    pass
