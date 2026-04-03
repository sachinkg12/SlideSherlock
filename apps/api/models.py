from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    Integer,
    Float,
)
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum

from .database import Base


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


class Project(Base):
    __tablename__ = "projects"

    project_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    jobs = relationship("Job", back_populates="project")
    artifacts = relationship("Artifact", back_populates="project")


class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.project_id"), nullable=False)
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING, nullable=False)
    input_file_path = Column(String, nullable=True)
    requested_language = Column(String, nullable=True)  # BCP-47 e.g. hi-IN for second variant
    config_json = Column(Text, nullable=True)  # JSON: vision.enabled, force_kind_by_slide, etc.
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    project = relationship("Project", back_populates="jobs")
    artifacts = relationship("Artifact", back_populates="job")
    slides = relationship("Slide", back_populates="job")
    sources = relationship("Source", back_populates="job")
    evidence_items = relationship("EvidenceItem", back_populates="job")


class Artifact(Base):
    __tablename__ = "artifacts"

    artifact_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.project_id"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.job_id"), nullable=True)
    artifact_type = Column(
        String, nullable=False
    )  # e.g., "script", "video", "evidence", "pptx"
    storage_path = Column(String, nullable=False)
    sha256 = Column(String, nullable=True)  # SHA256 hash of file content
    size_bytes = Column(String, nullable=True)  # File size in bytes
    metadata_json = Column(
        Text, nullable=True
    )  # JSON string (renamed from 'metadata' - reserved in SQLAlchemy)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="artifacts")
    job = relationship("Job", back_populates="artifacts")


class Slide(Base):
    __tablename__ = "slides"

    slide_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.job_id"), nullable=False)
    slide_index = Column(Integer, nullable=False)
    slide_title = Column(Text, nullable=True)
    png_artifact_id = Column(String, ForeignKey("artifacts.artifact_id"), nullable=True)
    pptx_ref = Column(String, nullable=True)

    job = relationship("Job", back_populates="slides")
    sources = relationship("Source", back_populates="slide")
    evidence_items = relationship("EvidenceItem", back_populates="slide")


class Source(Base):
    __tablename__ = "sources"

    source_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.job_id"), nullable=False)
    type = Column(String, nullable=False)
    artifact_id = Column(String, ForeignKey("artifacts.artifact_id"), nullable=True)
    slide_id = Column(String, ForeignKey("slides.slide_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    job = relationship("Job", back_populates="sources")
    artifact = relationship("Artifact")
    slide = relationship("Slide", back_populates="sources")
    evidence_items = relationship("EvidenceItem", back_populates="source")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    evidence_id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("jobs.job_id"), nullable=False)
    slide_id = Column(String, ForeignKey("slides.slide_id"), nullable=True)
    source_id = Column(String, ForeignKey("sources.source_id"), nullable=False)
    kind = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    language = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    job = relationship("Job", back_populates="evidence_items")
    slide = relationship("Slide", back_populates="evidence_items")
    source = relationship("Source", back_populates="evidence_items")
    source_refs = relationship("SourceRef", back_populates="evidence_item")
    claim_links = relationship("ClaimLink", back_populates="evidence_item")
    entity_links = relationship("EntityLink", back_populates="evidence_item")


class SourceRef(Base):
    __tablename__ = "source_refs"

    ref_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    evidence_id = Column(String, ForeignKey("evidence_items.evidence_id"), nullable=False)
    ref_type = Column(String, nullable=False)
    slide_index = Column(Integer, nullable=True)
    ppt_shape_id = Column(String, nullable=True)
    ppt_paragraph_ix = Column(Integer, nullable=True)
    ppt_run_ix = Column(Integer, nullable=True)
    bbox_x = Column(Float, nullable=True)
    bbox_y = Column(Float, nullable=True)
    bbox_w = Column(Float, nullable=True)
    bbox_h = Column(Float, nullable=True)
    page_num = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    url = Column(Text, nullable=True)

    evidence_item = relationship("EvidenceItem", back_populates="source_refs")


class ClaimLink(Base):
    __tablename__ = "claim_links"

    claim_link_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id = Column(String, nullable=False)
    evidence_id = Column(String, ForeignKey("evidence_items.evidence_id"), nullable=False)
    weight = Column(Float, nullable=True)

    evidence_item = relationship("EvidenceItem", back_populates="claim_links")


class EntityLink(Base):
    __tablename__ = "entity_links"

    entity_link_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String, nullable=False)
    evidence_id = Column(String, ForeignKey("evidence_items.evidence_id"), nullable=False)
    role = Column(String, nullable=True)

    evidence_item = relationship("EvidenceItem", back_populates="entity_links")
