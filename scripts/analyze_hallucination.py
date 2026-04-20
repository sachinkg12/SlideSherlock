#!/usr/bin/env python3
"""
Post-hoc hallucination analysis for experiment E1-E3.

Reads ai_narration.json + evidence_index.json from each condition,
applies token-overlap verification to measure what fraction of
narration claims are grounded in evidence.

Usage:
    python scripts/analyze_hallucination.py /path/to/hallucination_experiment
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

# Image-related keywords that indicate visual claims
IMAGE_KEYWORDS = {
    "image",
    "photo",
    "picture",
    "diagram",
    "chart",
    "graph",
    "figure",
    "illustration",
    "screenshot",
    "logo",
    "icon",
    "map",
    "table",
    "shows",
    "depicts",
    "displays",
    "illustrates",
    "visualizes",
    "appears",
    "seen",
    "visible",
    "landscape",
    "portrait",
}

# Filler/structural words to exclude from token overlap
STOP_WORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "shall",
    "can",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "we",
    "our",
    "you",
    "your",
    "they",
    "their",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "into",
    "through",
    "about",
    "between",
    "after",
    "before",
    "and",
    "or",
    "but",
    "not",
    "so",
    "if",
    "then",
    "than",
    "also",
    "just",
    "here",
    "there",
    "each",
    "every",
    "all",
    "both",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "only",
    "very",
    "s",
    "t",
    "slide",
    "slides",
}


def tokenize(text: str) -> set[str]:
    """Extract meaningful content tokens from text."""
    tokens = set(re.findall(r"[a-zA-Z0-9]+", text.lower()))
    return tokens - STOP_WORDS


def analyze_slide_narration(
    narration_text: str,
    slide_evidence: list[dict],
    slide_text: str = "",
    slide_notes: str = "",
) -> dict:
    """
    Analyze one slide's narration for hallucination indicators.

    Returns dict with:
    - narration_tokens: count of meaningful tokens in narration
    - grounded_tokens: tokens that appear in evidence/slide content
    - ungrounded_tokens: tokens NOT in any source
    - grounding_ratio: fraction of tokens that are grounded
    - has_image_claim: whether narration makes visual claims
    - image_claim_grounded: whether image claims cite image evidence
    """
    narr_tokens = tokenize(narration_text)
    if not narr_tokens:
        return {
            "narration_tokens": 0,
            "grounded_tokens": 0,
            "ungrounded_tokens": 0,
            "grounding_ratio": 1.0,
            "has_image_claim": False,
            "image_claim_grounded": True,
        }

    # Build source token pool from all available evidence
    source_tokens = set()

    # From evidence items
    for ev in slide_evidence:
        content = ev.get("content", "") or ""
        source_tokens |= tokenize(content)

    # From slide text and notes (always available as ground truth)
    source_tokens |= tokenize(slide_text)
    source_tokens |= tokenize(slide_notes)

    grounded = narr_tokens & source_tokens
    ungrounded = narr_tokens - source_tokens

    # Check for image claims
    narr_lower = narration_text.lower()
    has_image_claim = any(kw in narr_lower for kw in IMAGE_KEYWORDS)

    image_evidence_kinds = {
        "IMAGE_CAPTION",
        "IMAGE_OBJECTS",
        "IMAGE_ACTIONS",
        "IMAGE_TAGS",
        "IMAGE_ASSET",
        "DIAGRAM_ENTITIES",
        "DIAGRAM_INTERACTIONS",
        "DIAGRAM_SUMMARY",
    }
    has_image_evidence = any(ev.get("kind", "") in image_evidence_kinds for ev in slide_evidence)
    image_claim_grounded = not has_image_claim or has_image_evidence

    return {
        "narration_tokens": len(narr_tokens),
        "grounded_tokens": len(grounded),
        "ungrounded_tokens": len(ungrounded),
        "grounding_ratio": round(len(grounded) / len(narr_tokens), 4) if narr_tokens else 1.0,
        "has_image_claim": has_image_claim,
        "image_claim_grounded": image_claim_grounded,
    }


def analyze_condition(condition_dir: str) -> dict:
    """Analyze all files in one condition directory."""
    files = sorted(
        [d for d in os.listdir(condition_dir) if os.path.isdir(os.path.join(condition_dir, d))]
    )

    all_slides = []
    file_results = []

    for fname in files:
        fdir = os.path.join(condition_dir, fname)
        narr_path = os.path.join(fdir, "ai_narration.json")
        ev_path = os.path.join(fdir, "evidence_index.json")

        if not os.path.exists(narr_path):
            continue

        with open(narr_path) as f:
            narr_data = json.load(f)

        evidence_items = []
        if os.path.exists(ev_path):
            with open(ev_path) as f:
                ev_data = json.load(f)
            evidence_items = ev_data.get("evidence_items", [])

        entries = narr_data.get("entries", [])
        file_slides = []

        for entry in entries:
            si = entry.get("slide_index", 0)
            narr_text = entry.get("narration_text", "")

            # Get evidence for this slide
            slide_ev = [e for e in evidence_items if e.get("slide_index") == si]

            # Get slide text from evidence (TEXT_SPAN items)
            slide_text_parts = [
                e.get("content", "") for e in slide_ev if e.get("kind") == "TEXT_SPAN"
            ]
            slide_text = " ".join(slide_text_parts)

            # Get notes from SLIDE_CAPTION
            notes_parts = [
                e.get("content", "") for e in slide_ev if e.get("kind") == "SLIDE_CAPTION"
            ]
            notes = " ".join(notes_parts)

            result = analyze_slide_narration(narr_text, slide_ev, slide_text, notes)
            result["slide_index"] = si
            result["file"] = fname
            file_slides.append(result)
            all_slides.append(result)

        # Per-file aggregate
        if file_slides:
            avg_grounding = sum(s["grounding_ratio"] for s in file_slides) / len(file_slides)
            image_claims = sum(1 for s in file_slides if s["has_image_claim"])
            image_ungrounded = sum(
                1 for s in file_slides if s["has_image_claim"] and not s["image_claim_grounded"]
            )
            file_results.append(
                {
                    "file": fname,
                    "slides": len(file_slides),
                    "avg_grounding_ratio": round(avg_grounding, 4),
                    "image_claims": image_claims,
                    "image_claims_ungrounded": image_ungrounded,
                }
            )

    # Aggregate across all slides
    if not all_slides:
        return {"error": "no data"}

    total_narr_tokens = sum(s["narration_tokens"] for s in all_slides)
    total_grounded = sum(s["grounded_tokens"] for s in all_slides)
    total_ungrounded = sum(s["ungrounded_tokens"] for s in all_slides)
    total_image_claims = sum(1 for s in all_slides if s["has_image_claim"])
    total_image_ungrounded = sum(
        1 for s in all_slides if s["has_image_claim"] and not s["image_claim_grounded"]
    )

    return {
        "files_analyzed": len(file_results),
        "total_slides": len(all_slides),
        "total_narration_tokens": total_narr_tokens,
        "total_grounded_tokens": total_grounded,
        "total_ungrounded_tokens": total_ungrounded,
        "overall_grounding_ratio": round(total_grounded / total_narr_tokens, 4)
        if total_narr_tokens
        else 1.0,
        "hallucination_rate": round(total_ungrounded / total_narr_tokens * 100, 2)
        if total_narr_tokens
        else 0,
        "mean_slide_grounding": round(
            sum(s["grounding_ratio"] for s in all_slides) / len(all_slides), 4
        ),
        "image_claims_total": total_image_claims,
        "image_claims_ungrounded": total_image_ungrounded,
        "image_hallucination_rate": round(total_image_ungrounded / total_image_claims * 100, 2)
        if total_image_claims
        else 0,
        "per_file": file_results,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_hallucination.py <experiment_dir>")
        sys.exit(1)

    experiment_dir = sys.argv[1]
    conditions = ["condition_a", "condition_b", "condition_c"]
    labels = {
        "condition_a": "A: Raw GPT (no evidence, no verifier)",
        "condition_b": "B: Grounded prompt (evidence, no verifier)",
        "condition_c": "C: Full pipeline (evidence + verifier)",
    }

    results = {}
    for cond in conditions:
        cond_dir = os.path.join(experiment_dir, cond)
        if not os.path.isdir(cond_dir):
            print(f"  Skipping {cond}: directory not found")
            continue
        print(f"Analyzing {labels[cond]}...")
        results[cond] = analyze_condition(cond_dir)

    # Print comparison table
    print(f"\n{'='*80}")
    print("HALLUCINATION ANALYSIS RESULTS")
    print(f"{'='*80}\n")

    print(
        f"{'Condition':<45} {'Slides':>6} {'Ground%':>8} {'Halluc%':>8} {'ImgClaims':>10} {'ImgHalluc%':>11}"
    )
    print("-" * 90)
    for cond in conditions:
        if cond not in results:
            continue
        r = results[cond]
        print(
            f"{labels[cond]:<45} "
            f"{r['total_slides']:>6} "
            f"{r['overall_grounding_ratio']*100:>7.1f}% "
            f"{r['hallucination_rate']:>7.1f}% "
            f"{r['image_claims_total']:>10} "
            f"{r['image_hallucination_rate']:>10.1f}%"
        )

    print(f"\n{'='*80}")
    print("DETAILED METRICS")
    print(f"{'='*80}\n")
    for cond in conditions:
        if cond not in results:
            continue
        r = results[cond]
        print(f"{labels[cond]}:")
        print(f"  Files: {r['files_analyzed']}, Slides: {r['total_slides']}")
        print(f"  Narration tokens: {r['total_narration_tokens']}")
        print(
            f"  Grounded tokens: {r['total_grounded_tokens']} ({r['overall_grounding_ratio']*100:.1f}%)"
        )
        print(
            f"  Ungrounded tokens: {r['total_ungrounded_tokens']} ({r['hallucination_rate']:.1f}%)"
        )
        print(f"  Mean slide grounding: {r['mean_slide_grounding']*100:.1f}%")
        print(
            f"  Image claims: {r['image_claims_total']}, ungrounded: {r['image_claims_ungrounded']} ({r['image_hallucination_rate']:.1f}%)"
        )
        print()

    # Save results
    output_path = os.path.join(experiment_dir, "hallucination_analysis.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
