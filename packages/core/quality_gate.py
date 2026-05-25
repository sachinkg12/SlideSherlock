"""
Operational grounding gate.

Reads verifier, narration, and evidence artifacts from a single pipeline run
and emits one delivery decision: deliver, deliver_with_warnings, needs_review,
or block. This is the production control layer that sits on top of the
verifier; it does not call any model.

Inputs (paths or already-loaded dicts):
    verify_report.json       (verifier per-claim verdicts)
    coverage.json            (aggregate verifier counts)
    ai_narration.json        (per-slide final narration with source_used)
    evidence_index.json      (extracted slide content)
    translation_report.json  (optional, multi-language runs only)
    evidence_health.json     (optional; if not provided we compute the bits we need)

Output: quality_gate.json with the fields enumerated in the spec.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Union

PathLike = Union[str, os.PathLike]
JsonDict = Dict[str, Any]

DECISION_DELIVER = "deliver"
DECISION_DELIVER_WITH_WARNINGS = "deliver_with_warnings"
DECISION_NEEDS_REVIEW = "needs_review"
DECISION_BLOCK = "block"

_FALLBACK_SOURCES = {"post_rewrite_fallback", "template_fallback"}


def _load_json(path_or_obj):
    if path_or_obj is None:
        return None
    if isinstance(path_or_obj, dict) or isinstance(path_or_obj, list):
        return path_or_obj
    with open(path_or_obj) as f:
        return json.load(f)


def load_thresholds(path: Optional[PathLike] = None) -> JsonDict:
    """Load the default threshold config, or an override JSON if path is given."""
    if path is None:
        path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "config", "quality_gate.default.json",
        )
        path = os.path.normpath(path)
    with open(path) as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Signal extraction
# --------------------------------------------------------------------------


def _verifier_signals(verify_report: Optional[JsonDict]) -> JsonDict:
    """Pull per-claim signals out of verify_report.json."""
    if not verify_report:
        return {
            "missing_citation_count": 0,
            "invalid_evidence_id_count": 0,
            "low_confidence_vision_claim_count": 0,
            "image_claim_count": 0,
        }
    report = verify_report.get("report", []) if isinstance(verify_report, dict) else verify_report
    missing = 0
    invalid = 0
    low_conf_vision = 0
    image_claims = 0
    for entry in report:
        reasons = entry.get("reason_codes") or entry.get("reasons") or []
        if "NO_EVIDENCE_IDS" in reasons:
            missing += 1
        if "EVIDENCE_NOT_FOUND" in reasons:
            invalid += 1
        if entry.get("is_image_claim"):
            image_claims += 1
        # Low-confidence-vision claim: image claim whose cited evidence is below threshold
        # (the verifier records the actual confidence used)
        conf = entry.get("confidence_used")
        if entry.get("is_image_claim") and isinstance(conf, (int, float)) and 0.0 < conf < 0.6:
            low_conf_vision += 1
    return {
        "missing_citation_count": missing,
        "invalid_evidence_id_count": invalid,
        "low_confidence_vision_claim_count": low_conf_vision,
        "image_claim_count": image_claims,
    }


def _coverage_signals(coverage: Optional[JsonDict]) -> JsonDict:
    if not coverage:
        return {"pass_count": 0, "rewrite_count": 0, "remove_count": 0, "total_segments": 0}
    return {
        "pass_count": int(coverage.get("pass", 0) or 0),
        "rewrite_count": int(coverage.get("rewrite", 0) or 0),
        "remove_count": int(coverage.get("remove", 0) or 0),
        "total_segments": int(coverage.get("total_claims", 0) or 0),
    }


def _narration_signals(
    ai_narration: Optional[JsonDict],
    thresholds: JsonDict,
) -> JsonDict:
    if not ai_narration:
        return {
            "total_slides": 0,
            "fallback_count": 0,
            "fallback_rate": 0.0,
            "proxy_flagged_slide_count": 0,
            "proxy_flagged_rate": 0.0,
        }
    entries = ai_narration.get("entries") or ai_narration.get("narration_entries") or []
    total = len(entries)
    fallback = 0
    fab_kw = [kw.lower() for kw in thresholds["definitions"]["fabrication_keywords"]]
    flagged = 0
    for entry in entries:
        src = entry.get("source_used", "")
        if src in _FALLBACK_SOURCES:
            fallback += 1
        text = (entry.get("narration_text") or entry.get("text") or "").lower()
        if any(kw in text for kw in fab_kw):
            flagged += 1
    return {
        "total_slides": total,
        "fallback_count": fallback,
        "fallback_rate": (fallback / total) if total else 0.0,
        "proxy_flagged_slide_count": flagged,
        "proxy_flagged_rate": (flagged / total) if total else 0.0,
    }


def _chart_or_table_signal(
    ai_narration: Optional[JsonDict],
    evidence_index: Optional[JsonDict],
    thresholds: JsonDict,
) -> int:
    """Count slides whose narration references charts/tables when only IMAGE_CAPTION or
    TEXT_SPAN evidence exists for that slide (no native chart/table kind)."""
    if not ai_narration:
        return 0
    chart_kw = [kw.lower() for kw in thresholds["definitions"]["chart_like_keywords"]]
    table_kw = [kw.lower() for kw in thresholds["definitions"]["table_like_keywords"]]
    risk_words = chart_kw + table_kw
    entries = ai_narration.get("entries") or ai_narration.get("narration_entries") or []
    # Group evidence kinds by slide
    by_slide: Dict[int, set] = {}
    if evidence_index:
        for it in evidence_index.get("evidence_items", []):
            # slide_index is not directly present on every evidence item; try common locations
            si = it.get("slide_index")
            if si is None:
                ref = it.get("source_ref") or {}
                si = ref.get("slide_index")
            if si is None:
                continue
            by_slide.setdefault(int(si), set()).add(it.get("kind", ""))
    risk = 0
    # Native table evidence kinds extracted by evidence_index.py. If the slide has
    # any of these, narration mentions of "table" or "row" are grounded and do not
    # count as risk. We still flag chart-like narration on those slides because
    # native CHART extraction is not implemented (rendered chart images go through
    # the IMAGE_CAPTION path).
    table_kinds = {"TABLE", "TABLE_CELL", "TABLE_HEADER"}
    chart_kinds = {"CHART"}
    chart_words = set(chart_kw)
    for entry in entries:
        text = (entry.get("narration_text") or entry.get("text") or "").lower()
        mentions_chart = any(w in text for w in chart_words)
        mentions_table = any(w in text for w in table_kw)
        if not (mentions_chart or mentions_table):
            continue
        si = int(entry.get("slide_index", -1))
        kinds = by_slide.get(si, set())
        has_table_ev = bool(kinds & table_kinds)
        has_chart_ev = bool(kinds & chart_kinds)
        # Risk only when the narration's chart/table reference is not backed by a
        # native kind that grounds it.
        if mentions_chart and not has_chart_ev:
            risk += 1
            continue
        if mentions_table and not has_table_ev:
            risk += 1
    return risk


def _translation_signals(translation_report: Optional[JsonDict]) -> int:
    """Count translation warnings from translation_report.json."""
    if not translation_report:
        return 0
    items = translation_report
    if isinstance(translation_report, dict):
        items = (
            translation_report.get("report")
            or translation_report.get("entries")
            or []
        )
    warn = 0
    for it in items or []:
        if it.get("success") is False:
            warn += 1
        if it.get("warning"):
            warn += 1
    return warn


# --------------------------------------------------------------------------
# Decision logic
# --------------------------------------------------------------------------


def _decide(signals: JsonDict, thresholds: JsonDict) -> Dict[str, Any]:
    nr = thresholds["thresholds"]["needs_review"]
    bk = thresholds["thresholds"]["block"]
    reasons: List[str] = []

    # Block takes precedence
    if signals["missing_citation_count"] > bk["missing_citation_count_gt"]:
        reasons.append(
            f"missing_citation_count={signals['missing_citation_count']} > {bk['missing_citation_count_gt']}"
        )
    if signals["invalid_evidence_id_count"] > bk["invalid_evidence_id_count_gt"]:
        reasons.append(
            f"invalid_evidence_id_count={signals['invalid_evidence_id_count']} > {bk['invalid_evidence_id_count_gt']}"
        )
    if signals["proxy_flagged_rate"] > bk["proxy_flagged_rate_gt"]:
        reasons.append(
            f"proxy_flagged_rate={signals['proxy_flagged_rate']:.4f} > {bk['proxy_flagged_rate_gt']}"
        )

    if reasons:
        return {"decision": DECISION_BLOCK, "reasons": reasons}

    review_reasons: List[str] = []
    if signals["fallback_rate"] > nr["fallback_rate_gt"]:
        review_reasons.append(
            f"fallback_rate={signals['fallback_rate']:.4f} > {nr['fallback_rate_gt']}"
        )
    if signals["proxy_flagged_rate"] > nr["proxy_flagged_rate_gt"]:
        review_reasons.append(
            f"proxy_flagged_rate={signals['proxy_flagged_rate']:.4f} > {nr['proxy_flagged_rate_gt']}"
        )
    if signals["low_confidence_vision_claim_count"] > nr["low_confidence_vision_claim_count_gt"]:
        review_reasons.append(
            f"low_confidence_vision_claim_count={signals['low_confidence_vision_claim_count']} > {nr['low_confidence_vision_claim_count_gt']}"
        )
    if signals["chart_or_table_risk_count"] > nr["chart_or_table_risk_count_gt"]:
        review_reasons.append(
            f"chart_or_table_risk_count={signals['chart_or_table_risk_count']} > {nr['chart_or_table_risk_count_gt']}"
        )
    if signals["translation_warning_count"] > nr["translation_warning_count_gt"]:
        review_reasons.append(
            f"translation_warning_count={signals['translation_warning_count']} > {nr['translation_warning_count_gt']}"
        )
    # Optional in the needs_review profile: missing-citation and invalid-evidence-id
    # routing. The strict-audit profile leaves these undefined here and handles them
    # in the block block above; the production-review profile sets them here so the
    # same conditions route to review instead of block.
    if "missing_citation_count_gt" in nr and signals["missing_citation_count"] > nr["missing_citation_count_gt"]:
        review_reasons.append(
            f"missing_citation_count={signals['missing_citation_count']} > {nr['missing_citation_count_gt']}"
        )
    if "invalid_evidence_id_count_gt" in nr and signals["invalid_evidence_id_count"] > nr["invalid_evidence_id_count_gt"]:
        review_reasons.append(
            f"invalid_evidence_id_count={signals['invalid_evidence_id_count']} > {nr['invalid_evidence_id_count_gt']}"
        )
    if review_reasons:
        return {"decision": DECISION_NEEDS_REVIEW, "reasons": review_reasons}

    # No block, no review — choose between deliver and deliver_with_warnings.
    minor_reasons: List[str] = []
    if signals["fallback_rate"] > 0.0:
        minor_reasons.append(
            f"fallback_rate={signals['fallback_rate']:.4f} (any fallback is a minor warning)"
        )
    if signals["rewrite_count"] > 0:
        minor_reasons.append(
            f"rewrite_count={signals['rewrite_count']} (verifier rewrote some segments)"
        )
    if minor_reasons:
        return {"decision": DECISION_DELIVER_WITH_WARNINGS, "reasons": minor_reasons}
    return {"decision": DECISION_DELIVER, "reasons": []}


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def evaluate(
    verify_report: Optional[Union[PathLike, JsonDict]] = None,
    coverage: Optional[Union[PathLike, JsonDict]] = None,
    ai_narration: Optional[Union[PathLike, JsonDict]] = None,
    evidence_index: Optional[Union[PathLike, JsonDict]] = None,
    translation_report: Optional[Union[PathLike, JsonDict]] = None,
    job_id: Optional[str] = None,
    deck_id: Optional[str] = None,
    language: str = "en",
    thresholds_path: Optional[PathLike] = None,
) -> JsonDict:
    """Compute the quality_gate dict for one pipeline run."""
    thresholds = load_thresholds(thresholds_path)
    vr = _load_json(verify_report)
    cov = _load_json(coverage)
    nar = _load_json(ai_narration)
    ei = _load_json(evidence_index)
    tr = _load_json(translation_report)

    vsig = _verifier_signals(vr)
    csig = _coverage_signals(cov)
    nsig = _narration_signals(nar, thresholds)
    ct = _chart_or_table_signal(nar, ei, thresholds)
    tw = _translation_signals(tr)

    # job_id / deck_id resolution: prefer explicit args, then fall back to artifacts.
    if not job_id:
        for src in (vr, cov, nar, ei):
            if isinstance(src, dict) and src.get("job_id"):
                job_id = src["job_id"]
                break

    signals = {
        "total_slides": nsig["total_slides"],
        "total_segments": csig["total_segments"],
        "pass_count": csig["pass_count"],
        "rewrite_count": csig["rewrite_count"],
        "remove_count": csig["remove_count"],
        "fallback_count": nsig["fallback_count"],
        "fallback_rate": round(nsig["fallback_rate"], 6),
        "missing_citation_count": vsig["missing_citation_count"],
        "invalid_evidence_id_count": vsig["invalid_evidence_id_count"],
        "low_confidence_vision_claim_count": vsig["low_confidence_vision_claim_count"],
        "chart_or_table_risk_count": ct,
        "proxy_flagged_slide_count": nsig["proxy_flagged_slide_count"],
        "proxy_flagged_rate": round(nsig["proxy_flagged_rate"], 6),
        "translation_warning_count": tw,
    }

    decision = _decide(signals, thresholds)

    out: JsonDict = {
        "schema_version": "1.0",
        "job_id": job_id,
        "deck_id": deck_id,
        "language": language,
        **signals,
        "decision": decision["decision"],
        "reasons": decision["reasons"],
        # review_items is populated separately by review_queue.py to keep this module pure.
        "review_items": [],
        "thresholds_version": thresholds.get("version"),
    }
    return out


def write_quality_gate(
    out_path: PathLike,
    **evaluate_kwargs,
) -> JsonDict:
    """Convenience: evaluate() then write the JSON to out_path."""
    result = evaluate(**evaluate_kwargs)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    return result
