"""
Evidence health report.

Before grading the narration, look at the deck and ask whether it has enough
reliable evidence to ground anything. This module produces a deterministic
low / medium / high risk classification from evidence_index.json alone (and
graph.json + slide metrics if they happen to be available).

The point is operational, not academic: a deck dominated by photographs the
vision model could not caption clearly is a different kind of risk from a
deck dominated by text and shape labels.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Union

PathLike = Union[str, os.PathLike]
JsonDict = Dict[str, Any]

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

_TEXT_KINDS = {"TEXT_SPAN", "SHAPE_LABEL", "CONNECTOR"}
_IMAGE_KINDS = {
    "IMAGE_ASSET", "IMAGE_CAPTION", "IMAGE_OBJECTS", "IMAGE_ACTIONS",
    "IMAGE_TAGS", "SLIDE_CAPTION",
}
_DIAGRAM_KINDS = {
    "DIAGRAM_TYPE", "DIAGRAM_ENTITIES", "DIAGRAM_INTERACTIONS", "DIAGRAM_SUMMARY",
}
_LOW_CONF_VISION_THRESHOLD = 0.6
_CHART_LIKE_TOKENS = ("chart", "graph", "plot", "histogram")
_TABLE_LIKE_TOKENS = ("table", "row", "column", "spreadsheet")


def _load_json(path_or_obj):
    if path_or_obj is None:
        return None
    if isinstance(path_or_obj, (dict, list)):
        return path_or_obj
    with open(path_or_obj) as f:
        return json.load(f)


def _slide_index_of(item: JsonDict) -> Optional[int]:
    si = item.get("slide_index")
    if si is None:
        ref = item.get("source_ref") or {}
        si = ref.get("slide_index")
    try:
        return int(si) if si is not None else None
    except (TypeError, ValueError):
        return None


def evaluate(
    evidence_index: Union[PathLike, JsonDict],
    graph: Optional[Union[PathLike, JsonDict]] = None,
    slide_metrics: Optional[Union[PathLike, JsonDict]] = None,
    job_id: Optional[str] = None,
    deck_id: Optional[str] = None,
) -> JsonDict:
    ei = _load_json(evidence_index) or {}
    items = ei.get("evidence_items", []) if isinstance(ei, dict) else (ei or [])

    if not job_id and isinstance(ei, dict):
        job_id = ei.get("job_id")

    by_slide: Dict[int, List[JsonDict]] = defaultdict(list)
    by_kind = Counter()
    chart_like = 0
    table_like = 0
    for it in items:
        si = _slide_index_of(it)
        kind = it.get("kind", "")
        by_kind[kind] += 1
        if si is not None:
            by_slide[si].append(it)
        # Heuristic chart/table detection: keyword present in evidence content.
        content = (it.get("content") or "").lower()
        if any(tok in content for tok in _CHART_LIKE_TOKENS):
            chart_like += 1
        if any(tok in content for tok in _TABLE_LIKE_TOKENS):
            table_like += 1

    # If we have slide_metrics, we know slide count exactly; otherwise infer from observed.
    slides_total: int
    sm = _load_json(slide_metrics)
    if isinstance(sm, dict) and sm.get("slide_count"):
        slides_total = int(sm["slide_count"])
    else:
        slides_total = max(by_slide.keys()) if by_slide else 0

    slides_with_text = 0
    slides_with_images = 0
    slides_with_diagram = 0
    slides_with_low_confidence_vision = 0
    slides_with_no_evidence = 0
    slides_with_speaker_notes = 0  # not detectable from evidence_index alone

    if slides_total:
        observed = set(by_slide.keys())
        for si in range(1, slides_total + 1):
            sl_items = by_slide.get(si, [])
            if not sl_items:
                slides_with_no_evidence += 1
                continue
            kinds = {x.get("kind") for x in sl_items}
            if kinds & _TEXT_KINDS:
                slides_with_text += 1
            if kinds & _IMAGE_KINDS:
                slides_with_images += 1
            if kinds & _DIAGRAM_KINDS:
                slides_with_diagram += 1
            # Low-confidence vision: any IMAGE_* item on the slide with confidence < threshold
            for x in sl_items:
                if x.get("kind") in _IMAGE_KINDS:
                    conf = x.get("confidence")
                    if isinstance(conf, (int, float)) and 0 < conf < _LOW_CONF_VISION_THRESHOLD:
                        slides_with_low_confidence_vision += 1
                        break

    # Risk classification: deterministic, easy to reason about.
    risk_reasons: List[str] = []
    risk_level = RISK_LOW

    if slides_total == 0:
        risk_level = RISK_HIGH
        risk_reasons.append("no slide data available")
        return _result(
            job_id, deck_id, slides_total, len(items), by_kind,
            slides_with_text, slides_with_images, slides_with_diagram,
            slides_with_low_confidence_vision, slides_with_no_evidence,
            slides_with_speaker_notes, chart_like, table_like,
            risk_level, risk_reasons,
        )

    no_ev_frac = slides_with_no_evidence / slides_total
    low_conf_frac = slides_with_low_confidence_vision / slides_total
    image_only = slides_with_images and not slides_with_text
    text_frac = slides_with_text / slides_total

    if no_ev_frac > 0.30:
        risk_level = RISK_HIGH
        risk_reasons.append(
            f"slides_with_no_evidence={slides_with_no_evidence}/{slides_total} ({no_ev_frac:.0%}) > 30%"
        )
    elif no_ev_frac > 0.10:
        risk_level = RISK_MEDIUM
        risk_reasons.append(
            f"slides_with_no_evidence={slides_with_no_evidence}/{slides_total} ({no_ev_frac:.0%}) > 10%"
        )

    if low_conf_frac > 0.30:
        # Promote to high if it isn't already
        if risk_level != RISK_HIGH:
            risk_level = RISK_HIGH
        risk_reasons.append(
            f"slides_with_low_confidence_vision={slides_with_low_confidence_vision}/{slides_total} ({low_conf_frac:.0%}) > 30%"
        )
    elif low_conf_frac > 0.10:
        if risk_level == RISK_LOW:
            risk_level = RISK_MEDIUM
        risk_reasons.append(
            f"slides_with_low_confidence_vision={slides_with_low_confidence_vision}/{slides_total} ({low_conf_frac:.0%}) > 10%"
        )

    if text_frac < 0.25:
        if risk_level == RISK_LOW:
            risk_level = RISK_MEDIUM
        risk_reasons.append(
            f"slides_with_text={slides_with_text}/{slides_total} ({text_frac:.0%}) < 25% — image-heavy deck"
        )

    if chart_like > 0 or table_like > 0:
        if risk_level == RISK_LOW:
            risk_level = RISK_MEDIUM
        risk_reasons.append(
            f"chart_like_evidence_count={chart_like}, table_like_evidence_count={table_like} "
            "— no native chart/table kinds; grounding is approximate"
        )

    return _result(
        job_id, deck_id, slides_total, len(items), by_kind,
        slides_with_text, slides_with_images, slides_with_diagram,
        slides_with_low_confidence_vision, slides_with_no_evidence,
        slides_with_speaker_notes, chart_like, table_like,
        risk_level, risk_reasons,
    )


def _result(
    job_id, deck_id, slides_total, evidence_nodes_total, by_kind,
    slides_with_text, slides_with_images, slides_with_diagram,
    slides_with_low_confidence_vision, slides_with_no_evidence,
    slides_with_speaker_notes, chart_like, table_like,
    risk_level, risk_reasons,
):
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "deck_id": deck_id,
        "slides_total": slides_total,
        "evidence_nodes_total": evidence_nodes_total,
        "evidence_by_kind": dict(sorted(by_kind.items())),
        "slides_with_text": slides_with_text,
        "slides_with_images": slides_with_images,
        "slides_with_diagram_evidence": slides_with_diagram,
        "slides_with_low_confidence_vision": slides_with_low_confidence_vision,
        "slides_with_no_evidence": slides_with_no_evidence,
        "slides_with_speaker_notes": slides_with_speaker_notes,
        "chart_like_evidence_count": chart_like,
        "table_like_evidence_count": table_like,
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
    }


def write_evidence_health(out_path: PathLike, **kwargs) -> JsonDict:
    result = evaluate(**kwargs)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    return result
