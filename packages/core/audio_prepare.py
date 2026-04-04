"""
Audio prepare stage (Fig3 step 14).
Produces jobs/{job_id}/audio/slide_{i:03}.wav and script/narration_per_slide.json,
timing/slide_{i}_duration.json. Uses supplied audio or generates via TTS.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from audio_config import AudioConfig, AUDIO_MODE_USE_SUPPLIED
from narration_source import build_narration_per_slide
from audio_processor import _get_duration_seconds

# Input path for user-supplied audio (per slide)
INPUT_AUDIO_PREFIX = "input/audio"
AUDIO_OUTPUT_PREFIX = "audio"
TIMING_PREFIX = "timing"
SCRIPT_NARRATION = "script/narration_per_slide.json"
SCRIPT_BLUEPRINT = "script/narration_blueprint.json"

AUDIO_SAMPLE_RATE = 48000


def _slide_num(i: int) -> str:
    return f"{i:03d}"


def _check_supplied_audio_exists(
    minio_client: Any,
    job_id: str,
    slide_count: int,
) -> Tuple[bool, List[str]]:
    """
    Check if per-slide supplied audio exists at jobs/{job_id}/input/audio/slide_001.wav (or .mp3).
    Returns (all_exist, list of storage paths for each slide 1..N).
    """
    paths = []
    for i in range(1, slide_count + 1):
        sn = _slide_num(i)
        for ext in (".wav", ".mp3"):
            key = f"jobs/{job_id}/{INPUT_AUDIO_PREFIX}/slide_{sn}{ext}"
            if minio_client.exists(key):
                paths.append(key)
                break
        else:
            return False, []
    return len(paths) == slide_count, paths


def _download_supplied_audio(
    minio_client: Any,
    job_id: str,
    slide_count: int,
    local_dir: str,
) -> List[Tuple[str, float]]:
    """
    Download supplied audio to local_dir/slide_001.wav, etc.
    Returns list of (local_path, duration_seconds) per slide.
    """
    result = []
    for i in range(1, slide_count + 1):
        sn = _slide_num(i)
        found = None
        for ext in (".wav", ".mp3"):
            key = f"jobs/{job_id}/{INPUT_AUDIO_PREFIX}/slide_{sn}{ext}"
            try:
                data = minio_client.get(key)
                local = os.path.join(local_dir, f"slide_{sn}.wav")
                with open(local, "wb") as f:
                    f.write(data)
                dur = _get_duration_seconds(local)
                result.append((local, dur or 2.0))
                found = True
                break
            except Exception:
                continue
        if not found:
            result.append((os.path.join(local_dir, f"slide_{sn}.wav"), 2.0))
    return result


def run_audio_prepare(
    job_id: str,
    slide_count: int,
    minio_client: Any,
    temp_dir: str,
    config: AudioConfig,
    slides_notes_and_text: List[Tuple[str, str]],
    unified_graphs_by_slide: Dict[int, Dict[str, Any]],
    tts_provider: Optional[Any] = None,
    evidence_index: Optional[Dict[str, Any]] = None,
    llm_provider: Optional[Any] = None,
    variant_id: Optional[str] = None,
    voice_id: Optional[str] = None,
    lang: Optional[str] = None,
    narration_entries_override: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Tuple[str, float]], Dict[str, Any]]:
    """
    Run audio_prepare stage.
    Returns (narration_per_slide_entries, list of (local_audio_path, duration_seconds), narration_payload).
    Writes to MinIO: jobs/{job_id}/audio/slide_{i}.wav, jobs/{job_id}/script/narration_per_slide.json,
    jobs/{job_id}/script/narration_blueprint.json (when evidence_index provided),
    jobs/{job_id}/timing/slide_{i}_duration.json.
    When evidence_index provided: uses smart narration (blueprint + template/LLM fallback).
    variant_id: when set, write to audio/{variant_id}/, script/{variant_id}/, timing/{variant_id}/.
    voice_id: override TTS voice per variant.
    lang: BCP-47 language for TTS (e.g. hi-IN). Uses en-US if not set.
    narration_entries_override: if set, use these instead of build_narration_per_slide (e.g. translated).
    """
    from tts_provider import get_tts_provider

    v_prefix = f"{variant_id}/" if variant_id else ""
    from audio_processor import process_audio_simple
    from narration_blueprint import build_blueprint_per_slide

    all_exist, supplied_paths = _check_supplied_audio_exists(minio_client, job_id, slide_count)
    audio_dir = os.path.join(temp_dir, f"audio_out_{variant_id or 'default'}")
    os.makedirs(audio_dir, exist_ok=True)
    per_slide_audio: List[Tuple[str, float]] = []
    narration_entries: List[Dict[str, Any]] = []

    if config.mode == AUDIO_MODE_USE_SUPPLIED and all_exist:
        for i in range(slide_count):
            sn = _slide_num(i + 1)
            key = supplied_paths[i]
            data = minio_client.get(key)
            local_raw = os.path.join(audio_dir, f"slide_{sn}_raw.wav")
            with open(local_raw, "wb") as f:
                f.write(data)
            local_out = os.path.join(audio_dir, f"slide_{sn}.wav")
            dur = process_audio_simple(
                local_raw,
                local_out,
                loudness_normalize=config.loudness_normalize,
                lufs_target=config.lufs_target,
                sample_rate=config.sample_rate,
            )
            per_slide_audio.append((local_out, dur))
            narration_entries.append(
                {
                    "slide_index": i + 1,
                    "narration_text": "",
                    "source_used": "user_audio",
                    "word_count": 0,
                }
            )
    else:
        blueprints = None
        if narration_entries_override and len(narration_entries_override) >= slide_count:
            entries = narration_entries_override[:slide_count]
        else:
            llm_smart_fn = None
            if evidence_index:
                blueprints = build_blueprint_per_slide(
                    slide_count,
                    slides_notes_and_text,
                    unified_graphs_by_slide,
                    evidence_index.get("evidence_items", []),
                )
                if llm_provider and hasattr(llm_provider, "generate_narration"):
                    llm_smart_fn = llm_provider.generate_narration

            entries = build_narration_per_slide(
                slide_count,
                slides_notes_and_text,
                unified_graphs_by_slide,
                llm_narration_fn=None,
                blueprints=blueprints,
                evidence_index=evidence_index,
                llm_smart_narration_fn=llm_smart_fn,
            )
        provider = tts_provider or get_tts_provider(
            config.voice_provider,
            voice_id=voice_id,
            lang=lang or "en-US",
        )
        for i, entry in enumerate(entries):
            slide_index = entry["slide_index"]
            text = entry["narration_text"]
            sn = _slide_num(slide_index)
            raw_path = os.path.join(audio_dir, f"slide_{sn}_raw.wav")
            out_path = os.path.join(audio_dir, f"slide_{sn}.wav")
            dur_raw = provider.synthesize(text, raw_path, sample_rate=AUDIO_SAMPLE_RATE)
            dur = process_audio_simple(
                raw_path,
                out_path,
                loudness_normalize=config.loudness_normalize,
                lufs_target=config.lufs_target,
                sample_rate=config.sample_rate,
            )
            per_slide_audio.append((out_path, dur or dur_raw))
            entry_out = {
                "slide_index": slide_index,
                "narration_text": text,
                "source_used": entry["source_used"],
                "word_count": entry["word_count"],
            }
            if "referenced_entity_ids" in entry:
                entry_out["referenced_entity_ids"] = entry["referenced_entity_ids"]
            if "referenced_evidence_ids" in entry:
                entry_out["referenced_evidence_ids"] = entry["referenced_evidence_ids"]
            narration_entries.append(entry_out)

        if blueprints:
            blueprint_payload = {
                "schema_version": "1.0",
                "job_id": job_id,
                "blueprints": blueprints,
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            minio_client.put(
                f"jobs/{job_id}/script/{v_prefix}narration_blueprint.json",
                json.dumps(blueprint_payload, indent=2).encode("utf-8"),
                "application/json",
            )

    narration_payload = {
        "schema_version": "1.0",
        "job_id": job_id,
        "slides": narration_entries,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    for i in range(slide_count):
        sn = _slide_num(i + 1)
        local_path, dur = per_slide_audio[i]
        storage_audio = f"jobs/{job_id}/{AUDIO_OUTPUT_PREFIX}/{v_prefix}slide_{sn}.wav"
        with open(local_path, "rb") as f:
            minio_client.put(storage_audio, f.read(), "audio/wav")
        duration_payload = {
            "schema_version": "1.0",
            "job_id": job_id,
            "slide_index": i + 1,
            "audio_duration_seconds": round(dur, 3),
            "fallback_duration_seconds": round(dur, 3),
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        storage_duration = f"jobs/{job_id}/{TIMING_PREFIX}/{v_prefix}slide_{sn}_duration.json"
        minio_client.put(
            storage_duration,
            json.dumps(duration_payload, indent=2).encode("utf-8"),
            "application/json",
        )

    storage_narration = f"jobs/{job_id}/script/{v_prefix}narration_per_slide.json"
    minio_client.put(
        storage_narration,
        json.dumps(narration_payload, indent=2).encode("utf-8"),
        "application/json",
    )

    return narration_entries, per_slide_audio, narration_payload
