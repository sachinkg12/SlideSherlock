"""
Explain plan builder (Fig3 step 10).
Orders content for the script: intro -> clusters -> nodes -> flows -> summary.
Output: script/explain_plan.json
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

# Ordering as per Fig3: intro -> clusters -> nodes -> flows -> summary
PLAN_ORDER = ("intro", "clusters", "nodes", "flows", "summary")


def build_explain_plan(
    job_id: str,
    unified_graphs: List[Dict[str, Any]],
    rag_chunk_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build explain_plan from unified graphs (one per slide).
    Ordering: intro -> clusters -> nodes -> flows -> summary.
    If rag_chunk_ids provided (docs RAG enabled), attach to plan for context.
    """
    sections: List[Dict[str, Any]] = []
    rag_chunk_ids = rag_chunk_ids or []

    for g in unified_graphs:
        slide_index = g.get("slide_index", 0)
        nodes = g.get("nodes", [])
        edges = g.get("edges", [])
        clusters = g.get("clusters", [])

        # 1. Intro: one section per slide (overview)
        sections.append(
            {
                "section_type": "intro",
                "slide_index": slide_index,
                "entity_ids": [],
                "evidence_ids": [],
                "cluster_ids": [],
                "order_key": (slide_index, 0, "intro"),
            }
        )

        # 2. Clusters: each cluster gets a section
        for c in clusters:
            member_ids = c.get("member_node_ids", [])
            cid = c.get("cluster_id", "")
            sections.append(
                {
                    "section_type": "clusters",
                    "slide_index": slide_index,
                    "cluster_id": cid,
                    "entity_ids": member_ids,
                    "evidence_ids": [],
                    "cluster_ids": [cid] if cid else [],
                    "order_key": (slide_index, 1, "clusters", cid),
                }
            )

        # 3. Nodes: one section per node (or grouped by slide for brevity)
        for n in nodes:
            nid = n.get("node_id", "")
            sections.append(
                {
                    "section_type": "nodes",
                    "slide_index": slide_index,
                    "entity_ids": [nid],
                    "evidence_ids": [],
                    "cluster_ids": [],
                    "order_key": (slide_index, 2, "nodes", nid),
                }
            )

        # 4. Flows: each edge gets a section
        for e in edges:
            eid = e.get("edge_id", "")
            sections.append(
                {
                    "section_type": "flows",
                    "slide_index": slide_index,
                    "entity_ids": [eid],
                    "evidence_ids": [],
                    "cluster_ids": [],
                    "order_key": (slide_index, 3, "flows", eid),
                }
            )

        # 5. Summary: one section per slide at end
        sections.append(
            {
                "section_type": "summary",
                "slide_index": slide_index,
                "entity_ids": [],
                "evidence_ids": [],
                "cluster_ids": [],
                "order_key": (slide_index, 4, "summary"),
            }
        )

    # Sort by order_key so we get intro -> clusters -> nodes -> flows -> summary per slide
    sections.sort(key=lambda s: s["order_key"])
    for s in sections:
        s.pop("order_key", None)
        s.pop("cluster_id", None)  # only on clusters section; keep cluster_ids

    plan = {
        "schema_version": "1.0",
        "job_id": job_id,
        "ordering": list(PLAN_ORDER),
        "sections": sections,
        "rag_chunk_ids": rag_chunk_ids,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    return plan
