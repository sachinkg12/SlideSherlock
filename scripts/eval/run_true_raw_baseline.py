"""
True-raw GPT narration baseline (Condition A0).

This is a stronger baseline than the existing Condition A1 (the one that uses
SKIP_VERIFY=1 + NARRATE_NO_EVIDENCE=1 inside the full pipeline). A1 still
inherits post-rewrite verification and template fallback from NarrateStage,
which means many "raw" runs silently revert to the template. A0 is a clean
external baseline:

  * No evidence prompt.
  * No initial verifier.
  * No post-rewrite verifier.
  * No template fallback.
  * No quality gate affecting output.
  * Just GPT-4o-mini taking the slide's text (title + body) and writing
    a short narration paragraph per slide.

Output goes to a brand new folder so existing v2 results are not disturbed:

    hallucination_experiment_v3/condition_a0_true_raw/<deck_basename>/ai_narration.json

The output shape matches v2's ai_narration.json so the existing proxy /
permutation / table-export scripts can consume it without changes.

Usage:
    # Dry run: enumerate decks and slides, show prompt sizes, no API calls.
    python scripts/eval/run_true_raw_baseline.py \\
        --pptx-dir /path/to/30-deck-corpus \\
        --output hallucination_experiment_v3/condition_a0_true_raw \\
        --dry-run

    # Real run (requires OPENAI_API_KEY; costs API credits):
    python scripts/eval/run_true_raw_baseline.py \\
        --pptx-dir /path/to/30-deck-corpus \\
        --output hallucination_experiment_v3/condition_a0_true_raw \\
        --model gpt-4o-mini-2024-07-18 \\
        --temperature 0.7 --max-tokens 300

The model name and temperature should be pinned and recorded in the run-log
alongside the experiment artifacts so the run can be re-derived later.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

PROMPT_SYSTEM = (
    "You are narrating a slide for a video voiceover. Output two to three "
    "sentences. Do not use bullet points or headings. Speak naturally, as if "
    "presenting to an audience."
)

PROMPT_USER_TEMPLATE = (
    "Slide {slide_index} of {slide_total}.\n"
    "Slide title or first line: {title}\n"
    "Slide body text:\n{body}\n\n"
    "Write the narration for this slide."
)


def build_request_payload(
    slide_index: int,
    slide_total: int,
    title: str,
    body: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    """Pure function: build the OpenAI chat-completion payload for one slide.

    Kept separate from the HTTP call so tests can exercise it without keys.
    """
    return {
        "model": model,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "messages": [
            {"role": "system", "content": PROMPT_SYSTEM},
            {
                "role": "user",
                "content": PROMPT_USER_TEMPLATE.format(
                    slide_index=slide_index,
                    slide_total=slide_total,
                    title=title or "(no title)",
                    body=(body or "(no body text)").strip(),
                ),
            },
        ],
    }


def extract_slide_text(pptx_path: Path) -> List[Dict[str, Any]]:
    """Return [{slide_index, title, body}, ...] using python-pptx.

    Pulled into its own function so the dry-run path doesn't need an API key.
    Imported lazily so the script's `--help` doesn't fail when python-pptx
    isn't installed in the calling environment.
    """
    try:
        from pptx import Presentation  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "python-pptx is required. Install with `pip install python-pptx`."
        ) from e

    prs = Presentation(str(pptx_path))
    out: List[Dict[str, Any]] = []
    for i, slide in enumerate(prs.slides, start=1):
        title = ""
        body_parts: List[str] = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            tf = shape.text_frame
            text = "\n".join(p.text for p in tf.paragraphs if p.text)
            if not text.strip():
                continue
            if not title:
                title = text.split("\n", 1)[0].strip()
                rest = text[len(title):].lstrip("\n")
                if rest:
                    body_parts.append(rest)
            else:
                body_parts.append(text)
        out.append({
            "slide_index": i,
            "title": title,
            "body": "\n".join(body_parts).strip(),
        })
    return out


def call_openai(payload: Dict[str, Any], api_key: str, timeout: int = 60) -> Dict[str, Any]:
    """Fork-safe HTTP call to chat.completions. Imported here so tests can stub it."""
    import requests  # type: ignore
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def narrate_deck(
    pptx_path: Path,
    out_path: Path,
    model: str,
    temperature: float,
    max_tokens: int,
    dry_run: bool,
    api_key: Optional[str],
) -> Dict[str, Any]:
    slides = extract_slide_text(pptx_path)
    job_id = str(uuid.uuid4())
    entries: List[Dict[str, Any]] = []
    total = len(slides)
    for s in slides:
        payload = build_request_payload(
            slide_index=s["slide_index"],
            slide_total=total,
            title=s["title"],
            body=s["body"],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if dry_run:
            text = "(dry-run) " + (s["title"] or "")[:120]
        else:
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is required (or run with --dry-run).")
            resp = call_openai(payload, api_key)
            text = resp["choices"][0]["message"]["content"].strip()
        entries.append({
            "slide_index": s["slide_index"],
            "narration_text": text,
            "source_used": "true_raw_gpt",
            "word_count": len(text.split()),
        })

    result = {
        "schema_version": "1.0",
        "job_id": job_id,
        "condition": "A0_true_raw_gpt",
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "slide_count": total,
        "ai_rewritten": (not dry_run) and total,
        "entries": entries,
        "deck_basename": pptx_path.stem,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pptx-dir", required=True, type=Path)
    p.add_argument(
        "--output", required=True, type=Path,
        help="e.g. hallucination_experiment_v3/condition_a0_true_raw",
    )
    p.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--max-tokens", type=int, default=300)
    p.add_argument("--limit", type=int, default=None,
                   help="Process only the first N decks (for cost-bounded testing)")
    p.add_argument("--dry-run", action="store_true",
                   help="No API calls; verify enumeration and prompt construction only.")
    args = p.parse_args()

    if not args.pptx_dir.is_dir():
        print(f"pptx-dir not found: {args.pptx_dir}", file=sys.stderr)
        return 2
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        print(
            "OPENAI_API_KEY is required for a real run. "
            "Re-run with --dry-run to verify enumeration only.",
            file=sys.stderr,
        )
        return 2

    decks = sorted(p for p in args.pptx_dir.iterdir() if p.suffix.lower() == ".pptx")
    if args.limit:
        decks = decks[: args.limit]
    if not decks:
        print(f"no .pptx files found under {args.pptx_dir}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    n_done = 0
    for d in decks:
        out_path = args.output / d.stem / "ai_narration.json"
        try:
            narrate_deck(
                pptx_path=d,
                out_path=out_path,
                model=args.model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                dry_run=args.dry_run,
                api_key=api_key,
            )
            n_done += 1
            print(f"OK {d.stem}")
        except Exception as e:
            print(f"FAIL {d.stem}: {e}", file=sys.stderr)

    print(json.dumps({
        "decks_processed": n_done,
        "decks_total": len(decks),
        "output_root": str(args.output),
        "dry_run": args.dry_run,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
