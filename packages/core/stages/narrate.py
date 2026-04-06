"""
NarrateStage: AI-powered narration rewrite (per-variant).

Runs AFTER verify, BEFORE audio. Only activates when:
  - Job config_json has llm_provider=openai
  - OPENAI_API_KEY is set in the environment

Takes the evidence-grounded verified script and rewrites each slide's
narration to sound like a human presenter explaining the slide's intent.
Preserves all factual claims; changes only tone and delivery.

Output: overrides ctx.narration_entries_override so the audio stage
uses the AI-rewritten text for TTS.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import PipelineContext, StageResult


def _log(msg: str):
    print(f"  [NarrateStage] {msg}")


class NarrateStage:
    name = "narrate"

    def run(self, ctx: "PipelineContext") -> "StageResult":
        from pipeline import StageResult

        # ---- Gate checks with verbose logging ----
        api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        is_ai = ctx.config.get("ai_narration", False)

        _log(
            f"ai_narration={is_ai}, api_key={'set (' + str(len(api_key)) + ' chars)' if api_key else 'UNSET'}"
        )
        _log(f"config keys: {list(ctx.config.keys())}")

        if not is_ai:
            _log("SKIPPED: ai_narration not set in ctx.config")
            return StageResult(status="skipped", metrics={"reason": "AI narration not enabled"})
        if not api_key:
            _log("SKIPPED: OPENAI_API_KEY not set in environment")
            return StageResult(status="skipped", metrics={"reason": "no API key"})

        variant = ctx.variant or {}
        variant_id = variant.get("id", "en")
        verified_script = ctx.verified_script

        _log(f"variant={variant_id}, verified_script={'present' if verified_script else 'MISSING'}")
        if verified_script:
            seg_count = len(verified_script.get("segments", []))
            _log(f"verified_script has {seg_count} segments")

        if not verified_script:
            _log("SKIPPED: no verified script")
            return StageResult(status="skipped", metrics={"reason": "no verified script"})

        minio_client = ctx.minio_client
        job_id = ctx.job_id
        slide_count = ctx.slide_count
        evidence_index = ctx.evidence_index
        unified_by_slide = ctx.unified_by_slide

        _log(
            f"slide_count={slide_count}, evidence_items={len(evidence_index.get('evidence_items', [])) if evidence_index else 0}"
        )
        _log(f"slides_notes_and_text length={len(ctx.slides_notes_and_text)}")

        # ---- Gather all context per slide ----
        slides_context = []
        for si in range(1, slide_count + 1):
            ctx_parts = {}

            if si - 1 < len(ctx.slides_notes_and_text):
                notes_raw, text_raw = ctx.slides_notes_and_text[si - 1]
                ctx_parts["notes"] = (notes_raw or "").strip()[:600]
                ctx_parts["slide_text"] = (text_raw or "").strip()[:600]

            segments = [
                s for s in verified_script.get("segments", []) if s.get("slide_index") == si
            ]
            template_narration = " ".join(s.get("text", "") for s in segments).strip()
            ctx_parts["template_narration"] = template_narration[:800]

            evidence_items = evidence_index.get("evidence_items", []) if evidence_index else []
            slide_evidence = [e for e in evidence_items if e.get("slide_index") == si]
            evidence_texts = []
            for ev in slide_evidence[:5]:
                kind = ev.get("kind", "")
                content = (ev.get("content") or "").strip()
                if content and kind not in ("TEXT_SPAN",):
                    evidence_texts.append(f"{kind}: {content[:200]}")
            ctx_parts["evidence"] = evidence_texts

            graph = unified_by_slide.get(si, {})
            nodes = graph.get("nodes", [])
            node_labels = [n.get("label_text", "") for n in nodes[:8] if n.get("label_text")]
            if node_labels:
                ctx_parts["graph_elements"] = node_labels

            slides_context.append(ctx_parts)

        _log(f"Built context for {len(slides_context)} slides")
        for i, sc in enumerate(slides_context[:3], 1):
            _log(
                f"  Slide {i}: notes={len(sc.get('notes', ''))}chars, text={len(sc.get('slide_text', ''))}chars, template={len(sc.get('template_narration', ''))}chars, evidence={len(sc.get('evidence', []))} items"
            )

        # ---- Call GPT-4o for each slide ----
        import requests

        rewritten_entries = []
        success_count = 0

        system_prompt = (
            "You are a professional presenter narrating a slideshow to a live audience. "
            "For each slide, you receive:\n"
            "- TEMPLATE NARRATION: an evidence-grounded but robotic script\n"
            "- SPEAKER NOTES: the presenter's own notes (if available)\n"
            "- SLIDE TEXT: the visible text on the slide\n"
            "- EVIDENCE: extracted facts (image captions, diagram descriptions)\n"
            "- KEY ELEMENTS: entities/concepts from the knowledge graph\n\n"
            "Your task:\n"
            "1. Understand the INTENT and MESSAGE of the slide — what is it trying to communicate?\n"
            "2. Explain it naturally, as if presenting to colleagues — not reading bullet points\n"
            "3. If speaker notes exist, use them as the primary guide but rephrase for spoken delivery\n"
            "4. Connect ideas — explain WHY things matter, not just WHAT they are\n"
            "5. Keep ALL factual claims from the template — do NOT invent new facts\n"
            "6. Be concise: 2-5 natural sentences. No filler words.\n"
            "7. Vary your openings — don't start every slide with 'This slide' or 'Here we see'\n"
            "8. Output ONLY the narration text. No labels, no slide numbers, no meta-commentary."
        )

        # Build prompts for each slide
        slide_prompts = []
        for si, sc in enumerate(slides_context, 1):
            user_parts = []
            if sc.get("template_narration"):
                user_parts.append(f"TEMPLATE NARRATION:\n{sc['template_narration']}")
            if sc.get("notes"):
                user_parts.append(f"SPEAKER NOTES:\n{sc['notes']}")
            if sc.get("slide_text"):
                user_parts.append(f"SLIDE TEXT:\n{sc['slide_text']}")
            if sc.get("evidence"):
                user_parts.append("EVIDENCE:\n" + "\n".join(sc["evidence"]))
            if sc.get("graph_elements"):
                user_parts.append(f"KEY ELEMENTS: {', '.join(sc['graph_elements'])}")

            if not user_parts:
                slide_prompts.append((si, sc, None))
                continue

            user_prompt = f"Narrate slide {si} of {slide_count}:\n\n" + "\n\n".join(user_parts)
            slide_prompts.append((si, sc, user_prompt))

        # Parallel GPT calls with bounded concurrency to avoid rate limits
        from concurrent.futures import ThreadPoolExecutor, as_completed
        max_parallel = int(os.environ.get("NARRATE_PARALLEL", "5"))
        model = os.environ.get("NARRATE_MODEL", "gpt-4o-mini")
        _log(f"Starting parallel GPT-{model} calls for {slide_count} slides ({max_parallel} concurrent)...")

        def call_gpt(slide_idx: int, prompt: str) -> tuple:
            """Returns (slide_idx, text_or_None, error_msg)."""
            for attempt in range(3):
                try:
                    resp = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt},
                            ],
                            "max_tokens": 300,
                            "temperature": 0.7,
                        },
                        timeout=30,
                    )
                    if resp.status_code == 429:
                        wait = min(2 ** (attempt + 1), 30)
                        time.sleep(wait)
                        continue
                    if resp.status_code != 200:
                        if attempt < 2:
                            time.sleep(2)
                            continue
                        return (slide_idx, None, f"HTTP {resp.status_code}")
                    text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
                    if text and len(text) > 10:
                        return (slide_idx, text, None)
                    if attempt < 2:
                        continue
                    return (slide_idx, None, "response too short")
                except Exception as e:
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    return (slide_idx, None, str(e)[:80])
            return (slide_idx, None, "max retries exhausted")

        results_by_slide: Dict[int, tuple] = {}

        # Handle slides without context (instant fallback)
        for si, sc, prompt in slide_prompts:
            if prompt is None:
                results_by_slide[si] = (None, "no context")

        # Submit all GPT calls in parallel
        callable_prompts = [(si, sc, p) for si, sc, p in slide_prompts if p is not None]
        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            futures = {pool.submit(call_gpt, si, p): (si, sc) for si, sc, p in callable_prompts}
            for future in as_completed(futures):
                si, sc = futures[future]
                try:
                    _, text, err = future.result()
                    results_by_slide[si] = (text, err)
                    if text:
                        _log(f"  Slide {si}: OK ({len(text)} chars)")
                    else:
                        _log(f"  Slide {si}: FAILED ({err})")
                except Exception as e:
                    results_by_slide[si] = (None, str(e)[:80])
                    _log(f"  Slide {si}: EXCEPTION ({e})")

        # Build output entries in slide order
        for si, sc, _ in slide_prompts:
            text, err = results_by_slide.get(si, (None, "missing"))
            if text:
                rewritten_entries.append(
                    {
                        "slide_index": si,
                        "narration_text": text,
                        "source_used": "ai_narrate",
                        "word_count": len(text.split()),
                    }
                )
                success_count += 1
            else:
                fallback = sc.get("template_narration") or sc.get("notes") or f"Slide {si}."
                rewritten_entries.append(
                    {
                        "slide_index": si,
                        "narration_text": fallback,
                        "source_used": "template_fallback",
                        "word_count": len(fallback.split()),
                    }
                )

        # ---- Set override for audio stage ----
        _log(f"Setting narration_entries_override: {len(rewritten_entries)} entries")
        ctx.narration_entries_override = rewritten_entries

        # Save to MinIO for inspection
        script_prefix = ctx.script_prefix
        narrate_path = f"{script_prefix}ai_narration.json"
        narrate_payload = {
            "job_id": job_id,
            "variant_id": variant_id,
            "slide_count": slide_count,
            "ai_rewritten": success_count,
            "entries": rewritten_entries,
        }
        minio_client.put(
            narrate_path,
            json.dumps(narrate_payload, indent=2).encode("utf-8"),
            "application/json",
        )
        _log(f"Saved ai_narration.json to {narrate_path}")

        _log(f"DONE: {success_count}/{slide_count} slides rewritten by AI")

        return StageResult(
            status="ok",
            metrics={
                "slides_rewritten": success_count,
                "slides_total": slide_count,
                "slides_fallback": slide_count - success_count,
            },
        )
