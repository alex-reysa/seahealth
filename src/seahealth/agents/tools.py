"""Plain-Python tools the Query Agent (and tests) call directly.

Each function returns simple JSON-friendly dicts (or lists of dicts) so the
Anthropic tool-use loop can serialize them straight back to the model. The
Query Agent wraps these in a tool registry; unit tests can call them
directly without spinning up an LLM.

Reads source data from ``tables/facility_audits.parquet`` (or a path
override) and gracefully degrades when the file is absent — the demo
pipeline tolerates a cold-start state where no audits have been written
yet.

The retrieval iteration order is intentional: walk the broad
``facilities_index`` (~10k rows), enrich each surviving hit with the
hand-curated audit when present, and fall back to a heuristic capability
matcher otherwise. This makes location-driven queries (e.g. ONCOLOGY in
Mumbai) return results even when no audit is available yet.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from seahealth.schemas import GeoPoint

from .geocode import geocode, haversine_km

DEFAULT_AUDITS_PATH = "tables/facility_audits.parquet"
DEFAULT_FACILITIES_INDEX_PATH = "tables/facilities_index.parquet"
_JSON_COLUMNS = {"location", "capabilities", "trust_scores"}
# Columns we surface from facilities_index for downstream qualifier scoring.
_FACILITIES_INDEX_COLUMNS = ("numberDoctors", "capacity", "facilityTypeId")
# Hard cap on the number of search hits returned regardless of input radius.
_SEARCH_RESULT_CAP = 50
# Default score awarded to unaudited heuristic-matched candidates. Sits
# below most real audit scores so audited facilities outrank them.
_UNAUDITED_HEURISTIC_SCORE = 50


def tool_geocode(query: str) -> dict:
    """Wrap :func:`geocode` and return a JSON-friendly dict.

    Returns ``{'lat': float, 'lng': float, 'pin_code': str | None}`` on
    success or ``{'error': 'not_found'}`` if the city is unknown.
    """
    point = geocode(query)
    if point is None:
        return {"error": "not_found"}
    return {"lat": point.lat, "lng": point.lng, "pin_code": point.pin_code}


def _row_to_audit_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Decode a parquet row into a plain dict; JSON columns are eagerly parsed."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        value = _decode_jsonish(
            value,
            force=key.endswith("_json") or key in _JSON_COLUMNS,
        )
        out[key] = value
    if "location" not in out and {"lat", "lng"} <= set(out):
        out["location"] = {
            "lat": out.get("lat"),
            "lng": out.get("lng"),
            "pin_code": out.get("pin_code"),
        }
    if "capabilities" not in out and isinstance(out.get("capabilities_json"), list):
        out["capabilities"] = out["capabilities_json"]
    if "trust_scores" not in out and isinstance(out.get("trust_scores_json"), dict):
        out["trust_scores"] = out["trust_scores_json"]
    return out


def _decode_jsonish(value: Any, *, force: bool = False) -> Any:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    if force or stripped[0] in "[{":
        try:
            return json.loads(stripped)
        except (TypeError, ValueError, json.JSONDecodeError):
            return value
    return value


def _read_audits(audits_path: str | None) -> list[dict[str, Any]]:
    path = Path(audits_path) if audits_path else Path(DEFAULT_AUDITS_PATH)
    if not path.exists():
        return []
    try:
        table = pq.read_table(path)
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for raw in table.to_pylist():
        rows.append(_row_to_audit_dict(raw))
    return rows


def _coerce_optional_int(value: Any) -> int | None:
    """Best-effort cast of pandas/pyarrow nullable ints to plain ``int``.

    Returns ``None`` for missing / unparseable values rather than raising —
    we want the qualifier scorer to silently skip rather than drop facilities.
    """
    if value is None:
        return None
    # pandas nullable ints surface as pd.NA; pyarrow may surface np.nan.
    try:
        if value != value:  # NaN check without importing math
            return None
    except TypeError:
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=8)
def _read_facilities_index_full_cached(path_str: str) -> tuple[dict[str, Any], ...]:
    """Cached cold-load of ``facilities_index.parquet`` as a tuple of plain dicts.

    Returns an empty tuple when the file is missing or unreadable so callers
    degrade gracefully. Tuple (not list) so the cached value is hashable and
    can be safely shared across calls without copy-on-write surprises.
    """
    path = Path(path_str)
    if not path.exists():
        return ()
    try:
        table = pq.read_table(path)
    except Exception:
        return ()
    return tuple(table.to_pylist())


def _read_facilities_index_full(
    facilities_index_path: str | None,
) -> list[dict[str, Any]]:
    """Return the raw ``facilities_index`` row list (cached by path).

    Used by :func:`tool_search_facilities` to walk the broad index and
    enrich each surviving row with audit data. The list is rebuilt from the
    cached tuple so callers can mutate per-row dicts without poisoning the
    cache. The cache itself is keyed on the resolved path string.
    """
    resolved = (
        Path(facilities_index_path)
        if facilities_index_path
        else Path(DEFAULT_FACILITIES_INDEX_PATH)
    )
    rows = _read_facilities_index_full_cached(str(resolved))
    # Shallow copy each row so per-call mutation never bleeds into the cache.
    return [dict(row) for row in rows]


def _read_facilities_index(
    facilities_index_path: str | None,
) -> dict[str, dict[str, Any]]:
    """Side-load ``facilities_index.parquet`` keyed by ``facility_id``.

    Returns an empty dict if the file is missing or unreadable so callers
    degrade gracefully (qualifier scoring then becomes a no-op rather than a
    hard error). Backwards-compatible enrichment view layered on top of
    :func:`_read_facilities_index_full`.
    """
    out: dict[str, dict[str, Any]] = {}
    for raw in _read_facilities_index_full(facilities_index_path):
        fid = raw.get("facility_id")
        if not fid:
            continue
        entry: dict[str, Any] = {}
        for col in _FACILITIES_INDEX_COLUMNS:
            if col in raw:
                entry[col] = raw[col]
        out[str(fid)] = entry
    return out


def _location_from_audit(audit: dict[str, Any]) -> GeoPoint | None:
    raw = _decode_jsonish(audit.get("location"), force=True)
    if isinstance(raw, GeoPoint):
        return raw
    if isinstance(raw, dict):
        try:
            return GeoPoint(
                lat=float(raw["lat"]),
                lng=float(raw["lng"]),
                pin_code=raw.get("pin_code"),
            )
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _trust_for_capability(audit: dict[str, Any], capability_type: str) -> dict[str, Any] | None:
    raw = _decode_jsonish(audit.get("trust_scores"), force=True)
    if isinstance(raw, dict):
        score = _decode_jsonish(raw.get(capability_type), force=True)
        if isinstance(score, dict):
            return score
    return None


# Capability -> name-substring keywords for the heuristic matcher. Lowercase
# match against the facility ``name`` field. Kept narrow on purpose: false
# positives here are how unaudited facilities sneak into rankings.
_HEURISTIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ONCOLOGY": ("cancer", "oncology", "tata memorial", "chemo"),
    "MATERNAL": ("maternity", "matru", "prasuti", "women", "obstetric", "gynec"),
    "NEONATAL": (
        "neonatal",
        "newborn",
        "nicu",
        "sishu",
        "shishu",
        "paediatric",
        "pediatric",
        "child's",
        "children",
        "childs",
        "infant",
    ),
    "ICU": ("icu", "intensive", "critical care"),
    "TRAUMA": ("trauma", "accident", "emergency"),
    "DIALYSIS": ("dialysis", "kidney", "renal", "nephro"),
    "LAB": ("lab", "diagnostic", "pathology"),
    "RADIOLOGY": (
        "radiology",
        "imaging",
        "scan",
        " ct",
        "mri",
        "x-ray",
        "xray",
        "sonography",
    ),
    "PHARMACY": ("pharmacy", "medical store", "chemist"),
    "EMERGENCY_24_7": ("emergency", "24x7", "24 hour", "24-hour"),
}


def _heuristic_capability_match(
    name: str | None,
    facility_type_id: str | None,
    capability_type: str,
) -> bool:
    """Return True when an unaudited row plausibly offers ``capability_type``.

    Conservative by design: a pharmacy-typed facility never matches anything
    other than PHARMACY (so we don't pretend the local chemist does
    appendectomies), surgery capabilities require a hospital-typed row, and
    everything else falls through a small per-capability keyword table.
    """
    name_l = (name or "").lower()
    type_l = (facility_type_id or "").lower()
    cap = (capability_type or "").upper()

    # Type-aware whitelist: pharmacy facilityType only matches PHARMACY.
    if type_l == "pharmacy":
        return cap == "PHARMACY"

    # Empty / wildcard capability_type ⇒ accept any non-pharmacy facility.
    # (Location-only queries from sibling worktrees rely on this.)
    if not cap or cap == "*":
        return True

    if cap in _HEURISTIC_KEYWORDS:
        return any(kw in name_l for kw in _HEURISTIC_KEYWORDS[cap])

    if cap in ("SURGERY_GENERAL", "SURGERY_APPENDECTOMY"):
        if type_l != "hospital":
            return False
        return any(kw in name_l for kw in ("hospital", "surgical", "surgery"))

    return False


def tool_search_facilities(
    capability_type: str,
    lat: float,
    lng: float,
    radius_km: float,
    *,
    audits_path: str | None = None,
    facilities_index_path: str | None = None,
) -> list[dict]:
    """Return facilities within ``radius_km`` of (lat, lng) that match
    ``capability_type``.

    Iteration walks the broad ``facilities_index`` (~10k rows). For each row
    inside the radius:

    * If a hand-curated audit exists AND has a TrustScore for the requested
      capability, surface that score (``audit_status='audited'``).
    * Otherwise apply the conservative :func:`_heuristic_capability_match`
      keyword filter; surviving rows get a default score of
      ``_UNAUDITED_HEURISTIC_SCORE`` and ``audit_status='unaudited'``.

    Sort order: score desc, then distance asc. Capped at
    ``_SEARCH_RESULT_CAP`` rows. Each entry is a flat dict safe to
    JSON-serialize back to the model.

    Backwards compatible: the previous return shape is preserved and
    extended with ``audit_status``. Downstream :class:`RankedFacility`
    construction reads explicit fields, so the extra key is ignored there.
    """
    audits_by_id = {
        str(audit["facility_id"]): audit
        for audit in _read_audits(audits_path)
        if audit.get("facility_id")
    }
    # When an explicit audits_path is supplied without a matching index path
    # the caller is almost always a test fixture: defaulting to the real 10k
    # production index would silently inject unrelated heuristic hits. Mirror
    # the original "audits drive retrieval" behaviour in that case.
    if facilities_index_path is None and audits_path is not None:
        index_rows: list[dict[str, Any]] = []
    else:
        index_rows = _read_facilities_index_full(facilities_index_path)
    # Build a quick id->index_row lookup for enriching audit-only fallbacks
    # with `numberDoctors` (mirrors the legacy enrichment join).
    index_by_id: dict[str, dict[str, Any]] = {}
    for row in index_rows:
        fid = row.get("facility_id")
        if fid:
            index_by_id[str(fid)] = row
    # If the test/caller supplied an index but it doesn't carry lat/lng (e.g.
    # the legacy enrichment-only fixture), surface audited facilities via the
    # audits-fallback loop and use the index purely for `numberDoctors`.
    if not index_rows and not audits_by_id:
        return []

    origin = GeoPoint(lat=float(lat), lng=float(lng))
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _emit(
        *,
        facility_id: Any,
        name: Any,
        flat: float,
        flng: float,
        distance_km: float,
        score_value: int,
        contradictions: list[Any],
        evidence: list[Any],
        number_doctors: int | None,
        audit_status: str,
    ) -> None:
        candidates.append(
            {
                "facility_id": facility_id,
                "name": name,
                "lat": flat,
                "lng": flng,
                "distance_km": round(distance_km, 2),
                "score": score_value,
                "contradictions_flagged": len(contradictions),
                "evidence_count": len(evidence),
                "number_doctors": number_doctors,
                "audit_status": audit_status,
            }
        )

    for row in index_rows:
        flat = row.get("latitude")
        flng = row.get("longitude")
        if flat is None or flng is None:
            continue
        try:
            flat_f = float(flat)
            flng_f = float(flng)
        except (TypeError, ValueError):
            continue
        distance_km = haversine_km(origin, GeoPoint(lat=flat_f, lng=flng_f))
        if distance_km > radius_km:
            continue

        facility_id = row.get("facility_id")
        audit = audits_by_id.get(str(facility_id)) if facility_id else None
        score_obj = _trust_for_capability(audit, capability_type) if audit else None

        if score_obj is not None:
            try:
                score_value = int(score_obj.get("score", 0))
            except (TypeError, ValueError):
                score_value = 0
            contradictions = score_obj.get("contradictions") or []
            evidence = score_obj.get("evidence") or []
            audit_status = "audited"
        else:
            if not _heuristic_capability_match(
                row.get("name"), row.get("facilityTypeId"), capability_type
            ):
                continue
            score_value = _UNAUDITED_HEURISTIC_SCORE
            contradictions = []
            evidence = []
            audit_status = "unaudited"

        number_doctors = _coerce_optional_int(row.get("numberDoctors"))
        _emit(
            facility_id=facility_id,
            name=row.get("name"),
            flat=flat_f,
            flng=flng_f,
            distance_km=distance_km,
            score_value=score_value,
            contradictions=contradictions,
            evidence=evidence,
            number_doctors=number_doctors,
            audit_status=audit_status,
        )
        if facility_id:
            seen_ids.add(str(facility_id))

    # Audits without a row in facilities_index (e.g. the legacy in-memory
    # demo fixtures used by tests) would otherwise vanish. Walk the audit
    # table once more to surface any audited facility not yet emitted, so
    # the existing demo + Patna-only test fixtures keep working.
    for fid, audit in audits_by_id.items():
        if fid in seen_ids:
            continue
        score_obj = _trust_for_capability(audit, capability_type)
        if score_obj is None:
            continue
        location = _location_from_audit(audit)
        if location is None:
            continue
        distance_km = haversine_km(origin, location)
        if distance_km > radius_km:
            continue
        try:
            score_value = int(score_obj.get("score", 0))
        except (TypeError, ValueError):
            score_value = 0
        contradictions = score_obj.get("contradictions") or []
        evidence = score_obj.get("evidence") or []
        idx_row = index_by_id.get(fid)
        number_doctors = (
            _coerce_optional_int(idx_row.get("numberDoctors")) if idx_row else None
        )
        _emit(
            facility_id=audit.get("facility_id"),
            name=audit.get("name"),
            flat=location.lat,
            flng=location.lng,
            distance_km=distance_km,
            score_value=score_value,
            contradictions=contradictions,
            evidence=evidence,
            number_doctors=number_doctors,
            audit_status="audited",
        )

    candidates.sort(key=lambda c: (-c["score"], c["distance_km"]))
    return candidates[:_SEARCH_RESULT_CAP]


def tool_get_facility_audit(facility_id: str, *, audits_path: str | None = None) -> dict | None:
    """Fetch one FacilityAudit by id from the parquet table.

    Returns the row as a plain dict (with ``location``, ``capabilities``,
    and ``trust_scores`` decoded if they were stored as JSON strings) or
    ``None`` if the audit table is missing or the id is not present.
    """
    for audit in _read_audits(audits_path):
        if audit.get("facility_id") == facility_id:
            return audit
    return None


__all__ = [
    "DEFAULT_AUDITS_PATH",
    "DEFAULT_FACILITIES_INDEX_PATH",
    "tool_geocode",
    "tool_get_facility_audit",
    "tool_search_facilities",
]
