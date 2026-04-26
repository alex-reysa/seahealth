"""SeaHealth API data access layer.

Single entry point for the API endpoints to read data, abstracting over three
backends in priority order:

1. ``DELTA``   — Databricks SQL (gold catalog) when ``DATABRICKS_SQL_HTTP_PATH``
                 is set. Reads via ``databricks-sql-connector``. On any
                 connection or query failure we log a warning and fall back to
                 PARQUET for that single call.
2. ``PARQUET`` — local ``tables/facility_audits.parquet`` written by
                 ``seahealth.pipelines.build_audits``. Decodes JSON-string
                 columns (``capabilities_json``, ``trust_scores_json``) back
                 into Pydantic models.
3. ``FIXTURE`` — hand-built ``fixtures/*.json`` snapshots. Same behavior the
                 Phase-1E stub had; used for tests, demos, and cold-start.

Mode auto-detection happens once per process via ``detect_mode``. Tests can
force a mode by setting ``SEAHEALTH_API_MODE`` in the environment.

The four public loaders return canonical Pydantic models (or ``None`` /
``list[...]`` when the model is collection-shaped) so callers never have to
handle backend-specific row shapes.
"""

from __future__ import annotations

import json
import logging
import math
import os
from collections import defaultdict
from collections.abc import Iterable
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from seahealth.schemas import (
    Capability,
    CapabilityType,
    FacilityAudit,
    GeoPoint,
    MapRegionAggregate,
    SummaryMetrics,
    TrustScore,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------

# main.py -> api -> seahealth -> src -> repo_root
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "fixtures"

SUMMARY_FIXTURE = FIXTURES_DIR / "summary_demo.json"
FACILITY_AUDIT_FIXTURE = FIXTURES_DIR / "facility_audit_demo.json"
MAP_AGGREGATES_FIXTURE = FIXTURES_DIR / "map_aggregates_demo.json"

DEFAULT_FACILITY_AUDITS_PARQUET = REPO_ROOT / "tables" / "facility_audits.parquet"

DEFAULT_MAP_RADIUS_KM = 50.0
SUMMARY_VERIFIED_SCORE_THRESHOLD = 80
EARTH_RADIUS_KM = 6371.0

_MAP_AGGREGATES_ADAPTER = TypeAdapter(list[MapRegionAggregate])


class DataMode(StrEnum):
    """The three backends the API can read from, in priority order."""

    DELTA = "delta"
    PARQUET = "parquet"
    FIXTURE = "fixture"


class DataLayerError(RuntimeError):
    """Raised when none of the configured backends can satisfy a read."""


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


def _facility_audits_parquet_path() -> Path:
    override = os.environ.get("SEAHEALTH_FACILITY_AUDITS_PARQUET")
    if override:
        return Path(override)
    return DEFAULT_FACILITY_AUDITS_PARQUET


@lru_cache(maxsize=1)
def detect_mode() -> DataMode:
    """Pick the backend mode once per process.

    Order:
        1. ``SEAHEALTH_API_MODE`` env var — explicit override (used by tests).
        2. DELTA  if ``DATABRICKS_SQL_HTTP_PATH`` is set.
        3. PARQUET if ``tables/facility_audits.parquet`` (or override path) exists.
        4. FIXTURE otherwise.
    """
    forced = os.environ.get("SEAHEALTH_API_MODE")
    if forced:
        try:
            return DataMode(forced.lower())
        except ValueError:
            log.warning(
                "SEAHEALTH_API_MODE=%s is not one of %s; falling back to auto-detect",
                forced,
                [m.value for m in DataMode],
            )

    if os.environ.get("DATABRICKS_SQL_HTTP_PATH"):
        return DataMode.DELTA
    if _facility_audits_parquet_path().exists():
        return DataMode.PARQUET
    return DataMode.FIXTURE


def reset_mode_cache() -> None:
    """Clear the cached mode (test-only helper)."""
    detect_mode.cache_clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_fixture_path(path: Path) -> str:
    """Render ``path`` relative to the repo root when possible, else absolute.

    Tests sometimes monkeypatch the fixture path to a ``tmp_path`` outside the
    repository. ``Path.relative_to`` would raise ``ValueError`` there, so we
    fall back to the absolute string representation.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_json_file(path: Path) -> Any:
    if not path.exists():
        raise DataLayerError(f"fixture missing: {_format_fixture_path(path)}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:  # pragma: no cover - corrupted on disk
        raise DataLayerError(
            f"fixture not loadable: {_format_fixture_path(path)} ({exc.msg})"
        ) from exc


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _parquet_row_to_audit(row: dict[str, Any]) -> FacilityAudit | None:
    """Decode a single parquet row into a ``FacilityAudit``.

    The parquet shape produced by ``seahealth.pipelines.build_audits`` stores
    nested structures as JSON strings:

        - ``capabilities_json``  -> list[Capability]
        - ``trust_scores_json``  -> dict[CapabilityType, TrustScore]
    """
    try:
        location = GeoPoint(
            lat=float(row["lat"]),
            lng=float(row["lng"]),
            pin_code=row.get("pin_code"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("skipping audit with bad location: %s", exc)
        return None

    capabilities: list[Capability] = []
    raw_caps = row.get("capabilities_json")
    if isinstance(raw_caps, (bytes, bytearray)):
        raw_caps = raw_caps.decode("utf-8")
    if isinstance(raw_caps, str) and raw_caps:
        try:
            for entry in json.loads(raw_caps):
                capabilities.append(Capability.model_validate(entry))
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("skipping malformed capabilities_json: %s", exc)

    trust_scores: dict[CapabilityType, TrustScore] = {}
    raw_scores = row.get("trust_scores_json")
    if isinstance(raw_scores, (bytes, bytearray)):
        raw_scores = raw_scores.decode("utf-8")
    if isinstance(raw_scores, str) and raw_scores:
        try:
            for key, val in json.loads(raw_scores).items():
                try:
                    cap_key = CapabilityType(key)
                except ValueError:
                    log.warning("dropping unknown CapabilityType key: %s", key)
                    continue
                try:
                    trust_scores[cap_key] = TrustScore.model_validate(val)
                except ValidationError as exc:
                    log.warning("dropping malformed trust_score %s: %s", key, exc)
        except json.JSONDecodeError as exc:
            log.warning("skipping malformed trust_scores_json: %s", exc)

    try:
        return FacilityAudit(
            facility_id=str(row["facility_id"]),
            name=str(row.get("name") or row["facility_id"]),
            location=location,
            capabilities=capabilities,
            trust_scores=trust_scores,
            total_contradictions=int(row.get("total_contradictions") or 0),
            last_audited_at=row["last_audited_at"],
            mlflow_trace_id=row.get("mlflow_trace_id"),
        )
    except (KeyError, ValidationError) as exc:
        log.warning("skipping malformed audit row: %s", exc)
        return None


def _read_parquet_audits() -> list[FacilityAudit]:
    """Read the parquet table and materialize ``FacilityAudit`` rows."""
    path = _facility_audits_parquet_path()
    if not path.exists():
        raise DataLayerError(f"parquet missing: {path}")
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - pyarrow is a hard dep
        raise DataLayerError(f"pyarrow unavailable: {exc}") from exc
    try:
        table = pq.read_table(path)
    except Exception as exc:
        raise DataLayerError(f"parquet read failed ({path}): {exc}") from exc
    audits: list[FacilityAudit] = []
    for raw in table.to_pylist():
        audit = _parquet_row_to_audit(raw)
        if audit is not None:
            audits.append(audit)
    return audits


# ---------------------------------------------------------------------------
# Delta backend (live)
# ---------------------------------------------------------------------------


def _delta_connect() -> Any:
    """Open a databricks SQL connection. Raises ``DataLayerError`` on failure."""
    try:
        from databricks import sql as databricks_sql  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised when SDK absent
        raise DataLayerError(f"databricks-sql-connector not installed: {exc}") from exc

    host = os.environ.get("DATABRICKS_SERVER_HOSTNAME")
    if not host:
        raw = os.environ.get("DATABRICKS_HOST", "")
        host = raw.removeprefix("https://").removeprefix("http://").rstrip("/")
    http_path = os.environ.get("DATABRICKS_SQL_HTTP_PATH") or os.environ.get(
        "DATABRICKS_HTTP_PATH"
    )
    token = os.environ.get("DATABRICKS_TOKEN")

    if not host or not http_path or not token:
        raise DataLayerError(
            "Delta connection requires DATABRICKS_HOST/SERVER_HOSTNAME, "
            "DATABRICKS_SQL_HTTP_PATH and DATABRICKS_TOKEN"
        )
    try:
        return databricks_sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
        )
    except Exception as exc:
        raise DataLayerError(f"databricks.sql.connect failed: {exc}") from exc


_GOLD_SCHEMA = "workspace.seahealth_gold"


def _delta_query(sql: str, params: Iterable[Any] | None = None) -> tuple[list[str], list[tuple]]:
    """Execute ``sql`` and return ``(columns, rows)``."""
    conn = _delta_connect()
    try:
        with conn.cursor() as cursor:
            if params:
                cursor.execute(sql, list(params))
            else:
                cursor.execute(sql)
            description = cursor.description or []
            cols = [d[0] for d in description]
            rows = [tuple(r) for r in cursor.fetchall()]
            return cols, rows
    finally:
        try:
            conn.close()
        except Exception:  # pragma: no cover
            pass


def _delta_row_to_audit(columns: list[str], row: tuple) -> FacilityAudit | None:
    record = dict(zip(columns, row, strict=False))
    location_raw = record.get("location")
    if isinstance(location_raw, str):
        try:
            location_raw = json.loads(location_raw)
        except json.JSONDecodeError:
            location_raw = None
    if not isinstance(location_raw, dict):
        return None

    # capabilities + trust_scores arrive as STRUCT/MAP. databricks-sql-connector
    # returns them as plain Python (lists/dicts); JSON strings are accepted too.
    capabilities_raw = record.get("capabilities") or []
    if isinstance(capabilities_raw, str):
        try:
            capabilities_raw = json.loads(capabilities_raw)
        except json.JSONDecodeError:
            capabilities_raw = []

    trust_scores_raw = record.get("trust_scores") or {}
    if isinstance(trust_scores_raw, str):
        try:
            trust_scores_raw = json.loads(trust_scores_raw)
        except json.JSONDecodeError:
            trust_scores_raw = {}

    try:
        location = GeoPoint(
            lat=float(location_raw["lat"]),
            lng=float(location_raw["lng"]),
            pin_code=location_raw.get("pin_code"),
        )
    except (KeyError, TypeError, ValueError):
        return None

    capabilities: list[Capability] = []
    for entry in capabilities_raw or []:
        try:
            capabilities.append(Capability.model_validate(entry))
        except ValidationError:
            continue

    trust_scores: dict[CapabilityType, TrustScore] = {}
    for key, val in (trust_scores_raw or {}).items():
        try:
            cap_key = CapabilityType(key)
        except ValueError:
            continue
        try:
            trust_scores[cap_key] = TrustScore.model_validate(val)
        except ValidationError:
            continue

    try:
        return FacilityAudit(
            facility_id=str(record["facility_id"]),
            name=str(record.get("name") or record["facility_id"]),
            location=location,
            capabilities=capabilities,
            trust_scores=trust_scores,
            total_contradictions=int(record.get("total_contradictions") or 0),
            last_audited_at=record["last_audited_at"],
            mlflow_trace_id=record.get("mlflow_trace_id"),
        )
    except (KeyError, ValidationError):
        return None


def _delta_select_audits(
    facility_id: str | None = None, limit: int | None = None
) -> list[FacilityAudit]:
    sql = (
        "SELECT facility_id, name, location, capabilities, trust_scores, "
        "total_contradictions, last_audited_at, mlflow_trace_id "
        f"FROM {_GOLD_SCHEMA}.facility_audits"
    )
    params: list[Any] = []
    if facility_id is not None:
        sql += " WHERE facility_id = ?"
        params.append(facility_id)
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    cols, rows = _delta_query(sql, params)
    audits: list[FacilityAudit] = []
    for row in rows:
        audit = _delta_row_to_audit(cols, row)
        if audit is not None:
            audits.append(audit)
    return audits


def _delta_select_map_aggregates(
    capability_type: CapabilityType | None,
) -> list[MapRegionAggregate] | None:
    """Try the precomputed gold table; return ``None`` if it isn't there."""
    sql = (
        "SELECT region_id, region_name, state, capability_type, population, "
        "verified_facilities_count, flagged_facilities_count, gap_population, "
        f"centroid FROM {_GOLD_SCHEMA}.map_aggregates"
    )
    params: list[Any] = []
    if capability_type is not None:
        sql += " WHERE capability_type = ?"
        params.append(capability_type.value)
    try:
        cols, rows = _delta_query(sql, params)
    except DataLayerError as exc:
        log.warning("map_aggregates delta query failed: %s", exc)
        return None
    out: list[MapRegionAggregate] = []
    for row in rows:
        record = dict(zip(cols, row, strict=False))
        centroid = record.get("centroid")
        if isinstance(centroid, str):
            try:
                centroid = json.loads(centroid)
            except json.JSONDecodeError:
                continue
        if not isinstance(centroid, dict):
            continue
        try:
            out.append(
                MapRegionAggregate(
                    region_id=str(record["region_id"]),
                    region_name=str(record["region_name"]),
                    state=str(record["state"]),
                    capability_type=CapabilityType(record["capability_type"]),
                    population=int(record["population"]),
                    verified_facilities_count=int(record["verified_facilities_count"]),
                    flagged_facilities_count=int(record["flagged_facilities_count"]),
                    gap_population=int(record["gap_population"]),
                    centroid=GeoPoint(
                        lat=float(centroid["lat"]),
                        lng=float(centroid["lng"]),
                        pin_code=centroid.get("pin_code"),
                    ),
                    population_source="delta",
                )
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            log.warning("dropping bad map_aggregate row: %s", exc)
    return out


# ---------------------------------------------------------------------------
# Aggregation helpers (used by PARQUET + DELTA when no gold table)
# ---------------------------------------------------------------------------


def _summary_from_audits(
    audits: list[FacilityAudit], capability_type: CapabilityType | None
) -> SummaryMetrics:
    if capability_type is None:
        rows = audits
        audited = len(rows)
        verified = sum(
            1
            for a in rows
            if a.trust_scores
            and any(
                ts.score >= SUMMARY_VERIFIED_SCORE_THRESHOLD
                and not any(c.severity == "HIGH" for c in ts.contradictions)
                for ts in a.trust_scores.values()
            )
        )
        flagged = sum(1 for a in rows if a.total_contradictions > 0)
    else:
        rows = [a for a in audits if capability_type in a.trust_scores]
        audited = len(rows)
        verified = 0
        flagged = 0
        for a in rows:
            ts = a.trust_scores[capability_type]
            high = any(c.severity == "HIGH" for c in ts.contradictions)
            if ts.score >= SUMMARY_VERIFIED_SCORE_THRESHOLD and not high:
                verified += 1
            if ts.contradictions:
                flagged += 1

    # Use the filtered ``rows`` so a capability filter never reports a
    # timestamp from a facility outside the slice.
    if rows:
        last_at = max(a.last_audited_at for a in rows)
    elif audits:
        last_at = max(a.last_audited_at for a in audits)
    else:
        from datetime import UTC, datetime

        last_at = datetime.now(UTC)
    verified_ci: tuple[int, int] | None = None
    if audited > 0:
        from seahealth.eval.intervals import count_interval

        verified_ci = count_interval(verified, audited)
    return SummaryMetrics(
        audited_count=audited,
        verified_count=verified,
        flagged_count=flagged,
        last_audited_at=last_at,
        capability_type=capability_type,
        verified_count_ci=verified_ci,
    )


def _aggregate_map_from_audits(
    audits: list[FacilityAudit],
    capability_type: CapabilityType,
    radius_km: float,
) -> list[MapRegionAggregate]:
    """Group facilities by state and roll up verified/flagged counts.

    Used as a fallback when no precomputed ``map_aggregates`` table exists.
    Each state becomes one region; the centroid is the average of the included
    facilities' coordinates. Population/gap_population fields are best-effort
    (set to 0) since they require an external denominator we don't have here.
    """
    # Pre-aggregate by a synthesized state key (use pin prefix as a stand-in
    # when no state column is available in PARQUET mode). When ``radius_km``
    # is restrictive we drop facilities farther than ``radius_km`` from the
    # group's centroid; the default 50 km radius is permissive enough that
    # most state buckets keep all rows.
    grouped: dict[str, list[FacilityAudit]] = defaultdict(list)
    for a in audits:
        ts = a.trust_scores.get(capability_type)
        if ts is None:
            continue
        key = _state_label_from_pin(a.location.pin_code)
        grouped[key].append(a)

    out: list[MapRegionAggregate] = []
    for state_key, facilities in grouped.items():
        if not facilities:
            continue
        lat = sum(f.location.lat for f in facilities) / len(facilities)
        lng = sum(f.location.lng for f in facilities) / len(facilities)
        if radius_km > 0:
            facilities = [
                f
                for f in facilities
                if _haversine_km(lat, lng, f.location.lat, f.location.lng) <= radius_km
            ]
        if not facilities:
            continue
        verified = 0
        flagged = 0
        for f in facilities:
            ts = f.trust_scores.get(capability_type)
            if ts is None:
                continue
            high = any(c.severity == "HIGH" for c in ts.contradictions)
            if ts.score >= SUMMARY_VERIFIED_SCORE_THRESHOLD and not high:
                verified += 1
            if ts.contradictions:
                flagged += 1
        try:
            out.append(
                MapRegionAggregate(
                    region_id=f"AUTO-{state_key}",
                    region_name=state_key,
                    state=state_key,
                    capability_type=capability_type,
                    population=0,
                    verified_facilities_count=verified,
                    flagged_facilities_count=flagged,
                    gap_population=0,
                    centroid=GeoPoint(lat=lat, lng=lng, pin_code=None),
                    # PARQUET mode has no population source on the audit row;
                    # honesty over phantom denominators.
                    population_source="unavailable",
                )
            )
        except ValidationError as exc:  # pragma: no cover
            log.warning("skipping bad aggregate: %s", exc)
    return out


def _state_label_from_pin(pin_code: str | None) -> str:
    """Map a 6-digit India PIN code to a coarse state-zone label.

    Phase-4 PARQUET mode doesn't carry the state column on the audit row; we
    use the first PIN digit as a stand-in zone identifier so aggregations don't
    collapse every facility into one region.
    """
    if not pin_code:
        return "UNKNOWN"
    head = pin_code.strip()[:1]
    return f"PIN-{head}xxxxx" if head.isdigit() else "UNKNOWN"


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_summary(capability_type: CapabilityType | None = None) -> SummaryMetrics:
    """Return summary tile metrics, optionally filtered by capability."""
    mode = detect_mode()
    if mode is DataMode.DELTA:
        try:
            audits = _delta_select_audits()
            return _summary_from_audits(audits, capability_type)
        except DataLayerError as exc:
            log.warning("summary: delta failed (%s); falling back to parquet", exc)
            mode = DataMode.PARQUET
    if mode is DataMode.PARQUET:
        try:
            audits = _read_parquet_audits()
            return _summary_from_audits(audits, capability_type)
        except DataLayerError as exc:
            log.warning("summary: parquet failed (%s); falling back to fixture", exc)
            mode = DataMode.FIXTURE
    raw = _load_json_file(SUMMARY_FIXTURE)
    metrics = SummaryMetrics.model_validate(raw)
    if capability_type is not None:
        return metrics.model_copy(update={"capability_type": capability_type})
    return metrics


def load_facility_audit(facility_id: str) -> FacilityAudit | None:
    """Return one ``FacilityAudit`` by id, or ``None`` if absent."""
    mode = detect_mode()
    if mode is DataMode.DELTA:
        try:
            audits = _delta_select_audits(facility_id=facility_id, limit=1)
            return audits[0] if audits else None
        except DataLayerError as exc:
            log.warning("facility: delta failed (%s); falling back to parquet", exc)
            mode = DataMode.PARQUET
    if mode is DataMode.PARQUET:
        try:
            audits = _read_parquet_audits()
        except DataLayerError as exc:
            log.warning("facility: parquet failed (%s); falling back to fixture", exc)
            mode = DataMode.FIXTURE
        else:
            for a in audits:
                if a.facility_id == facility_id:
                    return a
            return None
    raw = _load_json_file(FACILITY_AUDIT_FIXTURE)
    audit = FacilityAudit.model_validate(raw)
    return audit if audit.facility_id == facility_id else None


def load_facilities(limit: int = 50) -> list[FacilityAudit]:
    """Return up to ``limit`` ``FacilityAudit`` rows."""
    if limit <= 0:
        return []
    mode = detect_mode()
    if mode is DataMode.DELTA:
        try:
            return _delta_select_audits(limit=limit)
        except DataLayerError as exc:
            log.warning("facilities: delta failed (%s); falling back to parquet", exc)
            mode = DataMode.PARQUET
    if mode is DataMode.PARQUET:
        try:
            audits = _read_parquet_audits()
            return audits[:limit]
        except DataLayerError as exc:
            log.warning("facilities: parquet failed (%s); falling back to fixture", exc)
            mode = DataMode.FIXTURE
    raw = _load_json_file(FACILITY_AUDIT_FIXTURE)
    audit = FacilityAudit.model_validate(raw)
    return [audit][:limit]


def load_all_audits() -> list[FacilityAudit]:
    """Return ALL audits without pagination — used by /facilities/geo."""
    mode = detect_mode()
    if mode is DataMode.DELTA:
        try:
            return _delta_select_audits()
        except DataLayerError as exc:
            log.warning("all_audits: delta failed (%s); falling back to parquet", exc)
            mode = DataMode.PARQUET
    if mode is DataMode.PARQUET:
        try:
            return _read_parquet_audits()
        except DataLayerError as exc:
            log.warning("all_audits: parquet failed (%s); falling back to fixture", exc)
            mode = DataMode.FIXTURE
    raw = _load_json_file(FACILITY_AUDIT_FIXTURE)
    audit = FacilityAudit.model_validate(raw)
    return [audit]


def load_map_aggregates(
    capability_type: CapabilityType | None = None,
    radius_km: float = DEFAULT_MAP_RADIUS_KM,
) -> list[MapRegionAggregate]:
    """Return desert-map region rollups, optionally filtered by capability."""
    mode = detect_mode()
    if mode is DataMode.DELTA:
        precomputed = _delta_select_map_aggregates(capability_type)
        if precomputed is not None:
            return precomputed
        try:
            audits = _delta_select_audits()
            cap = capability_type or CapabilityType.SURGERY_APPENDECTOMY
            return _aggregate_map_from_audits(audits, cap, radius_km)
        except DataLayerError as exc:
            log.warning("map: delta failed (%s); falling back to parquet", exc)
            mode = DataMode.PARQUET
    if mode is DataMode.PARQUET:
        try:
            audits = _read_parquet_audits()
        except DataLayerError as exc:
            log.warning("map: parquet failed (%s); falling back to fixture", exc)
            mode = DataMode.FIXTURE
        else:
            cap = capability_type or CapabilityType.SURGERY_APPENDECTOMY
            return _aggregate_map_from_audits(audits, cap, radius_km)
    raw = _load_json_file(MAP_AGGREGATES_FIXTURE)
    rows = _MAP_AGGREGATES_ADAPTER.validate_python(raw)
    if capability_type is not None:
        rows = [r for r in rows if r.capability_type == capability_type]
    return rows


# ---------------------------------------------------------------------------
# Diagnostic helpers (used by /health/data)
# ---------------------------------------------------------------------------


def health_snapshot() -> dict[str, Any]:
    """Snapshot of the current data-access posture for the demo health page."""
    mode = detect_mode()
    parquet_path = _facility_audits_parquet_path()
    snapshot: dict[str, Any] = {
        "mode": mode.value,
        "facility_audits_path": str(parquet_path),
        "delta_reachable": False,
    }
    if mode is DataMode.DELTA:
        try:
            _delta_query("SELECT 1")
            snapshot["delta_reachable"] = True
        except DataLayerError as exc:
            snapshot["delta_reachable"] = False
            snapshot["delta_error"] = str(exc)
    return snapshot


__all__ = [
    "DataMode",
    "DataLayerError",
    "detect_mode",
    "reset_mode_cache",
    "load_summary",
    "load_facility_audit",
    "load_facilities",
    "load_map_aggregates",
    "health_snapshot",
]
