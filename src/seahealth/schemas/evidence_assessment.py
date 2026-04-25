"""EvidenceAssessment — Validator's per-evidence stance, joined into the Facility Audit View."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .capability_type import CapabilityType


class EvidenceAssessment(BaseModel):
    """Validator's per-evidence stance, joined into the Facility Audit View.

    Each row pins one evidence span to one capability claim and records whether the
    Validator agent thinks that span verifies, contradicts, or is silent on the claim.
    """

    evidence_ref_id: str = Field(
        ..., description="Stable id of the EvidenceRef this assessment refers to."
    )
    capability_type: CapabilityType = Field(
        ..., description="The capability this evidence was assessed against."
    )
    facility_id: str = Field(..., description="Facility the evidence belongs to.")
    stance: Literal["verifies", "contradicts", "silent"] = Field(
        ...,
        description="Validator stance on this evidence relative to the capability claim.",
    )
    reasoning: str = Field(
        ..., description="One-sentence Validator rationale for the stance."
    )
    assessed_at: datetime = Field(..., description="When the Validator produced this stance.")
