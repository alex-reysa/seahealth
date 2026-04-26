"""Tests for the Naomi taxonomy -> internal-enum mapping."""
from __future__ import annotations

import pytest

from seahealth.eval.naomi_mapping import (
    NAOMI_CAPABILITY_MAP,
    NAOMI_CONTRADICTION_TYPE_MAP,
    UNMAPPED_CAPABILITY_VALUES,
    UNMAPPED_CONTRADICTION_VALUES,
    is_contradiction_label,
    map_capability,
    map_contradiction,
)
from seahealth.schemas import CapabilityType, ContradictionType

# Naomi's documented vocabularies — kept here verbatim so a typo in the mapping
# module trips the tests rather than the eval run.
NAOMI_CONTRADICTION_VOCAB = {
    "capability_equipment_mismatch",
    "capability_staff_mismatch",
    "capability_capacity_mismatch",
    "temporal_coverage_mismatch",
    "vague_claim",
    "stale_or_weak_source",
    "facility_type_mismatch",
    "none",
    "other",
}
NAOMI_CAPABILITY_VOCAB = {
    "surgery",
    "icu",
    "dialysis",
    "emergency_trauma",
    "neonatal",
    "oncology",
    "cardiology",
    "obstetrics",
    "dental",
    "diagnostics",
    "other",
}


@pytest.mark.parametrize(
    "naomi_value, expected",
    [
        ("capability_equipment_mismatch", ContradictionType.MISSING_EQUIPMENT),
        ("capability_staff_mismatch", ContradictionType.MISSING_STAFF),
        ("capability_capacity_mismatch", ContradictionType.VOLUME_MISMATCH),
        ("temporal_coverage_mismatch", ContradictionType.TEMPORAL_UNVERIFIED),
        ("stale_or_weak_source", ContradictionType.STALE_DATA),
        ("vague_claim", None),
        ("facility_type_mismatch", None),
        ("none", None),
        ("other", None),
    ],
)
def test_map_contradiction_known_values(naomi_value, expected):
    assert map_contradiction(naomi_value) == expected


@pytest.mark.parametrize(
    "naomi_value, expected",
    [
        ("surgery", CapabilityType.SURGERY_GENERAL),
        ("icu", CapabilityType.ICU),
        ("dialysis", CapabilityType.DIALYSIS),
        ("emergency_trauma", CapabilityType.TRAUMA),
        ("neonatal", CapabilityType.NEONATAL),
        ("oncology", CapabilityType.ONCOLOGY),
        ("obstetrics", CapabilityType.MATERNAL),
        ("diagnostics", CapabilityType.RADIOLOGY),
        ("cardiology", None),
        ("dental", None),
        ("other", None),
    ],
)
def test_map_capability_known_values(naomi_value, expected):
    assert map_capability(naomi_value) == expected


def test_map_contradiction_handles_blank_and_none():
    assert map_contradiction("") is None
    assert map_contradiction(None) is None
    assert map_contradiction("UNKNOWN_TYPE") is None


def test_map_capability_handles_blank_and_none():
    assert map_capability("") is None
    assert map_capability(None) is None
    assert map_capability("BOGUS") is None


def test_map_is_case_insensitive_and_strips():
    assert map_contradiction("  Capability_Staff_Mismatch  ") == ContradictionType.MISSING_STAFF
    assert map_capability("  ICU ") == CapabilityType.ICU


def test_is_contradiction_label():
    # "none" and blank/None are negatives.
    assert is_contradiction_label("none") is False
    assert is_contradiction_label("") is False
    assert is_contradiction_label(None) is False
    # Any other value (including unmapped) is a contradiction.
    assert is_contradiction_label("capability_staff_mismatch") is True
    assert is_contradiction_label("vague_claim") is True
    assert is_contradiction_label("other") is True


def test_naomi_vocabularies_fully_covered():
    """Every documented Naomi value appears in the mapping (no silent typos)."""
    assert NAOMI_CONTRADICTION_VOCAB <= set(NAOMI_CONTRADICTION_TYPE_MAP)
    assert NAOMI_CAPABILITY_VOCAB <= set(NAOMI_CAPABILITY_MAP)


def test_unmapped_value_sets_are_documented():
    """The advertised "limitations" sets must match what the maps actually mark None."""
    expected_unmapped_contra = {
        k for k, v in NAOMI_CONTRADICTION_TYPE_MAP.items() if v is None and k != "none"
    }
    expected_unmapped_cap = {k for k, v in NAOMI_CAPABILITY_MAP.items() if v is None}
    assert UNMAPPED_CONTRADICTION_VALUES == expected_unmapped_contra
    assert UNMAPPED_CAPABILITY_VALUES == expected_unmapped_cap
    # And these are the values we have to call out in the eval report.
    assert {"vague_claim", "facility_type_mismatch", "other"} <= UNMAPPED_CONTRADICTION_VALUES
    assert {"cardiology", "dental"} <= UNMAPPED_CAPABILITY_VALUES
