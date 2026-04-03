"""
Vision config per job (Prompt 8).
Parses job config for: vision.enabled, vision.force_kind_by_slide, vision.lang, vision.min_confidence_for_specific_claims.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional


def _parse_config(config_json: Optional[str]) -> Dict[str, Any]:
    """Parse job config_json to dict."""
    if not config_json or not (config_json or "").strip():
        return {}
    try:
        return json.loads(config_json) if isinstance(config_json, str) else (config_json or {})
    except (json.JSONDecodeError, TypeError):
        return {}


def get_vision_config(job_config: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract vision config from job config.
    Returns: {
        "enabled": bool (default True),
        "force_kind_by_slide": { "3": "DIAGRAM", "5": "PHOTO" },
        "lang": str (default "en-US"),
        "min_confidence_for_specific_claims": float (default from env or 0.65),
    }
    """
    cfg = _parse_config(job_config)
    vision = cfg.get("vision") or cfg
    enabled = vision.get("enabled")
    if enabled is None:
        enabled = True
    force = vision.get("force_kind_by_slide") or {}
    if not isinstance(force, dict):
        force = {}
    lang = (vision.get("lang") or os.environ.get("VISION_LANG") or "en-US").strip()
    min_conf = vision.get("min_confidence_for_specific_claims")
    if min_conf is None:
        min_conf = float(os.environ.get("VISION_MIN_CONFIDENCE_SPECIFIC_CLAIMS", "0.65"))
    else:
        min_conf = float(min_conf)
    return {
        "enabled": bool(enabled),
        "force_kind_by_slide": {str(k): str(v).upper() for k, v in force.items() if v},
        "lang": lang,
        "min_confidence_for_specific_claims": max(0.0, min(1.0, min_conf)),
    }


def get_vision_config_for_variant(
    job_config: Optional[str] = None,
    variant: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Vision config with per-variant lang override.
    variant: { "id", "lang", ... } - if provided, vision.lang = variant.get("lang", base_lang).
    """
    base = get_vision_config(job_config)
    if variant and variant.get("lang"):
        base["lang"] = (variant.get("lang") or "en-US").strip()
    return base
