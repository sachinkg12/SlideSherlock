"""
RAG hook: if docs enabled, retrieve chunks.
Simple tf-idf first; vector DB optional (not implemented here).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Tuple


def _tokenize(text: str) -> List[str]:
    """Lowercase tokenize; keep alphanumeric."""
    text = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return tokens


def _tf(tokens: List[str]) -> Counter:
    """Term frequencies for a document."""
    return Counter(tokens)


def _idf(doc_tokens: List[List[str]]) -> Dict[str, float]:
    """Inverse document frequency: log(N / (df + 1))."""
    n = len(doc_tokens)
    if n == 0:
        return {}
    df: Counter = Counter()
    for tokens in doc_tokens:
        for t in set(tokens):
            df[t] += 1
    return {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}


def tfidf_retrieve(
    query: str,
    chunks: List[Dict[str, Any]],
    text_key: str = "text",
    id_key: str = "id",
    top_k: int = 5,
) -> List[Tuple[str, float]]:
    """
    Simple tf-idf retrieval: score query against chunks, return top_k (chunk_id, score).
    chunks: list of dicts with id_key and text_key (e.g. {"id": "c1", "text": "..."}).
    """
    if not chunks:
        return []
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    doc_tokens = [_tokenize((c.get(text_key) or "")) for c in chunks]
    idf_map = _idf(doc_tokens)

    scores: List[Tuple[str, float]] = []
    for i, c in enumerate(chunks):
        doc_tok = doc_tokens[i]
        if not doc_tok:
            continue
        tf_d = _tf(doc_tok)
        score = 0.0
        for t in q_tokens:
            score += tf_d.get(t, 0) * idf_map.get(t, 1.0)
        if score > 0:
            cid = c.get(id_key) or str(i)
            scores.append((cid, score))

    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]


def retrieve_chunk_ids(
    query: str,
    chunks: List[Dict[str, Any]],
    text_key: str = "text",
    id_key: str = "id",
    top_k: int = 5,
) -> List[str]:
    """
    Return list of chunk ids for top_k matches (RAG hook).
    Use this when docs are enabled to pass chunk ids into explain plan / script.
    """
    scored = tfidf_retrieve(query, chunks, text_key=text_key, id_key=id_key, top_k=top_k)
    return [cid for cid, _ in scored]
