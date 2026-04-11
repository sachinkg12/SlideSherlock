"""
Unit tests for vision_config.py: get_vision_config, get_vision_config_for_variant, _parse_config.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vision_config import get_vision_config, get_vision_config_for_variant


def test_defaults_with_no_config():
    """No job_config -> defaults: enabled True, empty force_kind, en-US lang, 0.65 confidence."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("VISION_LANG", None)
        os.environ.pop("VISION_MIN_CONFIDENCE_SPECIFIC_CLAIMS", None)
        result = get_vision_config(None)
    assert result["enabled"] is True
    assert result["force_kind_by_slide"] == {}
    assert result["lang"] == "en-US"
    assert result["min_confidence_for_specific_claims"] == 0.65


def test_enabled_false_in_config():
    """vision.enabled=false in JSON config -> enabled False."""
    cfg = json.dumps({"vision": {"enabled": False}})
    result = get_vision_config(cfg)
    assert result["enabled"] is False


def test_force_kind_by_slide_parsing():
    """force_kind_by_slide keys are stringified, values uppercased."""
    cfg = json.dumps({"vision": {"force_kind_by_slide": {3: "diagram", 5: "photo"}}})
    result = get_vision_config(cfg)
    assert result["force_kind_by_slide"]["3"] == "DIAGRAM"
    assert result["force_kind_by_slide"]["5"] == "PHOTO"


def test_force_kind_by_slide_invalid_type_is_empty():
    """force_kind_by_slide that is not a dict is treated as empty."""
    cfg = json.dumps({"vision": {"force_kind_by_slide": "bad_value"}})
    result = get_vision_config(cfg)
    assert result["force_kind_by_slide"] == {}


def test_lang_from_config():
    """vision.lang in config overrides env default."""
    cfg = json.dumps({"vision": {"lang": "es-ES"}})
    result = get_vision_config(cfg)
    assert result["lang"] == "es-ES"


def test_lang_from_env_fallback():
    """VISION_LANG env var used when not in config."""
    with patch.dict(os.environ, {"VISION_LANG": "fr-FR"}, clear=False):
        result = get_vision_config(None)
    assert result["lang"] == "fr-FR"


def test_min_confidence_clamped_above_one():
    """min_confidence_for_specific_claims > 1.0 is clamped to 1.0."""
    cfg = json.dumps({"vision": {"min_confidence_for_specific_claims": 5.0}})
    result = get_vision_config(cfg)
    assert result["min_confidence_for_specific_claims"] == 1.0


def test_min_confidence_clamped_below_zero():
    """min_confidence_for_specific_claims < 0 is clamped to 0.0."""
    cfg = json.dumps({"vision": {"min_confidence_for_specific_claims": -1.0}})
    result = get_vision_config(cfg)
    assert result["min_confidence_for_specific_claims"] == 0.0


def test_min_confidence_from_env():
    """VISION_MIN_CONFIDENCE_SPECIFIC_CLAIMS env var used when not in config."""
    with patch.dict(os.environ, {"VISION_MIN_CONFIDENCE_SPECIFIC_CLAIMS": "0.8"}, clear=False):
        result = get_vision_config(None)
    assert result["min_confidence_for_specific_claims"] == 0.8


def test_invalid_json_config_returns_defaults():
    """Malformed JSON -> all defaults returned (no crash)."""
    result = get_vision_config("{not valid json}")
    assert result["enabled"] is True
    assert result["lang"] == "en-US"


def test_empty_string_config_returns_defaults():
    """Empty string config -> defaults."""
    result = get_vision_config("")
    assert result["enabled"] is True


def test_flat_config_without_vision_key():
    """Config without 'vision' nesting is still parsed (falls back to top-level dict)."""
    cfg = json.dumps({"enabled": False, "lang": "de-DE"})
    result = get_vision_config(cfg)
    assert result["enabled"] is False
    assert result["lang"] == "de-DE"


def test_variant_lang_override():
    """get_vision_config_for_variant overrides lang with variant lang."""
    cfg = json.dumps({"vision": {"lang": "en-US"}})
    variant = {"id": "v1", "lang": "ja-JP"}
    result = get_vision_config_for_variant(cfg, variant)
    assert result["lang"] == "ja-JP"


def test_variant_without_lang_keeps_base_lang():
    """get_vision_config_for_variant with no variant lang keeps base config lang."""
    cfg = json.dumps({"vision": {"lang": "pt-BR"}})
    variant = {"id": "v1"}
    result = get_vision_config_for_variant(cfg, variant)
    assert result["lang"] == "pt-BR"


def test_variant_none_keeps_base():
    """get_vision_config_for_variant with None variant returns base config unchanged."""
    cfg = json.dumps({"vision": {"lang": "ko-KR"}})
    result = get_vision_config_for_variant(cfg, None)
    assert result["lang"] == "ko-KR"
