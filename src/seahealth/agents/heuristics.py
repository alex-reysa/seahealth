"""Pure-function heuristic detectors for the Validator agent.

Each detector takes a `Capability` claim plus a normalized `FacilityFacts` snapshot
and returns either a `Contradiction` (or list of them) or `None`.  No I/O, no LLM
calls — purely deterministic so they are trivial to unit-test.

The aggregator `run_all_heuristics` runs every detector and returns the union of
non-None contradictions, populating the boilerplate fields (facility_id,
capability_type, evidence_for, detected_by, detected_at) consistently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from seahealth.schemas import (
    STALE_DATA_THRESHOLD_MONTHS,
    Capability,
    CapabilityType,
    Contradiction,
    ContradictionType,
)

# ---------------------------------------------------------------------------
# Per-capability allowlists / thresholds
# ---------------------------------------------------------------------------

# Core equipment keywords that must be matched (case-insensitive substring) in
# `FacilityFacts.equipment` for the capability to be considered equipped.
_CORE_EQUIPMENT: dict[CapabilityType, list[str]] = {
    CapabilityType.SURGERY_GENERAL: ["anesthesia", "laparoscopy"],
    CapabilityType.SURGERY_APPENDECTOMY: ["anesthesia", "laparoscopy"],
    CapabilityType.ICU: ["ventilator", "monitor"],
}

# Minimum staff_count required for the capability to be considered staffed.
_STAFF_THRESHOLDS: dict[CapabilityType, int] = {
    CapabilityType.ICU: 3,
    CapabilityType.SURGERY_GENERAL: 2,
    CapabilityType.SURGERY_APPENDECTOMY: 2,
    CapabilityType.NEONATAL: 2,
}

_SURGERY_TYPES = {
    CapabilityType.SURGERY_GENERAL,
    CapabilityType.SURGERY_APPENDECTOMY,
}


# ---------------------------------------------------------------------------
# FacilityFacts dataclass — the validator's normalized view of source-of-truth
# tabular data for one facility, derived from the source CSV / staff roster.
# ---------------------------------------------------------------------------


@dataclass
class FacilityFacts:
    """Normalized facts for a facility, used as the heuristic ground truth."""

    facility_id: str
    equipment: list[str] = field(default_factory=list)
    staff_count: int | None = None
    capacity_beds: int | None = None
    recency_of_page_update_months: int | None = None  # months since last update
    specialties: list[str] = field(default_factory=list)
    procedures: list[str] = field(default_factory=list)
    capability_claims: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _has_any(items: list[str], keywords: list[str]) -> bool:
    """Return True if any keyword appears (case-insensitive substring) in any item."""
    lowered = [s.lower() for s in items]
    return any(any(kw.lower() in item for item in lowered) for kw in keywords)


def _missing_keywords(items: list[str], keywords: list[str]) -> list[str]:
    """Return keywords that do NOT appear in any item (case-insensitive substring)."""
    lowered = [s.lower() for s in items]
    return [kw for kw in keywords if not any(kw.lower() in item for item in lowered)]


def _build(
    *,
    contradiction_type: ContradictionType,
    cap: Capability,
    facts: FacilityFacts,
    severity: str,
    reasoning: str,
    validator_id: str,
) -> Contradiction:
    return Contradiction(
        contradiction_type=contradiction_type,
        capability_type=cap.capability_type,
        facility_id=facts.facility_id,
        evidence_for=list(cap.evidence_refs),
        evidence_against=[],
        severity=severity,  # type: ignore[arg-type]
        reasoning=reasoning,
        detected_by=validator_id,
        detected_at=_utcnow(),
    )


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def detect_missing_equipment(
    cap: Capability,
    facts: FacilityFacts,
    *,
    validator_id: str = "validator.heuristics_v1",
) -> Contradiction | None:
    """Flag MISSING_EQUIPMENT for surgery/ICU capabilities lacking core gear.

    HIGH if the equipment list is empty, MEDIUM if it exists but lacks a core item.
    """
    if cap.capability_type not in _CORE_EQUIPMENT:
        return None

    core = _CORE_EQUIPMENT[cap.capability_type]

    if not facts.equipment:
        return _build(
            contradiction_type=ContradictionType.MISSING_EQUIPMENT,
            cap=cap,
            facts=facts,
            severity="HIGH",
            reasoning=(
                f"No equipment recorded for facility while {cap.capability_type.value} "
                f"requires core gear ({', '.join(core)})."
            ),
            validator_id=validator_id,
        )

    if not _has_any(facts.equipment, core):
        missing = _missing_keywords(facts.equipment, core)
        return _build(
            contradiction_type=ContradictionType.MISSING_EQUIPMENT,
            cap=cap,
            facts=facts,
            severity="MEDIUM",
            reasoning=(
                f"Equipment list lacks core item(s) for {cap.capability_type.value}: "
                f"{', '.join(missing)}."
            ),
            validator_id=validator_id,
        )

    return None


def detect_missing_staff(
    cap: Capability,
    facts: FacilityFacts,
    *,
    validator_id: str = "validator.heuristics_v1",
) -> Contradiction | None:
    """Flag MISSING_STAFF for staffing-sensitive capabilities below threshold.

    HIGH if staff_count is None or 0, MEDIUM if non-zero but below threshold.
    """
    if cap.capability_type not in _STAFF_THRESHOLDS:
        return None

    threshold = _STAFF_THRESHOLDS[cap.capability_type]

    if facts.staff_count is None or facts.staff_count == 0:
        return _build(
            contradiction_type=ContradictionType.MISSING_STAFF,
            cap=cap,
            facts=facts,
            severity="HIGH",
            reasoning=(
                f"Staff roster reports no staff for {cap.capability_type.value} "
                f"(requires at least {threshold})."
            ),
            validator_id=validator_id,
        )

    if facts.staff_count < threshold:
        return _build(
            contradiction_type=ContradictionType.MISSING_STAFF,
            cap=cap,
            facts=facts,
            severity="MEDIUM",
            reasoning=(
                f"Staff count {facts.staff_count} is below the {threshold}-person "
                f"threshold for {cap.capability_type.value}."
            ),
            validator_id=validator_id,
        )

    return None


def detect_volume_mismatch(
    cap: Capability,
    facts: FacilityFacts,
    *,
    validator_id: str = "validator.heuristics_v1",
) -> Contradiction | None:
    """Flag VOLUME_MISMATCH if a TRAUMA claim is paired with very low bed capacity."""
    if cap.capability_type != CapabilityType.TRAUMA:
        return None
    if facts.capacity_beds is None or facts.capacity_beds >= 5:
        return None

    return _build(
        contradiction_type=ContradictionType.VOLUME_MISMATCH,
        cap=cap,
        facts=facts,
        severity="MEDIUM",
        reasoning=(
            f"TRAUMA capacity claim is implausible at {facts.capacity_beds} bed(s)."
        ),
        validator_id=validator_id,
    )


def detect_temporal_unverified(
    cap: Capability,
    facts: FacilityFacts,
    *,
    validator_id: str = "validator.heuristics_v1",
) -> Contradiction | None:
    """Flag TEMPORAL_UNVERIFIED if a 24/7 claim is paired with a tiny staff roster."""
    if cap.capability_type != CapabilityType.EMERGENCY_24_7:
        return None
    if facts.staff_count is None or facts.staff_count > 2:
        return None

    return _build(
        contradiction_type=ContradictionType.TEMPORAL_UNVERIFIED,
        cap=cap,
        facts=facts,
        severity="MEDIUM",
        reasoning=(
            f"24/7 emergency claim is unverifiable with only {facts.staff_count} staff."
        ),
        validator_id=validator_id,
    )


def detect_stale_data(
    cap: Capability,
    facts: FacilityFacts,
    *,
    validator_id: str = "validator.heuristics_v1",
) -> Contradiction | None:
    """Flag STALE_DATA when the source page is older than the stale threshold."""
    if facts.recency_of_page_update_months is None:
        return None
    if facts.recency_of_page_update_months <= STALE_DATA_THRESHOLD_MONTHS:
        return None

    return _build(
        contradiction_type=ContradictionType.STALE_DATA,
        cap=cap,
        facts=facts,
        severity="LOW",
        reasoning=(
            f"Source page last updated {facts.recency_of_page_update_months} months ago, "
            f"exceeding the {STALE_DATA_THRESHOLD_MONTHS}-month stale threshold."
        ),
        validator_id=validator_id,
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def run_all_heuristics(
    cap: Capability,
    facts: FacilityFacts,
    *,
    validator_id: str = "validator.heuristics_v1",
) -> list[Contradiction]:
    """Apply all detectors and return the union of non-None Contradictions."""
    out: list[Contradiction] = []
    for detector in (
        detect_missing_equipment,
        detect_missing_staff,
        detect_volume_mismatch,
        detect_temporal_unverified,
        detect_stale_data,
    ):
        result = detector(cap, facts, validator_id=validator_id)
        if result is not None:
            out.append(result)
    return out
