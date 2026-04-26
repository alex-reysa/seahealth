"""Fixture-vs-schema round-trip checks.

Each ``fixtures/*.json`` file MUST validate against its declared Pydantic
model. Catching schema drift here keeps the OpenAPI spec and the demo
payloads in sync — mismatches trip the test instead of the UI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
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


# Fixture file -> validator callable. Each entry MUST deserialize cleanly
# against the canonical Pydantic model after AUD-01 schema hardening.
_FIXTURE_VALIDATORS: dict[str, Any] = {
    "summary_demo.json": SummaryMetrics.model_validate,
    "facility_audit_demo.json": FacilityAudit.model_validate,
    "demo_query_appendectomy.json": QueryResult.model_validate,
    "map_aggregates_demo.json": TypeAdapter(list[MapRegionAggregate]).validate_python,
}


@pytest.mark.parametrize("fixture_name", sorted(_FIXTURE_VALIDATORS.keys()))
def test_every_fixture_round_trips_against_its_pydantic_model(fixture_name: str):
    """Every ``fixtures/*.json`` file deserializes cleanly against its schema."""
    validator = _FIXTURE_VALIDATORS[fixture_name]
    raw = _load(fixture_name)
    validator(raw)  # raises ValidationError on drift


def test_summary_demo_fixture_round_trips():
    """Live L-1 run: 250 facilities audited, real distribution of verified vs flagged."""
    metrics = SummaryMetrics.model_validate(_load("summary_demo.json"))
    assert metrics.audited_count >= 50
    assert metrics.flagged_count >= 1
    # Verified can be 0 (the trust narrative: thin self-reports → nobody passes).
    assert metrics.verified_count >= 0
    assert metrics.last_audited_at is not None


def test_query_demo_fixture_round_trips():
    """Locked appendectomy query — Kimi found 0 SURGERY_APPENDECTOMY claims, so the
    query agent's trust-conscious fallback ranks against SURGERY_GENERAL. Top results
    are Patna-area facilities all carrying contradictions for unverifiable surgery.
    """
    result = QueryResult.model_validate(_load("demo_query_appendectomy.json"))
    # Either the original capability (if any facility specifically claimed it) OR the
    # SURGERY_GENERAL fallback must drive the parsed intent.
    assert result.parsed_intent.capability_type in {
        "SURGERY_APPENDECTOMY",
        "SURGERY_GENERAL",
    }
    assert len(result.ranked_facilities) >= 3
    # The demo narrative requires at least one facility flagged with contradictions.
    assert any(rf.contradictions_flagged > 0 for rf in result.ranked_facilities)


def test_facility_audit_demo_fixture_round_trips():
    """CIMS Hospital Patna — claims six high-stakes capabilities (ICU, surgery,
    neonatal, etc.) with no verifiable staffing/equipment evidence. Trust scorer
    correctly assigns 0 to the most demanding ones — the trust story.
    """
    audit = FacilityAudit.model_validate(_load("facility_audit_demo.json"))
    assert audit.facility_id  # any non-empty id
    assert len(audit.capabilities) >= 1
    assert audit.total_contradictions >= 1
    # For low-confidence facilities, evidence_refs may be empty (Kimi extracted the
    # claim from the chunk but couldn't pin a citation snippet). That itself is part
    # of the trust signal — the audit shape MUST validate either way.


def test_map_aggregates_demo_fixture_round_trips():
    """Map aggregates over the 250-facility demo subset — Bihar-clustered."""
    adapter = TypeAdapter(list[MapRegionAggregate])
    rows = adapter.validate_python(_load("map_aggregates_demo.json"))
    assert len(rows) >= 1
    # Every row carries the queried capability type.
    capabilities = {r.capability_type.value for r in rows}
    assert len(capabilities) == 1
