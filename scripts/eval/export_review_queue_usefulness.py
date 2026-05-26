"""
Quantify whether the operational gate narrows review scope.

Even when every deck routes to "needs review", the value to operators is
how few of each deck's segments actually need human attention. This
script reads per-deck quality-gate, review-queue, verifier, and narration
artifacts and emits two summaries:

    review_queue_usefulness.csv   one row of headline metrics
    review_queue_usefulness.json  same metrics + top reasons + per-deck table

Usage:
    python scripts/eval/export_review_queue_usefulness.py \\
        --input          hallucination_experiment_v2/condition_c \\
        --per-deck-input outputs/emnlp_industry_strict/per_deck \\
        --output         outputs/emnlp_industry
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def _load_json(p: Path) -> Any:
    with p.open() as f:
        return json.load(f)


def _segments_for_deck(verify_report_path: Path) -> int:
    """Number of claim segments the verifier saw for this deck."""
    try:
        data = _load_json(verify_report_path)
        report = data.get("report") if isinstance(data, dict) else data
        return len(report or [])
    except Exception:
        return 0


def _slide_count_for_deck(narration_path: Path) -> int:
    try:
        data = _load_json(narration_path)
        entries = data if isinstance(data, list) else (
            data.get("entries") or data.get("narration_entries") or []
        )
        return len(entries)
    except Exception:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, type=Path,
                    help="hallucination_experiment_v2/condition_c root "
                         "(per-deck verify_report.json + ai_narration.json live here)")
    ap.add_argument("--per-deck-input", required=True, type=Path,
                    help="outputs/<profile>/per_deck root with "
                         "quality_gate.json + review_items.json per deck")
    ap.add_argument("--output", required=True, type=Path,
                    help="output directory (csv + json written here)")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    reason_counter: Counter = Counter()

    for deck_dir in sorted(p for p in args.per_deck_input.iterdir() if p.is_dir()):
        deck_id = deck_dir.name
        qg_path = deck_dir / "quality_gate.json"
        ri_path = deck_dir / "review_items.json"
        if not (qg_path.exists() and ri_path.exists()):
            continue

        qg = _load_json(qg_path)
        ri_doc = _load_json(ri_path)
        review_items = (
            ri_doc.get("items") if isinstance(ri_doc, dict) else ri_doc
        ) or []
        for it in review_items:
            rt = it.get("risk_type")
            if rt:
                reason_counter[rt] += 1

        slides = qg.get("total_slides", 0)
        segments = qg.get("total_segments", 0)
        # Cross-check segment count against the verifier report if available.
        if segments == 0:
            segments = _segments_for_deck(
                args.input / deck_id / "verify_report.json"
            )
        n_items = len(review_items)
        # Slides touched by the review queue (at least one item with that slide_index)
        slides_in_queue = len({
            it.get("slide_index") for it in review_items
            if it.get("slide_index") is not None
        })

        rows.append({
            "deck_id": deck_id,
            "decision": qg.get("decision"),
            "total_slides": slides,
            "total_segments": segments,
            "review_items": n_items,
            "review_items_per_segment": (n_items / segments) if segments else 0.0,
            "slides_in_review_queue": slides_in_queue,
            "fraction_slides_in_queue": (slides_in_queue / slides) if slides else 0.0,
        })

    n_decks = len(rows)
    total_segments = sum(r["total_segments"] for r in rows)
    total_slides = sum(r["total_slides"] for r in rows)
    total_items = sum(r["review_items"] for r in rows)
    items_per_deck = [r["review_items"] for r in rows] or [0]
    items_per_seg = [r["review_items_per_segment"] for r in rows] or [0]
    slides_q_frac = [r["fraction_slides_in_queue"] for r in rows] or [0]

    def _pct(x: float) -> float:
        return round(x * 100, 2)

    def _p(values, percentile):
        if not values:
            return 0.0
        s = sorted(values)
        k = max(0, min(len(s) - 1, int(round((percentile / 100.0) * (len(s) - 1)))))
        return s[k]

    decks_full_review = sum(1 for r in rows if r["fraction_slides_in_queue"] >= 0.9)
    decks_targeted_review = sum(1 for r in rows if 0 < r["fraction_slides_in_queue"] < 0.9)
    decks_no_review = sum(1 for r in rows if r["fraction_slides_in_queue"] == 0)

    summary = {
        "total_decks": n_decks,
        "total_slides": total_slides,
        "total_claim_segments": total_segments,
        "total_review_items": total_items,
        "review_items_per_deck_mean": round(statistics.fmean(items_per_deck), 2),
        "review_items_per_deck_median": statistics.median(items_per_deck),
        "review_items_per_deck_p95": _p(items_per_deck, 95),
        "review_items_per_segment_mean": round(statistics.fmean(items_per_seg), 4),
        "percent_claim_segments_routed_to_review_avg": _pct(
            statistics.fmean(items_per_seg) if items_per_seg else 0
        ),
        "fraction_slides_in_queue_mean": round(statistics.fmean(slides_q_frac), 4),
        "fraction_slides_in_queue_median": round(statistics.median(slides_q_frac), 4),
        "decks_needing_full_manual_review": decks_full_review,
        "decks_with_targeted_review_only": decks_targeted_review,
        "decks_with_no_review_items": decks_no_review,
        "top_five_review_reasons": [
            {"risk_type": k, "count": v} for k, v in reason_counter.most_common(5)
        ],
        "per_deck": rows,
    }

    # CSV: one row of headline metrics + a section with per-deck rows
    with (args.output / "review_queue_usefulness.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k in (
            "total_decks", "total_slides", "total_claim_segments",
            "total_review_items",
            "review_items_per_deck_mean", "review_items_per_deck_median",
            "review_items_per_deck_p95",
            "review_items_per_segment_mean",
            "percent_claim_segments_routed_to_review_avg",
            "fraction_slides_in_queue_mean",
            "fraction_slides_in_queue_median",
            "decks_needing_full_manual_review",
            "decks_with_targeted_review_only",
            "decks_with_no_review_items",
        ):
            w.writerow([k, summary[k]])
        w.writerow([])
        w.writerow(["deck_id", "decision", "total_slides", "total_segments",
                    "review_items", "review_items_per_segment",
                    "slides_in_review_queue", "fraction_slides_in_queue"])
        for r in rows:
            w.writerow([r["deck_id"], r["decision"], r["total_slides"],
                        r["total_segments"], r["review_items"],
                        round(r["review_items_per_segment"], 4),
                        r["slides_in_review_queue"],
                        round(r["fraction_slides_in_queue"], 4)])

    with (args.output / "review_queue_usefulness.json").open("w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps({k: v for k, v in summary.items() if k != "per_deck"}, indent=2))
    print(f"\nWrote {args.output}/review_queue_usefulness.{{csv,json}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
