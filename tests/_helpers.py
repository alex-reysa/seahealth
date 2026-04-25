"""Shared schema-instance factories for SeaHealth tests.

Each factory returns a Pydantic-valid instance that can be passed straight
into agent/pipeline code. Override any field via keyword arguments.

Example
-------
>>> from tests._helpers import make_capability, make_contradiction
>>> cap = make_capability(facility_id="vf_demo")
>>> contra = make_contradiction(facility_id=cap.facility_id, severity="HIGH")

These helpers intentionally produce *deterministic* defaults (no
``datetime.now()``, no random ids) so tests stay reproducible.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from seahealth.schemas import (
    SEVERITY_PENALTY,
    Capability,
    CapabilityType,
    Contradiction,
    ContradictionType,
    EvidenceRef,
    FacilityAudit,
    GeoPoint,
    TrustScore,
)

# ---------------------------------------------------------------------------
# Canonical fixture timestamp + facility id
# ---------------------------------------------------------------------------

#: Single shared "now" so every helper stays deterministic.
NOW: datetime = datetime(2026, 4, 25, 22, 30, tzinfo=UTC)

#: Default facility id used when callers don't override one.
DEFAULT_FACILITY_ID: str = "vf_test_001"


def _apply_overrides(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    out = dict(defaults)
    out.update(overrides)
    return out


# ---------------------------------------------------------------------------
# EvidenceRef
# ---------------------------------------------------------------------------


def make_evidence_ref(**overrides: Any) -> EvidenceRef:
    """Construct a Pydantic-valid ``EvidenceRef`` for tests."""
    snippet = overrides.get("snippet", "general surgery available 24/7")
    defaults: dict[str, Any] = {
        "source_doc_id": "doc_test_1",
        "facility_id": DEFAULT_FACILITY_ID,
        "chunk_id": "chunk_1",
        "row_id": None,
        "span": (0, len(snippet)),
        "snippet": snippet,
        "source_type": "facility_note",
        "source_observed_at": NOW,
        "retrieved_at": NOW,
    }
    return EvidenceRef(**_apply_overrides(defaults, overrides))


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


def make_capability(
    facility_id: str = DEFAULT_FACILITY_ID,
    capability_type: CapabilityType = CapabilityType.SURGERY_GENERAL,
    **overrides: Any,
) -> Capability:
    """Construct a Pydantic-valid ``Capability`` with one evidence ref."""
    evidence_refs = overrides.pop(
        "evidence_refs",
        [make_evidence_ref(facility_id=facility_id)],
    )
    defaults: dict[str, Any] = {
        "facility_id": facility_id,
        "capability_type": capability_type,
        "claimed": True,
        "evidence_refs": evidence_refs,
        "source_doc_id": "doc_test_1",
        "extracted_at": NOW,
        "extractor_model": "claude-sonnet-4-6",
    }
    return Capability(**_apply_overrides(defaults, overrides))


# ---------------------------------------------------------------------------
# Contradiction
# ---------------------------------------------------------------------------


def make_contradiction(**overrides: Any) -> Contradiction:
    """Construct a Pydantic-valid ``Contradiction`` (default: MEDIUM severity)."""
    defaults: dict[str, Any] = {
        "contradiction_type": ContradictionType.MISSING_STAFF,
        "capability_type": CapabilityType.SURGERY_GENERAL,
        "facility_id": DEFAULT_FACILITY_ID,
        "evidence_for": [],
        "evidence_against": [],
        "severity": "MEDIUM",
        "reasoning": "Test contradiction reasoning.",
        "detected_by": "validator.test",
        "detected_at": NOW,
    }
    return Contradiction(**_apply_overrides(defaults, overrides))


# ---------------------------------------------------------------------------
# TrustScore
# ---------------------------------------------------------------------------


def make_trust_score(**overrides: Any) -> TrustScore:
    """Construct a ``TrustScore`` whose ``score`` matches the canonical formula.

    Callers may pass ``confidence`` and/or ``contradictions``; the score is
    auto-derived (``round(confidence*100) - severity_penalty``) unless an
    explicit ``score`` override is supplied.
    """
    confidence = overrides.pop("confidence", 0.9)
    contradictions = overrides.pop("contradictions", [])
    base = round(confidence * 100)
    penalty = sum(SEVERITY_PENALTY[c.severity] for c in contradictions)
    derived_score = max(0, min(100, base - penalty))

    defaults: dict[str, Any] = {
        "capability_type": CapabilityType.SURGERY_GENERAL,
        "claimed": True,
        "evidence": [make_evidence_ref()],
        "contradictions": contradictions,
        "confidence": confidence,
        "confidence_interval": (
            max(0.0, confidence - 0.05),
            min(1.0, confidence + 0.02),
        ),
        "score": derived_score,
        "reasoning": "Templated test reasoning.",
        "computed_at": NOW,
    }
    return TrustScore(**_apply_overrides(defaults, overrides))


# ---------------------------------------------------------------------------
# FacilityAudit
# ---------------------------------------------------------------------------


def make_facility_audit(**overrides: Any) -> FacilityAudit:
    """Construct a Pydantic-valid ``FacilityAudit``.

    Default shape: one SURGERY_GENERAL capability with one trust score and
    zero contradictions. Override ``capabilities`` / ``trust_scores`` /
    ``total_contradictions`` to tailor.
    """
    facility_id = overrides.pop("facility_id", DEFAULT_FACILITY_ID)
    cap = make_capability(facility_id=facility_id)
    ts = make_trust_score(capability_type=cap.capability_type)
    defaults: dict[str, Any] = {
        "facility_id": facility_id,
        "name": "Test Facility",
        "location": GeoPoint(lat=25.61, lng=85.14, pin_code="800001"),
        "capabilities": [cap],
        "trust_scores": {cap.capability_type: ts},
        "total_contradictions": 0,
        "last_audited_at": NOW,
        "mlflow_trace_id": None,
    }
    return FacilityAudit(**_apply_overrides(defaults, overrides))


__all__ = [
    "DEFAULT_FACILITY_ID",
    "NOW",
    "make_capability",
    "make_contradiction",
    "make_evidence_ref",
    "make_facility_audit",
    "make_trust_score",
]
