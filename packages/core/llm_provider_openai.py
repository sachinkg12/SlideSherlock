"""
OpenAI LLM provider: generates natural, intent-based narration using GPT-4o.

Instead of reading slide text verbatim, this provider:
1. Understands the INTENT of each slide from evidence (text, notes, images, graph)
2. Explains concepts naturally, as a knowledgeable presenter would
3. Maintains evidence grounding — every claim traces to evidence_ids

Usage:
    Set OPENAI_API_KEY env var. The pipeline selects this provider automatically
    when the key is present and LLM_PROVIDER is not set to "stub".
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from llm_provider import LLMProvider


class OpenAILLMProvider(LLMProvider):
    """
    GPT-4o powered narration: explains slides like a human presenter.

    For each segment, builds a prompt with:
    - Slide text and speaker notes (ground truth)
    - Evidence items (what was extracted from the PPTX)
    - Graph structure (entities, relationships)
    - Image/diagram descriptions (from vision pipeline)

    Then asks GPT-4o to explain the slide's INTENT, not just read its content.
    """

    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None):
        self._api_key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        self._model = model

    def _chat(self, messages: list, max_tokens: int = 200, temperature: float = 0.7) -> str:
        """Call OpenAI chat completions using requests (fork-safe, no httpx/asyncio)."""
        import requests
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data["choices"][0]["message"]["content"] or "").strip()

    def generate_segment(
        self,
        section: Dict[str, Any],
        graph: Dict[str, Any],
        evidence_ids: List[str],
        entity_ids: List[str],
        rag_snippets: Optional[List[str]] = None,
        context_bundle: Optional[Dict[str, Any]] = None,
    ) -> str:
        slide_index = section.get("slide_index", 0)
        section_type = section.get("section_type", "")

        # Build context from all available sources
        parts = []

        # Slide text
        slide_text = ""
        notes = ""
        if context_bundle:
            slide_text = (context_bundle.get("slide_text") or "").strip()
            notes = (context_bundle.get("notes") or "").strip()
            graph_summary = (context_bundle.get("graph_summary") or "").strip()

            if slide_text:
                parts.append(f"SLIDE TEXT:\n{slide_text[:500]}")
            if notes:
                parts.append(f"SPEAKER NOTES:\n{notes[:500]}")
            if graph_summary:
                parts.append(f"GRAPH STRUCTURE:\n{graph_summary[:300]}")

            # Image/diagram evidence
            image_items = context_bundle.get("image_evidence_items") or []
            for item in image_items[:3]:
                kind = item.get("kind", "")
                content = (item.get("content") or "").strip()
                conf = item.get("confidence", 0)
                if content:
                    parts.append(f"IMAGE EVIDENCE ({kind}, confidence={conf:.2f}):\n{content[:300]}")

        # Graph nodes and edges
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        if nodes:
            node_labels = [n.get("label_text", "") for n in nodes[:10] if n.get("label_text")]
            if node_labels:
                parts.append(f"KEY ELEMENTS: {', '.join(node_labels)}")
        if edges:
            edge_descs = []
            node_by_id = {n["node_id"]: n for n in nodes}
            for e in edges[:5]:
                src = node_by_id.get(e.get("src_node_id"), {})
                dst = node_by_id.get(e.get("dst_node_id"), {})
                src_l = src.get("label_text", "?")
                dst_l = dst.get("label_text", "?")
                edge_descs.append(f"{src_l} → {dst_l}")
            if edge_descs:
                parts.append(f"RELATIONSHIPS: {'; '.join(edge_descs)}")

        context = "\n\n".join(parts) if parts else f"Slide {slide_index} with {len(nodes)} elements."

        system_prompt = (
            "You are a professional presenter narrating a slideshow. "
            "Your job is to EXPLAIN the intent and meaning of each slide — not read it word-for-word. "
            "Speak naturally as if presenting to a live audience. "
            "Be concise (2-4 sentences). Do not say 'this slide shows' repeatedly. "
            "If the slide has speaker notes, use them as the basis but rephrase naturally. "
            "If there are diagrams or images, explain what they illustrate and why it matters. "
            "Never invent facts — only explain what the evidence supports."
        )

        if section_type == "summary":
            user_prompt = (
                f"This is the closing segment for slide {slide_index}. "
                f"Provide a brief transition sentence (1 sentence max).\n\n{context}"
            )
        elif section_type == "intro":
            user_prompt = (
                f"This is slide {slide_index}. Introduce what this slide covers.\n\n{context}"
            )
        else:
            user_prompt = (
                f"Explain slide {slide_index}. Section type: {section_type}.\n\n{context}"
            )

        try:
            text = self._chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ])
            if text:
                return text
        except Exception as e:
            print(f"  OpenAI LLM fallback for slide {slide_index}: {e}")

        # Fallback to notes or basic template
        if notes:
            return notes
        return f"This slide presents information about {slide_text[:100]}." if slide_text else f"Slide {slide_index}."

    def generate_narration(self, blueprint: Dict[str, Any]) -> Optional[Tuple[str, List[str], List[str]]]:
        """
        Smart narration from blueprint — used by audio_prepare for per-slide narration.
        Returns (narration_text, entity_ids, evidence_ids) or None.
        """
        slide_index = blueprint.get("slide_index", 0)
        slide_type = blueprint.get("slide_type", "content")
        template = (blueprint.get("template_narration") or "").strip()
        llm_ctx = blueprint.get("llm_context") or {}

        nodes = llm_ctx.get("nodes", [])
        edges = llm_ctx.get("edges", [])
        evidence_ids = llm_ctx.get("evidence_ids", [])
        notes = (llm_ctx.get("notes") or "").strip()
        slide_text = (llm_ctx.get("slide_text") or "").strip()

        parts = []
        if slide_text:
            parts.append(f"SLIDE TEXT:\n{slide_text[:500]}")
        if notes:
            parts.append(f"SPEAKER NOTES:\n{notes[:500]}")
        if nodes:
            labels = [n.get("label_text", "") for n in nodes[:10] if n.get("label_text")]
            if labels:
                parts.append(f"KEY ELEMENTS: {', '.join(labels)}")

        context = "\n\n".join(parts) if parts else f"Slide {slide_index}"

        system_prompt = (
            "You are narrating a presentation. Explain what this slide conveys in 2-4 natural sentences. "
            "Don't read verbatim — explain the meaning and significance. "
            "Be conversational but professional."
        )

        try:
            text = self._chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Narrate slide {slide_index} ({slide_type}):\n\n{context}"},
            ])
            if text:
                entity_ids = [n["node_id"] for n in nodes[:5]] if nodes else []
                return text, entity_ids, evidence_ids
        except Exception as e:
            print(f"  OpenAI narration fallback for slide {slide_index}: {e}")

        return None
