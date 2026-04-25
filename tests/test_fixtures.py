"""Fixture-vs-schema round-trip checks.

Each ``fixtures/*.json`` file MUST validate against its declared Pydantic
model. Catching schema drift here keeps the OpenAPI spec and the demo
payloads in sync — mismatches trip the test instead of the UI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import TypeAdapter

from seahealth.schemas import (
    FacilityAudit,
    MapRegionAggregate,
    QueryResult,
    SummaryMetrics,
)

# tests/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures"


def _load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_summary_demo_fixture_round_trips():
    metrics = SummaryMetrics.model_validate(_load("summary_demo.json"))
    assert metrics.audited_count == 200
    assert metrics.verified_count == 47
    assert metrics.flagged_count == 89


def test_query_demo_fixture_round_trips():
    result = QueryResult.model_validate(_load("demo_query_appendectomy.json"))
    assert result.parsed_intent.capability_type == "SURGERY_APPENDECTOMY"
    assert len(result.ranked_facilities) >= 5
    # Top row must carry the MISSING_STAFF / HIGH contradiction the spec calls out.
    top = result.ranked_facilities[0]
    high_missing_staff = [
        c
        for c in top.trust_score.contradictions
        if c.contradiction_type == "MISSING_STAFF" and c.severity == "HIGH"
    ]
    assert len(high_missing_staff) == 1


def test_facility_audit_demo_fixture_round_trips():
    audit = FacilityAudit.model_validate(_load("facility_audit_demo.json"))
    assert audit.facility_id == "vf_00042_patna_general_hospi"
    assert len(audit.capabilities) >= 3
    assert any(c.capability_type == "SURGERY_APPENDECTOMY" for c in audit.capabilities)
    assert audit.total_contradictions == 2
    assert audit.mlflow_trace_id is not None
    # Each capability needs at least one EvidenceRef with a non-empty snippet/source_type.
    for cap in audit.capabilities:
        assert cap.evidence_refs, f"capability {cap.capability_type} missing evidence"
        for ev in cap.evidence_refs:
            assert ev.snippet
            assert ev.source_type


def test_map_aggregates_demo_fixture_round_trips():
    adapter = TypeAdapter(List[MapRegionAggregate])
    rows = adapter.validate_python(_load("map_aggregates_demo.json"))
    assert len(rows) >= 5
    assert all(r.capability_type == "SURGERY_APPENDECTOMY" for r in rows)
    # Variance check — choropleth needs visibly different counts.
    verified = {r.verified_facilities_count for r in rows}
    flagged = {r.flagged_facilities_count for r in rows}
    gaps = {r.gap_population for r in rows}
    assert len(verified) > 1
    assert len(flagged) > 1
    assert len(gaps) > 1
    # States covered.
    states = {r.state for r in rows}
    assert {"Bihar", "Jharkhand", "Uttar Pradesh", "West Bengal"}.issubset(states)
