"""
Translation of narration (script segments) and notes for target language variants.
Preserves grounding (claim_id, entity_ids, evidence_ids). Faithful translation only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from verifier import verify_script
except ImportError:
    verify_script = None

SOURCE_LANG_DEFAULT = "en-US"


def translate_script_segments(
    verified_script: Dict[str, Any],
    translator: Any,
    source_lang: str,
    target_lang: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], bool]:
    """
    Translate segment texts only. Keep claim_id, entity_ids, evidence_ids unchanged.
    Returns (translated_script, report_entries, success).
    """
    if source_lang == target_lang:
        return verified_script, [], True
    segments = verified_script.get("segments", [])
    translated_segments: List[Dict[str, Any]] = []
    report_entries: List[Dict[str, Any]] = []
    all_ok = True
    for seg in segments:
        claim_id = seg.get("claim_id", "")
        text = (seg.get("text") or "").strip()
        slide_index = seg.get("slide_index", 0)
        translated = None
        if text and translator and translator.is_available():
            translated = translator.translate(text, source_lang, target_lang)
        if translated and (translated or "").strip():
            translated_segments.append({
                **seg,
                "text": translated.strip(),
            })
            report_entries.append({
                "claim_id": claim_id,
                "slide_index": slide_index,
                "success": True,
                "source_len": len(text),
                "target_len": len(translated),
            })
        else:
            translated_segments.append(seg)
            report_entries.append({
                "claim_id": claim_id,
                "slide_index": slide_index,
                "success": False,
                "fallback": "en",
            })
            all_ok = False
    return (
        {"segments": translated_segments, "schema_version": verified_script.get("schema_version", "1.0")},
        report_entries,
        all_ok,
    )


def translate_notes_per_slide(
    slides_notes: List[Tuple[str, str]],
    translator: Any,
    source_lang: str,
    target_lang: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Translate notes per slide. slides_notes: [(notes, slide_text), ...].
    Returns (translated_notes_list, report_entries).
    """
    if source_lang == target_lang:
        return [n for n, _ in slides_notes], []
    translated: List[str] = []
    report: List[Dict[str, Any]] = []
    for i, (notes, _) in enumerate(slides_notes):
        notes = (notes or "").strip()
        if not notes:
            translated.append("")
            report.append({"slide_index": i + 1, "success": True, "empty": True})
            continue
        tr = None
        if translator and translator.is_available():
            tr = translator.translate(notes, source_lang, target_lang)
        if tr and (tr or "").strip():
            translated.append(tr.strip())
            report.append({"slide_index": i + 1, "success": True, "source_len": len(notes), "target_len": len(tr)})
        else:
            translated.append(notes)
            report.append({"slide_index": i + 1, "success": False, "fallback": "en"})
    return translated, report


def verify_translated_script(
    translated_script: Dict[str, Any],
    evidence_index: Dict[str, Any],
    unified_graphs_by_slide: Dict[int, Dict[str, Any]],
) -> Tuple[bool, Dict[str, Any]]:
    """
    Run verifier on translated script. Check citations present, entity_ids valid.
    Returns (pass, coverage).
    """
    if not verify_script:
        return True, {}
    try:
        _, coverage = verify_script(
            translated_script,
            evidence_index,
            unified_graphs_by_slide,
        )
        pass_count = coverage.get("pass", 0)
        total = coverage.get("total_claims", 0)
        return (total == 0 or pass_count == total), coverage
    except Exception:
        return False, {}


def derive_narration_from_script(
    script: Dict[str, Any],
    slide_count: int,
) -> List[Dict[str, Any]]:
    """
    Derive per-slide narration by aggregating segment texts per slide.
    Returns narration_entries: [{slide_index, narration_text, source_used, word_count}, ...]
    """
    segments = script.get("segments", [])
    by_slide: Dict[int, List[str]] = defaultdict(list)
    for seg in segments:
        si = seg.get("slide_index", 0)
        text = (seg.get("text") or "").strip()
        if text:
            by_slide[si].append(text)
    entries = []
    for i in range(slide_count):
        slide_index = i + 1
        texts = by_slide.get(slide_index, [])
        narration_text = " ".join(texts).strip() if texts else ""
        entries.append({
            "slide_index": slide_index,
            "narration_text": narration_text,
            "source_used": "script",
            "word_count": len(narration_text.split()),
        })
    return entries


def build_translation_report(
    job_id: str,
    variant_id: str,
    target_lang: str,
    script_report: List[Dict[str, Any]],
    notes_report: List[Dict[str, Any]],
    script_verified: bool,
    degraded: bool,
) -> Dict[str, Any]:
    """Build translation_report.json payload."""
    script_ok = sum(1 for r in script_report if r.get("success")) if script_report else 0
    script_total = len(script_report) if script_report else 0
    notes_ok = sum(1 for r in notes_report if r.get("success")) if notes_report else 0
    notes_total = len(notes_report) if notes_report else 0
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "variant_id": variant_id,
        "target_lang": target_lang,
        "script_translated": script_ok,
        "script_total": script_total,
        "notes_translated": notes_ok,
        "notes_total": notes_total,
        "script_verified": script_verified,
        "degraded": degraded,
        "script_report": script_report,
        "notes_report": notes_report,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
