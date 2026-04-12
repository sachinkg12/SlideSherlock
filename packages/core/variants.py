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

    requested_language can be:
    - Single language: "hi-IN"
    - Comma-separated: "hi-IN,es-ES,fr-FR"
    - None: English only

    Each additional language gets its own variant (l2, l3, l4, ...) that
    runs translate → verify → narrate → audio → video independently.
    """
    variants: List[Dict[str, Any]] = [
        {"id": "en", "lang": "en-US", "voice_id": "default_en", "notes_translate": False},
    ]
    if not requested_language or not requested_language.strip():
        return variants

    langs = [lang_code.strip() for lang_code in requested_language.split(",") if lang_code.strip()]
    for i, lang in enumerate(langs):
        variant_id = f"l{i + 2}"  # l2, l3, l4, ...
        lang_base = lang.split("-")[0] if "-" in lang else lang
        variants.append(
            {
                "id": variant_id,
                "lang": lang,
                "voice_id": f"default_{lang_base}",
                "notes_translate": True,
            }
        )
    return variants


def get_variant_path_prefix(variant_id: str) -> str:
    """Return path prefix for variant: 'script/en/', 'audio/en/', etc."""
    return f"{variant_id}/"
