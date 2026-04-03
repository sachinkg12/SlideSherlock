"""
Output variants config: build output_variants from requested_language.
Each variant: id, lang (BCP-47), voice_id, notes_translate.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_output_variants(requested_language: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Build output_variants for manifest.
    Default: [{"id":"en","lang":"en-US","voice_id":"default_en","notes_translate":false}]
    With requested_language (e.g. hi-IN): add second variant l2.
    """
    variants: List[Dict[str, Any]] = [
        {"id": "en", "lang": "en-US", "voice_id": "default_en", "notes_translate": False},
    ]
    if requested_language and (requested_language or "").strip():
        lang = requested_language.strip()
        # Map lang to variant id (e.g. hi-IN -> l2)
        variants.append({
            "id": "l2",
            "lang": lang,
            "voice_id": f"default_{lang.split('-')[0]}" if "-" in lang else "default_l2",
            "notes_translate": True,
        })
    return variants


def get_variant_path_prefix(variant_id: str) -> str:
    """Return path prefix for variant: 'script/en/', 'audio/en/', etc."""
    return f"{variant_id}/"
