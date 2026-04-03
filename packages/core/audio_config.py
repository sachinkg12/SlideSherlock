"""
Audio config: mode, voice provider, loudness normalize.
Env: AUDIO_MODE, AUDIO_VOICE_PROVIDER, AUDIO_LOUDNESS_NORMALIZE.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


AUDIO_MODE_USE_SUPPLIED = "use_supplied"
AUDIO_MODE_GENERATE = "generate"

AUDIO_VOICE_LOCAL = "local"
AUDIO_VOICE_OPENAI = "openai"
AUDIO_VOICE_ELEVENLABS = "elevenlabs"

# Target loudness (LUFS) for broadcast-ish level
DEFAULT_LUFS_TARGET = -16.0
DEFAULT_SAMPLE_RATE = 48000


@dataclass
class AudioConfig:
    mode: str  # use_supplied | generate
    voice_provider: str  # local | openai | elevenlabs
    loudness_normalize: bool
    lufs_target: float = DEFAULT_LUFS_TARGET
    sample_rate: int = DEFAULT_SAMPLE_RATE

    @classmethod
    def from_env(cls) -> "AudioConfig":
        mode = (os.environ.get("AUDIO_MODE") or "generate").strip().lower()
        if mode not in (AUDIO_MODE_USE_SUPPLIED, AUDIO_MODE_GENERATE):
            mode = AUDIO_MODE_GENERATE
        voice = (os.environ.get("AUDIO_VOICE_PROVIDER") or "local").strip().lower()
        if voice not in (AUDIO_VOICE_LOCAL, AUDIO_VOICE_OPENAI, AUDIO_VOICE_ELEVENLABS):
            voice = AUDIO_VOICE_LOCAL
        norm = (os.environ.get("AUDIO_LOUDNESS_NORMALIZE", "1")).strip().lower() in ("1", "true", "yes")
        lufs = float(os.environ.get("AUDIO_LUFS_TARGET", str(DEFAULT_LUFS_TARGET)))
        sr = int(os.environ.get("AUDIO_SAMPLE_RATE", str(DEFAULT_SAMPLE_RATE)))
        return cls(
            mode=mode,
            voice_provider=voice,
            loudness_normalize=norm,
            lufs_target=lufs,
            sample_rate=sr,
        )
