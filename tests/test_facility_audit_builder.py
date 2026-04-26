"""Tests for ``seahealth.agents.facility_audit_builder``."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from seahealth.agents.facility_audit_builder import build_facility_audit
from seahealth.schemas import (
    Capability,
    CapabilityType,
    Contradiction,
    ContradictionType,
    EvidenceRef,
    GeoPoint,
    TrustScore,
)

NOW = datetime(2026, 4, 25, 22, 30, tzinfo=UTC)
FACILITY_ID = "vf_00042_janta_hospital_patna"


def _evidence(snippet: str = "snippet", chunk_id: str = "chunk_1") -> EvidenceRef:
    return EvidenceRef(
        source_doc_id="doc_1",
        facility_id=FACILITY_ID,
        chunk_id=chunk_id,
        row_id=None,
        span=(0, len(snippet)),
        snippet=snippet,
        source_type="facility_note",
        source_observed_at=NOW,
        retrieved_at=NOW,
    )


def _capability(cap_type: CapabilityType = CapabilityType.SURGERY_APPENDECTOMY) -> Capability:
    return Capability(
        facility_id=FACILITY_ID,
        capability_type=cap_type,
        claimed=True,
        evidence_refs=[_evidence()],
        source_doc_id="doc_1",
        extracted_at=NOW,
        extractor_model="claude-sonnet-4-6",
    )


def _contradiction(
    cap_type: CapabilityType = CapabilityType.SURGERY_APPENDECTOMY,
    severity: str = "MEDIUM",
    facility_id: str = FACILITY_ID,
) -> Contradiction:
    return Contradiction(
        contradiction_type=ContradictionType.MISSING_STAFF,
        capability_type=cap_type,
        facility_id=facility_id,
        evidence_for=[],
        evidence_against=[],
        severity=severity,  # type: ignore[arg-type]
        reasoning="test reason.",
        detected_by="validator.heuristics_v1",
        detected_at=NOW,
    )


def _trust_score(
    cap_type: CapabilityType,
    contradictions: list[Contradiction],
    *,
    confidence: float = 0.9,
    computed_at: datetime = NOW,
) -> TrustScore:
    base = round(confidence * 100)
    penalty = sum({"LOW": 5, "MEDIUM": 15, "HIGH": 30}[c.severity] for c in contradictions)
    return TrustScore(
        capability_type=cap_type,
        claimed=True,
        evidence=[_evidence()],
        contradictions=contradictions,
        confidence=confidence,
        confidence_interval=(0.0, 1.0),
        score=max(0, min(100, base - penalty)),
        reasoning="ok.",
        computed_at=computed_at,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_single_capability_no_contradictions():
    cap = _capability()
    ts = _trust_score(cap.capability_type, [])
    audit = build_facility_audit(
        facility_id=FACILITY_ID,
        name="Janta Hospital, Patna",
        location=GeoPoint(lat=25.61, lng=85.14, pin_code="800001"),
        capabilities=[cap],
        contradictions=[],
        evidence_assessments=[],
        trust_scores={cap.capability_type: ts},
    )

    assert audit.facility_id == FACILITY_ID
    assert audit.total_contradictions == 0
    assert list(audit.trust_scores.keys()) == [cap.capability_type]
    assert audit.last_audited_at == NOW


def test_two_capabilities_two_contradictions_total():
    cap_a = _capability(CapabilityType.SURGERY_APPENDECTOMY)
    cap_b = _capability(CapabilityType.ICU)
    c_a = _contradiction(CapabilityType.SURGERY_APPENDECTOMY, "HIGH")
    c_b = _contradiction(CapabilityType.ICU, "LOW")
    ts_a = _trust_score(cap_a.capability_type, [c_a])
    ts_b = _trust_score(cap_b.capability_type, [c_b])

    audit = build_facility_audit(
        facility_id=FACILITY_ID,
        name="Janta Hospital",
        location=GeoPoint(lat=25.61, lng=85.14),
        capabilities=[cap_a, cap_b],
        contradictions=[c_a, c_b],
        evidence_assessments=[],
        trust_scores={cap_a.capability_type: ts_a, cap_b.capability_type: ts_b},
    )

    assert audit.total_contradictions == 2
    assert set(audit.trust_scores.keys()) == {cap_a.capability_type, cap_b.capability_type}


def test_filters_contradictions_for_other_facilities():
    cap = _capability()
    ours = _contradiction(severity="MEDIUM")
    theirs = _contradiction(severity="HIGH", facility_id="vf_99999_some_other_facility")
    ts = _trust_score(cap.capability_type, [ours])

    audit = build_facility_audit(
        facility_id=FACILITY_ID,
        name="Janta Hospital",
        location=GeoPoint(lat=25.61, lng=85.14),
        capabilities=[cap],
        contradictions=[ours, theirs],
        evidence_assessments=[],
        trust_scores={cap.capability_type: ts},
    )

    assert audit.total_contradictions == 1


def test_total_contradictions_prefers_scored_contradictions():
    cap = _capability()
    scored = _contradiction(severity="LOW")
    unscored = _contradiction(CapabilityType.ICU, severity="HIGH")
    ts = _trust_score(cap.capability_type, [scored])

    audit = build_facility_audit(
        facility_id=FACILITY_ID,
        name="Janta Hospital",
        location=GeoPoint(lat=25.61, lng=85.14),
        capabilities=[cap],
        contradictions=[scored, unscored],
        evidence_assessments=[],
        trust_scores={cap.capability_type: ts},
    )

    assert audit.total_contradictions == 1


def test_last_audited_at_honors_max_trust_score_computed_at():
    cap_a = _capability(CapabilityType.SURGERY_APPENDECTOMY)
    cap_b = _capability(CapabilityType.ICU)
    earlier = NOW - timedelta(hours=2)
    later = NOW + timedelta(minutes=15)
    ts_a = _trust_score(cap_a.capability_type, [], computed_at=earlier)
    ts_b = _trust_score(cap_b.capability_type, [], computed_at=later)

    audit = build_facility_audit(
        facility_id=FACILITY_ID,
        name="Janta Hospital",
        location=GeoPoint(lat=25.61, lng=85.14),
        capabilities=[cap_a, cap_b],
        contradictions=[],
        evidence_assessments=[],
        trust_scores={cap_a.capability_type: ts_a, cap_b.capability_type: ts_b},
    )

    assert audit.last_audited_at == later


def test_mlflow_trace_id_passes_through():
    cap = _capability()
    ts = _trust_score(cap.capability_type, [])
    audit = build_facility_audit(
        facility_id=FACILITY_ID,
        name="Janta Hospital",
        location=GeoPoint(lat=25.61, lng=85.14),
        capabilities=[cap],
        contradictions=[],
        evidence_assessments=[],
        trust_scores={cap.capability_type: ts},
        mlflow_trace_id="trace-abc-123",
    )

    assert audit.mlflow_trace_id == "trace-abc-123"


def test_mlflow_trace_id_picked_from_caps_when_not_explicit():
    """When no explicit trace id is passed, builder picks first non-null from caps."""
    cap_a = _capability(CapabilityType.SURGERY_APPENDECTOMY).model_copy(
        update={"mlflow_trace_id": None}
    )
    cap_b = _capability(CapabilityType.ICU).model_copy(
        update={"mlflow_trace_id": "local::vf_00042_janta_hospital_patna::run-uuid-1"}
    )
    cap_c = _capability(CapabilityType.LAB).model_copy(
        update={"mlflow_trace_id": "local::vf_00042_janta_hospital_patna::run-uuid-2"}
    )
    ts_a = _trust_score(cap_a.capability_type, [])
    ts_b = _trust_score(cap_b.capability_type, [])
    ts_c = _trust_score(cap_c.capability_type, [])

    audit = build_facility_audit(
        facility_id=FACILITY_ID,
        name="Janta Hospital",
        location=GeoPoint(lat=25.61, lng=85.14),
        capabilities=[cap_a, cap_b, cap_c],
        contradictions=[],
        evidence_assessments=[],
        trust_scores={
            cap_a.capability_type: ts_a,
            cap_b.capability_type: ts_b,
            cap_c.capability_type: ts_c,
        },
    )

    # First non-null wins (cap_b's), even though cap_a is first overall.
    assert audit.mlflow_trace_id == "local::vf_00042_janta_hospital_patna::run-uuid-1"


def test_explicit_trace_id_wins_over_caps():
    """Explicit ``mlflow_trace_id`` takes precedence over capability-borne ones."""
    cap = _capability().model_copy(update={"mlflow_trace_id": "from-cap"})
    ts = _trust_score(cap.capability_type, [])
    audit = build_facility_audit(
        facility_id=FACILITY_ID,
        name="Janta Hospital",
        location=GeoPoint(lat=25.61, lng=85.14),
        capabilities=[cap],
        contradictions=[],
        evidence_assessments=[],
        trust_scores={cap.capability_type: ts},
        mlflow_trace_id="explicit-trace",
    )

    assert audit.mlflow_trace_id == "explicit-trace"
