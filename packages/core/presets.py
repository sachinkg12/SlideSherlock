"""
Quality presets: draft | standard | pro.
Each preset sets env vars (or exports for shell) for the pipeline.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

PRESET_DRAFT = "draft"
PRESET_STANDARD = "standard"
PRESET_PRO = "pro"

VALID_PRESETS = (PRESET_DRAFT, PRESET_STANDARD, PRESET_PRO)


# Env vars per preset. Values override defaults when preset is applied.
PRESET_ENV_VARS: Dict[str, Dict[str, str]] = {
    PRESET_DRAFT: {
        "VISION_ENABLED": "0",
        "AUDIO_BGM_ENABLED": "0",
        "VIDEO_TRANSITION": "cut",
        "ON_SCREEN_NOTES_ENABLED": "0",  # Disabled: covers slide content, 16× slower video encode
        "SUBTITLES_ENABLED": "0",
        "VIDEO_INTRO_ENABLED": "0",
        "VIDEO_OUTRO_ENABLED": "0",
        "AUDIO_LOUDNESS_NORMALIZE": "0",
    },
    PRESET_STANDARD: {
        "ON_SCREEN_NOTES_ENABLED": "0",  # Disabled: covers slide content, 16× slower video encode
        "VIDEO_TRANSITION": "crossfade",
        "SUBTITLES_ENABLED": "1",
        "VIDEO_INTRO_ENABLED": "1",
        "VIDEO_OUTRO_ENABLED": "1",
        "VISION_ENABLED": "0",
        "AUDIO_BGM_ENABLED": "0",
        "AUDIO_LOUDNESS_NORMALIZE": "1",
    },
    PRESET_PRO: {
        "VISION_ENABLED": "1",
        "ON_SCREEN_NOTES_ENABLED": "0",  # Disabled: covers slide content, 16× slower video encode
        "VIDEO_TRANSITION": "crossfade",
        "SUBTITLES_ENABLED": "1",
        "VIDEO_INTRO_ENABLED": "1",
        "VIDEO_OUTRO_ENABLED": "1",
        "AUDIO_BGM_ENABLED": "1",
        "AUDIO_BGM_DUCKING": "1",
        "AUDIO_LOUDNESS_NORMALIZE": "1",
    },
}


def get_preset_env_vars(preset: str) -> Dict[str, str]:
    """Return env var overrides for the given preset."""
    if preset not in VALID_PRESETS:
        return {}
    return dict(PRESET_ENV_VARS.get(preset, {}))


def apply_preset(preset: str) -> None:
    """
    Apply preset by setting os.environ. Use before running the pipeline.
    """
    for k, v in get_preset_env_vars(preset).items():
        os.environ[k] = v


def preset_to_export_lines(preset: str) -> List[str]:
    """Return shell export lines for the preset (for use in make/scripts)."""
    lines = []
    for k, v in get_preset_env_vars(preset).items():
        lines.append(f"export {k}={v!r}")
    return lines


def get_current_preset() -> Optional[str]:
    """Infer current preset from SLIDESHERLOCK_PRESET env var."""
    p = (os.environ.get("SLIDESHERLOCK_PRESET") or "").strip().lower()
    return p if p in VALID_PRESETS else None
