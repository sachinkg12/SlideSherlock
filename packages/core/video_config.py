"""
Video production config: transitions, intro/outro, subtitles, BGM.
Env: VIDEO_TRANSITION, VIDEO_TRANSITION_MS, VIDEO_INTRO_ENABLED, etc.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

TRANSITION_CUT = "cut"
TRANSITION_CROSSFADE = "crossfade"

DEFAULT_TRANSITION_MS = 300
DEFAULT_AUDIO_FADE_MS = 100
DEFAULT_BGM_VOLUME_DB = -28.0
DEFAULT_INTRO_DURATION = 2.0
DEFAULT_OUTRO_DURATION = 2.0


@dataclass
class VideoConfig:
    """Configuration for video composition (transitions, intro/outro, subtitles, BGM)."""

    # Transitions
    transition: str  # cut | crossfade
    transition_ms: int
    audio_fade_ms: int  # per-slide fade in/out to avoid clicks
    # Intro/outro
    intro_enabled: bool
    intro_title: str
    intro_subtitle: str
    intro_duration: float
    outro_enabled: bool
    outro_text: str
    outro_duration: float
    # Subtitles
    subtitles_enabled: bool
    subtitles_burn_in: bool
    # BGM
    bgm_enabled: bool
    bgm_volume_db: float
    bgm_ducking: bool
    bgm_path: str | None

    @classmethod
    def from_env(cls, deck_title: str = "", deck_subtitle: str = "") -> "VideoConfig":
        trans = (os.environ.get("VIDEO_TRANSITION") or "crossfade").strip().lower()
        if trans not in (TRANSITION_CUT, TRANSITION_CROSSFADE):
            trans = TRANSITION_CROSSFADE
        trans_ms = int(os.environ.get("VIDEO_TRANSITION_MS", str(DEFAULT_TRANSITION_MS)))
        trans_ms = max(0, min(1000, trans_ms))
        audio_fade = int(os.environ.get("VIDEO_AUDIO_FADE_MS", str(DEFAULT_AUDIO_FADE_MS)))
        audio_fade = max(0, min(300, audio_fade))
        intro_on = (os.environ.get("VIDEO_INTRO_ENABLED", "0")).strip().lower() in (
            "1",
            "true",
            "yes",
        )
        intro_title = os.environ.get("VIDEO_INTRO_TITLE", deck_title or "Presentation").strip()
        intro_subtitle = os.environ.get("VIDEO_INTRO_SUBTITLE", deck_subtitle).strip()
        intro_dur = float(os.environ.get("VIDEO_INTRO_DURATION", str(DEFAULT_INTRO_DURATION)))
        intro_dur = max(0.5, min(10.0, intro_dur))
        outro_on = (os.environ.get("VIDEO_OUTRO_ENABLED", "0")).strip().lower() in (
            "1",
            "true",
            "yes",
        )
        outro_text = os.environ.get("VIDEO_OUTRO_TEXT", "Thanks for watching").strip()
        outro_dur = float(os.environ.get("VIDEO_OUTRO_DURATION", str(DEFAULT_OUTRO_DURATION)))
        outro_dur = max(0.5, min(10.0, outro_dur))
        subs_on = (os.environ.get("SUBTITLES_ENABLED", "0")).strip().lower() in ("1", "true", "yes")
        subs_burn = (os.environ.get("SUBTITLES_BURN_IN", "0")).strip().lower() in (
            "1",
            "true",
            "yes",
        )
        bgm_on = (os.environ.get("AUDIO_BGM_ENABLED", "0")).strip().lower() in ("1", "true", "yes")
        bgm_vol = float(os.environ.get("AUDIO_BGM_VOLUME_DB", str(DEFAULT_BGM_VOLUME_DB)))
        bgm_vol = max(-60.0, min(0.0, bgm_vol))
        bgm_duck = (os.environ.get("AUDIO_BGM_DUCKING", "1")).strip().lower() in (
            "1",
            "true",
            "yes",
        )
        bgm_path = (os.environ.get("AUDIO_BGM_PATH") or "").strip() or None
        if bgm_path and not os.path.exists(bgm_path):
            bgm_path = None
        return cls(
            transition=trans,
            transition_ms=trans_ms,
            audio_fade_ms=audio_fade,
            intro_enabled=intro_on,
            intro_title=intro_title,
            intro_subtitle=intro_subtitle,
            intro_duration=intro_dur,
            outro_enabled=outro_on,
            outro_text=outro_text,
            outro_duration=outro_dur,
            subtitles_enabled=subs_on,
            subtitles_burn_in=subs_burn,
            bgm_enabled=bgm_on and bgm_path,
            bgm_volume_db=bgm_vol,
            bgm_ducking=bgm_duck,
            bgm_path=bgm_path,
        )
