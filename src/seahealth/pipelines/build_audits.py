"""Build per-facility :class:`FacilityAudit` records from Phase-2 parquet outputs.

Reads ``capabilities.parquet`` (Extractor), ``contradictions.parquet`` and
``evidence_assessments.parquet`` (Validator), and ``facilities_index.parquet``
(D-1 normalize) from ``tables/`` and emits one :class:`FacilityAudit` per
facility into ``tables/facility_audits.parquet``.

The audit_count returned dict is suitable for tests and the CLI banner.

Run::

    python -m seahealth.pipelines.build_audits --subset demo

The Delta mirror is best-effort and wrapped in try/except — Phase 4 (K-1) owns
the production write path.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from seahealth.agents.facility_audit_builder import build_facility_audit
from seahealth.agents.trust_scorer import score_capability
from seahealth.schemas import (
    Capability,
    CapabilityType,
    Contradiction,
    EvidenceAssessment,
    FacilityAudit,
    GeoPoint,
)

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TABLES_DIR = REPO_ROOT / "tables"

CAPABILITIES_FILE = "capabilities.parquet"
CONTRADICTIONS_FILE = "contradictions.parquet"
EVIDENCE_FILE = "evidence_assessments.parquet"
FACILITIES_INDEX_FILE = "facilities_index.parquet"
DEMO_SUBSET_FILE = "demo_subset.json"
AUDITS_FILE = "facility_audits.parquet"


# ---------------------------------------------------------------------------
# Parquet IO helpers
# ---------------------------------------------------------------------------


def _read_parquet_or_empty(path: Path) -> pd.DataFrame:
    """Return the parquet at ``path`` or an empty DataFrame if missing."""
    if not path.exists():
        log.info("Optional parquet missing, treating as empty: %s", path)
        return pd.DataFrame()
    try:
        return pq.read_table(path).to_pandas()
    except Exception as exc:
        log.warning("Failed to read parquet %s: %s — treating as empty.", path, exc)
        return pd.DataFrame()


def _row_json_field(row: pd.Series, key: str) -> Any:
    """Pull a column whose value may be a JSON string, dict, or NaN."""
    if key not in row.index:
        return None
    value = row[key]
    if value is None:
        return None
    # pandas may surface NaN for missing string cells.
    if isinstance(value, float):
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


# ---------------------------------------------------------------------------
# Row → schema reconstruction
# ---------------------------------------------------------------------------


def _row_optional_str(row: pd.Series, key: str) -> str | None:
    """Pull an optional string column; tolerate absent column or NaN."""
    if key not in row.index:
        return None
    value = row[key]
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str):
        return value if value.strip() else None
    return str(value)


def _capability_from_row(row: pd.Series) -> Capability | None:
    payload = _row_json_field(row, "payload")
    if isinstance(payload, dict):
        try:
            return Capability.model_validate(payload)
        except Exception as exc:  # pragma: no cover - guarded by parquet schema
            log.warning("Skipping malformed capability row: %s", exc)
            return None
    # Fallback: explicit columns. Only the minimal set we know how to write.
    # ``mlflow_trace_id`` is gracefully optional — old parquet rows produced
    # before the column existed deserialize as None.
    evidence_payload = _row_json_field(row, "evidence_refs")
    if not isinstance(evidence_payload, list):
        evidence_payload = _row_json_field(row, "evidence_refs_json")
    try:
        return Capability(
            facility_id=str(row["facility_id"]),
            capability_type=CapabilityType(row["capability_type"]),
            claimed=bool(row.get("claimed", True)),
            evidence_refs=evidence_payload or [],
            source_doc_id=str(row.get("source_doc_id", row["facility_id"])),
            extracted_at=pd.to_datetime(row.get("extracted_at", datetime.now(UTC))).to_pydatetime(),
            extractor_model=str(row.get("extractor_model", "unknown")),
            mlflow_trace_id=_row_optional_str(row, "mlflow_trace_id"),
        )
    except Exception as exc:
        log.warning("Skipping malformed capability row (fallback): %s", exc)
        return None


def _contradiction_from_row(row: pd.Series) -> Contradiction | None:
    payload = _row_json_field(row, "payload")
    if isinstance(payload, dict):
        try:
            return Contradiction.model_validate(payload)
        except Exception as exc:
            log.warning("Skipping malformed contradiction row: %s", exc)
            return None
    return None


def _assessment_from_row(row: pd.Series) -> EvidenceAssessment | None:
    payload = _row_json_field(row, "payload")
    if isinstance(payload, dict):
        try:
            return EvidenceAssessment.model_validate(payload)
        except Exception as exc:
            log.warning("Skipping malformed evidence_assessment row: %s", exc)
            return None
    return None


def _facilities_index_to_dict(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    if df.empty:
        return by_id
    for _, row in df.iterrows():
        fid = str(row.get("facility_id", "")).strip()
        if not fid:
            continue
        by_id[fid] = {
            "name": str(row.get("name", "") or fid),
            "lat": row.get("latitude"),
            "lng": row.get("longitude"),
            "pin_code": row.get("pin_code"),
        }
    return by_id


def _location_from_index(entry: dict[str, Any] | None) -> GeoPoint:
    if entry is None:
        return GeoPoint(lat=0.0, lng=0.0)
    lat = entry.get("lat")
    lng = entry.get("lng")
    if lat is None or pd.isna(lat):
        lat = 0.0
    if lng is None or pd.isna(lng):
        lng = 0.0
    pin = entry.get("pin_code")
    if pin is None or (isinstance(pin, float) and pd.isna(pin)):
        pin = None
    elif isinstance(pin, str):
        pin = pin if pin.strip() else None
    try:
        return GeoPoint(lat=float(lat), lng=float(lng), pin_code=pin)
    except Exception:
        return GeoPoint(lat=0.0, lng=0.0)


# ---------------------------------------------------------------------------
# Validator integration (lazy import)
# ---------------------------------------------------------------------------


def _maybe_validator() -> Any | None:
    """Return the validator module if importable, else None."""
    try:
        return importlib.import_module("seahealth.agents.validator")
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("validator module unavailable: %s", exc)
        return None


def _maybe_heuristics() -> Any | None:
    try:
        return importlib.import_module("seahealth.agents.heuristics")
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("heuristics module unavailable: %s", exc)
        return None


def _empty_facility_facts(facility_id: str) -> Any:
    """Return a vanilla ``FacilityFacts`` with only the facility_id populated.

    The build_audits pipeline does not currently re-derive facts from raw CSV;
    it relies on contradictions already present in the parquet. The empty
    facts object is supplied so the validator's heuristics path can run as a
    no-op safety net for capabilities lacking validator output.
    """
    heuristics = _maybe_heuristics()
    if heuristics is None:
        return None
    try:
        return heuristics.FacilityFacts(facility_id=facility_id)
    except Exception:  # pragma: no cover - defensive
        return None


# ---------------------------------------------------------------------------
# Audit assembly
# ---------------------------------------------------------------------------


def _group_by_facility(items: Iterable[Any], attr: str = "facility_id") -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for item in items:
        fid = getattr(item, attr, None)
        if fid is None:
            continue
        grouped[str(fid)].append(item)
    return dict(grouped)


def _audit_to_parquet_row(audit: FacilityAudit) -> dict[str, Any]:
    """Render a FacilityAudit as a parquet-friendly row.

    Capabilities, trust_scores, and contradictions are stored as JSON strings
    so the parquet stays simple and language-portable. Phase 4 K-1 will swap
    this for a richer Delta schema.
    """
    return {
        "facility_id": audit.facility_id,
        "name": audit.name,
        "lat": audit.location.lat,
        "lng": audit.location.lng,
        "pin_code": audit.location.pin_code,
        "total_contradictions": int(audit.total_contradictions),
        "last_audited_at": audit.last_audited_at,
        "mlflow_trace_id": audit.mlflow_trace_id,
        "capabilities_json": json.dumps(
            [c.model_dump(mode="json") for c in audit.capabilities],
            ensure_ascii=False,
            allow_nan=False,
        ),
        "trust_scores_json": json.dumps(
            {k.value: v.model_dump(mode="json") for k, v in audit.trust_scores.items()},
            ensure_ascii=False,
            allow_nan=False,
        ),
    }


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        # Write an empty table preserving the expected columns.
        empty_columns = [
            "facility_id",
            "name",
            "lat",
            "lng",
            "pin_code",
            "total_contradictions",
            "last_audited_at",
            "mlflow_trace_id",
            "capabilities_json",
            "trust_scores_json",
        ]
        df = pd.DataFrame(columns=empty_columns)
    else:
        df = pd.DataFrame.from_records(rows)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp_path)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _best_effort_delta_mirror(audits_path: Path) -> None:
    """Best-effort SQL warehouse mirror; never raise."""
    try:
        sql_warehouse = importlib.import_module("seahealth.db.sql_warehouse")
    except Exception as exc:
        log.info("sql_warehouse unavailable; skipping Delta mirror: %s", exc)
        return
    execute_sql = getattr(sql_warehouse, "execute_sql", None)
    if execute_sql is None:
        return
    try:  # pragma: no cover - exercised only in live DBX env
        execute_sql(
            "SELECT 'build_audits.mirror' AS marker, "
            f"'{audits_path.name}' AS source_file"
        )
    except Exception as exc:
        log.info("Delta mirror call failed (ignored): %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def main(
    tables_dir: str | Path | None = None,
    subset: str | None = None,
    *,
    use_llm: bool = False,
    rng_seed: int = 42,
    mlflow_trace_id: str | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Build FacilityAudit rows from parquet inputs.

    Args:
        tables_dir: Override for ``<repo>/tables``. Defaults to repo root.
        subset: When ``"demo"``, restrict to facilities in
            ``tables/demo_subset.json``. Otherwise process every facility
            present in capabilities.parquet.
        use_llm: Forwarded to ``score_capability``.
        rng_seed: Forwarded to ``score_capability``.
        mlflow_trace_id: Optional trace id attached to every emitted audit.
        limit: Cap the number of facilities audited after subset filtering.

    Returns:
        ``{"facility_count", "capability_count", "contradiction_count",
           "audit_count"}`` — handy for tests and the CLI banner.
    """
    tdir = Path(tables_dir) if tables_dir is not None else DEFAULT_TABLES_DIR

    capabilities_df = _read_parquet_or_empty(tdir / CAPABILITIES_FILE)
    contradictions_df = _read_parquet_or_empty(tdir / CONTRADICTIONS_FILE)
    assessments_df = _read_parquet_or_empty(tdir / EVIDENCE_FILE)
    facilities_df = _read_parquet_or_empty(tdir / FACILITIES_INDEX_FILE)

    facilities_index = _facilities_index_to_dict(facilities_df)

    # Reconstruct typed lists.
    capabilities: list[Capability] = []
    if not capabilities_df.empty:
        for _, row in capabilities_df.iterrows():
            cap = _capability_from_row(row)
            if cap is not None:
                capabilities.append(cap)

    contradictions: list[Contradiction] = []
    if not contradictions_df.empty:
        for _, row in contradictions_df.iterrows():
            contradiction = _contradiction_from_row(row)
            if contradiction is not None:
                contradictions.append(contradiction)

    assessments: list[EvidenceAssessment] = []
    if not assessments_df.empty:
        for _, row in assessments_df.iterrows():
            assessment = _assessment_from_row(row)
            if assessment is not None:
                assessments.append(assessment)

    # Optional subset gating.
    allowed_ids: set[str] | None = None
    if subset == "demo":
        demo_path = tdir / DEMO_SUBSET_FILE
        if demo_path.exists():
            try:
                blob = json.loads(demo_path.read_text(encoding="utf-8"))
                ids = blob.get("facility_ids") or []
                allowed_ids = {str(fid) for fid in ids}
            except Exception as exc:
                log.warning("Failed to read demo_subset.json: %s", exc)

    if allowed_ids is not None:
        capabilities = [c for c in capabilities if c.facility_id in allowed_ids]
        contradictions = [c for c in contradictions if c.facility_id in allowed_ids]
        assessments = [a for a in assessments if a.facility_id in allowed_ids]

    capabilities_by_facility = _group_by_facility(capabilities)
    contradictions_by_facility = _group_by_facility(contradictions)
    assessments_by_facility = _group_by_facility(assessments)
    facility_ids = list(facilities_index.keys())
    facility_ids.extend(fid for fid in capabilities_by_facility if fid not in facilities_index)
    if allowed_ids is not None:
        facility_ids = [fid for fid in facility_ids if fid in allowed_ids]

    if limit is not None:
        keep_ids = set(list(capabilities_by_facility)[:limit])
        capabilities_by_facility = {
            fid: caps for fid, caps in capabilities_by_facility.items() if fid in keep_ids
        }
        contradictions_by_facility = {
            fid: items for fid, items in contradictions_by_facility.items() if fid in keep_ids
        }
        assessments_by_facility = {
            fid: items for fid, items in assessments_by_facility.items() if fid in keep_ids
        }
        capabilities = [c for c in capabilities if c.facility_id in keep_ids]
        contradictions = [c for c in contradictions if c.facility_id in keep_ids]
        assessments = [a for a in assessments if a.facility_id in keep_ids]
        facility_ids = [fid for fid in facility_ids if fid in keep_ids]

    validator_module = _maybe_validator()

    audits: list[FacilityAudit] = []
    for facility_id in facility_ids:
        caps = capabilities_by_facility.get(facility_id, [])
        idx_entry = facilities_index.get(facility_id)
        name = idx_entry["name"] if idx_entry else facility_id
        location = _location_from_index(idx_entry)

        facility_contradictions = contradictions_by_facility.get(facility_id, [])
        facility_assessments = assessments_by_facility.get(facility_id, [])

        # Bucket contradictions per-capability for trust scoring.
        contradictions_by_cap: dict[CapabilityType, list[Contradiction]] = defaultdict(list)
        for c in facility_contradictions:
            contradictions_by_cap[c.capability_type].append(c)

        # If a capability has no contradictions and the validator is available,
        # run the heuristics safety net (use_llm=False).
        if validator_module is not None:
            facts = _empty_facility_facts(facility_id)
            if facts is not None:
                for cap in caps:
                    if contradictions_by_cap.get(cap.capability_type):
                        continue
                    try:
                        extra, _extra_assessments = validator_module.validate_capability(
                            cap, facts, use_llm=False
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        log.warning(
                            "validator.validate_capability failed for %s/%s: %s",
                            facility_id,
                            cap.capability_type.value,
                            exc,
                        )
                        continue
                    if extra:
                        contradictions_by_cap[cap.capability_type].extend(extra)
                        facility_contradictions = facility_contradictions + extra

        trust_scores: dict[CapabilityType, Any] = {}
        for cap in caps:
            cap_contradictions = contradictions_by_cap.get(cap.capability_type, [])
            ts = score_capability(
                cap,
                cap_contradictions,
                use_llm=use_llm,
                rng_seed=rng_seed,
            )
            trust_scores[cap.capability_type] = ts

        audit = build_facility_audit(
            facility_id=facility_id,
            name=name,
            location=location,
            capabilities=caps,
            contradictions=facility_contradictions,
            evidence_assessments=facility_assessments,
            trust_scores=trust_scores,
            mlflow_trace_id=mlflow_trace_id,
        )
        audits.append(audit)

    audits_path = tdir / AUDITS_FILE
    rows = [_audit_to_parquet_row(a) for a in audits]
    _write_parquet(rows, audits_path)
    _best_effort_delta_mirror(audits_path)

    summary = {
        "facility_count": len(facility_ids),
        "capability_count": len(capabilities),
        "contradiction_count": len(contradictions),
        "audit_count": len(audits),
    }
    print(
        "[build_audits] facilities={f} capabilities={c} contradictions={x} audits={a}".format(
            f=summary["facility_count"],
            c=summary["capability_count"],
            x=summary["contradiction_count"],
            a=summary["audit_count"],
        )
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--tables-dir",
        type=str,
        default=None,
        help="Override the tables directory (default: <repo>/tables).",
    )
    p.add_argument(
        "--subset",
        choices=("demo", "all"),
        default="all",
        help="Restrict to demo subset or process all facilities.",
    )
    p.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable the (optional) LLM reasoning step in the trust scorer.",
    )
    p.add_argument(
        "--rng-seed",
        type=int,
        default=42,
        help="Seed for bootstrap CI determinism.",
    )
    p.add_argument(
        "--mlflow-trace-id",
        type=str,
        default=None,
        help="Optional MLflow trace id to attach to every emitted audit.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Audit only the first N facilities after subset filtering.",
    )
    return p


def _cli(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    main(
        tables_dir=args.tables_dir,
        subset=args.subset if args.subset != "all" else None,
        use_llm=args.use_llm,
        rng_seed=args.rng_seed,
        mlflow_trace_id=args.mlflow_trace_id,
        limit=args.limit,
    )


if __name__ == "__main__":
    _cli()
