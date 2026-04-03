"""Pipeline stages for SlideSherlock."""
from stages.ingest import IngestStage
from stages.evidence import EvidenceStage
from stages.render import RenderStage
from stages.graph import GraphStage
from stages.script import ScriptStage
from stages.verify import VerifyStage
from stages.translate import TranslateStage
from stages.audio import AudioStage
from stages.video import VideoStage

__all__ = [
    "IngestStage",
    "EvidenceStage",
    "RenderStage",
    "GraphStage",
    "ScriptStage",
    "VerifyStage",
    "TranslateStage",
    "AudioStage",
    "VideoStage",
]
