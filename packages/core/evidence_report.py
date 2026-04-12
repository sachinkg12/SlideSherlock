"""
Generate a self-contained HTML evidence trail report from pipeline output.

Usage:
    from evidence_report import generate_evidence_report
    html = generate_evidence_report(evidence_index, coverage, verify_report)
    with open("evidence_report.html", "w") as f:
        f.write(html)

Or via CLI:
    slidesherlock run deck.pptx --preset pro -o output/
    python -m evidence_report output/evidence_index.json output/coverage.json output/verify_report.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any, Dict, List


def generate_evidence_report(
    evidence_index: Dict[str, Any],
    coverage: Dict[str, Any],
    verify_report: Dict[str, Any],
) -> str:
    """Generate a self-contained HTML report showing the evidence trail."""

    items = evidence_index.get("evidence_items", [])
    decisions = verify_report.get("report", [])
    if isinstance(decisions, dict):
        decisions = list(decisions.values())

    # Group evidence by slide
    evidence_by_slide: Dict[int, List[Dict]] = defaultdict(list)
    for item in items:
        si = item.get("slide_index", 0)
        evidence_by_slide[si].append(item)

    # Group decisions by slide
    decisions_by_slide: Dict[int, List[Dict]] = defaultdict(list)
    for d in decisions:
        si = d.get("slide_index", 0)
        decisions_by_slide[si].append(d)

    all_slides = sorted(set(list(evidence_by_slide.keys()) + list(decisions_by_slide.keys())))

    # Stats
    total_claims = coverage.get("total_claims", 0)
    pass_count = coverage.get("pass", 0)
    rewrite_count = coverage.get("rewrite", 0)
    remove_count = coverage.get("remove", 0)
    evidence_coverage = coverage.get("pct_claims_with_evidence", 0)

    # Build HTML
    slides_html = []
    for si in all_slides:
        ev_items = evidence_by_slide.get(si, [])
        slide_decisions = decisions_by_slide.get(si, [])

        # Evidence list
        ev_rows = ""
        for ev in ev_items:
            kind = ev.get("kind", "UNKNOWN")
            content = (ev.get("content") or "")[:200]
            eid = (ev.get("evidence_id") or "")[:16]
            confidence = ev.get("confidence")
            conf_str = f' <span class="conf">conf: {confidence:.2f}</span>' if confidence else ""
            ev_rows += f"""
            <div class="evidence-item">
                <span class="kind {kind.lower()}">{kind}</span>
                <span class="eid">{eid}...</span>{conf_str}
                <div class="content">{_escape(content)}</div>
            </div>"""

        # Decisions list
        dec_rows = ""
        for d in slide_decisions:
            verdict = d.get("verdict", "UNKNOWN")
            reasons = d.get("reasons", [])
            reason_str = ", ".join(reasons[:3]) if reasons else ""
            v_class = verdict.lower()
            dec_rows += f"""
            <div class="decision {v_class}">
                <span class="verdict-badge {v_class}">{verdict}</span>
                {f'<span class="reasons">{_escape(reason_str)}</span>' if reason_str else ""}
            </div>"""

        slides_html.append(
            f"""
        <div class="slide-section">
            <h2>Slide {si}</h2>
            <div class="columns">
                <div class="col">
                    <h3>Evidence ({len(ev_items)} items)</h3>
                    {ev_rows if ev_rows else '<p class="empty">No evidence items</p>'}
                </div>
                <div class="col">
                    <h3>Verifier Decisions ({len(slide_decisions)})</h3>
                    {dec_rows if dec_rows else '<p class="empty">No decisions</p>'}
                </div>
            </div>
        </div>"""
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SlideSherlock Evidence Trail</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
.subtitle {{ color: #94a3b8; margin-bottom: 2rem; }}
.stats {{ display: flex; gap: 1.5rem; margin-bottom: 2rem; flex-wrap: wrap; }}
.stat {{ background: #1e293b; border-radius: 10px; padding: 1rem 1.5rem; min-width: 140px; }}
.stat-value {{ font-size: 1.5rem; font-weight: 700; }}
.stat-label {{ font-size: 0.8rem; color: #94a3b8; }}
.stat-value.pass {{ color: #4ade80; }}
.stat-value.rewrite {{ color: #fbbf24; }}
.stat-value.remove {{ color: #f87171; }}
.stat-value.coverage {{ color: #38bdf8; }}
.slide-section {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
.slide-section h2 {{ font-size: 1.2rem; margin-bottom: 1rem; color: #f1f5f9; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
.columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
@media (max-width: 768px) {{ .columns {{ grid-template-columns: 1fr; }} }}
.col h3 {{ font-size: 0.9rem; color: #94a3b8; margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }}
.evidence-item {{ background: #0f172a; border-radius: 8px; padding: 0.75rem; margin-bottom: 0.5rem; font-size: 0.85rem; }}
.kind {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; margin-right: 0.5rem; }}
.kind.text_span {{ background: #1e3a5f; color: #93c5fd; }}
.kind.shape_label {{ background: #312e81; color: #a5b4fc; }}
.kind.image_caption, .kind.image_objects, .kind.image_tags, .kind.image_asset, .kind.image_actions {{ background: #134e4a; color: #5eead4; }}
.kind.diagram_summary, .kind.diagram_entities, .kind.diagram_type {{ background: #3b0764; color: #c4b5fd; }}
.kind.slide_caption {{ background: #422006; color: #fde68a; }}
.kind.connector {{ background: #1e293b; color: #94a3b8; }}
.eid {{ color: #64748b; font-family: monospace; font-size: 0.75rem; }}
.conf {{ color: #94a3b8; font-size: 0.75rem; }}
.content {{ color: #cbd5e1; margin-top: 0.4rem; line-height: 1.4; }}
.decision {{ background: #0f172a; border-radius: 8px; padding: 0.75rem; margin-bottom: 0.5rem; border-left: 3px solid; }}
.decision.pass {{ border-color: #4ade80; }}
.decision.rewrite {{ border-color: #fbbf24; }}
.decision.remove {{ border-color: #f87171; }}
.verdict-badge {{ display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; }}
.verdict-badge.pass {{ background: #14532d; color: #4ade80; }}
.verdict-badge.rewrite {{ background: #422006; color: #fbbf24; }}
.verdict-badge.remove {{ background: #450a0a; color: #f87171; }}
.reasons {{ color: #94a3b8; font-size: 0.8rem; margin-left: 0.5rem; }}
.empty {{ color: #475569; font-style: italic; font-size: 0.85rem; }}
.footer {{ margin-top: 2rem; text-align: center; color: #475569; font-size: 0.8rem; }}
</style>
</head>
<body>
<h1>SlideSherlock Evidence Trail</h1>
<p class="subtitle">Every claim traced to source evidence</p>

<div class="stats">
    <div class="stat"><div class="stat-value">{total_claims}</div><div class="stat-label">Total Claims</div></div>
    <div class="stat"><div class="stat-value pass">{pass_count}</div><div class="stat-label">PASS</div></div>
    <div class="stat"><div class="stat-value rewrite">{rewrite_count}</div><div class="stat-label">REWRITE</div></div>
    <div class="stat"><div class="stat-value remove">{remove_count}</div><div class="stat-label">REMOVE</div></div>
    <div class="stat"><div class="stat-value coverage">{evidence_coverage:.1f}%</div><div class="stat-label">Evidence Coverage</div></div>
    <div class="stat"><div class="stat-value">{len(items)}</div><div class="stat-label">Evidence Items</div></div>
</div>

{"".join(slides_html)}

<div class="footer">Generated by SlideSherlock &mdash; evidence-grounded presentation-to-video pipeline</div>
</body>
</html>"""


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: python -m evidence_report evidence_index.json coverage.json verify_report.json [output.html]"
        )
        sys.exit(1)
    ei = json.load(open(sys.argv[1]))
    cov = json.load(open(sys.argv[2]))
    vr = json.load(open(sys.argv[3]))
    out = sys.argv[4] if len(sys.argv) > 4 else "evidence_report.html"
    html = generate_evidence_report(ei, cov, vr)
    with open(out, "w") as f:
        f.write(html)
    print(f"Report written to {out}")
