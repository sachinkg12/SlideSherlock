"""
Run the operational grounding gate, evidence-health report, and review queue
across every deck in a results directory (e.g. a condition_c experiment dir),
then emit four summary artifacts:

    quality_gate_summary.csv      one row per deck
    evidence_health_summary.csv   one row per deck
    review_queue_summary.csv      one row per deck (counts only; full items
                                  are written per-deck for inspection)
    production_decision_summary.json   aggregated counts + top review reasons

Usage:
    python scripts/eval/export_quality_tables.py \\
        --input hallucination_experiment_v2/condition_c \\
        --output outputs/quality_tables
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

# Allow running both as `python scripts/eval/...` and `python -m scripts.eval...`
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "core"))

from packages.core import quality_gate, evidence_health, review_queue, production_summary  # noqa: E402


REQUIRED_PER_DECK = ("verify_report.json", "coverage.json", "ai_narration.json", "evidence_index.json")


def _process_deck(deck_dir: Path, thresholds_path: Path | None = None) -> Dict:
    paths = {name: deck_dir / name for name in REQUIRED_PER_DECK}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        return {"deck_id": deck_dir.name, "status": "skipped", "reason": f"missing {missing}"}

    eh = evidence_health.evaluate(
        evidence_index=str(paths["evidence_index.json"]),
        deck_id=deck_dir.name,
    )
    qg = quality_gate.evaluate(
        verify_report=str(paths["verify_report.json"]),
        coverage=str(paths["coverage.json"]),
        ai_narration=str(paths["ai_narration.json"]),
        evidence_index=str(paths["evidence_index.json"]),
        translation_report=str(deck_dir / "translation_report.json") if (deck_dir / "translation_report.json").exists() else None,
        deck_id=deck_dir.name,
        thresholds_path=str(thresholds_path) if thresholds_path else None,
    )
    rq = review_queue.build(
        quality_gate=qg,
        verify_report=str(paths["verify_report.json"]),
        evidence_index=str(paths["evidence_index.json"]),
        ai_narration=str(paths["ai_narration.json"]),
        evidence_health=eh,
    )
    summary = production_summary.build(qg, eh, rq)
    return {
        "deck_id": deck_dir.name,
        "status": "ok",
        "quality_gate": qg,
        "evidence_health": eh,
        "review_items": rq,
        "production_summary": summary,
    }


def _write_quality_gate_csv(out_path: Path, rows: List[Dict]) -> None:
    headers = [
        "deck_id", "decision", "total_slides", "total_segments",
        "pass_count", "rewrite_count", "remove_count",
        "fallback_count", "fallback_rate",
        "missing_citation_count", "invalid_evidence_id_count",
        "low_confidence_vision_claim_count",
        "chart_or_table_risk_count",
        "proxy_flagged_slide_count", "proxy_flagged_rate",
        "translation_warning_count",
        "reasons",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            qg = r["quality_gate"]
            w.writerow([
                r["deck_id"], qg["decision"],
                qg["total_slides"], qg["total_segments"],
                qg["pass_count"], qg["rewrite_count"], qg["remove_count"],
                qg["fallback_count"], qg["fallback_rate"],
                qg["missing_citation_count"], qg["invalid_evidence_id_count"],
                qg["low_confidence_vision_claim_count"],
                qg["chart_or_table_risk_count"],
                qg["proxy_flagged_slide_count"], qg["proxy_flagged_rate"],
                qg["translation_warning_count"],
                "; ".join(qg["reasons"]),
            ])


def _write_evidence_health_csv(out_path: Path, rows: List[Dict]) -> None:
    headers = [
        "deck_id", "risk_level", "slides_total", "evidence_nodes_total",
        "slides_with_text", "slides_with_images", "slides_with_diagram_evidence",
        "slides_with_low_confidence_vision", "slides_with_no_evidence",
        "chart_like_evidence_count", "table_like_evidence_count",
        "risk_reasons",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            eh = r["evidence_health"]
            w.writerow([
                r["deck_id"], eh["risk_level"],
                eh["slides_total"], eh["evidence_nodes_total"],
                eh["slides_with_text"], eh["slides_with_images"],
                eh["slides_with_diagram_evidence"],
                eh["slides_with_low_confidence_vision"],
                eh["slides_with_no_evidence"],
                eh["chart_like_evidence_count"],
                eh["table_like_evidence_count"],
                "; ".join(eh["risk_reasons"]),
            ])


def _write_review_queue_csv(out_path: Path, rows: List[Dict]) -> None:
    headers = [
        "deck_id", "total_review_items",
        "missing_citation", "invalid_evidence_id", "proxy_flag",
        "low_confidence_vision", "chart_or_table_risk", "high_fallback",
        "translation_warning", "unsupported_visual_claim", "weak_evidence_coverage",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            items = r["review_items"]
            counts = Counter(it["risk_type"] for it in items)
            w.writerow([
                r["deck_id"], len(items),
                counts.get("missing_citation", 0),
                counts.get("invalid_evidence_id", 0),
                counts.get("proxy_flag", 0),
                counts.get("low_confidence_vision", 0),
                counts.get("chart_or_table_risk", 0),
                counts.get("high_fallback", 0),
                counts.get("translation_warning", 0),
                counts.get("unsupported_visual_claim", 0),
                counts.get("weak_evidence_coverage", 0),
            ])


def _write_aggregate_json(out_path: Path, rows: List[Dict]) -> Dict:
    decisions = Counter(r["quality_gate"]["decision"] for r in rows)
    all_reasons = Counter()
    total_review_items = 0
    fallback_rates = []
    proxy_rates = []
    low_conf_decks = 0
    chart_table_decks = 0
    for r in rows:
        for it in r["review_items"]:
            all_reasons[it["risk_type"]] += 1
        total_review_items += len(r["review_items"])
        fallback_rates.append(r["quality_gate"]["fallback_rate"])
        proxy_rates.append(r["quality_gate"]["proxy_flagged_rate"])
        if r["quality_gate"]["low_confidence_vision_claim_count"] > 0:
            low_conf_decks += 1
        if r["quality_gate"]["chart_or_table_risk_count"] > 0:
            chart_table_decks += 1
    n = len(rows) or 1
    summary = {
        "schema_version": "1.0",
        "deck_count": len(rows),
        "decisions": {
            "deliver": decisions.get("deliver", 0),
            "deliver_with_warnings": decisions.get("deliver_with_warnings", 0),
            "needs_review": decisions.get("needs_review", 0),
            "block": decisions.get("block", 0),
        },
        "top_review_reasons_top5": [
            {"risk_type": k, "count": v} for k, v in all_reasons.most_common(5)
        ],
        "mean_fallback_rate": round(sum(fallback_rates) / n, 6) if rows else 0.0,
        "mean_proxy_flagged_rate": round(sum(proxy_rates) / n, 6) if rows else 0.0,
        "total_review_items": total_review_items,
        "mean_review_items_per_deck": round(total_review_items / n, 4) if rows else 0.0,
        "decks_with_low_confidence_vision_risk": low_conf_decks,
        "decks_with_chart_or_table_risk": chart_table_decks,
    }
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path,
                   help="Directory containing per-deck subdirectories with the four required JSON files.")
    p.add_argument("--output", required=True, type=Path,
                   help="Output directory; will be created.")
    p.add_argument("--write-per-deck", action="store_true",
                   help="Also write per-deck quality_gate/evidence_health/review_items/production_summary into output/per_deck/<deck>/")
    p.add_argument("--thresholds", type=Path, default=None,
                   help="Path to a quality_gate threshold profile JSON (defaults to config/quality_gate.default.json).")
    args = p.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    decks = sorted(p for p in args.input.iterdir() if p.is_dir())
    rows: List[Dict] = []
    skipped: List[Dict] = []
    for deck_dir in decks:
        result = _process_deck(deck_dir, thresholds_path=args.thresholds)
        if result.get("status") == "skipped":
            skipped.append(result)
            continue
        rows.append(result)
        if args.write_per_deck:
            per_deck_out = args.output / "per_deck" / deck_dir.name
            per_deck_out.mkdir(parents=True, exist_ok=True)
            with open(per_deck_out / "quality_gate.json", "w") as f:
                json.dump(result["quality_gate"], f, indent=2)
            with open(per_deck_out / "evidence_health.json", "w") as f:
                json.dump(result["evidence_health"], f, indent=2)
            with open(per_deck_out / "review_items.json", "w") as f:
                json.dump({"items": result["review_items"]}, f, indent=2)
            with open(per_deck_out / "production_summary.json", "w") as f:
                json.dump(result["production_summary"], f, indent=2)
            with open(per_deck_out / "production_summary.html", "w") as f:
                f.write(production_summary.render_html(result["production_summary"]))

    _write_quality_gate_csv(args.output / "quality_gate_summary.csv", rows)
    _write_evidence_health_csv(args.output / "evidence_health_summary.csv", rows)
    _write_review_queue_csv(args.output / "review_queue_summary.csv", rows)
    agg = _write_aggregate_json(args.output / "production_decision_summary.json", rows)

    print(json.dumps({
        "decks_processed": len(rows),
        "decks_skipped": len(skipped),
        "skip_reasons": [s["reason"] for s in skipped][:5],
        "summary": agg,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
