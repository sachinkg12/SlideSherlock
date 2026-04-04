"""
AI narration rewriter: transforms evidence-grounded template narration into
natural presenter-style delivery using GPT-4o.

This is a post-verification pass — the input is already verified against
the evidence index. The rewriter preserves all factual content but changes
tone, flow, and phrasing to sound like a human presenter.

Only runs when:
  1. User toggled "AI Narration" in the UI
  2. OPENAI_API_KEY is available
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple


def rewrite_narration_for_delivery(
    entries: List[Dict[str, Any]],
    slides_notes_and_text: List[Tuple[str, str]],
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Rewrite narration entries for natural delivery.

    Takes evidence-grounded narration entries and rewrites each one through
    GPT-4o to sound like a human presenter explaining the slide's intent.

    Args:
        entries: List of dicts with slide_index, narration_text, etc.
        slides_notes_and_text: Per-slide (notes, slide_text) tuples for context.
        api_key: OpenAI API key. If None, reads from OPENAI_API_KEY env var.

    Returns:
        Updated entries list with rewritten narration_text.
    """
    import requests

    key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key:
        print("  AI rewrite skipped: no OPENAI_API_KEY")
        return entries

    print(f"  AI narration rewrite: {len(entries)} slides...")

    system_prompt = (
        "You are rewriting presentation narration for natural spoken delivery. "
        "You receive the ORIGINAL narration (evidence-grounded, may sound robotic) "
        "and the SLIDE CONTEXT (notes and text from the slide).\n\n"
        "Your task:\n"
        "1. Rewrite the narration so it sounds like a knowledgeable presenter "
        "explaining the slide to a live audience\n"
        "2. Keep ALL factual claims from the original — do not add new facts\n"
        "3. Make it conversational but professional\n"
        "4. Use natural transitions (avoid 'This slide shows...' repeatedly)\n"
        "5. If the original is just 'Slide N' or very short, expand it using "
        "the slide context to create a meaningful explanation\n"
        "6. Keep it concise: 2-5 sentences per slide\n"
        "7. Do NOT add greetings, sign-offs, or meta-commentary\n"
        "8. Output ONLY the rewritten narration text, nothing else"
    )

    rewritten = []
    for entry in entries:
        slide_idx = entry.get("slide_index", 1)
        original_text = (entry.get("narration_text") or "").strip()

        # Get slide context
        notes = ""
        slide_text = ""
        if slide_idx - 1 < len(slides_notes_and_text):
            notes, slide_text = slides_notes_and_text[slide_idx - 1]

        context_parts = []
        if original_text:
            context_parts.append(f"ORIGINAL NARRATION:\n{original_text}")
        if notes and notes.strip():
            context_parts.append(f"SPEAKER NOTES:\n{notes.strip()[:500]}")
        if slide_text and slide_text.strip():
            context_parts.append(f"SLIDE TEXT:\n{slide_text.strip()[:500]}")

        if not context_parts:
            rewritten.append(entry)
            continue

        user_prompt = f"Rewrite the narration for slide {slide_idx}:\n\n" + "\n\n".join(context_parts)

        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 250,
                    "temperature": 0.7,
                },
                timeout=30,
            )
            resp.raise_for_status()
            new_text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
            if new_text and len(new_text) > 10:
                new_entry = {**entry, "narration_text": new_text, "source_used": "ai_rewrite"}
                new_entry["word_count"] = len(new_text.split())
                rewritten.append(new_entry)
                continue
        except Exception as e:
            print(f"  AI rewrite failed for slide {slide_idx}: {e}")

        # Keep original on failure
        rewritten.append(entry)

    ai_count = sum(1 for e in rewritten if e.get("source_used") == "ai_rewrite")
    print(f"  AI narration rewrite: {ai_count}/{len(entries)} slides rewritten")
    return rewritten
