from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from .models import JobStatus


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VisionConfigSchema(BaseModel):
    enabled: Optional[bool] = True
    force_kind_by_slide: Optional[dict] = None  # e.g. {"3": "DIAGRAM", "5": "PHOTO"}
    lang: Optional[str] = None  # e.g. en-US
    min_confidence_for_specific_claims: Optional[float] = None  # e.g. 0.65


class JobCreate(BaseModel):
    project_id: str
    requested_language: Optional[str] = None  # BCP-47 e.g. hi-IN for second output variant
    config: Optional[dict] = None  # vision.enabled, vision.force_kind_by_slide, etc.


class OutputVariantSchema(BaseModel):
    id: str
    lang: str
    voice_id: str
    notes_translate: bool


class VariantStatusSchema(BaseModel):
    variant_id: str
    status: str  # pending | ready | failed
    output_url: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    project_id: str
    status: JobStatus
    input_file_path: Optional[str]
    requested_language: Optional[str]
    error_message: Optional[str]
    output_variants: Optional[list] = None  # from manifest
    variant_statuses: Optional[list] = None  # per-variant status and URLs
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
