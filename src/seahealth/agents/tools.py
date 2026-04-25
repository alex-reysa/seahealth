"""Plain-Python tools the Query Agent (and tests) call directly.

Each function returns simple JSON-friendly dicts (or lists of dicts) so the
Anthropic tool-use loop can serialize them straight back to the model. The
Query Agent wraps these in a tool registry; unit tests can call them
directly without spinning up an LLM.

Reads source data from ``tables/facility_audits.parquet`` (or a path
override) and gracefully degrades when the file is absent — the demo
pipeline tolerates a cold-start state where no audits have been written
yet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from seahealth.schemas import GeoPoint

from .geocode import geocode, haversine_km

DEFAULT_AUDITS_PATH = "tables/facility_audits.parquet"


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
        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")
        if isinstance(value, str) and key in {
            "location",
            "capabilities",
            "trust_scores",
        }:
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                pass
        out[key] = value
    return out


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


def _location_from_audit(audit: dict[str, Any]) -> GeoPoint | None:
    raw = audit.get("location")
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


def _trust_for_capability(
    audit: dict[str, Any], capability_type: str
) -> dict[str, Any] | None:
    raw = audit.get("trust_scores")
    if isinstance(raw, dict):
        score = raw.get(capability_type)
        if isinstance(score, dict):
            return score
    return None


def tool_search_facilities(
    capability_type: str,
    lat: float,
    lng: float,
    radius_km: float,
    *,
    audits_path: str | None = None,
) -> list[dict]:
    """Return facilities within ``radius_km`` of (lat, lng) that have a
    TrustScore for ``capability_type``.

    Sort order: score desc, then distance_km asc. Each entry is a flat dict
    safe to JSON-serialize back to the model.
    """
    rows = _read_audits(audits_path)
    if not rows:
        return []
    origin = GeoPoint(lat=float(lat), lng=float(lng))
    candidates: list[dict[str, Any]] = []
    for audit in rows:
        location = _location_from_audit(audit)
        if location is None:
            continue
        distance_km = haversine_km(origin, location)
        if distance_km > radius_km:
            continue
        score_obj = _trust_for_capability(audit, capability_type)
        if score_obj is None:
            continue
        try:
            score_value = int(score_obj.get("score", 0))
        except (TypeError, ValueError):
            score_value = 0
        contradictions = score_obj.get("contradictions") or []
        evidence = score_obj.get("evidence") or []
        candidates.append(
            {
                "facility_id": audit.get("facility_id"),
                "name": audit.get("name"),
                "lat": location.lat,
                "lng": location.lng,
                "distance_km": round(distance_km, 4),
                "score": score_value,
                "contradictions_flagged": len(contradictions),
                "evidence_count": len(evidence),
            }
        )
    candidates.sort(key=lambda c: (-c["score"], c["distance_km"]))
    return candidates


def tool_get_facility_audit(
    facility_id: str, *, audits_path: str | None = None
) -> dict | None:
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
    "tool_geocode",
    "tool_get_facility_audit",
    "tool_search_facilities",
]
