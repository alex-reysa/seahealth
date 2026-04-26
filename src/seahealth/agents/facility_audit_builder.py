"""Pure-function assembler for :class:`FacilityAudit` records.

Joins per-capability outputs (Capability + Contradictions + EvidenceAssessments
+ TrustScore) into the canonical :class:`FacilityAudit` shape consumed by every
UI surface. No I/O, no LLM, no randomness — fully deterministic given inputs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from seahealth.schemas import (
    Capability,
    CapabilityType,
    Contradiction,
    EvidenceAssessment,  # noqa: F401  # carried through DATA_CONTRACT join surface
    FacilityAudit,
    GeoPoint,
    TrustScore,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def build_facility_audit(
    facility_id: str,
    name: str,
    location: GeoPoint,
    capabilities: list[Capability],
    contradictions: list[Contradiction],
    evidence_assessments: list[EvidenceAssessment],
    trust_scores: dict[CapabilityType, TrustScore],
    *,
    mlflow_trace_id: str | None = None,
) -> FacilityAudit:
    """Assemble a :class:`FacilityAudit` from already-computed components.

    The function is pure: given the same inputs it always produces the same
    output (modulo ``last_audited_at`` when ``trust_scores`` is empty, in which
    case we stamp ``utcnow``). Contradictions whose ``facility_id`` does not
    match the audit subject are silently dropped — the caller should usually
    have filtered already, but this guards the contract.

    Args:
        facility_id: Subject facility id; contradictions and trust scores
            should already pertain to this facility.
        name: Display name shown on the Facility Card.
        location: GeoPoint used by the map layer.
        capabilities: All capabilities extracted for this facility.
        contradictions: Contradictions for this facility (filtered here for
            safety).
        evidence_assessments: Validator's per-evidence stances. Currently
            accepted for the join surface but not aggregated into the audit
            (UI renders these via ``trust_scores[*].contradictions``).
        trust_scores: Per-capability TrustScore keyed by CapabilityType.
        mlflow_trace_id: Optional trace id passed through for transparency.

    Returns:
        A fully-validated :class:`FacilityAudit`.
    """
    # ``evidence_assessments`` is part of the join surface and reserved for
    # future use; explicit no-op keeps the import + parameter alive for callers
    # without a ruff/F401 warning.
    _ = evidence_assessments

    filtered_contradictions = [c for c in contradictions if c.facility_id == facility_id]
    scored_contradiction_count = sum(len(ts.contradictions) for ts in trust_scores.values())

    if trust_scores:
        last_audited_at = max(ts.computed_at for ts in trust_scores.values())
    else:
        last_audited_at = _utcnow()

    # Trace id resolution: an explicitly-passed ``mlflow_trace_id`` always wins.
    # Otherwise we walk the capabilities and pick the FIRST non-null trace id we
    # find. The extractor stamps the same id onto every Capability emitted in a
    # single facility run, so "first non-null" is deterministic and avoids the
    # cost of an agreement check.
    resolved_trace_id = mlflow_trace_id
    if resolved_trace_id is None:
        for cap in capabilities:
            cap_trace = getattr(cap, "mlflow_trace_id", None)
            if cap_trace:
                resolved_trace_id = cap_trace
                break

    return FacilityAudit(
        facility_id=facility_id,
        name=name,
        location=location,
        capabilities=list(capabilities),
        trust_scores=dict(trust_scores),
        total_contradictions=(
            scored_contradiction_count if trust_scores else len(filtered_contradictions)
        ),
        last_audited_at=last_audited_at,
        mlflow_trace_id=resolved_trace_id,
    )
