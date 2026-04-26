"""Pipeline: retrieve same-facility chunks and run the Validator agent.

Closes the audit's P0 gap (`docs/DATABRICKS_AUDIT.md`): the Validator's
``retrieved_evidence`` parameter was production-only on paper. This module
loads ``tables/capabilities.parquet`` (extractor output), pulls top-k
same-facility chunks via :func:`seahealth.db.retriever.get_retriever`, builds
``FacilityFacts`` from ``tables/facilities_index.parquet``, calls
:func:`seahealth.agents.validator.validate_capability`, and writes:

* ``tables/contradictions.parquet`` — one row per detected ``Contradiction``
  with a top-level ``payload`` JSON column matching what
  :func:`seahealth.pipelines.build_audits._contradiction_from_row` consumes.
* ``tables/evidence_assessments.parquet`` — same shape for
  ``EvidenceAssessment``.

LLM mode is opt-in (``--use-llm`` / ``use_llm=True``); the heuristic-only
default exercises the retriever wiring + parquet plumbing without a network
dependency. The pipeline-level work is wrapped in a ``seahealth.validate``
MLflow span; the per-capability work nests under the validator + scorer spans
already added in Phase B step 1.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seahealth.agents._mlflow_helpers import mlflow_span
from seahealth.agents.heuristics import FacilityFacts
from seahealth.agents.llm_client import get_validator_client
from seahealth.agents.validator import validate_capability
from seahealth.db.retriever import describe_retriever_mode, get_retriever
from seahealth.schemas import (
    Capability,
    CapabilityType,
    Contradiction,
    EvidenceAssessment,
    EvidenceRef,
    IndexedDoc,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TABLES_DIR = REPO_ROOT / "tables"

CAPABILITIES_FILE = "capabilities.parquet"
FACILITIES_INDEX_FILE = "facilities_index.parquet"
DEMO_SUBSET_FILE = "demo_subset.json"
CONTRADICTIONS_FILE = "contradictions.parquet"
EVIDENCE_ASSESSMENTS_FILE = "evidence_assessments.parquet"

DEFAULT_TOP_K = 5

CONTRADICTION_DELTA_FQN = "seahealth.silver.contradictions"
EVIDENCE_DELTA_FQN = "seahealth.silver.evidence_assessments"


# ---------------------------------------------------------------------------
# Parquet readers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _row_value(row: pd.Series, key: str) -> Any:
    if key not in row.index:
        return None
    value = row[key]
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def _parse_evidence_refs(raw: Any) -> list[EvidenceRef]:
    if raw is None:
        return []
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
    else:
        data = raw
    if not isinstance(data, list):
        return []
    refs: list[EvidenceRef] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        try:
            refs.append(EvidenceRef.model_validate(entry))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("dropping malformed EvidenceRef: %s", exc)
    return refs


def _capability_from_row(row: pd.Series) -> Capability | None:
    """Reconstruct a Capability from one row of capabilities.parquet."""
    try:
        cap_type = CapabilityType(_row_value(row, "capability_type"))
    except (TypeError, ValueError):
        return None
    facility_id = _row_value(row, "facility_id")
    if not facility_id:
        return None

    extracted_at = _row_value(row, "extracted_at")
    if isinstance(extracted_at, str):
        try:
            extracted_at = datetime.fromisoformat(extracted_at.replace("Z", "+00:00"))
        except Exception:
            extracted_at = _utcnow()
    elif extracted_at is None:
        extracted_at = _utcnow()

    claimed_raw = _row_value(row, "claimed")
    trace_raw = _row_value(row, "mlflow_trace_id")
    try:
        return Capability(
            facility_id=str(facility_id),
            capability_type=cap_type,
            claimed=bool(claimed_raw if claimed_raw is not None else True),
            evidence_refs=_parse_evidence_refs(_row_value(row, "evidence_refs_json")),
            source_doc_id=str(_row_value(row, "source_doc_id") or facility_id),
            extracted_at=extracted_at,
            extractor_model=str(_row_value(row, "extractor_model") or "unknown"),
            mlflow_trace_id=str(trace_raw) if trace_raw is not None else None,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("skipping malformed capability row: %s", exc)
        return None


def _load_capabilities(path: Path) -> list[Capability]:
    if not path.exists():
        raise FileNotFoundError(f"capabilities parquet not found: {path}")
    df = pq.read_table(path).to_pandas()
    out: list[Capability] = []
    for _, row in df.iterrows():
        cap = _capability_from_row(row)
        if cap is not None:
            out.append(cap)
    return out


def _facts_from_index_row(row: pd.Series) -> FacilityFacts:
    facility_id = str(_row_value(row, "facility_id") or "")

    def _opt_int(key: str) -> int | None:
        value = _row_value(row, key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return FacilityFacts(
        facility_id=facility_id,
        equipment=[],
        staff_count=_opt_int("numberDoctors"),
        capacity_beds=_opt_int("capacity"),
        # ``recency_of_page_update`` is a free-text string in the source CSV
        # (e.g. ``"3 months"``). A robust parser is out of scope; we leave
        # ``recency_of_page_update_months`` as ``None`` and rely on the
        # validator's heuristic to skip STALE_DATA when missing.
        recency_of_page_update_months=None,
        specialties=[],
        procedures=[],
        capability_claims=[],
    )


def _load_facts_index(path: Path) -> dict[str, FacilityFacts]:
    if not path.exists():
        logger.warning("facilities_index parquet missing; using empty FacilityFacts: %s", path)
        return {}
    df = pq.read_table(path).to_pandas()
    out: dict[str, FacilityFacts] = {}
    for _, row in df.iterrows():
        facts = _facts_from_index_row(row)
        if facts.facility_id:
            out[facts.facility_id] = facts
    return out


def _load_subset(subset_path: Path, subset: str) -> set[str] | None:
    if not subset_path.exists() or subset is None or subset == "all":
        return None
    payload = json.loads(subset_path.read_text(encoding="utf-8"))
    ids = payload.get("facility_ids") or []
    return {str(i) for i in ids}


# ---------------------------------------------------------------------------
# IndexedDoc → EvidenceRef
# ---------------------------------------------------------------------------


_SNIPPET_MAX_CHARS = 512


def _indexed_doc_to_evidence_ref(
    doc: IndexedDoc,
    *,
    facility_id: str,
    retrieved_at: datetime,
) -> EvidenceRef:
    """Convert a retrieval hit into an ``EvidenceRef`` the Validator can adjudicate.

    * ``IndexedDoc.doc_id`` is the upstream ``chunk_id`` (see
      ``retriever._row_to_indexed_doc``); we use it as ``EvidenceRef.chunk_id``.
    * ``source_doc_id`` falls back to ``facility_id`` when retrieval doesn't
      project the column (Mosaic VS only returns chunk_id/facility_id/
      source_type/text).
    * Span defaults to ``(0, 0)`` when the retriever doesn't carry character
      offsets — same convention the extractor uses before re-anchoring.
    """
    metadata = doc.metadata or {}
    source_doc_id = metadata.get("source_doc_id") or facility_id
    span_start_raw = metadata.get("span_start")
    span_end_raw = metadata.get("span_end")
    try:
        span_start = int(span_start_raw) if span_start_raw is not None else 0
        span_end = int(span_end_raw) if span_end_raw is not None else 0
    except (TypeError, ValueError):
        span_start, span_end = 0, 0
    if span_end < span_start:
        span_start, span_end = 0, 0

    snippet = (doc.text or "").strip()
    if len(snippet) > _SNIPPET_MAX_CHARS:
        snippet = snippet[:_SNIPPET_MAX_CHARS].rstrip()

    return EvidenceRef(
        source_doc_id=str(source_doc_id),
        facility_id=facility_id,
        chunk_id=str(doc.doc_id),
        row_id=None,
        span=(span_start, span_end),
        snippet=snippet,
        source_type=doc.source_type,
        source_observed_at=doc.source_observed_at,
        retrieved_at=retrieved_at,
    )


def _build_retrieval_query(cap: Capability, facts: FacilityFacts) -> str:
    """Compose a small free-text query for same-facility semantic retrieval."""
    parts = [cap.capability_type.value.replace("_", " ").lower()]
    if facts.facility_id:
        parts.append(facts.facility_id)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Parquet writers
# ---------------------------------------------------------------------------


def _contradiction_to_row(c: Contradiction) -> dict[str, Any]:
    return {
        "facility_id": c.facility_id,
        "capability_type": c.capability_type.value,
        "contradiction_type": c.contradiction_type.value,
        "severity": c.severity,
        "detected_by": c.detected_by,
        "payload": json.dumps(c.model_dump(mode="json"), ensure_ascii=False, allow_nan=False),
    }


def _assessment_to_row(a: EvidenceAssessment) -> dict[str, Any]:
    return {
        "facility_id": a.facility_id,
        "capability_type": a.capability_type.value,
        "evidence_ref_id": a.evidence_ref_id,
        "stance": a.stance,
        "payload": json.dumps(a.model_dump(mode="json"), ensure_ascii=False, allow_nan=False),
    }


_CONTRADICTION_COLUMNS = (
    "facility_id",
    "capability_type",
    "contradiction_type",
    "severity",
    "detected_by",
    "payload",
)
_ASSESSMENT_COLUMNS = (
    "facility_id",
    "capability_type",
    "evidence_ref_id",
    "stance",
    "payload",
)


def _write_parquet(
    rows: list[dict[str, Any]], path: Path, *, columns: tuple[str, ...]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        df = pd.DataFrame.from_records(rows)
    else:
        df = pd.DataFrame(columns=list(columns))
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp_path)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Best-effort Delta mirror
# ---------------------------------------------------------------------------


def _maybe_get_sql_executor():
    try:
        module = importlib.import_module("seahealth.db.sql_warehouse")
    except Exception:
        return None
    return getattr(module, "execute_sql", None)


def _maybe_mirror_to_delta(
    contradiction_rows: list[dict[str, Any]],
    assessment_rows: list[dict[str, Any]],
) -> dict[str, bool]:
    """Best-effort INSERT into silver Delta tables. Never fatal."""
    import os

    written = {"contradictions": False, "evidence_assessments": False}
    if not os.environ.get("DATABRICKS_HOST"):
        return written
    executor = _maybe_get_sql_executor()
    if executor is None:
        return written
    try:  # pragma: no cover - exercised only against a live workspace
        for row in contradiction_rows:
            executor(
                f"INSERT INTO {CONTRADICTION_DELTA_FQN} (facility_id, capability_type, "
                "contradiction_type, severity, detected_by, payload) VALUES "
                "(:facility_id, :capability_type, :contradiction_type, :severity, "
                ":detected_by, :payload)",
                params=row,
            )
        written["contradictions"] = bool(contradiction_rows)
    except Exception as exc:
        logger.warning("contradictions delta mirror skipped: %s", exc)
    try:  # pragma: no cover - exercised only against a live workspace
        for row in assessment_rows:
            executor(
                f"INSERT INTO {EVIDENCE_DELTA_FQN} (facility_id, capability_type, "
                "evidence_ref_id, stance, payload) VALUES "
                "(:facility_id, :capability_type, :evidence_ref_id, :stance, :payload)",
                params=row,
            )
        written["evidence_assessments"] = bool(assessment_rows)
    except Exception as exc:
        logger.warning("evidence_assessments delta mirror skipped: %s", exc)
    return written


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def main(
    *,
    subset: str | None = "demo",
    limit: int | None = None,
    use_llm: bool = False,
    top_k: int = DEFAULT_TOP_K,
    tables_dir: str | Path | None = None,
    capabilities_path: str | Path | None = None,
    facilities_index_path: str | Path | None = None,
    subset_path: str | Path | None = None,
    contradictions_out: str | Path | None = None,
    assessments_out: str | Path | None = None,
    retriever: Any | None = None,
    client_factory: Any | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run validation over previously-extracted capabilities.

    Args:
        subset: ``"demo"`` restricts to ``demo_subset.json``; ``"all"`` /
            ``None`` processes every facility in capabilities parquet.
        limit: Cap the number of facilities processed.
        use_llm: When True, route the LLM Validator through
            :func:`seahealth.agents.llm_client.get_validator_client`.
        top_k: Top-k chunks retrieved per capability.
        tables_dir: Override for ``<repo>/tables``.
        retriever: Override the retriever (handy for tests).
        client_factory: Override the validator LLM client factory.
        model: Override the validator model id passed to ``validate_capability``.

    Returns:
        Summary dict with input/output counts.
    """
    tdir = Path(tables_dir) if tables_dir is not None else DEFAULT_TABLES_DIR
    cap_path = (
        Path(capabilities_path)
        if capabilities_path is not None
        else tdir / CAPABILITIES_FILE
    )
    idx_path = (
        Path(facilities_index_path)
        if facilities_index_path is not None
        else tdir / FACILITIES_INDEX_FILE
    )
    sub_path = Path(subset_path) if subset_path is not None else tdir / DEMO_SUBSET_FILE
    contradictions_path = (
        Path(contradictions_out) if contradictions_out is not None else tdir / CONTRADICTIONS_FILE
    )
    assessments_path = (
        Path(assessments_out) if assessments_out is not None else tdir / EVIDENCE_ASSESSMENTS_FILE
    )

    capabilities = _load_capabilities(cap_path)
    facts_by_id = _load_facts_index(idx_path)
    keep_ids = _load_subset(sub_path, subset or "all")

    if keep_ids is not None:
        capabilities = [c for c in capabilities if c.facility_id in keep_ids]

    if limit is not None:
        seen_ids: list[str] = []
        kept: list[Capability] = []
        for cap in capabilities:
            if cap.facility_id not in seen_ids:
                if len(seen_ids) >= limit:
                    continue
                seen_ids.append(cap.facility_id)
            kept.append(cap)
        capabilities = kept

    retriever_obj = retriever if retriever is not None else get_retriever()
    if client_factory is not None:
        factory = client_factory
    else:
        factory = get_validator_client if use_llm else None

    contradiction_rows: list[dict[str, Any]] = []
    assessment_rows: list[dict[str, Any]] = []
    facility_ids: set[str] = set()
    failed_count = 0

    retriever_snapshot = describe_retriever_mode()

    pipeline_attrs = {
        "use_llm": use_llm,
        "top_k": top_k,
        "capability_count": len(capabilities),
        "retriever_mode": str(retriever_snapshot.get("mode")),
    }

    with mlflow_span("seahealth.validate", attrs=pipeline_attrs):
        retrieved_at = _utcnow()
        for cap in capabilities:
            facility_ids.add(cap.facility_id)
            facts = facts_by_id.get(cap.facility_id) or FacilityFacts(facility_id=cap.facility_id)
            try:
                hits = retriever_obj.search(
                    _build_retrieval_query(cap, facts), top_k, facility_id=cap.facility_id
                )
            except Exception as exc:  # pragma: no cover - retriever is best-effort
                logger.warning("retriever.search failed for %s: %s", cap.facility_id, exc)
                hits = []
            evidence = [
                _indexed_doc_to_evidence_ref(
                    doc, facility_id=cap.facility_id, retrieved_at=retrieved_at
                )
                for doc in hits
            ]
            try:
                kwargs: dict[str, Any] = {
                    "use_llm": use_llm,
                    "client_factory": factory,
                }
                if model is not None:
                    kwargs["model"] = model
                contradictions, assessments = validate_capability(
                    cap, facts, evidence, **kwargs
                )
            except Exception as exc:
                failed_count += 1
                logger.warning(
                    "validate_capability failed for %s/%s: %s",
                    cap.facility_id,
                    cap.capability_type.value,
                    exc,
                )
                continue
            contradiction_rows.extend(_contradiction_to_row(c) for c in contradictions)
            assessment_rows.extend(_assessment_to_row(a) for a in assessments)

    _write_parquet(contradiction_rows, contradictions_path, columns=_CONTRADICTION_COLUMNS)
    _write_parquet(assessment_rows, assessments_path, columns=_ASSESSMENT_COLUMNS)
    delta_written = _maybe_mirror_to_delta(contradiction_rows, assessment_rows)

    summary = {
        "facility_count": len(facility_ids),
        "capability_count": len(capabilities),
        "contradiction_count": len(contradiction_rows),
        "assessment_count": len(assessment_rows),
        "failed_count": failed_count,
        "use_llm": use_llm,
        "retriever_mode": retriever_snapshot.get("mode"),
        "contradictions_path": str(contradictions_path),
        "evidence_assessments_path": str(assessments_path),
        "delta_written": delta_written,
    }
    print(
        "[validate] facilities={f} capabilities={c} contradictions={x} "
        "assessments={a} retriever={r} use_llm={u}".format(
            f=summary["facility_count"],
            c=summary["capability_count"],
            x=summary["contradiction_count"],
            a=summary["assessment_count"],
            r=summary["retriever_mode"],
            u=summary["use_llm"],
        )
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the SeaHealth validator pipeline.")
    p.add_argument("--subset", type=str, default="demo", help="'demo' | 'all'")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable the LLM Validator pass (requires OPENROUTER_API_KEY or DATABRICKS_TOKEN).",
    )
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    p.add_argument("--tables-dir", type=str, default=None)
    p.add_argument("--model", type=str, default=None)
    return p


def _cli(argv: Iterable[str] | None = None) -> None:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    main(
        subset=args.subset,
        limit=args.limit,
        use_llm=args.use_llm,
        top_k=args.top_k,
        tables_dir=args.tables_dir,
        model=args.model,
    )


if __name__ == "__main__":  # pragma: no cover
    _cli()


__all__ = ["main"]
