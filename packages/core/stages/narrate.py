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
from typing import Any, Dict, List, TYPE_CHECKING

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

        _log(f"ai_narration={is_ai}, api_key={'set (' + str(len(api_key)) + ' chars)' if api_key else 'UNSET'}")
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

        _log(f"slide_count={slide_count}, evidence_items={len(evidence_index.get('evidence_items', [])) if evidence_index else 0}")
        _log(f"slides_notes_and_text length={len(ctx.slides_notes_and_text)}")

        # ---- Gather all context per slide ----
        slides_context = []
        for si in range(1, slide_count + 1):
            ctx_parts = {}

            if si - 1 < len(ctx.slides_notes_and_text):
                notes_raw, text_raw = ctx.slides_notes_and_text[si - 1]
                ctx_parts["notes"] = (notes_raw or "").strip()[:600]
                ctx_parts["slide_text"] = (text_raw or "").strip()[:600]

            segments = [s for s in verified_script.get("segments", []) if s.get("slide_index") == si]
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
            _log(f"  Slide {i}: notes={len(sc.get('notes', ''))}chars, text={len(sc.get('slide_text', ''))}chars, template={len(sc.get('template_narration', ''))}chars, evidence={len(sc.get('evidence', []))} items")

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

        _log(f"Starting GPT-4o calls for {slide_count} slides...")

        for si, sc in enumerate(slides_context, 1):
            user_parts = []
            if sc.get("template_narration"):
                user_parts.append(f"TEMPLATE NARRATION:\n{sc['template_narration']}")
            if sc.get("notes"):
                user_parts.append(f"SPEAKER NOTES:\n{sc['notes']}")
            if sc.get("slide_text"):
                user_parts.append(f"SLIDE TEXT:\n{sc['slide_text']}")
            if sc.get("evidence"):
                user_parts.append(f"EVIDENCE:\n" + "\n".join(sc["evidence"]))
            if sc.get("graph_elements"):
                user_parts.append(f"KEY ELEMENTS: {', '.join(sc['graph_elements'])}")

            if not user_parts:
                _log(f"  Slide {si}: NO context available, using fallback")
                rewritten_entries.append({
                    "slide_index": si,
                    "narration_text": f"Slide {si}.",
                    "source_used": "fallback",
                    "word_count": 2,
                })
                continue

            user_prompt = f"Narrate slide {si} of {slide_count}:\n\n" + "\n\n".join(user_parts)

            _log(f"  Slide {si}: sending to GPT-4o ({len(user_prompt)} chars prompt)...")

            # Retry with exponential backoff for rate limits
            max_retries = 4
            slide_done = False
            for attempt in range(max_retries):
                try:
                    if si > 1 or attempt > 0:
                        wait = 1.0 + attempt * 2.0
                        _log(f"  Slide {si}: waiting {wait:.1f}s before attempt {attempt + 1}")
                        time.sleep(wait)

                    resp = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "gpt-4o",
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "max_tokens": 300,
                            "temperature": 0.7,
                        },
                        timeout=30,
                    )

                    _log(f"  Slide {si}: HTTP {resp.status_code} (attempt {attempt + 1})")

                    if resp.status_code == 429:
                        wait = min(2 ** (attempt + 2), 60)
                        _log(f"  Slide {si}: RATE LIMITED (429), backing off {wait}s")
                        time.sleep(wait)
                        continue

                    if resp.status_code != 200:
                        _log(f"  Slide {si}: ERROR {resp.status_code}: {resp.text[:200]}")
                        continue

                    resp_json = resp.json()
                    new_text = (resp_json["choices"][0]["message"]["content"] or "").strip()
                    _log(f"  Slide {si}: GOT {len(new_text)} chars: '{new_text[:80]}...'")

                    if new_text and len(new_text) > 10:
                        rewritten_entries.append({
                            "slide_index": si,
                            "narration_text": new_text,
                            "source_used": "ai_narrate",
                            "word_count": len(new_text.split()),
                        })
                        success_count += 1
                        slide_done = True
                        break
                    else:
                        _log(f"  Slide {si}: response too short, retrying...")

                except Exception as e:
                    _log(f"  Slide {si}: EXCEPTION on attempt {attempt + 1}: {e}")
                    _log(f"  {traceback.format_exc()}")
                    if attempt < max_retries - 1:
                        continue
                    break

            if not slide_done:
                fallback = sc.get("template_narration") or sc.get("notes") or f"Slide {si}."
                _log(f"  Slide {si}: ALL ATTEMPTS FAILED, using fallback ({len(fallback)} chars)")
                rewritten_entries.append({
                    "slide_index": si,
                    "narration_text": fallback,
                    "source_used": "template_fallback",
                    "word_count": len(fallback.split()),
                })

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
