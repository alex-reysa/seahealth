"""Offline tests for the retriever fallback path.

These tests intentionally avoid the FAISS / sentence-transformers / BM25
backends and exercise the dependency-free TF/cosine path so they pass on a
minimal install.
"""

from __future__ import annotations

import builtins
import json
from unittest.mock import MagicMock

import pandas as pd
import pytest

from seahealth.db.retriever import (
    FaissRetriever,
    VectorSearchRetriever,
    _load_chunks_dataframe,
    get_retriever,
)


@pytest.fixture
def sample_chunks() -> pd.DataFrame:
    """A tiny chunks DataFrame mirroring the production schema."""
    rows = [
        {
            "chunk_id": "c1",
            "facility_id": "f1",
            "row_index": 0,
            "source_type": "facility_note",
            "source_doc_id": "f1",
            "text": "Apollo Hospital offers cardiology and ICU services with 200 beds.",
            "span_start": 0,
            "span_end": 60,
            "indexed_at": "2026-04-25T20:52:33+00:00",
        },
        {
            "chunk_id": "c2",
            "facility_id": "f2",
            "row_index": 0,
            "source_type": "facility_note",
            "source_doc_id": "f2",
            "text": "Fortis Clinic provides dental cleaning and orthodontic services.",
            "span_start": 0,
            "span_end": 60,
            "indexed_at": "2026-04-25T20:52:33+00:00",
        },
        {
            "chunk_id": "c3",
            "facility_id": "f1",
            "row_index": 1,
            "source_type": "staff_roster",
            "source_doc_id": "f1",
            "text": "Cardiology team includes 4 cardiologists and 12 ICU nurses.",
            "span_start": 0,
            "span_end": 60,
            "indexed_at": "2026-04-25T20:52:33+00:00",
        },
        {
            "chunk_id": "c4",
            "facility_id": "f3",
            "row_index": 0,
            "source_type": "facility_note",
            "source_doc_id": "f3",
            "text": "Children's clinic with pediatric vaccinations only.",
            "span_start": 0,
            "span_end": 50,
            "indexed_at": "2026-04-25T20:52:33+00:00",
        },
    ]
    return pd.DataFrame(rows)


def test_tf_retriever_finds_top_match(sample_chunks):
    """A query mentioning 'cardiology' should rank the cardiology chunks first."""
    retriever = FaissRetriever(df=sample_chunks)
    # We expect TF backend in test env (no faiss/bm25 installed).
    assert retriever.backend in {"tf", "bm25", "faiss"}
    results = retriever.search("cardiology services", k=2)
    assert len(results) == 2
    # Top result must be one of the cardiology chunks.
    assert results[0].doc_id in {"c1", "c3"}
    assert all(r.text for r in results)


def test_facility_filter_restricts_results(sample_chunks):
    """``facility_id`` parameter should restrict to that facility only."""
    retriever = FaissRetriever(df=sample_chunks)
    results = retriever.search("services", k=4, facility_id="f1")
    assert all(r.facility_id == "f1" for r in results)
    assert {r.doc_id for r in results} <= {"c1", "c3"}


def test_empty_dataframe_returns_empty_list():
    """An empty corpus must not crash and must yield an empty result list."""
    df = pd.DataFrame(
        columns=[
            "chunk_id", "facility_id", "row_index", "source_type",
            "source_doc_id", "text", "span_start", "span_end", "indexed_at",
        ]
    )
    retriever = FaissRetriever(df=df)
    assert retriever.search("anything", k=5) == []


def test_zero_text_tf_fallback_is_safe(monkeypatch):
    """Missing/null text must not crash or become a literal 'None' token."""
    real_import = builtins.__import__

    def _block_optional_imports(name, *args, **kwargs):
        if name in {"faiss", "rank_bm25", "sentence_transformers"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_optional_imports)
    df = pd.DataFrame(
        [
            {"chunk_id": "c1", "facility_id": "f1", "text": ""},
            {"chunk_id": "c2", "facility_id": "f2", "text": None},
            {"chunk_id": "c3", "facility_id": "f3"},
        ]
    )
    retriever = FaissRetriever(df=df)

    assert retriever.backend == "tf"
    assert retriever.search("", k=2) == []
    results = retriever.search("icu", k=3)
    assert len(results) == 3
    assert all(result.text == "" for result in results)


def test_returned_indexed_doc_has_correct_shape(sample_chunks):
    """Returned IndexedDoc must satisfy the 1024-d embedding length contract."""
    from seahealth.schemas import EMBEDDING_DIM

    retriever = FaissRetriever(df=sample_chunks)
    results = retriever.search("dental orthodontic", k=1)
    assert len(results) == 1
    doc = results[0]
    assert doc.doc_id == "c2"
    assert doc.facility_id == "f2"
    assert len(doc.embedding) == EMBEDDING_DIM
    assert doc.source_type == "facility_note"


def test_get_retriever_factory_returns_faiss_when_no_vs(monkeypatch, sample_chunks, tmp_path):
    """Without VS env vars set, the factory should return a FaissRetriever."""
    monkeypatch.delenv("SEAHEALTH_VS_ENDPOINT", raising=False)
    monkeypatch.delenv("SEAHEALTH_VS_INDEX", raising=False)

    parquet_path = tmp_path / "chunks.parquet"
    sample_chunks.to_parquet(parquet_path)

    retriever = get_retriever(chunks_parquet_path=parquet_path)
    assert isinstance(retriever, FaissRetriever)
    # Sanity: it can search.
    results = retriever.search("pediatric vaccinations", k=1)
    assert len(results) == 1
    assert results[0].doc_id == "c4"


def test_load_chunks_dataframe_returns_empty_when_missing(tmp_path):
    """``_load_chunks_dataframe`` returns an empty DataFrame for a missing path."""
    missing = tmp_path / "does_not_exist.parquet"
    df = _load_chunks_dataframe(missing)
    assert len(df) == 0
    # Schema columns should still be present so downstream code can rely on them.
    assert "chunk_id" in df.columns
    assert "text" in df.columns


def test_vector_search_rejects_unsafe_index_name():
    with pytest.raises(ValueError, match="invalid vector search index"):
        VectorSearchRetriever(
            endpoint_name="seahealth-vs",
            index_name="workspace.seahealth_bronze.chunks_index;DROP",
        )


def test_vector_search_filter_is_json_encoded():
    retriever = object.__new__(VectorSearchRetriever)
    retriever.endpoint_name = "seahealth-vs"
    retriever.index_name = "workspace.seahealth_bronze.chunks_index"
    retriever._client = MagicMock()
    index = MagicMock()
    retriever._client.get_index.return_value = index
    index.similarity_search.return_value = {
        "manifest": {
            "columns": [
                {"name": "chunk_id"},
                {"name": "facility_id"},
                {"name": "source_type"},
                {"name": "text"},
            ]
        },
        "result": {
            "data_array": [["c1", 'f"1', "facility_note", "icu"]],
            "row_count": 1,
        },
    }

    results = retriever.search("icu", k=1, facility_id='f"1')

    kwargs = index.similarity_search.call_args.kwargs
    assert json.loads(kwargs["filters_json"]) == {"facility_id": 'f"1'}
    assert kwargs["columns"] == ["chunk_id", "facility_id", "source_type", "text"]
    assert results[0].doc_id == "c1"
