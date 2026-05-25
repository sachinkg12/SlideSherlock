"""
Production summary report.

A manager-/operator-facing summary of one pipeline run: what the gate decided,
why, how much of the deck needs human attention, and what to do next.

JSON and a self-contained local HTML file. The HTML has no external scripts,
no tracking, no identity-revealing URLs.
"""
from __future__ import annotations

import html
import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Union

PathLike = Union[str, os.PathLike]
JsonDict = Dict[str, Any]

_NEXT_ACTION_BY_DECISION = {
    "deliver": "deliver",
    "deliver_with_warnings": "deliver after spot check",
    "needs_review": "review listed slides",
    "block": "block and regenerate",
}


def _load(p):
    if p is None:
        return None
    if isinstance(p, (dict, list)):
        return p
    with open(p) as f:
        return json.load(f)


def build(
    quality_gate: Union[PathLike, JsonDict],
    evidence_health: Optional[Union[PathLike, JsonDict]] = None,
    review_items: Optional[Union[PathLike, JsonDict, List[JsonDict]]] = None,
) -> JsonDict:
    qg = _load(quality_gate) or {}
    eh = _load(evidence_health) or {}
    items_obj = _load(review_items) or []
    items: List[JsonDict]
    if isinstance(items_obj, dict):
        items = items_obj.get("items", [])
    else:
        items = items_obj

    decision = qg.get("decision")
    top_reasons = Counter(it.get("risk_type") for it in items if it.get("risk_type"))
    top5 = [{"risk_type": k, "count": v} for k, v in top_reasons.most_common(5)]

    return {
        "schema_version": "1.0",
        "job_id": qg.get("job_id"),
        "deck_id": qg.get("deck_id"),
        "language": qg.get("language"),
        "decision": decision,
        "recommended_next_action": _NEXT_ACTION_BY_DECISION.get(decision, ""),
        "main_risks": qg.get("reasons", []),
        "totals": {
            "total_slides": qg.get("total_slides", 0),
            "total_narration_segments": qg.get("total_segments", 0),
            "verifier_pass": qg.get("pass_count", 0),
            "verifier_rewrite": qg.get("rewrite_count", 0),
            "verifier_remove": qg.get("remove_count", 0),
            "fallback_count": qg.get("fallback_count", 0),
            "fallback_rate": qg.get("fallback_rate", 0.0),
            "proxy_flagged_slide_count": qg.get("proxy_flagged_slide_count", 0),
            "proxy_flagged_rate": qg.get("proxy_flagged_rate", 0.0),
            "translation_warning_count": qg.get("translation_warning_count", 0),
        },
        "evidence_coverage": {
            "slides_total": eh.get("slides_total", 0),
            "slides_with_text": eh.get("slides_with_text", 0),
            "slides_with_images": eh.get("slides_with_images", 0),
            "slides_with_no_evidence": eh.get("slides_with_no_evidence", 0),
            "slides_with_low_confidence_vision": eh.get("slides_with_low_confidence_vision", 0),
            "chart_like_evidence_count": eh.get("chart_like_evidence_count", 0),
            "table_like_evidence_count": eh.get("table_like_evidence_count", 0),
            "risk_level": eh.get("risk_level"),
        },
        "review": {
            "item_count": len(items),
            "top_reasons": top5,
        },
    }


# --------------------------------------------------------------------------
# HTML renderer (self-contained, no external assets)
# --------------------------------------------------------------------------

_HTML_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial,
    sans-serif;
  margin: 0;
  padding: 24px;
  max-width: 880px;
  margin-left: auto;
  margin-right: auto;
  color: #1a1a1a;
  background: #fafafa;
}
h1 { font-size: 1.4rem; margin: 0 0 0.25rem; }
.sub { color: #555; font-size: 0.9rem; margin-bottom: 1.25rem; }
.decision {
  display: inline-block; padding: 6px 12px; border-radius: 4px;
  font-weight: 700; letter-spacing: 0.04em;
}
.decision.deliver { background: #ddebd8; color: #2d4f24; }
.decision.deliver_with_warnings { background: #fdf1c6; color: #6b5310; }
.decision.needs_review { background: #ffe3c4; color: #7a3d00; }
.decision.block { background: #f8d6d1; color: #7a1d10; }
.section {
  background: #fff; border: 1px solid #e2e2e2; border-radius: 6px;
  padding: 16px; margin-top: 16px;
}
.section h2 { font-size: 1.05rem; margin: 0 0 0.5rem; }
.grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 8px;
}
.kv { background: #f5f5f5; padding: 8px 10px; border-radius: 4px; }
.kv .k { color: #555; font-size: 0.8rem; }
.kv .v { font-weight: 600; font-size: 1.05rem; }
.next { font-weight: 600; margin-top: 6px; }
ul.reasons { margin: 0.25rem 0; padding-left: 1.2rem; }
ul.reasons li { margin-bottom: 0.15rem; font-size: 0.92rem; }
table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; font-size: 0.9rem; }
th { font-weight: 600; color: #444; }
.muted { color: #888; }
@media (prefers-color-scheme: dark) {
  body { background: #181818; color: #eaeaea; }
  .section { background: #232323; border-color: #333; }
  .kv { background: #2a2a2a; }
  .kv .k { color: #aaa; }
  th, td { border-color: #333; }
}
"""


def _pct(x):
    try:
        return f"{float(x) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def render_html(summary: JsonDict) -> str:
    t = summary.get("totals", {})
    ec = summary.get("evidence_coverage", {})
    rv = summary.get("review", {})
    decision = summary.get("decision") or ""
    next_action = summary.get("recommended_next_action") or ""

    def esc(x):
        return html.escape(str(x), quote=True) if x is not None else ""

    main_risks_html = ""
    if summary.get("main_risks"):
        items_html = "".join(f"<li>{esc(r)}</li>" for r in summary["main_risks"])
        main_risks_html = f"<ul class='reasons'>{items_html}</ul>"
    else:
        main_risks_html = "<p class='muted'>No blocking or review-triggering risks.</p>"

    top_html = ""
    if rv.get("top_reasons"):
        rows = "".join(
            f"<tr><td>{esc(r['risk_type'])}</td><td>{esc(r['count'])}</td></tr>"
            for r in rv["top_reasons"]
        )
        top_html = (
            "<table><thead><tr><th>Risk type</th><th>Items</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        top_html = "<p class='muted'>No review items.</p>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Production summary</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{_HTML_CSS}</style>
</head>
<body>
<h1>Production summary</h1>
<div class="sub">deck {esc(summary.get('deck_id') or '')} &middot; language {esc(summary.get('language') or '')}</div>

<div class="section">
  <h2>Decision</h2>
  <span class="decision {esc(decision)}">{esc(decision).replace('_', ' ').upper()}</span>
  <p class="next">Recommended next action: {esc(next_action)}</p>
  {main_risks_html}
</div>

<div class="section">
  <h2>Totals</h2>
  <div class="grid">
    <div class="kv"><div class="k">Slides</div><div class="v">{esc(t.get('total_slides', 0))}</div></div>
    <div class="kv"><div class="k">Segments</div><div class="v">{esc(t.get('total_narration_segments', 0))}</div></div>
    <div class="kv"><div class="k">Verifier PASS</div><div class="v">{esc(t.get('verifier_pass', 0))}</div></div>
    <div class="kv"><div class="k">Verifier REWRITE</div><div class="v">{esc(t.get('verifier_rewrite', 0))}</div></div>
    <div class="kv"><div class="k">Verifier REMOVE</div><div class="v">{esc(t.get('verifier_remove', 0))}</div></div>
    <div class="kv"><div class="k">Fallback count</div><div class="v">{esc(t.get('fallback_count', 0))}</div></div>
    <div class="kv"><div class="k">Fallback rate</div><div class="v">{_pct(t.get('fallback_rate', 0))}</div></div>
    <div class="kv"><div class="k">Proxy flagged</div><div class="v">{esc(t.get('proxy_flagged_slide_count', 0))}</div></div>
    <div class="kv"><div class="k">Proxy rate</div><div class="v">{_pct(t.get('proxy_flagged_rate', 0))}</div></div>
    <div class="kv"><div class="k">Translation warnings</div><div class="v">{esc(t.get('translation_warning_count', 0))}</div></div>
  </div>
</div>

<div class="section">
  <h2>Evidence coverage</h2>
  <div class="grid">
    <div class="kv"><div class="k">Slides total</div><div class="v">{esc(ec.get('slides_total', 0))}</div></div>
    <div class="kv"><div class="k">With text</div><div class="v">{esc(ec.get('slides_with_text', 0))}</div></div>
    <div class="kv"><div class="k">With images</div><div class="v">{esc(ec.get('slides_with_images', 0))}</div></div>
    <div class="kv"><div class="k">No evidence</div><div class="v">{esc(ec.get('slides_with_no_evidence', 0))}</div></div>
    <div class="kv"><div class="k">Low-conf vision</div><div class="v">{esc(ec.get('slides_with_low_confidence_vision', 0))}</div></div>
    <div class="kv"><div class="k">Chart-like</div><div class="v">{esc(ec.get('chart_like_evidence_count', 0))}</div></div>
    <div class="kv"><div class="k">Table-like</div><div class="v">{esc(ec.get('table_like_evidence_count', 0))}</div></div>
    <div class="kv"><div class="k">Risk level</div><div class="v">{esc(ec.get('risk_level') or '—')}</div></div>
  </div>
</div>

<div class="section">
  <h2>Review queue ({esc(rv.get('item_count', 0))} items)</h2>
  <h3 style="margin:0.5rem 0 0.25rem;font-size:0.95rem;">Top reasons</h3>
  {top_html}
</div>
</body>
</html>
"""


def write_production_summary(
    json_path: PathLike,
    html_path: PathLike,
    quality_gate: Union[PathLike, JsonDict],
    evidence_health: Optional[Union[PathLike, JsonDict]] = None,
    review_items: Optional[Union[PathLike, JsonDict, List[JsonDict]]] = None,
) -> JsonDict:
    summary = build(quality_gate, evidence_health, review_items)
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    with open(html_path, "w") as f:
        f.write(render_html(summary))
    return summary
