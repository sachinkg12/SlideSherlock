"""
Vision extractor interface for image understanding (photo caption/objects, diagram entities).
NO-HALLUCINATION: extraction must be from actual image analysis; low confidence => safe language only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Evidence kinds produced by vision extractors
KIND_IMAGE_CAPTION = "IMAGE_CAPTION"
KIND_IMAGE_OBJECTS = "IMAGE_OBJECTS"
KIND_IMAGE_ACTIONS = "IMAGE_ACTIONS"
KIND_DIAGRAM_ENTITIES = "DIAGRAM_ENTITIES"
KIND_DIAGRAM_INTERACTIONS = "DIAGRAM_INTERACTIONS"
KIND_DIAGRAM_SUMMARY = "DIAGRAM_SUMMARY"

# Reason codes when uncertain
REASON_LOW_CONFIDENCE = "LOW_CONFIDENCE"
REASON_EXTRACTION_FAILED = "EXTRACTION_FAILED"
REASON_NO_VISION_PROVIDER = "NO_VISION_PROVIDER"
REASON_SAFE_FALLBACK = "SAFE_FALLBACK"

CONFIDENCE_THRESHOLD = 0.7


@dataclass
class ImageExtractionResult:
    """Result of vision extraction for one image/slide."""

    slide_index: int
    content: str  # Caption, objects list, entities, etc.
    kind: str  # One of KIND_*
    confidence: float  # 0.0 - 1.0
    reason_code: Optional[str] = None  # Set when confidence < threshold
    image_bbox: Optional[Dict[str, float]] = None
    image_uri: Optional[str] = None
    ppt_picture_shape_id: Optional[str] = None
    slide_png_uri: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class VisionExtractor(ABC):
    """Interface for extracting facts from images. No hallucination: low confidence => safe content only."""

    @abstractmethod
    def extract_photo(
        self,
        image_bytes: bytes,
        slide_index: int,
        image_bbox: Optional[Dict[str, float]] = None,
        slide_png_uri: Optional[str] = None,
        ppt_picture_shape_id: Optional[str] = None,
    ) -> List[ImageExtractionResult]:
        """
        Extract caption, objects, actions from a photo/image region.
        Returns list of results (caption, objects, actions). Confidence < threshold => safe language only.
        """

    @abstractmethod
    def extract_diagram(
        self,
        image_bytes: bytes,
        slide_index: int,
        vision_graph: Optional[Dict[str, Any]] = None,
        slide_png_uri: Optional[str] = None,
    ) -> List[ImageExtractionResult]:
        """
        Extract entities, interactions, summary from a diagram slide.
        vision_graph: optional OCR/vision graph (nodes, edges) for grounding.
        """


class StubVisionExtractor(VisionExtractor):
    """
    Stub: no real vision model. Returns low-confidence safe statements only.
    Enforces NO-HALLUCINATION: never invent objects, actions, or relationships.
    """

    def extract_photo(
        self,
        image_bytes: bytes,
        slide_index: int,
        image_bbox: Optional[Dict[str, float]] = None,
        slide_png_uri: Optional[str] = None,
        ppt_picture_shape_id: Optional[str] = None,
    ) -> List[ImageExtractionResult]:
        return [
            ImageExtractionResult(
                slide_index=slide_index,
                content="This slide contains an image.",
                kind=KIND_IMAGE_CAPTION,
                confidence=0.3,
                reason_code=REASON_SAFE_FALLBACK,
                image_bbox=image_bbox,
                image_uri=None,
                ppt_picture_shape_id=ppt_picture_shape_id,
                slide_png_uri=slide_png_uri,
            )
        ]

    def extract_diagram(
        self,
        image_bytes: bytes,
        slide_index: int,
        vision_graph: Optional[Dict[str, Any]] = None,
        slide_png_uri: Optional[str] = None,
    ) -> List[ImageExtractionResult]:
        content = "The diagram appears to show visual elements. (low confidence)"
        if vision_graph:
            nodes = vision_graph.get("nodes", [])
            labels = [
                n.get("label_text", "").strip()
                for n in nodes[:5]
                if n.get("label_text", "").strip()
            ]
            if labels:
                content = f"The diagram appears to show: {', '.join(labels[:3])}. (low confidence)"
        return [
            ImageExtractionResult(
                slide_index=slide_index,
                content=content,
                kind=KIND_DIAGRAM_SUMMARY,
                confidence=0.4,
                reason_code=REASON_SAFE_FALLBACK,
                slide_png_uri=slide_png_uri,
                metadata={"vision_nodes_used": min(5, len(vision_graph.get("nodes", [])))}
                if vision_graph
                else None,
            )
        ]


def get_vision_extractor() -> VisionExtractor:
    """Factory: returns configured vision extractor. Default: StubVisionExtractor.
    Set VISION_EXTRACTOR_PROVIDER=openai and OPENAI_API_KEY for real extraction; if key missing, stub is used.
    """
    import os

    provider = (os.environ.get("VISION_EXTRACTOR_PROVIDER", "stub")).strip().lower()
    if provider == "stub":
        return StubVisionExtractor()
    if provider == "openai":
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            import sys

            print(
                "VISION_EXTRACTOR_PROVIDER=openai but OPENAI_API_KEY not set; using stub (see .env.example).",
                file=sys.stderr,
            )
            return StubVisionExtractor()
        try:
            from vision_provider_openai import OpenAIVisionExtractor

            return OpenAIVisionExtractor()
        except (ImportError, AttributeError):
            pass
    return StubVisionExtractor()


# =============================================================================
# VisionProvider: PHOTO caption + objects/actions (Prompt 3)
# =============================================================================

KIND_IMAGE_TAGS = "IMAGE_TAGS"

REASON_VISION_UNAVAILABLE = "VISION_UNAVAILABLE"
REASON_LOW_CONFIDENCE = "LOW_CONFIDENCE"


class VisionProvider(ABC):
    """
    Interface for PHOTO understanding: caption, objects, actions, tags.
    Works with image_uri (MinIO path). NO-HALLUCINATION: low confidence => safe fallback.
    """

    @abstractmethod
    def caption(
        self, image_uri: str, lang: str = "en-US", minio_client: Any = None
    ) -> Dict[str, Any]:
        """
        Generate image caption. Returns {caption, confidence, reason_code?}.
        """

    @abstractmethod
    def extract(
        self,
        image_uri: str,
        lang: str = "en-US",
        minio_client: Any = None,
        mode: str = "photo",
    ) -> Dict[str, Any]:
        """
        Extract structured content. mode in {"photo","diagram","slide"}.
        Returns:
        photo: {objects: [{label, conf}], actions: [{verb_phrase, conf}], scene_tags: [{tag, conf}], global_confidence}
        diagram: {diagram_type, entities, interactions, summary, global_confidence}
        slide: same as photo (treated as photo for compatibility)
        """


class StubVisionProvider(VisionProvider):
    """
    Stub: no external vision calls. Always returns low-confidence generic content.
    NO-HALLUCINATION fallback: "Image present (low confidence), details unavailable"
    """

    def caption(
        self, image_uri: str, lang: str = "en-US", minio_client: Any = None
    ) -> Dict[str, Any]:
        return {
            "caption": "Image present (low confidence), details unavailable",
            "confidence": 0.1,
            "reason_code": REASON_VISION_UNAVAILABLE,
        }

    def extract(
        self,
        image_uri: str,
        lang: str = "en-US",
        minio_client: Any = None,
        mode: str = "photo",
    ) -> Dict[str, Any]:
        return {
            "objects": [],
            "actions": [],
            "scene_tags": [],
            "global_confidence": 0.1,
            "reason_code": REASON_VISION_UNAVAILABLE,
        }


def get_vision_provider() -> VisionProvider:
    """Factory: returns VisionProvider for PHOTO understanding. Default: StubVisionProvider.
    Set VISION_PROVIDER=openai and OPENAI_API_KEY for real vision; if key is missing, stub is used.
    """
    import os

    provider = (os.environ.get("VISION_PROVIDER", "stub")).strip().lower()
    if provider == "stub":
        return StubVisionProvider()
    if provider == "openai":
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            import sys

            print(
                "VISION_PROVIDER=openai but OPENAI_API_KEY not set; using stub vision (see .env.example).",
                file=sys.stderr,
            )
            return StubVisionProvider()
        try:
            from vision_provider_openai import OpenAIVisionProvider

            return OpenAIVisionProvider()
        except (ImportError, AttributeError):
            pass
    return StubVisionProvider()
