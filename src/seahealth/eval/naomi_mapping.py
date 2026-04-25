"""Mapping between Naomi's hand-labeling taxonomy and our internal enums.

Naomi labels facility-capability claims with her own controlled vocabulary
(see `docs/tasks/naomi_labeling_guide.md`). This module is the only place
that translates her vocabulary into the closed enums defined in
`seahealth.schemas`.

Some Naomi values do not have a clean enum match. Those are mapped to
`None` and surfaced in the eval report's "Limitations" section. Keeping
the mapping explicit (rather than fuzzy) is a deliberate choice — silent
fuzzy mappings would inflate precision/recall by hiding genuine
mis-translations.
"""
from __future__ import annotations

from seahealth.schemas import CapabilityType, ContradictionType

# Sentinel value used in Naomi's CSV when she explicitly recorded "no contradiction".
NAOMI_NO_CONTRADICTION = "none"

# Naomi's contradiction_type vocabulary -> our ContradictionType (or None when
# the closed enum has no good match for that label class).
NAOMI_CONTRADICTION_TYPE_MAP: dict[str, ContradictionType | None] = {
    "capability_equipment_mismatch": ContradictionType.MISSING_EQUIPMENT,
    "capability_staff_mismatch": ContradictionType.MISSING_STAFF,
    "capability_capacity_mismatch": ContradictionType.VOLUME_MISMATCH,
    "temporal_coverage_mismatch": ContradictionType.TEMPORAL_UNVERIFIED,
    "stale_or_weak_source": ContradictionType.STALE_DATA,
    # Naomi categories with no clean closed-enum target. Counted as
    # contradictions for recall purposes but cannot be matched on type.
    "vague_claim": None,
    "facility_type_mismatch": None,
    # Explicit "no contradiction" — kept in the map so callers can round-trip.
    NAOMI_NO_CONTRADICTION: None,
    "other": None,
}

# Naomi's claimed_capability vocabulary -> our CapabilityType (or None when
# the closed enum has no good match).
NAOMI_CAPABILITY_MAP: dict[str, CapabilityType | None] = {
    "surgery": CapabilityType.SURGERY_GENERAL,
    "icu": CapabilityType.ICU,
    "dialysis": CapabilityType.DIALYSIS,
    "emergency_trauma": CapabilityType.TRAUMA,
    "neonatal": CapabilityType.NEONATAL,
    "oncology": CapabilityType.ONCOLOGY,
    "obstetrics": CapabilityType.MATERNAL,
    # Closest analogue: imaging/lab work. Documented in eval report.
    "diagnostics": CapabilityType.RADIOLOGY,
    # No clean enum target. Documented in eval report.
    "cardiology": None,
    "dental": None,
    "other": None,
}

# Values Naomi may emit that we cannot translate. Surface in the report.
UNMAPPED_CONTRADICTION_VALUES: frozenset[str] = frozenset(
    {k for k, v in NAOMI_CONTRADICTION_TYPE_MAP.items() if v is None}
    - {NAOMI_NO_CONTRADICTION}
)
UNMAPPED_CAPABILITY_VALUES: frozenset[str] = frozenset(
    {k for k, v in NAOMI_CAPABILITY_MAP.items() if v is None}
)


def _normalize(naomi_value: str | None) -> str:
    """Lowercase + strip; treat None/empty as ''."""
    if naomi_value is None:
        return ""
    return str(naomi_value).strip().lower()


def map_contradiction(naomi_value: str | None) -> ContradictionType | None:
    """Translate one of Naomi's contradiction_type values to our enum.

    Returns ``None`` for ``"none"``, blanks, unknown values, or values that
    Naomi uses but we have no clean enum target for (e.g. ``vague_claim``).
    Callers that need to distinguish "not a contradiction" from "contradiction
    but unmapped" should use :func:`is_contradiction_label`.
    """
    return NAOMI_CONTRADICTION_TYPE_MAP.get(_normalize(naomi_value))


def map_capability(naomi_value: str | None) -> CapabilityType | None:
    """Translate one of Naomi's claimed_capability values to our enum.

    Returns ``None`` for unknown values or values without a clean enum target
    (``cardiology``, ``dental``, ``other``).
    """
    return NAOMI_CAPABILITY_MAP.get(_normalize(naomi_value))


def is_contradiction_label(naomi_value: str | None) -> bool:
    """True if Naomi flagged this row as a contradiction.

    Treats ``"none"`` and the empty string as non-contradictions; every other
    value (including ``vague_claim``, ``other``, and unrecognized strings) is
    treated as a contradiction. This matters for recall: a contradiction Naomi
    cannot label cleanly is still a contradiction.
    """
    norm = _normalize(naomi_value)
    if norm in {"", NAOMI_NO_CONTRADICTION}:
        return False
    return True


__all__ = [
    "NAOMI_CAPABILITY_MAP",
    "NAOMI_CONTRADICTION_TYPE_MAP",
    "NAOMI_NO_CONTRADICTION",
    "UNMAPPED_CAPABILITY_VALUES",
    "UNMAPPED_CONTRADICTION_VALUES",
    "is_contradiction_label",
    "map_capability",
    "map_contradiction",
]
