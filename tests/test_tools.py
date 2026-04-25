"""Unit tests for the Query Agent's plain-Python tools."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from seahealth.agents.tools import (
    tool_geocode,
    tool_get_facility_audit,
    tool_search_facilities,
)


def _trust_score_dict(
    *,
    capability_type: str,
    score: int,
    confidence: float,
    contradictions: int = 0,
    evidence: int = 1,
) -> dict:
    """Build a TrustScore-shaped dict whose `score` matches the validator."""
    return {
        "capability_type": capability_type,
        "claimed": True,
        "evidence": [
            {
                "source_doc_id": f"doc_{capability_type}_{i}",
                "facility_id": "vf_test",
                "chunk_id": f"chunk_{i}",
                "row_id": None,
                "span": [0, 10],
                "snippet": "evidence snippet",
                "source_type": "facility_note",
                "source_observed_at": "2026-01-01T00:00:00Z",
                "retrieved_at": "2026-04-25T18:00:00Z",
            }
            for i in range(evidence)
        ],
        "contradictions": [],  # severity penalty 0 keeps the math simple
        "confidence": confidence,
        "confidence_interval": [max(0.0, confidence - 0.05), min(1.0, confidence + 0.02)],
        "score": score,
        "reasoning": "test reasoning",
        "computed_at": "2026-04-25T18:00:00Z",
    } | ({"_contradictions_count": contradictions} if contradictions else {})


@pytest.fixture()
def audits_parquet(tmp_path: Path) -> str:
    """Write a tiny FacilityAudits parquet with three facilities near/far from Patna."""
    facilities = [
        {
            "facility_id": "vf_near_patna",
            "name": "Patna Central",
            "location": {"lat": 25.6121, "lng": 85.1418, "pin_code": "800001"},
            "trust_scores": {
                "SURGERY_APPENDECTOMY": _trust_score_dict(
                    capability_type="SURGERY_APPENDECTOMY",
                    score=88,
                    confidence=0.88,
                    evidence=2,
                ),
            },
        },
        {
            "facility_id": "vf_close",
            "name": "Bihta District Hospital",
            # ~30 km west of Patna -> within 50 km radius.
            "location": {"lat": 25.5639, "lng": 84.8651, "pin_code": "801103"},
            "trust_scores": {
                "SURGERY_APPENDECTOMY": _trust_score_dict(
                    capability_type="SURGERY_APPENDECTOMY",
                    score=70,
                    confidence=0.70,
                    evidence=1,
                ),
            },
        },
        {
            "facility_id": "vf_far",
            "name": "Far Hospital",
            # ~200+ km away (rough Ranchi-ish) -> outside 50 km.
            "location": {"lat": 23.3441, "lng": 85.3096, "pin_code": "834001"},
            "trust_scores": {
                "SURGERY_APPENDECTOMY": _trust_score_dict(
                    capability_type="SURGERY_APPENDECTOMY",
                    score=95,
                    confidence=0.95,
                    evidence=3,
                ),
            },
        },
    ]
    table = pa.table(
        {
            "facility_id": [f["facility_id"] for f in facilities],
            "name": [f["name"] for f in facilities],
            "location": [json.dumps(f["location"]) for f in facilities],
            "trust_scores": [json.dumps(f["trust_scores"]) for f in facilities],
        }
    )
    path = tmp_path / "facility_audits.parquet"
    pq.write_table(table, path)
    return str(path)


def test_search_filters_by_radius(audits_parquet: str) -> None:
    results = tool_search_facilities(
        capability_type="SURGERY_APPENDECTOMY",
        lat=25.61,
        lng=85.14,
        radius_km=50.0,
        audits_path=audits_parquet,
    )
    ids = [r["facility_id"] for r in results]
    assert "vf_near_patna" in ids
    assert "vf_close" in ids
    assert "vf_far" not in ids
    # Sort: score desc, then distance asc.
    assert results == sorted(
        results, key=lambda r: (-r["score"], r["distance_km"])
    )


def test_search_returns_empty_when_no_parquet(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.parquet"
    assert (
        tool_search_facilities(
            capability_type="SURGERY_APPENDECTOMY",
            lat=25.61,
            lng=85.14,
            radius_km=50.0,
            audits_path=str(missing),
        )
        == []
    )


def test_get_facility_audit_found(audits_parquet: str) -> None:
    audit = tool_get_facility_audit("vf_near_patna", audits_path=audits_parquet)
    assert audit is not None
    assert audit["facility_id"] == "vf_near_patna"
    assert audit["location"]["pin_code"] == "800001"
    assert "SURGERY_APPENDECTOMY" in audit["trust_scores"]


def test_get_facility_audit_missing(audits_parquet: str) -> None:
    assert tool_get_facility_audit("does_not_exist", audits_path=audits_parquet) is None


def test_get_facility_audit_no_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.parquet"
    assert tool_get_facility_audit("anything", audits_path=str(missing)) is None


def test_geocode_tool() -> None:
    result = tool_geocode("Patna")
    assert "lat" in result and "lng" in result and "pin_code" in result
    assert result["pin_code"] == "800001"

    miss = tool_geocode("Atlantis")
    assert miss == {"error": "not_found"}
