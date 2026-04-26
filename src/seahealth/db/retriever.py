"""Unified retriever interface for SeaHealth agents.

Agents call :func:`get_retriever` to obtain a :class:`Retriever`. The concrete
implementation depends on what's available in the workspace at runtime:

  * :class:`VectorSearchRetriever` — wraps the Databricks Vector Search SDK
    when a working endpoint + index pair is available.
  * :class:`FaissRetriever` — purely local fallback over a Parquet file of
    chunks. Tries (in order) FAISS+sentence-transformers, BM25, then a
    dependency-free TF-cosine implementation. The TF path always works with
    just ``pyarrow`` and ``pandas`` from ``pyproject.toml``.

Both retrievers return a list of :class:`~seahealth.schemas.IndexedDoc`
instances. The retriever does NOT compute real 1024-d embeddings for the
fallback paths — it returns zero-vectors of the right length so downstream
code that inspects ``IndexedDoc.embedding`` keeps validating. This matches the
project rule that the production embedding model is BAAI/bge-large-en-v1.5
(1024 dim) — the fallback is for offline tests and emergency runs only.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from seahealth.schemas import EMBEDDING_DIM, IndexedDoc

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


# --------------------------------------------------------------------------- #
# Protocol
# --------------------------------------------------------------------------- #

class Retriever(Protocol):
    """Common surface every retriever exposes to agents."""

    def search(
        self, query: str, k: int, facility_id: str | None = None
    ) -> list[IndexedDoc]:
        """Return the top-``k`` chunks ranked by relevance to ``query``.

        Args:
            query: free-text query.
            k: number of results.
            facility_id: when given, restrict to chunks whose ``facility_id``
                matches.
        """
        ...


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _redact_secrets(value: object) -> str:
    return _BEARER_RE.sub("Bearer [REDACTED]", str(value))


def _validate_identifier(identifier: str, *, kind: str = "identifier") -> str:
    if not _IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(
            f"invalid {kind} {identifier!r}; expected pattern [A-Za-z0-9_]+"
        )
    return identifier


def _validate_fq_table(value: str, *, kind: str = "table") -> str:
    parts = value.split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid {kind} {value!r}; expected catalog.schema.table")
    for label, part in zip(("catalog", "schema", "table"), parts, strict=True):
        _validate_identifier(part, kind=f"{kind} {label}")
    return value


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _zero_embedding() -> list[float]:
    """Placeholder embedding for fallback retrievers (real model = bge-1024d)."""
    return [0.0] * EMBEDDING_DIM


def _text_values(df: pd.DataFrame) -> list[str]:
    """Return text values without turning missing/null text into the token 'None'."""
    if "text" not in df.columns:
        return [""] * len(df)
    return df["text"].fillna("").astype(str).tolist()


def _clean_text(value: Any) -> str:
    """Normalize nullable dataframe text values for IndexedDoc output."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value)


def _row_to_indexed_doc(row: dict[str, Any]) -> IndexedDoc:
    """Best-effort conversion of a chunks-table row into :class:`IndexedDoc`."""
    raw_observed = row.get("source_observed_at") or row.get("indexed_at")
    observed: datetime | None = None
    if isinstance(raw_observed, str):
        try:
            observed = datetime.fromisoformat(raw_observed.replace("Z", "+00:00"))
        except Exception:
            observed = None
    elif isinstance(raw_observed, datetime):
        observed = raw_observed

    metadata: dict[str, str] = {}
    span_start = row.get("span_start")
    span_end = row.get("span_end")
    if span_start is not None:
        metadata["span_start"] = str(span_start)
    if span_end is not None:
        metadata["span_end"] = str(span_end)
    if "source_doc_id" in row and row["source_doc_id"] is not None:
        metadata["source_doc_id"] = str(row["source_doc_id"])

    return IndexedDoc(
        doc_id=str(row.get("chunk_id") or row.get("doc_id") or ""),
        facility_id=row.get("facility_id"),
        text=_clean_text(row.get("text")),
        embedding=_zero_embedding(),
        chunk_index=int(row.get("row_index") or row.get("chunk_index") or 0),
        source_type=row.get("source_type") or "facility_note",  # type: ignore[arg-type]
        source_observed_at=observed,
        metadata=metadata,
    )


# --------------------------------------------------------------------------- #
# FAISS / BM25 / TF fallback retriever
# --------------------------------------------------------------------------- #

@dataclass
class FaissRetriever:
    """In-memory retriever over a chunks-table Parquet file or DataFrame.

    Despite the name, this class transparently picks the best available scoring
    backend at construction time:

    1. ``faiss`` + ``sentence_transformers`` if both are importable (true dense
       retrieval).
    2. ``rank_bm25`` if importable.
    3. A dependency-free TF / cosine similarity over token bags. This always
       works with the project's baseline deps.
    """

    df: pd.DataFrame
    backend: str = "tf"  # one of {"faiss", "bm25", "tf"}
    _model: Any = None
    _index: Any = None
    _bm25: Any = None
    _doc_vectors: list[Counter] | None = None
    _doc_norms: list[float] | None = None

    def __post_init__(self) -> None:
        if self.df.empty:
            self._doc_vectors = []
            self._doc_norms = []
            return
        texts = _text_values(self.df)

        # Try dense retrieval first.
        try:
            import faiss  # type: ignore
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            embs = self._model.encode(
                texts,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            self._index = faiss.IndexFlatIP(embs.shape[1])
            self._index.add(embs)
            self.backend = "faiss"
            return
        except Exception:  # pragma: no cover - depends on optional deps
            pass

        # Try BM25.
        try:
            from rank_bm25 import BM25Okapi  # type: ignore

            tokenized = [_tokenize(t) for t in texts]
            if any(tokenized):
                self._bm25 = BM25Okapi(tokenized)
                self.backend = "bm25"
                return
        except Exception:
            pass

        # Default: dependency-free TF / cosine.
        vectors: list[Counter] = []
        norms: list[float] = []
        for text in texts:
            counts = Counter(_tokenize(text))
            vectors.append(counts)
            norms.append(math.sqrt(sum(c * c for c in counts.values())) or 1.0)
        self._doc_vectors = vectors
        self._doc_norms = norms
        self.backend = "tf"

    # ----- protocol ---------------------------------------------------- #

    def search(
        self, query: str, k: int, facility_id: str | None = None
    ) -> list[IndexedDoc]:
        if self.df.empty or k <= 0 or not _tokenize(query):
            return []

        scores: list[float]
        if self.backend == "faiss":
            assert self._model is not None and self._index is not None
            q = self._model.encode([query], normalize_embeddings=True)
            distances, indices = self._index.search(q, len(self.df))
            scores = [0.0] * len(self.df)
            for d, i in zip(distances[0], indices[0], strict=False):
                if 0 <= int(i) < len(scores):
                    scores[int(i)] = float(d)
        elif self.backend == "bm25":
            assert self._bm25 is not None
            scores = list(self._bm25.get_scores(_tokenize(query)))
        else:
            scores = self._tf_scores(query)

        # Apply facility filter and pick top-k.
        rows = self.df.to_dict("records")
        scored: list[tuple[float, dict[str, Any]]] = []
        for score, row in zip(scores, rows, strict=True):
            if facility_id is not None and row.get("facility_id") != facility_id:
                continue
            scored.append((score, row))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:k]
        return [_row_to_indexed_doc(row) for _, row in top]

    # ----- TF/cosine implementation ------------------------------------ #

    def _tf_scores(self, query: str) -> list[float]:
        assert self._doc_vectors is not None and self._doc_norms is not None
        q_counts = Counter(_tokenize(query))
        if not q_counts:
            return [0.0] * len(self._doc_vectors)
        q_norm = math.sqrt(sum(c * c for c in q_counts.values())) or 1.0
        out: list[float] = []
        for doc_vec, doc_norm in zip(self._doc_vectors, self._doc_norms, strict=True):
            if not doc_vec:
                out.append(0.0)
                continue
            # Iterate the smaller dict for speed.
            small, large = (
                (q_counts, doc_vec)
                if len(q_counts) <= len(doc_vec)
                else (doc_vec, q_counts)
            )
            dot = 0
            for tok, cnt in small.items():
                dot += cnt * large.get(tok, 0)
            out.append(dot / (q_norm * doc_norm))
        return out


# --------------------------------------------------------------------------- #
# Vector Search retriever
# --------------------------------------------------------------------------- #

@dataclass
class VectorSearchRetriever:
    """Wraps the Databricks Vector Search SDK.

    Constructor expects an endpoint name + index name. Search uses similarity
    search over the index ``text`` column and projects ``chunk_id``,
    ``facility_id``, ``source_type``, ``text`` columns.
    """

    endpoint_name: str
    index_name: str
    _client: Any = None

    def __post_init__(self) -> None:  # pragma: no cover - exercised live only
        if not self.endpoint_name:
            raise ValueError("endpoint_name is required")
        _validate_fq_table(self.index_name, kind="vector search index")
        try:
            from databricks.vector_search.client import VectorSearchClient  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                f"databricks-vectorsearch not installed: {exc}"
            ) from exc
        self._client = VectorSearchClient()

    def search(
        self, query: str, k: int, facility_id: str | None = None
    ) -> list[IndexedDoc]:  # pragma: no cover - live only
        if k <= 0 or not _tokenize(query):
            return []
        idx = self._client.get_index(
            endpoint_name=self.endpoint_name, index_name=self.index_name
        )
        kwargs: dict[str, Any] = dict(
            query_text=query,
            num_results=k,
            columns=["chunk_id", "facility_id", "source_type", "text"],
        )
        if facility_id is not None:
            kwargs["filters_json"] = json.dumps({"facility_id": facility_id})
        result = idx.similarity_search(**kwargs)

        # Result shape:
        # {"result": {"data_array": [[chunk_id, facility_id, source_type, text, score], ...],
        #             "row_count": N},
        #  "manifest": {"columns": [...]}}
        data = result.get("result", {}).get("data_array", []) or []
        cols = [c["name"] for c in result.get("manifest", {}).get("columns", [])]
        out: list[IndexedDoc] = []
        for row in data:
            row_dict = {col: val for col, val in zip(cols, row, strict=False)}
            out.append(_row_to_indexed_doc(row_dict))
        return out


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

def _default_chunks_parquet_paths() -> list[Path]:
    """Resolve the chunks-parquet candidate list, env-var first.

    ``SEAHEALTH_CHUNKS_PARQUET`` (when set) is tried before the project-relative
    and absolute developer-machine fallbacks.
    """
    env_path = os.environ.get("SEAHEALTH_CHUNKS_PARQUET")
    paths: list[Path] = []
    if env_path:
        paths.append(Path(env_path))
    paths.extend([
        Path(__file__).resolve().parents[3] / "tables" / "chunks.parquet",
        # Last-resort absolute fallback for the original developer machine.
        Path("/Users/alejandro/Desktop/seahealth/tables/chunks.parquet"),
    ])
    return paths


DEFAULT_CHUNKS_PARQUET_PATHS: Sequence[Path] = tuple(_default_chunks_parquet_paths())


def _load_chunks_dataframe(path: Path | None = None) -> pd.DataFrame:
    """Load the chunks Parquet from disk; returns an empty DataFrame if missing."""
    candidates: Iterable[Path]
    if path is not None:
        candidates = [path]
    else:
        candidates = DEFAULT_CHUNKS_PARQUET_PATHS
    for cand in candidates:
        if cand.exists():
            logger.info("retriever: loading chunks from %s", cand)
            return pd.read_parquet(cand)
    logger.warning("retriever: no chunks parquet found; returning empty DataFrame")
    return pd.DataFrame(
        columns=[
            "chunk_id", "facility_id", "row_index", "source_type",
            "source_doc_id", "text", "span_start", "span_end", "indexed_at",
        ]
    )


def get_retriever(
    *,
    endpoint_name: str | None = None,
    index_name: str | None = None,
    chunks_parquet_path: Path | None = None,
) -> Retriever:
    """Return the best available retriever.

    Resolution:
      1. If both ``endpoint_name`` and ``index_name`` are given (or set via
         ``SEAHEALTH_VS_ENDPOINT`` / ``SEAHEALTH_VS_INDEX`` env vars), try a
         :class:`VectorSearchRetriever`.
      2. Otherwise, return a :class:`FaissRetriever` over the chunks Parquet.
    """
    ep = endpoint_name or os.getenv("SEAHEALTH_VS_ENDPOINT")
    idx = index_name or os.getenv("SEAHEALTH_VS_INDEX")
    if ep and idx:
        try:
            return VectorSearchRetriever(endpoint_name=ep, index_name=idx)
        except Exception as exc:
            logger.warning(
                "retriever: VectorSearch unavailable (%s); falling back to FAISS",
                _redact_secrets(exc),
            )

    df = _load_chunks_dataframe(chunks_parquet_path)
    return FaissRetriever(df=df)


__all__ = [
    "FaissRetriever",
    "Retriever",
    "VectorSearchRetriever",
    "get_retriever",
]


# Suppress unused import warnings for `timezone` (re-exported for callers).
_ = timezone
