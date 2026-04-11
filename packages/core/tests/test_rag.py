"""
Tests for rag.py: _tokenize, _tf, _idf, tfidf_retrieve, retrieve_chunk_ids.
Pure Python – no external dependencies to mock.
"""
from __future__ import annotations

import os
import sys
import math

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rag import _tokenize, _tf, _idf, tfidf_retrieve, retrieve_chunk_ids


# ---------------------------------------------------------------------------
# _tokenize
# ---------------------------------------------------------------------------

def test_tokenize_lowercases():
    assert _tokenize("Hello World") == ["hello", "world"]


def test_tokenize_removes_punctuation():
    tokens = _tokenize("foo, bar! baz.")
    assert tokens == ["foo", "bar", "baz"]


def test_tokenize_empty_string():
    assert _tokenize("") == []


def test_tokenize_keeps_digits():
    tokens = _tokenize("slide123 test")
    assert "slide123" in tokens
    assert "test" in tokens


def test_tokenize_none_safe():
    # None should be coerced to empty string
    assert _tokenize(None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _tf
# ---------------------------------------------------------------------------

def test_tf_counts_terms():
    from collections import Counter
    counts = _tf(["a", "b", "a", "c"])
    assert counts["a"] == 2
    assert counts["b"] == 1
    assert counts["c"] == 1


def test_tf_empty_list():
    from collections import Counter
    counts = _tf([])
    assert len(counts) == 0


# ---------------------------------------------------------------------------
# _idf
# ---------------------------------------------------------------------------

def test_idf_empty_returns_empty():
    assert _idf([]) == {}


def test_idf_single_doc():
    result = _idf([["foo", "bar"]])
    # Both terms appear in 1/1 docs, so idf = log(2/2)+1 = 1.0
    assert "foo" in result
    assert "bar" in result
    for v in result.values():
        assert v > 0


def test_idf_penalises_common_terms():
    # "the" appears in all docs; "rare" appears in only one
    docs = [
        ["the", "cat"],
        ["the", "dog"],
        ["the", "rare"],
    ]
    idf = _idf(docs)
    assert idf["rare"] > idf["the"]


# ---------------------------------------------------------------------------
# tfidf_retrieve
# ---------------------------------------------------------------------------

CHUNKS = [
    {"id": "c1", "text": "machine learning model training"},
    {"id": "c2", "text": "neural network deep learning architecture"},
    {"id": "c3", "text": "random forest decision tree ensemble"},
]


def test_tfidf_retrieve_returns_top_match():
    results = tfidf_retrieve("machine learning", CHUNKS)
    assert results[0][0] == "c1"


def test_tfidf_retrieve_respects_top_k():
    results = tfidf_retrieve("learning", CHUNKS, top_k=2)
    assert len(results) <= 2


def test_tfidf_retrieve_empty_chunks():
    assert tfidf_retrieve("query", []) == []


def test_tfidf_retrieve_empty_query():
    assert tfidf_retrieve("", CHUNKS) == []


def test_tfidf_retrieve_scores_sorted_descending():
    results = tfidf_retrieve("learning", CHUNKS, top_k=5)
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)


def test_tfidf_retrieve_no_match_returns_empty():
    # Query has zero overlap with any chunk
    result = tfidf_retrieve("zzzzxxx", CHUNKS)
    assert result == []


# ---------------------------------------------------------------------------
# retrieve_chunk_ids
# ---------------------------------------------------------------------------

def test_retrieve_chunk_ids_returns_id_list():
    ids = retrieve_chunk_ids("machine learning", CHUNKS)
    assert isinstance(ids, list)
    assert ids[0] == "c1"


def test_retrieve_chunk_ids_top_k_respected():
    ids = retrieve_chunk_ids("learning", CHUNKS, top_k=1)
    assert len(ids) == 1


def test_retrieve_chunk_ids_empty_query_returns_empty():
    assert retrieve_chunk_ids("", CHUNKS) == []
