"""Tests for every schema under seahealth.schemas.

For each model:
  - JSON round-trip preserves equality.
  - Bound/enum violations raise ValidationError.

One small hand-built valid example per model keeps the round-trip blocks short.
"""
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from seahealth.schemas import (
    EMBEDDING_DIM,
    SEVERITY_PENALTY,
    STALE_DATA_THRESHOLD_MONTHS,
    Capability,
    CapabilityType,
    Contradiction,
    ContradictionType,
    EvidenceAssessment,
    EvidenceRef,
    FacilityAudit,
    GeoPoint,
    IndexedDoc,
    MapRegionAggregate,
    ParsedIntent,
    PopulationReference,
    QueryResult,
    RankedFacility,
    SummaryMetrics,
    TrustScore,
)

# ---------------------------------------------------------------------------
# Canonical fixtures (one valid instance per model)
# ---------------------------------------------------------------------------

NOW = datetime(2026, 4, 25, 22, 30, tzinfo=UTC)


def _geo() -> GeoPoint:
    return GeoPoint(lat=25.61, lng=85.14, pin_code="800001")


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        source_doc_id="doc_1",
        facility_id="vf_00001_aiims_patna",
        chunk_id="chunk_1",
        row_id=None,
        span=(0, 42),
        snippet="24/7 emergency surgery available",
        source_type="facility_note",
        source_observed_at=NOW,
        retrieved_at=NOW,
    )


def _capability() -> Capability:
    return Capability(
        facility_id="vf_00001_aiims_patna",
        capability_type=CapabilityType.SURGERY_APPENDECTOMY,
        claimed=True,
        evidence_refs=[_evidence()],
        source_doc_id="doc_1",
        extracted_at=NOW,
        extractor_model="claude-sonnet-4-6",
    )


def _contradiction(severity: str = "MEDIUM") -> Contradiction:
    return Contradiction(
        contradiction_type=ContradictionType.MISSING_EQUIPMENT,
        capability_type=CapabilityType.SURGERY_APPENDECTOMY,
        facility_id="vf_00001_aiims_patna",
        evidence_for=[_evidence()],
        evidence_against=[],
        severity=severity,  # type: ignore[arg-type]
        reasoning="No anesthesia machine listed.",
        detected_by="validator.equipment_v1",
        detected_at=NOW,
    )


def _trust_score(with_med_contradiction: bool = False) -> TrustScore:
    contradictions = [_contradiction("MEDIUM")] if with_med_contradiction else []
    confidence = 0.92
    base = round(confidence * 100)
    penalty = sum(SEVERITY_PENALTY[c.severity] for c in contradictions)
    score = max(0, min(100, base - penalty))
    return TrustScore(
        capability_type=CapabilityType.SURGERY_APPENDECTOMY,
        claimed=True,
        evidence=[_evidence()],
        contradictions=contradictions,
        confidence=confidence,
        confidence_interval=(0.85, 0.95),
        score=score,
        reasoning="Supported by staff roster and equipment inventory.",
        computed_at=NOW,
    )


def _facility_audit() -> FacilityAudit:
    ts = _trust_score(with_med_contradiction=True)
    return FacilityAudit(
        facility_id="vf_00001_aiims_patna",
        name="AIIMS Patna",
        location=_geo(),
        capabilities=[_capability()],
        trust_scores={CapabilityType.SURGERY_APPENDECTOMY: ts},
        total_contradictions=len(ts.contradictions),
        last_audited_at=NOW,
        mlflow_trace_id="trace_abc123",
    )


def _indexed_doc() -> IndexedDoc:
    return IndexedDoc(
        doc_id="doc_1",
        facility_id="vf_00001_aiims_patna",
        text="AIIMS Patna provides 24/7 emergency surgery.",
        embedding=[0.0] * EMBEDDING_DIM,
        chunk_index=0,
        source_type="facility_note",
        source_observed_at=NOW,
        metadata={"region": "Bihar"},
    )


def _query_result() -> QueryResult:
    rf = RankedFacility(
        facility_id="vf_00001_aiims_patna",
        name="AIIMS Patna",
        location=_geo(),
        distance_km=2.4,
        trust_score=_trust_score(),
        contradictions_flagged=0,
        evidence_count=1,
        rank=1,
    )
    return QueryResult(
        query="Which facilities within 50km of Patna can perform an appendectomy?",
        parsed_intent=ParsedIntent(
            capability_type=CapabilityType.SURGERY_APPENDECTOMY,
            location=_geo(),
            radius_km=50.0,
        ),
        ranked_facilities=[rf],
        total_candidates=12,
        query_trace_id="trace_query_1",
        generated_at=NOW,
    )


def _evidence_assessment() -> EvidenceAssessment:
    return EvidenceAssessment(
        evidence_ref_id="ev_1",
        capability_type=CapabilityType.SURGERY_APPENDECTOMY,
        facility_id="vf_00001_aiims_patna",
        stance="verifies",
        reasoning="Roster lists a general surgeon on staff.",
        assessed_at=NOW,
    )


def _summary_metrics() -> SummaryMetrics:
    return SummaryMetrics(
        audited_count=200,
        verified_count=140,
        flagged_count=35,
        last_audited_at=NOW,
        capability_type=CapabilityType.SURGERY_APPENDECTOMY,
    )


def _map_region_aggregate() -> MapRegionAggregate:
    return MapRegionAggregate(
        region_id="IN-BR-PAT",
        region_name="Patna",
        state="Bihar",
        capability_type=CapabilityType.SURGERY_APPENDECTOMY,
        population=2_046_000,
        verified_facilities_count=12,
        flagged_facilities_count=3,
        gap_population=900_000,
        centroid=_geo(),
    )


def _population_reference() -> PopulationReference:
    return PopulationReference(region_id="IN-BR-PAT", population_total=2_046_000)


# ---------------------------------------------------------------------------
# Round-trip tests (one per model)
# ---------------------------------------------------------------------------

ROUND_TRIP_CASES = [
    ("GeoPoint", _geo(), GeoPoint),
    ("EvidenceRef", _evidence(), EvidenceRef),
    ("Capability", _capability(), Capability),
    ("Contradiction", _contradiction(), Contradiction),
    ("TrustScore", _trust_score(), TrustScore),
    ("FacilityAudit", _facility_audit(), FacilityAudit),
    ("IndexedDoc", _indexed_doc(), IndexedDoc),
    ("ParsedIntent", _query_result().parsed_intent, ParsedIntent),
    ("RankedFacility", _query_result().ranked_facilities[0], RankedFacility),
    ("QueryResult", _query_result(), QueryResult),
    ("EvidenceAssessment", _evidence_assessment(), EvidenceAssessment),
    ("SummaryMetrics", _summary_metrics(), SummaryMetrics),
    ("MapRegionAggregate", _map_region_aggregate(), MapRegionAggregate),
    ("PopulationReference", _population_reference(), PopulationReference),
]


@pytest.mark.parametrize(
    "name,instance,model_cls",
    ROUND_TRIP_CASES,
    ids=[c[0] for c in ROUND_TRIP_CASES],
)
def test_json_round_trip(name, instance, model_cls):
    payload = instance.model_dump_json()
    restored = model_cls.model_validate_json(payload)
    assert restored == instance


# ---------------------------------------------------------------------------
# Bound + enum + literal violations
# ---------------------------------------------------------------------------

def test_geopoint_lat_out_of_range():
    with pytest.raises(ValidationError):
        GeoPoint(lat=91.0, lng=0.0)


def test_geopoint_lng_out_of_range():
    with pytest.raises(ValidationError):
        GeoPoint(lat=0.0, lng=181.0)


def test_geopoint_pin_code_too_short():
    with pytest.raises(ValidationError):
        GeoPoint(lat=0.0, lng=0.0, pin_code="1234")


def test_trust_score_confidence_out_of_range():
    with pytest.raises(ValidationError):
        TrustScore(
            capability_type=CapabilityType.ICU,
            claimed=True,
            evidence=[],
            contradictions=[],
            confidence=1.5,
            confidence_interval=(0.0, 1.0),
            score=100,
            reasoning="x",
            computed_at=NOW,
        )


def test_trust_score_confidence_interval_lo_greater_than_hi():
    with pytest.raises(ValidationError):
        TrustScore(
            capability_type=CapabilityType.ICU,
            claimed=True,
            evidence=[],
            contradictions=[],
            confidence=0.7,
            confidence_interval=(0.8, 0.6),
            score=70,
            reasoning="x",
            computed_at=NOW,
        )


def test_trust_score_score_must_match_formula():
    # confidence=0.9 => base=90, no contradictions => expected=90; supplying 80 must fail.
    with pytest.raises(ValidationError):
        TrustScore(
            capability_type=CapabilityType.ICU,
            claimed=True,
            evidence=[],
            contradictions=[],
            confidence=0.9,
            confidence_interval=(0.85, 0.95),
            score=80,
            reasoning="x",
            computed_at=NOW,
        )


def test_trust_score_confidence_interval_normalizes_to_include_confidence():
    score = TrustScore(
        capability_type=CapabilityType.ICU,
        claimed=True,
        evidence=[],
        contradictions=[],
        confidence=0.7,
        confidence_interval=(0.8, 0.9),
        score=70,
        reasoning="x",
        computed_at=NOW,
    )

    assert score.confidence_interval == (0.7, 0.9)


def test_datetime_fields_normalize_to_utc_and_serialize_z():
    ref = EvidenceRef(
        source_doc_id="doc_1",
        facility_id="vf_00001_aiims_patna",
        chunk_id="chunk_1",
        span=(0, 1),
        snippet="x",
        source_type="facility_note",
        source_observed_at="2026-04-26T00:30:00+02:00",
        retrieved_at=datetime(2026, 4, 25, 22, 30),
    )

    assert ref.source_observed_at == datetime(2026, 4, 25, 22, 30, tzinfo=UTC)
    assert ref.retrieved_at == NOW

    payload = json.loads(ref.model_dump_json())
    assert payload["source_observed_at"] == "2026-04-25T22:30:00Z"
    assert payload["retrieved_at"] == "2026-04-25T22:30:00Z"


def test_evidence_span_rejects_negative_offsets():
    with pytest.raises(ValidationError, match="span offsets must be >= 0"):
        EvidenceRef(
            source_doc_id="doc_1",
            facility_id="vf_00001_aiims_patna",
            chunk_id="chunk_1",
            span=(-1, 1),
            snippet="x",
            source_type="facility_note",
            retrieved_at=NOW,
        )


def test_evidence_span_rejects_reversed_offsets():
    with pytest.raises(ValidationError, match="span start must be <= end"):
        EvidenceRef(
            source_doc_id="doc_1",
            facility_id="vf_00001_aiims_patna",
            chunk_id="chunk_1",
            span=(2, 1),
            snippet="x",
            source_type="facility_note",
            retrieved_at=NOW,
        )


def test_map_region_gap_population_non_negative():
    with pytest.raises(ValidationError):
        MapRegionAggregate(
            region_id="IN-BR-PAT",
            region_name="Patna",
            state="Bihar",
            capability_type=CapabilityType.SURGERY_APPENDECTOMY,
            population=2_046_000,
            verified_facilities_count=12,
            flagged_facilities_count=3,
            gap_population=-1,
            centroid=_geo(),
        )


def test_ui_nullable_fields_remain_nullable():
    ref = EvidenceRef(
        source_doc_id="doc_1",
        facility_id="vf_00001_aiims_patna",
        chunk_id="chunk_1",
        row_id=None,
        span=(0, 1),
        snippet="x",
        source_type="facility_note",
        source_observed_at=None,
        retrieved_at=NOW,
    )
    audit = FacilityAudit(
        facility_id="vf_00001_aiims_patna",
        name="AIIMS Patna",
        location=GeoPoint(lat=25.61, lng=85.14, pin_code=None),
        last_audited_at=NOW,
        mlflow_trace_id=None,
    )
    summary = SummaryMetrics(
        audited_count=0,
        verified_count=0,
        flagged_count=0,
        last_audited_at=NOW,
        capability_type=None,
    )

    assert ref.row_id is None
    assert ref.source_observed_at is None
    assert audit.location.pin_code is None
    assert audit.mlflow_trace_id is None
    assert summary.capability_type is None


def test_heuristic_core_equipment_capabilities_are_schema_capabilities():
    from seahealth.agents.heuristics import _CORE_EQUIPMENT

    assert set(_CORE_EQUIPMENT) <= set(CapabilityType)


def test_capability_type_membership():
    assert CapabilityType("ICU") is CapabilityType.ICU
    with pytest.raises(ValueError):
        CapabilityType("BOGUS")


def test_contradiction_type_membership():
    assert ContradictionType("STALE_DATA") is ContradictionType.STALE_DATA
    with pytest.raises(ValueError):
        ContradictionType("NOPE")


def test_indexed_doc_embedding_wrong_length():
    with pytest.raises(ValidationError):
        IndexedDoc(
            doc_id="d",
            text="t",
            embedding=[0.0] * (EMBEDDING_DIM - 1),
            chunk_index=0,
            source_type="facility_note",
        )


def test_indexed_doc_embedding_too_long():
    with pytest.raises(ValidationError):
        IndexedDoc(
            doc_id="d",
            text="t",
            embedding=[0.0] * (EMBEDDING_DIM + 1),
            chunk_index=0,
            source_type="facility_note",
        )


def test_evidence_assessment_stance_literal():
    for stance in ("verifies", "contradicts", "silent"):
        EvidenceAssessment(
            evidence_ref_id="ev",
            capability_type=CapabilityType.ICU,
            facility_id="f",
            stance=stance,  # type: ignore[arg-type]
            reasoning="r",
            assessed_at=NOW,
        )
    with pytest.raises(ValidationError):
        EvidenceAssessment(
            evidence_ref_id="ev",
            capability_type=CapabilityType.ICU,
            facility_id="f",
            stance="maybe",  # type: ignore[arg-type]
            reasoning="r",
            assessed_at=NOW,
        )


def test_parsed_intent_radius_must_be_positive():
    with pytest.raises(ValidationError):
        ParsedIntent(
            capability_type=CapabilityType.ICU,
            location=_geo(),
            radius_km=0.0,
        )


def test_summary_metrics_negative_count():
    with pytest.raises(ValidationError):
        SummaryMetrics(
            audited_count=-1,
            verified_count=0,
            flagged_count=0,
            last_audited_at=NOW,
        )


def test_constants_exported():
    assert STALE_DATA_THRESHOLD_MONTHS == 24
    assert EMBEDDING_DIM == 1024
    assert SEVERITY_PENALTY == {"LOW": 5, "MEDIUM": 15, "HIGH": 30}
