"""
Human review queue.

Picks out the small set of slides or segments a human should actually look at,
rather than asking them to review the whole video. Each item carries the
risk type, severity, evidence pointers, and a suggested action.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Union

PathLike = Union[str, os.PathLike]
JsonDict = Dict[str, Any]

# Risk types (the allowed vocabulary)
RISK_MISSING_CITATION = "missing_citation"
RISK_INVALID_EVIDENCE_ID = "invalid_evidence_id"
RISK_PROXY_FLAG = "proxy_flag"
RISK_LOW_CONFIDENCE_VISION = "low_confidence_vision"
RISK_CHART_OR_TABLE = "chart_or_table_risk"
RISK_HIGH_FALLBACK = "high_fallback"
RISK_TRANSLATION_WARNING = "translation_warning"
RISK_UNSUPPORTED_VISUAL_CLAIM = "unsupported_visual_claim"
RISK_WEAK_EVIDENCE_COVERAGE = "weak_evidence_coverage"

# Severity
SEV_LOW = "low"
SEV_MEDIUM = "medium"
SEV_HIGH = "high"

# Suggested action
ACT_ACCEPT = "accept"
ACT_EDIT = "edit"
ACT_REGENERATE = "regenerate"
ACT_BLOCK = "block"

_DEFAULT_FAB_KW = (
    "vibrant", "serene", "intricate", "stunning", "landscape", "rural",
    "scenic", "colorful", "abstract", "artistic", "microscopic", "aerial",
    "panoramic", "beautiful", "elegant", "captures", "gazing", "glimpse",
    "vivid", "bright", "lush", "backdrop", "swaying", "tranquil",
)
_CHART_TOKENS = ("chart", "graph", "plot", "histogram")
_TABLE_TOKENS = ("table", "row", "column", "spreadsheet")


def _load(p):
    if p is None:
        return None
    if isinstance(p, (dict, list)):
        return p
    with open(p) as f:
        return json.load(f)


def _evidence_lookup(evidence_index: JsonDict) -> Dict[str, JsonDict]:
    if not evidence_index:
        return {}
    return {
        it.get("evidence_id"): it
        for it in evidence_index.get("evidence_items", [])
        if it.get("evidence_id")
    }


def _snippet(evidence_item: Optional[JsonDict], n: int = 120) -> str:
    if not evidence_item:
        return ""
    txt = (evidence_item.get("content") or "").strip().replace("\n", " ")
    return txt[:n]


def _make_item(
    job_id, deck_id, slide_index, segment_index, segment_text,
    risk_type, risk_reason, evidence_ids, ev_lookup, severity, suggested_action,
):
    return {
        "job_id": job_id,
        "deck_id": deck_id,
        "slide_index": slide_index,
        "segment_index": segment_index,
        "segment_text": segment_text,
        "risk_type": risk_type,
        "risk_reason": risk_reason,
        "evidence_ids": evidence_ids,
        "evidence_snippets": [
            {"evidence_id": eid, "snippet": _snippet(ev_lookup.get(eid))}
            for eid in evidence_ids
        ],
        "severity": severity,
        "suggested_action": suggested_action,
    }


def build(
    quality_gate: Union[PathLike, JsonDict],
    verify_report: Optional[Union[PathLike, JsonDict]] = None,
    evidence_index: Optional[Union[PathLike, JsonDict]] = None,
    ai_narration: Optional[Union[PathLike, JsonDict]] = None,
    evidence_health: Optional[Union[PathLike, JsonDict]] = None,
    translation_report: Optional[Union[PathLike, JsonDict]] = None,
    job_id: Optional[str] = None,
    deck_id: Optional[str] = None,
) -> List[JsonDict]:
    qg = _load(quality_gate) or {}
    vr = _load(verify_report) or {}
    ei = _load(evidence_index) or {}
    nar = _load(ai_narration) or {}
    eh = _load(evidence_health) or {}
    tr = _load(translation_report) or []

    job_id = job_id or qg.get("job_id")
    deck_id = deck_id or qg.get("deck_id")

    items: List[JsonDict] = []
    ev_lookup = _evidence_lookup(ei)

    # 1) Verifier-level: missing citation, invalid evidence ID, low-conf vision claims
    report = vr.get("report", []) if isinstance(vr, dict) else (vr or [])
    for idx, entry in enumerate(report):
        si = entry.get("slide_index")
        reasons = entry.get("reason_codes") or entry.get("reasons") or []
        pointers = entry.get("pointers") or {}
        seg_text = (pointers.get("claim_snippet") or "")[:200]
        cited = pointers.get("evidence_ids") or []

        if "NO_EVIDENCE_IDS" in reasons:
            items.append(_make_item(
                job_id, deck_id, si, idx, seg_text,
                RISK_MISSING_CITATION,
                "verifier reported NO_EVIDENCE_IDS",
                cited, ev_lookup, SEV_HIGH, ACT_REGENERATE,
            ))
        if "EVIDENCE_NOT_FOUND" in reasons:
            items.append(_make_item(
                job_id, deck_id, si, idx, seg_text,
                RISK_INVALID_EVIDENCE_ID,
                f"verifier reported EVIDENCE_NOT_FOUND; invalid={pointers.get('invalid_evidence_ids')}",
                cited, ev_lookup, SEV_HIGH, ACT_BLOCK,
            ))
        # Low-confidence vision evidence used in an image claim
        if entry.get("is_image_claim"):
            conf = entry.get("confidence_used")
            if isinstance(conf, (int, float)) and 0 < conf < 0.6:
                items.append(_make_item(
                    job_id, deck_id, si, idx, seg_text,
                    RISK_LOW_CONFIDENCE_VISION,
                    f"image-claim cited evidence with confidence={conf} < 0.6",
                    cited, ev_lookup, SEV_MEDIUM, ACT_EDIT,
                ))
        if "IMAGE_UNGROUNDED" in reasons or "IMAGE_CLAIM_NEEDS_IMAGE_EVIDENCE" in reasons:
            items.append(_make_item(
                job_id, deck_id, si, idx, seg_text,
                RISK_UNSUPPORTED_VISUAL_CLAIM,
                "image-related claim with no IMAGE_*/DIAGRAM_* evidence",
                cited, ev_lookup, SEV_MEDIUM, ACT_EDIT,
            ))

    # 2) Narration-level: proxy-flagged slides, chart/table risk, high fallback
    entries = nar.get("entries") or nar.get("narration_entries") or []
    fallback_rate = qg.get("fallback_rate", 0.0) or 0.0
    proxy_flagged_rate = qg.get("proxy_flagged_rate", 0.0) or 0.0
    fab_kw = _DEFAULT_FAB_KW

    for idx, entry in enumerate(entries):
        si = entry.get("slide_index")
        text = entry.get("narration_text") or entry.get("text") or ""
        ltext = text.lower()

        hits = [kw for kw in fab_kw if kw in ltext]
        if hits:
            items.append(_make_item(
                job_id, deck_id, si, idx, text[:200],
                RISK_PROXY_FLAG,
                f"proxy keywords: {sorted(set(hits))[:8]}",
                [], ev_lookup,
                SEV_HIGH if proxy_flagged_rate > 0.10 else SEV_MEDIUM,
                ACT_EDIT,
            ))

        if any(t in ltext for t in _CHART_TOKENS) or any(t in ltext for t in _TABLE_TOKENS):
            items.append(_make_item(
                job_id, deck_id, si, idx, text[:200],
                RISK_CHART_OR_TABLE,
                "narration mentions chart/table; no native CHART/TABLE evidence kind",
                [], ev_lookup, SEV_MEDIUM, ACT_EDIT,
            ))

    # 3) Deck-level: high fallback
    if fallback_rate > 0.50:
        items.append(_make_item(
            job_id, deck_id, None, None, "",
            RISK_HIGH_FALLBACK,
            f"fallback_rate={fallback_rate:.4f} > 0.50",
            [], ev_lookup,
            SEV_HIGH if fallback_rate > 0.80 else SEV_MEDIUM,
            ACT_EDIT,
        ))

    # 4) Translation warnings
    tr_items = tr if isinstance(tr, list) else (tr.get("report") or tr.get("entries") or [])
    for tr_entry in tr_items:
        if tr_entry.get("success") is False or tr_entry.get("warning"):
            items.append(_make_item(
                job_id, deck_id, tr_entry.get("slide_index"), None, "",
                RISK_TRANSLATION_WARNING,
                f"translation report: {tr_entry}",
                [], ev_lookup, SEV_LOW, ACT_EDIT,
            ))

    # 5) Evidence-coverage risk from evidence_health (deck-level)
    if isinstance(eh, dict):
        if eh.get("risk_level") == "high":
            items.append(_make_item(
                job_id, deck_id, None, None, "",
                RISK_WEAK_EVIDENCE_COVERAGE,
                f"evidence_health risk_level=high; reasons={eh.get('risk_reasons', [])}",
                [], ev_lookup, SEV_HIGH, ACT_BLOCK,
            ))
        elif eh.get("risk_level") == "medium":
            items.append(_make_item(
                job_id, deck_id, None, None, "",
                RISK_WEAK_EVIDENCE_COVERAGE,
                f"evidence_health risk_level=medium; reasons={eh.get('risk_reasons', [])}",
                [], ev_lookup, SEV_MEDIUM, ACT_EDIT,
            ))

    return items


def write_review_queue(out_path: PathLike, **kwargs) -> List[JsonDict]:
    items = build(**kwargs)
    with open(out_path, "w") as f:
        json.dump({"items": items, "count": len(items)}, f, indent=2)
    return items
