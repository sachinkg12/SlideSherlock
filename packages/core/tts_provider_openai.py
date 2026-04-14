"""
OpenAI TTS provider. Uses the OpenAI text-to-speech API (tts-1 or tts-1-hd).
Works on all platforms (Linux, macOS, Windows). Supports 57 languages.

Cost: ~$0.015 per 1000 characters ($0.03 per 1000 for tts-1-hd).
"""
from __future__ import annotations

import os
from typing import Optional

import requests


class OpenAITTSProvider:
    """OpenAI TTS API provider. Fork-safe (uses requests, not openai SDK)."""

    # OpenAI TTS voice options: alloy, echo, fable, onyx, nova, shimmer
    DEFAULT_VOICE = "nova"

    def __init__(
        self,
        voice_id: Optional[str] = None,
        lang: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.voice = (
            voice_id if voice_id and not voice_id.startswith("default") else self.DEFAULT_VOICE
        )
        self.lang = lang or "en-US"
        self.model = model or os.environ.get("OPENAI_TTS_MODEL", "tts-1")
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    def synthesize(self, text: str, output_path: str, sample_rate: int = 48000) -> float:
        text = (text or "").strip()
        if not text:
            self._write_silence(output_path, 0.5, sample_rate)
            return 0.5

        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set — cannot use OpenAI TTS")

        # Call OpenAI TTS API directly via requests (fork-safe)
        response = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": text,
                "voice": self.voice,
                "response_format": "wav",
                "speed": 1.0,
            },
            timeout=30,
        )

        if response.status_code == 429:
            # Rate limited — retry once after 2s
            import time

            time.sleep(2)
            response = requests.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": text,
                    "voice": self.voice,
                    "response_format": "wav",
                    "speed": 1.0,
                },
                timeout=30,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"OpenAI TTS API error {response.status_code}: {response.text[:200]}"
            )

        # Write the WAV response directly
        with open(output_path, "wb") as f:
            f.write(response.content)

        # Get duration
        dur = self._get_duration(output_path)
        return dur if dur and dur > 0 else 2.0

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _get_duration(self, path: str) -> Optional[float]:
        import subprocess

        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass
        return None

    def _write_silence(self, path: str, duration_s: float, sample_rate: int) -> None:
        import struct
        import wave

        n_frames = int(duration_s * sample_rate)
        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))
