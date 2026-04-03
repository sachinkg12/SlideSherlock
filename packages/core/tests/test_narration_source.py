"""
Unit tests for narration source selection (Fig3 step 14).
- Primary: Speaker notes (if present and long enough).
- Secondary: Slide text + diagram summary (G_unified).
- Optional: LLM/template when notes missing or too short.
- source_used: user_audio | notes | llm | mixed | slide_and_graph.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from narration_source import (
    get_narration_text_for_slide,
    get_narration_with_smart_fallback,
    build_narration_per_slide,
    SOURCE_NOTES,
    SOURCE_SLIDE_AND_GRAPH,
    SOURCE_MIXED,
    SOURCE_LLM,
    SOURCE_TEMPLATE,
    SOURCE_USER_AUDIO,
)


def test_notes_primary_when_long_enough():
    """When notes have >= MIN_NOTES_WORDS, use notes and source_used=notes."""
    notes = "These are speaker notes with enough words for the slide."
    slide_text = "Slide title"
    text, source = get_narration_text_for_slide(1, notes, slide_text, None)
    assert source == SOURCE_NOTES
    assert text == notes
    assert "enough words" in text


def test_notes_ignored_when_too_short():
    """When notes have < MIN_NOTES_WORDS, fall back to slide/graph or mixed."""
    notes = "Short."
    slide_text = "Slide content with several words here."
    text, source = get_narration_text_for_slide(1, notes, slide_text, None)
    assert source in (SOURCE_SLIDE_AND_GRAPH, SOURCE_MIXED)
    assert "Slide content" in text or "Short." in text


def test_slide_and_graph_when_no_notes():
    """When no notes, use slide text (or diagram summary); source_used=slide_and_graph."""
    notes = ""
    slide_text = "Introduction to the architecture."
    graph = {"nodes": [{"label_text": "API"}], "edges": [], "clusters": []}
    text, source = get_narration_text_for_slide(1, notes, slide_text, graph)
    assert source == SOURCE_SLIDE_AND_GRAPH
    assert "Introduction" in text


def test_diagram_summary_from_graph():
    """Diagram summary includes node labels, edge count, cluster count."""
    notes = ""
    slide_text = ""
    graph = {
        "nodes": [{"label_text": "A"}, {"label_text": "B"}],
        "edges": [{"edge_id": "e1"}],
        "clusters": [{"cluster_id": "c1"}],
    }
    text, source = get_narration_text_for_slide(1, notes, slide_text, graph)
    assert source == SOURCE_SLIDE_AND_GRAPH
    assert "A" in text or "B" in text
    assert "1 connection" in text or "connection" in text
    assert "1 group" in text or "group" in text


def test_mixed_when_short_notes_plus_fallback():
    """When notes are short but present and fallback has enough words, combine -> mixed."""
    notes = "Hi."
    slide_text = "Detailed slide content with multiple words for narration."
    graph = {}
    text, source = get_narration_text_for_slide(1, notes, slide_text, graph)
    assert source == SOURCE_MIXED
    assert "Hi." in text
    assert "Detailed" in text


def test_llm_template_when_no_notes_no_slide():
    """When no notes and no slide text, use diagram summary or template; source_used=slide_and_graph or llm."""
    notes = ""
    slide_text = ""
    graph = {"nodes": [], "edges": [], "clusters": []}
    text, source = get_narration_text_for_slide(1, notes, slide_text, graph)
    assert source in (SOURCE_LLM, SOURCE_SLIDE_AND_GRAPH)
    assert "slide 1" in text.lower() or "Diagram" in text or "diagram" in text


def test_llm_callback_used_when_provided():
    """When llm_narration_fn provided and notes/slide insufficient, use LLM output."""
    notes = ""
    slide_text = "x y"  # too short for slide_and_graph
    graph = {}

    def fake_llm(slide_index: int, slide_text: str, diagram_summary: str, notes: str) -> str:
        return "Generated narration for this slide."

    text, source = get_narration_text_for_slide(1, notes, slide_text, graph, llm_narration_fn=fake_llm)
    assert source == SOURCE_LLM
    assert "Generated narration" in text


def test_llm_callback_fallback_on_exception():
    """When llm_narration_fn raises, fall back to template."""
    notes = ""
    slide_text = "a b"
    graph = {}

    def failing_llm(*args, **kwargs):
        raise RuntimeError("LLM error")

    text, source = get_narration_text_for_slide(1, notes, slide_text, graph, llm_narration_fn=failing_llm)
    assert source == SOURCE_LLM
    assert "slide 1" in text.lower()


def test_build_narration_per_slide_structure():
    """build_narration_per_slide returns list of entries with slide_index, narration_text, source_used, word_count."""
    slides_notes_and_text = [
        ("Speaker notes with enough words for slide one.", "Slide 1 title"),
        ("", "Slide two content with several words."),
    ]
    unified_graphs = {
        1: {"nodes": [{"label_text": "A"}], "edges": [], "clusters": []},
        2: {"nodes": [], "edges": [], "clusters": []},
    }
    entries = build_narration_per_slide(2, slides_notes_and_text, unified_graphs, llm_narration_fn=None)
    assert len(entries) == 2
    for i, entry in enumerate(entries):
        assert entry["slide_index"] == i + 1
        assert "narration_text" in entry
        assert entry["source_used"] in (SOURCE_NOTES, SOURCE_SLIDE_AND_GRAPH, SOURCE_MIXED, SOURCE_LLM)
        assert isinstance(entry["word_count"], int)
        assert entry["word_count"] >= 0


def test_build_narration_per_slide_sources():
    """First slide uses notes, second uses slide_and_graph or template."""
    slides_notes_and_text = [
        ("These are valid speaker notes with sufficient word count.", "Title"),
        ("", "Second slide has enough text for narration."),
    ]
    unified_graphs = {1: {}, 2: {}}
    entries = build_narration_per_slide(2, slides_notes_and_text, unified_graphs, llm_narration_fn=None)
    assert entries[0]["source_used"] == SOURCE_NOTES
    assert entries[1]["source_used"] in (SOURCE_SLIDE_AND_GRAPH, SOURCE_MIXED, SOURCE_LLM)


def test_empty_slides_use_template():
    """When slide_count > len(slides_notes_and_text), missing slides get (\"\", \"\") -> template."""
    slides_notes_and_text = [("One two three four five six.", "Text")]  # slide 1: 6 words -> notes
    entries = build_narration_per_slide(3, slides_notes_and_text, {}, llm_narration_fn=None)
    assert len(entries) == 3
    assert entries[0]["source_used"] == SOURCE_NOTES
    assert entries[1]["source_used"] in (SOURCE_LLM, SOURCE_SLIDE_AND_GRAPH)
    assert entries[2]["source_used"] in (SOURCE_LLM, SOURCE_SLIDE_AND_GRAPH)
    assert "slide 2" in entries[1]["narration_text"].lower() or "slide 3" in entries[2]["narration_text"].lower() or "Diagram" in entries[1]["narration_text"]


def test_smart_fallback_uses_template_when_no_llm():
    """get_narration_with_smart_fallback uses template when llm_narration_fn is None."""
    notes = ""
    slide_text = "Some diagram"
    graph = {"nodes": [{"node_id": "n1", "label_text": "A"}], "edges": [], "clusters": []}
    blueprint = {
        "slide_index": 1,
        "slide_type": "diagram_process",
        "template_narration": "This slide shows a diagram with key elements: A.",
        "llm_context": {},
    }
    text, source, eids, evids = get_narration_with_smart_fallback(
        1, notes, slide_text, graph, blueprint, {}, llm_narration_fn=None
    )
    assert source == SOURCE_TEMPLATE
    assert "diagram" in text.lower() or "A" in text
    assert eids is None
    assert evids is None


def test_smart_fallback_uses_template_when_llm_ungrounded():
    """When LLM returns content without valid entity_ids/evidence_ids, fall back to template."""
    notes = ""
    slide_text = "Diagram"
    graph = {"nodes": [{"node_id": "n1", "label_text": "A"}], "edges": [], "clusters": []}
    blueprint = {
        "slide_index": 1,
        "template_narration": "Template: diagram with A.",
        "llm_context": {"evidence_ids": ["ev1"]},
    }
    evidence_by_id = {"ev1": {"evidence_id": "ev1", "content": "A"}}

    def ungrounded_llm(bp):
        return ("Hallucinated text.", [], [])  # empty entity_ids, evidence_ids -> fails grounding

    text, source, _, _ = get_narration_with_smart_fallback(
        1, notes, slide_text, graph, blueprint, evidence_by_id, llm_narration_fn=ungrounded_llm
    )
    assert source == SOURCE_TEMPLATE
    assert "Template" in text


def test_smart_fallback_uses_llm_when_grounded():
    """When LLM returns valid entity_ids/evidence_ids, use LLM output."""
    notes = ""
    slide_text = "Diagram"
    graph = {
        "nodes": [{"node_id": "n1", "label_text": "A"}],
        "edges": [],
        "clusters": [],
    }
    blueprint = {"slide_index": 1, "template_narration": "Template.", "llm_context": {}}
    evidence_by_id = {"ev1": {"evidence_id": "ev1", "content": "A"}}

    def grounded_llm(bp):
        return ("Grounded narration about A.", ["n1"], ["ev1"])

    text, source, eids, evids = get_narration_with_smart_fallback(
        1, notes, slide_text, graph, blueprint, evidence_by_id, llm_narration_fn=grounded_llm
    )
    assert source == SOURCE_LLM
    assert "Grounded" in text
    assert eids == ["n1"]
    assert evids == ["ev1"]


def test_build_narration_per_slide_with_blueprints_uses_template():
    """build_narration_per_slide with evidence_index uses blueprint template when no LLM."""
    slides_notes_and_text = [("", "Diagram slide with nodes"), ("", "")]
    unified_graphs = {
        1: {"nodes": [{"node_id": "n1", "label_text": "A"}], "edges": [], "clusters": []},
        2: {"nodes": [], "edges": [], "clusters": []},
    }
    evidence_index = {"evidence_items": [{"evidence_id": "ev1", "slide_index": 1, "content": "A"}]}
    entries = build_narration_per_slide(
        2, slides_notes_and_text, unified_graphs,
        evidence_index=evidence_index,
        llm_smart_narration_fn=None,
    )
    assert len(entries) == 2
    assert entries[0]["source_used"] in (SOURCE_TEMPLATE, SOURCE_SLIDE_AND_GRAPH)
    assert entries[1]["source_used"] in (SOURCE_TEMPLATE, SOURCE_SLIDE_AND_GRAPH)
