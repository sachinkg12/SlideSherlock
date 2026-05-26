"""
Annotate a sample of slide narrations with a richer label vocabulary than
the binary keyword proxy.

This is a deployment-triage calibration tool, not an academic annotation
study. The labels are the operational categories the production review
queue actually routes on (visual_embellishment, unsupported_chart_trend,
unsupported_entity, unsupported_relation, unsupported_numeric_claim,
translation_drift, other). The four-way label
(supported / unsupported / partially_supported / unclear) maps cleanly
onto the gate's `accept` / `block` / `edit` actions.

Usage (interactive, one row at a time):
    python tools/annotate_review_sample.py \\
        --input  hallucination_annotation.csv \\
        --output reviewer2_labels.csv

Usage (batch from a labels JSON file produced by another annotator):
    python tools/annotate_review_sample.py \\
        --input  hallucination_annotation.csv \\
        --labels reviewer2_calls.json \\
        --output reviewer2_labels.csv

The labels JSON is a list of objects with at minimum `row_id`, `label`,
and `risk_reason`; optional fields are `notes` and `annotator_id`.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

LABELS = ("supported", "unsupported", "partially_supported", "unclear")
RISK_REASONS = (
    "visual_embellishment",
    "unsupported_chart_trend",
    "unsupported_entity",
    "unsupported_relation",
    "unsupported_numeric_claim",
    "translation_drift",
    "other",
    "",  # empty when label is "supported"
)


def load_input(path: Path) -> List[Dict[str, Any]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def load_labels(path: Path) -> Dict[str, Dict[str, Any]]:
    with path.open() as f:
        data = json.load(f)
    return {str(item["row_id"]): item for item in data}


def interactive_annotate(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, r in enumerate(rows, 1):
        print()
        print(f"=== row {i}/{len(rows)} (row_id={r['row_id']}) ===")
        print(f"condition: {r.get('condition','?')}  proxy_flagged: {r.get('proxy_flagged','?')}")
        print(f"slide_text:    {(r.get('slide_text') or '(none)')[:200]}")
        print(f"shape_labels:  {(r.get('shape_labels') or '(none)')[:200]}")
        print(f"image_caption: {(r.get('image_captions') or '(none)')[:300]}")
        print(f"narration:     {r.get('narration','')[:400]}")
        print(f"reviewer1:     {r.get('your_label','?')}")
        try:
            print(f"label one of: {LABELS}")
            label = input("label > ").strip().lower()
            if label not in LABELS:
                print("(skipped, invalid)")
                continue
            reason = ""
            if label != "supported":
                print(f"risk_reason one of: {RISK_REASONS}")
                reason = input("risk_reason > ").strip().lower()
            notes = input("notes (optional) > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(interrupted; saving what we have)")
            break
        out.append({
            "row_id": r["row_id"],
            "annotator_id": "reviewer2",
            "label": label,
            "risk_reason": reason,
            "notes": notes,
        })
    return out


def merge_labels(
    rows: List[Dict[str, Any]],
    labels: Dict[str, Dict[str, Any]],
    annotator_id: str = "reviewer2",
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        rid = str(r["row_id"])
        lab = labels.get(rid)
        if lab is None:
            continue
        if lab.get("label") not in LABELS:
            raise ValueError(f"row {rid}: invalid label {lab.get('label')!r}")
        if lab.get("risk_reason", "") not in RISK_REASONS:
            raise ValueError(
                f"row {rid}: invalid risk_reason {lab.get('risk_reason')!r}"
            )
        out.append({
            "row_id": rid,
            "annotator_id": lab.get("annotator_id", annotator_id),
            "label": lab["label"],
            "risk_reason": lab.get("risk_reason", ""),
            "notes": lab.get("notes", ""),
        })
    return out


def write_csv(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["row_id", "annotator_id", "label", "risk_reason", "notes"])
        for it in items:
            w.writerow([it["row_id"], it["annotator_id"], it["label"],
                        it["risk_reason"], it["notes"]])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, type=Path,
                    help="CSV with row_id, condition, slide_text, narration, ...")
    ap.add_argument("--output", required=True, type=Path,
                    help="reviewer2_labels.csv (row_id, annotator_id, label, ...)")
    ap.add_argument("--labels", type=Path, default=None,
                    help="batch mode: JSON list of {row_id, label, risk_reason, notes}")
    ap.add_argument("--annotator-id", default="reviewer2")
    args = ap.parse_args()

    rows = load_input(args.input)

    if args.labels:
        labels = load_labels(args.labels)
        items = merge_labels(rows, labels, args.annotator_id)
    else:
        items = interactive_annotate(rows)

    write_csv(args.output, items)
    print(f"wrote {len(items)} annotations to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
