"""
TTS provider interface: local (pyttsx3), openai, elevenlabs (pluggable).
Generates narration audio from text per slide.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import Optional

# Preferred sample rate for pipeline
TTS_SAMPLE_RATE = 48000


class TTSProvider(ABC):
    """Interface for generating speech from text."""

    @abstractmethod
    def synthesize(self, text: str, output_path: str, sample_rate: int = TTS_SAMPLE_RATE) -> float:
        """
        Synthesize text to audio file. Returns duration in seconds.
        output_path: .wav or .mp3.
        """


# Voice/lang mapping for system TTS (macOS say, espeak)
# BCP-47 lang -> system voice/lang code. Covers the top 15 languages
# by internet users. macOS `say` supports all of these with neural voices.
VOICE_LANG_MAP = {
    "en": "en_US",
    "en-US": "en_US",
    "en-GB": "en_GB",
    "es": "es_ES",
    "es-ES": "es_ES",
    "es-MX": "es_MX",
    "fr": "fr_FR",
    "fr-FR": "fr_FR",
    "de": "de_DE",
    "de-DE": "de_DE",
    "pt": "pt_BR",
    "pt-BR": "pt_BR",
    "pt-PT": "pt_PT",
    "it": "it_IT",
    "it-IT": "it_IT",
    "zh": "zh_CN",
    "zh-CN": "zh_CN",
    "zh-TW": "zh_TW",
    "ja": "ja_JP",
    "ja-JP": "ja_JP",
    "ko": "ko_KR",
    "ko-KR": "ko_KR",
    "hi": "hi_IN",
    "hi-IN": "hi_IN",
    "ar": "ar_SA",
    "ar-SA": "ar_SA",
    "tr": "tr_TR",
    "tr-TR": "tr_TR",
    "nl": "nl_NL",
    "nl-NL": "nl_NL",
    "pl": "pl_PL",
    "pl-PL": "pl_PL",
    "sv": "sv_SE",
    "sv-SE": "sv_SE",
    "ru": "ru_RU",
    "ru-RU": "ru_RU",
    "id": "id_ID",
    "id-ID": "id_ID",
    # Added: top 40 languages coverage (where macOS TTS is available)
    "bn": "bn_IN",
    "bn-IN": "bn_IN",
    "vi": "vi_VN",
    "vi-VN": "vi_VN",
    "te": "te_IN",
    "te-IN": "te_IN",
    "ta": "ta_IN",
    "ta-IN": "ta_IN",
    "th": "th_TH",
    "th-TH": "th_TH",
    "kn": "kn_IN",
    "kn-IN": "kn_IN",
    "zh-HK": "zh_HK",
    "yue": "zh_HK",
    "ms": "ms_MY",
    "ms-MY": "ms_MY",
    "he": "he_IL",
    "he-IL": "he_IL",
    "uk": "uk_UA",
    "uk-UA": "uk_UA",
    "cs": "cs_CZ",
    "cs-CZ": "cs_CZ",
    "hu": "hu_HU",
    "hu-HU": "hu_HU",
    "el": "el_GR",
    "el-GR": "el_GR",
    "fi": "fi_FI",
    "fi-FI": "fi_FI",
    "da": "da_DK",
    "da-DK": "da_DK",
    "nb": "nb_NO",
    "no": "nb_NO",
    "nb-NO": "nb_NO",
    "ro": "ro_RO",
    "ro-RO": "ro_RO",
    "hr": "hr_HR",
    "hr-HR": "hr_HR",
    "sk": "sk_SK",
    "sk-SK": "sk_SK",
    "bg": "bg_BG",
    "bg-BG": "bg_BG",
    "ca": "ca_ES",
    "ca-ES": "ca_ES",
    "sl": "sl_SI",
    "sl-SI": "sl_SI",
}

# Supported languages for UI dropdown (display name → BCP-47 code)
# Ordered by total speakers (native + L2). Only languages with macOS TTS support.
SUPPORTED_LANGUAGES = [
    ("English", "en-US"),
    ("Chinese (Mandarin)", "zh-CN"),
    ("Hindi", "hi-IN"),
    ("Spanish", "es-ES"),
    ("Arabic", "ar-SA"),
    ("French", "fr-FR"),
    ("Bengali", "bn-IN"),
    ("Portuguese (Brazil)", "pt-BR"),
    ("Indonesian", "id-ID"),
    ("Russian", "ru-RU"),
    ("German", "de-DE"),
    ("Japanese", "ja-JP"),
    ("Vietnamese", "vi-VN"),
    ("Telugu", "te-IN"),
    ("Turkish", "tr-TR"),
    ("Tamil", "ta-IN"),
    ("Cantonese", "zh-HK"),
    ("Korean", "ko-KR"),
    ("Thai", "th-TH"),
    ("Italian", "it-IT"),
    ("Kannada", "kn-IN"),
    ("Polish", "pl-PL"),
    ("Dutch", "nl-NL"),
    ("Swedish", "sv-SE"),
    ("Ukrainian", "uk-UA"),
    ("Hebrew", "he-IL"),
    ("Czech", "cs-CZ"),
    ("Hungarian", "hu-HU"),
    ("Greek", "el-GR"),
    ("Romanian", "ro-RO"),
    ("Finnish", "fi-FI"),
    ("Danish", "da-DK"),
    ("Norwegian", "nb-NO"),
    ("Croatian", "hr-HR"),
    ("Slovak", "sk-SK"),
    ("Bulgarian", "bg-BG"),
    ("Catalan", "ca-ES"),
    ("Slovenian", "sl-SI"),
    ("Malay", "ms-MY"),
]


class LocalTTSProvider(TTSProvider):
    """
    Local TTS using pyttsx3 (offline) or fallback to system say/espeak.
    Supports voice_id and lang for multilingual output.
    """

    def __init__(
        self,
        sample_rate: int = TTS_SAMPLE_RATE,
        voice_id: Optional[str] = None,
        lang: Optional[str] = None,
    ):
        self.sample_rate = sample_rate
        self.voice_id = voice_id or "default"
        self.lang = (lang or "en-US").strip()
        self._engine = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
            return self._engine
        except Exception:
            return None

    def synthesize(self, text: str, output_path: str, sample_rate: int = TTS_SAMPLE_RATE) -> float:
        text = (text or "").strip()
        if not text:
            self._write_silence(output_path, 0.5, sample_rate)
            return 0.5
        engine = self._get_engine()
        if engine:
            try:
                engine.save_to_file(text, output_path)
                engine.runAndWait()
                dur = self._get_duration_seconds(output_path)
                return dur if dur and dur > 0 else 2.0
            finally:
                self._engine = None
        return self._synthesize_say(output_path, text, sample_rate)

    def _get_duration_seconds(self, path: str) -> Optional[float]:
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

    def _write_silence(self, path: str, duration_sec: float, sample_rate: int) -> None:
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"anullsrc=channel_layout=stereo:sample_rate={sample_rate}:duration={duration_sec}",
                    "-ac",
                    "1",
                    path,
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except Exception:
            with open(path, "wb") as f:
                f.write(b"\x00" * int(sample_rate * duration_sec * 2))

    def _synthesize_say(self, output_path: str, text: str, sample_rate: int) -> float:
        """Fallback: macOS say or Linux espeak, then convert to WAV. Uses voice_id/lang for multilingual."""
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
            aiff_path = f.name
        try:
            if os.name == "posix" and os.uname().sysname == "Darwin":
                cmd = ["say", "-o", aiff_path]
                lang_code = VOICE_LANG_MAP.get(
                    self.lang, VOICE_LANG_MAP.get(self.lang.split("-")[0], "en_US")
                )
                if lang_code and lang_code != "en_US":
                    cmd.extend(["-l", lang_code.replace("_", "-")])
                if self.voice_id and self.voice_id != "default":
                    cmd.extend(["-v", self.voice_id])
                cmd.append(text)
                subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            else:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as w:
                    wav_tmp = w.name
                try:
                    espeak_cmd = ["espeak", "-w", wav_tmp]
                    base_lang = self.lang.split("-")[0]
                    if base_lang and base_lang != "en":
                        espeak_cmd.extend(["-v", base_lang])
                    espeak_cmd.append(text)
                    subprocess.run(espeak_cmd, check=True, capture_output=True, timeout=30)
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            wav_tmp,
                            "-ar",
                            str(sample_rate),
                            "-ac",
                            "1",
                            output_path,
                        ],
                        check=True,
                        capture_output=True,
                        timeout=10,
                    )
                    return self._get_duration_seconds(output_path) or 2.0
                finally:
                    if os.path.exists(wav_tmp):
                        os.unlink(wav_tmp)
            subprocess.run(
                ["ffmpeg", "-y", "-i", aiff_path, "-ar", str(sample_rate), "-ac", "1", output_path],
                check=True,
                capture_output=True,
                timeout=10,
            )
            return self._get_duration_seconds(output_path) or 2.0
        except Exception:
            fallback = (os.environ.get("TTS_FALLBACK_TO_EN", "0")).strip().lower() in (
                "1",
                "true",
                "yes",
            )
            if fallback and self.lang and self.lang.lower() not in ("en", "en-us", "en_us"):
                orig_lang, orig_voice = self.lang, self.voice_id
                self.lang, self.voice_id = "en-US", "default"
                try:
                    return self._synthesize_say(output_path, text, sample_rate)
                except Exception:
                    self.lang, self.voice_id = orig_lang, orig_voice
                    self._write_silence(output_path, 2.0, sample_rate)
                    return 2.0
                finally:
                    self.lang, self.voice_id = orig_lang, orig_voice
            self._write_silence(output_path, 2.0, sample_rate)
            return 2.0
        finally:
            if os.path.exists(aiff_path):
                os.unlink(aiff_path)


def _make_local_tts(voice_id, lang):
    return LocalTTSProvider(voice_id=voice_id, lang=lang)


def _make_openai_tts(voice_id, lang):
    try:
        from tts_provider_openai import OpenAITTSProvider

        return OpenAITTSProvider(voice_id=voice_id, lang=lang)
    except (ImportError, TypeError):
        return LocalTTSProvider(voice_id=voice_id, lang=lang)


def _make_elevenlabs_tts(voice_id, lang):
    try:
        from tts_provider_elevenlabs import ElevenLabsTTSProvider

        return ElevenLabsTTSProvider(voice_id=voice_id, lang=lang)
    except (ImportError, TypeError):
        return LocalTTSProvider(voice_id=voice_id, lang=lang)


# Registry: adding a new TTS provider = one entry here.
_TTS_PROVIDER_REGISTRY = {
    "local": _make_local_tts,
    "openai": _make_openai_tts,
    "elevenlabs": _make_elevenlabs_tts,
}


def register_tts_provider(name: str, factory) -> None:
    """Register a new TTS provider factory. factory(voice_id, lang) -> TTSProvider."""
    _TTS_PROVIDER_REGISTRY[name] = factory


def get_tts_provider(
    voice_provider: str,
    voice_id: Optional[str] = None,
    lang: Optional[str] = None,
) -> Optional[TTSProvider]:
    """Factory: lookup provider in registry; falls back to local."""
    factory = _TTS_PROVIDER_REGISTRY.get(voice_provider, _TTS_PROVIDER_REGISTRY["local"])
    return factory(voice_id, lang)
