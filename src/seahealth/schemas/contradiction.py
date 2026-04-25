"""Contradiction taxonomy + Contradiction model.

The taxonomy is closed. New types require an explicit DECISIONS.md entry and a schema bump.
"""
from datetime import datetime
from enum import Enum
from typing import List, Literal

from pydantic import BaseModel, Field

from .capability_type import CapabilityType
from .evidence import EvidenceRef

STALE_DATA_THRESHOLD_MONTHS: int = 24  # Evidence older than this trips STALE_DATA.


class ContradictionType(str, Enum):
    """Closed taxonomy of validator-detectable contradictions for the hackathon demo."""

    MISSING_EQUIPMENT = "MISSING_EQUIPMENT"
    MISSING_STAFF = "MISSING_STAFF"
    VOLUME_MISMATCH = "VOLUME_MISMATCH"
    TEMPORAL_UNVERIFIED = "TEMPORAL_UNVERIFIED"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    STALE_DATA = "STALE_DATA"


class Contradiction(BaseModel):
    """A single detected contradiction tying a claim to the evidence that contests it.

    Rendered as a flag in FacilityAudit and RankedFacility.
    """

    contradiction_type: ContradictionType
    capability_type: CapabilityType
    facility_id: str
    evidence_for: List[EvidenceRef] = Field(
        default_factory=list, description="Evidence supporting the original claim."
    )
    evidence_against: List[EvidenceRef] = Field(
        default_factory=list, description="Evidence undermining the claim."
    )
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    reasoning: str = Field(..., description="One-sentence model-generated rationale.")
    detected_by: str = Field(
        ..., description="Validator agent id (e.g. 'validator.equipment_v1')."
    )
    detected_at: datetime
