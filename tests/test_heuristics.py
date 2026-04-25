"""Deterministic unit tests for the validator heuristic detectors."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from seahealth.agents.heuristics import (
    FacilityFacts,
    detect_missing_equipment,
    detect_missing_staff,
    detect_stale_data,
    detect_temporal_unverified,
    detect_volume_mismatch,
    run_all_heuristics,
)
from seahealth.schemas import (
    Capability,
    CapabilityType,
    ContradictionType,
    EvidenceRef,
)

NOW = datetime(2026, 4, 25, 22, 30, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "validator"


def _evidence(facility_id: str = "vf_test") -> EvidenceRef:
    return EvidenceRef(
        source_doc_id="doc_1",
        facility_id=facility_id,
        chunk_id="chunk_1",
        row_id=None,
        span=(0, 10),
        snippet="snippet",
        source_type="facility_note",
        source_observed_at=NOW,
        retrieved_at=NOW,
    )


def _capability(
    cap_type: CapabilityType,
    facility_id: str = "vf_test",
) -> Capability:
    return Capability(
        facility_id=facility_id,
        capability_type=cap_type,
        claimed=True,
        evidence_refs=[_evidence(facility_id)],
        source_doc_id="doc_1",
        extracted_at=NOW,
        extractor_model="claude-sonnet-4-6",
    )


def _facts(**overrides) -> FacilityFacts:
    base = dict(
        facility_id="vf_test",
        equipment=["anesthesia machine", "laparoscopy tower", "ventilator", "monitor"],
        staff_count=5,
        capacity_beds=50,
        recency_of_page_update_months=6,
        specialties=[],
        procedures=[],
        capability_claims=[],
    )
    base.update(overrides)
    return FacilityFacts(**base)


# ---------------------------------------------------------------------------
# detect_missing_equipment
# ---------------------------------------------------------------------------


def test_missing_equipment_empty_list_high():
    cap = _capability(CapabilityType.SURGERY_APPENDECTOMY)
    facts = _facts(equipment=[])
    result = detect_missing_equipment(cap, facts)
    assert result is not None
    assert result.contradiction_type == ContradictionType.MISSING_EQUIPMENT
    assert result.severity == "HIGH"
    assert result.facility_id == "vf_test"
    assert result.evidence_for == cap.evidence_refs


def test_missing_equipment_non_empty_missing_core_medium():
    cap = _capability(CapabilityType.SURGERY_GENERAL)
    facts = _facts(equipment=["x-ray", "ultrasound"])
    result = detect_missing_equipment(cap, facts)
    assert result is not None
    assert result.severity == "MEDIUM"


def test_missing_equipment_present_returns_none():
    cap = _capability(CapabilityType.SURGERY_APPENDECTOMY)
    facts = _facts(equipment=["Anesthesia Machine", "Laparoscopy Tower"])
    assert detect_missing_equipment(cap, facts) is None


def test_missing_equipment_requires_every_core_item():
    cap = _capability(CapabilityType.SURGERY_APPENDECTOMY)
    facts = _facts(equipment=["anesthesia machine", "x-ray"])
    result = detect_missing_equipment(cap, facts)
    assert result is not None
    assert result.severity == "MEDIUM"
    assert "laparoscopy" in result.reasoning


def test_missing_equipment_matches_case_and_punctuation_tolerantly():
    cap = _capability(CapabilityType.ICU)
    facts = _facts(equipment=["ICU VENTILATORS", "bedside-monitor units"])
    assert detect_missing_equipment(cap, facts) is None


def test_missing_equipment_icu_ventilator_present_none():
    cap = _capability(CapabilityType.ICU)
    facts = _facts(equipment=["ventilator", "patient monitor"])
    assert detect_missing_equipment(cap, facts) is None


def test_missing_equipment_irrelevant_capability_returns_none():
    # PHARMACY is not in the allowlist — should be ignored regardless of equipment.
    cap = _capability(CapabilityType.PHARMACY)
    facts = _facts(equipment=[])
    assert detect_missing_equipment(cap, facts) is None


# ---------------------------------------------------------------------------
# detect_missing_staff
# ---------------------------------------------------------------------------


def test_missing_staff_none_high():
    cap = _capability(CapabilityType.ICU)
    facts = _facts(staff_count=None)
    result = detect_missing_staff(cap, facts)
    assert result is not None
    assert result.severity == "HIGH"


def test_missing_staff_zero_high():
    cap = _capability(CapabilityType.SURGERY_APPENDECTOMY)
    facts = _facts(staff_count=0)
    result = detect_missing_staff(cap, facts)
    assert result is not None
    assert result.severity == "HIGH"


def test_missing_staff_below_threshold_medium():
    cap = _capability(CapabilityType.ICU)  # threshold = 3
    facts = _facts(staff_count=2)
    result = detect_missing_staff(cap, facts)
    assert result is not None
    assert result.severity == "MEDIUM"


def test_missing_staff_at_threshold_returns_none():
    cap = _capability(CapabilityType.NEONATAL)  # threshold = 2
    facts = _facts(staff_count=2)
    assert detect_missing_staff(cap, facts) is None


def test_missing_staff_irrelevant_capability_returns_none():
    cap = _capability(CapabilityType.LAB)
    facts = _facts(staff_count=0)
    assert detect_missing_staff(cap, facts) is None


# ---------------------------------------------------------------------------
# detect_volume_mismatch
# ---------------------------------------------------------------------------


def test_volume_mismatch_trauma_low_beds_medium():
    cap = _capability(CapabilityType.TRAUMA)
    facts = _facts(capacity_beds=3)
    result = detect_volume_mismatch(cap, facts)
    assert result is not None
    assert result.contradiction_type == ContradictionType.VOLUME_MISMATCH
    assert result.severity == "MEDIUM"


def test_volume_mismatch_trauma_ok_beds_none():
    cap = _capability(CapabilityType.TRAUMA)
    facts = _facts(capacity_beds=20)
    assert detect_volume_mismatch(cap, facts) is None


def test_volume_mismatch_not_trauma_none():
    cap = _capability(CapabilityType.ICU)
    facts = _facts(capacity_beds=2)
    assert detect_volume_mismatch(cap, facts) is None


def test_volume_mismatch_trauma_unknown_capacity_none():
    cap = _capability(CapabilityType.TRAUMA)
    facts = _facts(capacity_beds=None)
    assert detect_volume_mismatch(cap, facts) is None


# ---------------------------------------------------------------------------
# detect_temporal_unverified
# ---------------------------------------------------------------------------


def test_temporal_unverified_24_7_with_one_doc_medium():
    cap = _capability(CapabilityType.EMERGENCY_24_7)
    facts = _facts(staff_count=1)
    result = detect_temporal_unverified(cap, facts)
    assert result is not None
    assert result.contradiction_type == ContradictionType.TEMPORAL_UNVERIFIED
    assert result.severity == "MEDIUM"


def test_temporal_unverified_24_7_with_many_staff_none():
    cap = _capability(CapabilityType.EMERGENCY_24_7)
    facts = _facts(staff_count=10)
    assert detect_temporal_unverified(cap, facts) is None


def test_temporal_unverified_not_24_7_none():
    cap = _capability(CapabilityType.ICU)
    facts = _facts(staff_count=1)
    assert detect_temporal_unverified(cap, facts) is None


# ---------------------------------------------------------------------------
# detect_stale_data
# ---------------------------------------------------------------------------


def test_stale_data_above_threshold_low():
    cap = _capability(CapabilityType.ICU)
    facts = _facts(recency_of_page_update_months=30)
    result = detect_stale_data(cap, facts)
    assert result is not None
    assert result.contradiction_type == ContradictionType.STALE_DATA
    assert result.severity == "LOW"


def test_stale_data_below_threshold_none():
    cap = _capability(CapabilityType.ICU)
    facts = _facts(recency_of_page_update_months=12)
    assert detect_stale_data(cap, facts) is None


def test_stale_data_unknown_recency_none():
    cap = _capability(CapabilityType.ICU)
    facts = _facts(recency_of_page_update_months=None)
    assert detect_stale_data(cap, facts) is None


# ---------------------------------------------------------------------------
# run_all_heuristics
# ---------------------------------------------------------------------------


def test_run_all_heuristics_icu_empty_equipment_no_staff_returns_two():
    cap = _capability(CapabilityType.ICU)
    facts = _facts(
        equipment=[],
        staff_count=0,
        recency_of_page_update_months=6,
    )
    results = run_all_heuristics(cap, facts)
    types = {c.contradiction_type for c in results}
    assert ContradictionType.MISSING_EQUIPMENT in types
    assert ContradictionType.MISSING_STAFF in types
    assert len(results) == 2
    assert all(c.detected_by == "validator.heuristics_v1" for c in results)


def test_run_all_heuristics_clean_facility_returns_empty():
    cap = _capability(CapabilityType.SURGERY_APPENDECTOMY)
    facts = _facts(
        equipment=["anesthesia machine", "laparoscopy tower"],
        staff_count=4,
        recency_of_page_update_months=6,
    )
    assert run_all_heuristics(cap, facts) == []


# ---------------------------------------------------------------------------
# Fixture-driven sanity check
# ---------------------------------------------------------------------------


def test_fixture_clean_passes_no_contradictions():
    cap = Capability.model_validate_json((FIXTURES / "sample_capability.json").read_text())
    facts_blob = json.loads((FIXTURES / "sample_facts.json").read_text())
    facts = FacilityFacts(**facts_blob["clean"])
    assert run_all_heuristics(cap, facts) == []


def test_fixture_flagged_yields_high_severity_flags():
    cap = Capability.model_validate_json((FIXTURES / "sample_capability.json").read_text())
    facts_blob = json.loads((FIXTURES / "sample_facts.json").read_text())
    facts = FacilityFacts(**facts_blob["flagged"])
    results = run_all_heuristics(cap, facts)
    types = {c.contradiction_type for c in results}
    assert ContradictionType.MISSING_EQUIPMENT in types
    assert ContradictionType.MISSING_STAFF in types
    high = [c for c in results if c.severity == "HIGH"]
    assert len(high) >= 2


@pytest.mark.parametrize(
    "cap_type,equipment,expected_severity",
    [
        (CapabilityType.SURGERY_APPENDECTOMY, [], "HIGH"),
        (CapabilityType.SURGERY_APPENDECTOMY, ["x-ray"], "MEDIUM"),
        (CapabilityType.ICU, [], "HIGH"),
        (CapabilityType.ICU, ["x-ray"], "MEDIUM"),
    ],
)
def test_missing_equipment_severity_matrix(cap_type, equipment, expected_severity):
    cap = _capability(cap_type)
    facts = _facts(equipment=equipment)
    result = detect_missing_equipment(cap, facts)
    assert result is not None
    assert result.severity == expected_severity
