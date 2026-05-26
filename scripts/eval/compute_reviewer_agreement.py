"""
Compare two annotators' labels on the proxy-validation slide sample.

This is a deployment-triage calibration metric: how often does the rich
four-way label (supported / unsupported / partially_supported / unclear)
agree on the binary delivery-relevant question "would this segment be
routed for human review?" The output is precision, recall, F1, agreement
rate, Cohen's kappa, a confusion matrix, and the disagreement examples
(so a deployment team can read the disagreements).

Reviewer 1 labels come from hallucination_annotation.csv (column
`your_label`, values HALLUCINATED / NOT). Reviewer 2 labels come from
the richer schema produced by tools/annotate_review_sample.py.

Mapping for the binary comparison:
    reviewer 1 HALLUCINATED   <->  reviewer 2 unsupported or partially_supported
    reviewer 1 NOT            <->  reviewer 2 supported
    reviewer 2 unclear        ->   excluded from the binary metric
                                   (reported separately)

Usage:
    python -m scripts.eval.compute_reviewer_agreement \\
        --reviewer1 hallucination_annotation.csv \\
        --reviewer2 reviewer2_labels.csv \\
        --output-json outputs/emnlp_industry/reviewer_agreement.json \\
        --output-csv  outputs/emnlp_industry/reviewer_agreement.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple


LABELS_R2 = ("supported", "unsupported", "partially_supported", "unclear")


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _r1_binary(value: str) -> bool:
    return (value or "").strip().upper().startswith("HALL")


def _r2_binary(label: str) -> int:
    """Return 1 if reviewer 2 would route to review, 0 if not, -1 if unclear."""
    lab = (label or "").strip().lower()
    if lab == "supported":
        return 0
    if lab in {"unsupported", "partially_supported"}:
        return 1
    return -1  # unclear


def _cohens_kappa(p_o: float, p_e: float) -> float:
    if p_e >= 1.0:
        return 0.0
    return (p_o - p_e) / (1.0 - p_e)


def compute(
    reviewer1_rows: List[Dict[str, str]],
    reviewer2_rows: List[Dict[str, str]],
) -> Dict[str, Any]:
    r2_by_id: Dict[str, Dict[str, str]] = {r["row_id"]: r for r in reviewer2_rows}

    paired: List[Tuple[str, int, int, Dict[str, str], Dict[str, str]]] = []
    excluded_unclear: List[str] = []
    label_counts_r2 = {lab: 0 for lab in LABELS_R2}
    for r1 in reviewer1_rows:
        rid = r1["row_id"]
        r2 = r2_by_id.get(rid)
        if r2 is None:
            continue
        label_counts_r2[r2["label"]] = label_counts_r2.get(r2["label"], 0) + 1
        v1 = 1 if _r1_binary(r1["your_label"]) else 0
        v2 = _r2_binary(r2["label"])
        if v2 < 0:
            excluded_unclear.append(rid)
            continue
        paired.append((rid, v1, v2, r1, r2))

    n = len(paired)
    if n == 0:
        return {
            "n_paired": 0,
            "n_excluded_unclear": len(excluded_unclear),
            "note": "no paired observations after excluding unclear",
        }

    tp = sum(1 for _, v1, v2, *_ in paired if v1 == 1 and v2 == 1)
    fp = sum(1 for _, v1, v2, *_ in paired if v1 == 0 and v2 == 1)
    fn = sum(1 for _, v1, v2, *_ in paired if v1 == 1 and v2 == 0)
    tn = sum(1 for _, v1, v2, *_ in paired if v1 == 0 and v2 == 0)

    agree = tp + tn
    p_o = agree / n
    p1_pos = (tp + fn) / n
    p2_pos = (tp + fp) / n
    p_e = p1_pos * p2_pos + (1 - p1_pos) * (1 - p2_pos)
    kappa = _cohens_kappa(p_o, p_e)

    # As a "would route to review" classifier, reviewer-2 vs reviewer-1 as ground truth:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # Pull disagreements with brief context
    disagreements: List[Dict[str, Any]] = []
    for rid, v1, v2, r1, r2 in paired:
        if v1 != v2:
            disagreements.append({
                "row_id": rid,
                "condition": r1.get("condition"),
                "reviewer1": "HALLUCINATED" if v1 else "NOT",
                "reviewer2_label": r2.get("label"),
                "reviewer2_risk_reason": r2.get("risk_reason", ""),
                "proxy_flagged": r1.get("proxy_flagged"),
                "narration_snippet": (r1.get("narration") or "")[:200],
                "notes": r2.get("notes", ""),
            })

    return {
        "n_paired": n,
        "n_excluded_unclear": len(excluded_unclear),
        "excluded_unclear_row_ids": excluded_unclear,
        "label_counts_r2": label_counts_r2,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "agreement_rate": round(p_o, 4),
        "cohens_kappa": round(kappa, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "disagreements": disagreements,
    }


def _write_csv_summary(out_path: Path, stats: Dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["n_paired", stats["n_paired"]])
        w.writerow(["n_excluded_unclear", stats["n_excluded_unclear"]])
        cm = stats.get("confusion_matrix", {})
        for k in ("tp", "fp", "fn", "tn"):
            w.writerow([k, cm.get(k, 0)])
        for k in ("agreement_rate", "cohens_kappa", "precision", "recall", "f1"):
            w.writerow([k, stats.get(k, 0)])
        for k, v in stats.get("label_counts_r2", {}).items():
            w.writerow([f"r2_label_count_{k}", v])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reviewer1", required=True, type=Path)
    ap.add_argument("--reviewer2", required=True, type=Path)
    ap.add_argument("--output-json", type=Path, default=None)
    ap.add_argument("--output-csv", type=Path, default=None)
    args = ap.parse_args()

    r1 = _read_csv(args.reviewer1)
    r2 = _read_csv(args.reviewer2)
    stats = compute(r1, r2)

    print(json.dumps({k: v for k, v in stats.items() if k != "disagreements"}, indent=2))
    print(f"\n({len(stats.get('disagreements', []))} disagreements; "
          f"see {args.output_json or 'output JSON'} for the list.)")

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with args.output_json.open("w") as f:
            json.dump(stats, f, indent=2)
    if args.output_csv:
        _write_csv_summary(args.output_csv, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
