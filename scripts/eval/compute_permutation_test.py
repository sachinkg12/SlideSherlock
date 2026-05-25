"""
Paired permutation test between hallucination-experiment conditions.

Reads per-slide narration text from each condition's ai_narration.json files,
labels each slide with the 24-keyword fabrication proxy, and runs a paired
permutation test (two-sided) on the per-slide binary labels.

Usage:
    python -m scripts.eval.compute_permutation_test \\
        --root /path/to/hallucination_experiment_v2 \\
        --left condition_a --right condition_c \\
        --n 10000 --seed 42

For the released A vs C comparison on 30 decks (279 slides, 21 discordant
pairs) the script reports a Monte Carlo two-sided p of order 1e-4. The
exact analytical p (sign-flip null on the discordant pairs, equivalent to
McNemar's exact for binary paired data) is 464 / 2^21 = 2.21e-4.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Mirrors scripts/eval/proxy_evaluator.py. Kept here so this script runs as a
# stand-alone reproducibility artifact in the anonymous supplementary archive.
FABRICATION_KEYWORDS = (
    "vibrant", "serene", "intricate", "stunning", "landscape", "rural",
    "scenic", "colorful", "abstract", "artistic", "microscopic", "aerial",
    "panoramic", "beautiful", "elegant", "captures", "gazing", "glimpse",
    "vivid", "bright", "lush", "backdrop", "swaying", "tranquil",
)


def _slide_flagged(text: str) -> bool:
    t = (text or "").lower()
    return any(kw in t for kw in FABRICATION_KEYWORDS)


def _iter_narration_entries(data) -> List[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("narration_entries", "entries"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def load_condition_labels(root: Path, condition: str) -> Dict[Tuple[str, int], int]:
    """Map (deck_basename, slide_index) -> 1 if flagged else 0."""
    cond_dir = root / condition
    if not cond_dir.is_dir():
        raise FileNotFoundError(f"condition directory not found: {cond_dir}")
    labels: Dict[Tuple[str, int], int] = {}
    for deck_dir in sorted(p for p in cond_dir.iterdir() if p.is_dir()):
        narration_path = deck_dir / "ai_narration.json"
        if not narration_path.exists():
            continue
        with narration_path.open() as f:
            data = json.load(f)
        for entry in _iter_narration_entries(data):
            text = entry.get("narration_text") or entry.get("text") or ""
            slide_idx = entry.get("slide_index")
            if slide_idx is None:
                continue
            key = (deck_dir.name, int(slide_idx))
            labels[key] = 1 if _slide_flagged(text) else 0
    return labels


def paired_permutation_test(
    left: List[int],
    right: List[int],
    n_permutations: int,
    seed: int,
) -> dict:
    if len(left) != len(right):
        raise ValueError(
            f"paired arrays must be the same length: {len(left)} vs {len(right)}"
        )
    diffs = [r - l for l, r in zip(left, right)]
    observed = sum(diffs) / len(diffs)
    rng = random.Random(seed)
    n_ge_obs = 0
    abs_obs = abs(observed)
    for _ in range(n_permutations):
        s = 0.0
        for d in diffs:
            if rng.random() < 0.5:
                s -= d
            else:
                s += d
        if abs(s / len(diffs)) >= abs_obs:
            n_ge_obs += 1
    # Two-sided p-value with the standard +1 / +1 finite-sample correction.
    p_value = (n_ge_obs + 1) / (n_permutations + 1)
    return {
        "n_pairs": len(diffs),
        "observed_mean_diff": observed,
        "n_permutations": n_permutations,
        "seed": seed,
        "n_at_least_as_extreme": n_ge_obs,
        "p_value": p_value,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path,
                        help="root of hallucination_experiment_v2/")
    parser.add_argument("--left", default="condition_a")
    parser.add_argument("--right", default="condition_c")
    parser.add_argument("--n", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=None,
                        help="optional path to write a JSON result")
    args = parser.parse_args()

    left_labels = load_condition_labels(args.root, args.left)
    right_labels = load_condition_labels(args.root, args.right)

    shared = sorted(set(left_labels) & set(right_labels))
    if not shared:
        print(
            f"no shared (deck, slide) keys between {args.left} and {args.right}",
            file=sys.stderr,
        )
        return 2

    left_arr = [left_labels[k] for k in shared]
    right_arr = [right_labels[k] for k in shared]
    left_rate = sum(left_arr) / len(left_arr)
    right_rate = sum(right_arr) / len(right_arr)

    test = paired_permutation_test(left_arr, right_arr, args.n, args.seed)

    result = {
        "root": str(args.root),
        "left_condition": args.left,
        "right_condition": args.right,
        "n_slides_paired": len(shared),
        "left_flagged": sum(left_arr),
        "right_flagged": sum(right_arr),
        "left_rate": round(left_rate, 6),
        "right_rate": round(right_rate, 6),
        "absolute_reduction": round(left_rate - right_rate, 6),
        "relative_reduction": (
            round((left_rate - right_rate) / left_rate, 6) if left_rate > 0 else None
        ),
        "permutation_test": test,
    }
    out = json.dumps(result, indent=2)
    print(out)
    if args.out:
        args.out.write_text(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
