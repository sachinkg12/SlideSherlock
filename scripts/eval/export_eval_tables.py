"""
Regenerate the hallucination-experiment summary tables from on-disk artifacts.

The tables are derived from:
  - hallucination_experiment_v2/condition_{a,b,c}/<deck>/ai_narration.json
  - hallucination_experiment_v2/experiment_results.json
  - <manual_annotation_csv> (optional, defaults to hallucination_annotation.csv)

Usage:
    python -m scripts.eval.export_eval_tables \\
        --root /path/to/hallucination_experiment_v2 \\
        --table main
    python -m scripts.eval.export_eval_tables --root <...> --table fallback
    python -m scripts.eval.export_eval_tables --root <...> --table verifier
    python -m scripts.eval.export_eval_tables --root <...> --table proxy_validation \\
        --annotation /path/to/hallucination_annotation.csv

The script emits a small JSON header on stdout followed by either a plain
Markdown table or, with --latex, the booktabs LaTeX rows.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

FABRICATION_KEYWORDS = (
    "vibrant", "serene", "intricate", "stunning", "landscape", "rural",
    "scenic", "colorful", "abstract", "artistic", "microscopic", "aerial",
    "panoramic", "beautiful", "elegant", "captures", "gazing", "glimpse",
    "vivid", "bright", "lush", "backdrop", "swaying", "tranquil",
)
CONDITIONS = ("condition_a", "condition_b", "condition_c")
CONDITION_LABEL = {
    "condition_a": "A: raw GPT",
    "condition_b": "B: evidence prompt",
    "condition_c": "C: full pipeline",
}


def _slide_flagged(text: str) -> bool:
    t = (text or "").lower()
    return any(kw in t for kw in FABRICATION_KEYWORDS)


def _iter_entries(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("narration_entries", "entries"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def collect_per_condition(root: Path) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for cond in CONDITIONS:
        cond_dir = root / cond
        if not cond_dir.is_dir():
            continue
        n_slides = 0
        n_flagged = 0
        source_counter: Counter = Counter()
        for deck_dir in sorted(p for p in cond_dir.iterdir() if p.is_dir()):
            nar = deck_dir / "ai_narration.json"
            if not nar.exists():
                continue
            with nar.open() as f:
                data = json.load(f)
            for entry in _iter_entries(data):
                text = entry.get("narration_text") or entry.get("text") or ""
                source = entry.get("source_used") or entry.get("source") or ""
                n_slides += 1
                if _slide_flagged(text):
                    n_flagged += 1
                if source:
                    source_counter[source] += 1
        out[cond] = {
            "slides": n_slides,
            "flagged": n_flagged,
            "rate": (n_flagged / n_slides) if n_slides else 0.0,
            "source_used": dict(source_counter),
        }
    return out


def load_aggregate_verifier(root: Path) -> Dict[str, int]:
    agg_path = root / "experiment_results.json"
    if not agg_path.exists():
        return {}
    with agg_path.open() as f:
        data = json.load(f)
    c = (
        data.get("conditions", {})
        .get("condition_c", {})
        .get("aggregate", {})
    )
    return {
        "total_claims": c.get("total_claims", 0),
        "pass": c.get("verifier_pass", 0),
        "rewrite": c.get("verifier_rewrite", 0),
        "remove": c.get("verifier_remove", 0),
    }


def compute_proxy_validation(csv_path: Path) -> Dict[str, int]:
    rows = list(csv.DictReader(csv_path.open()))

    def _b(v: str) -> bool:
        s = (v or "").strip().lower()
        return s in {"1", "true", "yes", "y", "t", "fabricated", "hallucinated"}

    proxy = [_b(r.get("proxy_flagged", "")) for r in rows]
    manual = [_b(r.get("your_label", "")) for r in rows]
    tp = sum(1 for p, m in zip(proxy, manual) if p and m)
    fp = sum(1 for p, m in zip(proxy, manual) if p and not m)
    fn = sum(1 for p, m in zip(proxy, manual) if not p and m)
    tn = sum(1 for p, m in zip(proxy, manual) if not p and not m)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "n": len(rows),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _print_md_main(per_cond: Dict[str, Dict]) -> None:
    base = per_cond.get("condition_a", {}).get("rate", 0.0)
    print("| Condition | Flagged | Total | Rate | Δ vs A |")
    print("|---|---:|---:|---:|---:|")
    for cond in CONDITIONS:
        d = per_cond.get(cond, {})
        flagged = d.get("flagged", 0)
        slides = d.get("slides", 0)
        rate = d.get("rate", 0.0) * 100
        if base > 0:
            delta_pct = (rate / 100 - base) / base * 100
            delta_str = f"{delta_pct:+.1f}%"
        else:
            delta_str = "—"
        delta = "—" if cond == "condition_a" else delta_str
        print(
            f"| {CONDITION_LABEL[cond]} | {flagged} | {slides} | "
            f"{rate:.2f}% | {delta} |"
        )


def _print_latex_main(per_cond: Dict[str, Dict]) -> None:
    base = per_cond.get("condition_a", {}).get("rate", 0.0)
    rows: List[str] = []
    for cond in CONDITIONS:
        d = per_cond.get(cond, {})
        flagged = d.get("flagged", 0)
        slides = d.get("slides", 0)
        rate = d.get("rate", 0.0) * 100
        if cond == "condition_a":
            delta = "---"
        elif base > 0:
            r = d.get("rate", 0.0)
            delta_pct = (r - base) / base * 100
            delta = f"{delta_pct:+.0f}\\%"
        else:
            delta = "---"
        rows.append(
            f"{CONDITION_LABEL[cond]} & {flagged} & {slides} & "
            f"{rate:.2f}\\% & {delta} \\\\"
        )
    print("\n".join(rows))


def _print_md_fallback(per_cond: Dict[str, Dict]) -> None:
    print("| Condition | Slides | Fallback | Rate |")
    print("|---|---:|---:|---:|")
    for cond in CONDITIONS:
        d = per_cond.get(cond, {})
        n = d.get("slides", 0)
        fb = d.get("source_used", {}).get("post_rewrite_fallback", 0)
        rate = (fb / n * 100) if n else 0.0
        print(f"| {CONDITION_LABEL[cond]} | {n} | {fb} | {rate:.1f}% |")


def _print_md_verifier(v: Dict[str, int]) -> None:
    total = v.get("total_claims", 0)
    print("| Verdict | Count | Share |")
    print("|---|---:|---:|")
    for name in ("pass", "rewrite", "remove"):
        c = v.get(name, 0)
        share = (c / total * 100) if total else 0.0
        print(f"| {name.upper()} | {c} | {share:.1f}% |")


def _print_md_proxy(v: Dict[str, int]) -> None:
    print("| Metric | Value |")
    print("|---|---:|")
    for k in ("n", "tp", "fp", "fn", "tn", "precision", "recall", "f1"):
        print(f"| {k} | {v[k]} |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--table",
        required=True,
        choices=("main", "fallback", "verifier", "proxy_validation"),
    )
    parser.add_argument(
        "--annotation",
        type=Path,
        default=None,
        help="path to hallucination_annotation.csv (for --table proxy_validation)",
    )
    parser.add_argument("--latex", action="store_true",
                        help="emit LaTeX rows (currently for --table main only)")
    args = parser.parse_args()

    if args.table in {"main", "fallback"}:
        per_cond = collect_per_condition(args.root)
        if args.table == "main":
            print(json.dumps({"table": "main", "per_condition": per_cond}, indent=2))
            print("---")
            if args.latex:
                _print_latex_main(per_cond)
            else:
                _print_md_main(per_cond)
        else:
            print(json.dumps({"table": "fallback", "per_condition": per_cond}, indent=2))
            print("---")
            _print_md_fallback(per_cond)
        return 0

    if args.table == "verifier":
        v = load_aggregate_verifier(args.root)
        print(json.dumps({"table": "verifier", "aggregate": v}, indent=2))
        print("---")
        _print_md_verifier(v)
        return 0

    if args.table == "proxy_validation":
        if not args.annotation:
            print(
                "--annotation is required for --table proxy_validation",
                file=sys.stderr,
            )
            return 2
        if not args.annotation.exists():
            print(f"annotation file not found: {args.annotation}", file=sys.stderr)
            return 2
        v = compute_proxy_validation(args.annotation)
        print(json.dumps({"table": "proxy_validation", "stats": v}, indent=2))
        print("---")
        _print_md_proxy(v)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
